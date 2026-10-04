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

    def test_model_command_routes_to_loop(self, tmp_path):
        # Phase 5 (MODEL-01): /model is a first-class command. A bare Bedrock
        # id validates via resolve_model and returns the loop-owned action.
        index = _fresh_index(tmp_path)
        action, message = dispatch("/model sonnet", session_id=index.mint(), index=index)
        assert action == "model"
        assert message == "sonnet"


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
        # 1 = session, 2 = delete row, 3 = start new.
        with patch("strands_code_cli.router.typer.prompt", return_value=3):
            assert show_picker(index, session_dir=session_dir) is None


class TestForgetCommand:
    def _backed_session(self, tmp_path, index, title="Doomed Work"):
        session_dir = tmp_path / "sessions"
        sid = index.mint()
        index.rename(sid, title)
        _with_snapshot(session_dir, sid)
        stash = index.root / "rich_history" / f"{sid}.json"
        stash.parent.mkdir(parents=True, exist_ok=True)
        stash.write_text("{}", encoding="utf-8")
        return session_dir, sid

    def test_forget_exact_id_removes_everything(self, tmp_path):
        index = _fresh_index(tmp_path)
        session_dir, sid = self._backed_session(tmp_path, index)
        current = index.mint()
        action, message = dispatch(f"/forget {sid}", session_id=current, index=index)
        assert action == "reply"
        assert message == f"Forgot session 'Doomed Work' [{sid[:8]}]."
        assert not (session_dir / "session" / sid).exists()
        assert not (index.root / "rich_history" / f"{sid}.json").exists()
        assert sid not in {e["id"] for e in index.list_recent(limit=None)}

    def test_forget_unique_prefix_resolves(self, tmp_path):
        index = _fresh_index(tmp_path)
        _, sid = self._backed_session(tmp_path, index)
        current = index.mint()
        action, message = dispatch(f"/forget {sid[:8]}", session_id=current, index=index)
        assert action == "reply"
        assert sid[:8] in message
        assert sid not in {e["id"] for e in index.list_recent(limit=None)}

    def test_forget_ambiguous_prefix_lists_matches(self, tmp_path):
        from strands_code_cli.session_index import SessionIndex

        root = tmp_path / "index"
        index = SessionIndex(root)
        # Two ids sharing a long prefix, minted deterministically.
        base = "abc12345"
        first = base + "0" + "0" * 23
        second = base + "1" + "1" * 23
        index.ensure(first)
        index.ensure(second)
        current = index.mint()
        action, message = dispatch(f"/forget {base}", session_id=current, index=index)
        assert action == "reply"
        assert "Ambiguous" in message
        assert first in message and second in message
        # Nothing deleted.
        assert {first, second} <= {e["id"] for e in index.list_recent(limit=None)}

    def test_forget_unknown_and_bare_and_current(self, tmp_path):
        index = _fresh_index(tmp_path)
        _, sid = self._backed_session(tmp_path, index)
        current = index.mint()
        action, message = dispatch("/forget nope-nope", session_id=current, index=index)
        assert action == "reply"
        assert "No session matches" in message
        action, message = dispatch("/forget", session_id=current, index=index)
        assert message == "Usage: /forget <session-id-or-prefix>"
        action, message = dispatch(f"/forget {current}", session_id=current, index=index)
        assert action == "reply"
        assert "active session" in message
        assert current in {e["id"] for e in index.list_recent(limit=None)}

    def test_forget_pure_orphan_dir(self, tmp_path):
        index = _fresh_index(tmp_path)
        session_dir = tmp_path / "sessions"
        orphan = "deadbeef-" + "2" * 27
        _with_snapshot(session_dir, orphan)
        current = index.mint()
        action, message = dispatch(f"/forget {orphan}", session_id=current, index=index)
        assert action == "reply"
        assert orphan in message
        assert not (session_dir / "session" / orphan).exists()

    def test_forget_traversal_arg_deletes_nothing(self, tmp_path):
        index = _fresh_index(tmp_path)
        session_dir, sid = self._backed_session(tmp_path, index)
        sentinel = session_dir / "session" / "sentinel.txt"
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("keep", encoding="utf-8")
        current = index.mint()
        action, message = dispatch("/forget ../../..", session_id=current, index=index)
        assert action == "reply"
        assert "No session matches" in message
        assert sentinel.exists()
        assert (session_dir / "session" / sid).exists()


class TestPickerDeleteTyped:
    def test_delete_confirmed_loops_back(self, tmp_path):
        index = _fresh_index(tmp_path)
        session_dir = tmp_path / "sessions"
        first = index.mint()
        index.rename(first, "First Work")
        second = index.mint()
        index.rename(second, "Second Work")
        index.ensure(first)  # first is most recent: listed first
        _with_snapshot(session_dir, first)
        _with_snapshot(session_dir, second)
        # 3 = delete row (2 sessions), 1 = first entry, 1 = confirm,
        # then refreshed list (1 session): 3 = start new.
        prompts = iter([3, 1, 1, 3])
        with patch(
            "strands_code_cli.router.typer.prompt", side_effect=lambda *a, **k: next(prompts)
        ):
            assert show_picker(index, session_dir=session_dir) is None
        assert first not in {e["id"] for e in index.list_recent(limit=None)}
        assert not (session_dir / "session" / first).exists()
        assert second in {e["id"] for e in index.list_recent(limit=None)}
        assert (session_dir / "session" / second).exists()

    def test_delete_cancel_keeps_everything(self, tmp_path):
        index = _fresh_index(tmp_path)
        session_dir = tmp_path / "sessions"
        sid = index.mint()
        _with_snapshot(session_dir, sid)
        # 2 = delete row, 2 = cancel in the sub-list, 3 = start new.
        prompts = iter([2, 2, 3])
        with patch(
            "strands_code_cli.router.typer.prompt", side_effect=lambda *a, **k: next(prompts)
        ):
            assert show_picker(index, session_dir=session_dir) is None
        assert sid in {e["id"] for e in index.list_recent(limit=None)}
        assert (session_dir / "session" / sid).exists()


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


