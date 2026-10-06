"""Minimal REPL loop: prompt, synchronous agent turn, clean exit."""

from __future__ import annotations

import asyncio
import copy
import logging
import os
import queue
import re
import signal
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from time import monotonic, sleep
from pathlib import Path
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory, History

from rich.console import Console

from strands_code_cli.btw import (
    BTW_IDLE_APPROVAL,
    BtwContext,
    BtwQueue,
    append_btw_turn,
    build_btw_agent,
    register_btw_cancel,
    render_btw_error,
    unregister_btw_cancel,
)
from strands_code_cli.choice import radio_choice
from strands_code_cli.cost_context import (
    AUTO_COMPACT_PCT,
    MODEL_PRICING,
    compact_messages,
    estimate_messages_tokens,
    model_summarize,
    usage_line,
    window_for,
)
from strands_code_cli.memory_file import (
    MEMORY_RELOAD_NOTE,
    load_memory,
    memory_banner,
    memory_section_names,
    sweep_memory_files,
)
from strands_code_cli.memory_modes import (
    MEMORY_FACT_DIR,
    CurateQueue,
    InitState,
    MemoryModeConfig,
    MemoryModeState,
    ReviseState,
    format_revise_prompt,
    seed_promotion_seen,
    silent_note,
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
    supports_streaming_tools,
    to_stash_json,
)
from strands_code_cli.output import output_context, print_plain
from strands_code_cli.policy_gate import (
    TurnCancelled,
    _active_broker,
    bind_turn,
    gate_open,
    set_mode as set_gate_mode,
)
from strands_code_cli.router import (
    apply_approved_proposal,
    apply_memory_section,
    dispatch,
    read_memory_section,
)
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


def flush_memory(agent: Any) -> None:
    """Flush pending harness memory extractions so short runs lose nothing.

    Mirrors explicit_save exactly: guarded for test doubles, logged,
    never raised.
    """
    manager = getattr(agent, "memory_manager", None)
    flush = getattr(manager, "flush", None)
    if flush is None:
        return
    try:
        asyncio.run(flush())
    except Exception as exc:
        logger.warning("Memory flush on exit failed: %s", exc)


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


def resolve_cancel_targets(choice: str | None) -> tuple[str, ...]:
    """Map a cancel-chooser answer to the cancel events to set (D-08).

    Unknown answers (None/ESC, anything unexpected) map to the empty
    tuple: fail closed, cancel nothing, the turn continues.
    """
    if choice == "main":
        return ("main",)
    if choice == "btw":
        return ("btw",)
    if choice == "both":
        return ("main", "btw")
    return ()


def ask_cancel_target() -> str | None:
    """Ask which worker to cancel; None fails closed (cancel nothing).

    No tty (tests, pipes) denies the prompt with None instead of
    crashing the turn. Ctrl-C inside the chooser propagates as
    KeyboardInterrupt — the caller escalates that to cancelling both.
    """
    try:
        return radio_choice(
            "Cancel which?",
            (("main", "Main task"), ("btw", "Side answer"), ("both", "Both")),
        )
    except RuntimeError:
        return None  # no tty: fail closed, the turn continues


def _choose_cancel_targets() -> tuple[str, ...]:
    """Run the chooser; Ctrl-C inside escalates to both.

    The executor shutdown below the pump waits for both workers, so an
    interrupt that carries no answer must still name targets —
    returning empty there would park shutdown on uncancelled workers.
    """
    try:
        return resolve_cancel_targets(ask_cancel_target())
    except KeyboardInterrupt:
        return ("main", "btw")


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
        {
            "turn": len(session_turns) + 1,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "model": current_model,
        }
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


def _finish_btw_turn(
    btw: BtwContext, btw_agent: Any, future: Any, question: str
) -> None:
    """Reap one side turn: hold its Q&A for the boundary flush.

    Main-thread only. A side failure renders fenced and never raises
    into the main turn; ``agent.messages`` is untouched here — the
    boundary flush owns history.
    """
    try:
        result = future.result()
    except Exception as exc:  # noqa: BLE001 — side failure must never fail the main turn
        render_btw_error(question, exc)
        return
    btw.pending.append((question, _result_text(btw_agent, result), result))
    btw.done = True


