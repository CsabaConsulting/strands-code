"""Arrow-key choice dialogs: approval mapping, cancel, picker (CHOICE-01).

The approval gate uses the prompt_toolkit dialog on a tty and the typed
``input()`` path otherwise (existing ``test_policy_gate`` fakes cover the
typed path). These tests cover the dialog branch by faking a tty plus a
stubbed ``radio_choice`` — no real terminal needed.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from strands.vended_interventions.hitl import HumanInTheLoop

import strands_code_cli.choice as choice_module
from strands_code_cli.policy import PolicyConfig
from strands_code_cli.policy_gate import PolicyClassifier
from strands_code_cli.router import show_picker


class _FakeAgent:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {}


def _event(name: str, tool_input: dict[str, Any], uid: str = "t1"):
    return SimpleNamespace(
        agent=_FakeAgent(),
        tool_use={"name": name, "input": tool_input, "toolUseId": uid},
    )


def _tty_gate(monkeypatch, picked: Any):
    """Classifier + handler with a tty stdin and stubbed radio dialog."""
    monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: True))
    if isinstance(picked, BaseException):
        def _raise(*args, **kwargs):
            raise picked

        monkeypatch.setattr(choice_module, "radio_choice", _raise)
    else:
        monkeypatch.setattr(choice_module, "radio_choice", lambda *a, **k: picked)
    classifier = PolicyClassifier(policy_loader=PolicyConfig.load)
    handler = HumanInTheLoop(
        allowed_tools=["read", "search"], classifier=classifier, ask=classifier.ask
    )
    return classifier, handler


def _run(handler, event):
    return asyncio.run(handler.before_tool_call(event))


class TestApprovalDialog:
    def test_dialog_yes_approves(self, monkeypatch):
        classifier, handler = _tty_gate(monkeypatch, "y")
        result = _run(handler, _event("shell", {"command": "make test"}, uid="u1"))
        assert result.evaluate("y") is True
        assert any("approved shell" in line for line in classifier.batch.covered())

    def test_dialog_escape_denies_fail_closed(self, monkeypatch):
        _, handler = _tty_gate(monkeypatch, None)
        result = _run(handler, _event("shell", {"command": "make test"}, uid="u2"))
        assert result.evaluate("n") is False

    def test_dialog_ctrl_c_reraises_for_cancel(self, monkeypatch):
        _, handler = _tty_gate(monkeypatch, KeyboardInterrupt())
        with pytest.raises(KeyboardInterrupt):
            _run(handler, _event("shell", {"command": "make test"}, uid="u3"))


class TestSessionPickerDialog:
    def _index(self):
        return SimpleNamespace(
            list_recent=lambda limit=None: [
                {"id": "abc123", "title": "first"},
                {"id": "def456", "title": "second"},
            ]
        )

    def test_picker_returns_chosen_id(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: True))
        monkeypatch.setattr(choice_module, "radio_choice", lambda *a, **k: "def456")
        assert show_picker(self._index()) == "def456"

    def test_picker_escape_means_start_new(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: True))
        monkeypatch.setattr(choice_module, "radio_choice", lambda *a, **k: None)
        assert show_picker(self._index()) is None

    def _real_index(self, tmp_path):
        from strands_code_cli.session_index import SessionIndex

        index = SessionIndex(tmp_path / "index")
        session_dir = tmp_path / "sessions"
        first = index.mint()
        index.rename(first, "First Work")
        second = index.mint()
        index.rename(second, "Second Work")
        index.ensure(first)  # first is most recent: listed first
        for sid in (first, second):
            (session_dir / "session" / sid).mkdir(parents=True, exist_ok=True)
        return index, session_dir, first, second

    def _script(self, monkeypatch, replies):
        monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: True))
        calls = []

        def _stub(title, options, **kwargs):
            calls.append(title)
            return replies[len(calls) - 1]

        monkeypatch.setattr(choice_module, "radio_choice", _stub)
        return calls

    def test_picker_delete_confirmed(self, tmp_path, monkeypatch):
        from strands_code_cli.router import _SESSION_DELETE, _SESSION_DELETE_CONFIRM

        index, session_dir, first, second = self._real_index(tmp_path)
        calls = self._script(
            monkeypatch, [_SESSION_DELETE, first, _SESSION_DELETE_CONFIRM, None]
        )
        assert show_picker(index, session_dir=session_dir) is None
        assert calls == [
            "Recent sessions",
            "Delete a session",
            f"Delete 'First Work' [{first[:8]}]?",
            "Recent sessions",
        ]
        assert first not in {e["id"] for e in index.list_recent(limit=None)}
        assert not (session_dir / "session" / first).exists()
        assert second in {e["id"] for e in index.list_recent(limit=None)}

    def test_picker_delete_cancel_at_target(self, tmp_path, monkeypatch):
        from strands_code_cli.router import _SESSION_DELETE

        index, session_dir, first, _second = self._real_index(tmp_path)
        self._script(monkeypatch, [_SESSION_DELETE, None, None])
        assert show_picker(index, session_dir=session_dir) is None
        assert first in {e["id"] for e in index.list_recent(limit=None)}
        assert (session_dir / "session" / first).exists()

    def test_picker_delete_cancel_at_confirm(self, tmp_path, monkeypatch):
        from strands_code_cli.router import _SESSION_DELETE

        index, session_dir, first, _second = self._real_index(tmp_path)
        self._script(monkeypatch, [_SESSION_DELETE, first, None, None])
        assert show_picker(index, session_dir=session_dir) is None
        assert first in {e["id"] for e in index.list_recent(limit=None)}
        assert (session_dir / "session" / first).exists()


class TestRadioChoice:
    def test_refuses_without_tty(self):
        # Test stdin is a pipe: the dialog must decline so callers fall back
        # to typed input instead of crashing on a headless terminal.
        with pytest.raises(RuntimeError):
            choice_module.radio_choice("T?", [("y", "Yes")])

    def test_all_options_rendered(self):
        # Regression: popping the trailing newline once dropped the last
        # option tuple ("Start new session" / "Never" silently missing).
        values = [("a", "Alpha"), ("b", "Beta"), ("c", "Gamma"), (None, "Start new")]
        for selected in range(len(values)):
            text = "".join(
                chunk for _, chunk in choice_module._choice_fragments(values, selected)
            )
            for _, label in values:
                assert label in text
            assert text.count("(*)") == 1
            assert not text.endswith("\n")

    def test_window_renders_visible_slice_only(self):
        # Long lists (Bedrock discovery returns 50+ models) render only the
        # visible window so the frame fits the terminal; the highlight must
        # sit on the selected row inside the window.
        values = [(f"v{i}", f"Model-{i:02d}") for i in range(10)]
        text = "".join(
            chunk
            for _, chunk in choice_module._choice_fragments(
                values, 7, top=5, visible=4
            )
        )
        assert "Model-07" in text
        assert text.count("(*)") == 1
        marked = [line for line in text.split("\n") if "(*)" in line]
        assert marked == [" (*) Model-07"]
        for label in ("Model-00", "Model-04", "Model-09"):
            assert label not in text
        assert not text.endswith("\n")

    def test_window_clamps_to_available_options(self):
        values = [(f"v{i}", f"Model-{i:02d}") for i in range(3)]
        text = "".join(
            chunk
            for _, chunk in choice_module._choice_fragments(
                values, 2, top=0, visible=10
            )
        )
        assert text.count("(*)") == 1
        for label in ("Model-00", "Model-01", "Model-02"):
            assert label in text
        marked = [line for line in text.split("\n") if "(*)" in line]
        assert marked == [" (*) Model-02"]


class TestHeadlessDialog:
    """Drive the real prompt_toolkit app with piped keys (no tty needed).

    Regression cover for the Enter-did-nothing picker bug: the stock
    widget binds Enter to "check the item" without exiting, shadowing any
    app-level Enter binding.
    """

    def _run_keys(self, keys: str, default: int = 0):
        from prompt_toolkit.input.defaults import create_pipe_input
        from prompt_toolkit.output import DummyOutput

        values = [("a", "Alpha"), ("b", "Beta"), ("c", "Gamma")]
        with create_pipe_input() as inp:
            inp.send_text(keys)
            app = choice_module._build_app(
                "Pick?", values, default, input=inp, output=DummyOutput()
            )
            return app.run()

    # NOTE: feed raw byte sequences here — prompt_toolkit's Keys members
    # are binding *names* ("down", "escape"), not input sequences.
    DOWN = "\x1b[B"
    UP = "\x1b[A"
    ENTER = "\r"
    SPACE = " "
    ESCAPE = "\x1b"
    CTRL_C = "\x03"

    def test_enter_confirms_highlighted(self):
        assert self._run_keys(self.ENTER) == "a"

    def test_space_confirms_highlighted(self):
        assert self._run_keys(self.SPACE) == "a"

    def test_arrows_then_enter_confirms_moved(self):
        assert self._run_keys(self.DOWN + self.ENTER) == "b"

    def test_arrows_clamp_at_edges(self):
        assert self._run_keys(self.UP + self.ENTER) == "a"
        assert self._run_keys(self.DOWN + self.DOWN + self.DOWN + self.ENTER) == "c"

    def test_escape_denies(self):
        assert self._run_keys(self.ESCAPE) is None

    def test_ctrl_c_returns_cancel_sentinel(self):
        assert self._run_keys(self.CTRL_C) is choice_module.CANCELLED

    def test_selection_moves_past_first_window(self):
        # With a 5-row window over 30 options, 12 downs must land on and
        # confirm option 12 — the window follows the highlight.
        from prompt_toolkit.input.defaults import create_pipe_input
        from prompt_toolkit.output import DummyOutput

        values = [(f"v{i}", f"Model-{i:02d}") for i in range(30)]
        with create_pipe_input() as inp:
            inp.send_text(self.DOWN * 12 + self.ENTER)
            app = choice_module._build_app(
                "Pick?",
                values,
                0,
                input=inp,
                output=DummyOutput(),
                visible_rows=5,
            )
            assert app.run() == "v12"
            # The rendered window followed: 5 rows with the marker on Model-12.
            control = app.layout.current_control
            rendered = "".join(chunk for _, chunk in control.text())
            assert rendered.count("(*)") == 1
            assert " (*) Model-12" in rendered.split("\n")
            assert len(rendered.split("\n")) == 5


class TestDialogGuard:
    """radio_choice choke point: guard hold plus typeahead hygiene (R2b)."""

    def test_holds_guard_during_dialog(self, monkeypatch):
        from strands_code_cli.steering import stdin_guard

        monkeypatch.setattr(
            "sys.stdin",
            SimpleNamespace(isatty=lambda: True, fileno=lambda: 0, encoding="utf-8"),
        )
        seen: dict[str, Any] = {}

        class _App:
            def run(self):
                seen["held"] = stdin_guard.held()
                return "y"

        monkeypatch.setattr(choice_module, "_build_app", lambda *a, **k: _App())
        assert choice_module.radio_choice("T?", [("y", "Yes")]) == "y"
        assert seen["held"] is True  # held for the dialog's whole lifetime
        assert stdin_guard.held() is False  # released after

    def test_entry_clears_typeahead(self, monkeypatch):
        from prompt_toolkit.input.typeahead import get_typeahead, store_typeahead

        from strands_code_cli.steering import stdin_guard

        monkeypatch.setattr(
            "sys.stdin",
            SimpleNamespace(isatty=lambda: False, fileno=lambda: 0, encoding="utf-8"),
        )
        probe = SimpleNamespace(typeahead_hash=lambda: "fd-0")
        store_typeahead(probe, ["mashed-1", "mashed-2"])  # last dialog's mash
        with pytest.raises(RuntimeError):
            choice_module.radio_choice("T?", [("y", "Yes")])
        # Hygiene runs before the tty check: mashed keys cannot
        # auto-confirm the next dialog.
        assert get_typeahead(probe) == []
        assert stdin_guard.held() is False  # released on the error path
