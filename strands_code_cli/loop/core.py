"""Minimal REPL loop: prompt, synchronous agent turn, clean exit."""

from __future__ import annotations

import asyncio
import copy
import logging
import os
import re
import signal
import sys
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory, History, InMemoryHistory

import strands_code_cli.routing.core as routing_mod
from strands_code_cli.cost.cost_context import (
    AUTO_COMPACT_PCT,
    MODEL_PRICING,
    compact_messages,
    estimate_messages_tokens,
    model_summarize,
    usage_line,
    window_for,
)
from strands_code_cli.dispatch.core import (
    apply_approved_proposal,
    apply_memory_section,
    dispatch,
    read_memory_section,
)
from strands_code_cli.entry.provider_config import ProviderConfig
from strands_code_cli.loop.btw import (
    BTW_IDLE_APPROVAL,
    BtwContext,
    BtwQueue,
    append_btw_turn,
    build_btw_agent,
    render_btw_cancelled,
    render_btw_dropped,
    render_btw_error,
    unregister_btw_cancel,
)
from strands_code_cli.loop.steering import (
    SteeringSlot,
    SteeringState,
    register_steering_hook,
    start_steering_reader,
)
from strands_code_cli.memory.memory_file import (
    MEMORY_RELOAD_NOTE,
    MemorySnapshot,
    load_memory,
    memory_banner,
    memory_section_names,
    sweep_memory_files,
)
from strands_code_cli.memory.memory_modes import (
    MEMORY_FACT_DIR,
    CurateQueue,
    InitState,
    MemoryModeState,
    ReviseState,
    format_revise_prompt,
    seed_promotion_seen,
    silent_note,
)
from strands_code_cli.model.model_switch import (
    MODEL_REFUSAL,
    UNARY_TOOL_MODE_NOTE,
    _has_reasoning,
    _provider_of,
    apply_switch,
    canonical_prefix_hash,
    convert_history,
    estimate_fit,
    from_stash_json,
    model_id_of,
    normalize_model_ref,
    prepare_resumed_history,
    resolve_harness_model,
    same_provider,
    same_vendor,
    scoped_base_url,
    supports_reasoning,
    supports_streaming_tools,
    to_stash_json,
)
from strands_code_cli.platform_io import (
    atomic_write_text,
    ensure_private_dir,
    refuse_symlink,
)
from strands_code_cli.policy.codeact import (
    CodeactState,
    CodeactStint,
    codeact_label,
    default_repl_handle,
    resolve_initial_interface,
    resolve_turn_interface,
    restore_after_turn,
    shape_turn_text,
    swap_for_code_turn,
)
from strands_code_cli.policy.diff_gate import DEFAULT_MODE as DEFAULT_DIFF_MODE
from strands_code_cli.policy.diff_gate import DiffModeState
from strands_code_cli.policy.mode import PLAN_PREFIX, ModeState
from strands_code_cli.policy.policy_gate import (
    TurnCancelled,
    broker_for,
    gate_for,
    gate_open,
    worker_cancelled,
)
from strands_code_cli.session.session_index import SessionIndex, rich_stash_path
from strands_code_cli.ui.attachments import (
    discover_workspace_files,
    prepare_turn_prompt,
)
from strands_code_cli.ui.choice import radio_choice
from strands_code_cli.ui.console import console, sanitize_display, sanitize_line
from strands_code_cli.ui.output import output_context, print_plain

logger = logging.getLogger(__name__)


def _prompt_inline(text: str) -> None:
    """Write an inline no-markup prompt without newline and flush before input()."""
    console.print(text, end="", markup=False, highlight=False)
    if hasattr(console.file, "flush"):
        console.file.flush()


_emitted_chain_skip_notes: set[str] = set()
"""D-03 skip notes already printed this session (tests reset by attribute)."""

TITLE_PROMPT = "Summarize this exchange in at most six words, plain words only: "
TITLE_WORDS = 6
TITLE_FALLBACK_WORDS = 8
TITLE_FALLBACK_CHARS = 60


def _history() -> History:
    """Reply history backed by a file; in-memory when the cache dir is unusable.

    History holds typed asks (T-01-03): the cache dir and file get the same
    0o700 treatment as the session/index dirs, with ancestor symlink refusal.
    """
    import os

    try:
        import platformdirs

        cache = ensure_private_dir(
            Path(platformdirs.user_cache_dir("strands-code")),
            "cache dir",
            mode=0o700,
            max_ancestors=1,
        )
        history_file = cache / "repl_history"
        refuse_symlink(history_file, "REPL history", max_ancestors=1)
        history_file.touch(exist_ok=True)
        os.chmod(history_file, 0o600)
        return FileHistory(str(history_file))
    except Exception as exc:  # best-effort history must never block the loop
        logger.warning("Falling back to in-memory REPL history: %s", exc)
        return InMemoryHistory()


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


