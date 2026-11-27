"""Single-intervention permissions gate on Strands InterventionHandler (D-01..D-04).

Replaces the legacy ``HumanInTheLoop`` + ``DENY:`` reason smuggling +
``_ACTIVE`` module global with a single stateful :class:`PolicyGateHandler`
attached directly to each built agent via :func:`build_interventions` and
``agent._policy_gate``.

Threading & safety invariants:
- ``name == "strands-code:policy-gate"`` enforces single-handler uniqueness
  via ``InterventionRegistry`` / ``resolve_interventions``.
- ``on_error`` remains ``"throw"`` (inherited from ``InterventionHandler``) so
  ``TurnCancelled`` and ``KeyboardInterrupt`` propagate cleanly to the loop;
  internal gate errors catch fail-closed to ``Deny``.
- Agent identity keys on ``id(agent)`` (``"main"``, registered ``"btw"``,
  unregistered delegated ``"subagent"``) with ``weakref.finalize`` cleanup and
  per-agent ``read_only_agents`` tracking.
- ``BatchState`` is mutex-protected and keys signatures with full SHA-256 of
  canonical JSON ``tool_input``.
- Worker threads NEVER open ``output_context()``; full prompt rendering executes
  inside :meth:`ApprovalBroker.request` on the main pump thread under
  :data:`RENDER_LOCK`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import queue
import sys
import threading
import weakref
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from rich.syntax import Syntax
from strands.interventions import Deny as InterventionDeny
from strands.interventions import InterventionHandler
from strands.interventions import Proceed as InterventionProceed
from strands.types.exceptions import EventLoopException

from strands_code_cli.loop.steering import stdin_guard as gate_open
from strands_code_cli.policy.core import (
    TOOL_ONLY_TOOLS,
    Allow,
    Deny,
    PolicyConfig,
    Prompt,
    Rule,
    _is_protected_skills_or_config_path,
    _is_sensitive_read_path,
    _is_sensitive_search_input,
    decide,
    normalise_command,
)
from strands_code_cli.ui.console import (
    RENDER_LOCK,
    console,
    sanitize_display,
    sanitize_line,
    sanitize_multiline,
)
from strands_code_cli.ui.output import print_plain

logger = logging.getLogger(__name__)

_ASK_OPTIONS = "Approve? [y/n/always/never]"
_PROTECTED_ASK_OPTIONS = (
    "[y]es once / [n]o skip / [never] deny+remember (protected path)"
)
_ANSWER_PROMPT = "> "

PLAN_MUTATING_TOOLS = ("write", "edit", "shell", "python_repl")
"""Tools denied in Plan mode and on read-only delegated agents."""

PLAN_DENY_TEMPLATE = "Plan mode is read-only — {tool} skipped, continuing."
"""Mode-vocabulary denial (never a policy-rule or diff-mode word)."""

REVISE_HINT = "Revise the code or try a different approach."
"""Revise hint appended to denied python_repl observations."""


def _emit(text: str) -> None:
    """Print dynamic text to the shared UI console under RENDER_LOCK."""
    with RENDER_LOCK:
        print_plain(console, text)


def _is_protected_prompt(
    tool_name: str, tool_input: dict[str, Any], base: Path | None = None
) -> bool:
    """True when Standing Allow ('always') and trust_delegated must be blocked."""
    root = base if base is not None else Path.cwd()
    raw = tool_input.get("path", "")
    if tool_name in ("write", "edit"):
        return _is_protected_skills_or_config_path(raw, root)
    if tool_name == "read":
        return _is_sensitive_read_path(raw, root)
    if tool_name == "search":
        return _is_sensitive_search_input(tool_input, root)
    return False


def _is_outside_scope_prompt(tool_name: str, verdict: Prompt) -> bool:
    """True when unboxed read/search triggered an outside-allowed-roots prompt."""
    return (
        tool_name in ("read", "search")
        and "is outside the allowed roots:" in verdict.reason
    )


def tag_for(agent: Any, main_agent: Any) -> str:
    """Compat helper: ``"main"`` when unset or equal to ``main_agent``, else ``"btw"``."""
    if agent is None or agent is main_agent:
        return "main"
    return "btw"


def _input_signature(
    tool_name: str, tool_input: dict[str, Any], verdict: Prompt | Deny
) -> tuple[str, ...]:
    """Full-input SHA-256 cache key preventing identical-prefix batch aliasing."""
    canonical = json.dumps(
        tool_input, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    if isinstance(verdict, Deny):
        detail = verdict.rule.describe() if verdict.rule is not None else verdict.reason
        return ("deny", tool_name, detail, digest)
    return ("prompt", tool_name, verdict.reason, digest)


class BatchState:
    """Thread-safe turn-scoped approval cache keyed by full input signature."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._turn: str | None = None
        self._covered: set[tuple[str, tuple[str, ...]]] = set()
        self._log: list[str] = []

    def bind_turn(self, turn_id: str) -> None:
        """Start a new turn: clear per-turn coverage, keep the session log."""
        with self._lock:
            self._turn = turn_id
            self._covered = set()

    def is_covered(self, signature: tuple[str, ...], tag: str = "main") -> bool:
        """True when this signature was already approved this turn for ``tag``."""
        with self._lock:
            return (tag, signature) in self._covered

    def mark(
        self, signature: tuple[str, ...], description: str, tag: str = "main"
    ) -> None:
        """Record an approved signature plus its human-readable description."""
        with self._lock:
            self._covered.add((tag, signature))
            self._log.append(description)

    def covered(self) -> list[str]:
        """Snapshot of covered/recorded action descriptions for ``/policy last``."""
        with self._lock:
            return list(self._log)

    def record(self, description: str) -> None:
        """Log an outcome for ``/policy last`` without marking batch coverage."""
        with self._lock:
            self._log.append(description)


