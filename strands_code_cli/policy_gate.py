"""Single-HITL permissions gate: classifier + ask + batching (TOOL-03, D-01..D-04, D-12).

Exactly ONE :class:`HumanInTheLoop` instance carries the allowlist plus a
custom classifier (TOML matching, owns the verdict) and a custom ask
(rendering only). A second instance would collide at construction
(``strands:human-in-the-loop`` name rule) — see the tracer test module.

Secure-reading note on 03-PLAN.md resolved item 5: it states
"Deny → requires_approval False ... so ask short-circuits". Taken
literally that would ``Proceed()`` (run) the denied tool — fail-open.
Implemented instead as requires-approval True with a ``DENY:``-prefixed
reason so the ask layer short-circuits to a printed refusal and returns
``"n"`` (deny) without prompting. Fail-closed wins over literal text.

Layer split: ``PolicyClassifier`` reads the ``BeforeToolCallEvent`` tool
name + input and calls :func:`strands_code_cli.policy.decide`; the ask
renders full detail (exact command or diff + one-line risk reason, D-01)
inside :func:`strands_code_cli.output.output_context`. D-03 remember
writes happen inside the ask (which closes over tool name + input via
the classifier's last-decision context), never in ``evaluate`` (which
stays ``default_evaluate``). No ``enable_trust`` (wrong granularity),
no second handler.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import queue
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterator

from strands.vended_interventions.hitl import HumanInTheLoop
from strands.vended_interventions.hitl.classifier import ClassifierResult

from strands_code_cli.output import output_context
from strands_code_cli.policy import (
    Allow,
    Deny,
    PolicyConfig,
    Prompt,
    Rule,
    decide,
    normalise_command,
)

logger = logging.getLogger(__name__)

_ASK_OPTIONS = "Approve? [y/n/always/never]"
_ASK_SUFFIX = _ASK_OPTIONS + " "
_ANSWER_PROMPT = "> "

gate_open = threading.Event()
"""Set while the gate ``ask`` prompt waits for an answer.

The steering reader checks this flag and never consumes stdin while it
is set, so a steering line can never be consumed as an answer (and
the prompt answer is never diverted into steering). Covers both the
typed ``input()`` fallback and the arrow-key dialog."""

PLAN_MUTATING_TOOLS = ("write", "edit", "shell", "python_repl")
"""Tools denied in Plan mode (MODE-01, D-03).

