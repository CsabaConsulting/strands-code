"""Minimal REPL loop: prompt, synchronous agent turn, clean exit."""

from __future__ import annotations

import asyncio
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
    extractive_summarize,
    compact_messages,
    scrub_credentials,
)
from strands_code_cli.mode import PLAN_PREFIX, ModeState
from strands_code_cli.model_switch import (
    MODEL_REFUSAL,
    apply_switch,
    convert_history,
    estimate_fit,
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
from strands_code_cli.session_index import SessionIndex
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


def _invoke_agent(agent: Any, text: str, cancel_event: threading.Event) -> None:
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
            agent(text, cancel_signal=cancel_event)
        else:
            agent(text)
        return
    kwargs = {"cancel_signal": cancel_event} if hasattr(agent, "cancel_signal") else {}
    with broker.pump(cancel_event):
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(agent, text, **kwargs)
            while True:
                if future.done():
                    try:
                        future.result()
                    except TurnCancelled:
                        # Worker aborted on cancel without a main-thread
                        # KeyboardInterrupt reaching us: same cancel path.
                        raise KeyboardInterrupt from None
                    return
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


def _live_summarize(agent: Any, old: list) -> str:
    """Summarize old messages via the session model, extractive fallback.

    Summarizer input is credential-scrubbed best-effort; failures fall back
    to the offline extractive summary (compact must never crash the loop).
    """
    texts = [
        block.get("text", "")
        for message in old
        if message.get("role") == "user"
        for block in message.get("content", [])
        if "text" in block
    ]
    prompt = (
        "Summarize this earlier conversation for context compaction. "
        "Keep decisions, file paths, and tool outcomes; drop chatter:\n"
        + scrub_credentials("\n".join(texts))[:6000]
    )
    try:
        generate = getattr(getattr(agent, "model", None), "generate", None)
        if generate is None:
            raise AttributeError("agent exposes no direct model call")
        raw = generate(prompt)
        candidate = raw if isinstance(raw, str) else getattr(raw, "text", "") or ""
        if candidate.strip():
            return candidate.strip()
    except Exception:
        pass
    return extractive_summarize(old)


def apply_model_action(
    agent: Any,
    new_id: str,
    *,
    turn_running: bool,
    current_model: str,
) -> tuple[str | None, str]:
    """Apply a validated /model selection (loop-owned; never the router).

    Idle only: a running turn gets the immediate refusal reply, never a
    queue (D-01 fail-closed). Otherwise convert-when-fits else
    summarize-old + keep-recent + replay-last-user-message, then the
    tracer-winning in-place swap.

    Args:
        agent: Live session agent.
        new_id: Validated ``provider/name`` selection (verbatim).
        turn_running: True when a turn is in flight → refuse.
        current_model: Active model id string for the fit estimate.

    Returns:
        ``(resolved_id, reply)``; resolved_id is None on refusal.
    """
    if turn_running:
        return (None, MODEL_REFUSAL)
    converted = convert_history(list(agent.messages), current_model, new_id)
    fits, _pct, _tokens = estimate_fit(converted, new_id)
    if fits:
        del agent.messages[:]
        agent.messages.extend(converted)
        mode_word = "kept"
    else:
        del agent.messages[:]
        agent.messages.extend(converted)
        kept = compact_messages(
            agent, summarize=lambda old: _live_summarize(agent, old)
        )
        mode_word = "compacted" if kept < len(converted) else "kept"
    _model, resolved_id = apply_switch(agent, new_id)
    count = len(agent.messages)
    return (
        resolved_id,
        f"Model: {new_id} — conversation continued ({count} messages {mode_word}).",
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
        )
        if action == "exit":
            break
        if action == "reply":
            if message:
                console.print(message)
            set_gate_mode(mode.mode)  # /mode or /approve may have flipped
            continue
        if action == "model" and message is not None:
            resolved_id, reply = apply_model_action(
                agent, message, turn_running=False, current_model=current_model
            )
            console.print(reply)
            if resolved_id is not None:
                current_model = message  # verbatim selection string persists
                try:
                    ProviderConfig.load().save_model_choice(message)
                except ValueError as exc:
                    logger.warning("Model choice not persisted: %s", exc)
                explicit_save(agent)
                index.ensure(session_id)
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
                if mode.mode == "plan":
                    _invoke_agent(agent, f"{PLAN_PREFIX}\n\n{agent_text}", cancel_event)
                else:
                    _invoke_agent(agent, agent_text, cancel_event)
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
