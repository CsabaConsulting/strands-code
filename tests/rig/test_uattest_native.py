"""UAT rig native-area contract tests (Phase 12 rig split, D-14).

Re-homed pins over the native strategy helper plus the n1/n2/n3/n4
scenarios behind the thin driver dispatch. Loaded via importlib since
the rig has no package path (CF-07).
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DRIVER = REPO_ROOT / "scripts" / "uattest" / "driver.py"
NATIVE = REPO_ROOT / "scripts" / "uattest" / "scenarios_native.py"

BARE_FORM = "bedrock/amazon.nova-micro-v1:0"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


native = _load("scenarios_native", NATIVE)


class TestRigModelId:
    def test_native_helper_builds_from_shared_constant(self):
        src = inspect.getsource(native._native_strategy)
        assert "RIG_NOVA_MICRO" in src
        assert BARE_FORM not in src


class TestNativeScenarios:
    def test_scenarios_exist(self):
        assert callable(native.scenario_n1)
        assert callable(native.scenario_n2)
        assert callable(native.scenario_n3)
        assert callable(native.scenario_n4)

    def test_dispatch_lists_native_scenarios(self):
        src = DRIVER.read_text()
        assert '"n1"' in src and '"n2"' in src and '"n3"' in src and '"n4"' in src