def _invoke_parallel(
    agent: Any,
    text: str,
    kwargs: dict,
    btw: BtwContext,
    broker: Any,
    cancel_event: threading.Event,
    both_running: threading.Event | None = None,
    side_pool: ThreadPoolExecutor | None = None,
) -> Any:
    """Run one main turn with a parallel /btw side channel (LOOP-03).

    The main turn runs on a turn-scoped pool while side agents run on
    the session side pool (one worker: at most one side agent at a
    time — further questions wait their turn), all driven from this
    (main) thread under one broker pump. A side run still going when
    the main turn ends is NOT joined: it stays attached to the
    session context (D-11 outliving-main) for the idle drain and the
    next turn's pump, which re-enters with the live future adopted.
    Completed Q&A flushes to history on the main thread before
    returning. Exactly one pump serves both futures; this never nests
    ``broker.pump`` and never calls :func:`_invoke_agent` recursively.

    ``both_running`` mirrors the side worker's lifetime for the turn
    SIGINT handler: set while a btw future runs, cleared otherwise.
    A Ctrl-C arriving with the side worker running opens the cancel
    chooser on this (main) thread — it must run here, inside the
    executor context, because unwinding first would park executor
    shutdown on still-uncancelled workers (and a no-choice answer
    resumes the pump, which is only possible before unwinding).

    ``side_pool`` is the session side executor (owned by
    :func:`run_loop`); None (direct calls, tests) builds an ad-hoc
    single-worker pool whose thread a live side rides to completion.
    """
    btw.cancel_targets = ()
    adopted = btw.detach_live()
    if adopted is not None:
        btw_agent, btw_future, btw_question = adopted
        btw.running.set()
        if both_running is not None:
            both_running.set()
    else:
        btw_future = None
        btw_question: str | None = None
        btw_agent: Any = None
    own_side_pool = None
    if side_pool is None:
        own_side_pool = ThreadPoolExecutor(max_workers=1)
        side_pool = own_side_pool
    try:
        return _pump_parallel(
            agent,
            text,
            kwargs,
            btw,
            broker,
            cancel_event,
            both_running,
            side_pool,
            btw_agent,
            btw_future,
            btw_question,
        )
    finally:
        if own_side_pool is not None:
            # Never join here: a live side rides this thread to
            # completion and the context reaps it (D-11 outliving).
            own_side_pool.shutdown(wait=False)


def _pump_parallel(
    agent: Any,
    text: str,
    kwargs: dict,
    btw: BtwContext,
    broker: Any,
    cancel_event: threading.Event,
    both_running: threading.Event | None,
    side_pool: ThreadPoolExecutor,
    btw_agent: Any,
    btw_future: Any,
    btw_question: str | None,
) -> Any:
    """Dual-future pump body (see :func:`_invoke_parallel`)."""
    pump = broker.pump(cancel_event) if broker is not None else nullcontext()
    with pump:
        with ThreadPoolExecutor(max_workers=1) as turn_pool:
            main_future = turn_pool.submit(agent, text, **kwargs)

            def _spawn_next() -> None:
                """Start one queued side run on the session pool (no-op when idle)."""
                nonlocal btw_future, btw_agent, btw_question
                try:
                    question = btw.spawn_queue.get_nowait()
                except queue.Empty:
                    # No side live, nothing queued: idle-side.
                    # Cleared only here (never at reap) so a submit
                    # landing mid-respawn still reads running.
                    btw.running.clear()
                    return
                try:
                    built_agent, prompt = btw.build(question)
                except Exception as exc:  # noqa: BLE001 — a failed spawn must never fail the main turn
                    render_btw_error(question, exc)
                    return
                # Fresh event per side run: the session context outlives
                # turns, so the live run always owns a pristine signal.
                btw.cancel_event = threading.Event()
                btw_kwargs = (
                    {"cancel_signal": btw.cancel_event}
                    if hasattr(built_agent, "cancel_signal")
                    else {}
                )
                btw_future = side_pool.submit(built_agent, prompt, **btw_kwargs)
                register_btw_cancel(broker, btw)
                btw_agent = built_agent
                btw_question = question
                btw.running.set()
                if both_running is not None:
                    both_running.set()

            while True:
                try:
                    if main_future.done():
                        if btw_future is None and btw.spawn_queue.empty():
                            break
                        # Main done but side work remains: reap a
                        # completed side, start the next queued question
                        # so it runs across the idle gap, then return
                        # WITHOUT waiting (D-11 outliving-main) — the
                        # live side stays attached for the idle drain
                        # and the next turn's pump.
                        if btw_future is not None and btw_future.done():
                            _finish_btw_turn(btw, btw_agent, btw_future, btw_question or "")
                            unregister_btw_cancel(broker)
                            btw_future = None
                            btw_question = None
                            btw_agent = None
                            if both_running is not None:
                                both_running.clear()
                        if btw_future is None:
                            _spawn_next()
                        break
                    if btw_future is not None and btw_future.done():
                        _finish_btw_turn(btw, btw_agent, btw_future, btw_question or "")
                        unregister_btw_cancel(broker)
                        btw_future = None
                        btw_question = None
                        btw_agent = None
                        if both_running is not None:
                            both_running.clear()
                    if btw_future is None:
                        _spawn_next()
                    if broker is not None:
                        req = broker.poll()
                        if req is not None:
                            req.run_prompt()
                    else:
                        sleep(0.005)
                except KeyboardInterrupt:
                    if btw_future is None or btw_future.done():
                        # Single worker (or side already reaped):
                        # legacy path, the main event is already set
                        # by the turn SIGINT handler.
                        btw.cancel_event.set()
                        unregister_btw_cancel(broker)
                        raise
                    targets = _choose_cancel_targets()
                    if not targets:
                        continue  # no choice: cancel nothing, turn continues
                    btw.cancel_targets = targets
                    if "main" in targets:
                        cancel_event.set()
                    if "btw" in targets:
                        btw.cancel_event.set()
                        unregister_btw_cancel(broker)
                    if "main" not in targets:
                        continue  # side aborts, main continues
                    if "btw" not in targets:
                        # Main aborts; hold the pump until the side
                        # answer lands (cancel-path hold only — normal
                        # completion never joins since D-11 outliving),
                        # then unwind for the cancel UX.
                        try:
                            while btw_future is not None and not btw_future.done():
                                if broker is not None:
                                    req = broker.poll()
                                    if req is not None:
                                        req.run_prompt()
                                else:
                                    sleep(0.005)
                        except KeyboardInterrupt:
                            # Second interrupt while draining: stop
                            # everything rather than park shutdown; the
                            # aborting side stays attached so the next
                            # turn reaps it instead of orphaning it.
                            btw.cancel_targets = ("main", "btw")
                            btw.cancel_event.set()
                            unregister_btw_cancel(broker)
                            if btw_future is not None:
                                btw.attach_live(btw_agent, btw_future, btw_question or "")
                            if both_running is not None:
                                both_running.clear()
                            raise
                        _finish_btw_turn(btw, btw_agent, btw_future, btw_question or "")
                        unregister_btw_cancel(broker)
                        btw_future = None
                        btw_question = None
                        btw_agent = None
                        if both_running is not None:
                            both_running.clear()
                    else:
                        # Both picked: the side aborts on its event; it
                        # stays attached so the next turn reaps the
                        # abort (fenced error, flag hygiene).
                        if btw_future is not None:
                            btw.attach_live(btw_agent, btw_future, btw_question or "")
                        if both_running is not None:
                            both_running.clear()
                    raise
            if btw_future is not None:
                # Outliving-main: the side keeps running past the turn
                # boundary; the idle drain and the next turn's pump
                # reap it from the session context.
                btw.attach_live(btw_agent, btw_future, btw_question or "")
            try:
                result = main_future.result()
            except TurnCancelled:
                # Worker aborted on cancel without a main-thread
                # KeyboardInterrupt reaching us: same cancel path.
                btw.cancel_event.set()
                unregister_btw_cancel(broker)
                raise KeyboardInterrupt from None
    history = getattr(agent, "messages", None)
    if isinstance(history, list):
        for question, answer, _ in btw.pending:
            append_btw_turn(history, question, answer)
    return result


