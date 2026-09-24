"""Entry UX: slash dispatch, resume picker, session routing (D-02/D-03/D-04)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from strands_code_cli.router import USAGE_HINT, dispatch, show_picker


def _fresh_index(tmp_path):
    from strands_code_cli.session_index import SessionIndex

    return SessionIndex(tmp_path / "index")


def _with_snapshot(session_dir: Path, session_id: str) -> None:
    (session_dir / "session" / session_id).mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Slash dispatch
# ---------------------------------------------------------------------------


class TestSlashDispatch:
    def test_plain_text_is_agent_turn(self, tmp_path):
        index = _fresh_index(tmp_path)
        sid = index.mint()
        assert dispatch("fix the bug", session_id=sid, index=index) == ("agent", None)

    def test_exit_dispatches(self, tmp_path):
        index = _fresh_index(tmp_path)
        action, _ = dispatch("/exit", session_id=index.mint(), index=index)
        assert action == "exit"

    def test_resume_lists_recent_titles(self, tmp_path):
        index = _fresh_index(tmp_path)
        index.mint()
        sid = index.mint()
        index.rename(sid, "Atlas Project")
        action, message = dispatch("/resume", session_id=sid, index=index)
        assert action == "reply"
        assert "Atlas Project" in message

    def test_resume_unknown_id_replies_without_agent_turn(self, tmp_path):
        index = _fresh_index(tmp_path)
        action, message = dispatch("/resume nope", session_id=index.mint(), index=index)
        assert action == "reply"
        assert "Unknown session" in message

    def test_rename_persists_and_shows(self, tmp_path):
        index = _fresh_index(tmp_path)
        sid = index.mint()
        action, message = dispatch("/rename Atlas Project", session_id=sid, index=index)
        assert action == "reply"
        assert "Atlas Project" in message
        assert index.list_recent()[0]["title"] == "Atlas Project"

    def test_rename_empty_shows_usage(self, tmp_path):
        index = _fresh_index(tmp_path)
        action, message = dispatch("/rename", session_id=index.mint(), index=index)
        assert action == "reply"
        assert "Usage" in message

    def test_unknown_slash_hints_never_agent_turn(self, tmp_path):
        index = _fresh_index(tmp_path)
        action, message = dispatch("/bogus arg", session_id=index.mint(), index=index)
        assert action == "reply"
        assert USAGE_HINT in message

    def test_model_command_out_of_scope(self, tmp_path):
        index = _fresh_index(tmp_path)
        action, message = dispatch("/model sonnet", session_id=index.mint(), index=index)
        assert action == "reply"
        assert USAGE_HINT in message


# ---------------------------------------------------------------------------
# Resume picker
# ---------------------------------------------------------------------------


class TestShowPicker:
    def test_empty_index_returns_none_without_prompting(self, tmp_path):
        index = _fresh_index(tmp_path)
        with patch("strands_code_cli.router.typer.prompt") as prompt:
            assert show_picker(index, session_dir=tmp_path / "sessions") is None
        prompt.assert_not_called()

    def test_order_follows_updated_at(self, tmp_path):
        index = _fresh_index(tmp_path)
        session_dir = tmp_path / "sessions"
        first = index.mint()
        second = index.mint()
        index.rename(first, "First Work")
        index.rename(second, "Second Work")
        index.ensure(first)  # first is now the most recent
        _with_snapshot(session_dir, first)
        _with_snapshot(session_dir, second)
        with patch("strands_code_cli.router.typer.prompt", return_value=1):
            assert show_picker(index, session_dir=session_dir) == first

    def test_entries_without_snapshots_hidden(self, tmp_path):
        index = _fresh_index(tmp_path)
        session_dir = tmp_path / "sessions"
        orphan = index.mint()
        index.rename(orphan, "Orphan Mint")
        backed = index.mint()
        index.rename(backed, "Backed Session")
        _with_snapshot(session_dir, backed)
        with patch("strands_code_cli.router.typer.prompt", return_value=1):
            assert show_picker(index, session_dir=session_dir) == backed

    def test_all_orphans_returns_none_without_prompting(self, tmp_path):
        index = _fresh_index(tmp_path)
        index.mint()
        with patch("strands_code_cli.router.typer.prompt") as prompt:
            assert show_picker(index, session_dir=tmp_path / "sessions") is None
        prompt.assert_not_called()

    def test_start_new_choice_returns_none(self, tmp_path):
        index = _fresh_index(tmp_path)
        session_dir = tmp_path / "sessions"
        sid = index.mint()
        _with_snapshot(session_dir, sid)
        with patch("strands_code_cli.router.typer.prompt", return_value=2):
            assert show_picker(index, session_dir=session_dir) is None


# ---------------------------------------------------------------------------
# Auto-title helper
# ---------------------------------------------------------------------------


class _FakeModel:
    def __init__(self, text: str) -> None:
        self._text = text

    def generate(self, prompt: str) -> str:
        assert prompt
        return self._text


class TestAutoTitle:
    def test_model_title_capped_at_six_words(self, tmp_path):
        from types import SimpleNamespace

        from strands_code_cli.loop import _maybe_auto_title

        index = _fresh_index(tmp_path)
        sid = index.mint()
        agent = SimpleNamespace(model=_FakeModel("one two three four five six seven eight"))
        _maybe_auto_title(agent, sid, index, "what does this do")
        assert index.list_recent()[0]["title"] == "one two three four five six"

    def test_no_model_falls_back_to_first_ask(self, tmp_path):
        from strands_code_cli.loop import _maybe_auto_title

        index = _fresh_index(tmp_path)
        sid = index.mint()
        _maybe_auto_title(object(), sid, index, "explain the retry logic here please")
        assert index.list_recent()[0]["title"] == "explain the retry logic here please"
