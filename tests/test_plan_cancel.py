"""Two-press cancel + cancel-time flush tests (LOOP-04, D-13..D-16).

Semantics pinned here (04-PLAN.md resolved items 5+8+11):

- Press #1 during a turn requests graceful stop via the caller-owned
  event and prints the first-press copy; the session flushes at cancel
  time (``explicit_save`` + ``index.ensure``) so partial work survives
  even a killed CLI. Press #2 inside 5 s confirms (idempotent — the
  stop was already requested). A press after the window lapses prints
  the honest still-cancelling copy: the SDK offers no un-cancel, the
  remainder is dropped, and no resume is ever promised.
- Ctrl-C at the idle prompt still clears the line (D-14, untouched).
- Ctrl-C inside an open gate prompt propagates (``except Exception``
  cannot catch KeyboardInterrupt): the ask finally clears the gate flag
  and the turn takes the normal two-press path. The per-turn SIGINT
  handler additionally sets the caller-owned cancel event first, so the
  stop is also observed when the SDK absorbs the exception.
- After cancel the loop falls through to the prompt in the same
  session with the mode unchanged (D-07/D-16).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from prompt_toolkit.history import InMemoryHistory

import strands_code_cli.loop as loop_module
from strands_code_cli.loop import (
    CANCEL_CONFIRMED,
    CANCEL_FIRST_PRESS,
    CANCEL_STILL,
    _choose_cancel_targets,
    _handle_turn_cancel,
    _make_turn_sigint_handler,
    ask_cancel_target,
    resolve_cancel_targets,
    run_loop,
)
from strands_code_cli.mode import APPROVE_EMPTY, MODE_PLAN_REPLY, PLAN_PREFIX
from strands_code_cli.session_index import SessionIndex


class _LoopAgent:
    """Turn double: records inputs, hooks, and cancel-time saves."""

    def __init__(self, behavior=None) -> None:
        self.inputs: list[str] = []
        self.hooks: list[tuple] = []
        self.saved: list[bool] = []
        self._behavior = behavior if behavior is not None else (lambda text: None)

        async def _save(agent: Any, is_latest: bool = True) -> None:
            self.saved.append(is_latest)

        self._session_manager = SimpleNamespace(save_snapshot=_save)

    def __call__(self, text: str) -> None:
        self.inputs.append(text)
        return self._behavior(text)

    def add_hook(self, callback: Any, event_type: Any = None, **kwargs: Any) -> None:
        self.hooks.append((callback, event_type, kwargs))


def _raise_keyboard_interrupt(text: str) -> None:
    raise KeyboardInterrupt


class _ScriptSession:
    """PromptSession double: scripted lines, then EOF (Ctrl-D)."""

    def __init__(self, script: list[Any]) -> None:
        self._script = list(script)

    def prompt(self, *args: Any, **kwargs: Any) -> str:
        if not self._script:
            raise EOFError
        item = self._script.pop(0)
        if item is KeyboardInterrupt:
            raise KeyboardInterrupt
        return item


def _run_script(script: list[Any], tmp_path, agent=None, monotonic=None, monkeypatch=None):
    agent = agent if agent is not None else _LoopAgent()
    monkeypatch.setattr(loop_module, "PromptSession", lambda **k: _ScriptSession(script))
    monkeypatch.setattr(loop_module, "_history", lambda: InMemoryHistory())
    # Hermetic curate boundary: ambient harness fact files must not queue
    # promotion proposals (and prompt on stdin) during scripted loop runs.
    monkeypatch.setattr(loop_module, "MEMORY_FACT_DIR", tmp_path / "memory")
    if monotonic is not None:
        monkeypatch.setattr(loop_module, "monotonic", monotonic)
    index = SessionIndex(tmp_path / "index")
    session_id = index.mint()
    run_loop(agent, session_id=session_id, index=index)
    return agent, index, session_id


def _flat(out: str) -> str:
    """Collapse console wrapping so copy asserts match exactly."""
    return " ".join(out.split())


class TestPlanTurnPrefix:
    def test_plan_turn_carries_prefix_act_turn_bare(self, tmp_path, monkeypatch, capsys):
        agent, _, _ = _run_script(
            ["/mode plan", "design it", "/mode act", "build it", "/exit"],
            tmp_path,
            monkeypatch=monkeypatch,
        )
        assert agent.inputs[0] == f"{PLAN_PREFIX}\n\ndesign it"
        assert agent.inputs[1] == "build it"
        out = _flat(capsys.readouterr().out)
        assert MODE_PLAN_REPLY in out

    def test_approve_runs_execution_turn_with_prompt(self, tmp_path, monkeypatch, capsys):
        from strands_code_cli.mode import APPROVE_EXECUTE, APPROVE_OK

        agent, _, _ = _run_script(
            ["/mode plan", "design it", "/approve", "/exit"],
            tmp_path,
            monkeypatch=monkeypatch,
        )
        assert agent.inputs[0] == f"{PLAN_PREFIX}\n\ndesign it"
        assert agent.inputs[1] == f"{APPROVE_OK}\n{APPROVE_EXECUTE}"

    def test_cancelled_plan_turn_arms_no_approve(self, tmp_path, monkeypatch, capsys):
        agent = _LoopAgent(behavior=_raise_keyboard_interrupt)
        _run_script(["/mode plan", "doomed", "/approve", "/exit"], tmp_path, agent,
                    monkeypatch=monkeypatch)
        out = _flat(capsys.readouterr().out)
        assert CANCEL_FIRST_PRESS in out
        assert APPROVE_EMPTY in out  # cancelled turn proposed nothing


class TestTwoPressCancel:
    def test_first_press_requests_stop_and_flushes(self, tmp_path, monkeypatch, capsys):
        agent = _LoopAgent(behavior=_raise_keyboard_interrupt)
        agent, _, session_id = _run_script(
            ["t1", "/exit"], tmp_path, agent, monkeypatch=monkeypatch
        )
        out = _flat(capsys.readouterr().out)
        assert CANCEL_FIRST_PRESS in out
        assert CANCEL_CONFIRMED not in out
        assert agent.saved  # cancel-time flush ran (kill-after-cancel keeps work)

    def test_second_press_inside_window_confirms(self, tmp_path, monkeypatch, capsys):
        agent = _LoopAgent(behavior=_raise_keyboard_interrupt)
        ticks = iter([100.0, 101.0])
        _run_script(
            ["t1", "t2", "/exit"], tmp_path, agent,
            monotonic=lambda: next(ticks), monkeypatch=monkeypatch,
        )
        out = _flat(capsys.readouterr().out)
        assert CANCEL_FIRST_PRESS in out
        assert CANCEL_CONFIRMED in out
        assert len(agent.saved) >= 2  # flush on request and on confirm

    def test_press_after_window_lapse_is_honest(self, tmp_path, monkeypatch, capsys):
        agent = _LoopAgent(behavior=_raise_keyboard_interrupt)
        ticks = iter([100.0, 200.0])
        _run_script(
            ["t1", "t2", "/exit"], tmp_path, agent,
            monotonic=lambda: next(ticks), monkeypatch=monkeypatch,
        )
        out = _flat(capsys.readouterr().out)
        assert CANCEL_STILL in out
        assert CANCEL_CONFIRMED not in out
        assert "resume" not in out.lower()  # no un-cancel promise anywhere

    def test_idle_ctrl_c_still_clears_line(self, tmp_path, monkeypatch, capsys):
        agent = _LoopAgent()
        _run_script([KeyboardInterrupt, "/exit"], tmp_path, agent, monkeypatch=monkeypatch)
        out = _flat(capsys.readouterr().out)
        assert CANCEL_FIRST_PRESS not in out
        assert agent.inputs == []  # no turn ran

    def test_post_cancel_mode_unchanged(self, tmp_path, monkeypatch, capsys):
        agent = _LoopAgent(behavior=_raise_keyboard_interrupt)
        _run_script(
            ["/mode plan", "doomed", "/mode", "/exit"], tmp_path, agent,
            monkeypatch=monkeypatch,
        )
        out = _flat(capsys.readouterr().out)
        assert out.count(MODE_PLAN_REPLY) == 2  # switch announce + still plan after cancel


class TestKillAfterCancel:
    def test_cancel_flush_keeps_partial_work(self, tmp_path):
        import uuid
        from pathlib import Path

        from strands_code_cli.loop import explicit_save
        from tests.test_kill_resume import _make_session_agent, _transcript_text

        session_id = str(uuid.uuid4())
        session_dir = Path(tmp_path) / "sessions"
        first = _make_session_agent(session_id, session_dir, "first answer")
        first("completed turn marker")
        explicit_save(first)  # exactly what the cancel path runs
        # SIGKILL here: no exit flush, no index update.
        second = _make_session_agent(session_id, session_dir, "second answer")
        assert "completed turn marker" in _transcript_text(second)


class TestTurnSigintHandler:
    """Per-turn SIGINT handler: effective even when the SDK absorbs KI."""

    def test_handler_sets_event_and_chains_default(self):
        import signal
        import threading

        from strands_code_cli.loop import _make_turn_sigint_handler

        event = threading.Event()
        handler = _make_turn_sigint_handler(event, signal.SIG_DFL)
        try:
            handler(signal.SIGINT, None)
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("default disposition must re-raise")
        assert event.is_set()

    def test_handler_chains_callable_prev(self):
        import signal
        import threading

        from strands_code_cli.loop import _make_turn_sigint_handler

        event = threading.Event()
        seen: list[str] = []
        handler = _make_turn_sigint_handler(event, lambda s, f: seen.append("prev"))
        handler(signal.SIGINT, None)
        assert event.is_set()
        assert seen == ["prev"]

    def test_handler_ignores_sig_ign_but_sets_event(self):
        import signal
        import threading

        from strands_code_cli.loop import _make_turn_sigint_handler

        event = threading.Event()
        handler = _make_turn_sigint_handler(event, signal.SIG_IGN)
        handler(signal.SIGINT, None)  # must not raise
        assert event.is_set()

    def test_turn_installs_and_restores_handler(self, tmp_path, monkeypatch):
        import signal

        before = signal.getsignal(signal.SIGINT)
        agent, _, _ = _run_script(["hello", "/exit"], tmp_path, monkeypatch=monkeypatch)
        assert agent.inputs == ["hello"]
        assert signal.getsignal(signal.SIGINT) is before

    def test_handler_installed_during_turn(self, tmp_path, monkeypatch):
        import signal

        import strands_code_cli.loop as loop_module

        seen: list[str] = []

        def behavior(text: str) -> None:
            current = signal.getsignal(signal.SIGINT)
            seen.append("wrapped" if "turn_sigint" in repr(getattr(current, "__qualname__", "")) else "other")

        agent = _LoopAgent(behavior=behavior)
        _run_script(["hello", "/exit"], tmp_path, agent, monkeypatch=monkeypatch)
        assert seen == ["wrapped"]


class TestResolveCancelTargets:
    """Chooser answer → named cancel events (D-08). Unknown fails closed."""

    def test_maps_every_answer(self):
        assert resolve_cancel_targets("main") == ("main",)
        assert resolve_cancel_targets("btw") == ("btw",)
        assert resolve_cancel_targets("both") == ("main", "btw")
        assert resolve_cancel_targets(None) == ()
        assert resolve_cancel_targets("bogus") == ()


class TestAskCancelTarget:
    """Chooser dialog contract: picked value or None, never a crash."""

    def test_returns_picked_value(self, monkeypatch):
        monkeypatch.setattr(loop_module, "radio_choice", lambda *a, **k: "btw")
        assert ask_cancel_target() == "btw"

    def test_esc_returns_none(self, monkeypatch):
        monkeypatch.setattr(loop_module, "radio_choice", lambda *a, **k: None)
        assert ask_cancel_target() is None

    def test_no_tty_fails_closed(self, monkeypatch):
        def _raise(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("radio_choice needs a tty")

        monkeypatch.setattr(loop_module, "radio_choice", _raise)
        assert ask_cancel_target() is None

    def test_ctrl_c_propagates(self, monkeypatch):
        def _raise(*args: Any, **kwargs: Any) -> Any:
            raise KeyboardInterrupt

        monkeypatch.setattr(loop_module, "radio_choice", _raise)
        try:
            ask_cancel_target()
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("Ctrl-C in the chooser must propagate")

    def test_chooser_title_and_items(self, monkeypatch):
        seen: dict[str, Any] = {}

        def _fake(title: str, options: Any, **kwargs: Any) -> Any:
            seen["title"] = title
            seen["options"] = tuple(options)
            return "main"

        monkeypatch.setattr(loop_module, "radio_choice", _fake)
        assert ask_cancel_target() == "main"
        assert seen["title"] == "Cancel which?"
        assert seen["options"] == (
            ("main", "Main task"),
            ("btw", "Side answer"),
            ("both", "Both"),
        )

    def test_chooser_holds_guard_during_dialog(self, monkeypatch):
        seen: dict[str, Any] = {}

        def _fake(title: str, options: Any, **kwargs: Any) -> Any:
            seen["held"] = loop_module.gate_open.held()
            return "btw"

        monkeypatch.setattr(loop_module, "radio_choice", _fake)
        assert loop_module.gate_open.held() is False  # headless: no holder
        assert ask_cancel_target() == "btw"
        assert seen["held"] is True  # held for the whole dialog call
        assert loop_module.gate_open.held() is False  # released after


class TestChooseCancelTargets:
    """Pump-level choice: empty passes through, in-chooser Ctrl-C names both."""

    def test_empty_answer_passes_through(self, monkeypatch):
        monkeypatch.setattr(loop_module, "ask_cancel_target", lambda: None)
        assert _choose_cancel_targets() == ()

    def test_ctrl_c_inside_escalates_to_both(self, monkeypatch):
        def _raise() -> Any:
            raise KeyboardInterrupt

        monkeypatch.setattr(loop_module, "ask_cancel_target", _raise)
        assert _choose_cancel_targets() == ("main", "btw")


class TestBothRunningHandler:
    """Turn SIGINT handler with the both_running flag (D-08).

    While both workers run the handler sets no event — the chooser
    names the targets — and still chains the previous disposition.
    """

    def test_set_flag_chains_default_without_setting_either_event(self):
        import signal
        import threading

        event = threading.Event()
        bystander = threading.Event()
        both_running = threading.Event()
        both_running.set()
        handler = _make_turn_sigint_handler(
            event, signal.SIG_DFL, both_running=both_running
        )
        try:
            handler(signal.SIGINT, None)
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("default disposition must re-raise")
        assert not event.is_set()
        assert not bystander.is_set()

    def test_set_flag_chains_callable_prev_without_setting(self):
        import signal
        import threading

        event = threading.Event()
        both_running = threading.Event()
        both_running.set()
        seen: list[str] = []
        handler = _make_turn_sigint_handler(
            event, lambda s, f: seen.append("prev"), both_running=both_running
        )
        handler(signal.SIGINT, None)
        assert not event.is_set()
        assert seen == ["prev"]

    def test_unset_flag_keeps_legacy_set_event_behavior(self):
        import signal
        import threading

        event = threading.Event()
        both_running = threading.Event()  # clear: single worker
        handler = _make_turn_sigint_handler(
            event, signal.SIG_DFL, both_running=both_running
        )
        try:
            handler(signal.SIGINT, None)
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("default disposition must re-raise")
        assert event.is_set()


class TestHandleTurnCancelTarget:
    """Per-target two-press copy: main byte-identical, others tagged."""

    def test_btw_first_press_names_target(self, tmp_path, capsys):
        import threading

        agent = _LoopAgent()
        index = SessionIndex(tmp_path / "index")
        session_id = index.mint()
        event = threading.Event()
        armed = _handle_turn_cancel(agent, session_id, index, event, None, target="btw")
        out = _flat(capsys.readouterr().out)
        assert CANCEL_FIRST_PRESS in out
        assert "[btw]" in out
        assert event.is_set()
        assert armed is not None

    def test_btw_second_press_confirms(self, tmp_path, capsys):
        import threading

        agent = _LoopAgent()
        index = SessionIndex(tmp_path / "index")
        session_id = index.mint()
        event = threading.Event()
        armed = _handle_turn_cancel(agent, session_id, index, event, None, target="btw")
        capsys.readouterr()
        assert armed is not None
        confirmed = _handle_turn_cancel(
            agent, session_id, index, event, armed, target="btw"
        )
        out = _flat(capsys.readouterr().out)
        assert CANCEL_CONFIRMED in out
        assert "[btw]" in out
        assert confirmed is None

    def test_main_target_keeps_legacy_copy(self, tmp_path, capsys):
        import threading

        agent = _LoopAgent()
        index = SessionIndex(tmp_path / "index")
        session_id = index.mint()
        event = threading.Event()
        _handle_turn_cancel(agent, session_id, index, event, None, target="main")
        out = _flat(capsys.readouterr().out)
        assert CANCEL_FIRST_PRESS in out
        assert "[main]" not in out

