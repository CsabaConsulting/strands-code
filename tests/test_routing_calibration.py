"""Calibration probe + UAT rig contract tests (Phase 08 Nyquist audit fill).

Closes the hermetic gaps the 08-05 SUMMARY verified only by hand-run CLI
commands (probe dry-run/run/compare, probe composition, baseline-vs-code
knob equality, promptfoo-or-fallback) plus a static contract guard over
the r2/r3/r4 rig scenarios whose live runs stay manual-only.

All tests here are hermetic: no network, no tmux, no credentials.
Live behavior stays covered by TestLiveEngines (integration-marked)
and the tmux rig (scripts/uattest/driver.py).
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest

import strands_code_cli.routing as routing_mod

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNNER = REPO_ROOT / "scripts" / "route-probe.py"
PROBE_FILE = REPO_ROOT / "evals" / "routing-probe" / "probes.jsonl"
BASELINE_FILE = REPO_ROOT / "evals" / "routing-probe" / "baseline.json"
PROMPTFOO_CONFIG = REPO_ROOT / "evals" / "routing-probe" / "promptfooconfig.yaml"
DRIVER = REPO_ROOT / "scripts" / "uattest" / "driver.py"


def _load_probes():
    return [json.loads(line) for line in PROBE_FILE.read_text().splitlines() if line.strip()]


def _load_baseline():
    return json.loads(BASELINE_FILE.read_text())


def _load_driver():
    spec = importlib.util.spec_from_file_location("uattest_driver", DRIVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestProbeRunner:
    def test_dry_run_lists_twenty_probe_ids_with_zero_exit(self):
        proc = subprocess.run(
            [sys.executable, str(RUNNER), "--dry-run"],
            capture_output=True, text=True, timeout=120, cwd=REPO_ROOT,
        )
        assert proc.returncode == 0, proc.stderr
        assert "probes: 20" in proc.stdout
        probe_ids = {p["id"] for p in _load_probes()}
        assert len(probe_ids) == 20
        for pid in probe_ids:
            assert pid in proc.stdout, f"dry-run omits probe {pid}"

    def test_runner_reuses_production_decision_stack(self):
        source = RUNNER.read_text()
        for symbol in (
            "build_decision_state",
            "decide_via_openrouter",
            "decide_via_ollama",
            "gate_model",
        ):
            assert symbol in source, f"runner bypasses production {symbol}"

    def test_probe_paths_are_trackable_not_ignored(self):
        proc = subprocess.run(
            ["git", "check-ignore", str(RUNNER), str(PROBE_FILE)],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert proc.returncode == 1, "probe runner or probe set is git-ignored"


class TestProbeComposition:
    EXPECTED_FIELDS = {"id", "ask", "side", "acceptable", "expected", "category"}

    def test_probe_set_matches_ai_spec_composition(self):
        from collections import Counter

        counts = Counter(p["category"] for p in _load_probes())
        assert counts == {"critical": 6, "edge": 6, "failure": 5, "adversarial": 3}

    def test_each_probe_carries_label_fields(self):
        for probe in _load_probes():
            missing = self.EXPECTED_FIELDS - set(probe)
            assert not missing, f"{probe.get('id')}: missing {missing}"
            assert isinstance(probe["side"], bool)
            assert isinstance(probe["acceptable"], list)
            assert probe["expected"] in {"route", "hold", "effort-route", "route-or-hold"}

    def test_probe_ids_are_unique(self):
        ids = [p["id"] for p in _load_probes()]
        assert len(ids) == len(set(ids)) == 20


class TestCalibrationBaseline:
    def test_shipped_knobs_equal_baseline_derived_values(self):
        derived = _load_baseline()["derived"]
        assert routing_mod.DEFAULT_CONFIDENCE_THRESHOLD == derived["confidence_threshold"]
        assert routing_mod.DEFAULT_TIE_MARGIN == derived["tie_margin"]

    def test_baseline_records_snapshots_distributions_and_derivation(self):
        baseline = _load_baseline()
        assert set(baseline["snapshots"]) == {"local", "openrouter"}
        assert all(baseline["snapshots"].values())
        assert set(baseline["distributions"]) == {"local", "openrouter"}
        assert "derivation" in baseline and len(baseline["derivation"]) > 50
        assert baseline["probe_count"] == 20

    def test_baseline_verdicts_cover_every_probe_on_both_engines(self):
        probe_ids = {p["id"] for p in _load_probes()}
        verdicts = _load_baseline()["verdicts"]
        assert set(verdicts) == {"local", "openrouter"}
        for engine, records in verdicts.items():
            assert len(records) == 20, f"{engine}: {len(records)} verdicts"
            assert set(records) == probe_ids, f"{engine}: id drift"

    def test_no_provisional_markers_remain_in_routing(self):
        for line in routing_mod.__file__ and Path(routing_mod.__file__).read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert "PROVISIONAL" not in line

    def test_calibration_artifacts_carry_no_secret_values(self):
        for path in (PROBE_FILE, BASELINE_FILE):
            text = path.read_text()
            assert "sk-or-v1" not in text, f"{path.name} leaks a key prefix"


class TestRegressionPath:
    def test_promptfoo_config_or_compare_fallback_exists(self):
        if PROMPTFOO_CONFIG.exists():
            assert "probes.jsonl" in PROMPTFOO_CONFIG.read_text()
        else:
            docstring = RUNNER.read_text()
            assert "compare-mode fallback" in docstring
            assert "--compare" in docstring


@pytest.fixture(scope="module")
def driver():
    return _load_driver()


class TestRigScenarioContracts:
    """Static guards over r2/r3/r4 (live runs stay manual-only)."""

    def test_driver_compiles(self):
        proc = subprocess.run(
            [sys.executable, "-m", "py_compile", str(DRIVER)],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr

    def test_rig_exposes_all_four_routing_scenarios(self, driver):
        for name in ("scenario_r1", "scenario_r2", "scenario_r3", "scenario_r4"):
            assert callable(getattr(driver, name, None)), f"{name} missing"

    def test_r2_asserts_zero_local_spend(self, driver):
        source = inspect.getsource(driver.scenario_r2)
        assert "via local" in source
        assert r"via local \$0\.0000" in source

    def test_r3_asserts_both_confidences_and_hold_shape(self, driver):
        source = inspect.getsource(driver.scenario_r3)
        assert "routed_line_with_confidences" in source
        assert "HOLD_NOTE_RE" in source

    def test_r4_asserts_side_headed_routed_line(self, driver):
        source = inspect.getsource(driver.scenario_r4)
        assert "side=True" in source
        assert "(btw)" in source
        assert "routed_line_with_confidences" in source

    def test_rig_strategies_advertise_routable_levels(self, driver):
        for name in ("scenario_r2", "scenario_r3", "scenario_r4"):
            source = inspect.getsource(getattr(driver, name))
            assert "levels: [auto, off]" in source, f"{name} lacks levels"

    def test_rig_rejects_key_material_in_strategy_files(self, driver):
        source = inspect.getsource(driver.scenario_r1)
        assert '"api_key" not in saved' in source
