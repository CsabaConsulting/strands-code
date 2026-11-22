"""UAT rig upstream-resync contract tests (Phase 13 live-tmux scenarios).

Pins over scenarios_upstream.py (u1/u2/u3) behind the thin driver
dispatch. Loaded via importlib since scripts/uattest has no package path.
"""

from __future__ import annotations

import importlib.util
import inspect
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DRIVER = REPO_ROOT / "scripts" / "uattest" / "driver.py"
UPSTREAM = REPO_ROOT / "scripts" / "uattest" / "scenarios_upstream.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


upstream = _load("scenarios_upstream", UPSTREAM)


class TestUpstreamRig:
    def test_scenarios_exist(self):
        assert callable(upstream.scenario_u1)
        assert callable(upstream.scenario_u2)
        assert callable(upstream.scenario_u3)

    def test_dispatch_lists_upstream_scenarios(self):
        src = DRIVER.read_text()
        assert '"u1"' in src and '"u2"' in src and '"u3"' in src

    def test_scenarios_use_shared_constants_and_xdg_isolation(self):
        assert upstream.RIG_MISTRAL_2402 == "mistral.mistral-large-2402-v1:0"
        assert upstream.RIG_PIXTRAL_2502 == "us.mistral.pixtral-large-2502-v1:0"
        assert upstream.RIG_SONNET_46 == "bedrock/us.anthropic.claude-sonnet-4-6"
        assert upstream.RIG_NOVA_2_LITE == "bedrock/us.amazon.nova-2-lite-v1:0"
        assert (
            upstream.RIG_HAIKU_45
            == "bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0"
        )
        src_u1 = inspect.getsource(upstream.scenario_u1)
        src_u2 = inspect.getsource(upstream.scenario_u2)
        src_u3 = inspect.getsource(upstream.scenario_u3)
        assert "RIG_MISTRAL_2402" in src_u1 and "RIG_PIXTRAL_2502" in src_u1
        assert "RIG_SONNET_46" in src_u2 and "RIG_NOVA_2_LITE" in src_u2
        assert "RIG_HAIKU_45" in src_u3
        for src in (src_u1, src_u2, src_u3):
            assert "XDG_CONFIG_HOME" in src

    def test_usage_end_regex_matches_priced_and_unpriced_lines(self):
        assert upstream.USAGE_END_RE.search("turn output\n  1.00K (1%) $0.00\n> ")
        assert upstream.USAGE_END_RE.search("turn output\n1.00K (0%)\n> ")
        assert upstream.USAGE_END_RE.search("  4.49K (n/a) $0.00\n")
        assert upstream.USAGE_END_RE.search("  6.00K (5%) $0.00 actual\n")
        assert not upstream.USAGE_END_RE.search("turn output\n> ")

    def test_scenario_contracts(self):
        u1 = inspect.getsource(upstream.scenario_u1)
        assert "streaming disabled for" in u1
        assert "UNARY_TOOL_SENTINEL_13" in u1
        assert "model-capabilities.yaml" not in u1
        assert "_write_xdg_capabilities" not in u1
        assert "U1 PASS" in u1

        u2 = inspect.getsource(upstream.scenario_u2)
        assert "--session-id" in u2
        assert "of 1.00M" in u2
        assert "_wait_idle_prompt" in u2
        assert "391" in u2
        assert "U2 PASS" in u2

        u3 = inspect.getsource(upstream.scenario_u3)
        hitl_pat = r"Approve\? \[main\] shell — echo HITL_OK_13"
        assert hitl_pat in u3
        assert re.search(hitl_pat, "| Approve? [main] shell — echo HITL_OK_13 |")
        assert not re.search(hitl_pat, "| Approve? [main] shell — uname -a |")
        assert "Denied by policy rule" in u3
        assert "/mode plan" in u3
        assert "U3 PASS" in u3
