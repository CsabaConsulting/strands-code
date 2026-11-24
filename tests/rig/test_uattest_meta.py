"""UAT rig Meta Model API contract tests (Phase 16 live-tmux m1).

Pins over scenarios_meta.py behind the thin driver dispatch.
Loaded via importlib since scripts/uattest has no package path.
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DRIVER = REPO_ROOT / "scripts" / "uattest" / "driver.py"
META_SCENARIOS = REPO_ROOT / "scripts" / "uattest" / "scenarios_meta.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestMetaRig:
    def test_scenario_m1_exists_and_driver_dispatches_m1(self):
        mod = _load("scenarios_meta", META_SCENARIOS)
        assert callable(mod.scenario_m1)
        src = DRIVER.read_text(encoding="utf-8")
        assert '"m1": scenario_m1' in src

    def test_scenario_m1_contract_constants_and_isolation(self):
        mod = _load("scenarios_meta", META_SCENARIOS)
        assert mod.RIG_META_PRIMARY == "meta/muse-spark-1.3-contributor"
        assert mod.RIG_META_SECONDARY == "meta/muse-ember-1.0"
        m1_src = inspect.getsource(mod.scenario_m1)
        assert "_run_provider_rig" in m1_src
        assert "RIG_META_PRIMARY" in m1_src
        assert "RIG_META_SECONDARY" in m1_src
        assert "META_SENTINEL_16" in m1_src
        assert "of 1.05M" in m1_src
        assert "M1 PASS" in m1_src