def _maybe_auto_title(
    agent: Any, session_id: str, index: SessionIndex, first_text: str
) -> None:
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

    Holds the stdin guard for the dialog, mirroring ``ask()`` — the
    steering reader never steals chooser keys. No tty (tests, pipes)
    denies the prompt with None instead of crashing the turn. Ctrl-C
    inside the chooser propagates as KeyboardInterrupt — the caller
    escalates that to cancelling both.
    """
    try:
        with gate_open.hold():
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


def _poll_live(broker: Any) -> Any:
    """Next live approval request, skipping dead workers' (D-08, G-7-2 F-1).

    The pump is the only choke point that sees both workers: a request
    whose waiter's cancel event is already set belongs to a dead worker
    (cancel landed after queueing, or the pump won the poll race), so
    it is aborted — never served as a phantom dialog — and polling
    continues. ``cancel=None`` (legacy/tests) always serves.
    """
    while True:
        req = broker.poll()
        if req is None:
            return None
        cancel = getattr(req, "cancel", None)
        if cancel is not None and cancel.is_set():
            req.abort()
            continue
        return req


def _drain_reported_cost(model: Any) -> float | None:
    """Reported turn spend from a cost-aware model, else None (fail soft)."""
    take = getattr(model, "take_reported_costs", None)
    if not callable(take):
        # Agent-shaped callers carry the capture on the serving model.
        take = getattr(getattr(model, "model", None), "take_reported_costs", None)
        if not callable(take):
            return None
    try:
        from strands_code_cli.cost.reported_cost import sum_reported_costs

        return sum_reported_costs(take())
    except Exception:
        return None


_UNSET: Any = object()
"""Sentinel distinguishing an omitted reported_cost from explicit None."""


def _is_exclusive_usage_provider(model_id: str) -> bool:
    """True when ``inputTokens`` excludes cached read/write token counts."""
    lowered = model_id.lower()
    if lowered.startswith(("anthropic/", "bedrock/", "arn:")):
        return True
    return "/" not in lowered


def _extract_prompt_usage(
    result: Any,
    current_model: str,
    raw_in: int,
    raw_out: int,
) -> tuple[int, int, int]:
    """Normalize ``(total_input_tokens, cache_read, cache_write)`` from SDK metrics."""
    try:
        summary = result.metrics.get_summary()
        usage = summary.get("accumulated_usage") if isinstance(summary, dict) else None
    except Exception:
        return (raw_in, 0, 0)
    if not isinstance(usage, dict):
        return (raw_in, 0, 0)
    try:
        cache_read = max(0, int(usage.get("cacheReadInputTokens", 0) or 0))
        cache_write = max(0, int(usage.get("cacheWriteInputTokens", 0) or 0))
        total_tok = int(usage.get("totalTokens", 0) or 0)
    except (TypeError, ValueError):
        return (raw_in, 0, 0)
    if cache_read == 0 and cache_write == 0:
        return (raw_in, 0, 0)
    if total_tok > 0:
        is_bedrock = _provider_of(normalize_model_ref(current_model)) == "bedrock"
        if raw_in + raw_out != total_tok or (
            _is_exclusive_usage_provider(current_model)
            and (raw_in < cache_read or is_bedrock)
        ):
            total_in = raw_in + cache_read + cache_write
        else:
            total_in = raw_in
    elif _is_exclusive_usage_provider(current_model):
        total_in = raw_in + cache_read + cache_write
    else:
        total_in = raw_in
    return (total_in, cache_read, cache_write)


def record_turn_metrics(
    result: Any,
    current_model: str,
    session_turns: list,
    model: Any = None,
    reported_cost: Any = _UNSET,
) -> str | None:
    """Append one per-turn token row; return the usage line when computable.

    Best-effort display only: doubles without metrics (tests, direct calls)
    yield None instead of raising.
    """
    from strands_code_agent.utils import get_response_metrics

    # Drain first: a failed turn must never bleed costs into the next turn.
    # An explicitly passed reported cost (including None) wins without
    # consulting the model, so drained side turns never re-drain a newer
    # agent; only the omitted case drains the serving model.
    if reported_cost is _UNSET:
        reported = _drain_reported_cost(model)
    else:
        reported = reported_cost
    try:
        metrics = get_response_metrics(
            result, model_id=current_model, price_table=MODEL_PRICING
        )
    except Exception:
        return None
    try:
        raw_in = int(metrics.get("input_tokens", 0))
        out_tok = int(metrics.get("output_tokens", 0))
    except (TypeError, ValueError):
        return None
    in_tok, cache_read, cache_write = _extract_prompt_usage(
        result, current_model, raw_in, out_tok
    )
    row: dict[str, Any] = {
        "turn": len(session_turns) + 1,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "model": current_model,
    }
    if cache_read > 0:
        row["cache_read_tokens"] = cache_read
    if cache_write > 0:
        row["cache_write_tokens"] = cache_write
    if reported is not None:
        row["reported_cost"] = reported
    session_turns.append(row)
    return usage_line(
        in_tok,
        out_tok,
        current_model,
        reported_cost=reported,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        model=model,
    )


def maybe_auto_compact(agent: Any, current_model: str) -> str | None:
    """Compact at 80% of the window, pair-atomic; announce or return None."""
    window = window_for(current_model, model=getattr(agent, "model", None))
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
        try:
            result = future.result()
        except Exception as exc:  # noqa: BLE001 — side failure must never fail the main turn
            if worker_cancelled(exc):
                render_btw_cancelled(question)
                return
            render_btw_error(question, exc)
            return
        side_model = getattr(btw_agent, "model", None)
        reported = _drain_reported_cost(side_model)
        side_model_id = model_id_of(side_model, "")
        btw.pending.append(
            (question, _result_text(btw_agent, result), result, reported, side_model_id)
        )
        btw.done = True
    finally:
        _teardown_btw_agent(btw_agent)


def _route_side_spawn(
    question: str,
    kwargs: dict,
    live_model: Any,
    current_model: str,
    routing: routing_mod.RoutingState | None,
    routing_events: list | None,
) -> None:
    """One spawn-time side decision mutating the replayed kwargs (D-04).

    Runs synchronously on the pump (main) thread inside the build
    closure, once per spawn, before :func:`build_btw_agent`. A gated
    pick for another model validates its effort and resolves through
    ``resolve_model``, re-pointing the replayed ``model`` plus
    ``effort``; a same-model pick skips validation and resolve like
    the main hook's no-op fast path. Any hold or failure keeps the
    parent live model with no side note. The shared strategy, toggle,
    and quiet rules apply: routing off or unconfigured spawns
    exactly as before. A turn the pre-turn hook paused spawns with
    zero decisions on a held paused event. Every side decision,
    routed or held, appends one side-flagged routing event.
    """
    if routing is not None and not routing.is_on():
        return
    try:
        strategy = routing_mod.load_strategy()
    except ValueError:
        return
    if strategy is None or not strategy.candidates:
        return
    if routing is not None and routing.is_paused():
        _record_routing_event(
            routing_events,
            strategy=strategy,
            side=True,
            model=current_model,
            effort="",
            model_confidence=None,
            effort_confidence=None,
            tie_break=False,
            engine="paused",
            decision_engine="paused",
            usage=(0, 0, None),
            held=True,
        )
        return

    kwargs["model"] = live_model
    try:
        pick, engine, usage, detail = routing_mod.decide(
            strategy, current_model=current_model, side=True, ask=question
        )
    except Exception:  # noqa: BLE001 — side holds stay silent on the live model
        _record_routing_event(
            routing_events,
            strategy=strategy,
            side=True,
            model=current_model,
            effort="",
            model_confidence=None,
            effort_confidence=None,
            tie_break=False,
            engine="decide",
            decision_engine="decide",
            usage=(0, 0, None),
            held=True,
        )
        return
    if pick is None:
        if routing is not None and routing_mod.is_pause_detail(detail):
            routing.pause()
        _record_routing_event(
            routing_events,
            strategy=strategy,
            side=True,
            model=current_model,
            effort="",
            model_confidence=None,
            effort_confidence=None,
            tie_break=False,
            engine=engine,
            decision_engine=engine,
            usage=usage,
            held=True,
        )
        return
    if pick.model != current_model:
        try:
            effort_ok = routing_mod.validate_routed_effort(pick, strategy.candidates)
        except Exception:  # noqa: BLE001 — gate failure holds, never kills
            effort_ok = False
        if not effort_ok:
            _record_routing_event(
                routing_events,
                strategy=strategy,
                side=True,
                model=current_model,
                effort="",
                model_confidence=None,
                effort_confidence=None,
                tie_break=False,
                engine=engine,
                decision_engine=engine,
                usage=usage,
                held=True,
            )
            return
        try:
            side_base_url = scoped_base_url(
                kwargs.get("_base_url"),
                kwargs.get("_base_url_provider"),
                pick.model,
            )
            routed = resolve_harness_model(
                pick.model,
                pick.model,
                effort=pick.effort,
                base_url=side_base_url,
                api_mode=(
                    kwargs.get("_api_mode") if side_base_url is not None else None
                ),
            )
        except Exception:  # noqa: BLE001 — resolve failure holds to the live model
            _record_routing_event(
                routing_events,
                strategy=strategy,
                side=True,
                model=current_model,
                effort="",
                model_confidence=None,
                effort_confidence=None,
                tie_break=False,
                engine="resolve",
                decision_engine=engine,
                usage=usage,
                held=True,
            )
            return
        kwargs["model"] = routed
        kwargs["effort"] = pick.effort
    _record_routing_event(
        routing_events,
        strategy=strategy,
        side=True,
        model=pick.model,
        effort=pick.effort,
        model_confidence=pick.model_confidence,
        effort_confidence=pick.effort_confidence,
        tie_break=pick.tie_break,
        engine=engine,
        decision_engine=engine,
        usage=usage,
        held=False,
    )
    if not strategy.quiet:
        print_plain(
            console,
            routing_mod.format_routed_line(
                model=pick.model,
                effort=pick.effort,
                model_confidence=pick.model_confidence,
                effort_confidence=pick.effort_confidence,
                tie_break=pick.tie_break,
                truncated=routing_mod.TRUNCATION_MARKER in detail,
                prev_model=current_model,
                ask=question,
                side=True,
            ),
            style="dim",
        )


def _btw_context_for(
    agent: Any,
    *,
    routing: routing_mod.RoutingState | None = None,
    routing_events: list | None = None,
) -> BtwContext:
    """Session side-channel state closing over the parent factory kwargs.

    The build closure replays the ``create_harness`` kwargs stashed by
    ``build_agent`` with the live resolved model (D-07: the SAME model
    object, never a re-resolved one) and a fresh history snapshot per
    spawn. One context serves the whole session (D-11 outliving-main):
    the queue, pending, and live handle survive turn boundaries.
    Each spawn routes once through the shared strategy side-flagged
    (D-04); a live side run never re-decides, so a build issued while
    a run is attached spawns on the parent model with no decision.
    """
    parent_kwargs = dict(getattr(agent, "_harness_kwargs", {}) or {})
    live_model = getattr(agent, "model", None)
    if live_model is not None:
        parent_kwargs["model"] = live_model

    holder: dict[str, Any] = {}

    def _build(question: str) -> tuple[Any, list]:
        history = getattr(agent, "messages", None) or []
        kwargs = dict(parent_kwargs)
        live = getattr(agent, "model", None)
        if live is not None:
            kwargs["model"] = live
        for attr in ("_base_url", "_base_url_provider", "_api_mode"):
            val = getattr(agent, attr, None)
            if val is None:
                kwargs.pop(attr, None)
            else:
                kwargs[attr] = val
        kwargs["_parent_agent"] = agent
        btw = holder.get("btw")
        if btw is not None and btw.has_live:
            return build_btw_agent(kwargs, list(history), question)
        if live is not None:
            _route_side_spawn(
                question, kwargs, live, model_id_of(live, "?"), routing, routing_events
            )
        return build_btw_agent(kwargs, list(history), question)

    context = BtwContext(
        spawn_queue=BtwQueue(),
        build=_build,
        cancel_event=threading.Event(),
        pending=[],
    )
    holder["btw"] = context
    return context


def _set_gate_mode(agent: Any, mode_name: str) -> None:
    gate = gate_for(agent)
    if gate is not None:
        gate.set_mode(mode_name)


def _bind_gate_turn(agent: Any, turn_id: str) -> None:
    gate = gate_for(agent)
    if gate is not None:
        gate.bind_turn(turn_id)


def _invoke_agent(
    agent: Any,
    text: Any,
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
    broker = broker_for(agent)
    if broker is None and btw is None:
        if hasattr(agent, "cancel_signal"):
            return agent(text, cancel_signal=cancel_event)
        return agent(text)
    kwargs = {"cancel_signal": cancel_event} if hasattr(agent, "cancel_signal") else {}
    if broker is not None:
        broker.register_cancel("main", cancel_event)
    try:
        if btw is not None:
            # Deferred: pump.py owns the dual-future pump and imports its
            # core helpers at module level, so this edge goes the other
            # way to keep the package acyclic.
            from strands_code_cli.loop.pump import _invoke_parallel

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
                        except Exception as exc:
                            if not worker_cancelled(exc):
                                raise
                            # SDK-wrapped cancel: same cancel path.
                            raise KeyboardInterrupt from None
                    req = _poll_live(broker)
                    if req is None:
                        continue
                    req.run_prompt()
    finally:
        if broker is not None:
            broker.unregister_cancel("main")


async def _poll_idle_approvals(broker: Any) -> str:
    """Broker-poll arm of the idle race: returns once one waits."""
    while True:
        await asyncio.sleep(0.05)
        if broker.has_pending:
            return "APPROVAL"


async def _race_idle_episode(session: Any, broker: Any, buf: str) -> tuple[str, str]:
    """One prompt-vs-broker race; the loser is cancelled and settled."""

    # The prompt arm channels Ctrl-C/EOF as values: a KeyboardInterrupt
    # raised inside prompt_task would tear down run_until_complete
    # itself, stranding the poll task pending ("Task was destroyed but
    # it is pending"). Re-raised below, after the quiesce, it reaches
    # the idle loop's cancel-line/exit contracts with no task left over.
    async def _prompt_arm() -> tuple[str, Any]:
        try:
            return ("line", await session.prompt_async("> ", default=buf))
        except asyncio.CancelledError:
            raise  # our own cancel when the poll arm wins
        except BaseException as exc:
            return ("error", exc)

    prompt_task = asyncio.ensure_future(_prompt_arm())
    poll_task = asyncio.ensure_future(_poll_idle_approvals(broker))
    done, pending = await asyncio.wait(
        {prompt_task, poll_task}, return_when=asyncio.FIRST_COMPLETED
    )
    for task in pending:
        task.cancel()
    for task in pending:  # quiesce before the loop returns
        try:
            await task
        except BaseException:
            pass
    if prompt_task in done:
        kind, payload = prompt_task.result()
        if kind == "error":
            raise payload
        return ("line", payload)
    return ("approval", session.default_buffer.text)


def _run_idle_episode(session: Any, broker: Any, buf: str) -> tuple[str, str]:
    """Run one idle episode on a fresh loop; the loop never nests.

    Each episode owns its loop outright (new + close): the sync serve
    below always runs with no loop on the thread, so prompt_toolkit's
    ``.run()`` can never nest inside a running loop (the 07-03 probe-1
    disproof). Strictly sequential: suspend, serve sync, re-issue.
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_race_idle_episode(session, broker, buf))
    finally:
        try:
            loop.close()
        finally:
            asyncio.set_event_loop(None)


