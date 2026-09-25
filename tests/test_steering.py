"""Steering hook + reader tests (LOOP-02, D-09..D-12; replay model only).

Boundaries pinned here:

- The hook cancels the *next* tool call with a redirect message and
  clears one-shot; empty mailboxes are a no-op. Nothing on this path
  invokes the agent (no re-entrancy, no ``ConcurrencyException``).
- The reader arms pending text; while ``gate_open`` is set it never
  consumes stdin, so an open approval prompt is unaffected and
  buffered lines apply at the next boundary after the prompt closes.
- Reader lifecycle is turn-owned: explicit shutdown + join leaves no
  live thread behind.
"""

from __future__ import annotations

import os
import threading
import time
from types import SimpleNamespace

from strands_code_cli.policy_gate import PolicyClassifier, gate_open
from strands_code_cli.policy import PolicyConfig
from strands_code_cli.steering import (
    STEERING_NOTED,
    STREAMING_LIMIT,
    SteeringReader,
    SteeringSlot,
    SteeringState,
    _default_on_line,
    make_steering_hook,
    start_steering_reader,
)


def _hook_event(name="shell", uid="u1", **tool_input):
    return SimpleNamespace(
        tool_use={"name": name, "input": tool_input, "toolUseId": uid},
        cancel_tool=False,
    )


def _wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


class TestSteeringState:
    def test_bind_turn_resets(self):
        state = SteeringState()
        state.note("hello")
        state.arm("u1")
        state.bind_turn("turn-2")
        assert not state.has_pending()
        assert not state.consume_arm("u1")

    def test_blank_lines_ignored(self):
        state = SteeringState()
        assert state.note("   \n") is False
        assert not state.has_pending()

    def test_take_is_one_shot(self):
        state = SteeringState()
        state.note("go left")
        assert state.take() == "go left"
        assert state.take() is None


class TestSteeringHook:
    def test_redirect_message_shape(self):
        state = SteeringState()
        state.note("use sqlite")
        event = _hook_event(uid="u7")
        make_steering_hook(state)(event)
        assert event.cancel_tool.startswith("Steering redirected by user: use sqlite")
        assert "continue toward the revised goal" in event.cancel_tool
        assert "was not executed" in event.cancel_tool

    def test_hook_arms_boundary_for_skip_prompt(self):
        state = SteeringState()
        state.note("use sqlite")
        make_steering_hook(state)(_hook_event(uid="u7"))
        assert state.consume_arm("u7") is True
        assert state.consume_arm("u7") is False  # one-shot

    def test_hook_noop_without_pending(self):
        state = SteeringState()
        event = _hook_event()
        make_steering_hook(state)(event)
        assert event.cancel_tool is False

    def test_slot_source_delegates(self):
        slot = SteeringSlot()
        state = SteeringState()
        slot.state = state
        state.note("pivot")
        event = _hook_event(uid="u3")
        make_steering_hook(slot)(event)
        assert "pivot" in event.cancel_tool
        assert slot.consume_arm("u3") is True


class TestArmedSkipPrompt:
    def test_armed_boundary_skips_prompt_then_normal(self):
        classifier = PolicyClassifier(policy_loader=lambda: PolicyConfig())
        slot = SteeringSlot()
        state = SteeringState()
        slot.state = state
        classifier.bind_steering(slot)
        state.note("steer me")
        make_steering_hook(slot)(_hook_event(uid="u5"))

        from tests.test_mode import _event

        first = classifier(_event("shell", {"command": "x"}, uid="u5"))
        assert first.requires_human_in_the_loop is False
        assert first.reason == "steering-redirected"
        # Arm consumed: the same boundary shape prompts normally again.
        second = classifier(_event("shell", {"command": "x"}, uid="u6"))
        assert second.requires_human_in_the_loop is True


class _PipeStdin:
    """Minimal stdin double exposing a real fd for the select+read loop."""

    def __init__(self, fd: int) -> None:
        self._fd = fd

    def fileno(self) -> int:
        return self._fd


class TestSteeringReader:
    def test_capture_arms_pending_and_echoes(self):
        received: list[str] = []
        state = SteeringState()
        gate = threading.Event()
        read_fd, write_fd = os.pipe()
        try:
            reader = start_steering_reader(
                state, gate, stdin=_PipeStdin(read_fd), on_line=received.append
            )
            os.write(write_fd, b"use poetry instead\n")
            assert _wait_for(state.has_pending)
            assert state.take() == "use poetry instead"
            assert received == ["use poetry instead"]
            reader.stop()
            assert not reader.alive
        finally:
            os.close(write_fd)
            os.close(read_fd)

    def test_gate_open_buffers_without_arming(self):
        received: list[str] = []
        state = SteeringState()
        gate = threading.Event()
        gate.set()  # approval prompt open
        read_fd, write_fd = os.pipe()
        try:
            reader = start_steering_reader(
                state, gate, stdin=_PipeStdin(read_fd), on_line=received.append
            )
            os.write(write_fd, b"steer during prompt\n")
            time.sleep(0.3)
            # Untouched while the prompt is open: no pending, no echo.
            assert not state.has_pending()
            assert received == []
            gate.clear()  # prompt closed: buffered line applies next boundary
            assert _wait_for(state.has_pending)
            assert state.take() == "steer during prompt"
            reader.stop()
            assert not reader.alive
        finally:
            os.close(write_fd)
            os.close(read_fd)

    def test_gate_open_leaves_approval_unaffected(self, monkeypatch):
        # While gate_open is set, the classifier still returns its normal
        # verdict — the reader never diverts the y/n answer.
        classifier = PolicyClassifier(policy_loader=lambda: PolicyConfig())
        from tests.test_mode import _event

        gate_open.set()
        try:
            result = classifier(_event("shell", {"command": "make test"}, uid="u1"))
            assert result.requires_human_in_the_loop is True
        finally:
            gate_open.clear()

    def test_stop_joins_without_input(self):
        state = SteeringState()
        gate = threading.Event()
        read_fd, write_fd = os.pipe()
        try:
            reader = start_steering_reader(state, gate, stdin=_PipeStdin(read_fd))
            assert isinstance(reader, SteeringReader)
            reader.stop()
            assert not reader.alive
        finally:
            os.close(write_fd)
            os.close(read_fd)

    def test_default_echo_names_next_step(self, capsys):
        _default_on_line("pivot to sqlite")
        out = capsys.readouterr().out
        assert STEERING_NOTED in out
        assert "pivot to sqlite" in out

    def test_streaming_limit_named(self):
        assert "next step" in STREAMING_LIMIT
