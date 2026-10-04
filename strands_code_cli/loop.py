"""Minimal REPL loop: prompt, synchronous agent turn, clean exit."""

from __future__ import annotations

import asyncio
import copy
import logging
import os
import signal
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from time import monotonic
from pathlib import Path
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory, History

from rich.console import Console

from strands_code_cli.cost_context import (
    AUTO_COMPACT_PCT,
    MODEL_PRICING,
    compact_messages,
    estimate_messages_tokens,
    model_summarize,
    usage_line,
    window_for,
)
from strands_code_cli.mode import PLAN_PREFIX, ModeState
from strands_code_cli.model_switch import (
    MODEL_REFUSAL,
    apply_switch,
    canonical_prefix_hash,
    convert_history,
    estimate_fit,
    from_stash_json,
    normalize_model_ref,
    same_vendor,
    supports_reasoning,
    to_stash_json,
)
from strands_code_cli.output import output_context
from strands_code_cli.policy_gate import (
    TurnCancelled,
    _active_broker,
    bind_turn,
    gate_open,
    set_mode as set_gate_mode,
)
from strands_code_cli.router import dispatch
from strands_code_cli.session_index import SessionIndex, rich_stash_path
from strands_code_cli.steering import (
    SteeringSlot,
    SteeringState,
    register_steering_hook,
    start_steering_reader,
)

logger = logging.getLogger(__name__)
console = Console()

TITLE_PROMPT = "Summarize this exchange in at most six words, plain words only: "
TITLE_WORDS = 6
TITLE_FALLBACK_WORDS = 8
TITLE_FALLBACK_CHARS = 60


def _history() -> History:
    """Reply history backed by a file; in-memory when the cache dir is unusable.

    History holds typed asks (T-01-03): the cache dir and file get the same
    0o700 treatment as the session/index dirs.
    """
    import os

    try:
        import platformdirs

        cache = Path(platformdirs.user_cache_dir("strands-code"))
        cache.mkdir(parents=True, exist_ok=True)
        os.chmod(cache, 0o700)
        history_file = cache / "repl_history"
        history_file.touch(exist_ok=True)
        os.chmod(history_file, 0o600)
        return FileHistory(str(history_file))
    except Exception as exc:  # best-effort history must never block the loop
        logger.warning("Falling back to in-memory REPL history: %s", exc)
        return History()


def explicit_save(agent: Any) -> None:
    """Overwrite ``snapshot_latest`` so a clean exit loses nothing.

    Per-message saves already cover kill-safety; this adds determinism on
    the exit path. Failures are logged, never raised.
    """
    manager = getattr(agent, "_session_manager", None)
    save = getattr(manager, "save_snapshot", None)
    if save is None:
        return
    try:
        asyncio.run(save(agent, is_latest=True))
    except Exception as exc:
        logger.warning("Explicit session save on exit failed: %s", exc)


def _fallback_title(first_text: str) -> str:
    """First-ask truncation used when the model title call fails."""
    clipped = " ".join(first_text.split()[:TITLE_FALLBACK_WORDS])
    return clipped[:TITLE_FALLBACK_CHARS].strip() or "untitled"


def _maybe_auto_title(agent: Any, session_id: str, index: SessionIndex, first_text: str) -> None:
    """Title once from the first exchange (D-04); a manual rename always wins.

    A cheap direct model call is attempted first; any failure falls back to
    first-ask truncation. ``update_title`` no-ops on user-renamed sessions.
    """
    title = _fallback_title(first_text)
    try:
        generate = getattr(getattr(agent, "model", None), "generate", None)
        if generate is None:
            raise AttributeError("agent exposes no direct model call")
        raw = generate(f"{TITLE_PROMPT}{first_text[:500]}")
        candidate = raw if isinstance(raw, str) else getattr(raw, "text", "") or ""
        words = candidate.split()
        if words:
            title = " ".join(words[:TITLE_WORDS])
    except Exception:
        pass  # fallback title stands
    title = title.replace("/", "-").replace("\\", "-")
    try:
        index.update_title(session_id, title)
    except (KeyError, ValueError) as exc:
        logger.warning("Auto-title skipped for session %s: %s", session_id, exc)


CANCEL_WINDOW_S = 5.0
"""Second-press window for two-press cancel (LOOP-04, D-13)."""

