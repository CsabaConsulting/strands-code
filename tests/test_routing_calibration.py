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
        assert set(baseline["snapshots"]) == {"local", "openrouter", "native"}
        assert all(baseline["snapshots"].values())
        assert baseline["pins"]["native"] == "jev-1.13.0"
        assert set(baseline["distributions"]) == {"local", "openrouter", "native"}
        assert "derivation" in baseline and len(baseline["derivation"]) > 50
        assert baseline["probe_count"] == 20

    def test_baseline_verdicts_cover_every_probe_on_every_engine(self):
        probe_ids = {p["id"] for p in _load_probes()}
        verdicts = _load_baseline()["verdicts"]
        assert set(verdicts) == {"local", "openrouter", "native"}
        for engine, records in verdicts.items():
            assert len(records) == 20, f"{engine}: {len(records)} verdicts"
            assert set(records) == probe_ids, f"{engine}: id drift"
        for pid in probe_ids:
            assert sorted(verdicts["native"][pid]) == sorted(
                verdicts["openrouter"][pid]
            ), f"{pid}: native record shape drift"

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


def _load_runner():
    spec = importlib.util.spec_from_file_location("route_probe", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canned_record(probe_id):
    return {
        "probe": probe_id,
        "gated": None,
        "detail": "hold for test",
        "top1": "candidate-x",
        "fault": None,
        "had_answers": True,
    }


@pytest.fixture(scope="module")
def driver():
    return _load_driver()


@pytest.fixture(scope="module")
def runner():
    return _load_runner()


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

    def test_rig_exposes_native_scenarios(self, driver):
        for name in ("scenario_n1", "scenario_n2", "scenario_n3", "scenario_n4"):
            assert callable(getattr(driver, name, None)), f"{name} missing"

    def test_native_strategy_advertises_routable_levels(self, driver):
        source = inspect.getsource(driver._native_strategy)
        assert "levels: [auto, off]" in source
        for name in ("scenario_n3", "scenario_n4"):
            scenario = inspect.getsource(getattr(driver, name))
            assert "_native_strategy" in scenario, f"{name} bypasses the helper"

    def test_native_bad_key_uses_bogus_value_only(self, driver):
        assert driver.BOGUS_TYPESAFE_KEY == "probe-bogus-key"
        source = inspect.getsource(driver.scenario_n3)
        assert "BOGUS_TYPESAFE_KEY" in source


class TestLazyLocalTag:
    """GAP-03: cloud runs never touch local-tag resolution (D-06).

    Commits the 08-06 /tmp scratch check as a durable hermetic test:
    a cloud run must complete with a raising resolver. Fails on the
    pre-fix unconditional ``resolve_local_model()`` call in ``cmd_run``.
    """

    def _stub_probes(self, runner, monkeypatch):
        seen = []

        def _fake_run(
            probe, *, engine, decision_model, local_model, native_model=None
        ):
            seen.append(local_model)
            return _canned_record(probe["id"])

        monkeypatch.setattr(runner, "load_probes", lambda: [{"id": "p1"}, {"id": "p2"}])
        monkeypatch.setattr(runner, "run_probe", _fake_run)
        return seen

    def test_cloud_run_completes_with_raising_resolver(
        self, runner, tmp_path, monkeypatch
    ):
        def _boom(base_url=None):
            raise SystemExit("no decision model pulled")

        monkeypatch.setattr(runner, "resolve_local_model", _boom)
        seen = self._stub_probes(runner, monkeypatch)
        out = tmp_path / "cloud.jsonl"
        rc = runner.cmd_run(
            "openrouter", out=out, decision_model="decider", local_model=None
        )
        assert rc == 0
        assert len(out.read_text().splitlines()) == 2
        assert seen == [runner.LOCAL_MODEL_PIN] * 2

    def test_explicit_local_model_honored_on_cloud_path(
        self, runner, tmp_path, monkeypatch
    ):
        def _boom(base_url=None):
            raise SystemExit("resolver must not fire")

        monkeypatch.setattr(runner, "resolve_local_model", _boom)
        seen = self._stub_probes(runner, monkeypatch)
        rc = runner.cmd_run(
            "openrouter",
            out=tmp_path / "cloud.jsonl",
            decision_model="decider",
            local_model="custom:tag",
        )
        assert rc == 0
        assert seen == ["custom:tag"] * 2

    def test_local_run_still_resolves_and_warms(self, runner, tmp_path, monkeypatch):
        monkeypatch.setattr(
            runner, "resolve_local_model", lambda base_url=None: "resolved:tag"
        )
        warmed = []
        monkeypatch.setattr(runner, "_warm_local", warmed.append)
        seen = self._stub_probes(runner, monkeypatch)
        rc = runner.cmd_run(
            "local",
            out=tmp_path / "local.jsonl",
            decision_model="decider",
            local_model=None,
        )
        assert rc == 0
        assert warmed == ["resolved:tag"]
        assert seen == ["resolved:tag"] * 2


class TestNativeProbeArm:
    """09-03: --run native dispatch plus the native fault set.

    All hermetic: the native transport is stubbed, so no live key is
    needed. Fault arms use bogus key values only, never real ones.
    """

    PROBE = {
        "id": "t-native-dispatch",
        "ask": "What is the default decision timeout in seconds?",
        "side": False,
        "acceptable": ["cheap"],
        "expected": "route",
        "category": "critical",
    }
    CANNED = {
        "type": "choice",
        "choice": "anthropic/claude-haiku-4-5",
        "probabilities": {
            "anthropic/claude-haiku-4-5": 0.95,
            "anthropic/claude-sonnet-4-5": 0.04,
            "anthropic/claude-opus-4-5": 0.01,
        },
        "confidence": 0.8,
    }

    def _stub_transport(self, runner, monkeypatch, seen):
        def _fake(*, native_model, state, questions, **kwargs):
            seen.append(
                {
                    "native_model": native_model,
                    "state": state,
                    "questions": questions,
                    "kwargs": kwargs,
                }
            )
            return routing_mod.EngineResult(
                answers={"pick_model": dict(self.CANNED)},
                input_tokens=100,
                output_tokens=5,
                cost=100 * 0.042 / 1_000_000,
                model="jev-1.13.0",
            )

        monkeypatch.setattr(runner, "decide_via_typesafe", _fake)

    def test_native_dispatch_calls_production_transport(self, runner, monkeypatch):
        seen = []
        self._stub_transport(runner, monkeypatch, seen)
        record = runner.run_probe(
            dict(self.PROBE),
            engine="native",
            decision_model="decider",
            local_model="nimble",
        )
        assert len(seen) == 1
        call = seen[0]
        assert call["native_model"] == runner.NATIVE_MODEL_PIN
        assert set(call["state"]) == {"ask", "directives", "side"}
        assert set(call["questions"]) == {"pick_model"}
        assert call["kwargs"] == {}
        assert record["engine"] == "native"
        assert record["pin"] == runner.NATIVE_MODEL_PIN
        assert record["snapshot"] == "jev-1.13.0"
        assert record["gated"] == "anthropic/claude-haiku-4-5"
        assert record["match"] is True

    def test_native_arm_passes_timeout_only_no_base_override(
        self, runner, monkeypatch
    ):
        seen = []
        self._stub_transport(runner, monkeypatch, seen)
        probe = dict(self.PROBE, fault="timeout")
        record = runner.run_probe(
            probe,
            engine="native",
            decision_model="decider",
            local_model="nimble",
        )
        assert seen[0]["kwargs"] == {"timeout": 0.001}
        assert "local_base_url" not in seen[0]["kwargs"]
        assert record["fault"] == "timeout"

    def test_native_unknown_model_override_reaches_transport(
        self, runner, monkeypatch
    ):
        seen = []
        self._stub_transport(runner, monkeypatch, seen)
        probe = dict(self.PROBE, fault={"native": "unknown-model"})
        runner.run_probe(
            probe,
            engine="native",
            decision_model="decider",
            local_model="nimble",
        )
        assert seen[0]["native_model"] == "probe-no-such-model-xyz"

    def test_native_bad_key_restores_key_byte_identically(
        self, runner, monkeypatch
    ):
        monkeypatch.setenv("TYPESAFE_API_KEY", "sentinel-value-xyz")
        with runner._FaultContext("bad-key", "native"):
            import os

            assert os.environ["TYPESAFE_API_KEY"] == "probe-bogus-key"
        import os

        assert os.environ["TYPESAFE_API_KEY"] == "sentinel-value-xyz"

    def test_native_no_key_restores_presence_and_absence(
        self, runner, monkeypatch
    ):
        import os

        monkeypatch.setenv("TYPESAFE_API_KEY", "sentinel-value-xyz")
        with runner._FaultContext("no-key", "native"):
            assert "TYPESAFE_API_KEY" not in os.environ
        assert os.environ["TYPESAFE_API_KEY"] == "sentinel-value-xyz"
        monkeypatch.delenv("TYPESAFE_API_KEY")
        with runner._FaultContext("no-key", "native"):
            assert "TYPESAFE_API_KEY" not in os.environ
        assert "TYPESAFE_API_KEY" not in os.environ

    def test_native_fault_records_carry_no_key_material(
        self, runner, monkeypatch
    ):
        import os

        monkeypatch.setenv("TYPESAFE_API_KEY", "sentinel-value-xyz")
        seen = []
        self._stub_transport(runner, monkeypatch, seen)
        probe = dict(self.PROBE, fault={"native": "bad-key"})
        record = runner.run_probe(
            probe,
            engine="native",
            decision_model="decider",
            local_model="nimble",
        )
        dumped = json.dumps(record)
        assert "probe-bogus-key" not in dumped
        assert "sentinel-value-xyz" not in dumped
        assert os.environ["TYPESAFE_API_KEY"] == "sentinel-value-xyz"

    def test_calibration_strategy_carries_native_model(self, runner):
        strategy, _ = runner.calibration_strategy(
            single=False,
            decision_model="decider",
            local_model="nimble",
            native_model="jev-1.13.0",
        )
        assert strategy.engine.native_model == "jev-1.13.0"

    def test_native_run_takes_cloud_path_without_resolver_or_warmup(
        self, runner, tmp_path, monkeypatch
    ):
        def _boom(base_url=None):
            raise SystemExit("resolver must not fire")

        def _warm_boom(tag):
            raise SystemExit("warmup must not fire")

        monkeypatch.setattr(runner, "resolve_local_model", _boom)
        monkeypatch.setattr(runner, "_warm_local", _warm_boom)
        seen = []

        def _fake_run(
            probe, *, engine, decision_model, local_model, native_model=None
        ):
            seen.append((engine, native_model))
            return _canned_record(probe["id"])

        monkeypatch.setattr(runner, "load_probes", lambda: [{"id": "p1"}])
        monkeypatch.setattr(runner, "run_probe", _fake_run)
        rc = runner.cmd_run(
            "native",
            out=tmp_path / "native.jsonl",
            decision_model="decider",
            local_model=None,
        )
        assert rc == 0
        assert seen == [("native", runner.NATIVE_MODEL_PIN)]

    def test_dry_run_lists_native_engine(self, runner, capsys):
        assert runner.cmd_dry_run() == 0
        assert "native" in capsys.readouterr().out
