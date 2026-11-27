"""Diff-gate contracts: mode store, wrapper gate matrix, rendering (TOOL-02, D-04)."""

from __future__ import annotations

import asyncio

import pytest
from rich.console import Console

import strands_code_cli.policy.diff_gate as diff_gate
from strands_code_agent.callback_handler import CodeAgentCallbackHandler
from strands_code_cli.dispatch.core import USAGE_HINT, dispatch
from strands_code_cli.entry.provider_config import ProviderConfig
from strands_code_cli.policy.diff_gate import (
    DEFAULT_MODE,
    DiffModeState,
    PendingStore,
    apply_stashed,
    bind_session,
    make_gated_edit,
    make_gated_write,
    split_hunks,
    store_for,
    unified_diff,
)
from strands_code_cli.session.session_index import SessionIndex


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
# DiffModeState & session-scoped PendingStore
# ---------------------------------------------------------------------------


class TestDiffModeState:
    def test_default_mode_on_demand_and_sticky_switch(self):
        holder = DiffModeState()
        assert holder.mode == DEFAULT_MODE == "on-demand"
        assert holder.announce() == "Diff mode: on-demand."
        assert holder.set("auto") == "Diff mode set to auto."
        assert holder.mode == "auto"
        assert holder.set("auto") == "Diff mode unchanged (auto)."

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="on-demand"):
            DiffModeState(initial="approve-each")
        with pytest.raises(ValueError, match="on-demand"):
            DiffModeState().set("yolo")


class TestSessionScopedPendingStore:
    def test_stores_are_isolated_per_session_id(self, tmp_path):
        s_a = PendingStore(tmp_path, session_id="sess-a")
        s_b = PendingStore(tmp_path, session_id="sess-b")
        s_a.stash("/tmp/a.py", "1", "2", "write")
        assert (tmp_path / "pending-sess-a.json").exists()
        assert s_b.list() == {}

    def test_invalid_session_id_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="pending-store"):
            PendingStore(tmp_path, session_id="../escape")


# ---------------------------------------------------------------------------
# Router: /diff + /search dispatch (reply only, never an agent turn)
# ---------------------------------------------------------------------------


class TestDiffRouter:
    def test_diff_bare_lists_mode_and_pending_files(self, tmp_path):
        index = _fresh_index(tmp_path)
        sid = index.mint()
        store = PendingStore(tmp_path / "sess", session_id=sid)
        store.stash("/tmp/x.py", "a\n", "b\n", "write")
        bind_session(sid, store)
        holder = DiffModeState(initial="auto")
        action, message = dispatch(
            "/diff", session_id=sid, index=index, diff_mode=holder
        )
        assert action == "reply"
        assert "Diff mode: auto (1 pending)." in message
        assert "write: /tmp/x.py" in message
        assert "--- a/" not in message

    def test_diff_show_and_uppercase_render_unified_diff(self, tmp_path):
        index = _fresh_index(tmp_path)
        sid = index.mint()
        store = PendingStore(tmp_path / "sess", session_id=sid)
        store.stash("/tmp/x.py", "a\n", "\x1b[31mb\x1b[0m\n", "write")
        bind_session(sid, store)
        for cmd in ("/diff show", "/diff SHOW", "/diff show /tmp/x.py"):
            action, message = dispatch(cmd, session_id=sid, index=index)
            assert action == "reply"
            assert "--- a//tmp/x.py" in message
            assert "+++ b//tmp/x.py" in message
            assert "-a" in message and "+b" in message
            assert "\x1b[" not in message

        action_miss, msg_miss = dispatch(
            "/diff show /tmp/nope.py", session_id=sid, index=index
        )
        assert action_miss == "reply"
        assert "No pending change to /tmp/nope.py." == msg_miss

    def test_diff_set_mode_session_sticky_and_config_yaml_persists(
        self, tmp_path, monkeypatch
    ):
        import strands_code_cli.entry.provider_config as provider_config_module

        cfg = tmp_path / "config.yaml"
        monkeypatch.setattr(provider_config_module, "default_config_path", lambda: cfg)
        index = _fresh_index(tmp_path)
        holder = DiffModeState()
        action, message = dispatch(
            "/diff auto", session_id=index.mint(), index=index, diff_mode=holder
        )
        assert action == "reply"
        assert message == "Diff mode set to auto."
        assert holder.mode == "auto"
        assert not cfg.exists()

        ProviderConfig(diff_mode="auto").save(cfg)
        assert ProviderConfig.load(cfg).diff_mode == "auto"

    def test_diff_bogus_and_retired_mode_usage(self, tmp_path):
        index = _fresh_index(tmp_path)
        for bad in ("yolo", "approve-each"):
            action, message = dispatch(
                f"/diff {bad}", session_id=index.mint(), index=index
            )
            assert action == "reply"
            assert "Usage" in message

    def test_search_empty_pattern_usage_never_agent_turn(self, tmp_path):
        index = _fresh_index(tmp_path)
        action, message = dispatch(
            "/search", session_id=index.mint(), index=index, cwd=tmp_path
        )
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
        body = unified_diff(
            "l1\nl2\nl3\nl4\nl5\nl6\nl7\n", "L1\nl2\nl3\nl4\nl5\nl6\nL7\n", "f.py"
        )
        hunks = split_hunks(body)
        assert len(hunks) >= 1
        assert all("@@ " in h or "--- " in h for h in hunks)


