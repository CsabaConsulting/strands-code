"""Boundary steering for mid-task redirect (LOOP-02, D-09..D-12).

Machinery: a turn-owned reader thread (select+read on the stdin fd,
temporarily nonblocking so the turn-end join is prompt) captures
anything typed while a turn runs (D-12) into an explicit per-turn
:class:`SteeringState`; a ``BeforeToolCallEvent`` hook registered at
``HookOrder.SDK_FIRST`` (runs before the HITL intervention dispatcher at
``INTERVENTION_INPUT``) cancels the *next* tool call with a redirect
message. The in-flight call always finishes first (D-10) — there is no
mid-call preemption primitive, so finish-then-redirect is structural,
not a UX choice. The turn continues toward the revised goal (D-11);
the hook never calls ``agent()`` re-entrantly (``ConcurrencyException``
otherwise).

Ordering fallback (proven by tracer against the SDK): the intervention
dispatcher does not check ``cancel_tool`` before running the HITL
handler, so a steered call would still hit the approval prompt. The
hook therefore arms the consumed ``toolUseId`` on the state, and
``PolicyClassifier`` treats an armed boundary as skip-prompt (returns
allow) while the executor still cancels the call with the redirect
message. Steering-cancelled calls are never approval-prompted.

Gate-open coordination: while the gate ``ask`` prompt is open the
reader does not consume stdin, so buffered keystrokes stay available
for the prompt and are picked up as steering only after it closes —
a steering line is never consumed as a y/n answer and vice versa.

Streaming limit (named, not fixed): stretches of model output with no
tool call have no boundary, so steering waits for the next step.

Echo note: captured lines are printed directly (no nested
``output_context`` — swapping the global ``sys.stdout`` proxy from a
second thread would corrupt the turn's active proxy on restore). The
turn holds ``output_context`` open while the reader runs, so the echo
still lands in the transcript.

``SteeringState`` is an explicit object threaded through ``run_loop``
(never a module-level registry); ``SteeringSlot`` is the
session-scoped holder the registered hook closes over while each turn
swaps in a fresh state.
"""

from __future__ import annotations

import os
import select
import sys
import threading
from typing import Any, Callable

STEERING_NOTED = "Steering noted — applies at the next step."
STREAMING_LIMIT = (
    "Steering applies at the next tool-call boundary; "
    "long stretches with no tool call delay redirect until the next step."
)

STEERING_REDIRECT_TEMPLATE = (
    "Steering redirected by user: {text} — continue toward the revised "
    "goal from the next step; the skipped call was not executed."
)


class SteeringState:
    """Per-turn steering mailbox plus one-shot boundary arms.

    Mirrors the ``BatchState``/``bind_turn`` pattern: reset every turn,
    never shared across turns. Thread-safe: the reader thread writes
    via :meth:`note`, the hook thread reads via :meth:`take`.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: str | None = None
        self._armed: set[str] = set()
        self._turn: str | None = None

    def bind_turn(self, turn_id: str) -> None:
        """Start a new turn: drop pending text and stale arms."""
        with self._lock:
            self._turn = turn_id
            self._pending = None
            self._armed = set()

    def note(self, text: str) -> bool:
        """Record typed steering; blank lines are ignored.

        Returns:
            True when the text armed pending steering.
        """
        cleaned = text.strip()
        if not cleaned:
            return False
        with self._lock:
            self._pending = cleaned
        return True

    def take(self) -> str | None:
        """Pop pending steering (hook consumption, one-shot)."""
        with self._lock:
            text = self._pending
            self._pending = None
        return text

    def has_pending(self) -> bool:
        """True when un-consumed steering text is waiting."""
        with self._lock:
            return self._pending is not None

    def arm(self, tool_use_id: str) -> None:
        """Mark a boundary as steering-redirected (skip-prompt key)."""
        with self._lock:
            self._armed.add(tool_use_id)

    def consume_arm(self, tool_use_id: str) -> bool:
        """One-shot check: True once per armed boundary, then forgotten."""
        with self._lock:
            if tool_use_id in self._armed:
                self._armed.discard(tool_use_id)
                return True
            return False


class SteeringSlot:
    """Session-scoped holder the registered hook closes over.

    ``run_loop`` swaps :attr:`state` every turn; the hook and the
    classifier always see the current turn's state through this slot.
    """

    def __init__(self) -> None:
        self.state: SteeringState | None = None

    def take(self) -> str | None:
        """Pop pending steering from the current turn's state."""
        state = self.state
        return state.take() if state is not None else None

    def consume_arm(self, tool_use_id: str) -> bool:
        """One-shot armed-boundary check against the current state."""
        state = self.state
        return state.consume_arm(tool_use_id) if state is not None else False


def make_steering_hook(source: SteeringState | SteeringSlot) -> Callable[[Any], None]:
    """Build the boundary hook: pending text becomes ``cancel_tool``.

    Never invokes the agent — it only writes the event field, so no
    re-entrancy (``ConcurrencyException``) is possible on this path.
    """

    def _hook(event: Any) -> None:
        text = source.take()
        if not text:
            return  # no steering: the call proceeds untouched
        tool_use = getattr(event, "tool_use", None) or {}
        tool_use_id = tool_use.get("toolUseId", "") if isinstance(tool_use, dict) else ""
        if tool_use_id:
            arm = getattr(source, "arm", None)
            state = getattr(source, "state", None)
            if callable(arm):
                arm(tool_use_id)
            elif state is not None:
                state.arm(tool_use_id)
        event.cancel_tool = STEERING_REDIRECT_TEMPLATE.format(text=text)

    return _hook


