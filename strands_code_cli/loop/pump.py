"""Parallel main/side pump for agent turns (LOOP-03, D-11).

The dual-future pump: the main turn plus at most one side agent run
under the single broker pump, with the cancel chooser, the
outliving-main handoff, and the boundary Q&A flush. The turn loop
(:mod:`strands_code_cli.loop.core`) enters through
:func:`_invoke_parallel`; the pump imports its turn-loop helpers
(poll, reap, chooser) from core at module level, so core reaches back
only through a deferred import (see :func:`_invoke_agent`).
"""

from __future__ import annotations

import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from time import sleep
from typing import Any

from strands_code_cli.loop.btw import (
    BtwContext,
    append_btw_turn,
    register_btw_cancel,
    render_btw_error,
    unregister_btw_cancel,
)
from strands_code_cli.loop.core import (
    CANCEL_FIRST_PRESS,
    _choose_cancel_targets,
    _finish_btw_turn,
    _poll_live,
    console,
)
from strands_code_cli.output import print_plain
from strands_code_cli.policy_gate import TurnCancelled, worker_cancelled


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

    Cancel aborts at step granularity (no thread preemption): model
    streams and approval waits abort promptly, but a synchronous tool
    step runs to completion — so the pump acknowledges the cancel
    before raising, while the pool-exit join waits out the step.
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
                            _finish_btw_turn(
                                btw, btw_agent, btw_future, btw_question or ""
                            )
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
                        req = _poll_live(broker)
                        if req is not None:
                            req.run_prompt()
                    else:
                        sleep(0.005)
                except KeyboardInterrupt:
                    if btw_future is None or btw_future.done():
                        # Single worker (or side already reaped):
                        # legacy path, the main event is normally set
                        # by the turn SIGINT handler — but a stale
                        # both_running flag may have suppressed it, so
                        # set here too (idempotent) and the turn always
                        # stops.
                        cancel_event.set()
                        btw.cancel_event.set()
                        unregister_btw_cancel(broker)
                        # Ack before the pool-exit join waits out the step.
                        print_plain(console, CANCEL_FIRST_PRESS, style="yellow")
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
                                    req = _poll_live(broker)
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
                                btw.attach_live(
                                    btw_agent, btw_future, btw_question or ""
                                )
                            if both_running is not None:
                                both_running.clear()
                            print_plain(console, CANCEL_FIRST_PRESS, style="yellow")
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
                        # abort (fenced cancel note, flag hygiene).
                        if btw_future is not None:
                            btw.attach_live(btw_agent, btw_future, btw_question or "")
                        if both_running is not None:
                            both_running.clear()
                    print_plain(console, CANCEL_FIRST_PRESS, style="yellow")
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
            except Exception as exc:
                if not worker_cancelled(exc):
                    raise
                # SDK-wrapped cancel (EventLoopException): same path.
                btw.cancel_event.set()
                unregister_btw_cancel(broker)
                raise KeyboardInterrupt from None
    history = getattr(agent, "messages", None)
    if isinstance(history, list):
        for question, answer, _, _ in btw.pending:
            append_btw_turn(history, question, answer)
    return result