Read-only = ``read`` + ``search`` (gate allowlist) plus GET-shaped
``web_fetch``/``web_search`` (pre-allowed, harmless). ``python_repl``
is mutating-by-construction (interior ``open()``/write, residual
T-03-08) so it is denied, not merely discouraged.
"""

PLAN_DENY_TEMPLATE = "Plan mode is read-only — {tool} skipped, continuing."
"""Mode-vocabulary denial (never a policy-rule or diff-mode word)."""


class BatchState:
    """Turn-scoped approval cache keyed by matched-rule signature (D-04).

    Tool calls execute sequentially, so upfront listing of future actions
    is impossible: the first matching call per (signature, turn) prompts
    with full detail naming the covering rule; later same-signature
    APPROVED calls in the turn proceed silently and are recorded. Denied
    calls never cover — a denied-then-retried call re-prompts
    (fail-closed). Reset per turn via :meth:`bind_turn` (called from
    ``loop.py`` before each ``agent(text)``); the cache never crosses
    turns. Also keeps the covered-action log for ``/policy last``.
    """

    def __init__(self) -> None:
        self._turn: str | None = None
        self._covered: set[tuple[str, ...]] = set()
        self._log: list[str] = []

    def bind_turn(self, turn_id: str) -> None:
        """Start a new turn: clear per-turn coverage, keep the log."""
        self._turn = turn_id
        self._covered = set()

    def is_covered(self, signature: tuple[str, ...]) -> bool:
        """True when this signature already prompted this turn."""
        return signature in self._covered

    def mark(self, signature: tuple[str, ...], description: str) -> None:
        """Record a covered signature plus its human-readable description."""
        self._covered.add(signature)
        self._log.append(description)

    def covered(self) -> list[str]:
        """Covered-action descriptions for ``/policy last``."""
        return list(self._log)

    def record(self, description: str) -> None:
        """Log a one-shot outcome for ``/policy last`` WITHOUT covering.

        Denials never cover: a denied-then-retried call must re-prompt
        (fail-closed). Only approvals cover, keeping the D-04
        same-signature silence for the approved case.
        """
        self._log.append(description)


class TurnCancelled(Exception):
    """Worker-side abort: cancel fired while awaiting a prompt answer.

    Raised in the SDK worker thread when the turn's cancel event is set.
    Never swallowed: ``ask`` re-raises past its fail-closed handler so the
    worker exits instead of parking on stdin.
    """


class _ApprovalRequest:
    """One prompt handoff from the SDK worker thread to the pump thread."""

    def __init__(self, prompt: Callable[[], str]) -> None:
        self._prompt = prompt
        self._done = threading.Event()
        self.answer: str | None = None

    def run_prompt(self) -> None:
        """Execute the prompt in the pump thread (KeyboardInterrupt propagates)."""
        try:
            self.answer = self._prompt()
        finally:
            self._done.set()

    def wait_answer(self, cancel: threading.Event | None) -> str:
        """Worker side: block for the answer; abort promptly on cancel.

        A set done-flag with no answer means the pump died without
        answering (Ctrl-C took the dialog's cancel path while prompt_toolkit
        owned SIGINT, so the turn handler never set cancel): that is a
        cancellation too, never an ``AssertionError`` — the bare assert's
        empty message used to surface as a blank "failed closed" line.
        """
        while not self._done.wait(0.05):
            if cancel is not None and cancel.is_set():
                raise TurnCancelled()
        if cancel is not None and cancel.is_set():
            raise TurnCancelled()
        if self.answer is None:
            raise TurnCancelled()
        return self.answer


class ApprovalBroker:
    """Hands approval prompts from the SDK worker thread to the pump thread.

    The SDK invokes ``ask`` inside its event-loop worker thread
    (``ThreadPoolExecutor`` + ``asyncio.run``), where blocking on stdin is
    fatal twice over: SIGINT lands in the main thread (parked in
    ``future.result()``), so the worker stays parked in the read while the
    main thread unwinds — executor ``shutdown(wait=True)`` then stalls
    until Enter, and a second Ctrl-C leaks the parked worker, which steals
    every later prompt's input (the double-Ctrl-C wedge). Prompt_toolkit
    is unusable there too: ``asyncio.run`` cannot nest in the running loop
    (observed ``run_async was never awaited`` → fail-closed deny).

    So the worker hands the prompt to the pump thread and waits on a
    per-request event plus the turn's cancel signal; the pump (main thread
    during ``_invoke_agent``) prompts synchronously, where signals and
    ``asyncio.run`` behave. With no pump registered (tests, direct calls)
    the prompt runs inline, legacy behaviour.
    """

    def __init__(self) -> None:
        self._queue: queue.Queue[_ApprovalRequest] = queue.Queue()
        self._pumping = threading.Event()
        self._cancel: threading.Event | None = None
        self._pump_ident: int | None = None

    @contextmanager
    def pump(self, cancel: threading.Event) -> Iterator["ApprovalBroker"]:
        """Serve prompts on this thread until the turn ends."""
        old_cancel, old_ident = self._cancel, self._pump_ident
        self._cancel = cancel
        self._pump_ident = threading.get_ident()
        self._pumping.set()
        try:
            yield self
        finally:
            self._pumping.clear()
            self._cancel = old_cancel
            self._pump_ident = old_ident

    def request(self, prompt: Callable[[], str]) -> str:
        """Worker side: have the prompt answered by the pump thread."""
        if not self._pumping.is_set() or threading.get_ident() == self._pump_ident:
            return prompt()
        req = _ApprovalRequest(prompt)
        self._queue.put(req)
        return req.wait_answer(self._cancel)

    def poll(self, timeout: float = 0.05) -> _ApprovalRequest | None:
        """Pump side: next pending prompt, or None on timeout."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None


def _signature(tool_name: str, verdict: Prompt | Deny) -> tuple[str, ...]:
    """Cache key: identical actions share it, distinct ones do not."""
    if isinstance(verdict, Deny):
        detail = verdict.rule.describe() if verdict.rule is not None else verdict.reason
        return ("deny", tool_name, detail)
    return ("prompt", tool_name, verdict.reason)