def _idle_prompt_multiplexed(
    session: Any, broker: Any, btw: BtwContext, *, initial_buf: str = ""
) -> str:
    """Idle prompt multiplexed against the broker queue (D-11 primary, E).

    Main-thread only; built exactly as the Task 1 live-pty spike proved
    (verdict GO in tests/test_idle_multiplex.py): the prompt races the
    broker queue, an approval arrival suspends the prompt, one request
    serves sync after the loop quiesces, and the prompt re-issues with
    the preserved buffer. No nested prompt_toolkit apps, ever.

    Ctrl-C in the serve dialog cancels the side run (the turn-semantic
    analogue — at idle the side is the only work) and re-issues with
    the buffer; Ctrl-C/EOF at the prompt propagate to the idle loop's
    line-cancel/exit contracts. No broker (tests, direct calls) — or a
    prompt()-only session double without prompt_async — keeps the
    legacy blocking prompt.
    """
    if broker is None or not hasattr(session, "prompt_async"):
        if initial_buf:
            try:
                return session.prompt("> ", default=initial_buf)
            except TypeError:
                pass
        return session.prompt("> ")
    buf = initial_buf
    while True:
        kind, text = _run_idle_episode(session, broker, buf)
        if kind == "line":
            return text
        buf = text  # approval won; the buffer survives the serve
        req = _poll_live(broker)
        if req is None:
            continue  # dead-tag drain ate it, or the poll won a race
        try:
            req.run_prompt()
        except KeyboardInterrupt:
            req.abort()
            btw.cancel_event.set()
            continue  # re-issue with the preserved buffer