CANCEL_FIRST_PRESS = "Cancelling after the current step… press Ctrl-C again to confirm."
CANCEL_CONFIRMED = "Cancel confirmed — partial work kept."
CANCEL_STILL = "Still cancelling — graceful stop already requested; the current step finishes first."


def record_turn_metrics(
    result: Any, current_model: str, session_turns: list
) -> str | None:
    """Append one per-turn token row; return the usage line when computable.

    Best-effort display only: doubles without metrics (tests, direct calls)
    yield None instead of raising.
    """
    from strands_code_agent.utils import get_response_metrics

    try:
        metrics = get_response_metrics(
            result, model_id=current_model, price_table=MODEL_PRICING
        )
    except Exception:
        return None
    try:
        in_tok = int(metrics.get("input_tokens", 0))
        out_tok = int(metrics.get("output_tokens", 0))
    except (TypeError, ValueError):
        return None
    session_turns.append(
        {"turn": len(session_turns) + 1, "input_tokens": in_tok, "output_tokens": out_tok}
    )
    return usage_line(in_tok, out_tok, current_model)


def maybe_auto_compact(agent: Any, current_model: str) -> str | None:
    """Compact at 80% of the window, pair-atomic; announce or return None."""
    window = window_for(current_model)
    if not window:
        return None  # unknown window: no signal, no compaction
    messages = getattr(agent, "messages", None) or []
    if not messages:
        return None
    tokens = estimate_messages_tokens(list(messages))
    pct = tokens / window * 100.0
    if pct < AUTO_COMPACT_PCT:
        return None
    kept = compact_messages(agent, summarize=lambda old: model_summarize(agent, old))
    return f"Context at {pct:.0f}% — auto-compacted, {kept} recent messages kept."


def _invoke_agent(agent: Any, text: str, cancel_event: threading.Event) -> Any:
    """Run one turn, handing the caller-owned cancel event to SDK agents.

    Real agents expose ``cancel_signal`` and accept a per-invocation
    ``cancel_signal`` kwarg (observed, never mutated, by the agent);
    plain test doubles take bare text.

    The agent call runs in an owned worker thread while this (main) thread
    pumps approval prompts via the session broker: the SDK invokes ``ask``
    inside its event-loop thread, where blocking on stdin is fatal
    (signals land here, the worker would park; ``asyncio.run`` cannot
    nest). Served prompts run here, where signals and prompt_toolkit
    behave; a KeyboardInterrupt propagates with the cancel event already
    set, so the worker aborts instead of parking. No broker (tests,
    direct calls) → legacy direct call.
    """
    broker = _active_broker()
    if broker is None:
        if hasattr(agent, "cancel_signal"):
            return agent(text, cancel_signal=cancel_event)
        return agent(text)
    kwargs = {"cancel_signal": cancel_event} if hasattr(agent, "cancel_signal") else {}
    with broker.pump(cancel_event):
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(agent, text, **kwargs)
            while True:
                if future.done():
                    try:
                        return future.result()
                    except TurnCancelled:
                        # Worker aborted on cancel without a main-thread
                        # KeyboardInterrupt reaching us: same cancel path.
                        raise KeyboardInterrupt from None
                req = broker.poll()
                if req is None:
                    continue
                req.run_prompt()


def _handle_turn_cancel(
    agent: Any,
    session_id: str,
    index: SessionIndex,
    cancel_event: threading.Event,
    armed_at: float | None,
) -> float | None:
    """Two-press cancel state machine (LOOP-04, D-13/D-15/D-16).

    Press #1 requests graceful stop (caller-owned event set, observed
    at the next cancellation-safe point) and flushes the session so
    partial work survives even a killed CLI. Press #2 inside the window
    confirms (idempotent — stop already requested). A press after the
    window lapses re-states the honest position: no un-cancel exists,
    the remainder is dropped, the mode is unchanged.

    Returns:
        The updated arm timestamp (None when disarmed by confirm).
    """
    cancel_event.set()
    now = monotonic()
    if armed_at is not None and (now - armed_at) <= CANCEL_WINDOW_S:
        console.print(f"[yellow]{CANCEL_CONFIRMED}[/yellow]")
        explicit_save(agent)
        index.ensure(session_id)
        return None
    if armed_at is not None:
        console.print(f"[yellow]{CANCEL_STILL}[/yellow]")
    else:
        console.print(f"[yellow]{CANCEL_FIRST_PRESS}[/yellow]")
    explicit_save(agent)
    index.ensure(session_id)
    return now


