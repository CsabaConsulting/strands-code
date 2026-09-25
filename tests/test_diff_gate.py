"""Diff-gate contracts: mode store, wrapper gate matrix, rendering (TOOL-02, D-04)."""

from __future__ import annotations

import asyncio

import pytest
from rich.console import Console

from strands_code_agent.callback_handler import CodeAgentCallbackHandler
from strands_code_cli import diff_gate
from strands_code_cli.diff_config import DEFAULT_MODE, DiffConfig
from strands_code_cli.diff_gate import (
    PendingStore,
    apply_stashed,
    bind_session,
    make_gated_edit,
    make_gated_write,
    split_hunks,
    store_for,
    unified_diff,
)
from strands_code_cli.router import USAGE_HINT, dispatch
from strands_code_cli.session_index import SessionIndex


def _mem_io(files: dict):
    async def read(path):
        return files.get(path)

    async def write(path, content):
        files[path] = content

    return read, write


def _run(coro):
    return asyncio.run(coro)


def _fresh_index(tmp_path):
    return SessionIndex(tmp_path / "index")


# ---------------------------------------------------------------------------
# DiffConfig persistence (ProviderConfig pattern)
# ---------------------------------------------------------------------------


class TestDiffConfig:
    def test_default_mode_on_demand(self):
        assert DiffConfig().mode == DEFAULT_MODE == "on-demand"

    def test_mode_round_trip(self, tmp_path):
        path = tmp_path / "diff.yaml"
        DiffConfig(mode="approve-each").save(path)
        assert DiffConfig.load(path).mode == "approve-each"

    def test_missing_file_fail_soft(self, tmp_path):
        assert DiffConfig.load(tmp_path / "nope.yaml").mode == "on-demand"

    def test_corrupt_file_fail_soft(self, tmp_path):
        path = tmp_path / "diff.yaml"
        path.write_text("{{{not yaml")
        assert DiffConfig.load(path).mode == "on-demand"

    def test_bogus_mode_fail_soft(self, tmp_path):
        path = tmp_path / "diff.yaml"
        path.write_text("mode: yolo\n")
        assert DiffConfig.load(path).mode == "on-demand"

    def test_symlink_refused(self, tmp_path):
        real = tmp_path / "real.yaml"
        real.write_text("mode: auto\n")
        link = tmp_path / "link.yaml"
        try:
            link.symlink_to(real)
        except OSError:
            pytest.skip("symlinks unavailable")
        with pytest.raises(ValueError, match="symlink"):
            DiffConfig.load(link)

    def test_save_rejects_bogus_mode(self, tmp_path):
        with pytest.raises(ValueError, match="approve-each"):
            DiffConfig(mode="yolo").save(tmp_path / "diff.yaml")


# ---------------------------------------------------------------------------
# Router: /diff + /search dispatch (reply only, never an agent turn)
# ---------------------------------------------------------------------------