def _default_on_line(line: str) -> None:
    """Echo a captured line: plain print lands in the turn transcript."""
    print(STEERING_NOTED)
    print(f"> {line}")


STEERING_HOOK_ORDER = -100
"""Hook priority for the steering hook (mirrors ``HookOrder.SDK_FIRST``).

Lower values run first; the HITL intervention dispatcher runs at
``INTERVENTION_INPUT`` (90), so the steering hook always sees the
boundary first. Kept as a literal so this module never imports the
hooks package at module scope.
"""


def register_steering_hook(agent: Any, slot: SteeringSlot | None = None) -> SteeringSlot:
    """Register the boundary hook on an agent (idempotent per agent).

    Args:
        agent: SDK agent supporting ``add_hook``.
        slot: Session slot the hook closes over (created when omitted).

    Returns:
        The slot (also stashed as ``agent._steering_slot`` for the loop).
    """
    existing = getattr(agent, "_steering_slot", None)
    if isinstance(existing, SteeringSlot) and getattr(agent, "_steering_hook_registered", False):
        return existing
    from strands.hooks import HookOrder
    from strands.hooks.events import BeforeToolCallEvent

    owned = slot if slot is not None else (
        existing if isinstance(existing, SteeringSlot) else SteeringSlot()
    )
    agent.add_hook(make_steering_hook(owned), BeforeToolCallEvent, order=HookOrder.SDK_FIRST)
    try:
        agent._steering_slot = owned
        agent._steering_hook_registered = True
    except Exception:
        pass
    return owned


class SteeringReader:
    """Handle for a turn-owned stdin reader thread."""

    def __init__(self, thread: threading.Thread, shutdown: threading.Event) -> None:
        self._thread = thread
        self._shutdown = shutdown

    def stop(self) -> None:
        """Signal shutdown and join; never leaves a live reader behind."""
        self._shutdown.set()
        self._thread.join(timeout=5)

    @property
    def alive(self) -> bool:
        """True while the reader thread is running."""
        return self._thread.is_alive()


def start_steering_reader(
    state: SteeringState,
    gate_open: threading.Event,
    *,
    stdin: Any | None = None,
    on_line: Callable[[str], None] | None = None,
    poll_interval: float = 0.05,
) -> SteeringReader:
    """Start the turn-owned raw-readline reader (daemon + explicit stop).

    While ``gate_open`` is set the reader never consumes stdin, so an
    open approval prompt owns the terminal exclusively; buffered lines
    are picked up as steering once the prompt closes.

    Args:
        state: Per-turn mailbox armed by captured lines.
        gate_open: Set while the gate ``ask`` prompt is open.
        stdin: Stream to read (default: current ``sys.stdin``); tests
            pass a pipe. Must provide ``readline``.
        on_line: Capture callback (default: transcript echo).
        poll_interval: Sleep/select quantum between checks.

    Returns:
        A :class:`SteeringReader`; the caller must :meth:`stop` it at
        turn end (never daemon-only).
    """
    stream = stdin if stdin is not None else sys.stdin
    emit = on_line if on_line is not None else _default_on_line
    shutdown = threading.Event()

    try:
        fileno = stream.fileno()
    except Exception:
        fileno = None

    def _emit(line: str) -> None:
        if state.note(line):
            try:
                emit(line.strip())
            except Exception:
                pass  # capture must never kill the turn

    def _run() -> None:
        if fileno is not None:
            _run_fd(fileno)
        else:
            _run_readline()

    def _run_fd(fd: int) -> None:
        """Select+read loop on a nonblocking fd; shutdown is always prompt.

        A blocking ``readline`` cannot be woken for the turn-end join,
        and a parked reader would steal the next idle prompt's input
        (T-04-12) — so the fd is switched to nonblocking for the turn
        and restored afterwards. In cooked terminal mode the kernel
        still delivers complete lines, preserving line editing.
        """
        try:
            blocking = os.get_blocking(fd)
        except OSError:
            return
        buf = ""
        try:
            os.set_blocking(fd, False)
            while not shutdown.is_set():
                if gate_open.is_set():
                    if shutdown.wait(poll_interval):
                        break
                    continue
                try:
                    ready, _, _ = select.select([fd], [], [], poll_interval)
                except (OSError, ValueError):
                    break
                if shutdown.is_set():
                    break
                if not ready:
                    continue
                try:
                    chunk = os.read(fd, 4096)
                except BlockingIOError:
                    continue
                except OSError:
                    break
                if not chunk:  # EOF: pause, do not spin
                    if shutdown.wait(poll_interval):
                        break
                    continue
                buf += chunk.decode("utf-8", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    _emit(line)
        finally:
            try:
                os.set_blocking(fd, blocking)
            except OSError:
                pass

    def _run_readline() -> None:
        """Fallback for streams without a fileno (never production stdin)."""
        readline = getattr(stream, "readline", None)
        if readline is None:
            return
        while not shutdown.is_set():
            if gate_open.is_set():
                if shutdown.wait(poll_interval):
                    break
                continue
            try:
                line = readline()
            except (OSError, ValueError):
                break
            if not line:
                if shutdown.wait(poll_interval):
                    break
                continue
            _emit(line)

    thread = threading.Thread(target=_run, name="steering-reader", daemon=True)
    thread.start()
    return SteeringReader(thread, shutdown)
