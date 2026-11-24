"""UAT rig OpenAI & Anthropic contract tests (Phase 15 live-tmux o1 & an1).

Pins over scenarios_openai_anthropic.py behind the thin driver dispatch.
Loaded via importlib since scripts/uattest has no package path.
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DRIVER = REPO_ROOT / "scripts" / "uattest" / "driver.py"
OA_ANTHROPIC = REPO_ROOT / "scripts" / "uattest" / "scenarios_openai_anthropic.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestOpenAIAnthropicRig:
    def test_scenarios_exist_and_driver_dispatches_o1_and_an1(self):
        mod = _load("scenarios_openai_anthropic", OA_ANTHROPIC)
        assert callable(mod.scenario_o1)
        assert callable(mod.scenario_an1)
        src = DRIVER.read_text(encoding="utf-8")
        assert '"a1": scenario_a1' in src
        assert '"a2": scenario_a2' in src
        assert '"g1": scenario_g1' in src
        assert '"o1": scenario_o1' in src
        assert '"an1": scenario_an1' in src

    def test_scenario_o1_and_an1_contract_constants_and_isolation(self):
        mod = _load("scenarios_openai_anthropic", OA_ANTHROPIC)
        assert mod.RIG_OPENAI_PRIMARY == "openai/gpt-6.1-sol"
        assert mod.RIG_OPENAI_SECONDARY == "openai/gpt-6.1-terra"
        assert mod.RIG_ANTHROPIC_PRIMARY == "anthropic/claude-sonnet-5-5"
        assert mod.RIG_ANTHROPIC_SECONDARY == "anthropic/claude-haiku-5-5"

        rig_src = inspect.getsource(mod._run_provider_rig)
        for aws_var in (
            "-u AWS_ACCESS_KEY_ID",
            "-u AWS_SECRET_ACCESS_KEY",
            "-u AWS_SESSION_TOKEN",
            "-u AWS_PROFILE",
            "-u AWS_DEFAULT_PROFILE",
        ):
            assert aws_var in rig_src
        for needle in (
            "XDG_CONFIG_HOME",
            "config.yaml",
            "/context",
            "Context — ",
            "_wait_idle_prompt",
            "/cost",
            "Cost — ",
            "Display only",
            "/model ",
        ):
            assert needle in rig_src

        o1_src = inspect.getsource(mod.scenario_o1)
        assert "RIG_OPENAI_PRIMARY" in o1_src
        assert "RIG_OPENAI_SECONDARY" in o1_src
        assert "OPENAI_SENTINEL_15" in o1_src
        assert "1.05M" in o1_src
        assert "O1 PASS" in o1_src

        an1_src = inspect.getsource(mod.scenario_an1)
        assert "RIG_ANTHROPIC_PRIMARY" in an1_src
        assert "RIG_ANTHROPIC_SECONDARY" in an1_src
        assert "ANTHROPIC_SENTINEL_15" in an1_src
        assert "1.00M" in an1_src
        assert "AN1 PASS" in an1_src

    def test_usage_end_regex_matches_cache_aware_usage_lines(self):
        upstream = _load(
            "scenarios_upstream",
            REPO_ROOT / "scripts" / "uattest" / "scenarios_upstream.py",
        )
        assert upstream.USAGE_END_RE.search("turn output\n1.00K (0%) $0.00\n> ")
        assert upstream.USAGE_END_RE.search(
            "turn output\n13.35K (1%, 50% cached) $0.02\n> "
        )
        assert upstream.USAGE_END_RE.search(
            "turn output\n40.60K (4%, 99% cache write) $0.10\n> "
        )
        assert upstream.USAGE_END_RE.search("165.60K (n/a, 75% cached)\n")
        assert not upstream.USAGE_END_RE.search("turn output\n> ")