class TurnCancelled(Exception):
    """Worker-side abort raised when cancel fires while awaiting an approval prompt."""


def worker_cancelled(exc: BaseException) -> bool:
    """True when ``exc`` is ``TurnCancelled`` or wraps one via ``EventLoopException``."""
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, TurnCancelled):
            return True
        if not isinstance(current, EventLoopException):
            return False
        current = current.original_exception
    return False


class _ApprovalRequest:
    """One prompt handoff from the SDK worker thread to the pump thread."""

    def __init__(
        self, prompt: Callable[[], str], cancel: threading.Event | None = None
    ) -> None:
        self._prompt = prompt
        self._done = threading.Event()
        self.answer: str | None = None
        self.cancel = cancel

    def run_prompt(self) -> None:
        """Execute the prompt in the pump thread (KeyboardInterrupt propagates)."""
        try:
            self.answer = self._prompt()
        except Exception as exc:
            logger.warning("Approval prompt failed; defaulting to deny: %s", exc)
            self.answer = "n"
        finally:
            self._done.set()

    def abort(self) -> None:
        """Mark a dead worker's request unanswered (pump-side skip)."""
        self.answer = None
        self._done.set()

    def wait_answer(self, cancel: threading.Event | None) -> str:
        """Worker side: wait for pump answer, aborting cleanly on cancel."""
        while not self._done.wait(0.05):
            if cancel is not None and cancel.is_set():
                raise TurnCancelled()
        if cancel is not None and cancel.is_set():
            raise TurnCancelled()
        if self.answer is None:
            raise TurnCancelled()
        return self.answer