# ---------------------------------------------------------------------------
# Gate mode matrix (TOOL-02 granularity: per-hunk / whole-change / none)
# ---------------------------------------------------------------------------


class TestDiffGateModes:
    def test_auto_mode_applies_without_prompt(self, tmp_path):
        files: dict = {}
        read, write = _mem_io(files)
        gated = make_gated_write(
            cwd=tmp_path,
            get_mode=lambda: "auto",
            reader=read,
            writer=write,
        )
        result = _run(gated(path="n.txt", content="hello\n"))
        assert "Applied" in result
        assert files[str(tmp_path / "n.txt")] == "hello\n"

    def test_unknown_mode_falls_back_to_on_demand(self, tmp_path):
        files: dict = {}
        read, write = _mem_io(files)
        store = PendingStore(tmp_path / "sess")
        gated = make_gated_write(
            cwd=tmp_path,
            get_mode=lambda: "approve-each",
            store=store,
            reader=read,
            writer=write,
        )
        result = _run(gated(path="n.txt", content="hello\n"))
        assert "Stashed" in result
        assert files == {}

    def test_on_demand_stash_then_diff_apply(self, tmp_path):
        files: dict = {}
        read, write = _mem_io(files)
        store = PendingStore(tmp_path / "sess")
        gated = make_gated_write(
            cwd=tmp_path,
            get_mode=lambda: "on-demand",
            store=store,
            reader=read,
            writer=write,
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
            cwd=tmp_path,
            get_mode=lambda: "auto",
            reader=read,
            writer=write,
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
            cwd=tmp_path,
            get_mode=lambda: "auto",
            reader=flaky_read,
            writer=mem_write,
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
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "name": "edit",
                            "input": {
                                "path": "/tmp/a.py",
                                "old_str": "x = 1",
                                "new_str": "x = 2",
                            },
                        }
                    }
                ],
            },
        )
        assert "+++" in out and "---" in out

    def test_write_renders_diff_markers(self):
        handler = CodeAgentCallbackHandler()
        out = _rendered_output(
            handler,
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "name": "write",
                            "input": {"path": "/tmp/b.py", "content": "print(1)\n"},
                        }
                    }
                ],
            },
        )
        assert "+++" in out and "---" in out

    def test_search_renders_pattern(self):
        handler = CodeAgentCallbackHandler()
        out = _rendered_output(
            handler,
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "name": "search",
                            "input": {"pattern": "needle_fn", "path": "/tmp"},
                        }
                    }
                ],
            },
        )
        assert "needle_fn" in out

    def test_search_result_hits_keep_path_line_prefixes(self):
        handler = CodeAgentCallbackHandler()
        out = _rendered_output(
            handler,
            {
                "role": "assistant",
                "content": [
                    {
                        "toolResult": {
                            "status": "success",
                            "content": [{"text": "/tmp/hay.py:3:def needle_fn():"}],
                        }
                    }
                ],
            },
        )
        assert "/tmp/hay.py:3:" in out

    def test_unknown_tool_falls_through(self):
        handler = CodeAgentCallbackHandler()
        out = _rendered_output(
            handler,
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "name": "mystery",
                            "input": {"foo": "bar"},
                        }
                    }
                ],
            },
        )
        assert "foo" in out and "bar" in out


