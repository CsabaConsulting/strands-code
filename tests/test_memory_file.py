"""Dual memory-file contract: load, inject, reload, modes (SKILL-02).

Injector seam (observed in the installed source): ``from
strands.vended_plugins.context_injector import ContextInjector`` —
``ContextInjector(render, trigger="userTurn").init_agent(agent)``
registers render on the agent's ``InvokeModelStage.Input`` middleware;
render is called as ``render(context)`` and may be sync. No live model
and no network is touched here; fixtures are tmp_path-built files.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from strands_code_cli.loop import flush_memory
from strands_code_cli.memory_file import (
    AGENT_MEMORY,
    MEMORY_FRONTMATTER_DEFAULTS,
    MEMORY_INJECT_CAP,
    MEMORY_PRECEDENCE_LINE,
    MEMORY_RELOAD_NOTE,
    MEMORY_TRUNCATION_MARKER,
    MEMORY_UNTRUSTED_PREFIX,
    ROOT_MEMORY,
    MemorySnapshot,
    dump_memory_file,
    load_memory,
    memory_banner,
    parse_memory_file,
    register_memory_plugin,
    render_memory_block,
    sweep_memory_files,
)


def _write(path: Path, text: str) -> Path:
    """Write a raw memory fixture, creating parents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


ROOT_BODY = "<!-- updated: 2026-10-01 -->\n## Build\nRun uv build.\n"
AGENT_BODY = "<!-- updated: 2026-10-02 -->\n## Test\nRun uv pytest.\n"


def _with_frontmatter(frontmatter: str, body: str) -> str:
    return f"---\n{frontmatter}---\n{body}"


# ----------------------------------------------------------------------
# Contract: dual load + inject + save
# ----------------------------------------------------------------------


class TestMemoryFileContract:
    def test_paths_are_the_d04_contract(self):
        assert ROOT_MEMORY == Path("STRANDS.md")
        assert AGENT_MEMORY == Path(".agent/MEMORY.md")

    def test_dual_load_injects_root_before_agent_with_precedence(self, tmp_path):
        root = _write(
            tmp_path / "STRANDS.md",
            _with_frontmatter("scope: repo\nversion: 1\nupdated: 2026-10-01\n", ROOT_BODY),
        )
        agent = _write(
            tmp_path / ".agent" / "MEMORY.md",
            _with_frontmatter(
                "scope: repo\nversion: 1\nupdated: 2026-10-02\nsource: manual\n", AGENT_BODY
            ),
        )
        snapshot = load_memory(root, agent)
        assert snapshot.missing == []
        block = render_memory_block(snapshot)
        assert block is not None
        assert block.startswith(MEMORY_UNTRUSTED_PREFIX)
        assert "<system-reminder>" in block
        assert block.index("Run uv build.") < block.index("Run uv pytest.")
        assert MEMORY_PRECEDENCE_LINE in block
        assert "On conflict, .agent/MEMORY.md wins." in block
        assert "scope: repo" not in block  # frontmatter stripped before injection

    def test_frontmatter_round_trip_preserves_source_on_agent_only(self, tmp_path):
        root = tmp_path / "STRANDS.md"
        agent = tmp_path / ".agent" / "MEMORY.md"
        root_fm = dict(MEMORY_FRONTMATTER_DEFAULTS)
        agent_fm = dict(MEMORY_FRONTMATTER_DEFAULTS, source="manual")
        dump_memory_file(root, root_fm, ROOT_BODY)
        dump_memory_file(agent, agent_fm, AGENT_BODY)
        root_fm_back, root_body_back = parse_memory_file(root)
        agent_fm_back, agent_body_back = parse_memory_file(agent)
        assert root_fm_back["scope"] == "repo"
        assert root_fm_back["version"] == 1
        assert root_fm_back["updated"] == MEMORY_FRONTMATTER_DEFAULTS["updated"]
        assert "source" not in root_fm_back
        assert agent_fm_back["source"] == "manual"
        assert root_body_back == ROOT_BODY
        assert agent_body_back == AGENT_BODY
        # Section markers round-trip through save + load untouched.
        assert "<!-- updated: 2026-10-01 -->" in root_body_back
        assert "<!-- updated: 2026-10-02 -->" in agent_body_back

    def test_agent_file_gets_0600_root_keeps_repo_perms(self, tmp_path):
        root = tmp_path / "STRANDS.md"
        agent = tmp_path / ".agent" / "MEMORY.md"
        dump_memory_file(root, dict(MEMORY_FRONTMATTER_DEFAULTS), ROOT_BODY)
        dump_memory_file(agent, dict(MEMORY_FRONTMATTER_DEFAULTS), AGENT_BODY)
        assert stat.S_IMODE(os.stat(agent).st_mode) == 0o600
        assert stat.S_IMODE(os.stat(root).st_mode) != 0o600

    def test_corrupt_frontmatter_falls_back_without_raising(self, tmp_path):
        raw = "---\n{unclosed: [oops\n---\nBody survives.\n"
        path = _write(tmp_path / "STRANDS.md", raw)
        frontmatter, body = parse_memory_file(path)
        assert frontmatter == {}
        assert body == raw
        snapshot = load_memory(path, tmp_path / ".agent" / "MEMORY.md")
        assert "Body survives." in snapshot.root_text
        assert snapshot.missing == [str(tmp_path / ".agent" / "MEMORY.md")]

    def test_oversized_content_ends_with_truncation_marker(self):
        snapshot = MemorySnapshot(root_text="x" * (MEMORY_INJECT_CAP + 500), agent_text="")
        block = render_memory_block(snapshot)
        assert block is not None
        assert block.endswith(MEMORY_TRUNCATION_MARKER)

    def test_empty_snapshot_renders_no_block(self):
        assert render_memory_block(MemorySnapshot(root_text="", agent_text="")) is None

    def test_symlinked_memory_root_raises_value_error(self, tmp_path):
        real = _write(tmp_path / "real.md", "Body.\n")
        link = tmp_path / "STRANDS.md"
        link.symlink_to(real)
        with pytest.raises(ValueError):
            parse_memory_file(link)
        with pytest.raises(ValueError):
            load_memory(link, tmp_path / ".agent" / "MEMORY.md")
        with pytest.raises(ValueError):
            dump_memory_file(link, dict(MEMORY_FRONTMATTER_DEFAULTS), "new\n")

    def test_dump_is_atomic_with_no_tmp_left_behind(self, tmp_path):
        path = tmp_path / "STRANDS.md"
        dump_memory_file(path, dict(MEMORY_FRONTMATTER_DEFAULTS), ROOT_BODY)
        assert "Run uv build." in path.read_text(encoding="utf-8")
        assert list(tmp_path.glob("*.tmp")) == []
        assert list(tmp_path.glob("*.tmp.*")) == []

    def test_register_twice_registers_exactly_once(self):
        calls: list = []
        stub = SimpleNamespace(
            _middleware_registry=SimpleNamespace(
                add_middleware=lambda *args: calls.append(args)
            )
        )
        loader_calls: list = []

        def loader():
            loader_calls.append(1)
            return MemorySnapshot(root_text="r", agent_text="a")

        first = register_memory_plugin(stub, loader)
        second = register_memory_plugin(stub, loader)
        assert len(calls) == 1
        assert second is first
        assert stub._memory_plugin_registered is True