# ---------------------------------------------------------------------------
# CliRunner routing (D-01/D-02, agent construction patched out)
# ---------------------------------------------------------------------------


def _patched_launch(main_module):
    """Patch the expensive seams; yields (build_agent, run_loop) mocks."""
    from contextlib import ExitStack, contextmanager

    @contextmanager
    def _launch():
        with ExitStack() as stack:
            stack.enter_context(
                patch.object(main_module, "_preflight_credentials", return_value=None)
            )
            build = stack.enter_context(
                patch.object(main_module, "build_agent", return_value=object())
            )
            yield build, stack.enter_context(patch.object(main_module, "run_loop"))

    return _launch()


class TestCliRouting:
    def test_no_arg_reaches_repl(self, tmp_path, monkeypatch):
        import importlib

        main_module = importlib.import_module("strands_code_cli.main")

        monkeypatch.chdir(tmp_path)  # real SessionIndex must not touch the repo
        with _patched_launch(main_module) as (_, loop):
            from typer.testing import CliRunner

            result = CliRunner().invoke(main_module.app, [])
        assert result.exit_code == 0, result.output
        loop.assert_called_once()
        minted = loop.call_args[1]["session_id"]
        import uuid

        uuid.UUID(minted)  # no-arg mints a fresh session id (D-01)

    def test_session_id_routes_to_given_session(self, tmp_path, monkeypatch):
        import importlib
        import uuid

        main_module = importlib.import_module("strands_code_cli.main")

        monkeypatch.chdir(tmp_path)
        session_id = str(uuid.uuid4())
        with _patched_launch(main_module) as (build, loop):
            from typer.testing import CliRunner

            result = CliRunner().invoke(main_module.app, ["--session-id", session_id])
        assert result.exit_code == 0, result.output
        assert build.call_args[0][0] == session_id
        assert loop.call_args[1]["session_id"] == session_id

    def test_session_id_skips_picker(self, tmp_path, monkeypatch):
        import importlib
        import uuid

        main_module = importlib.import_module("strands_code_cli.main")

        monkeypatch.chdir(tmp_path)
        with _patched_launch(main_module) as loop, patch.object(
            main_module, "show_picker", side_effect=AssertionError("picker must be skipped")
        ):
            from typer.testing import CliRunner

            result = CliRunner().invoke(
                main_module.app, ["--session-id", str(uuid.uuid4())]
            )
        assert result.exit_code == 0, result.output

    def test_no_arg_with_sessions_shows_picker(self, tmp_path, monkeypatch):
        import importlib

        main_module = importlib.import_module("strands_code_cli.main")

        monkeypatch.chdir(tmp_path)
        from strands_code_cli.session_index import SessionIndex

        index = SessionIndex(".agent/session_index")
        chosen = index.mint()
        index.rename(chosen, "Picked Work")
        (Path(".agent/sessions/session") / chosen).mkdir(parents=True)
        with _patched_launch(main_module) as (_, loop):
            from typer.testing import CliRunner

            result = CliRunner().invoke(main_module.app, [], input="1\n")
        assert result.exit_code == 0, result.output
        assert "Picked Work" in result.output
        assert loop.call_args[1]["session_id"] == chosen

    def test_malformed_id_is_usage_error_without_sessions(self, tmp_path, monkeypatch):
        import importlib

        main_module = importlib.import_module("strands_code_cli.main")

        monkeypatch.chdir(tmp_path)
        from typer.testing import CliRunner

        result = CliRunner().invoke(main_module.app, ["--session-id", "../../x"])
        assert result.exit_code != 0
        assert "session-id" in result.output.lower()
        assert not Path(".agent").exists()


# ---------------------------------------------------------------------------
# /policy inspect-only dispatch (Phase 3: reply-only, never an agent turn)
# ---------------------------------------------------------------------------


class TestPolicyDispatch:
    def test_policy_show_is_reply(self, tmp_path):
        index = _fresh_index(tmp_path)
        action, message = dispatch("/policy show", session_id=index.mint(), index=index)
        assert action == "reply"
        assert "deny-wins" in message

    def test_policy_bare_show_is_reply(self, tmp_path):
        index = _fresh_index(tmp_path)
        action, message = dispatch("/policy", session_id=index.mint(), index=index)
        assert action == "reply"
        assert "Effective policy" in message

    def test_policy_last_is_reply(self, tmp_path):
        index = _fresh_index(tmp_path)
        action, message = dispatch("/policy last", session_id=index.mint(), index=index)
        assert action == "reply"
        assert message is not None

    def test_policy_bogus_shows_usage_never_agent_turn(self, tmp_path):
        index = _fresh_index(tmp_path)
        action, message = dispatch("/policy bogus", session_id=index.mint(), index=index)
        assert action == "reply"
        assert "Usage: /policy" in message