def _btw_context_for(agent: Any) -> BtwContext:
    """Session side-channel state closing over the parent factory kwargs.

    The build closure replays the ``create_harness`` kwargs stashed by
    ``build_agent`` with the live resolved model (D-07: the SAME model
    object, never a re-resolved one) and a fresh history snapshot per
    spawn. One context serves the whole session (D-11 outliving-main):
    the queue, pending, and live handle survive turn boundaries.
    """
    parent_kwargs = dict(getattr(agent, "_harness_kwargs", {}) or {})
    live_model = getattr(agent, "model", None)
    if live_model is not None:
        parent_kwargs["model"] = live_model

    def _build(question: str) -> tuple[Any, list]:
        history = getattr(agent, "messages", None) or []
        return build_btw_agent(parent_kwargs, list(history), question)

    return BtwContext(
        spawn_queue=BtwQueue(),
        build=_build,
        cancel_event=threading.Event(),
        pending=[],
    )


def _invoke_agent(
    agent: Any,
    text: str,
    cancel_event: threading.Event,
    *,
    btw: BtwContext | None = None,
    both_running: threading.Event | None = None,
    side_pool: ThreadPoolExecutor | None = None,
) -> Any:
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

    With ``btw`` set, the turn runs on the dual-future pump
    (:func:`_invoke_parallel`): the main turn plus at most one side
    agent under the single broker pump, and a side run still going at
    the boundary outlives the turn (D-11) for the idle drain.
    """
    broker = _active_broker()
    if broker is None and btw is None:
        if hasattr(agent, "cancel_signal"):
            return agent(text, cancel_signal=cancel_event)
        return agent(text)
    kwargs = {"cancel_signal": cancel_event} if hasattr(agent, "cancel_signal") else {}
    if broker is not None:
        broker.register_cancel("main", cancel_event)
    try:
        if btw is not None:
            return _invoke_parallel(
                agent, text, kwargs, btw, broker, cancel_event, both_running, side_pool
            )
        assert broker is not None
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
    finally:
        if broker is not None:
            broker.unregister_cancel("main")


def _drain_idle_btw(
    agent: Any,
    btw: BtwContext,
    broker: Any,
    current_model: str,
    session_turns: list,
) -> None:
    """Idle-boundary btw delivery (D-11 bounded-wait).

    Main-thread only; runs when the idle prompt returns a line and
    once on session exit. Reaps a completed outliving side run into
    history (boundary Q&A append) plus the session metrics row — the
    fenced transcript itself already streamed live. Never spawns (the
    turn pump owns the single spawn site) and never serves approvals:
    a side approval waiting at idle stays queued for the next turn's
    pump, announced once via :data:`BTW_IDLE_APPROVAL`.
    """
    taken = btw.take_done_live()
    if taken is not None:
        side_agent, future, question = taken
        before = len(btw.pending)
        _finish_btw_turn(btw, side_agent, future, question)
        unregister_btw_cancel(broker)
        delivered = btw.pending[before:]
        del btw.pending[before:]
        history = getattr(agent, "messages", None)
        for answered, body, result in delivered:
            if isinstance(history, list):
                append_btw_turn(history, answered, body)
            usage = record_turn_metrics(result, current_model, session_turns)
            if usage is not None:
                print_plain(console, usage, style="dim")
    if broker is not None and btw.has_live and broker.has_pending:
        if not btw.approval_announced:
            print_plain(console, BTW_IDLE_APPROVAL)
            btw.approval_announced = True
    elif broker is None or not broker.has_pending:
        btw.approval_announced = False


def _handle_turn_cancel(
    agent: Any,
    session_id: str,
    index: SessionIndex,
    cancel_event: threading.Event,
    armed_at: float | None,
    *,
    target: str = "main",
) -> float | None:
    """Two-press cancel state machine (LOOP-04, D-13/D-15/D-16).

    Press #1 requests graceful stop (caller-owned event set, observed
    at the next cancellation-safe point) and flushes the session so
    partial work survives even a killed CLI. Press #2 inside the window
    confirms (idempotent — stop already requested). A press after the
    window lapses re-states the honest position: no un-cancel exists,
    the remainder is dropped, the mode is unchanged.

    ``target`` names the cancelled worker for the chooser path (D-08);
    anything but ``"main"`` prefixes the line with ``[<target>]``. The
    ``"main"`` copy is byte-identical to the legacy single-worker UX.

    Returns:
        The updated arm timestamp (None when disarmed by confirm).
    """
    cancel_event.set()
    now = monotonic()
    confirmed = armed_at is not None and (now - armed_at) <= CANCEL_WINDOW_S
    if confirmed:
        line = CANCEL_CONFIRMED
    elif armed_at is not None:
        line = CANCEL_STILL
    else:
        line = CANCEL_FIRST_PRESS
    if target != "main":
        line = f"[{target}] {line}"
    print_plain(console, line, style="yellow")
    explicit_save(agent)
    index.ensure(session_id)
    return None if confirmed else now


def _make_turn_sigint_handler(
    cancel_event: threading.Event,
    prev: Any,
    *,
    both_running: threading.Event | None = None,
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

    While ``both_running`` is set (a side worker runs beside the main
    turn), the handler sets no event at all — the cancel chooser (D-08)
    names the targets instead. Otherwise the exact legacy set-main
    behavior is kept.

    The previous disposition is always chained (default re-raises
    KeyboardInterrupt), so the two-press UX is preserved whenever the
    exception does propagate. The handler itself stays side-effect-free
    apart from setting the event (async-signal-safety).
    """

    def _handler(signum: Any, frame: Any) -> None:
        if both_running is None or not both_running.is_set():
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