class ApprovalBroker:
    """Hands approval prompts from SDK worker threads to the main pump thread."""

    def __init__(self) -> None:
        self._queue: queue.Queue[_ApprovalRequest] = queue.Queue()
        self._pumping = threading.Event()
        self._pump_lock = threading.Lock()
        self._cancel: threading.Event | None = None
        self._pump_ident: int | None = None
        self._depth = 0
        self._cancel_lock = threading.Lock()
        self._cancel_by_tag: dict[str, threading.Event] = {}

    @contextmanager
    def pump(self, cancel: threading.Event) -> Iterator["ApprovalBroker"]:
        """Serve prompts on this thread until the turn or session ends."""
        with self._pump_lock:
            old_cancel, old_ident = self._cancel, self._pump_ident
            self._cancel = cancel
            self._pump_ident = threading.get_ident()
            self._depth += 1
            self._pumping.set()
        try:
            yield self
        finally:
            to_abort: list[_ApprovalRequest] = []
            with self._pump_lock:
                self._cancel = old_cancel
                self._pump_ident = old_ident
                self._depth = max(0, self._depth - 1)
                if self._depth == 0:
                    self._pumping.clear()
                    while True:
                        try:
                            to_abort.append(self._queue.get_nowait())
                        except queue.Empty:
                            break
            for orphan in to_abort:
                orphan.abort()

    def register_cancel(self, tag: str, event: threading.Event) -> None:
        """Bind a worker cancel event under ``tag``."""
        with self._cancel_lock:
            self._cancel_by_tag[tag] = event

    def unregister_cancel(self, tag: str) -> None:
        """Drop ``tag``'s cancel binding."""
        with self._cancel_lock:
            self._cancel_by_tag.pop(tag, None)

    def cancel_for(self, tag: str) -> threading.Event | None:
        """Return ``tag``'s cancel event, or None when unregistered."""
        with self._cancel_lock:
            return self._cancel_by_tag.get(tag)

    def request(
        self, prompt: Callable[[], str], cancel: threading.Event | None = None
    ) -> str:
        """Run ``prompt`` on the pump thread (inline if already on pump/no pump)."""
        req: _ApprovalRequest | None = None
        wait_cancel = cancel
        with self._pump_lock:
            if not self._pumping.is_set() or threading.get_ident() == self._pump_ident:
                req = None
            else:
                req = _ApprovalRequest(prompt, cancel)
                if wait_cancel is None:
                    wait_cancel = self._cancel
                self._queue.put(req)
        if req is None:
            return prompt()
        try:
            return req.wait_answer(wait_cancel)
        except TurnCancelled:
            self.discard(req)
            raise

    def discard(self, req: _ApprovalRequest) -> None:
        """Drop an unpolled request orphaned by cancel (best-effort)."""
        with self._queue.mutex:
            try:
                self._queue.queue.remove(req)
            except ValueError:
                pass

    def poll(self, timeout: float = 0.05) -> _ApprovalRequest | None:
        """Pump side: fetch next pending request, or None on timeout."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    @property
    def has_pending(self) -> bool:
        """True when an unserved request waits in the queue."""
        return not self._queue.empty()


def _derive_rule(tool_name: str, tool_input: dict[str, Any]) -> Rule | None:
    """Derive a narrow persisted TOML rule for ``always``/``never`` responses."""
    if tool_name == "shell":
        command = tool_input.get("command", "")
        if isinstance(command, str) and command.strip():
            cleaned = command.replace("\r\n", "\n").replace("\r", "\n")
            return Rule(tool="shell", command=normalise_command(cleaned))
        return None
    if tool_name == "python_repl":
        code = tool_input.get("code", "")
        if isinstance(code, str) and code.strip():
            cleaned = code.replace("\r\n", "\n").replace("\r", "\n")
            return Rule(tool="python_repl", command=normalise_command(cleaned)[:500])
        return None
    if tool_name in ("write", "edit", "read", "search"):
        raw = tool_input.get("path", "")
        if isinstance(raw, str) and raw:
            expanded = os.path.expanduser(raw)
            absolute = (
                expanded
                if Path(expanded).is_absolute()
                else str(Path(os.getcwd()) / expanded)
            )
            real = os.path.realpath(absolute)
            if any(ch in real for ch in ("*", "?", "[", "]")):
                return None
            return Rule(tool=tool_name, path=real)
        if tool_name == "search" and str(tool_input.get("file_glob", "")).strip():
            return Rule(tool=tool_name)
        return None
    if tool_name in TOOL_ONLY_TOOLS:
        return Rule(tool=tool_name)
    return None


def _detail_line(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Sanitized single-line tool detail for prompt headers (strips ANSI/controls)."""
    if tool_name == "shell":
        raw = str(tool_input.get("command", ""))
    elif tool_name == "python_repl":
        raw = str(tool_input.get("code", ""))
    elif "path" in tool_input:
        raw = str(tool_input.get("path", ""))
    else:
        raw = str(tool_input)
    return sanitize_line(raw, max_len=500)