def _make_turn_sigint_handler(
    cancel_event: threading.Event, prev: Any
) -> Any:
    """SIGINT handler for the duration of one turn (LOOP-04).

    The SDK may absorb KeyboardInterrupt internally (converting it to a
    graceful stop of the current model stream) so the loop's
    ``except KeyboardInterrupt`` two-press path never runs and the turn
    continues to the next tool — observed live as "Ctrl-C ignored, next
    approval prompt arrives anyway". Setting the caller-owned event here
    makes press #1 effective regardless: the SDK observes ``cancel_signal``
    at its next checkpoint and stops after the current step (D-10/D-13),
    even when no KeyboardInterrupt ever reaches the loop.

    The previous disposition is always chained (default re-raises
    KeyboardInterrupt), so the two-press UX is preserved whenever the
    exception does propagate. The handler itself stays side-effect-free
    apart from setting the event (async-signal-safety).
    """

    def _handler(signum: Any, frame: Any) -> None:
        cancel_event.set()
        if callable(prev):
            prev(signum, frame)
        elif prev == signal.SIG_DFL:
            signal.default_int_handler(signum, frame)  # raises KeyboardInterrupt
        # SIG_IGN stays absorbed; the event above still stops the turn.

    return _handler


def _steering_slot_for(agent: Any) -> SteeringSlot:
    """Session slot for the steering hook: reuse build_agent's, else register."""
    slot = getattr(agent, "_steering_slot", None)
    if isinstance(slot, SteeringSlot):
        return slot
    return register_steering_hook(agent)


_RICH_STASH_VERSION = 1


class RichHistory:
    """Richest-variant stash for switch-back (MODEL-01 preservation).

    Single slot, loop-owned: each switch stashes the pre-conversion source
    when it carries thinking blocks; switching to a same-vendor
    reasoning-capable target restores the stash plus the turns made while
    away. Bounded (one deepcopy, replaced per switch) and fail-safe
    (restores only when the canonical prefix hash proves no compaction,
    clear, or edit trimmed underneath the stash point).

    The stash persists to a sidecar file per session, so a switch-back
    after resume restores native thinking instead of re-stripping it.
    """

    def __init__(self) -> None:
        self.messages: list | None = None
        self.model_id: str | None = None
        self.length: int = 0
        self.prefix_hash: str | None = None

    def reset(self) -> None:
        """Drop the stash (history was cleared or compacted underneath)."""
        self.messages = None
        self.model_id = None
        self.length = 0
        self.prefix_hash = None

    def save(self, path: Path | None) -> None:
        """Persist the stash; an empty stash removes any stale file.

        Fail-soft: filesystem errors are logged, never raised.
        """
        if path is None:
            return
        if self.messages is None or self.model_id is None:
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Rich stash cleanup failed: %s", exc)
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                to_stash_json(
                    {
                        "version": _RICH_STASH_VERSION,
                        "model_id": self.model_id,
                        "length": self.length,
                        "prefix_hash": self.prefix_hash,
                        "messages": self.messages,
                    }
                ),
                encoding="utf-8",
            )
        except (OSError, TypeError, ValueError) as exc:
            logger.warning("Rich stash save failed: %s", exc)

    @classmethod
    def load(cls, path: Path | None) -> RichHistory:
        """Load a persisted stash; missing or corrupt files load empty."""
        rich = cls()
        if path is None:
            return rich
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            return rich
        try:
            data = from_stash_json(raw)
        except ValueError:
            return rich
        if (
            not isinstance(data, dict)
            or data.get("version") != _RICH_STASH_VERSION
            or not isinstance(data.get("model_id"), str)
            or not isinstance(data.get("length"), int)
            or not isinstance(data.get("prefix_hash"), str)
            or not isinstance(data.get("messages"), list)
            or not all(isinstance(m, dict) for m in data["messages"])
        ):
            return rich
        rich.messages = data["messages"]
        rich.model_id = data["model_id"]
        rich.length = data["length"]
        rich.prefix_hash = data["prefix_hash"]
        return rich