def _turn_appended_empty(before: int, messages: list) -> bool:
    """True when the turn recorded its user message but zero content blocks.

    The observed shape is ``[user, assistant(content=[])]`` — a successful
    turn whose output never landed (376 billed output tokens, nothing
    kept). Anything else (nothing appended, no user message, any content
    block at all) is not an empty turn: retrying blind there risks
    duplicating side effects or scrambling role order.
    """
    appended = list(messages)[before:]
    if not appended:
        return False
    if not any(m.get("role") == "user" for m in appended):
        return False
    return not any(m.get("content") for m in appended if m.get("role") == "assistant")


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
    tools_note = (
        " Warning: this model rejects tool use in streaming mode — turns "
        "will fail until a non-streaming fallback lands upstream (/model to switch back)."
        if not supports_streaming_tools(new_id)
        else ""
    )
    return (
        resolved_id,
        f"Model: {new_id} — conversation continued ({count} messages {mode_word}{suffix}).{tools_note}",
    )


def _review_answer() -> str:
    """One approve/deny/revise answer; anything unclear fails closed to deny."""
    if sys.stdin.isatty():
        from strands_code_cli.choice import radio_choice

        try:
            picked = radio_choice(
                "Memory proposal",
                [
                    ("approve", "Approve — apply to memory"),
                    ("deny", "Deny — skip, don't ask again"),
                    ("revise", "Revise in words — describe the change"),
                ],
                default=1,  # fail-closed highlight on deny
            )
        except RuntimeError:
            return "deny"
        return picked if picked in ("approve", "deny", "revise") else "deny"
    # Same stream discipline as the gate: print the prompt, then bare
    # input() so echo stays on the prompt line.
    print("approve / deny / revise [deny]: ", end="", flush=True)
    typed = input().strip().lower()
    if typed in ("approve", "a", "y", "yes"):
        return "approve"
    if typed in ("revise", "r"):
        return "revise"
    return "deny"  # empty and unknown fail closed


def review_memory_queue(
    queue: CurateQueue,
    mode_state: MemoryModeState,
    apply_fn: Any,
    on_revise: Any = None,
) -> list[str]:
    """Turn-boundary curate review; returns transcript lines to print.

    Silent mode applies every pending proposal with one
    :func:`silent_note` line each. Curate mode prompts per proposal
    with the full body quoted plus the source line, then an
    approve/deny/revise-in-words choice (fail-closed default on deny;
    typed path when stdin is not a tty). The revise choice reads one
    instruction line and hands ``(proposal, instruction)`` to
    ``on_revise`` (None keeps the test-only noted path); a wired
    revise arms the round and ends the review — one revise turn per
    boundary, the rest stay pending. Ctrl-C or Ctrl-D stops the
    review; unreviewed proposals stay pending for the next turn.
    """
    lines: list[str] = []
    pending = queue.list_pending()
    if mode_state.mode == "silent":
        for proposal in pending:
            queue.approve(proposal.id, apply_fn)
            lines.append(silent_note(proposal.section, proposal.source))
        return lines
    for proposal in pending:
        try:
            with output_context():
                for body_line in proposal.body.splitlines() or [""]:
                    print(f"> {body_line}")
                print(f"Source: {proposal.source} → section {proposal.section}")
                answer = _review_answer()
                instruction = ""
                if answer == "revise":
                    print("Describe the change in words: ", end="", flush=True)
                    instruction = input().strip()
        except KeyboardInterrupt:
            break
        except EOFError:
            break  # Ctrl-D fails closed: proposals stay pending
        if answer == "approve":
            lines.append(queue.approve(proposal.id, apply_fn))
        elif answer == "revise":
            if on_revise is None:
                lines.append(f"Revise for {proposal.id} noted — proposal kept pending.")
            else:
                note = on_revise(proposal, instruction)
                if note:
                    lines.append(note)
                break  # one revise turn per boundary; rest stay pending
        else:
            lines.append(queue.deny(proposal.id))
    return lines