class TestDiffRouter:
    def test_diff_show_reports_mode_and_pending(self, tmp_path):
        index = _fresh_index(tmp_path)
        sid = index.mint()
        cfg = tmp_path / "diff.yaml"
        DiffConfig(mode="auto").save(cfg)
        store = PendingStore(tmp_path / "sess")
        store.stash("/tmp/x.py", "a", "b", "write")
        bind_session(sid, store)
        action, message = dispatch("/diff show", session_id=sid, index=index, diff_config_path=cfg)
        assert action == "reply"
        assert "auto" in message
        assert "1 pending" in message

    def test_diff_bare_is_show(self, tmp_path):
        index = _fresh_index(tmp_path)
        action, message = dispatch(
            "/diff", session_id=index.mint(), index=index, diff_config_path=tmp_path / "d.yaml"
        )
        assert action == "reply"
        assert "Diff mode:" in message

    def test_diff_set_mode_persists(self, tmp_path):
        index = _fresh_index(tmp_path)
        cfg = tmp_path / "diff.yaml"
        action, message = dispatch(
            "/diff approve-each", session_id=index.mint(), index=index, diff_config_path=cfg
        )
        assert action == "reply"
        assert "approve-each" in message
        assert DiffConfig.load(cfg).mode == "approve-each"

    def test_diff_bogus_mode_usage_never_agent_turn(self, tmp_path):
        index = _fresh_index(tmp_path)
        action, message = dispatch(
            "/diff yolo", session_id=index.mint(), index=index, diff_config_path=tmp_path / "d.yaml"
        )
        assert action == "reply"
        assert "Usage" in message

    def test_search_empty_pattern_usage_never_agent_turn(self, tmp_path):
        index = _fresh_index(tmp_path)
        action, message = dispatch("/search", session_id=index.mint(), index=index, cwd=tmp_path)
        assert action == "reply"
        assert "Usage" in message

    def test_search_answers_from_repl(self, tmp_path):
        (tmp_path / "hay.py").write_text("def needle_fn():\n    pass\n")
        index = _fresh_index(tmp_path)
        action, message = dispatch(
            "/search needle_fn", session_id=index.mint(), index=index, cwd=tmp_path
        )
        assert action == "reply"
        assert "hay.py" in message

    def test_diff_survives_restart(self, tmp_path):
        cfg = tmp_path / "diff.yaml"
        DiffConfig(mode="auto").save(cfg)
        assert DiffConfig.load(cfg).mode == "auto"

    def test_usage_hint_lists_diff_and_search(self):
        assert "/diff" in USAGE_HINT
        assert "/search" in USAGE_HINT


# ---------------------------------------------------------------------------
# Diff helpers
# ---------------------------------------------------------------------------


class TestDiffHelpers:
    def test_unified_diff_markers(self):
        body = unified_diff("a\n", "b\n", "f.py")
        assert "--- " in body and "+++ " in body

    def test_split_hunks(self):
        body = unified_diff("l1\nl2\nl3\nl4\nl5\nl6\nl7\n", "L1\nl2\nl3\nl4\nl5\nl6\nL7\n", "f.py")
        hunks = split_hunks(body)
        assert len(hunks) >= 1
        assert all("@@ " in h or "--- " in h for h in hunks)


# ---------------------------------------------------------------------------
# Gate mode matrix (TOOL-02 granularity: per-hunk / whole-change / none)
# ---------------------------------------------------------------------------