def _drain_idle_btw(
    agent: Any,
    btw: BtwContext,
    broker: Any,
    current_model: str,
    session_turns: list,
    *,
    from_exit: bool = False,
) -> None:
    """Idle-boundary btw delivery (D-11 multiplex + bounded-wait remnant).

    Main-thread only; runs when the idle prompt returns a line and
    once on session exit. Reaps a completed outliving side run into
    history (boundary Q&A append) plus the session metrics row — the
    fenced transcript itself already streamed live. Never spawns (the
    turn pump owns the single spawn site).

    The multiplexed idle prompt serves approvals at idle, so the
    announce below only fires for the race sliver: an approval queued
    after the winning prompt episode returned but before this drain
    runs. It stays queued for the next turn's pump, announced once via
    :data:`BTW_IDLE_APPROVAL`. On the exit path (``from_exit``) the
    announce never fires — exit promises no next turn; the dropped
    side is named by :func:`_note_dropped_side` instead.
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
        for answered, body, result, reported, side_model_id in delivered:
            if isinstance(history, list):
                append_btw_turn(history, answered, body)
            usage = record_turn_metrics(
                result,
                side_model_id or current_model,
                session_turns,
                reported_cost=reported,
            )
            if usage is not None:
                print_plain(console, usage, style="dim")
    if broker is not None and btw.has_live and broker.has_pending:
        if not btw.approval_announced and not from_exit:
            print_plain(console, BTW_IDLE_APPROVAL)
            btw.approval_announced = True
    elif broker is None or not broker.has_pending:
        btw.approval_announced = False


def _note_dropped_side(btw: BtwContext, broker: Any) -> None:
    """Exit-path note: name a live side run before it is cancelled.

    Main-thread only; call after the exit drain (which reaps done runs)
    and before ``cancel_event.set()``. A still-attached run is dropped
    by the exit, so it is named with its state — waiting on an
    approval vs still running — instead of vanishing silently. Nothing
    attached (or already reaped) prints nothing.
    """
    if not btw.has_live:
        return
    waiting = broker is not None and broker.has_pending
    render_btw_dropped(btw.live_question or "", waiting)


def _cancel_agent_background_tasks(agent: Any) -> None:
    """Cancel outstanding background tasks on ``agent`` when supported."""
    cancel = getattr(agent, "cancel", None)
    if not callable(cancel):
        return
    try:
        cancel(cancel_background_tasks=True)
    except Exception as exc:  # noqa: BLE001 — best-effort cleanup
        logger.warning("Agent background cancel failed: %s", exc)


def _shutdown_agent(agent: Any) -> None:
    """Run ``agent.shutdown()`` at session exit when supported."""
    shutdown = getattr(agent, "shutdown", None)
    if not callable(shutdown):
        return
    try:
        shutdown()
    except Exception as exc:  # noqa: BLE001 — best-effort cleanup
        logger.warning("Agent shutdown failed: %s", exc)


def _teardown_btw_agent(btw_agent: Any) -> None:
    """Cancel background tasks, close REPLs, shut down, and unregister a side agent."""
    if btw_agent is None:
        return
    from strands_code_cli.sandbox.monty import close_agent_repls

    _cancel_agent_background_tasks(btw_agent)
    close_agent_repls(btw_agent)
    _shutdown_agent(btw_agent)
    gate = gate_for(btw_agent) or getattr(btw_agent, "_policy_gate", None)
    unregister = getattr(gate, "unregister_agent", None)
    if callable(unregister):
        try:
            unregister(btw_agent)
        except Exception as exc:  # noqa: BLE001 — best-effort cleanup
            logger.warning("Btw gate unregister failed: %s", exc)


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
    if target == "main":
        _cancel_agent_background_tasks(agent)
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
                refuse_symlink(path, "rich stash", max_ancestors=2)
                path.unlink(missing_ok=True)
            except (OSError, ValueError) as exc:
                logger.warning("Rich stash cleanup failed: %s", exc)
            return
        try:
            atomic_write_text(
                path,
                to_stash_json(
                    {
                        "version": _RICH_STASH_VERSION,
                        "model_id": self.model_id,
                        "length": self.length,
                        "prefix_hash": self.prefix_hash,
                        "messages": self.messages,
                    }
                ),
                mode=0o600,
                dir_mode=0o700,
                refuse_ancestors=2,
                label="rich stash",
            )
        except (OSError, TypeError, ValueError) as exc:
            logger.warning("Rich stash save failed: %s", exc)

    @classmethod
    def load(cls, path: Path | None) -> RichHistory:
        """Load a persisted stash; missing, symlinked, or corrupt files load empty."""
        rich = cls()
        if path is None:
            return rich
        try:
            refuse_symlink(path, "rich stash", max_ancestors=2)
            raw = path.read_text(encoding="utf-8")
        except (OSError, ValueError):
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
    """True when any content block carries reasoningContent or toolUse thought sig."""
    return _has_reasoning(messages)


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


def _should_restore_rich(rich: RichHistory | None, new_id: str, source: list) -> bool:
    """True when stashed provider-native thinking/summary blocks can restore."""
    if (
        rich is None
        or rich.messages is None
        or rich.model_id is None
        or rich.prefix_hash is None
    ):
        return False
    can_restore_provider = supports_reasoning(new_id) or (
        _provider_of(new_id) == "anthropic"
    )
    if not (
        can_restore_provider
        and same_vendor(rich.model_id, new_id)
        and same_provider(rich.model_id, new_id)
    ):
        return False
    return (
        len(source) >= rich.length
        and canonical_prefix_hash(source[: rich.length]) == rich.prefix_hash
    )


def _convert_restore_or_source(
    source: list[dict[str, Any]],
    current_model: str,
    new_id: str,
    rich: RichHistory | None,
) -> tuple[list[dict[str, Any]], bool]:
    """Convert rich prefix (under rich.model_id) and away-model tail separately."""
    if _should_restore_rich(rich, new_id, source):
        assert (
            rich is not None and rich.messages is not None and rich.model_id is not None
        )
        prefix = convert_history(copy.deepcopy(rich.messages), rich.model_id, new_id)
        tail = convert_history(
            copy.deepcopy(source[rich.length :]), current_model, new_id
        )
        return (prefix + tail, True)
    return (convert_history(source, current_model, new_id), False)


def apply_model_action(
    agent: Any,
    new_id: str,
    *,
    turn_running: bool,
    current_model: str,
    rich: RichHistory | None = None,
    effort: str | None = None,
) -> tuple[str | None, str]:
    """Apply a validated /model selection (loop-owned; never the router).

    Idle only: a running turn gets the immediate refusal reply, never a
    queue (D-01 fail-closed). Otherwise restore-then-convert (the rich
    stash when switching back to a same-vendor, same-provider model),
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
        effort: Routed thinking level (None → harness default, the
            manual-/model-switch behavior).

    Returns:
        ``(resolved_id, reply)``; resolved_id is None on refusal.
    """
    if turn_running:
        return (None, MODEL_REFUSAL)
    new_id = normalize_model_ref(new_id)
    # Switch first: resolve raises before any history mutation, so a bad
    # selection leaves the session (model AND messages) untouched.
    _model, resolved_id = apply_switch(agent, new_id, effort=effort)
    source = list(agent.messages)
    converted, restored = _convert_restore_or_source(
        source, current_model, new_id, rich
    )
    fits, _pct, _tokens = estimate_fit(converted, new_id, model=_model)
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
    if rich is not None:
        stash_src = converted if restored else source
        stash_model = new_id if restored else current_model
        if _has_thinking(stash_src):
            rich.messages = copy.deepcopy(stash_src)
            rich.model_id = stash_model
            rich.length = len(stash_src)
            rich.prefix_hash = canonical_prefix_hash(stash_src)
    count = len(agent.messages)
    suffix = ", thinking restored" if restored else ""
    tools_note = (
        f" {UNARY_TOOL_MODE_NOTE.format(model_id=new_id)}"
        if _provider_of(new_id) == "bedrock" and not supports_streaming_tools(new_id)
        else ""
    )
    return (
        resolved_id,
        f"Model: {new_id} — conversation continued ({count} messages {mode_word}{suffix}).{tools_note}",
    )


def _record_routing_event(
    routing_events: list | None,
    *,
    strategy: routing_mod.RoutingStrategy,
    side: bool,
    model: str,
    effort: str,
    model_confidence: float | None,
    effort_confidence: float | None,
    tie_break: bool,
    engine: str,
    decision_engine: str,
    usage: tuple[int, int, float | None],
    held: bool,
) -> None:
    """Append one routing event for a decided ask (None list skips).

    The record carries the 1-based ask number, the side flag, the
    serving (or picked) model plus routed effort and confidences, the
    tie-break marker, the producing (or failed) engine, the
    decision-call token pair plus reported cost, the held marker, and
    the decision model id behind ``decision_engine`` for /cost
    pricing. Held asks record the serving model with empty effort and
    no confidences.
    """
    if routing_events is None:
        return
    routing_events.append(
        {
            "ask": len(routing_events) + 1,
            "side": side,
            "model": model,
            "effort": effort,
            "model_confidence": model_confidence,
            "effort_confidence": effort_confidence,
            "tie_break": tie_break,
            "engine": engine,
            "decision_engine": decision_engine,
            "input_tokens": usage[0],
            "output_tokens": usage[1],
            "decision_cost": usage[2],
            "held": held,
            "decision_model": routing_mod.decision_model_for(strategy, decision_engine),
        }
    )


def _emit_chain_skip_notes(strategy: routing_mod.RoutingStrategy) -> None:
    """Print each listed-but-keyless engine note once per session (D-03).

    The ``skip_notes`` knob alone governs: notes print even under
    ``quiet``. Already-emitted notes stay silent.
    """
    if strategy.engine.skip_notes:
        for note in routing_mod.chain_skip_notes(strategy):
            if note not in _emitted_chain_skip_notes:
                _emitted_chain_skip_notes.add(note)
                print_plain(console, note)


def _decide_routed_pick(
    strategy: routing_mod.RoutingStrategy,
    current_model: str,
    ask_text: str,
    routing: routing_mod.RoutingState | None,
    routing_events: list | None,
) -> tuple[routing_mod.RoutingPick | None, str, tuple[int, int, float | None], str]:
    """Run the routing decision, holding current on any failure (D-08).

    A decide exception or a None pick records a held event and prints
    the hold note; a pause-detail pick also pauses routing for the
    turn. History is untouched on every hold path.

    Returns:
        The ``(pick, engine, usage, detail)`` tuple; ``pick`` is None
        exactly when the ask held.
    """
    try:
        pick, engine, usage, detail = routing_mod.decide(
            strategy, current_model=current_model, side=False, ask=ask_text
        )
    except Exception as exc:  # noqa: BLE001 — pricing/validation failure holds, never kills
        logger.warning("Routing decision failed (%s); holding %s", exc, current_model)
        _record_routing_event(
            routing_events,
            strategy=strategy,
            side=False,
            model=current_model,
            effort="",
            model_confidence=None,
            effort_confidence=None,
            tie_break=False,
            engine="decide",
            decision_engine="decide",
            usage=(0, 0, None),
            held=True,
        )
        print_plain(
            console,
            routing_mod.format_hold_line(current=current_model, detail="decide failed"),
        )
        return None, "decide", (0, 0, None), "decide failed"
    if pick is None:
        if routing is not None and routing_mod.is_pause_detail(detail):
            routing.pause()
        _record_routing_event(
            routing_events,
            strategy=strategy,
            side=False,
            model=current_model,
            effort="",
            model_confidence=None,
            effort_confidence=None,
            tie_break=False,
            engine=engine,
            decision_engine=engine,
            usage=usage,
            held=True,
        )
        print_plain(
            console, routing_mod.format_hold_line(current=current_model, detail=detail)
        )
        return None, engine, usage, detail
    return pick, engine, usage, detail


def _apply_routed_pick(
    agent: Any,
    pick: routing_mod.RoutingPick,
    strategy: routing_mod.RoutingStrategy,
    current_model: str,
    rich: RichHistory | None,
    index: SessionIndex,
    session_id: str,
    stash_path: Path | None,
    engine: str,
    usage: tuple[int, int, float | None],
    routing_events: list | None,
) -> tuple[str, bool]:
    """Validate and apply a cross-model routed pick; holds stay on current.

    A gated pick validates its routed effort, then applies through
    :func:`apply_model_action` with the same persistence as the
    model-action site (FENCE: in memory only, never the global
    default). Any gate or resolve failure holds current with history
    untouched and prints the hold note.

    Returns:
        ``(model_id, applied)`` where ``applied`` is True iff switched.
    """
    try:
        effort_ok = routing_mod.validate_routed_effort(pick, strategy.candidates)
    except Exception as exc:  # noqa: BLE001 — gate failure holds, never kills
        logger.warning("Routed effort gate failed (%s); holding %s", exc, current_model)
        effort_ok = False
    if not effort_ok:
        logger.warning(
            "Routed effort %r unsupported by %s; holding %s",
            pick.effort,
            pick.model,
            current_model,
        )
        _record_routing_event(
            routing_events,
            strategy=strategy,
            side=False,
            model=current_model,
            effort="",
            model_confidence=None,
            effort_confidence=None,
            tie_break=False,
            engine=engine,
            decision_engine=engine,
            usage=usage,
            held=True,
        )
        print_plain(
            console,
            routing_mod.format_hold_line(
                current=current_model,
                detail=f"effort {pick.effort!r} unsupported by {pick.model}",
            ),
        )
        return (current_model, False)
    try:
        resolved_id, _reply = apply_model_action(
            agent,
            pick.model,
            turn_running=False,
            current_model=current_model,
            rich=rich,
            effort=pick.effort,
        )
    except Exception as exc:  # noqa: BLE001 — switch-first: history untouched
        logger.warning("Routed switch failed (%s); holding %s", exc, current_model)
        _record_routing_event(
            routing_events,
            strategy=strategy,
            side=False,
            model=current_model,
            effort="",
            model_confidence=None,
            effort_confidence=None,
            tie_break=False,
            engine="resolve",
            decision_engine=engine,
            usage=usage,
            held=True,
        )
        print_plain(
            console,
            routing_mod.format_hold_line(
                current=current_model, detail="resolve failed"
            ),
        )
        return (current_model, False)
    if resolved_id is not None:
        # FENCE (G-08-1): routed picks apply in memory only and
        # never persist the global default (routing re-decides
        # every ask; only explicit /model choices persist).
        current_model = pick.model
        explicit_save(agent)
        index.ensure(session_id)
        index.set_model(session_id, current_model)
        if rich is not None and stash_path is not None:
            rich.save(stash_path)
        return (current_model, True)
    _record_routing_event(
        routing_events,
        strategy=strategy,
        side=False,
        model=current_model,
        effort="",
        model_confidence=None,
        effort_confidence=None,
        tie_break=False,
        engine="resolve",
        decision_engine=engine,
        usage=usage,
        held=True,
    )
    print_plain(
        console,
        routing_mod.format_hold_line(current=current_model, detail="resolve failed"),
    )
    return (current_model, False)


def _print_routed_note(
    strategy: routing_mod.RoutingStrategy,
    pick: routing_mod.RoutingPick,
    detail: str,
    prev_model: str,
    ask_text: str,
) -> None:
    """Print the one routed-ask transcript line (suppressed under quiet).

    A failed note is logged with the switch standing — it must never
    kill the turn.
    """
    if not strategy.quiet:
        try:
            routed_line = routing_mod.format_routed_line(
                model=pick.model,
                effort=pick.effort,
                model_confidence=pick.model_confidence,
                effort_confidence=pick.effort_confidence,
                tie_break=pick.tie_break,
                truncated=routing_mod.TRUNCATION_MARKER in detail,
                prev_model=prev_model,
                ask=ask_text,
            )
        except Exception as exc:  # noqa: BLE001 — a failed note must not kill the turn
            logger.warning("Routed note failed (%s); switch stands", exc)
        else:
            print_plain(console, routed_line, style="dim")


def _route_pre_turn(
    agent: Any,
    *,
    current_model: str,
    ask_text: str,
    rich: RichHistory | None,
    index: SessionIndex,
    session_id: str,
    stash_path: Path | None,
    routing: routing_mod.RoutingState | None = None,
    routing_events: list | None = None,
) -> str:
    """Pre-turn routing hook: decide, switch, note; returns the model id.

    Runs after dispatch plus the plan prefix and before the retry loop.
    A toggled-off session or an unconfigured one (no strategy, or zero
    candidates) skips silently; a gated pick validates its routed
    effort (levels plus reasoning support) and then applies through
    :func:`apply_model_action` with the same persistence as the
    model-action site, and every routed ask prints one transcript line
    (suppressed when the strategy sets ``quiet``). A same-model pick
    skips the switch (no-op fast path) but still prints the line.
    Every engine, validation, gate, or resolve failure holds current
    with history untouched and prints the hold note with its reason
    detail (D-08, D-16) — hold and failure notes always print, even
    under ``quiet``. A listed-but-keyless engine prints its one-line
    skip note once per session unless the strategy sets ``skip_notes``
    false (D-03) — the knob alone governs, so the note prints even
    under ``quiet``. An all-refused ask pauses routing for the turn
    with the distinct pause note, and later same-turn decisions skip
    with zero POSTs (D-09). Every decided ask, held included, appends
    one routing event for /cost (T-08-08). Effort is per-ask: nothing
    persists, and manual switches keep the default.
    """
    if routing is not None and not routing.is_on():
        return current_model
    try:
        strategy = routing_mod.load_strategy()
    except ValueError as exc:
        logger.warning("Routing disabled for this ask: %s", exc)
        print_plain(console, f"Routing disabled ({exc}).")
        return current_model
    if strategy is None or not strategy.candidates:
        return current_model
    _emit_chain_skip_notes(strategy)
    if routing is not None:
        routing.resume()  # a new ask attempts fresh; pause covers one ask
    pick, engine, usage, detail = _decide_routed_pick(
        strategy, current_model, ask_text, routing, routing_events
    )
    if pick is None:
        return current_model
    prev_model = current_model
    applied = True
    if pick.model != current_model:
        current_model, applied = _apply_routed_pick(
            agent,
            pick,
            strategy,
            current_model,
            rich,
            index,
            session_id,
            stash_path,
            engine,
            usage,
            routing_events,
        )
    if applied:
        _record_routing_event(
            routing_events,
            strategy=strategy,
            side=False,
            model=pick.model,
            effort=pick.effort,
            model_confidence=pick.model_confidence,
            effort_confidence=pick.effort_confidence,
            tie_break=pick.tie_break,
            engine=engine,
            decision_engine=engine,
            usage=usage,
            held=False,
        )
        _print_routed_note(strategy, pick, detail, prev_model, ask_text)
    return current_model


def _review_answer() -> str:
    """One approve/deny/revise answer; anything unclear fails closed to deny."""
    if sys.stdin.isatty():
        from strands_code_cli.ui.choice import radio_choice

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
    _prompt_inline("approve / deny / revise [deny]: ")
    typed = input().strip().lower()
    if typed in ("approve", "a", "y", "yes"):
        return "approve"
    if typed in ("revise", "r"):
        return "revise"
    return "deny"  # empty and unknown fail closed


def _review_silent(queue: CurateQueue, pending: list[Any], apply_fn: Any) -> list[str]:
    """Auto-apply promoted proposals in silent mode; keep init-* pending."""
    lines: list[str] = []
    for proposal in pending:
        if proposal.source != "promoted":
            continue
        queue.approve(proposal.id, apply_fn)
        lines.append(silent_note(proposal.section, proposal.source))
    return lines


def review_memory_queue(
    queue: CurateQueue,
    mode_state: MemoryModeState,
    apply_fn: Any,
    on_revise: Any = None,
) -> list[str]:
    """Turn-boundary curate review; returns transcript lines to print.

    Silent mode auto-applies ``"promoted"`` proposals with one
    :func:`silent_note` line each (leaving ``init-*`` drafts pending for
    explicit ``/memory`` review). Curate mode prompts per proposal
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
        return _review_silent(queue, pending, apply_fn)
    for proposal in pending:
        try:
            with output_context():
                for body_line in proposal.body.splitlines() or [""]:
                    print_plain(console, f"> {sanitize_line(body_line, max_len=1000)}")
                print_plain(
                    console,
                    f"Source: {sanitize_display(proposal.source)} → section {sanitize_display(proposal.section)}",
                )
                answer = _review_answer()
                instruction = ""
                if answer == "revise":
                    _prompt_inline("Describe the change in words: ")
                    instruction = input().strip()
        except KeyboardInterrupt:
            break
        except EOFError:
            break  # Ctrl-D fails closed: proposals stay pending
        if answer == "approve":
            lines.append(queue.approve(proposal.id, apply_fn))
        elif answer == "revise":
            if on_revise is None:
                lines.append(
                    f"Revise for {sanitize_display(proposal.id)} noted — proposal kept pending."
                )
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
        from strands_code_cli.ui.choice import radio_choice

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
    _prompt_inline("accept / revert / iterate [revert]: ")
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
    safe_section = sanitize_display(section)
    block, summary = _first_fence(result_text)
    if block is None:
        revise_state.disarm()
        return (
            f"No fenced block found — revision discarded, '{safe_section}' unchanged."
        )
    try:
        with output_context():
            for line in block.splitlines() or [""]:
                print_plain(console, f"> {sanitize_line(line, max_len=1000)}")
            if summary:
                print_plain(
                    console, f"Summary: {sanitize_display(summary, max_len=1000)}"
                )
            answer = _revise_answer()
            instruction = ""
            if answer == "iterate":
                _prompt_inline("Describe the change in words: ")
                instruction = input().strip()
    except KeyboardInterrupt:
        revise_state.disarm()
        raise
    except EOFError:
        revise_state.disarm()
        return f"Reverted — '{safe_section}' unchanged."
    if answer == "accept":
        apply_fn(section, block)
        revise_state.disarm()
        return f"Memory section '{safe_section}' updated."
    if answer == "iterate" and instruction:
        revise_state.arm(section, revise_state.previous_text, instruction)
        return None
    # Revert — plus empty-instruction iterate, which fails closed
    # instead of re-arming with a broken prompt.
    revise_state.disarm()
    return f"Reverted — '{safe_section}' unchanged."


