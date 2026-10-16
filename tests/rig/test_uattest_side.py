"""UAT rig side-area contract tests (Phase 12 rig split, D-14).

Pins over the s1/s2 scenarios: they stay importable callables behind
the thin driver dispatch. Loaded via importlib since the rig has no
package path (CF-07).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DRIVER = REPO_ROOT / "scripts" / "uattest" / "driver.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


side = _load("uattest_driver", DRIVER)


class TestSideScenarios:
    def test_scenarios_exist(self):
        assert callable(side.scenario_s1)
        assert callable(side.scenario_s2)

    def test_dispatch_lists_side_scenarios(self):
        src = DRIVER.read_text()
        assert '"s1"' in src and '"s2"' in src