def _derive_rule(tool_name: str, tool_input: dict[str, Any]) -> Rule | None:
    """Narrow derived rule for D-03 always/never (never ``tool = "*"``)."""
    if tool_name == "shell":
        command = tool_input.get("command", "")
        if isinstance(command, str) and command.strip():
            return Rule(tool="shell", command=normalise_command(command))
        return None
    if tool_name == "python_repl":
        code = tool_input.get("code", "")
        if isinstance(code, str) and code.strip():
            return Rule(tool="python_repl", command=normalise_command(code)[:500])
        return None
    if tool_name in ("write", "edit"):
        raw = tool_input.get("path", "")
        if isinstance(raw, str) and raw:
            absolute = raw if Path(raw).is_absolute() else str(Path(os.getcwd()) / raw)
            return Rule(tool=tool_name, path=os.path.realpath(absolute))
        return None
    return None


class PolicyClassifier:
    """Custom HITL classifier: TOML matching over the tool-call event.

    Reads ``event.tool_use`` name + input, honours D-12
    ``trust_delegated`` (unbound/unknown agent → prompt, fail-closed),
    and stashes the last decision as the ask layer's context.
    """

    def __init__(
        self,
        policy_loader: Callable[[], PolicyConfig] | None = None,
        batch: BatchState | None = None,
        append_path: str | Path | None = None,
    ) -> None:
        self._loader = policy_loader or PolicyConfig.load
        self._batch = batch if batch is not None else BatchState()
        self._append_path = append_path
        self._main_agent: Any = None
        self._main_bound = False
        self._last: dict[str, Any] | None = None
        self._mode = "act"
        self._steering: Any = None

    @property
    def batch(self) -> BatchState:
        """The turn cache (shared with the ask closure)."""
        return self._batch

    def bind_main_agent(self, agent: Any) -> None:
        """Record the main agent for D-12 delegated-turn detection."""
        self._main_agent = agent
        self._main_bound = True

    def set_mode(self, mode: str) -> None:
        """Flip the Plan/Act enforcement flag (MODE-02, D-06/D-07).

        Raises:
            ValueError: For anything outside ``plan|act``.
        """
        if mode not in ("plan", "act"):
            raise ValueError(f"unknown mode {mode!r}: expected plan|act")
        self._mode = mode

    def bind_steering(self, source: Any) -> None:
        """Bind the steering slot for armed-boundary skip-prompt.

        ``source`` needs only ``consume_arm(tool_use_id) -> bool``
        (``SteeringState`` or ``SteeringSlot``); duck-typed so this
        module never imports the steering layer.
        """
        self._steering = source

    def _current_policy(self) -> PolicyConfig:
        try:
            return self._loader()
        except Exception as exc:  # symlink fail-loud surfaces as prompt-all here
            logger.warning("Policy load failed; prompting for everything: %s", exc)
            return PolicyConfig()

    def __call__(self, event: Any, **kwargs: Any) -> ClassifierResult | Awaitable[ClassifierResult]:
        tool_use = event.tool_use or {}
        tool_name = tool_use.get("name", "")
        tool_input = tool_use.get("input", {})
        if not isinstance(tool_input, dict):
            tool_input = {}
        tool_use_id = tool_use.get("toolUseId", "")
        # Steering-armed boundary: the hook already redirected this call
        # via cancel_tool, so skip the approval prompt (Proceed) while the
        # executor still cancels with the redirect message. One-shot and
        # above everything — a steered call is never prompted.
        if tool_use_id and self._steering is not None:
            try:
                if self._steering.consume_arm(tool_use_id):
                    return ClassifierResult(
                        requires_human_in_the_loop=False, reason="steering-redirected"
                    )
            except Exception as exc:  # fail-closed: a broken arm still prompts
                logger.warning("Steering arm check failed closed: %s", exc)
        # Plan-deny sits ABOVE the trust_delegated early return: delegated
        # turns do not escape read-only. Always denied (never batch-covered
        # to Proceed) so Plan mode cannot execute a mutation on retry.
        if self._mode == "plan" and tool_name in PLAN_MUTATING_TOOLS:
            reason = PLAN_DENY_TEMPLATE.format(tool=tool_name)
            verdict = Deny(reason=reason)
            signature = _signature(tool_name, verdict)
            self._last = {
                "tool_name": tool_name,
                "tool_input": tool_input,
                "verdict": verdict,
                "signature": signature,
            }
            return ClassifierResult(requires_human_in_the_loop=True, reason=f"DENY:{reason}")
        policy = self._current_policy()
        agent = getattr(event, "agent", None)
        if (
            policy.options.trust_delegated
            and self._main_bound
            and agent is not None
            and agent is not self._main_agent
        ):
            return ClassifierResult(requires_human_in_the_loop=False, reason="delegated-trusted")
        verdict = decide(tool_name, tool_input, policy)
        if isinstance(verdict, Allow):
            return ClassifierResult(requires_human_in_the_loop=False)
        signature = _signature(tool_name, verdict)
        if self._batch.is_covered(signature):
            return ClassifierResult(requires_human_in_the_loop=False, reason="batch-covered")
        self._last = {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "verdict": verdict,
            "signature": signature,
        }
        if isinstance(verdict, Deny):
            rule_text = verdict.rule.describe() if verdict.rule is not None else verdict.reason
            return ClassifierResult(
                requires_human_in_the_loop=True, reason=f"DENY:{rule_text}"
            )
        return ClassifierResult(requires_human_in_the_loop=True, reason=verdict.reason)

    def ask(self, prompt: str, **kwargs: Any) -> str:
        """Render the approval prompt; return canonical ``"y"``/``"n"``.

        Deny verdicts short-circuit to a printed refusal (no ``input``).
        Errors anywhere return ``"n"`` — a callback raise would abort the
        run, so the gate fails to skip-and-continue instead.
        """
        ctx = self._last
        try:
            with output_context():
                if ctx is None:
                    print("Approval context missing — denying (fail-closed).")
                    return "n"
                verdict = ctx["verdict"]
                tool_name = ctx["tool_name"]
                signature = ctx["signature"]
                if isinstance(verdict, Deny):
                    rule_text = verdict.rule.describe() if verdict.rule is not None else verdict.reason
                    if rule_text.startswith("Plan mode is read-only"):
                        # Plan denial: mode vocabulary only, never the
                        # policy-rule wrapper (vocabulary lock, T-04-10).
                        print(rule_text)
                        self._batch.record(f"plan-mode denied {tool_name}")
                        return "n"
                    print(f"Denied by policy rule [deny {rule_text}] — skipped, continuing.")
                    self._batch.record(f"denied {tool_name} [{rule_text}]")
                    return "n"
                assert isinstance(verdict, Prompt)
                print(f"Approval needed: {tool_name}")
                print(f"  Detail: {_detail_line(tool_name, ctx['tool_input'])}")
                print(f"  Risk: {verdict.reason}")
                def read_answer() -> str:
                    if sys.stdin.isatty():
                        # Arrow-key dialog (choice.radio_choice): prompt_toolkit
                        # owns SIGINT + termios for the duration. Runs in the
                        # pump thread (main), never the SDK worker thread.
                        # Ctrl-C re-raises (cancel path); ESC/failure denies.
                        return self._dialog_answer()
                    # Print the whole prompt block through the same stream:
                    # input()'s own prompt arg bypasses the output proxy and
                    # lands lines too early (observed "> " jumping above the
                    # Approval block). Bare input() keeps echo on the "> " line.
                    # The stdin fd mode is never touched here (nor by the
                    # steering reader): flipping the shared fd parked the
                    # reader in os.read and wedged the terminal.
                    print(_ASK_OPTIONS)
                    print(_ANSWER_PROMPT, end="", flush=True)
                    return input().strip().lower()

                broker = _active_broker()
                gate_open.set()
                try:
                    if broker is not None:
                        answer = broker.request(read_answer)
                    else:
                        answer = read_answer()
                finally:
                    gate_open.clear()
                return self._apply_answer(answer, ctx)
        except TurnCancelled:
            raise  # worker abort on cancel: must reach the SDK, never deny
        except Exception as exc:  # never leak a raise into the HITL run
            logger.warning("Policy ask failed closed: %s", exc)
            return "n"

    def _dialog_answer(self) -> str:
        """Arrow-key approval choice; ESC/failure denies, Ctrl-C re-raises."""
        from strands_code_cli.choice import radio_choice

        picked = radio_choice(
            "Approve?",
            [
                ("y", "Yes — approve once"),
                ("n", "No — skip (deny once)"),
                ("always", "Always — approve + remember rule"),
                ("never", "Never — deny + remember rule"),
            ],
            default=1,  # fail-closed highlight
        )
        if picked is None:
            return "n"
        return str(picked)

    def _apply_answer(self, answer: str, ctx: dict[str, Any]) -> str:
        """Shared verdict handling for the dialog and typed answers."""
        verdict = ctx["verdict"]
        tool_name = ctx["tool_name"]
        signature = ctx["signature"]
        if answer in ("y", "yes"):
            self._batch.mark(signature, f"approved {tool_name}: {verdict.reason}")
            return "y"
        if answer in ("always", "never"):
            derived = _derive_rule(tool_name, ctx["tool_input"])
            if derived is None:
                print("Cannot derive a narrow rule here; one-shot answer only.")
                single = "y" if answer == "always" else "n"
                if single == "y":
                    self._batch.mark(signature, f"{single}-once {tool_name}: {verdict.reason}")
                else:
                    self._batch.record(f"{single}-once {tool_name}: {verdict.reason}")
                return single
            kind = "allow" if answer == "always" else "deny"
            try:
                if self._append_path is not None:
                    PolicyConfig().append_rule(kind, derived, repo_path=self._append_path)
                else:
                    PolicyConfig().append_rule(kind, derived)
            except (OSError, ValueError) as exc:
                print(f"Could not append standing rule: {exc}")
                return "n" if answer == "never" else "y"
            print(f"Appended standing rule [{kind} {derived.describe()}].")
            if answer == "always":
                self._batch.mark(signature, f"{answer} {tool_name} [{derived.describe()}]")
            else:
                self._batch.record(f"{answer} {tool_name} [{derived.describe()}]")
            return "y" if answer == "always" else "n"
        self._batch.record(f"denied {tool_name}: {verdict.reason}")
        return "n"