def _has_thinking(messages: list) -> bool:
    """True when any content block carries reasoningContent."""
    return any(
        "reasoningContent" in block
        for message in messages
        for block in message.get("content", [])
    )


def apply_model_action(
    agent: Any,
    new_id: str,
    *,
    turn_running: bool,
    current_model: str,
    rich: RichHistory | None = None,
) -> tuple[str | None, str]:
    """Apply a validated /model selection (loop-owned; never the router).

    Idle only: a running turn gets the immediate refusal reply, never a
    queue (D-01 fail-closed). Otherwise restore-then-convert (the rich
    stash when switching back to a same-vendor thinking model),
    convert-when-fits else summarize-old + keep-recent +
    replay-last-user-message, then the tracer-winning in-place swap.

    Args:
        agent: Live session agent.
        new_id: Validated ``provider/name`` selection (verbatim; profile
            ARNs are normalized to tails, and the switch resolves before
            any history mutation so failures leave the session untouched).
        turn_running: True when a turn is in flight → refuse.
        current_model: Active model id string for the fit estimate.
        rich: Loop-owned richest-variant stash (None → convert only).

    Returns:
        ``(resolved_id, reply)``; resolved_id is None on refusal.
    """
    if turn_running:
        return (None, MODEL_REFUSAL)
    new_id = normalize_model_ref(new_id)
    # Switch first: resolve raises before any history mutation, so a bad
    # selection leaves the session (model AND messages) untouched.
    _model, resolved_id = apply_switch(agent, new_id)
    source = list(agent.messages)
    restored = False
    if (
        rich is not None
        and rich.messages is not None
        and rich.model_id is not None
        and rich.prefix_hash is not None
        and supports_reasoning(new_id)
        and same_vendor(rich.model_id, new_id)
        and len(source) >= rich.length
        and canonical_prefix_hash(source[: rich.length]) == rich.prefix_hash
    ):
        source = copy.deepcopy(rich.messages) + copy.deepcopy(source[rich.length :])
        restored = True
    convert_from = current_model
    if restored and rich is not None and rich.model_id is not None:
        # Restored thinking keeps its original vendor for the same-vendor
        # check — converting "from" the away model would re-strip it.
        convert_from = rich.model_id
    converted = convert_history(source, convert_from, new_id)
    fits, _pct, _tokens = estimate_fit(converted, new_id)
    if fits:
        del agent.messages[:]
        agent.messages.extend(converted)
        mode_word = "kept"
    else:
        del agent.messages[:]
        agent.messages.extend(converted)
        kept = compact_messages(
            agent, summarize=lambda old: model_summarize(agent, old)
        )
        mode_word = "compacted" if kept < len(converted) else "kept"
    if rich is not None and _has_thinking(source):
        rich.messages = copy.deepcopy(source)
        # Provenance follows the thinking, not the away model: after a
        # restore the stashed blocks are the ORIGINAL vendor's.
        rich.model_id = convert_from
        rich.length = len(source)
        rich.prefix_hash = canonical_prefix_hash(source)
    count = len(agent.messages)
    suffix = ", thinking restored" if restored else ""
    return (
        resolved_id,
        f"Model: {new_id} — conversation continued ({count} messages {mode_word}{suffix}).",
    )