_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
"""First-fence matcher for revise/init consumer turns."""


def _first_fence(text: str) -> tuple[str | None, str]:
    """First fenced block plus the one-line tail summary after it.

    Returns ``(None, "")`` when no fenced block is present. The block
    keeps its content verbatim apart from the single line break
    before the closing fence.
    """
    match = _FENCE_RE.search(text)
    if match is None:
        return None, ""
    block = match.group(1)
    if block.endswith("\n"):
        block = block[:-1]
    summary = ""
    for line in text[match.end() :].splitlines():
        if line.strip():
            summary = line.strip()
            break
    return block, summary


def _message_text(message: Any) -> str:
    """Join the text blocks of one Strands message dict ("" when none)."""
    if not isinstance(message, dict):
        return ""
    parts = [
        block["text"]
        for block in message.get("content", []) or []
        if isinstance(block, dict) and isinstance(block.get("text"), str)
    ]
    return "\n".join(p for p in parts if p)


def _result_text(agent: Any, result: Any) -> str:
    """Best-effort text of one agent-turn result (revise/init consumers).

    Prefers the result's own text/message payload, then the last
    assistant text in history; empty string when nothing is found.
    """
    if isinstance(result, str):
        return result
    text = getattr(result, "text", None)
    if isinstance(text, str) and text:
        return text
    found = _message_text(getattr(result, "message", None))
    if found:
        return found
    history = getattr(agent, "messages", None)
    if isinstance(history, list):
        for entry in reversed(history):
            if isinstance(entry, dict) and entry.get("role") == "assistant":
                found = _message_text(entry)
                if found:
                    return found
    return ""


def _revise_answer() -> str:
    """One accept/revert/iterate answer; anything unclear fails closed to revert."""
    if sys.stdin.isatty():
        from strands_code_cli.choice import radio_choice

        try:
            picked = radio_choice(
                "Memory revision",
                [
                    ("accept", "Accept — apply the revision"),
                    ("revert", "Revert — keep the previous text"),
                    ("iterate", "Iterate — describe another change"),
                ],
                default=1,  # fail-closed highlight on revert
            )
        except RuntimeError:
            return "revert"
        return picked if picked in ("accept", "revert", "iterate") else "revert"
    print("accept / revert / iterate [revert]: ", end="", flush=True)
    typed = input().strip().lower()
    if typed in ("accept", "a", "y", "yes"):
        return "accept"
    if typed in ("iterate", "i"):
        return "iterate"
    return "revert"  # empty and unknown fail closed


def consume_revise_turn(
    result_text: str,
    revise_state: ReviseState,
    apply_fn: Any,
) -> str | None:
    """Consume one armed revise round; None means iterate (still armed).

    Quotes the revised block for review with its one-line summary,
    then prompts accept/revert/iterate (fail-closed default on
    revert; typed path when stdin is not a tty). Accept applies the
    block verbatim; revert and a missing fence leave the files
    untouched. Ctrl-C disarms and re-raises, so an interrupted round
    leaves both memory files byte-identical. Ctrl-D disarms and
    returns the revert note instead of raising.
    """
    section = revise_state.section
    block, summary = _first_fence(result_text)
    if block is None:
        revise_state.disarm()
        return f"No fenced block found — revision discarded, '{section}' unchanged."
    try:
        with output_context():
            for line in block.splitlines() or [""]:
                print(f"> {line}")
            if summary:
                print(f"Summary: {summary}")
            answer = _revise_answer()
            instruction = ""
            if answer == "iterate":
                print("Describe the change in words: ", end="", flush=True)
                instruction = input().strip()
    except KeyboardInterrupt:
        revise_state.disarm()
        raise
    except EOFError:
        revise_state.disarm()
        return f"Reverted — '{section}' unchanged."
    if answer == "accept":
        apply_fn(section, block)
        revise_state.disarm()
        return f"Memory section '{section}' updated."
    if answer == "iterate" and instruction:
        revise_state.arm(section, revise_state.previous_text, instruction)
        return None
    # Revert — plus empty-instruction iterate, which fails closed
    # instead of re-arming with a broken prompt.
    revise_state.disarm()
    return f"Reverted — '{section}' unchanged."


