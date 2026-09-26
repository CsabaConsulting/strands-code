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
