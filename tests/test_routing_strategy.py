"""Strategy file load/merge tests (MODEL-03 tracer).

Covers the strategy-file aspect of routing: fail-soft load, per-entry
warn-and-skip, repo-wins precedence, symlink refusal.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

import pytest
import yaml

import strands_code_cli.routing as routing_mod
from strands_code_cli.router import (
    _SETUP_DONE,
    _setup_decision_entries,
    dispatch,
)
from strands_code_cli.routing import (
    RoutingCandidate,
    load_strategy,
    save_strategy,
    validate_strategy,
)
from strands_code_cli.session_index import SessionIndex


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

    def test_knobs_default_when_absent(self, tmp_path):
        path = _write(tmp_path / "routing.yaml", _strategy_yaml())
        strategy = load_strategy(global_path=path, repo_path=tmp_path / "absent.yaml")
        assert strategy is not None
        assert strategy.tie_margin == routing_mod.DEFAULT_TIE_MARGIN
        assert strategy.confidence_threshold == routing_mod.DEFAULT_CONFIDENCE_THRESHOLD

    def test_knobs_load_explicit_values(self, tmp_path):
        path = _write(
            tmp_path / "routing.yaml",
            _strategy_yaml(extra="tie_margin: 0.1\nconfidence_threshold: 0.6\n"),
        )
        strategy = load_strategy(global_path=path, repo_path=tmp_path / "absent.yaml")
        assert strategy is not None
        assert strategy.tie_margin == 0.1
        assert strategy.confidence_threshold == 0.6

    def test_knob_wrong_type_warns_and_defaults(self, tmp_path, caplog):
        import logging

        path = _write(
            tmp_path / "routing.yaml",
            _strategy_yaml(extra="tie_margin: wide\nconfidence_threshold: true\n"),
        )
        with caplog.at_level(logging.WARNING, logger="strands_code_cli.routing"):
            strategy = load_strategy(
                global_path=path, repo_path=tmp_path / "absent.yaml"
            )
        assert strategy is not None
        assert strategy.tie_margin == routing_mod.DEFAULT_TIE_MARGIN
        # YAML bools are not numbers: true must not become 1.0.
        assert strategy.confidence_threshold == (
            routing_mod.DEFAULT_CONFIDENCE_THRESHOLD
        )
        assert "tie_margin" in caplog.text
        assert "confidence_threshold" in caplog.text

    def test_knob_out_of_range_warns_and_defaults(self, tmp_path, caplog):
        import logging

        path = _write(
            tmp_path / "routing.yaml",
            _strategy_yaml(extra="tie_margin: 2.0\nconfidence_threshold: -1.0\n"),
        )
        with caplog.at_level(logging.WARNING, logger="strands_code_cli.routing"):
            strategy = load_strategy(
                global_path=path, repo_path=tmp_path / "absent.yaml"
            )
        assert strategy is not None
        assert strategy.tie_margin == routing_mod.DEFAULT_TIE_MARGIN
        assert strategy.confidence_threshold == (
            routing_mod.DEFAULT_CONFIDENCE_THRESHOLD
        )
        assert "outside 0..1" in caplog.text

    def test_criteria_loads_onto_candidate(self, tmp_path):
        path = _write(
            tmp_path / "routing.yaml",
            _strategy_yaml(candidates="[{id: a/1, criteria: 'Cheap small model'}]"),
        )
        strategy = load_strategy(global_path=path, repo_path=tmp_path / "absent.yaml")
        assert strategy is not None
        assert strategy.candidates[0].criteria == "Cheap small model"
        bare = _write(tmp_path / "bare.yaml", _strategy_yaml())
        plain = load_strategy(global_path=bare, repo_path=tmp_path / "absent.yaml")
        assert plain is not None
        assert plain.candidates[0].criteria is None

    def test_criteria_wrong_type_skips_entry(self, tmp_path):
        path = _write(
            tmp_path / "routing.yaml",
            _strategy_yaml(candidates="[{id: a/1, criteria: [not, prose]}]"),
        )
        strategy = load_strategy(global_path=path, repo_path=tmp_path / "absent.yaml")
        assert strategy is not None
        assert strategy.candidates == []

    def test_save_round_trips_new_keys(self, tmp_path):
        data = {
            "candidates": [{"id": "a/1", "criteria": "Cheap small model"}],
            "directives": "d",
            "tie_margin": 0.1,
            "confidence_threshold": 0.6,
            "engine": {"primary": "openrouter", "decision_model": "c/d"},
        }
        path = save_strategy(data, "repo", repo_path=tmp_path / "r.yaml")
        strategy = load_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert strategy is not None
        assert strategy.tie_margin == 0.1
        assert strategy.confidence_threshold == 0.6
        assert strategy.candidates[0].criteria == "Cheap small model"

    def test_ordered_engines_load(self, tmp_path):
        path = _write(
            tmp_path / "routing.yaml",
            "candidates: [{id: a/1}]\n"
            "directives: d\n"
            "engine: {order: [native, openrouter], native_model: jev-1.13.0,"
            " decision_model: cheap/decider, skip_notes: false}\n",
        )
        strategy = load_strategy(global_path=path, repo_path=tmp_path / "absent.yaml")
        assert strategy is not None
        assert strategy.engine.order == ["native", "openrouter"]
        assert strategy.engine.native_model == "jev-1.13.0"
        assert strategy.engine.skip_notes is False

    def test_order_defaults_when_absent(self, tmp_path):
        path = _write(tmp_path / "routing.yaml", _strategy_yaml())
        strategy = load_strategy(global_path=path, repo_path=tmp_path / "absent.yaml")
        assert strategy is not None
        assert strategy.engine.order is None
        assert strategy.engine.native_model is None
        assert strategy.engine.skip_notes is True

    def test_order_dedups_and_drops_unknown(self, tmp_path, caplog):
        import logging

        path = _write(
            tmp_path / "routing.yaml",
            "candidates: [{id: a/1}]\n"
            "directives: d\n"
            "engine: {order: [native, bogus, native, openrouter]}\n",
        )
        with caplog.at_level(logging.WARNING, logger="strands_code_cli.routing"):
            strategy = load_strategy(
                global_path=path, repo_path=tmp_path / "absent.yaml"
            )
        assert strategy is not None
        assert strategy.engine.order == ["native", "openrouter"]
        assert "bogus" in caplog.text

    def test_order_wrong_type_warns_and_defaults(self, tmp_path, caplog):
        import logging

        path = _write(
            tmp_path / "routing.yaml",
            "candidates: [{id: a/1}]\n"
            "directives: d\n"
            "engine: {primary: local, order: native}\n",
        )
        with caplog.at_level(logging.WARNING, logger="strands_code_cli.routing"):
            strategy = load_strategy(
                global_path=path, repo_path=tmp_path / "absent.yaml"
            )
        assert strategy is not None
        assert strategy.engine.order is None  # legacy primary mapping wins
        assert "'order' (not a list)" in caplog.text

    def test_native_model_wrong_type_warns_and_defaults(self, tmp_path, caplog):
        import logging

        path = _write(
            tmp_path / "routing.yaml",
            "candidates: [{id: a/1}]\n"
            "directives: d\n"
            "engine: {order: [native], native_model: 42}\n",
        )
        with caplog.at_level(logging.WARNING, logger="strands_code_cli.routing"):
            strategy = load_strategy(
                global_path=path, repo_path=tmp_path / "absent.yaml"
            )
        assert strategy is not None
        assert strategy.engine.native_model is None
        assert "'native_model' (not a string)" in caplog.text

    def test_skip_notes_wrong_type_warns_and_defaults_true(self, tmp_path, caplog):
        import logging

        path = _write(
            tmp_path / "routing.yaml",
            "candidates: [{id: a/1}]\n"
            "directives: d\n"
            "engine: {order: [native], skip_notes: sometimes}\n",
        )
        with caplog.at_level(logging.WARNING, logger="strands_code_cli.routing"):
            strategy = load_strategy(
                global_path=path, repo_path=tmp_path / "absent.yaml"
            )
        assert strategy is not None
        assert strategy.engine.skip_notes is True
        assert "'skip_notes' (not true/false)" in caplog.text


_SETUP_CATALOG = [
    {
        "id": "good/cheap",
        "context_length": 32000,
        "pricing": {"prompt": "0.00000010", "completion": "0.00000020"},
        "architecture": {
            "input_modalities": ["text"],
            "output_modalities": ["text"],
        },
        "supported_parameters": ["temperature", "response_format"],
    },
    {
        "id": "good/pricey",
        "context_length": 200000,
        "pricing": {"prompt": "0.00000300", "completion": "0.00001500"},
        "architecture": {
            "input_modalities": ["text"],
            "output_modalities": ["text"],
        },
        "supported_parameters": ["temperature"],
    },
    {
        "id": "good/unpriced",
        "context_length": 64000,
        "architecture": {
            "input_modalities": ["text"],
            "output_modalities": ["text"],
        },
        "supported_parameters": ["structured_outputs"],
    },
    {"id": "vendor/embed-large", "pricing": {"prompt": "0", "completion": "0"}},
    {"id": "vendor/rerank-pro", "pricing": {"prompt": "0", "completion": "0"}},
    {"id": "broken/entry", "pricing": {"prompt": "n/a"}},
    "not-a-dict",
    {"id": ""},
]
"""Fixture /models payload: priced, unpriced, non-chat, and malformed rows."""


def _setup_paths(monkeypatch, tmp_path):
    """Point both strategy defaults at tmp files; return (repo, global)."""
    repo = tmp_path / "repo" / ".agent" / "routing.yaml"
    glob = tmp_path / "home" / "routing.yaml"
    monkeypatch.setattr(routing_mod, "default_repo_strategy_path", lambda: repo)
    monkeypatch.setattr(routing_mod, "default_global_strategy_path", lambda: glob)
    return (repo, glob)


def _scripted_radio(monkeypatch, picks):
    """Serve scripted radio picks; return the (title, options) call log."""
    import strands_code_cli.choice as choice_mod

    calls: list = []
    queue = list(picks)

    def _fake(title, options, default=0):
        calls.append((title, list(options)))
        return queue.pop(0)

    monkeypatch.setattr(choice_mod, "radio_choice", _fake)
    return calls


def _scripted_input(monkeypatch, lines):
    """Serve scripted input() lines in order."""
    queue = list(lines)
    monkeypatch.setattr("builtins.input", lambda *args: queue.pop(0))


_SETUP_DECISIONS = [
    {
        "id": "decide/cheap",
        "context_length": 64000,
        "pricing": {"prompt": "0.00000004", "completion": "0"},
        "architecture": {
            "input_modalities": ["text"],
            "output_modalities": ["decisions"],
        },
    },
    {
        "id": "decide/pricey",
        "context_length": 32000,
        "pricing": {"prompt": "0.00000020", "completion": "0"},
        "architecture": {
            "input_modalities": ["text"],
            "output_modalities": ["text", "decisions"],
        },
    },
    {
        "id": "decide/unpriced",
        "context_length": 128000,
        "architecture": {
            "input_modalities": ["text"],
            "output_modalities": ["decisions"],
        },
    },
    {
        "id": "~decide/alias",
        "context_length": 64000,
        "pricing": {"prompt": "0.00000001", "completion": "0"},
        "architecture": {"output_modalities": ["decisions"]},
    },
    {
        "id": "decide/zero-ctx",
        "context_length": 0,
        "pricing": {"prompt": "0.00000001", "completion": "0"},
        "architecture": {"output_modalities": ["decisions"]},
    },
    {
        "id": "chat/only",
        "context_length": 64000,
        "pricing": {"prompt": "0.00000001", "completion": "0"},
        "architecture": {"output_modalities": ["text"]},
    },
    {"id": "broken/decider", "pricing": {"prompt": "n/a"}},
    "not-a-dict",
    {"id": ""},
]
"""Fixture decisions catalog: valid, alias, zero-context, chat-only, malformed."""


def _setup_catalog(monkeypatch, payload=None, decisions=None):
    """Serve fixture catalogs (deep-ish copies) for both setup fetches."""
    import strands_code_cli.live_pricing as live_pricing_mod

    rows = payload if payload is not None else _SETUP_CATALOG
    monkeypatch.setattr(
        live_pricing_mod,
        "fetch_openrouter_models",
        lambda: [dict(e) if isinstance(e, dict) else e for e in rows],
    )
    decision_rows = decisions if decisions is not None else _SETUP_DECISIONS
    monkeypatch.setattr(
        live_pricing_mod,
        "fetch_openrouter_decision_models",
        lambda: [dict(e) if isinstance(e, dict) else e for e in decision_rows],
    )


def _run_setup(tmp_path):
    return dispatch(
        "/route setup", session_id="s", index=SessionIndex(tmp_path / "index")
    )


class TestRouteSetup:
    def test_full_run_writes_repo_scope_in_pick_order(self, tmp_path, monkeypatch):
        repo_path, global_path = _setup_paths(monkeypatch, tmp_path)
        _setup_catalog(monkeypatch)
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        monkeypatch.setattr(routing_mod, "local_engine_ready", lambda b, t: True)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        calls = _scripted_radio(
            monkeypatch,
            [
                "repo",  # scope
                "good/pricey",  # candidate 1 (not cheapest: pick order wins)
                "good/cheap",  # candidate 2
                _SETUP_DONE,  # done
                "decide/cheap",  # decision model (decisions catalog)
            ],
        )
        _scripted_input(
            monkeypatch,
            [
                "",  # accept the proposed order
                "",  # local tag takes nimble
                "",  # skip notes stay on
                "trivial asks go cheap",
                "deep work goes big",
                "",
            ],
        )
        action, message = _run_setup(tmp_path)
        assert action == "reply"
        assert repo_path.exists() and not global_path.exists()
        data = yaml.safe_load(repo_path.read_text(encoding="utf-8"))
        assert [c["id"] for c in data["candidates"]] == [
            "good/pricey",
            "good/cheap",
        ]
        assert data["directives"] == "trivial asks go cheap\ndeep work goes big"
        assert data["engine"] == {
            "order": ["openrouter", "local"],
            "skip_notes": True,
            "decision_model": "decide/cheap",
            "local_model": "nimble",
        }
        assert "(repo)" in message
        assert "2 candidates" in message
        assert "engine order openrouter, local" in message
        assert "/route validate" in message
        assert "Manual /model always wins" in message
        # Catalog hygiene: price-ascending offer, non-chat and malformed
        # rows never offered, unpriced chat-shaped rows offered last.
        first_pick = [value for value, _ in calls[1][1]]
        assert first_pick == [
            "good/cheap",
            "good/pricey",
            "broken/entry",
            "good/unpriced",
            _SETUP_DONE,
        ]
        offered = [value for _, opts in calls for value, _ in opts]
        assert "vendor/embed-large" not in offered
        assert "vendor/rerank-pro" not in offered
        decision_pick = [value for value, _ in calls[4][1]]
        assert decision_pick == [
            "decide/cheap",
            "decide/pricey",
            "decide/unpriced",
        ]
        assert "~decide/alias" not in decision_pick
        assert "decide/zero-ctx" not in decision_pick
        assert "chat/only" not in decision_pick

    def test_global_scope_run_writes_global_path(self, tmp_path, monkeypatch):
        repo_path, global_path = _setup_paths(monkeypatch, tmp_path)
        _setup_catalog(monkeypatch)
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        monkeypatch.setattr(routing_mod, "local_engine_ready", lambda b, t: True)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        _scripted_radio(
            monkeypatch,
            ["global", "good/cheap", _SETUP_DONE, "decide/cheap"],
        )
        _scripted_input(
            monkeypatch,
            ["", "", "", "", "yes"],  # proposal, tag, skip, empty directives + confirm
        )
        action, message = _run_setup(tmp_path)
        assert action == "reply"
        assert global_path.exists() and not repo_path.exists()
        data = yaml.safe_load(global_path.read_text(encoding="utf-8"))
        assert [c["id"] for c in data["candidates"]] == ["good/cheap"]
        assert data["directives"] == ""
        assert data["engine"]["order"] == ["openrouter", "local"]
        assert "(global)" in message

    def test_esc_mid_flow_writes_nothing(self, tmp_path, monkeypatch):
        repo_path, global_path = _setup_paths(monkeypatch, tmp_path)
        _setup_catalog(monkeypatch)
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        monkeypatch.setattr(routing_mod, "local_engine_ready", lambda b, t: True)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        _scripted_radio(monkeypatch, ["repo", None])  # ESC at the primary radio
        _scripted_input(monkeypatch, ["no"])  # decline the proposal first
        action, message = _run_setup(tmp_path)
        assert action == "reply"
        assert "no changes written" in message
        assert not repo_path.exists() and not global_path.exists()

    def test_empty_input_aborts_off_tty(self, tmp_path, monkeypatch):
        repo_path, global_path = _setup_paths(monkeypatch, tmp_path)
        _setup_catalog(monkeypatch)
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        monkeypatch.setattr(routing_mod, "local_engine_ready", lambda b, t: True)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        _scripted_input(monkeypatch, [""])  # empty scope answer aborts
        action, message = _run_setup(tmp_path)
        assert action == "reply"
        assert "no changes written" in message
        assert not repo_path.exists() and not global_path.exists()

    def test_done_with_zero_picks_reprompts(self, tmp_path, monkeypatch, capsys):
        repo_path, _ = _setup_paths(monkeypatch, tmp_path)
        _setup_catalog(monkeypatch)
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        monkeypatch.setattr(routing_mod, "local_engine_ready", lambda b, t: True)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        _scripted_radio(
            monkeypatch,
            [
                "repo",
                _SETUP_DONE,  # done with zero picks: re-prompted
                "good/cheap",
                _SETUP_DONE,
                "decide/cheap",
            ],
        )
        _scripted_input(monkeypatch, ["", "", "", "d", ""])
        action, _ = _run_setup(tmp_path)
        assert action == "reply"
        data = yaml.safe_load(repo_path.read_text(encoding="utf-8"))
        assert [c["id"] for c in data["candidates"]] == ["good/cheap"]
        assert "at least one candidate" in capsys.readouterr().out

    def test_off_tty_comma_list_reprompts_once_then_writes_valid_subset(
        self, tmp_path, monkeypatch, capsys
    ):
        repo_path, _ = _setup_paths(monkeypatch, tmp_path)
        _setup_catalog(monkeypatch)
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        monkeypatch.setattr(routing_mod, "local_engine_ready", lambda b, t: True)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        _scripted_input(
            monkeypatch,
            [
                "2",  # scope: repo
                "",  # accept the proposed order
                "good/cheap, bogus/model",  # attempt 1: one unknown id
                "good/cheap, good/pricey",  # attempt 2: valid subset written
                "decide/cheap",  # decision model (decisions catalog)
                "",  # local tag takes nimble
                "",  # skip notes stay on
                "cheap first",
                "",
            ],
        )
        action, message = _run_setup(tmp_path)
        assert action == "reply"
        assert "saved" in message
        data = yaml.safe_load(repo_path.read_text(encoding="utf-8"))
        assert [c["id"] for c in data["candidates"]] == [
            "good/cheap",
            "good/pricey",
        ]
        assert "bogus/model" in capsys.readouterr().out

    def test_catalog_fetch_failure_offers_typed_id_path(
        self, tmp_path, monkeypatch, capsys
    ):
        repo_path, _ = _setup_paths(monkeypatch, tmp_path)
        import strands_code_cli.live_pricing as live_pricing_mod

        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        monkeypatch.setattr(routing_mod, "local_engine_ready", lambda b, t: True)
        monkeypatch.setattr(live_pricing_mod, "fetch_openrouter_models", lambda: None)
        monkeypatch.setattr(
            live_pricing_mod, "fetch_openrouter_decision_models", lambda: None
        )
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        _scripted_radio(monkeypatch, ["repo"])
        _scripted_input(
            monkeypatch,
            [
                "",
                "custom/alpha, custom/beta",
                "custom/decider",
                "",
                "",
                "hands on",
                "",
            ],
        )
        action, message = _run_setup(tmp_path)
        assert action == "reply"
        assert "saved" in message
        data = yaml.safe_load(repo_path.read_text(encoding="utf-8"))
        assert [c["id"] for c in data["candidates"]] == [
            "custom/alpha",
            "custom/beta",
        ]
        assert data["engine"]["decision_model"] == "custom/decider"
        assert "manually" in capsys.readouterr().out

    def test_local_engine_run_captures_local_model(self, tmp_path, monkeypatch):
        repo_path, _ = _setup_paths(monkeypatch, tmp_path)
        _setup_catalog(monkeypatch)
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        monkeypatch.setattr(routing_mod, "local_engine_ready", lambda b, t: True)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        _scripted_radio(
            monkeypatch,
            ["repo", "good/cheap", _SETUP_DONE, "decide/pricey"],
        )
        _scripted_input(monkeypatch, ["", "tev1:0.8b", "", "side note", ""])
        action, _ = _run_setup(tmp_path)
        assert action == "reply"
        data = yaml.safe_load(repo_path.read_text(encoding="utf-8"))
        assert data["engine"] == {
            "order": ["openrouter", "local"],
            "skip_notes": True,
            "decision_model": "decide/pricey",
            "local_model": "tev1:0.8b",
        }

    def test_decision_entries_drop_alias_zero_context_and_chat_only(self):
        entries = _setup_decision_entries(_SETUP_DECISIONS)
        assert [entry["id"] for entry in entries] == [
            "decide/cheap",
            "decide/pricey",
            "decide/unpriced",
        ]
        assert entries[0]["label"].endswith("(price n/a)") is False
        assert "per 1M" in entries[0]["label"]
        assert entries[2]["label"].endswith("(price n/a)")
        assert _setup_decision_entries(None) == []
        assert _setup_decision_entries({"id": "x"}) == []
        assert _setup_decision_entries("nope") == []

    def test_unreachable_decisions_catalog_falls_back_to_typed_id(
        self, tmp_path, monkeypatch, capsys
    ):
        repo_path, _ = _setup_paths(monkeypatch, tmp_path)
        _setup_catalog(monkeypatch)
        import strands_code_cli.live_pricing as live_pricing_mod

        # Chat catalog fine, decisions catalog down: candidates pick
        # from the radio, the decider falls back to a typed id with
        # no default assumed.
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        monkeypatch.setattr(routing_mod, "local_engine_ready", lambda b, t: True)
        monkeypatch.setattr(
            live_pricing_mod, "fetch_openrouter_decision_models", lambda: None
        )
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        _scripted_radio(monkeypatch, ["repo", "good/cheap", _SETUP_DONE])
        _scripted_input(monkeypatch, ["", "custom/decider", "", "", "hands on", ""])
        action, message = _run_setup(tmp_path)
        assert action == "reply"
        assert "saved" in message
        data = yaml.safe_load(repo_path.read_text(encoding="utf-8"))
        assert [c["id"] for c in data["candidates"]] == ["good/cheap"]
        assert data["engine"]["decision_model"] == "custom/decider"
        assert "Decisions catalog unreachable" in capsys.readouterr().out

    def test_useless_decisions_catalog_falls_back_to_typed_id(
        self, tmp_path, monkeypatch, capsys
    ):
        repo_path, _ = _setup_paths(monkeypatch, tmp_path)
        # Reachable but nothing usable (alias + zero-context only).
        _setup_catalog(
            monkeypatch,
            decisions=[
                {"id": "~d/alias", "context_length": 1},
                {"id": "d/zero", "context_length": 0},
            ],
        )
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        monkeypatch.setattr(routing_mod, "local_engine_ready", lambda b, t: True)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        _scripted_radio(monkeypatch, ["repo", "good/cheap", _SETUP_DONE])
        _scripted_input(monkeypatch, ["", "typed/decider", "", "", "d", ""])
        action, message = _run_setup(tmp_path)
        assert action == "reply"
        assert "saved" in message
        data = yaml.safe_load(repo_path.read_text(encoding="utf-8"))
        assert data["engine"]["decision_model"] == "typed/decider"
        assert "No usable decision models" in capsys.readouterr().out

    def test_abort_at_decider_writes_nothing(self, tmp_path, monkeypatch):
        repo_path, global_path = _setup_paths(monkeypatch, tmp_path)
        _setup_catalog(monkeypatch)
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        monkeypatch.setattr(routing_mod, "local_engine_ready", lambda b, t: True)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        _scripted_input(
            monkeypatch,
            [
                "2",  # scope: repo
                "",  # accept the proposed order
                "good/cheap",  # candidates
                "",  # decider: empty aborts
            ],
        )
        action, message = _run_setup(tmp_path)
        assert action == "reply"
        assert "no changes written" in message
        assert not repo_path.exists() and not global_path.exists()

    def test_off_tty_decider_reprompts_once_then_aborts(
        self, tmp_path, monkeypatch, capsys
    ):
        repo_path, _ = _setup_paths(monkeypatch, tmp_path)
        _setup_catalog(monkeypatch)
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        monkeypatch.setattr(routing_mod, "local_engine_ready", lambda b, t: True)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        _scripted_input(
            monkeypatch,
            [
                "2",
                "",
                "good/cheap",
                "bogus/decider",  # attempt 1: unknown, re-prompted
                "bogus/again",  # attempt 2: unknown, aborts
            ],
        )
        action, message = _run_setup(tmp_path)
        assert action == "reply"
        assert "no changes written" in message
        assert not repo_path.exists()
        assert "Unknown decision model" in capsys.readouterr().out

    def test_setup_never_prompts_for_keys(self, tmp_path, monkeypatch, capsys):
        _setup_paths(monkeypatch, tmp_path)
        _setup_catalog(monkeypatch)
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        monkeypatch.setattr(routing_mod, "local_engine_ready", lambda b, t: True)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        _scripted_radio(
            monkeypatch,
            ["repo", "good/cheap", _SETUP_DONE, "decide/cheap"],
        )
        _scripted_input(monkeypatch, ["", "", "", "d", ""])
        action, message = _run_setup(tmp_path)
        assert action == "reply"
        assert "saved" in message
        out = capsys.readouterr().out.lower()
        assert "api_key" not in out
        assert "api key" not in out

    def test_local_model_empty_takes_nimble_default(self, tmp_path, monkeypatch):
        repo_path, _ = _setup_paths(monkeypatch, tmp_path)
        _setup_catalog(monkeypatch)
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        monkeypatch.setattr(routing_mod, "local_engine_ready", lambda b, t: True)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        _scripted_radio(
            monkeypatch,
            ["repo", "good/cheap", _SETUP_DONE, "decide/cheap"],
        )
        _scripted_input(monkeypatch, ["", "", "", "side note", ""])
        action, _ = _run_setup(tmp_path)
        assert action == "reply"
        data = yaml.safe_load(repo_path.read_text(encoding="utf-8"))
        assert data["engine"]["local_model"] == "nimble"

    def test_save_strategy_refuses_symlinked_target(self, tmp_path):
        target = tmp_path / "real.yaml"
        target.write_text("candidates: []\n", encoding="utf-8")
        link = tmp_path / "link.yaml"
        link.symlink_to(target)
        with pytest.raises(ValueError, match="symlink"):
            save_strategy({"candidates": [{"id": "a/1"}]}, "repo", repo_path=link)

    def test_save_strategy_drops_api_key_shaped_keys(self, tmp_path, caplog):
        import logging

        data = {
            "candidates": [{"id": "a/1"}],
            "directives": "d",
            "api_key": "sk-live-123",
            "engine": {
                "primary": "openrouter",
                "decision_model": "c/d",
                "API_KEY": "sk-live-456",
            },
        }
        with caplog.at_level(logging.WARNING, logger="strands_code_cli.routing"):
            path = save_strategy(
                data, "global", global_path=tmp_path / "cfg" / "g.yaml"
            )
        saved = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert "api_key" not in saved
        assert "API_KEY" not in saved.get("engine", {})
        assert saved["candidates"] == [{"id": "a/1"}]
        assert saved["engine"]["decision_model"] == "c/d"
        assert "sk-live" not in path.read_text(encoding="utf-8")
        assert "secret-shaped" in caplog.text
        assert path.parent.stat().st_mode & 0o777 == 0o700

    def test_save_strategy_drops_typesafe_key_shaped_keys(self, tmp_path, caplog):
        import logging

        data = {
            "candidates": [{"id": "a/1"}],
            "directives": "d",
            "TYPESAFE_API_KEY": "ts-[REDACTED]",
            "engine": {
                "order": ["native"],
                "native_model": "jev-1.13.0",
                "TYPESAFE_API_KEY": "ts-[REDACTED]",
            },
        }
        with caplog.at_level(logging.WARNING, logger="strands_code_cli.routing"):
            path = save_strategy(
                data, "global", global_path=tmp_path / "cfg" / "g.yaml"
            )
        saved = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert "TYPESAFE_API_KEY" not in saved
        assert "TYPESAFE_API_KEY" not in saved.get("engine", {})
        assert saved["engine"]["native_model"] == "jev-1.13.0"
        assert saved["engine"]["order"] == ["native"]
        assert "ts-[REDACTED]" not in path.read_text(encoding="utf-8")
        assert "secret-shaped" in caplog.text

    def test_save_strategy_refuses_zero_usable_candidates(self, tmp_path):
        with pytest.raises(ValueError, match="zero usable candidates"):
            save_strategy(
                {"candidates": [], "directives": "d"},
                "repo",
                repo_path=tmp_path / "r.yaml",
            )
        with pytest.raises(ValueError, match="zero usable candidates"):
            save_strategy(
                {"candidates": [{"bogus": True}]},
                "repo",
                repo_path=tmp_path / "r.yaml",
            )
        assert not (tmp_path / "r.yaml").exists()

    def test_docs_routing_examples_are_valid_yaml(self):
        text = (Path(__file__).parent.parent / "docs" / "ROUTING.md").read_text(
            encoding="utf-8"
        )
        blocks = re.findall(r"```yaml\n(.*?)```", text, re.DOTALL)
        examples = [block for block in blocks if "candidates:" in block]
        assert len(examples) == 2
        for example in examples:
            data = yaml.safe_load(example)
            assert {"candidates", "directives", "engine"} <= set(data)
            assert data["candidates"] and all("id" in c for c in data["candidates"])
            assert data["engine"]["decision_model"]


def _seed_cache_ids(tmp_path, filename, ids):
    """Seed one isolated OpenRouter disk cache file with the given ids."""
    (tmp_path / "cache" / filename).write_text(
        json.dumps(
            {
                "fetched_at": 0,
                "models": {i: {"in": 1.0, "out": 2.0} for i in ids},
            }
        ),
        encoding="utf-8",
    )


def _seed_catalog_ids(tmp_path, ids):
    """Seed the isolated OpenRouter chat disk cache with the given ids."""
    _seed_cache_ids(tmp_path, "openrouter-models.json", ids)


def _seed_decision_ids(tmp_path, ids):
    """Seed the isolated decisions disk cache with the given ids."""
    _seed_cache_ids(tmp_path, "openrouter-decision-models.json", ids)


class TestRouteValidate:
    @pytest.fixture(autouse=True)
    def _empty_cache(self, tmp_path, monkeypatch):
        cache = tmp_path / "cache"
        cache.mkdir(exist_ok=True)
        monkeypatch.setenv("STRANDS_CODE_CACHE_DIR", str(cache))

    def test_valid_file_reports_clean_naming_winning_source(self, tmp_path):
        _seed_decision_ids(tmp_path, ["cheap/decider"])
        path = _write(tmp_path / "repo.yaml", _strategy_yaml())
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is True
        assert report.source == path
        text = report.format()
        assert text.startswith("Routing strategy VALID")
        assert str(path) in text
        assert "candidate #0 a/1: ok" in text
        assert "known in the cached decisions catalog" in text
        assert "directives: present" in text

    def test_unchecked_catalog_stays_valid(self, tmp_path):
        path = _write(tmp_path / "repo.yaml", _strategy_yaml())
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is True
        text = report.format()
        assert "unchecked" in text and "/cost refresh" in text

    def test_long_directives_validate_with_warning(self, tmp_path):
        _seed_decision_ids(tmp_path, ["cheap/decider"])
        path = _write(
            tmp_path / "repo.yaml",
            "candidates: [{id: a/1}]\n"
            f"directives: {'d' * 5000}\n"
            "engine: {primary: openrouter, decision_model: cheap/decider}\n",
        )
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is True  # a warning, never a failure
        text = report.format()
        assert "directives: present (5000 chars)" in text
        # Match the line content: the tmp path itself carries the
        # test name, so a bare "warning" substring would false-hit.
        assert "warning: directives exceed ~4K chars" in text

    def test_directives_warning_boundary(self, tmp_path):
        _seed_decision_ids(tmp_path, ["cheap/decider"])

        def _validate_with(directives: str) -> str:
            path = _write(
                tmp_path / "repo.yaml",
                "candidates: [{id: a/1}]\n"
                f"directives: {directives}\n"
                "engine: {primary: openrouter, decision_model: cheap/decider}\n",
            )
            report = validate_strategy(
                global_path=tmp_path / "absent.yaml", repo_path=path
            )
            assert report.valid is True
            return report.format()

        assert "exceed ~4K chars" not in _validate_with("d" * 4096)
        assert "exceed ~4K chars" in _validate_with("d" * 4097)

    def test_openrouter_prefixed_id_matches_verbatim(self, tmp_path):
        # UAT R1: openrouter/auto is a genuine catalog id — the
        # aggregator-prefix strip must not mangle it into "auto".
        _seed_decision_ids(tmp_path, ["openrouter/auto"])
        path = _write(
            tmp_path / "repo.yaml",
            "candidates: [{id: a/1}]\n"
            "directives: d\n"
            "engine: {primary: openrouter, decision_model: openrouter/auto}\n",
        )
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is True
        assert "known in the cached decisions catalog" in report.format()

    def test_unknown_decision_model_reports_engine_failure(self, tmp_path):
        _seed_decision_ids(tmp_path, ["other/model"])
        path = _write(tmp_path / "repo.yaml", _strategy_yaml())
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is False
        text = report.format()
        assert text.startswith("Routing strategy INVALID")
        assert "not in the cached decisions catalog" in text
        assert "fix: pick a live id from the decisions listing" in text

    def test_corrupt_file_reports_invalid_with_loader_reason(self, tmp_path):
        repo = _write(tmp_path / "repo.yaml", "candidates: [unclosed\n")
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=repo)
        assert report.valid is False
        text = report.format()
        assert f"repo strategy {repo} is unreadable" in text
        assert "fix: repair the YAML" in text
        listed = _write(tmp_path / "listed.yaml", "- just\n- a\n- list\n")
        report = validate_strategy(
            global_path=tmp_path / "absent.yaml", repo_path=listed
        )
        assert report.valid is False
        assert "not a mapping" in report.format()

    def test_corrupt_repo_falls_back_to_global_with_note(self, tmp_path):
        _seed_decision_ids(tmp_path, ["cheap/decider"])
        repo = _write(tmp_path / "repo.yaml", "candidates: [unclosed\n")
        home = _write(tmp_path / "global.yaml", _strategy_yaml())
        report = validate_strategy(global_path=home, repo_path=repo)
        assert report.valid is True
        assert report.source == home
        assert "using the global file instead" in report.format()

    def test_entry_with_unknown_keys_reports_skip_reason_with_fix(self, tmp_path):
        _seed_decision_ids(tmp_path, ["cheap/decider"])
        path = _write(
            tmp_path / "repo.yaml",
            _strategy_yaml(
                candidates=("\n  - {id: good/1}\n  - {id: bad/1, bogus: true}\n")
            ),
        )
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is False
        text = report.format()
        assert "candidate #0 good/1: ok" in text
        assert "candidate #1: SKIP — unknown keys: ['bogus']" in text
        assert "fix: remove the unknown keys from candidates[1]" in text

    def test_missing_decision_model_with_primary_openrouter(self, tmp_path):
        path = _write(
            tmp_path / "repo.yaml",
            "candidates: [{id: a/1}]\ndirectives: d\nengine: {primary: openrouter}\n",
        )
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is False
        text = report.format()
        assert "with no decision_model" in text
        assert "fix: set engine.decision_model" in text

    def test_missing_local_model_with_primary_local(self, tmp_path):
        path = _write(
            tmp_path / "repo.yaml",
            "candidates: [{id: a/1}]\ndirectives: d\nengine: {primary: local}\n",
        )
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is False
        text = report.format()
        assert "with no local_model" in text
        assert "fix: set engine.local_model" in text

    def test_local_primary_with_model_reports_valid(self, tmp_path):
        path = _write(
            tmp_path / "repo.yaml",
            "candidates: [{id: a/1}]\ndirectives: d\n"
            "engine: {primary: local, local_model: qwen3:8b}\n",
        )
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is True
        assert "unused while primary is local" in report.format()

    def test_primary_off_reports_valid_disabled(self, tmp_path):
        path = _write(
            tmp_path / "repo.yaml",
            "candidates: [{id: a/1}]\ndirectives: d\nengine: {primary: off}\n",
        )
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is True
        assert "disabled by config" in report.format()

    def test_empty_candidates_list_reports_invalid(self, tmp_path):
        missing = _write(tmp_path / "missing.yaml", "directives: d\n")
        report = validate_strategy(
            global_path=tmp_path / "absent.yaml", repo_path=missing
        )
        assert report.valid is False
        assert "no usable candidates" in report.format()
        empty = _write(
            tmp_path / "empty.yaml",
            "candidates: []\ndirectives: d\n"
            "engine: {primary: openrouter, decision_model: c/d}\n",
        )
        report = validate_strategy(
            global_path=tmp_path / "absent.yaml", repo_path=empty
        )
        assert report.valid is False
        assert "no usable candidates" in report.format()

    def test_no_strategy_file_reports_invalid(self, tmp_path):
        report = validate_strategy(
            global_path=tmp_path / "absent-global.yaml",
            repo_path=tmp_path / "absent-repo.yaml",
        )
        assert report.valid is False
        text = report.format()
        assert "no strategy file found" in text
        assert "fix: run /route setup" in text

    def test_symlinked_path_reports_invalid_without_raising(self, tmp_path):
        target = _write(tmp_path / "real.yaml", _strategy_yaml())
        link = tmp_path / "link.yaml"
        link.symlink_to(target)
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=link)
        assert report.valid is False
        assert "symlink" in report.format()

    def test_unknown_top_level_keys_are_notes_not_failures(self, tmp_path):
        path = _write(tmp_path / "repo.yaml", _strategy_yaml(extra="mystery: 42\n"))
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is True
        assert "unknown top-level keys ignored" in report.format()

    def test_skip_reason_matches_loader_warning(self, tmp_path, caplog):
        import logging

        path = _write(
            tmp_path / "repo.yaml",
            _strategy_yaml(
                candidates=("\n  - {id: good/1}\n  - {id: bad/1, bogus: true}\n")
            ),
        )
        with caplog.at_level(logging.WARNING, logger="strands_code_cli.routing"):
            strategy = load_strategy(
                global_path=path, repo_path=tmp_path / "absent.yaml"
            )
        assert strategy is not None
        assert [c.id for c in strategy.candidates] == ["good/1"]
        assert "Ignoring routing candidate #1 (unknown keys: ['bogus'])" in caplog.text
        report = validate_strategy(global_path=path, repo_path=tmp_path / "absent.yaml")
        assert "candidate #1: SKIP — unknown keys: ['bogus']" in report.format()

    def test_validate_dispatch_never_writes_or_fetches(self, tmp_path, monkeypatch):
        import urllib.request

        repo = _write(tmp_path / "r.yaml", _strategy_yaml())
        monkeypatch.setattr(routing_mod, "default_repo_strategy_path", lambda: repo)
        monkeypatch.setattr(
            routing_mod, "default_global_strategy_path", lambda: tmp_path / "g.yaml"
        )

        def _boom(request, timeout=None):
            raise AssertionError("validate must not touch the network")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        index = SessionIndex(tmp_path / "index")
        before = {
            path: path.read_bytes() if path.is_file() else None
            for path in tmp_path.rglob("*")
        }
        action, message = dispatch("/route validate", session_id="s", index=index)
        after = {
            path: path.read_bytes() if path.is_file() else None
            for path in tmp_path.rglob("*")
        }
        assert action == "reply"
        assert message.startswith("Routing strategy VALID")
        assert str(repo) in message
        assert after == before

    def test_27_candidates_fail_naming_cap(self, tmp_path):
        _seed_decision_ids(tmp_path, ["cheap/decider"])
        rows = "\n".join(f"  - {{id: m/{n}}}" for n in range(27))
        path = _write(tmp_path / "repo.yaml", _strategy_yaml(candidates=f"\n{rows}\n"))
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is False
        text = report.format()
        assert "27 entries" in text
        assert "26-candidate cap" in text
        assert "fix: keep at most 26 candidates" in text

    def test_26_candidates_pass_cap(self, tmp_path):
        _seed_decision_ids(tmp_path, ["cheap/decider"])
        rows = "\n".join(f"  - {{id: m/{n}}}" for n in range(26))
        path = _write(tmp_path / "repo.yaml", _strategy_yaml(candidates=f"\n{rows}\n"))
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is True

    def test_knob_out_of_range_fails_with_fix(self, tmp_path):
        path = _write(
            tmp_path / "repo.yaml",
            _strategy_yaml(extra="tie_margin: 2.0\nconfidence_threshold: -1.0\n"),
        )
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is False
        text = report.format()
        assert "tie_margin: INVALID — 2.0 is outside 0..1" in text
        assert "confidence_threshold: INVALID — -1.0 is outside 0..1" in text
        assert "fix: set tie_margin to a number between 0 and 1" in text
        assert "fix: set confidence_threshold to a number between 0 and 1" in text

    def test_knob_wrong_type_fails_with_fix(self, tmp_path):
        path = _write(
            tmp_path / "repo.yaml",
            _strategy_yaml(extra="tie_margin: wide\n"),
        )
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is False
        text = report.format()
        assert "tie_margin: INVALID — 'wide' is not a number" in text
        assert "fix: set tie_margin to a number between 0 and 1" in text

    def test_knob_defaults_reported(self, tmp_path):
        _seed_decision_ids(tmp_path, ["cheap/decider"])
        path = _write(tmp_path / "repo.yaml", _strategy_yaml())
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is True
        text = report.format()
        assert "tie_margin: 0.04 (default)" in text
        assert "confidence_threshold: 0.62 (default)" in text

    def test_explicit_knobs_reported(self, tmp_path):
        _seed_decision_ids(tmp_path, ["cheap/decider"])
        path = _write(
            tmp_path / "repo.yaml",
            _strategy_yaml(extra="tie_margin: 0.1\nconfidence_threshold: 0.6\n"),
        )
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is True
        text = report.format()
        assert "tie_margin: 0.1" in text
        assert "confidence_threshold: 0.6" in text
        assert "(default)" not in text

    def test_criteria_wrong_type_fails_with_fix(self, tmp_path):
        _seed_decision_ids(tmp_path, ["cheap/decider"])
        path = _write(
            tmp_path / "repo.yaml",
            _strategy_yaml(candidates="[{id: a/1, criteria: [not, prose]}]"),
        )
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is False
        text = report.format()
        assert "candidate #0: SKIP — 'criteria' not a string" in text
        assert "fix: make candidates[0].criteria a string" in text

    def test_criteria_present_passes(self, tmp_path):
        _seed_decision_ids(tmp_path, ["cheap/decider"])
        path = _write(
            tmp_path / "repo.yaml",
            _strategy_yaml(candidates="[{id: a/1, criteria: 'Cheap small model'}]"),
        )
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is True
        assert "candidate #0 a/1: ok" in report.format()

    def test_chat_only_model_as_decider_fails_with_decisions_fix(self, tmp_path):
        # Known in the chat cache but absent from the decisions
        # cache: the decider check reads the decisions ids only.
        _seed_catalog_ids(tmp_path, ["chat/only"])
        _seed_decision_ids(tmp_path, ["other/decider"])
        path = _write(
            tmp_path / "repo.yaml",
            "candidates: [{id: a/1}]\n"
            "directives: d\n"
            "engine: {primary: openrouter, decision_model: chat/only}\n",
        )
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is False
        text = report.format()
        assert "not in the cached decisions catalog" in text
        assert "fix: pick a live id from the decisions listing" in text

    def test_decisions_catalog_id_as_decider_validates(self, tmp_path):
        _seed_decision_ids(tmp_path, ["decide/yes"])
        path = _write(
            tmp_path / "repo.yaml",
            "candidates: [{id: a/1}]\n"
            "directives: d\n"
            "engine: {primary: openrouter, decision_model: decide/yes}\n",
        )
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is True
        assert "known in the cached decisions catalog" in report.format()

    def test_validate_makes_zero_network_calls(self, tmp_path, monkeypatch):
        _seed_decision_ids(tmp_path, ["cheap/decider"])
        calls = []

        def _count(request, timeout=None):
            calls.append(request)
            raise AssertionError("validate must not touch the network")

        monkeypatch.setattr(urllib.request, "urlopen", _count)
        path = _write(tmp_path / "repo.yaml", _strategy_yaml())
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is True
        assert calls == []

    def test_docs_routing_examples_validate_verbatim(self, tmp_path):
        text = (Path(__file__).parent.parent / "docs" / "ROUTING.md").read_text(
            encoding="utf-8"
        )
        blocks = re.findall(r"```yaml\n(.*?)```", text, re.DOTALL)
        examples = [block for block in blocks if "candidates:" in block]
        assert len(examples) == 2
        deciders = set()
        for example in examples:
            engine = yaml.safe_load(example).get("engine") or {}
            if engine.get("decision_model"):
                deciders.add(engine["decision_model"])
        assert deciders, "examples carry no decider to seed"
        _seed_decision_ids(tmp_path, sorted(deciders))
        for pos, example in enumerate(examples):
            path = _write(tmp_path / f"example-{pos}.yaml", example)
            report = validate_strategy(
                global_path=tmp_path / "absent.yaml", repo_path=path
            )
            assert report.valid is True, report.format()

    @pytest.mark.parametrize("model", ["jev-1.13.0", "jev-latest"])
    def test_native_verified_ids_validate_with_ok_line(self, tmp_path, model):
        path = _write(
            tmp_path / "repo.yaml",
            "candidates: [{id: a/1}]\n"
            "directives: d\n"
            f"engine: {{order: [native], native_model: {model}}}\n",
        )
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is True
        assert f"engine: native model {model} — ok" in report.format()

    @pytest.mark.parametrize(
        "model", ["jev-1.13", "typesafe/jev-1.13", "no-such-model"]
    )
    def test_native_unverified_strings_fail_naming_pin(self, tmp_path, model):
        path = _write(
            tmp_path / "repo.yaml",
            "candidates: [{id: a/1}]\n"
            "directives: d\n"
            f"engine: {{order: [native], native_model: {model}}}\n",
        )
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is False
        text = report.format()
        assert "not a verified native id" in text
        assert "fix: set engine.native_model to jev-1.13.0" in text

    def test_native_missing_model_fails_with_setup_fix(self, tmp_path):
        path = _write(
            tmp_path / "repo.yaml",
            "candidates: [{id: a/1}]\ndirectives: d\nengine: {order: [native]}\n",
        )
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is False
        text = report.format()
        assert "order lists native with no native_model" in text
        assert "fix: set engine.native_model" in text
        assert "/route setup" in text

    def test_unknown_order_entry_fails_naming_entry(self, tmp_path):
        path = _write(
            tmp_path / "repo.yaml",
            "candidates: [{id: a/1}]\n"
            "directives: d\n"
            "engine: {order: [native, bogus], native_model: jev-1.13.0}\n",
        )
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is False
        text = report.format()
        assert "unknown engine 'bogus' in engine.order" in text
        assert "fix: remove 'bogus' from engine.order" in text

    def test_order_not_a_list_fails_with_fix(self, tmp_path):
        path = _write(
            tmp_path / "repo.yaml",
            "candidates: [{id: a/1}]\n"
            "directives: d\n"
            "engine: {primary: openrouter, order: native,"
            " decision_model: cheap/decider}\n",
        )
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is False
        text = report.format()
        assert "engine.order is not a list" in text
        assert "fix: set engine.order to a list" in text

    def test_legacy_primary_nudges_without_failing(self, tmp_path):
        _seed_decision_ids(tmp_path, ["cheap/decider"])
        path = _write(tmp_path / "repo.yaml", _strategy_yaml())
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is True
        assert "re-run /route setup to adopt the engines list" in report.format()

    def test_order_and_primary_notes_primary_ignored(self, tmp_path):
        path = _write(
            tmp_path / "repo.yaml",
            "candidates: [{id: a/1}]\n"
            "directives: d\n"
            "engine: {primary: local, order: [native],"
            " native_model: jev-1.13.0}\n",
        )
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is True
        text = report.format()
        assert "engine.primary is ignored" in text
        assert "engine: native model jev-1.13.0 — ok" in text
        assert "unused while primary is local" not in text
        bogus = _write(
            tmp_path / "bogus.yaml",
            "candidates: [{id: a/1}]\n"
            "directives: d\n"
            "engine: {primary: bogus, order: [native],"
            " native_model: jev-1.13.0}\n",
        )
        report = validate_strategy(
            global_path=tmp_path / "absent.yaml", repo_path=bogus
        )
        assert report.valid is True  # ignored primary judges nothing
        assert "unknown primary" not in report.format()

    def test_empty_order_matches_legacy_off_line(self, tmp_path):
        path = _write(
            tmp_path / "repo.yaml",
            "candidates: [{id: a/1}]\ndirectives: d\nengine: {order: []}\n",
        )
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=path)
        assert report.valid is True
        assert "engine: primary off — routing disabled by config" in report.format()

    def test_ordered_openrouter_and_local_judge_per_engine(self, tmp_path):
        _seed_decision_ids(tmp_path, ["cheap/decider"])
        bare = _write(
            tmp_path / "bare.yaml",
            "candidates: [{id: a/1}]\n"
            "directives: d\n"
            "engine: {order: [openrouter, local]}\n",
        )
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=bare)
        assert report.valid is False
        text = report.format()
        assert "order lists openrouter with no decision_model" in text
        assert "order lists local with no local_model" in text
        full = _write(
            tmp_path / "full.yaml",
            "candidates: [{id: a/1}]\n"
            "directives: d\n"
            "engine: {order: [openrouter, local],"
            " decision_model: cheap/decider, local_model: nimble}\n",
        )
        report = validate_strategy(global_path=tmp_path / "absent.yaml", repo_path=full)
        assert report.valid is True
        text = report.format()
        assert "known in the cached decisions catalog" in text
        assert "engine: local model nimble — ok" in text


class TestBoolLevelNormalization:
    def test_false_level_parses_to_off_string(self):
        candidate = routing_mod._parse_candidate(
            {"id": "x", "levels": ["auto", False]}, 0
        )
        assert candidate is not None
        assert candidate.levels == ["auto", "off"]

    def test_true_level_parses_to_on_string(self):
        candidate = routing_mod._parse_candidate({"id": "x", "levels": [True]}, 0)
        assert candidate is not None
        assert candidate.levels == ["on"]

    def test_unquoted_off_yaml_loads_usable_candidate(self, tmp_path):
        path = _write(
            tmp_path / "routing.yaml",
            _strategy_yaml(candidates="\n  - {id: x, levels: [auto, off]}\n"),
        )
        strategy = load_strategy(global_path=path, repo_path=tmp_path / "absent.yaml")
        assert strategy is not None
        assert [c.id for c in strategy.candidates] == ["x"]
        assert strategy.candidates[0].levels == ["auto", "off"]

    def test_skip_reason_accepts_bool_levels(self):
        assert (
            routing_mod._candidate_skip_reason(
                {"id": "x", "levels": ["auto", False]}, 0
            )
            is None
        )

    def test_int_level_still_skips(self):
        assert (
            routing_mod._candidate_skip_reason({"id": "x", "levels": ["auto", 3]}, 0)
            == "'levels' not a string list"
        )
        assert (
            routing_mod._parse_candidate({"id": "x", "levels": ["auto", 3]}, 0) is None
        )