_DIALOG_DETAIL_CHARS = 60
"""Maximum descriptor characters displayed in an approval dialog title."""


def _dialog_title(tag: str, tool_name: str, tool_input: dict[str, Any]) -> str:
    """Sanitized self-identifying dialog title carrying agent tag, tool, and detail."""
    safe_tag = sanitize_display(tag, max_len=40)
    safe_tool = sanitize_display(tool_name, max_len=80)
    raw = _detail_line(tool_name, tool_input)
    detail = sanitize_display(raw, max_len=_DIALOG_DETAIL_CHARS)
    if not detail:
        return f"Approve? [{safe_tag}] {safe_tool}"
    return f"Approve? [{safe_tag}] {safe_tool} — {detail}"


def _user_deny_action(
    tool_name: str, prefix: str = "Denied by user"
) -> InterventionDeny:
    """Format model-facing InterventionDeny reason with optional REPL revise hint."""
    reason = f"{prefix} — skipped, continuing."
    if tool_name == "python_repl":
        reason += f" {REVISE_HINT}"
    return InterventionDeny(reason=reason)


_MAX_PREVIEW_BYTES = 256 * 1024


def _read_regular_utf8_nofollow(path: Path, max_bytes: int) -> str | None:
    """Read UTF-8 text via ``O_NOFOLLOW`` and ``fstat`` checks; ``""`` when absent."""
    import stat

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return ""
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > max_bytes:
            return None
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                return None
            chunks.append(chunk)
        return b"".join(chunks).decode("utf-8", errors="strict")
    except (OSError, UnicodeDecodeError):
        return None
    finally:
        os.close(fd)


def _safe_existing_text_for_preview(
    raw_path: str, cwd: Path, extra_roots: list[Path]
) -> str | None:
    """Read existing UTF-8 file text only when confined, non-sensitive, regular, and small.

    Returns ``""`` when the target does not exist yet (new-file preview) and
    ``None`` when the path is outside scope, sensitive, symlinked, special,
    binary, or larger than 256 KiB.
    """
    from strands_code_cli.platform_io import refuse_symlink, refuse_symlink_under_roots
    from strands_code_cli.policy.scope import confine, resolve

    raw_obj = Path(os.path.expanduser(raw_path))
    raw_candidate = Path(
        os.path.normpath(str(raw_obj if raw_obj.is_absolute() else cwd / raw_obj))
    )
    try:
        refuse_symlink(raw_candidate, "diff preview target", max_ancestors=1)
        refuse_symlink_under_roots(
            raw_candidate, [cwd, cwd.resolve(), *extra_roots], "diff preview target"
        )
    except ValueError:
        return None
    resolved = resolve(raw_path, cwd)
    try:
        confined = confine(resolved, cwd, extra_roots)
    except ValueError:
        return None
    if (
        _is_sensitive_read_path(raw_path, cwd)
        or _is_sensitive_read_path(str(confined), cwd)
        or _is_protected_skills_or_config_path(raw_path, cwd)
        or _is_protected_skills_or_config_path(str(confined), cwd)
    ):
        return None
    try:
        refuse_symlink_under_roots(confined, [cwd, *extra_roots], "diff preview target")
    except ValueError:
        return None
    return _read_regular_utf8_nofollow(confined, _MAX_PREVIEW_BYTES)