# ----------------------------------------------------------------------
# Reload: external-edit sweep + banner + flush (no live loop)
# ----------------------------------------------------------------------


class TestMemoryReload:
    def test_sweep_detects_touched_file_only(self, tmp_path):
        root = _write(tmp_path / "STRANDS.md", ROOT_BODY)
        agent = _write(tmp_path / ".agent" / "MEMORY.md", AGENT_BODY)
        snapshot = load_memory(root, agent)
        assert sweep_memory_files(snapshot, paths=(root, agent)) == []
        stamp = root.stat().st_mtime + 100
        os.utime(root, (stamp, stamp))
        assert sweep_memory_files(snapshot, paths=(root, agent)) == [root]

    def test_sweep_counts_presence_flips_as_changed(self, tmp_path):
        root = _write(tmp_path / "STRANDS.md", ROOT_BODY)
        agent = tmp_path / ".agent" / "MEMORY.md"
        snapshot = load_memory(root, agent)
        assert sweep_memory_files(snapshot, paths=(root, agent)) == []
        _write(agent, AGENT_BODY)  # missing-to-present
        assert sweep_memory_files(snapshot, paths=(root, agent)) == [agent]
        reloaded = load_memory(root, agent)
        root.unlink()  # present-to-missing
        assert sweep_memory_files(reloaded, paths=(root, agent)) == [root]

    def test_reload_note_format(self):
        assert (
            MEMORY_RELOAD_NOTE.format(filename="STRANDS.md")
            == "Memory reloaded — STRANDS.md changed on disk."
        )

    def test_banner_names_both_files_with_missing_pointer(self, tmp_path):
        root = _write(tmp_path / "STRANDS.md", ROOT_BODY)
        agent = tmp_path / ".agent" / "MEMORY.md"
        snapshot = load_memory(root, agent)
        banner = memory_banner(snapshot, paths=(root, agent))
        assert "STRANDS.md" in banner
        assert "MEMORY.md" in banner
        assert "run /init to scaffold" in banner

    def test_flush_awaits_manager_flush_exactly_once(self):
        calls: list = []

        async def fake_flush():
            calls.append(1)

        flush_memory(SimpleNamespace(memory_manager=SimpleNamespace(flush=fake_flush)))
        assert len(calls) == 1

    def test_flush_with_flush_less_double_returns_silently(self):
        flush_memory(SimpleNamespace())
        flush_memory(SimpleNamespace(memory_manager=SimpleNamespace()))
        flush_memory(object())

    def test_loop_calls_flush_on_exit_and_mutation_paths(self):
        source = (
            Path(__file__).resolve().parent.parent
            / "strands_code_cli"
            / "loop.py"
        ).read_text(encoding="utf-8")
        assert source.count("flush_memory(agent)") == 2