def _drain_revise_rounds(
    agent: Any,
    result: Any,
    revise_state: ReviseState,
    cancel_event: threading.Event,
    session_turns: list,
    current_model: str,
    mode: ModeState,
    apply_fn: Any = None,
) -> None:
    """Consume armed revise rounds, re-invoking while the user iterates.

    Prints each round's reply. Follow-up iterate turns reuse the
    normal invocation path (plan prefix, metrics); a failed
    follow-up disarms with a note. Ctrl-C propagates after consume
    disarms, so the interrupt lands on the cancel path with clean
    state.
    """
    writer = apply_fn if apply_fn is not None else apply_memory_section
    text = _result_text(agent, result)
    while revise_state.armed:
        reply = consume_revise_turn(text, revise_state, writer)
        if reply is not None:
            print_plain(console, reply)
        if not revise_state.armed:
            break
        follow_up = format_revise_prompt(
            revise_state.section,
            revise_state.previous_text,
            revise_state.instruction,
        )
        if mode.mode == "plan":
            follow_up = f"{PLAN_PREFIX}\n\n{follow_up}"
        try:
            follow_result = _invoke_agent(agent, follow_up, cancel_event)
        except (KeyboardInterrupt, TurnCancelled):
            raise
        except Exception as exc:
            print_plain(
                console, f"Turn failed ({type(exc).__name__}): {exc}", style="red"
            )
            console.print("Revise round dropped — the turn failed.")
            revise_state.disarm()
            break
        usage = record_turn_metrics(follow_result, current_model, session_turns)
        if usage is not None:
            print_plain(console, usage, style="dim")
        text = _result_text(agent, follow_result)


_INIT_FENCE_RE = re.compile(r"```proposed:(?P<label>[^\n]*)\n(?P<body>.*?)```", re.DOTALL)
"""Labeled-draft matcher for init consumer turns."""


def consume_init_turn(
    result_text: str,
    init_state: InitState,
    queue: CurateQueue,
) -> str:
    """Queue one labeled fenced block per stale section; always disarms.

    Only blocks labeled with a stale section queue (merge-scan:
    only missing or stale sections become proposals); repeats after
    the first block per section are ignored, as are unlabeled
    fences. Nothing is written — drafts enter the curate queue for
    approval.
    """
    depth = init_state.depth
    stale = set(init_state.stale_sections)
    queued_sections: set[str] = set()
    count = 0
    for match in _INIT_FENCE_RE.finditer(result_text):
        label = match.group("label").strip()
        if label not in stale or label in queued_sections:
            continue
        body = match.group("body")
        if body.endswith("\n"):
            body = body[:-1]
        queue.propose(label, f"init-{depth}", body)
        queued_sections.add(label)
        count += 1
    init_state.disarm()
    return f"Drafted {count} sections from {depth} scan — review with /memory."