# ---------------------------------------------------------------------------
# Gate subsumption (Phase 3 D-10: one prompt total per write)
# ---------------------------------------------------------------------------


class TestGateSubsumption:
    def _two_hunk_files(self, tmp_path):
        old = "".join(f"line{i}\n" for i in range(1, 21))
        new = old.replace("line3\n", "CHANGED3\n").replace("line17\n", "CHANGED17\n")
        assert len(split_hunks(unified_diff(old, new, "m.txt"))) == 2
        return old, new

    def test_gate_active_skips_wrapper_ask(self, tmp_path):
        files: dict = {}
        read, write = _mem_io(files)
        old, new = self._two_hunk_files(tmp_path)
        files[str(tmp_path / "m.txt")] = old
        calls = {"n": 0}

        def fail_ask(prompt):
            calls["n"] += 1
            raise AssertionError("auto wrapper must not ask per hunk")

        gated = make_gated_write(
            cwd=tmp_path,
            get_mode=lambda: "auto",
            ask=fail_ask,
            reader=read,
            writer=write,
            gate_active=True,
        )
        result = _run(gated(path="m.txt", content=new))
        assert "Applied" in result
        assert calls["n"] == 0

    def test_one_prompt_total_with_gate(self, tmp_path):
        """Gate ask (1, answered y) + gate-active wrapper (0) == 1 total."""
        from strands_code_cli.policy.core import PolicyConfig
        from strands_code_cli.policy.policy_gate import PolicyGateHandler

        files: dict = {}
        read, write = _mem_io(files)
        gate_prompts = {"n": 0}

        handler = PolicyGateHandler(policy_loader=PolicyConfig.load)
        import builtins

        real_input = builtins.input
        builtins.input = lambda *args: (
            gate_prompts.__setitem__("n", gate_prompts["n"] + 1),
            "y",
        )[1]
        try:
            import asyncio
            from types import SimpleNamespace

            class _Agent:
                state: dict = {}

            action = asyncio.run(
                handler.before_tool_call(
                    SimpleNamespace(
                        agent=_Agent(),
                        tool_use={
                            "name": "write",
                            "input": {"path": "n.txt"},
                            "toolUseId": "w1",
                        },
                    )
                )
            )
        finally:
            builtins.input = real_input
        from strands.interventions.actions import Proceed

        assert isinstance(action, Proceed)

        def fail_ask(prompt):
            raise AssertionError("wrapper must not re-prompt under gate_active")

        gated = make_gated_write(
            cwd=tmp_path,
            get_mode=lambda: "auto",
            ask=fail_ask,
            reader=read,
            writer=write,
            gate_active=True,
        )
        result = _run(gated(path="n.txt", content="hello\n"))
        assert "Applied" in result
        assert gate_prompts["n"] == 1

    def test_on_demand_apply_never_reprompts(self, tmp_path):
        files: dict = {}
        read, write = _mem_io(files)
        store = PendingStore(tmp_path / "sess")
        gated = make_gated_write(
            cwd=tmp_path,
            get_mode=lambda: "on-demand",
            store=store,
            reader=read,
            writer=write,
            gate_active=True,
        )
        assert "Stashed" in _run(gated(path="n.txt", content="hello\n"))
        applied = _run(apply_stashed(store, reader=read, writer=write))
        assert "Applied" in applied

    def test_read_allow_rule_does_not_widen_write_or_edit_roots(
        self, tmp_path, monkeypatch
    ):
        from pathlib import Path

        from strands_code_cli.policy.core import PolicyConfig, Rule

        outside = Path("/opt/outside-read-only")
        monkeypatch.setattr(
            PolicyConfig,
            "load",
            classmethod(
                lambda cls: cls(allow=[Rule(tool="read", path=str(outside / "*"))])
            ),
        )
        gated_write = make_gated_write(cwd=tmp_path, get_mode=lambda: "auto")
        gated_edit = make_gated_edit(cwd=tmp_path, get_mode=lambda: "auto")
        with pytest.raises(ValueError, match="allowed roots"):
            _run(gated_write(path=str(outside / "pwn.txt"), content="x"))
        with pytest.raises(ValueError, match="allowed roots"):
            _run(gated_edit(path=str(outside / "pwn.txt"), old_str="a", new_str="b"))

    def test_apply_stashed_enforces_scope_symlink_protected_and_null_toctou(
        self, tmp_path
    ):
        store = PendingStore(tmp_path / "pending")
        # 1. Outside scope target kept pending and not written:
        store.stash("/opt/evil/pwn.txt", None, "bad", "write")
        # 2. Protected repo path kept pending:
        repo = tmp_path / "repo"
        (repo / ".agent").mkdir(parents=True)
        prot = repo / ".agent" / "policy.toml"
        store.stash(str(prot), None, "allow = []", "write")
        # 3. Symlinked target kept pending:
        secret = tmp_path / "secret.txt"
        secret.write_text("keep")
        sym = repo / "link.txt"
        sym.symlink_to(secret)
        store.stash(str(sym), None, "clobber", "write")
        # 4. TOCTOU: stashed as new file (expected None) but file appeared before apply:
        new_file = repo / "created_later.txt"
        new_file.write_text("already here")
        store.stash(str(new_file), None, "overwrite", "write")

        report = _run(apply_stashed(store, cwd=repo))
        assert "outside the allowed roots" in report
        assert "protected path cannot be auto-applied" in report
        assert "symlink" in report
        assert "changed since preview" in report
        assert secret.read_text() == "keep"
        assert new_file.read_text() == "already here"
        assert not prot.exists()
        assert len(store.list()) == 4

    def test_apply_stashed_refuses_grandparent_symlink_and_resolves_relative_against_cwd(
        self, tmp_path, monkeypatch
    ):
        import shutil

        # 1. Swapped grandparent symlink inside repo must be refused (never clobbers target).
        repo = tmp_path / "repo"
        (repo / "sub" / "deep").mkdir(parents=True)
        (repo / "other" / "deep").mkdir(parents=True)
        orig = repo / "sub" / "deep" / "app.py"
        other = repo / "other" / "deep" / "app.py"
        orig.write_text("v1", encoding="utf-8")
        other.write_text("v1", encoding="utf-8")
        store = PendingStore(repo / ".agent" / "pending.json")
        store.stash(str(orig), "v1", "PWNED", "edit")
        shutil.rmtree(repo / "sub")
        try:
            (repo / "sub").symlink_to(repo / "other")
        except OSError:
            pytest.skip("symlinks unavailable")
        res_gp = _run(apply_stashed(store, cwd=repo))
        assert "symlink" in res_gp
        assert other.read_text(encoding="utf-8") == "v1"
        assert str(orig) in store.list()

        # 2. Relative targets resolve/read/write against `cwd`, never process os.getcwd().
        wrong_cwd = tmp_path / "wrong_cwd"
        wrong_cwd.mkdir()
        monkeypatch.chdir(wrong_cwd)
        (repo / "sub_real").mkdir()
        (repo / "sub_real" / "target.txt").write_text("keep", encoding="utf-8")
        (repo / "sub_real" / "link.txt").symlink_to(repo / "sub_real" / "target.txt")

        rel_store = PendingStore(repo / ".agent" / "pending_rel.json")
        rel_store.stash("new_rel.txt", None, "inside_repo", "write")
        rel_store.stash("sub_real/link.txt", "keep", "clobber", "edit")
        res_rel = _run(apply_stashed(rel_store, cwd=repo))
        assert "Applied new_rel.txt." in res_rel
        assert (repo / "new_rel.txt").read_text(encoding="utf-8") == "inside_repo"
        assert not (wrong_cwd / "new_rel.txt").exists()
        assert "symlink" in res_rel
        assert (repo / "sub_real" / "target.txt").read_text(encoding="utf-8") == "keep"

    def test_apply_stashed_enforces_repo_deny_and_atomic_fs_write(self, tmp_path):
        from strands_code_cli.policy.diff_gate import _fs_write

        repo = tmp_path / "repo"
        (repo / ".agent").mkdir(parents=True)
        (repo / ".agent" / "policy.toml").write_text(
            '[[deny]]\ntool = "write"\npath = "*.pem"\n',
            encoding="utf-8",
        )
        store = PendingStore(repo / ".agent" / "pending_deny.json")
        store.stash(str(repo / "secret.pem"), None, "PRIVATE", "write")
        store.stash(str(repo / "notes.txt"), None, "hello\n", "write")

        report = _run(apply_stashed(store, cwd=repo))
        assert "Denied by policy rule" in report
        assert "Applied" in report
        assert not (repo / "secret.pem").exists()
        assert (repo / "notes.txt").read_text(encoding="utf-8") == "hello\n"
        assert list(store.list()) == [str(repo / "secret.pem")]

        # Direct _fs_write helper writes atomically and refuses symlink targets.
        real_target = repo / "real.txt"
        real_target.write_text("orig", encoding="utf-8")
        sym_target = repo / "sym.txt"
        try:
            sym_target.symlink_to(real_target)
        except OSError:
            pytest.skip("symlinks unavailable")
        with pytest.raises(ValueError, match="Refusing symlink"):
            _run(_fs_write(str(sym_target), "clobber"))
        assert real_target.read_text(encoding="utf-8") == "orig"

        # Symlinked repo policy fails closed in _validate_stashed_target; missing target reports.
        evil_pol = repo / "evil.toml"
        evil_pol.write_text('[[allow]]\ntool = "write"\npath = "*"\n', encoding="utf-8")
        (repo / ".agent" / "policy.toml").unlink()
        (repo / ".agent" / "policy.toml").symlink_to(evil_pol)
        store.stash(str(repo / "notes.txt"), None, "blocked", "write")
        sym_pol_res = _run(apply_stashed(store, path=str(repo / "notes.txt"), cwd=repo))
        assert "Refusing symlink" in sym_pol_res
        assert "no pending change." in _run(
            apply_stashed(store, path=str(repo / "missing.txt"), cwd=repo)
        )

    def test_diff_show_apply_discard_resolve_relative_paths_and_sanitize(
        self, tmp_path
    ):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".agent").mkdir()
        (repo / "notes.txt").write_text("old\n", encoding="utf-8")
        store = PendingStore(tmp_path / "sess", session_id="rel-s1")
        bind_session("rel-s1", store)
        store.stash(str(repo / "notes.txt"), "old\n", "new\n", "write")
        store.stash(str(repo / "drop.txt"), "a\n", "b\n", "write")
        from strands_code_cli.session.session_index import SessionIndex

        idx = SessionIndex(tmp_path / "idx")

        show_rel = dispatch(
            "/diff show notes.txt", session_id="rel-s1", index=idx, cwd=repo
        )[1]
        assert "@@" in show_rel and "+new" in show_rel

        apply_rel = dispatch(
            "/diff apply notes.txt", session_id="rel-s1", index=idx, cwd=repo
        )[1]
        assert "Applied" in apply_rel
        assert (repo / "notes.txt").read_text(encoding="utf-8") == "new\n"

        discard_rel = dispatch(
            "/diff discard drop.txt", session_id="rel-s1", index=idx, cwd=repo
        )[1]
        assert "Discarded pending change" in discard_rel
        assert str(repo / "drop.txt") not in store.list()

        miss = dispatch(
            "/diff show \x1b[31mevil\u202ename",
            session_id="rel-s1",
            index=idx,
            cwd=repo,
        )[1]
        assert "\x1b" not in miss and "\u202e" not in miss

    def test_diff_and_apply_stashed_sanitize_poisoned_op_and_path_echoes(
        self, tmp_path
    ):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".agent").mkdir()
        store = PendingStore(tmp_path / "sess", session_id="poison-s1")
        bind_session("poison-s1", store)
        target = str(repo / "a.txt")
        store.stash(target, "a", "a", "\x1b[31mevil_op\u202e")
        store.stash(str(repo / "\x1b[31mevil.txt"), None, "x", "write")
        from strands_code_cli.session.session_index import SessionIndex

        idx = SessionIndex(tmp_path / "idx")
        list_out = dispatch("/diff", session_id="poison-s1", index=idx, cwd=repo)[1]
        show_out = dispatch("/diff show", session_id="poison-s1", index=idx, cwd=repo)[
            1
        ]
        apply_out = _run(
            apply_stashed(store, path=str(repo / "\x1b[31mevil.txt"), cwd=repo)
        )
        for rendered in (list_out, show_out, apply_out):
            assert "\x1b" not in rendered and "\u202e" not in rendered