def _detail_line(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Exact command/code/path shown in the prompt (D-01 full detail)."""
    if tool_name == "shell":
        return str(tool_input.get("command", ""))[:500]
    if tool_name == "python_repl":
        return str(tool_input.get("code", ""))[:500]
    if "path" in tool_input:
        return str(tool_input.get("path", ""))[:500]
    return str(tool_input)[:500]


_ACTIVE: dict[str, Any] = {}


def build_interventions(
    policy_loader: Callable[[], PolicyConfig] | None = None,
) -> list[HumanInTheLoop]:
    """Build the single-HITL intervention list (the ONLY construction site).

    Returns exactly one ``HumanInTheLoop`` carrying the read/search
    allowlist, the TOML classifier, and the rendering ask.
    """
    classifier = PolicyClassifier(policy_loader=policy_loader)
    gate = HumanInTheLoop(
        allowed_tools=["read", "search"],
        classifier=classifier,
        ask=classifier.ask,
    )
    broker = ApprovalBroker()
    _ACTIVE["classifier"] = classifier
    _ACTIVE["batch"] = classifier.batch
    _ACTIVE["handler"] = gate
    _ACTIVE["broker"] = broker
    return [gate]


def _active_classifier() -> PolicyClassifier | None:
    candidate = _ACTIVE.get("classifier")
    return candidate if isinstance(candidate, PolicyClassifier) else None


def _active_broker() -> ApprovalBroker | None:
    """Session broker for main-thread prompts (None before build / in tests)."""
    candidate = _ACTIVE.get("broker")
    return candidate if isinstance(candidate, ApprovalBroker) else None


def policy_ask(prompt: str, **kwargs: Any) -> str:
    """Module-level ask entry: delegates to the built gate, ``"n"`` if none."""
    classifier = _active_classifier()
    if classifier is None:
        return "n"
    result = classifier.ask(prompt, **kwargs)
    if inspect.isawaitable(result):
        return asyncio.run(result)  # type: ignore[return-value]
    return result


def bind_main_agent(agent: Any) -> None:
    """Record the main agent for D-12 detection (no-op before build)."""
    classifier = _active_classifier()
    if classifier is not None:
        classifier.bind_main_agent(agent)


def set_mode(mode: str) -> None:
    """Flip the active classifier's Plan/Act flag (no-op before build)."""
    classifier = _active_classifier()
    if classifier is not None:
        classifier.set_mode(mode)


def bind_steering(source: Any) -> None:
    """Bind the steering slot for armed-boundary skip-prompt (no-op before build)."""
    classifier = _active_classifier()
    if classifier is not None:
        classifier.bind_steering(source)


def bind_turn(turn_id: str) -> None:
    """Reset the turn cache (called from ``loop.py``; no-op before build)."""
    batch = _ACTIVE.get("batch")
    if isinstance(batch, BatchState):
        batch.bind_turn(turn_id)


def last_covered() -> list[str]:
    """Covered-action log for ``/policy last`` (empty before build)."""
    batch = _ACTIVE.get("batch")
    if isinstance(batch, BatchState):
        return batch.covered()
    return []