def skill_match_note(skills: Any, text: str) -> str | None:
    """Echo line confirming a typed slash head matched a loaded skill.

    Mirrors the dispatch head split (strip, slash head before the
    first space); typos, unknown names, shadowed entries, and
    non-slash lines stay silent (D-13 accept-echo).

    Args:
        skills: Loop-owned skill index, or None when skills are off.
        text: Raw input line already routed to an agent turn.

    Returns:
        ``"Matched skill '<namespaced>' — <description>"`` on a
        match, else None.
    """
    stripped = text.strip()
    if not stripped.startswith("/") or skills is None:
        return None
    head = stripped.partition(" ")[0]
    entry = skills.resolve(head[1:])
    if entry is None or entry.shadowed:
        return None
    return f"Matched skill '{entry.namespaced}' — {entry.description}"


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

    Phase 6: the loop owns the dual-memory :class:`MemorySnapshot`
    (first-load banner, per-turn mtime reload sweep with one transcript
    note per changed file) and flushes pending harness extractions via
    ``flush_memory`` on exit and after ``/compact``/``/clear``. The loop
    also owns the session-sticky :class:`MemoryModeState` (opening in
    the persisted home choice) plus :class:`CurateQueue`: each turn
    boundary sweeps promotion candidates — facts predating the launch
    and already-memorialized sections stay quiet — then reviews the
    queue (prompting in curate mode, auto-applying in silent mode). Armed revise rounds (``/memory
    revise`` or the review's revise choice) run as agent turns whose
    fenced blocks are consumed after the turn, re-invoking while the
    user iterates. Armed ``/init`` drafts run one agent turn whose
    labeled blocks queue as proposals for curate approval.
    """
    from strands_harness.defaults import DEFAULT_MODEL

    from strands_code_cli.completer import build_completer
    from strands_code_cli.provider_config import ProviderConfig
    from strands_code_cli.skills import BUILTIN_SLASH_HEADS, SkillIndex

    console.print(f"[dim]Session {session_id} — Ctrl-D to exit.[/dim]")
    skills = SkillIndex()
    for warning in skills.warnings:
        print_plain(console, warning, style="yellow")
    memory_snapshot = load_memory()
    print_plain(console, memory_banner(memory_snapshot))

    def _skill_words() -> list[tuple[str, str]]:
        words = [(head, f"/{head}") for head in sorted(BUILTIN_SLASH_HEADS)]
        words.extend(
            (entry.name, f"/{entry.namespaced}")
            for entry in skills.list_entries()
            if not entry.shadowed
        )
        return words

    def _refresh_harness_skills() -> None:
        """Rescan the harness skills registry (no-op without the plugin).

        Reads the handle ``build_agent`` stashed; test doubles without
        one simply skip the refresh.
        """
        plugin = getattr(agent, "_skills_plugin", None)
        if plugin is None:
            return
        plugin.set_available_skills([str(skills.skills_dir)])

    session: PromptSession = PromptSession(
        history=_history(), completer=build_completer(_skill_words)
    )
    mode = ModeState()
    try:
        initial_mode = MemoryModeConfig.load().mode
    except ValueError:
        logger.warning("Ignoring tampered memory mode config; starting in curate.")
        initial_mode = "curate"
    memory_mode = MemoryModeState(initial=initial_mode)
    curate_queue = CurateQueue()
    promotion_seen: set[str] = seed_promotion_seen(MEMORY_FACT_DIR)
    revise_state = ReviseState()
    init_state = InitState()
    boundary_revise: dict[str, Any] = {"template": None}

    def _arm_revise_from_review(proposal: Any, instruction: str) -> str:
        """Boundary revise choice: arm the round and stash its turn text."""
        current = read_memory_section(proposal.section) or ""
        revise_state.arm(proposal.section, current, instruction)
        boundary_revise["template"] = format_revise_prompt(
            proposal.section, current, instruction
        )
        return f"Revise armed for '{proposal.section}' — running."

    current_model = (
        model_id or ProviderConfig.load().model or DEFAULT_MODEL
    )
    if not supports_streaming_tools(current_model):
        print_plain(
            console,
            f"Warning: {current_model} rejects tool use in streaming "
            "mode — turns will fail; /model to switch.",
            style="yellow",
        )
    session_turns: list = []
    stash_path = rich_stash_path(index.root, session_id)
    rich = RichHistory.load(stash_path)
    slot = _steering_slot_for(agent)
    set_gate_mode(mode.mode)
    cancel_armed_at: float | None = None
    titled = False
    # Session side channel (D-11 outliving-main): one context plus one
    # single-worker pool for the whole session, so a side run keeps
    # going across main-turn boundaries. The session broker pump stays
    # entered across idle gaps (turn pumps nest inside it), so a side
    # approval requested while main-idle enqueues for the next turn
    # instead of running inline on the worker thread. Entered and
    # exited manually around the loop to avoid re-indenting it; the
    # only exits are the breaks below plus a crashing exception (whose
    # process death moots the broker flag anyway).
    broker = _active_broker()
    session_cancel = threading.Event()
    session_pump = broker.pump(session_cancel) if broker is not None else None
    if session_pump is not None:
        session_pump.__enter__()
    btw_session = _btw_context_for(agent)
    side_pool = ThreadPoolExecutor(max_workers=1)
    while True:
        changed = sweep_memory_files(memory_snapshot)
        if changed:
            memory_snapshot = load_memory()
            for changed_path in changed:
                print_plain(
                    console, MEMORY_RELOAD_NOTE.format(filename=changed_path)
                )
        boundary_revise["template"] = None
        curate_queue.sweep_promotions(
            MEMORY_FACT_DIR,
            promotion_seen,
            skip_sections=memory_section_names(memory_snapshot.agent_text),
        )
        try:
            review_lines = review_memory_queue(
                curate_queue,
                memory_mode,
                apply_approved_proposal,
                on_revise=_arm_revise_from_review,
            )
        except (OSError, ValueError) as exc:
            review_lines = [f"Memory review skipped — write failed: {exc}"]
        for review_line in review_lines:
            print_plain(console, review_line)
        boundary_template = boundary_revise["template"]
        try:
            if boundary_template is not None:
                text = boundary_template
            else:
                # An outliving side streams through the idle proxy
                # above the prompt line instead of tearing it (D-11
                # idle delivery rides the documented patch_stdout
                # shape; turn dialogs already nest this way).
                with output_context():
                    text = session.prompt("> ")
        except KeyboardInterrupt:
            continue  # Ctrl-C cancels the line
        except EOFError:
            break  # Ctrl-D exits
        if not text.strip():
            continue  # empty input submits nothing; re-prompt
        _drain_idle_btw(agent, btw_session, broker, current_model, session_turns)
        if boundary_template is not None:
            action, message = "agent", boundary_template
            text = f"/memory revise {revise_state.section} {revise_state.instruction}"
        else:
            action, message = dispatch(
                text,
                session_id=session_id,
                index=index,
                mode=mode,
                current_model=current_model,
                agent=agent,
                session_turns=session_turns,
                skills=skills,
                harness_skills_refresh=_refresh_harness_skills,
                memory_mode=memory_mode,
                curate=curate_queue,
                revise=revise_state,
                init=init_state,
            )
        if action == "agent":
            match_note = skill_match_note(skills, text)
            if match_note is not None:
                print_plain(console, match_note)
        if action == "exit":
            break
        if action == "reply":
            if message:
                print_plain(console, message)
            set_gate_mode(mode.mode)  # /mode or /approve may have flipped
            head = text.strip().partition(" ")[0].lower()
            if head in ("/compact", "/clear"):
                explicit_save(agent)  # history mutated: flush immediately
                flush_memory(agent)
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
                print_plain(console, f"Model switch failed ({exc}); session unchanged.")
                continue
            print_plain(console, reply)
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
        both_running = threading.Event()
        btw = btw_session
        reader = None
        cancelled = False
        prev_sigint: Any = None
        if threading.current_thread() is threading.main_thread():
            prev_sigint = signal.getsignal(signal.SIGINT)
            signal.signal(
                signal.SIGINT,
                _make_turn_sigint_handler(
                    cancel_event, prev_sigint, both_running=both_running
                ),
            )
        try:
            with output_context():
                bind_turn(turn_id)
                steering.bind_turn(turn_id)
                slot.state = steering
                set_gate_mode(mode.mode)
                reader = start_steering_reader(
                    steering, gate_open, on_btw=btw.submit
                )
                agent_text = message if message is not None else text
                if mode.mode == "plan":
                    agent_text = f"{PLAN_PREFIX}\n\n{agent_text}"
                history = getattr(agent, "messages", None)
                before = len(history) if isinstance(history, list) else 0
                attempts = 0
                result = None
                failed = False
                while True:
                    attempts += 1
                    try:
                        result = _invoke_agent(
                            agent,
                            agent_text,
                            cancel_event,
                            btw=btw,
                            both_running=both_running,
                            side_pool=side_pool,
                        )
                    except (KeyboardInterrupt, TurnCancelled):
                        raise
                    except Exception as exc:
                        # Provider/model errors (validation, throttling, ...)
                        # must fail the turn, never the session: report and
                        # re-prompt. Errors never retry — only empty success.
                        print_plain(
                            console,
                            f"Turn failed ({type(exc).__name__}): {exc}",
                            style="red",
                        )
                        if "tool use in streaming mode" in str(exc):
                            console.print(
                                "[red]This model needs non-streaming tool use — "
                                "/model to switch to a supported model.[/red]"
                            )
                        failed = True
                        break
                    # Side-channel spend melts into the session total (D-15):
                    # each completed btw turn records through the shared
                    # row shape — no btw-specific field, tag, or report
                    # branch. Consumed so an empty-retry never re-records.
                    for _, _, btw_result in btw.pending:
                        btw_usage = record_turn_metrics(
                            btw_result, current_model, session_turns
                        )
                        if btw_usage is not None:
                            print_plain(console, btw_usage, style="dim")
                    btw.pending.clear()
                    usage = record_turn_metrics(result, current_model, session_turns)
                    if usage is not None:
                        print_plain(console, usage, style="dim")
                    history = getattr(agent, "messages", None)
                    if (
                        attempts >= 2
                        or not isinstance(history, list)
                        or not _turn_appended_empty(before, history)
                    ):
                        break
                    # Empty success: drop the no-op attempt so history shows
                    # the question once, then run it back exactly once.
                    del history[before:]
                    logger.info("Empty turn response; retrying once.")
                if failed:
                    if revise_state.armed:
                        revise_state.disarm()
                        console.print("Revise round dropped — the turn failed.")
                    if init_state.armed:
                        init_state.disarm()
                        console.print("Init draft dropped — the turn failed.")
                    continue
                if revise_state.armed:
                    _drain_revise_rounds(
                        agent,
                        result,
                        revise_state,
                        cancel_event,
                        session_turns,
                        current_model,
                        mode,
                    )
                if init_state.armed:
                    init_reply = consume_init_turn(
                        _result_text(agent, result), init_state, curate_queue
                    )
                    console.print(init_reply)
                history = getattr(agent, "messages", None)
                if (
                    attempts == 2
                    and isinstance(history, list)
                    and _turn_appended_empty(before, history)
                ):
                    console.print(
                        "[dim]No response content — the model returned empty twice.[/dim]"
                    )
                announcement = maybe_auto_compact(agent, current_model)
                if announcement is not None:
                    console.print(announcement)
                    explicit_save(agent)
                    index.ensure(session_id)
        except KeyboardInterrupt:
            cancelled = True
            if revise_state.armed:
                revise_state.disarm()
                console.print("Revise round dropped — interrupted, memory unchanged.")
            if init_state.armed:
                init_state.disarm()
                console.print("Init draft dropped — interrupted, memory unchanged.")
            # Chooser path (D-08): the pump records the named targets on
            # the turn context; each gets its own two-press line against
            # its own event, all judged against the same arm snapshot so
            # a first-press "both" reads first-press for both. No record
            # means the legacy single-worker path.
            targets = getattr(btw, "cancel_targets", None) or ("main",)
            armed_snapshot = cancel_armed_at
            for target in targets:
                event = btw.cancel_event if target == "btw" else cancel_event
                cancel_armed_at = _handle_turn_cancel(
                    agent, session_id, index, event, armed_snapshot, target=target
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
    # A side run completed just before exit still lands (history plus
    # metrics); a still-running one gets a graceful stop — the session
    # is over, so D-11's never-cut rule yields to a clean exit — and
    # the pool join below waits for the abort, never for full work.
    _drain_idle_btw(agent, btw_session, broker, current_model, session_turns)
    if btw_session.has_live:
        btw_session.cancel_event.set()
    try:
        side_pool.shutdown(wait=True)
    except KeyboardInterrupt:
        side_pool.shutdown(wait=False)
        raise
    if session_pump is not None:
        session_pump.__exit__(None, None, None)
    explicit_save(agent)
    flush_memory(agent)
    index.ensure(session_id)
    console.print("[dim]Session saved.[/dim]")