class TestDiffGateModes:
    def test_approve_applies(self, tmp_path):
        files: dict = {}
        read, write = _mem_io(files)
        gated = make_gated_write(
            cwd=tmp_path, get_mode=lambda: "approve-each", ask=lambda prompt: True,
            reader=read, writer=write,
        )
        result = _run(gated(path="n.txt", content="hello\n"))
        assert "Applied" in result
        assert files[str(tmp_path / "n.txt")] == "hello\n"

    def test_deny_discards(self, tmp_path):
        files: dict = {}
        read, write = _mem_io(files)
        gated = make_gated_write(
            cwd=tmp_path, get_mode=lambda: "approve-each", ask=lambda prompt: False,
            reader=read, writer=write,
        )
        result = _run(gated(path="n.txt", content="hello\n"))
        assert "Discarded" in result
        assert files == {}

    def test_on_demand_stash_then_diff_apply(self, tmp_path):
        files: dict = {}
        read, write = _mem_io(files)
        store = PendingStore(tmp_path / "sess")
        gated = make_gated_write(
            cwd=tmp_path, get_mode=lambda: "on-demand", store=store, reader=read, writer=write,
        )
        result = _run(gated(path="n.txt", content="hello\n"))
        assert "Stashed" in result
        assert files == {}
        assert len(store.list()) == 1
        applied = _run(apply_stashed(store, reader=read, writer=write))
        assert "Applied" in applied
        assert files[str(tmp_path / "n.txt")] == "hello\n"
        assert store.list() == {}

    def test_auto_applies(self, tmp_path):
        files: dict = {}
        read, write = _mem_io(files)
        gated = make_gated_edit(
            cwd=tmp_path, get_mode=lambda: "auto", reader=read, writer=write,
        )
        files[str(tmp_path / "e.txt")] = "old line\n"
        result = _run(gated(path="e.txt", old_str="old line", new_str="new line"))
        assert "Applied" in result
        assert files[str(tmp_path / "e.txt")] == "new line\n"

    def test_stale_file_exact_once_failure(self, tmp_path):
        calls = {"n": 0}

        async def flaky_read(path):
            calls["n"] += 1
            return "v1\n" if calls["n"] == 1 else "v1-changed\n"

        written: dict = {}

        async def mem_write(path, content):
            written[path] = content

        gated = make_gated_write(
            cwd=tmp_path, get_mode=lambda: "auto", reader=flaky_read, writer=mem_write,
        )
        with pytest.raises(ValueError, match="changed since preview"):
            _run(gated(path="s.txt", content="v2\n"))
        assert written == {}

    def test_stale_stash_kept_pending(self, tmp_path):
        files = {str(tmp_path / "k.txt"): "changed\n"}
        read, write = _mem_io(files)
        store = PendingStore(tmp_path / "sess")
        store.stash(str(tmp_path / "k.txt"), "original\n", "updated\n", "write")
        result = _run(apply_stashed(store, reader=read, writer=write))
        assert "changed since preview" in result
        assert len(store.list()) == 1
        assert files[str(tmp_path / "k.txt")] == "changed\n"

    def test_scope_refusal_in_gate(self, tmp_path):
        gated = make_gated_write(cwd=tmp_path, get_mode=lambda: "auto")
        with pytest.raises(ValueError, match="allowed roots"):
            _run(gated(path="/etc/evil.txt", content="x"))

    def test_wrapper_name_collision(self):
        assert getattr(make_gated_write(cwd="/tmp"), "tool_name", "") == "write"
        assert getattr(make_gated_edit(cwd="/tmp"), "tool_name", "") == "edit"

    def test_diff_apply_no_pending(self, tmp_path):
        store = PendingStore(tmp_path / "sess")
        assert "No pending changes." in _run(apply_stashed(store))

    def test_bound_store_round_trip(self, tmp_path):
        store = PendingStore(tmp_path / "sess")
        bind_session("sid-1", store)
        assert store_for("sid-1") is store

    def test_gate_docstring_documents_shell_bypass(self):
        assert "sed -i" in diff_gate.__doc__


# ---------------------------------------------------------------------------
# Rendering: diff + search display inside output_context (callback handler)
# ---------------------------------------------------------------------------


def _rendered_output(handler, message):
    handler.console = Console(record=True, width=120)
    handler(message=message)
    return handler.console.export_text()


class TestDiffRendering:
    def test_edit_renders_unified_diff_markers(self):
        handler = CodeAgentCallbackHandler()
        out = _rendered_output(
            handler,
            {"role": "assistant", "content": [{"toolUse": {
                "name": "edit",
                "input": {"path": "/tmp/a.py", "old_str": "x = 1", "new_str": "x = 2"},
            }}]},
        )
        assert "+++" in out and "---" in out

    def test_write_renders_diff_markers(self):
        handler = CodeAgentCallbackHandler()
        out = _rendered_output(
            handler,
            {"role": "assistant", "content": [{"toolUse": {
                "name": "write",
                "input": {"path": "/tmp/b.py", "content": "print(1)\n"},
            }}]},
        )
        assert "+++" in out and "---" in out

    def test_search_renders_pattern(self):
        handler = CodeAgentCallbackHandler()
        out = _rendered_output(
            handler,
            {"role": "assistant", "content": [{"toolUse": {
                "name": "search",
                "input": {"pattern": "needle_fn", "path": "/tmp"},
            }}]},
        )
        assert "needle_fn" in out

    def test_search_result_hits_keep_path_line_prefixes(self):
        handler = CodeAgentCallbackHandler()
        out = _rendered_output(
            handler,
            {"role": "assistant", "content": [{"toolResult": {
                "status": "success",
                "content": [{"text": "/tmp/hay.py:3:def needle_fn():"}],
            }}]},
        )
        assert "/tmp/hay.py:3:" in out

    def test_unknown_tool_falls_through(self):
        handler = CodeAgentCallbackHandler()
        out = _rendered_output(
            handler,
            {"role": "assistant", "content": [{"toolUse": {
                "name": "mystery", "input": {"foo": "bar"},
            }}]},
        )
        assert "foo" in out and "bar" in out
