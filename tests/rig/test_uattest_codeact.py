"""UAT rig codeact-area contract tests (Phase 12 rig split, D-14).

Re-homed pins over the a1/a2 scenarios behind the thin driver
dispatch; the start_cli signature check follows start_cli into the
shared library (D-13). Loaded via importlib since the rig has no
package path (CF-07).
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DRIVER = REPO_ROOT / "scripts" / "uattest" / "driver.py"
LIB = REPO_ROOT / "scripts" / "uattest" / "uattest_lib.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lib = _load("uattest_lib", LIB)
codeact = _load("uattest_driver", DRIVER)


class TestCodeactRig:
    def test_scenarios_exist(self):
        assert callable(codeact.scenario_a1)
        assert callable(codeact.scenario_a2)

    def test_dispatch_lists_codeact_scenarios(self):
        src = DRIVER.read_text()
        assert '"a1"' in src and '"a2"' in src

    def test_start_cli_accepts_cli_args(self):
        assert "cli_args" in inspect.signature(lib.start_cli).parameters

    def test_a1_fails_fast_on_bare_flag_rejection(self):
        src = inspect.getsource(codeact.scenario_a1)
        assert "requires an argument" in src
        assert "A1 PASS" in src

    def test_a2_asserts_labels_and_unshaped_tool_turn(self):
        src = inspect.getsource(codeact.scenario_a2)
        assert "interface: codeact" in src
        assert "interface: tool" in src
        assert "[Tool] python_repl" in src
        assert "A2 PASS" in src
