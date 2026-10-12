"""UAT rig driver contract tests (Phase 08 gap closure G-08-1).

Hermetic pins over scripts/uattest/driver.py: the rig must route to the
invokable Bedrock profile-form id from a single shared constant, and the
routed waits must fail fast on failed turns instead of hanging to
timeout. Loaded via importlib since the driver has no package path
(precedent: tests/test_routing_calibration.py _load_driver).
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DRIVER = REPO_ROOT / "scripts" / "uattest" / "driver.py"

PROFILE_FORM = "bedrock/us.amazon.nova-micro-v1:0"
BARE_FORM = "bedrock/amazon.nova-micro-v1:0"


def _load_driver():
    spec = importlib.util.spec_from_file_location("uattest_driver", DRIVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


driver = _load_driver()


class TestRigModelId:
    def test_shared_constant_is_profile_form(self):
        assert driver.RIG_NOVA_MICRO == PROFILE_FORM

    def test_no_bare_form_in_driver_source(self):
        lines = [ln for ln in DRIVER.read_text().splitlines() if not ln.startswith("#")]
        hits = [ln for ln in lines if BARE_FORM in ln]
        assert hits == []

    def test_scenarios_build_from_shared_constant(self):
        for name in ("scenario_r2", "scenario_r3", "scenario_r4"):
            src = inspect.getsource(getattr(driver, name))
            assert "RIG_NOVA_MICRO" in src, f"{name} does not use the shared constant"
            assert BARE_FORM not in src, f"{name} still hardcodes the bare id"
