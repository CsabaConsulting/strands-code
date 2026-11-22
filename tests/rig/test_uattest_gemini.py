"""UAT rig Google Gemini contract tests (Phase 14 live-tmux g1 scenario).

Pins over scenarios_gemini.py behind the thin driver dispatch. Loaded via
importlib since scripts/uattest has no package path.
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DRIVER = REPO_ROOT / "scripts" / "uattest" / "driver.py"
GEMINI = REPO_ROOT / "scripts" / "uattest" / "scenarios_gemini.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestGeminiRig:
    def test_scenario_exists_and_driver_dispatches_g1(self):
        gemini = _load("scenarios_gemini", GEMINI)
        assert callable(gemini.scenario_g1)
        src = DRIVER.read_text(encoding="utf-8")
        assert '"g1": scenario_g1' in src

    def test_scenario_g1_contract_constants_zero_aws_and_xdg_isolation(self):
        gemini = _load("scenarios_gemini", GEMINI)
        assert gemini.RIG_GEMINI_FLASH == "google/gemini-2.5-flash"
        assert gemini.RIG_GEMINI_PRO == "google/gemini-2.5-pro"

        src = inspect.getsource(gemini.scenario_g1)
        for aws_var in (
            "-u AWS_ACCESS_KEY_ID",
            "-u AWS_SECRET_ACCESS_KEY",
            "-u AWS_SESSION_TOKEN",
            "-u AWS_PROFILE",
            "-u AWS_DEFAULT_PROFILE",
        ):
            assert aws_var in src
        assert "XDG_CONFIG_HOME" in src
        assert "--model {RIG_GEMINI_FLASH}" in src
        assert "config.yaml" in src
        assert "GEMINI_SENTINEL_14" in src
        assert "/context" in src
        assert "Context — {RIG_GEMINI_FLASH}" in src
        assert "1.05M" in src and "1.00M" in src
        assert "/cost" in src
        assert "Cost — {RIG_GEMINI_FLASH}" in src
        assert "Display only" in src
        assert "RIG_GEMINI_PRO" in src
        assert "Dropping reasoningContent" in src
        assert "G1 PASS" in src
