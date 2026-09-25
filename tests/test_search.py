"""Search tool contracts: rg wrapper plus stdlib fallback (TOOL-04, D-08/D-09).

The suite never requires the ``rg`` binary: hit-shape tests pass through
whichever backend is present, and the fallback is forced by monkeypatching
``shutil.which`` to ``None``. No index files are created — every call greps
the live tree.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from strands_code_agent import search_tool
from strands_code_agent.search_tool import format_hits, run_search


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "alpha.py").write_text("def target_fn():\n    return 1\n")
    (tmp_path / "beta.py").write_text("x = 1\n" + "\n".join(f"match line {i}" for i in range(20)) + "\n")
    (tmp_path / "notes.txt").write_text("nothing relevant here\n")
    return tmp_path


class TestSearchHits:
    def test_rg_hit_shape(self, repo):
        output = run_search("target_fn", cwd=repo)
        assert output != "No matches found."
        first = output.splitlines()[0]
        assert first.startswith(f"{repo}/alpha.py:1:")
        assert "target_fn" in first

    def test_no_match_empty(self, repo):
        assert run_search("zzz_no_such_symbol_zzz", cwd=repo) == "No matches found."

    def test_symbol_navigation_on_the_fly(self, repo):
        output = run_search("def target_fn|class \\w+", cwd=repo)
        assert "alpha.py" in output

    def test_missing_rg_fallback(self, repo, monkeypatch):
        monkeypatch.setattr(search_tool.shutil, "which", lambda _: None)
        output = run_search("target_fn", cwd=repo)
        assert output.splitlines()[0].startswith(f"{repo}/alpha.py:1:")

    def test_fallback_skips_undecodable_files(self, repo, monkeypatch):
        monkeypatch.setattr(search_tool.shutil, "which", lambda _: None)
        (repo / "blob.bin").write_bytes(b"\xff\xfe\x00bad")
        assert "target_fn" in run_search("target_fn", cwd=repo)

    def test_path_out_of_scope_refused(self, repo):
        with pytest.raises(ValueError, match="allowed roots"):
            run_search("x", path="/etc", cwd=repo)

    def test_empty_pattern_refused(self, repo):
        with pytest.raises(ValueError, match="non-empty"):
            run_search("   ", cwd=repo)

    def test_limit_truncation_note(self, repo):
        output = run_search("match line", limit=5, cwd=repo)
        lines = output.splitlines()
        assert len(lines) == 6
        assert lines[-1] == "... truncated to 5 of 20 matches."

    def test_file_glob_limits_filenames(self, repo):
        output = run_search("match line", file_glob="*.txt", cwd=repo)
        assert output == "No matches found."

    def test_no_index_files_created(self, repo):
        before = {p.name for p in repo.iterdir()}
        run_search("target_fn", cwd=repo)
        assert {p.name for p in repo.iterdir()} == before

    def test_search_tool_registered_name(self):
        assert getattr(search_tool.search, "tool_name", "") == "search"

    def test_format_hits_prefixes(self, repo):
        output = run_search("target_fn", cwd=repo)
        rendered = format_hits("target_fn", output)
        assert "target_fn" in rendered
        assert f"{repo}/alpha.py" in rendered

    def test_format_hits_no_match(self):
        assert "No matches found." in format_hits("zzz", "No matches found.")