class PolicyGateHandler(InterventionHandler):
    """Single deterministic TOML+Python permissions gate on Strands InterventionHandler."""

    def __init__(
        self,
        policy_loader: Callable[[], PolicyConfig] | None = None,
        batch: BatchState | None = None,
        append_path: str | Path | None = None,
        broker: ApprovalBroker | None = None,
        mode: str = "act",
    ) -> None:
        if mode not in ("plan", "act"):
            raise ValueError(f"unknown mode {mode!r}: expected plan|act")
        self._loader = policy_loader or PolicyConfig.load
        self._batch = batch if batch is not None else BatchState()
        self._append_path = append_path
        self._broker = broker if broker is not None else ApprovalBroker()
        self._state_lock = threading.RLock()
        self._mode = mode
        self._main_agent_id: int | None = None
        self._main_bound = False
        self._agent_tags: dict[int, str] = {}
        self._read_only_agents: set[int] = set()
        self._finalizers: dict[int, weakref.finalize] = {}
        self._finalizer_tokens: dict[int, object] = {}

    @property
    def name(self) -> str:
        """Unique handler identifier enforcing single-gate registration."""
        return "strands-code:policy-gate"

    @property
    def batch(self) -> BatchState:
        """Per-turn approval cache and session covered-action log."""
        return self._batch

    @property
    def broker(self) -> ApprovalBroker:
        """Main-thread prompt broker owned by this gate."""
        return self._broker

    def _cleanup_agent_id(self, agent_id: int, token: object | None = None) -> None:
        with self._state_lock:
            if token is not None and self._finalizer_tokens.get(agent_id) is not token:
                return
            self._agent_tags.pop(agent_id, None)
            self._read_only_agents.discard(agent_id)
            self._finalizers.pop(agent_id, None)
            self._finalizer_tokens.pop(agent_id, None)
            if self._main_agent_id == agent_id:
                self._main_agent_id = None
                self._main_bound = False

    def _attach_finalizer_locked(self, agent: Any, agent_id: int) -> None:
        if agent_id in self._finalizers:
            return
        token = object()
        try:
            self._finalizer_tokens[agent_id] = token
            self._finalizers[agent_id] = weakref.finalize(
                agent, self._cleanup_agent_id, agent_id, token
            )
        except TypeError:
            self._finalizer_tokens.pop(agent_id, None)  # non-weakrefable test doubles

    def bind_main_agent(self, agent: Any) -> None:
        """Register the primary session agent as ``"main"``."""
        if agent is None:
            return
        agent_id = id(agent)
        with self._state_lock:
            self._main_agent_id = agent_id
            self._main_bound = True
            self._agent_tags[agent_id] = "main"
            self._attach_finalizer_locked(agent, agent_id)

    def register_agent(self, agent: Any, tag: str) -> None:
        """Associate an agent object with an explicit tag (e.g. ``"btw"``, ``"subagent"``)."""
        if agent is None:
            return
        agent_id = id(agent)
        with self._state_lock:
            self._agent_tags[agent_id] = tag
            self._attach_finalizer_locked(agent, agent_id)

    def unregister_agent(self, agent: Any) -> None:
        """Explicitly remove ``agent`` from tag and read-only tracking."""
        if agent is None:
            return
        agent_id = id(agent)
        with self._state_lock:
            self._agent_tags.pop(agent_id, None)
            self._read_only_agents.discard(agent_id)
            self._finalizer_tokens.pop(agent_id, None)
            fin = self._finalizers.pop(agent_id, None)
            if fin is not None:
                fin.detach()
            if self._main_agent_id == agent_id:
                self._main_agent_id = None
                self._main_bound = False

    def tag_for(self, agent: Any) -> str:
        """Return ``"main"``, registered tag (e.g. ``"btw"``), or ``"subagent"``."""
        if agent is None:
            return "main"
        agent_id = id(agent)
        with self._state_lock:
            if agent_id in self._agent_tags:
                return self._agent_tags[agent_id]
            if not self._main_bound or agent_id == self._main_agent_id:
                return "main"
            return "subagent"

    def is_delegated(self, agent: Any) -> bool:
        """True when ``agent`` is a non-main agent and main agent has been bound."""
        if agent is None:
            return False
        agent_id = id(agent)
        with self._state_lock:
            return self._main_bound and agent_id != self._main_agent_id

    def set_mode(self, mode: str) -> None:
        """Flip session-wide ``"plan"`` vs ``"act"`` mode."""
        if mode not in ("plan", "act"):
            raise ValueError(f"unknown mode {mode!r}: expected plan|act")
        with self._state_lock:
            self._mode = mode

    def enter_read_only(self, agent: Any) -> None:
        """Restrict ``agent`` to read-only operations until released."""
        if agent is None:
            return
        agent_id = id(agent)
        with self._state_lock:
            self._read_only_agents.add(agent_id)
            self._attach_finalizer_locked(agent, agent_id)

    def exit_read_only(self, agent: Any) -> None:
        """Lift per-agent read-only restriction from ``agent``."""
        if agent is None:
            return
        with self._state_lock:
            self._read_only_agents.discard(id(agent))

    def is_read_only(self, agent: Any) -> bool:
        """True when session mode is ``"plan"`` or ``agent`` is marked read-only."""
        agent_id = id(agent) if agent is not None else None
        with self._state_lock:
            if self._mode == "plan":
                return True
            return agent_id is not None and agent_id in self._read_only_agents

    @contextmanager
    def read_only(self, agent: Any) -> Iterator[None]:
        """Context manager placing ``agent`` in read-only mode for the block."""
        self.enter_read_only(agent)
        try:
            yield
        finally:
            self.exit_read_only(agent)

    def bind_turn(self, turn_id: str) -> None:
        """Reset per-turn approval batch cache."""
        self._batch.bind_turn(turn_id)

    def last_covered(self) -> list[str]:
        """Covered and logged gate outcomes for ``/policy last``."""
        return self._batch.covered()

    def _current_policy(self) -> PolicyConfig:
        try:
            return self._loader()
        except Exception as exc:
            logger.warning(
                "Policy load failed; preserving home defaults if available: %s", exc
            )
            if (
                getattr(self._loader, "__func__", None) is PolicyConfig.load.__func__
                and getattr(self._loader, "__self__", None) is PolicyConfig
            ):
                return PolicyConfig.load_home_only()
            return PolicyConfig()

    def _handle_deny(self, tag: str, tool_name: str, verdict: Deny) -> InterventionDeny:
        rule_text = sanitize_line(
            verdict.rule.describe() if verdict.rule is not None else verdict.reason,
            max_len=400,
        )
        safe_tag = sanitize_line(tag, max_len=40)
        safe_tool = sanitize_line(tool_name, max_len=80)
        refusal = f"Denied by policy rule [deny {rule_text}] — skipped, continuing."
        if tool_name == "python_repl":
            refusal += f" {REVISE_HINT}"
        _emit(refusal)
        self._batch.record(f"[{safe_tag}] denied {safe_tool} [{rule_text}]")
        return InterventionDeny(reason=refusal)

    def _preview_roots(self, cwd: Path, tool_name: str) -> list[Path]:
        from strands_code_cli.policy.scope import effective_roots

        try:
            policy = self._current_policy()
            return list(effective_roots(cwd, policy, tool_name=tool_name))
        except Exception:
            return []

    def _render_mutation_diff(self, tool_name: str, tool_input: dict[str, Any]) -> None:
        raw_path = str(tool_input.get("path") or "")
        if not raw_path:
            return
        from strands_code_cli.policy.diff_gate import (
            bounded_diff,
            preview_for_edit,
            unified_diff,
        )

        if tool_name == "edit":
            diff = preview_for_edit(
                raw_path,
                str(tool_input.get("old_str") or ""),
                str(tool_input.get("new_str") or ""),
            )
        else:
            cwd = Path.cwd()
            extra = self._preview_roots(cwd, tool_name)
            old_text = _safe_existing_text_for_preview(raw_path, cwd, extra)
            if old_text is None:
                return
            diff = unified_diff(
                old_text, str(tool_input.get("content") or ""), raw_path
            )
        preview = bounded_diff(diff, max_lines=40)
        if preview:
            console.print(Syntax(sanitize_multiline(preview), "diff"))

    def _render_prompt_header(
        self, tag: str, tool_name: str, tool_input: dict[str, Any], verdict: Prompt
    ) -> None:
        safe_tag = sanitize_line(tag, max_len=40)
        safe_tool = sanitize_line(tool_name, max_len=80)
        with RENDER_LOCK:
            print_plain(console, f"Approval needed: [{safe_tag}] {safe_tool}")
            if tool_name == "python_repl":
                safe_code = sanitize_multiline(tool_input.get("code", ""))
                console.print(Syntax(safe_code, "python"))
            elif tool_name in ("write", "edit"):
                print_plain(console, f"  Detail: {_detail_line(tool_name, tool_input)}")
                self._render_mutation_diff(tool_name, tool_input)
            else:
                print_plain(console, f"  Detail: {_detail_line(tool_name, tool_input)}")
            print_plain(
                console, f"  Risk: {sanitize_line(verdict.reason, max_len=500)}"
            )

    def _prompt_user(
        self,
        tag: str,
        tool_name: str,
        tool_input: dict[str, Any],
        verdict: Prompt,
        signature: tuple[str, ...],
        protected: bool,
    ) -> InterventionProceed | InterventionDeny:
        def render_and_read() -> str:
            self._render_prompt_header(tag, tool_name, tool_input, verdict)
            if sys.stdin.isatty():
                return self._dialog_answer(
                    _dialog_title(tag, tool_name, tool_input),
                    allow_always=not protected,
                )
            with RENDER_LOCK:
                print_plain(
                    console,
                    _PROTECTED_ASK_OPTIONS if protected else _ASK_OPTIONS,
                )
                console.print(_ANSWER_PROMPT, end="", markup=False)
                if hasattr(console.file, "flush"):
                    console.file.flush()
            return input().strip().lower()

        with gate_open.hold():
            answer = self._broker.request(render_and_read, self._broker.cancel_for(tag))
        return self._apply_answer(
            answer, tag, tool_name, tool_input, verdict, signature, protected
        )

    def _dialog_answer(
        self, title: str = "Approve?", *, allow_always: bool = True
    ) -> str:
        """Arrow-key approval choice; ESC/failure denies, Ctrl-C re-raises."""
        from strands_code_cli.ui.choice import radio_choice

        options = [
            ("y", "Yes — approve once"),
            ("n", "No — skip (deny once)"),
        ]
        if allow_always:
            options.append(("always", "Always — approve + remember rule"))
        options.append(("never", "Never — deny + remember rule"))
        picked = radio_choice(title, options, default=1)
        return str(picked) if picked is not None else "n"

    def _append_standing_rule(self, kind: str, derived: Rule) -> bool:
        try:
            if self._append_path is not None:
                PolicyConfig().append_rule(kind, derived, repo_path=self._append_path)
            else:
                PolicyConfig().append_rule(kind, derived)
        except (OSError, ValueError) as exc:
            _emit(f"Could not append standing rule: {sanitize_line(exc, max_len=300)}")
            return False
        _emit(
            f"Appended standing rule [{kind} {sanitize_line(derived.describe(), max_len=300)}]."
        )
        return True

    def _record_one_shot(
        self,
        approve: bool,
        tag: str,
        tool_name: str,
        reason: str,
        signature: tuple[str, ...],
        label: str,
    ) -> InterventionProceed | InterventionDeny:
        entry = (
            f"[{sanitize_line(tag, max_len=40)}] {label} "
            f"{sanitize_line(tool_name, max_len=80)}: "
            f"{sanitize_line(reason, max_len=400)}"
        )
        if approve:
            self._batch.mark(signature, entry, tag=tag)
            return InterventionProceed()
        self._batch.record(entry)
        return _user_deny_action(tool_name)

    def _apply_answer(
        self,
        answer: str,
        tag: str,
        tool_name: str,
        tool_input: dict[str, Any],
        verdict: Prompt,
        signature: tuple[str, ...],
        protected: bool,
    ) -> InterventionProceed | InterventionDeny:
        if answer in ("y", "yes"):
            return self._record_one_shot(
                True, tag, tool_name, verdict.reason, signature, "approved"
            )
        if answer == "always" and protected:
            _emit("Protected path: standing allow rules are disabled; approving once.")
            return self._record_one_shot(
                True, tag, tool_name, verdict.reason, signature, "y-once"
            )
        if answer in ("always", "never"):
            return self._apply_standing_choice(
                answer, tag, tool_name, tool_input, verdict, signature
            )
        return self._record_one_shot(
            False, tag, tool_name, verdict.reason, signature, "denied"
        )

    def _apply_standing_choice(
        self,
        answer: str,
        tag: str,
        tool_name: str,
        tool_input: dict[str, Any],
        verdict: Prompt,
        signature: tuple[str, ...],
    ) -> InterventionProceed | InterventionDeny:
        approve = answer == "always"
        derived = _derive_rule(tool_name, tool_input)
        if derived is None:
            _emit("Cannot derive a narrow rule here; one-shot answer only.")
            label = "y-once" if approve else "n-once"
            return self._record_one_shot(
                approve, tag, tool_name, verdict.reason, signature, label
            )
        kind = "allow" if approve else "deny"
        if not self._append_standing_rule(kind, derived):
            return InterventionProceed() if approve else _user_deny_action(tool_name)
        desc = (
            f"[{sanitize_line(tag, max_len=40)}] {answer} "
            f"{sanitize_line(tool_name, max_len=80)} "
            f"[{sanitize_line(derived.describe(), max_len=300)}]"
        )
        if approve:
            self._batch.mark(signature, desc, tag=tag)
            return InterventionProceed()
        self._batch.record(desc)
        return _user_deny_action(
            tool_name, f"Denied by user [never {derived.describe()}]"
        )

    async def before_tool_call(
        self, event: Any, **kwargs: Any
    ) -> InterventionProceed | InterventionDeny:
        """Evaluate tool call deterministically: steering -> Plan/RO -> decide -> trust -> batch -> prompt."""
        try:
            if getattr(event, "cancel_tool", False):
                return InterventionProceed(reason="steering-redirected")
            tool_use = event.tool_use or {}
            tool_name = tool_use.get("name", "")
            raw_input = tool_use.get("input", {})
            tool_input = raw_input if isinstance(raw_input, dict) else {}
            agent = getattr(event, "agent", None)
            tag = self.tag_for(agent)
            if self.is_read_only(agent) and tool_name in PLAN_MUTATING_TOOLS:
                safe_tool = sanitize_line(tool_name, max_len=80)
                reason = PLAN_DENY_TEMPLATE.format(tool=safe_tool)
                _emit(reason)
                self._batch.record(
                    f"[{sanitize_line(tag, max_len=40)}] plan-mode denied {safe_tool}"
                )
                return InterventionDeny(reason=reason)
            return self._evaluate_act_call(agent, tag, tool_name, tool_input)
        except (TurnCancelled, KeyboardInterrupt):
            raise
        except Exception as exc:
            logger.warning("Policy gate failed closed: %s", exc)
            return InterventionDeny(
                reason="Approval gate failed closed — skipped, continuing."
            )

    def _evaluate_act_call(
        self,
        agent: Any,
        tag: str,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> InterventionProceed | InterventionDeny:
        policy = self._current_policy()
        verdict = decide(tool_name, tool_input, policy)
        if isinstance(verdict, Allow):
            return InterventionProceed()
        if isinstance(verdict, Deny):
            return self._handle_deny(tag, tool_name, verdict)
        protected = _is_protected_prompt(tool_name, tool_input)
        outside_scope = _is_outside_scope_prompt(tool_name, verdict)
        if (
            policy.options.trust_delegated
            and self.is_delegated(agent)
            and not protected
            and not outside_scope
        ):
            _emit(
                f"Auto-trusted delegated call ({sanitize_line(tool_name, max_len=80)}) — trust_delegated is on."
            )
            return InterventionProceed(reason="delegated-trusted")
        signature = _input_signature(tool_name, tool_input, verdict)
        if self._batch.is_covered(signature, tag=tag):
            return InterventionProceed(reason="batch-covered")
        return self._prompt_user(
            tag, tool_name, tool_input, verdict, signature, protected
        )


def build_interventions(
    policy_loader: Callable[[], PolicyConfig] | None = None,
) -> list[PolicyGateHandler]:
    """Construct the single PolicyGateHandler instance for ``create_harness``."""
    return [PolicyGateHandler(policy_loader=policy_loader)]


def gate_for(agent: Any) -> PolicyGateHandler | None:
    """Return the :class:`PolicyGateHandler` attached to ``agent``, or None."""
    candidate = getattr(agent, "_policy_gate", None)
    return candidate if isinstance(candidate, PolicyGateHandler) else None


def broker_for(agent: Any) -> ApprovalBroker | None:
    """Return the :class:`ApprovalBroker` bound to ``agent`` (gate or test override)."""
    gate = gate_for(agent)
    if gate is not None:
        return gate.broker
    candidate = getattr(agent, "_approval_broker", None)
    return candidate if isinstance(candidate, ApprovalBroker) else None
