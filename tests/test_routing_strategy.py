"""Strategy file load/merge tests (MODEL-03 tracer).

Covers the strategy-file aspect of routing: fail-soft load, per-entry
warn-and-skip, repo-wins precedence, symlink refusal.
"""

from __future__ import annotations

import pytest

from strands_code_cli.routing import (
    RoutingCandidate,
    load_strategy,
)


def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def _strategy_yaml(candidates="[{id: a/1}]", extra=""):
    return (
        f"candidates: {candidates}\n"
        "directives: trivial asks go cheap\n"
        "engine: {primary: openrouter, decision_model: cheap/decider}\n"
        f"{extra}"
    )


class TestStrategyLoad:
    def test_missing_pair_yields_none(self, tmp_path):
        assert (
            load_strategy(
                global_path=tmp_path / "nope-global.yaml",
                repo_path=tmp_path / "nope-repo.yaml",
            )
            is None
        )

    def test_valid_global_loads(self, tmp_path):
        path = _write(tmp_path / "routing.yaml", _strategy_yaml())
        strategy = load_strategy(global_path=path, repo_path=tmp_path / "absent.yaml")
        assert strategy is not None
        assert [c.id for c in strategy.candidates] == ["a/1"]
        assert strategy.directives == "trivial asks go cheap"
        assert strategy.engine.decision_model == "cheap/decider"
        assert strategy.quiet is False
        assert strategy.source == path

    def test_corrupt_yaml_warns_and_yields_none(self, tmp_path):
        path = _write(tmp_path / "routing.yaml", "candidates: [unclosed\n")
        assert (
            load_strategy(global_path=path, repo_path=tmp_path / "absent.yaml") is None
        )

    def test_non_mapping_yaml_yields_none(self, tmp_path):
        path = _write(tmp_path / "routing.yaml", "- just\n- a\n- list\n")
        assert (
            load_strategy(global_path=path, repo_path=tmp_path / "absent.yaml") is None
        )

    def test_unknown_top_level_keys_warn_and_default(self, tmp_path):
        path = _write(
            tmp_path / "routing.yaml",
            _strategy_yaml(extra="mystery: 42\n"),
        )
        strategy = load_strategy(global_path=path, repo_path=tmp_path / "absent.yaml")
        assert strategy is not None
        assert [c.id for c in strategy.candidates] == ["a/1"]

    def test_entry_with_unknown_keys_skips_only_that_entry(self, tmp_path):
        path = _write(
            tmp_path / "routing.yaml",
            _strategy_yaml(
                candidates=(
                    "\n"
                    "  - {id: good/1, levels: [low, high], tier: small,"
                    " benchmarks: {swe_verified: 70, pulled: '2026-10-01'}}\n"
                    "  - {id: bad/1, bogus: true}\n"
                    "  - {tier: missing-id}\n"
                )
            ),
        )
        strategy = load_strategy(global_path=path, repo_path=tmp_path / "absent.yaml")
        assert strategy is not None
        assert strategy.candidates == [
            RoutingCandidate(
                id="good/1",
                tier="small",
                levels=["low", "high"],
                benchmarks={"swe_verified": 70, "pulled": "2026-10-01"},
            )
        ]

    def test_repo_content_wins_whole_file_over_global(self, tmp_path):
        home = _write(
            tmp_path / "global.yaml",
            _strategy_yaml(candidates="[{id: global/1}]", extra="quiet: true\n"),
        )
        repo = _write(
            tmp_path / "repo.yaml",
            _strategy_yaml(candidates="[{id: repo/1}]"),
        )
        strategy = load_strategy(global_path=home, repo_path=repo)
        assert strategy is not None
        assert [c.id for c in strategy.candidates] == ["repo/1"]
        assert strategy.quiet is False  # whole-file: no field merge with global
        assert strategy.source == repo

    def test_corrupt_repo_falls_back_to_global(self, tmp_path):
        home = _write(tmp_path / "global.yaml", _strategy_yaml())
        repo = _write(tmp_path / "repo.yaml", "candidates: [unclosed\n")
        strategy = load_strategy(global_path=home, repo_path=repo)
        assert strategy is not None
        assert [c.id for c in strategy.candidates] == ["a/1"]

    def test_symlinked_path_raises_value_error(self, tmp_path):
        target = _write(tmp_path / "real.yaml", _strategy_yaml())
        link = tmp_path / "link.yaml"
        link.symlink_to(target)
        with pytest.raises(ValueError, match="symlink"):
            load_strategy(global_path=link, repo_path=tmp_path / "absent.yaml")
        with pytest.raises(ValueError, match="symlink"):
            load_strategy(global_path=tmp_path / "absent.yaml", repo_path=link)

    def test_empty_candidates_means_routing_off_shape(self, tmp_path):
        path = _write(
            tmp_path / "routing.yaml",
            "directives: nothing to choose\n",
        )
        strategy = load_strategy(global_path=path, repo_path=tmp_path / "absent.yaml")
        assert strategy is not None
        assert strategy.candidates == []