def _drain_revise_rounds(
    agent: Any,
    result: Any,
    revise_state: ReviseState,
    cancel_event: threading.Event,
    session_turns: list,
    current_model: str,
    mode: ModeState,
    apply_fn: Any = None,
    turn_interface: str = "tool",
    turn_interfaces: list | None = None,
) -> None:
    """Consume armed revise rounds, re-invoking while the user iterates.

    Prints each round's reply. Follow-up iterate turns reuse the
    normal invocation path (plan prefix, metrics); a failed
    follow-up disarms with a note. Ctrl-C propagates after consume
    disarms, so the interrupt lands on the cancel path with clean
    state. Rounds record under the owning turn's interface (D-15).
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
            if worker_cancelled(exc):
                raise KeyboardInterrupt from None
            print_plain(
                console, f"Turn failed ({type(exc).__name__}): {exc}", style="red"
            )
            print_plain(console, "Revise round dropped — the turn failed.")
            revise_state.disarm()
            break
        usage = record_turn_metrics(
            follow_result,
            current_model,
            session_turns,
            model=getattr(agent, "model", None),
        )
        if turn_interfaces is not None:
            turn_interfaces.append(turn_interface)
        if usage is not None:
            print_plain(console, usage, style="dim")
        print_plain(console, codeact_label(turn_interface), style="dim")
        text = _result_text(agent, follow_result)


_INIT_FENCE_RE = re.compile(
    r"```proposed:(?P<label>[^\n]*)\n(?P<body>.*?)```", re.DOTALL
)
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
        queued_sections.add(label)
        if queue.propose(label, f"init-{depth}", body) is not None:
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


_INPUT_LINE = "line"
"""Turn-input kind: a submitted line to dispatch."""

_INPUT_SKIP = "skip"
"""Turn-input kind: empty input, re-prompt."""

_INPUT_EXIT = "exit"
"""Turn-input kind: Ctrl-D, exit the loop."""


def _reload_changed_memory(memory_snapshot: MemorySnapshot) -> MemorySnapshot:
    """Reload changed memory files with one transcript note each.

    Returns:
        The (possibly reloaded) memory snapshot.
    """
    changed = sweep_memory_files(memory_snapshot)
    if changed:
        memory_snapshot = load_memory()
        for changed_path in changed:
            print_plain(console, MEMORY_RELOAD_NOTE.format(filename=changed_path))
    return memory_snapshot


def _print_review_lines(review_lines: list[str]) -> None:
    """Print one turn-boundary curate review transcript line each."""
    for review_line in review_lines:
        print_plain(console, review_line)


def _read_turn_input(
    session: PromptSession,
    broker: Any,
    btw: BtwContext,
    boundary_template: str | None,
    *,
    initial_buf: str = "",
) -> tuple[str, str]:
    """Read one turn input: armed revise template or the idle prompt.

    An armed boundary revise runs without prompting. Ctrl-C cancels
    the line, Ctrl-D exits, empty input submits nothing.

    Returns:
        ``(kind, text)`` where kind is ``_INPUT_LINE`` with the
        submitted text, ``_INPUT_SKIP`` with ``""`` to re-prompt, or
        ``_INPUT_EXIT`` with ``""`` to exit.
    """
    try:
        if boundary_template is not None:
            text = boundary_template
        else:
            # An outliving side streams through the idle proxy
            # above the prompt line instead of tearing it (D-11
            # idle delivery rides the documented patch_stdout
            # shape; turn dialogs already nest this way).
            with output_context():
                text = _idle_prompt_multiplexed(
                    session, broker, btw, initial_buf=initial_buf
                )
    except KeyboardInterrupt:
        return _INPUT_SKIP, ""
    except EOFError:
        return _INPUT_EXIT, ""
    if not text.strip():
        return _INPUT_SKIP, ""
    return _INPUT_LINE, text


def _dispatch_turn_input(
    agent: Any,
    text: str,
    boundary_template: str | None,
    revise_state: ReviseState,
    session_id: str,
    index: SessionIndex,
    mode: ModeState,
    current_model: str,
    session_turns: list,
    skills: Any,
    harness_skills_refresh: Callable[[], str | None],
    memory_mode: MemoryModeState,
    curate_queue: CurateQueue,
    init_state: InitState,
    routing: routing_mod.RoutingState | None,
    routing_events: list | None,
    interface: CodeactState,
    stint: CodeactStint,
    diff_mode: DiffModeState | None = None,
) -> tuple[str, str | None, str]:
    """Dispatch one turn input through the router.

    Armed boundary revises bypass dispatch as agent turns. A
    ``/codeact`` flip stays session-sticky in memory and resets the
    stint (D-17).

    Returns:
        The ``(action, message, text)`` triple; ``text`` is rewritten
        to the revise command on the boundary path.
    """
    if boundary_template is not None:
        action, message = "agent", boundary_template
        text = f"/memory revise {revise_state.section} {revise_state.instruction}"
    else:
        codeact_before = interface.interface
        action, message = dispatch(
            text,
            session_id=session_id,
            index=index,
            mode=mode,
            current_model=current_model,
            agent=agent,
            session_turns=session_turns,
            skills=skills,
            harness_skills_refresh=harness_skills_refresh,
            memory_mode=memory_mode,
            curate=curate_queue,
            revise=revise_state,
            init=init_state,
            routing=routing,
            routing_events=routing_events,
            interface=interface,
            diff_mode=diff_mode,
        )
        if action == "reply" and interface.interface != codeact_before:
            # D-17: each CodeAct stint starts fresh on every switch.
            stint.reset()
    return action, message, text


def _emit_skill_match_note(skills: Any, action: str, text: str) -> None:
    """Echo the accept line when a typed slash head matched a skill (D-13)."""
    if action == "agent":
        match_note = skill_match_note(skills, text)
        if match_note is not None:
            print_plain(console, match_note)


def _handle_reply_action(
    agent: Any,
    message: str | None,
    mode: ModeState,
    text: str,
    session_id: str,
    index: SessionIndex,
    rich: RichHistory,
    stash_path: Path | None,
) -> None:
    """Serve one router reply: print, re-sync the gate, flush on mutation.

    ``/compact`` and ``/clear`` mutate history, so the session
    flushes immediately and the rich stash resets.
    """
    if message:
        print_plain(console, message)
    _set_gate_mode(agent, mode.mode)  # /mode or /approve may have flipped
    head = text.strip().partition(" ")[0].lower()
    if head in ("/compact", "/clear"):
        explicit_save(agent)  # history mutated: flush immediately
        flush_memory(agent)
        index.ensure(session_id)
        rich.reset()
        rich.save(stash_path)  # empty stash removes the sidecar


def _install_turn_sigint_handler(
    cancel_event: threading.Event, both_running: threading.Event | None
) -> Any:
    """Install the turn SIGINT handler on the main thread.

    Returns:
        The previous SIGINT disposition, or None off the main thread.
    """
    if threading.current_thread() is threading.main_thread():
        prev_sigint = signal.getsignal(signal.SIGINT)
        signal.signal(
            signal.SIGINT,
            _make_turn_sigint_handler(
                cancel_event, prev_sigint, both_running=both_running
            ),
        )
        return prev_sigint
    return None


def _compose_agent_text(message: str | None, text: str, mode: ModeState) -> str:
    """Coalesce the composed message over raw text; plan mode prefixes read-only."""
    agent_text = message if message is not None else text
    if mode.mode == "plan":
        agent_text = f"{PLAN_PREFIX}\n\n{agent_text}"
    return agent_text


def _announce_turn_usage(
    btw: BtwContext,
    result: Any,
    current_model: str,
    session_turns: list,
    agent: Any,
    turn_interface: str,
    turn_interfaces: list,
) -> None:
    """Melt side-channel and main spend into the session total (D-15).

    Each completed btw turn records through the shared row shape —
    no btw-specific field, tag, or report branch. Consumed so an
    empty-retry never re-records.
    """
    for _, _, btw_result, btw_reported, side_model_id in btw.pending:
        btw_usage = record_turn_metrics(
            btw_result,
            side_model_id or current_model,
            session_turns,
            reported_cost=btw_reported,
        )
        if btw_usage is not None:
            print_plain(console, btw_usage, style="dim")
    btw.pending.clear()
    usage = record_turn_metrics(
        result,
        current_model,
        session_turns,
        model=getattr(agent, "model", None),
    )
    turn_interfaces.append(turn_interface)
    if usage is not None:
        print_plain(console, usage, style="dim")
    print_plain(console, codeact_label(turn_interface), style="dim")


def _run_turn_attempts(
    agent: Any,
    agent_text: Any,
    turn_id: str,
    cancel_event: threading.Event,
    btw: BtwContext,
    both_running: threading.Event | None,
    side_pool: ThreadPoolExecutor,
    current_model: str,
    session_turns: list,
    turn_interface: str,
    turn_interfaces: list,
) -> tuple[Any, bool, int, int]:
    """Run one turn's invoke attempts with a single empty-output retry.

    Provider/model errors fail the turn (reported, re-prompt) but
    never the session — errors never retry, only empty success.
    Cancels propagate to the turn handler.

    Returns:
        ``(result, failed, attempts, before)``: the agent result
        (None when the turn failed), whether the turn failed, the
        attempt count, and the pre-turn history length backing the
        persistent-empty note.
    """
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
            if worker_cancelled(exc):
                raise KeyboardInterrupt from None
            # Provider/model errors (validation, throttling, ...)
            # must fail the turn, never the session: report and
            # re-prompt. Errors never retry — only empty success.
            print_plain(
                console,
                f"Turn failed ({type(exc).__name__}): {exc}",
                style="red",
            )
            if "tool use in streaming mode" in str(exc):
                print_plain(
                    console,
                    "This model needs non-streaming tool use — "
                    "/model to switch to a supported model.",
                    style="red",
                )
            failed = True
            break
        _announce_turn_usage(
            btw,
            result,
            current_model,
            session_turns,
            agent,
            turn_interface,
            turn_interfaces,
        )
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
    return result, failed, attempts, before


def _drop_armed_on_failure(revise_state: ReviseState, init_state: InitState) -> None:
    """Drop armed revise/init rounds when the turn failed (fresh arm next turn)."""
    if revise_state.armed:
        revise_state.disarm()
        print_plain(console, "Revise round dropped — the turn failed.")
    if init_state.armed:
        init_state.disarm()
        print_plain(console, "Init draft dropped — the turn failed.")


def _consume_followup_rounds(
    agent: Any,
    result: Any,
    revise_state: ReviseState,
    init_state: InitState,
    curate_queue: CurateQueue,
    cancel_event: threading.Event,
    session_turns: list,
    current_model: str,
    mode: ModeState,
    turn_interface: str,
    turn_interfaces: list,
) -> None:
    """Drain armed revise/init follow-up rounds after a successful turn.

    The revise drain keeps issue rounds until clean, exhausted, or
    cancelled; the init consume prints the draft review.
    """
    if revise_state.armed:
        _drain_revise_rounds(
            agent,
            result,
            revise_state,
            cancel_event,
            session_turns,
            current_model,
            mode,
            turn_interface=turn_interface,
            turn_interfaces=turn_interfaces,
        )
    if init_state.armed:
        init_reply = consume_init_turn(
            _result_text(agent, result), init_state, curate_queue
        )
        print_plain(console, init_reply)


def _finish_successful_turn(
    agent: Any,
    current_model: str,
    index: SessionIndex,
    session_id: str,
    before: int,
    attempts: int,
) -> None:
    """Close a successful turn: persistent-empty note, auto-compact, save."""
    history = getattr(agent, "messages", None)
    if (
        attempts == 2
        and isinstance(history, list)
        and _turn_appended_empty(before, history)
    ):
        print_plain(
            console,
            "No response content — the model returned empty twice.",
            style="dim",
        )
    announcement = maybe_auto_compact(agent, current_model)
    if announcement is not None:
        print_plain(console, announcement)
        explicit_save(agent)
        index.ensure(session_id)


def _print_skill_warnings(skills: Any) -> None:
    """Print skill-index load warnings (bad manifests stay visible)."""
    for warning in skills.warnings:
        print_plain(console, warning, style="yellow")


def _init_routing_state() -> routing_mod.RoutingState:
    """Boot the session routing toggle: on when a strategy configures, else off.

    Boot once, decide per ask: each ask re-reads the strategy file
    for pause/quiet/candidates while the paused flag rides the session.
    """
    try:
        boot_strategy = routing_mod.load_strategy()
    except ValueError as exc:
        logger.warning("Routing disabled: %s", exc)
        print_plain(console, f"Routing disabled ({exc}).")
        boot_strategy = None
    return routing_mod.RoutingState(
        initial=(
            "on" if boot_strategy is not None and boot_strategy.candidates else "off"
        )
    )


def _load_initial_toggles(
    codeact: str | None, agent: Any
) -> tuple[CodeactState, DiffModeState, MemoryModeState]:
    """Load session-sticky codeact, diff, and memory modes once from ProviderConfig."""
    try:
        saved = ProviderConfig.load()
    except ValueError:
        logger.warning("Ignoring tampered provider config; using toggle defaults.")
        saved = ProviderConfig()
    interface = CodeactState(initial=resolve_initial_interface(codeact, saved.codeact))
    existing_diff = getattr(agent, "_diff_mode", None)
    if isinstance(existing_diff, DiffModeState):
        diff_mode = existing_diff
    else:
        diff_mode = DiffModeState(initial=saved.diff_mode or DEFAULT_DIFF_MODE)
    memory_mode = MemoryModeState(initial=saved.memory_mode or "curate")
    return interface, diff_mode, memory_mode


def _warn_if_no_streaming_tools(current_model: str) -> None:
    """Print a concise note when the opening model uses Bedrock unary tool mode."""
    normalized = normalize_model_ref(current_model)
    if _provider_of(normalized) == "bedrock" and not supports_streaming_tools(
        normalized
    ):
        print_plain(
            console,
            UNARY_TOOL_MODE_NOTE.format(model_id=current_model),
            style="dim",
        )


def _enter_session_pump(broker: Any, session_cancel: threading.Event) -> Any:
    """Enter the session broker pump across idle gaps (None without a broker).

    Entered and exited manually around the loop; the only exits are
    the loop breaks plus a crashing exception (whose process death
    moots the broker flag anyway).
    """
    session_pump = broker.pump(session_cancel) if broker is not None else None
    if session_pump is not None:
        session_pump.__enter__()
    return session_pump


def _handle_turn_cancel_path(
    agent: Any,
    session_id: str,
    index: SessionIndex,
    cancel_event: threading.Event,
    btw: BtwContext,
    cancel_armed_at: float | None,
    revise_state: ReviseState,
    init_state: InitState,
) -> float | None:
    """Run the per-target cancel UX after a turn interrupt (D-08).

    Armed revise/init rounds drop with memory unchanged. The pump
    records the named targets on the turn context; each gets its
    own two-press line against its own event, all judged against
    the same arm snapshot so a first-press "both" reads first-press
    for both. No record means the legacy single-worker path.

    Returns:
        The rearmed cancel timestamp for the two-press window.
    """
    if revise_state.armed:
        revise_state.disarm()
        print_plain(console, "Revise round dropped — interrupted, memory unchanged.")
    if init_state.armed:
        init_state.disarm()
        print_plain(console, "Init draft dropped — interrupted, memory unchanged.")
    targets = getattr(btw, "cancel_targets", None) or ("main",)
    armed_snapshot = cancel_armed_at
    for target in targets:
        event = btw.cancel_event if target == "btw" else cancel_event
        cancel_armed_at = _handle_turn_cancel(
            agent, session_id, index, event, armed_snapshot, target=target
        )
    return cancel_armed_at


def _restore_turn_handlers(prev_sigint: Any, reader: Any, slot: Any) -> None:
    """Restore the pre-turn SIGINT disposition, stop the reader, clear the slot."""
    if prev_sigint is not None:
        signal.signal(signal.SIGINT, prev_sigint)
    if reader is not None:
        reader.stop()
    slot.state = None


def _finish_turn(
    mode: ModeState,
    cancelled: bool,
    titled: bool,
    agent: Any,
    session_id: str,
    index: SessionIndex,
    text: str,
    *,
    note_plan: bool = True,
) -> bool:
    """Close the turn: note plan proposals, auto-title once per session.

    Returns:
        The updated titled flag.
    """
    if note_plan and not cancelled and mode.mode == "plan":
        mode.note_plan_proposed()
    if not titled:
        titled = True
        _maybe_auto_title(agent, session_id, index, text)
    return titled


def _execute_turn_cycle(
    agent: Any,
    *,
    action: str,
    message: Any,
    text: str,
    session_id: str,
    index: SessionIndex,
    mode: ModeState,
    current_model: str,
    session_turns: list,
    revise_state: ReviseState,
    init_state: InitState,
    curate_queue: CurateQueue,
    rich: RichHistory,
    stash_path: Path | None,
    routing: routing_mod.RoutingState | None,
    routing_events: list,
    interface: CodeactState,
    stint: CodeactStint,
    default_repl: Any,
    turn_interfaces: list,
    slot: Any,
    btw_session: BtwContext,
    side_pool: ThreadPoolExecutor,
    cancel_armed_at: float | None,
    titled: bool,
) -> tuple[str, float | None, bool]:
    """Execute one non-command agent turn with routing, attachments, and cleanup."""
    steering = SteeringState()
    turn_id = f"{session_id}:{uuid.uuid4().hex}"
    cancel_event = threading.Event()
    both_running = threading.Event()
    reader = None
    cancelled = False
    note_plan = True
    swapped = False
    prev_sigint = _install_turn_sigint_handler(cancel_event, both_running)
    try:
        with output_context():
            _bind_gate_turn(agent, turn_id)
            steering.bind_turn(turn_id)
            slot.state = steering
            _set_gate_mode(agent, mode.mode)
            reader = start_steering_reader(
                steering, gate_open, on_btw=btw_session.submit
            )
            agent_text = _compose_agent_text(message, text, mode)
            turn_interface = resolve_turn_interface(interface.resolve_turn())
            agent_text = shape_turn_text(turn_interface, agent_text)
            swapped = swap_for_code_turn(
                agent,
                turn_interface,
                stint.tool if turn_interface == "code" else None,
                default_repl,
            )
            current_model = _route_pre_turn(
                agent,
                current_model=current_model,
                ask_text=text,
                rich=rich,
                index=index,
                session_id=session_id,
                stash_path=stash_path,
                routing=routing,
                routing_events=routing_events,
            )
            turn_prompt, attach_err = prepare_turn_prompt(
                text,
                agent_text,
                current_model=current_model,
                scan_attachments=True,
            )
            if attach_err is not None or turn_prompt is None:
                print_plain(
                    console,
                    attach_err or "Attachment resolution cancelled the turn.",
                )
                note_plan = False
                return current_model, cancel_armed_at, titled
            result, failed, attempts, before = _run_turn_attempts(
                agent,
                turn_prompt,
                turn_id,
                cancel_event,
                btw_session,
                both_running,
                side_pool,
                current_model,
                session_turns,
                turn_interface,
                turn_interfaces,
            )
            if failed:
                _drop_armed_on_failure(revise_state, init_state)
                return current_model, cancel_armed_at, titled
            _consume_followup_rounds(
                agent,
                result,
                revise_state,
                init_state,
                curate_queue,
                cancel_event,
                session_turns,
                current_model,
                mode,
                turn_interface,
                turn_interfaces,
            )
            _finish_successful_turn(
                agent, current_model, index, session_id, before, attempts
            )
    except KeyboardInterrupt:
        cancelled = True
        cancel_armed_at = _handle_turn_cancel_path(
            agent,
            session_id,
            index,
            cancel_event,
            btw_session,
            cancel_armed_at,
            revise_state,
            init_state,
        )
    finally:
        restore_after_turn(agent, swapped, default_repl)
        _restore_turn_handlers(prev_sigint, reader, slot)
    titled = _finish_turn(
        mode, cancelled, titled, agent, session_id, index, text, note_plan=note_plan
    )
    return current_model, cancel_armed_at, titled


def _close_loop_session(
    agent: Any,
    btw: BtwContext,
    broker: Any,
    current_model: str,
    session_turns: list,
    side_pool: ThreadPoolExecutor,
    session_pump: Any,
    index: SessionIndex,
    session_id: str,
    stint: Any = None,
) -> None:
    """Drain side work and persist the session at loop exit.

    A side run completed just before exit still lands (history plus
    metrics); a still-running one is named and gets a graceful stop —
    the session is over, so D-11's never-cut rule yields to a clean
    exit — and the pool join waits for the abort, never for full work.
    """
    from strands_code_cli.sandbox.monty import close_agent_repls

    _drain_idle_btw(agent, btw, broker, current_model, session_turns, from_exit=True)
    _note_dropped_side(btw, broker)
    live_btw_agent = btw.live_agent if btw.has_live else None
    if btw.has_live:
        btw.cancel_event.set()
        _cancel_agent_background_tasks(live_btw_agent)
    interrupted = False
    try:
        try:
            side_pool.shutdown(wait=True)
        except KeyboardInterrupt:
            interrupted = True
            side_pool.shutdown(wait=False)
            raise
    finally:
        unregister_btw_cancel(broker)
        if session_pump is not None:
            session_pump.__exit__(None, None, None)
        _cancel_agent_background_tasks(agent)
        explicit_save(agent)
        flush_memory(agent)
        close_agent_repls(agent)
        if stint is not None:
            stint.close()
        _shutdown_agent(agent)
        if live_btw_agent is not None:
            _teardown_btw_agent(live_btw_agent)
            btw.detach_live()
        index.ensure(session_id)
        if not interrupted:
            print_plain(console, "Session saved.", style="dim")


def _clear_agent_base_url_on_provider_change(agent: Any, new_model: str) -> None:
    """Drop in-memory custom base_url/api_mode when switching to another provider."""
    from strands_code_cli.model.provider_id import provider_of

    owner = getattr(agent, "_base_url_provider", None)
    if (
        not owner
        or provider_of(normalize_model_ref(new_model), unwrap_litellm=True) == owner
    ):
        return
    agent._base_url = None
    agent._base_url_provider = None
    if hasattr(agent, "_api_mode"):
        agent._api_mode = None
    kwargs = getattr(agent, "_harness_kwargs", None)
    if isinstance(kwargs, dict):
        kwargs.pop("_base_url", None)
        kwargs.pop("_base_url_provider", None)
        kwargs.pop("_api_mode", None)


def run_loop(
    agent: Any,
    *,
    session_id: str,
    index: SessionIndex,
    model_id: str | None = None,
    codeact: str | None = None,
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

    Phase 8: the loop owns the session-sticky :class:`RoutingState`
    (``/route`` toggle, defaulting to on when a strategy configures)
    and runs the pre-turn routing hook at idle; a confirmed manual
    ``/model`` switch disables routing with a transcript note.

    Phase 11: the loop owns the session-sticky :class:`CodeactState`
    (``/codeact`` toggle, starting on tool-calling unless the
    ``--codeact`` flag or remember-last config says otherwise);
    ``/codeact`` switches persist as the last choice.
    """
    from strands_harness.defaults import DEFAULT_MODEL

    from strands_code_cli.memory.skills import BUILTIN_SLASH_HEADS, SkillIndex
    from strands_code_cli.ui.completer import build_completer

    print_plain(console, f"Session {session_id} — Ctrl-D to exit.", style="dim")
    skills = SkillIndex()
    _print_skill_warnings(skills)
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

    def _refresh_harness_skills() -> str | None:
        """Rescan the harness skills registry (no-op without the plugin).

        Reads the handle ``build_agent`` stashed; test doubles without
        one simply skip the refresh. Defers while a side run is live:
        the side agent shares this plugin object, so a mid-turn rescan
        would mutate the registry concurrently with its use.

        Returns:
            A deferral note for the reload reply, or None when the
            refresh ran (or there was no plugin to refresh).
        """
        plugin = getattr(agent, "_skills_plugin", None)
        if plugin is None:
            return None
        if btw_session.has_live:
            return "model registry refresh deferred — side answer running"
        plugin.set_available_skills(skills.discover_plugin_sources())
        return None

    def _workspace_files() -> list[str]:
        return discover_workspace_files()

    session: PromptSession = PromptSession(
        history=_history(), completer=build_completer(_skill_words, _workspace_files)
    )
    mode = ModeState()
    interface, diff_mode, memory_mode = _load_initial_toggles(codeact, agent)
    # Loop-owned CodeAct stint (D-10/D-11): REPL state persists across
    # code turns within the stint and resets on every interface switch
    # (D-17) at the post-dispatch hook below. Built lazily on first use.
    stint = CodeactStint(cwd=os.getcwd())
    # Always-on tool-turn python_repl, captured once at startup: code
    # turns swap the stint tool in at send and restore this at the
    # boundary (None when absent — code turns stay prefix-shaped).
    default_repl = default_repl_handle(agent)
    routing = _init_routing_state()
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

    current_model = model_id or ProviderConfig.load().model or DEFAULT_MODEL
    _warn_if_no_streaming_tools(current_model)
    session_turns: list = []
    # Per-turn interface record (D-15) parallel to session_turns —
    # the cost rows keep their shape (D-16), so the interface lives
    # here, never as a rendered column.
    turn_interfaces: list = []
    routing_events: list = []
    stash_path = rich_stash_path(index.root, session_id)
    rich = RichHistory.load(stash_path)
    prepare_resumed_history(
        agent,
        current_model,
        rich,
        stash_path,
        prior_model=index.model_of(session_id),
    )
    index.set_model(session_id, current_model)
    slot = _steering_slot_for(agent)
    _set_gate_mode(agent, mode.mode)
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
    broker = broker_for(agent)
    session_cancel = threading.Event()
    session_pump = _enter_session_pump(broker, session_cancel)
    btw_session = _btw_context_for(
        agent, routing=routing, routing_events=routing_events
    )
    side_pool = ThreadPoolExecutor(max_workers=1)
    next_prefill = ""
    while True:
        boundary_revise["template"] = None
        memory_snapshot = _reload_changed_memory(memory_snapshot)
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
        _print_review_lines(review_lines)
        boundary_template = boundary_revise["template"]
        kind, text = _read_turn_input(
            session, broker, btw_session, boundary_template, initial_buf=next_prefill
        )
        next_prefill = ""
        if kind == _INPUT_SKIP:
            continue  # empty input submits nothing; re-prompt
        if kind == _INPUT_EXIT:
            break  # Ctrl-D exits
        _drain_idle_btw(agent, btw_session, broker, current_model, session_turns)
        action, message, text = _dispatch_turn_input(
            agent,
            text,
            boundary_template,
            revise_state,
            session_id,
            index,
            mode,
            current_model,
            session_turns,
            skills,
            _refresh_harness_skills,
            memory_mode,
            curate_queue,
            init_state,
            routing,
            routing_events,
            interface,
            stint,
            diff_mode=diff_mode,
        )
        _emit_skill_match_note(skills, action, text)
        if action == "exit":
            break
        if action == "prefill":
            next_prefill = message or ""
            continue
        if action == "reply":
            _handle_reply_action(
                agent, message, mode, text, session_id, index, rich, stash_path
            )
            continue
        if action == "model" and message is not None:
            try:
                resolved_id, reply = apply_model_action(
                    agent,
                    message,
                    turn_running=False,
                    current_model=current_model,
                    rich=rich,
                )
            except Exception as exc:  # noqa: BLE001 — a failed switch must not kill the session
                print_plain(console, f"Model switch failed ({exc}); session unchanged.")
                continue
            print_plain(console, reply)
            if resolved_id is not None:
                current_model = message  # verbatim selection string persists
                _clear_agent_base_url_on_provider_change(agent, message)
                try:
                    ProviderConfig.load().save_model_choice(message)
                except ValueError as exc:
                    logger.warning("Model choice not persisted: %s", exc)
                explicit_save(agent)
                index.ensure(session_id)
                index.set_model(session_id, current_model)
                rich.save(stash_path)
                if routing_mod.warn_applies(routing):
                    # Warn-path apply: manual override wins, routing off.
                    routing.set("off")
                    print_plain(console, routing_mod.ROUTING_MANUAL_OFF_NOTE)
            continue
        current_model, cancel_armed_at, titled = _execute_turn_cycle(
            agent,
            action=action,
            message=message,
            text=text,
            session_id=session_id,
            index=index,
            mode=mode,
            current_model=current_model,
            session_turns=session_turns,
            revise_state=revise_state,
            init_state=init_state,
            curate_queue=curate_queue,
            rich=rich,
            stash_path=stash_path,
            routing=routing,
            routing_events=routing_events,
            interface=interface,
            stint=stint,
            default_repl=default_repl,
            turn_interfaces=turn_interfaces,
            slot=slot,
            btw_session=btw_session,
            side_pool=side_pool,
            cancel_armed_at=cancel_armed_at,
            titled=titled,
        )
    _close_loop_session(
        agent,
        btw_session,
        broker,
        current_model,
        session_turns,
        side_pool,
        session_pump,
        index,
        session_id,
        stint=stint,
    )
