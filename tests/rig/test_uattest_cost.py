"""UAT rig cost-area contract tests (Phase 12 rig split, D-14).

Re-homed pins over the shared OpenRouter id plus the actual-marker and
split-line regexes the c1/c2 scenarios assert. Loaded via importlib
since the rig has no package path (CF-07).
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DRIVER = REPO_ROOT / "scripts" / "uattest" / "driver.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cost = _load("uattest_driver", DRIVER)


class TestReportedSpendRig:
    def test_shared_id_is_cli_accepted_form(self):
        assert cost.CHEAP_OPENROUTER_ID == "litellm/openrouter/openai/gpt-4o-mini"

    def test_scenarios_use_shared_id(self):
        for name in ("scenario_c1", "scenario_c2"):
            src = inspect.getsource(getattr(cost, name))
            assert "CHEAP_OPENROUTER_ID" in src, f"{name} hardcodes the model id"

    def test_actual_usage_marker(self):
        assert cost.ACTUAL_USAGE_RE.search("6.00K (5%) $0.00 actual\n")
        assert not cost.ACTUAL_USAGE_RE.search("6.00K (5%) $0.00\n")

    def test_actual_row_marker(self):
        assert cost.ACTUAL_ROW_RE.search("Turn 1 ... $0.0024 actual\n")
        assert not cost.ACTUAL_ROW_RE.search("Turn 1 ... $0.0024\n")

    def test_split_line(self):
        assert cost.SPLIT_RE.search("  (actual $0.0024 + estimated $0.0100)\n")
        assert not cost.SPLIT_RE.search("Total $0.0124\n")


class TestCostScenarios:
    def test_dispatch_lists_cost_scenarios(self):
        src = DRIVER.read_text()
        assert '"c1"' in src and '"c2"' in src