def run_loop(
    agent: Any,
    *,
    session_id: str,
    index: SessionIndex,
    model_id: str | None = None,
) -> None:
    """Run the REPL until Ctrl-D or /exit.

    One ``PromptSession`` owns input; slash lines dispatch through the
    router while plain text runs synchronously with the prompt suspended
    via ``patch_stdout``. Ctrl-C cancels the line, Ctrl-D exits cleanly
    with an explicit save plus an index recency bump.

    Phase 4: the loop owns the session-sticky :class:`ModeState`
    (``/mode`` cycling, ``/approve`` handoff, Plan input prefix), the
    per-turn :class:`SteeringState` lifecycle (reader started before
    ``agent(text)``, stopped after), and the per-turn caller-owned
    cancel event behind the two-press Ctrl-C state machine.

    Phase 5: the loop owns the active model id (``/model`` swaps apply
    here at the idle prompt, never mid-turn) and persists the choice to
    ``ProviderConfig`` (model string only, never credentials).
    """
    from strands_harness.defaults import DEFAULT_MODEL

    from strands_code_cli.provider_config import ProviderConfig

    console.print(f"[dim]Session {session_id} — Ctrl-D to exit.[/dim]")
    session: PromptSession = PromptSession(history=_history())
    mode = ModeState()
    current_model = (
        model_id or ProviderConfig.load().model or DEFAULT_MODEL
    )
    session_turns: list = []
    stash_path = rich_stash_path(index.root, session_id)
    rich = RichHistory.load(stash_path)
    slot = _steering_slot_for(agent)
    set_gate_mode(mode.mode)
    cancel_armed_at: float | None = None
    titled = False
    while True:
        try:
            text = session.prompt("> ")
        except KeyboardInterrupt:
            continue  # Ctrl-C cancels the line
        except EOFError:
            break  # Ctrl-D exits
        if not text.strip():
            continue  # empty input submits nothing; re-prompt
        action, message = dispatch(
            text,
            session_id=session_id,
            index=index,
            mode=mode,
            current_model=current_model,
            agent=agent,
            session_turns=session_turns,
        )
        if action == "exit":
            break
        if action == "reply":
            if message:
                console.print(message)
            set_gate_mode(mode.mode)  # /mode or /approve may have flipped
            head = text.strip().partition(" ")[0].lower()
            if head in ("/compact", "/clear"):
                explicit_save(agent)  # history mutated: flush immediately
                index.ensure(session_id)
                rich.reset()
                rich.save(stash_path)  # empty stash removes the sidecar
            continue
        if action == "model" and message is not None:
            try:
                resolved_id, reply = apply_model_action(
                    agent, message, turn_running=False, current_model=current_model, rich=rich
                )
            except Exception as exc:  # noqa: BLE001 — a failed switch must not kill the session
                console.print(f"Model switch failed ({exc}); session unchanged.")
                continue
            console.print(reply)
            if resolved_id is not None:
                current_model = message  # verbatim selection string persists
                try:
                    ProviderConfig.load().save_model_choice(message)
                except ValueError as exc:
                    logger.warning("Model choice not persisted: %s", exc)
                explicit_save(agent)
                index.ensure(session_id)
                rich.save(stash_path)
            continue
        steering = SteeringState()
        turn_id = f"{session_id}:{uuid.uuid4().hex}"
        cancel_event = threading.Event()
        reader = None
        cancelled = False
        prev_sigint: Any = None
        if threading.current_thread() is threading.main_thread():
            prev_sigint = signal.getsignal(signal.SIGINT)
            signal.signal(
                signal.SIGINT, _make_turn_sigint_handler(cancel_event, prev_sigint)
            )
        try:
            with output_context():
                bind_turn(turn_id)
                steering.bind_turn(turn_id)
                slot.state = steering
                set_gate_mode(mode.mode)
                reader = start_steering_reader(steering, gate_open)
                agent_text = message if message is not None else text
                try:
                    if mode.mode == "plan":
                        result = _invoke_agent(
                            agent, f"{PLAN_PREFIX}\n\n{agent_text}", cancel_event
                        )
                    else:
                        result = _invoke_agent(agent, agent_text, cancel_event)
                except (KeyboardInterrupt, TurnCancelled):
                    raise
                except Exception as exc:
                    # Provider/model errors (validation, throttling, ...) must
                    # fail the turn, never the session: report and re-prompt.
                    console.print(f"[red]Turn failed ({type(exc).__name__}): {exc}[/red]")
                    continue
                usage = record_turn_metrics(result, current_model, session_turns)
                if usage is not None:
                    console.print(f"[dim]{usage}[/dim]")
                announcement = maybe_auto_compact(agent, current_model)
                if announcement is not None:
                    console.print(announcement)
                    explicit_save(agent)
                    index.ensure(session_id)
        except KeyboardInterrupt:
            cancelled = True
            cancel_armed_at = _handle_turn_cancel(
                agent, session_id, index, cancel_event, cancel_armed_at
            )
        finally:
            if prev_sigint is not None:
                signal.signal(signal.SIGINT, prev_sigint)
            if reader is not None:
                reader.stop()
            slot.state = None
        if not cancelled and mode.mode == "plan":
            mode.note_plan_proposed()
        if not titled:
            titled = True
            _maybe_auto_title(agent, session_id, index, text)
    explicit_save(agent)
    index.ensure(session_id)
    console.print("[dim]Session saved.[/dim]")
