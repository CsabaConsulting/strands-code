"""UAT rig routing-area contract tests (Phase 12 rig split, D-14).

Re-homed pins over the shared Bedrock profile-form id, the fail-fast
waits, and the r1/r2/r3/r4 scenarios. Wait behavior plus the pane_text
monkeypatch target live in the shared library (D-13); scenario sources
live in the per-area module behind the thin driver dispatch (D-14).
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DRIVER = REPO_ROOT / "scripts" / "uattest" / "driver.py"
LIB = REPO_ROOT / "scripts" / "uattest" / "uattest_lib.py"
ROUTING = REPO_ROOT / "scripts" / "uattest" / "scenarios_routing.py"

PROFILE_FORM = "bedrock/us.amazon.nova-micro-v1:0"
BARE_FORM = "bedrock/amazon.nova-micro-v1:0"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lib = _load("uattest_lib", LIB)
routing = _load("scenarios_routing", ROUTING)


class TestRigModelId:
    def test_shared_constant_is_profile_form(self):
        assert lib.RIG_NOVA_MICRO == PROFILE_FORM

    def test_no_bare_form_in_driver_source(self):
        for path in (DRIVER, ROUTING):
            lines = [
                ln for ln in path.read_text().splitlines() if not ln.startswith("#")
            ]
            hits = [ln for ln in lines if BARE_FORM in ln]
            assert hits == [], f"bare form in {path.name}"

    def test_scenarios_build_from_shared_constant(self):
        for name in ("scenario_r2", "scenario_r3", "scenario_r4"):
            src = inspect.getsource(getattr(routing, name))
            assert "RIG_NOVA_MICRO" in src, f"{name} does not use the shared constant"
            assert BARE_FORM not in src, f"{name} still hardcodes the bare id"

    def test_docs_example_uses_profile_form(self):
        docs = (REPO_ROOT / "docs" / "ROUTING.md").read_text()
        assert PROFILE_FORM in docs
        hits = [
            ln
            for ln in docs.splitlines()
            if BARE_FORM in ln and not ln.strip().startswith("#")
        ]
        assert hits == []


FAILED_TURN = (
    "Routed \u2192 bedrock/us.amazon.nova-micro-v1:0 (off): model 68%, effort 100%\n"
    "Turn failed (ValidationException): Invocation of model ID "
    "amazon.nova-micro-v1:0 with on-demand throughput isn't supported.\n"
    "> "
)
CLEAN_MAIN_END = "turn output\n(12%) $0.0012\n> "
NA_WINDOW_MAIN_END = "turn output\n4.49K (n/a) $0.00\n> "
CLEAN_ROUTED = (
    "Routed \u2192 bedrock/us.amazon.nova-micro-v1:0 (off): model 68%, effort 100%\n> "
)


class TestFailFast:
    def test_wait_main_end_aborts_on_failed_turn(self, monkeypatch):
        monkeypatch.setattr(lib, "pane_text", lambda sess: FAILED_TURN)
        with pytest.raises(AssertionError) as excinfo:
            lib.wait_main_end("sess", timeout=1)
        msg = str(excinfo.value)
        assert "main-end" in msg
        assert "Turn failed (ValidationException)" in msg
        assert "TIMEOUT" not in msg

    def test_wait_routed_aborts_on_failed_turn(self, monkeypatch):
        monkeypatch.setattr(lib, "pane_text", lambda sess: FAILED_TURN)
        with pytest.raises(AssertionError) as excinfo:
            lib.wait_routed("sess", 1, "routed-line")
        msg = str(excinfo.value)
        assert "routed-line" in msg
        assert "Turn failed (ValidationException)" in msg
        assert "TIMEOUT" not in msg

    def test_wait_main_end_clean_transcript_unchanged(self, monkeypatch):
        monkeypatch.setattr(lib, "pane_text", lambda sess: CLEAN_MAIN_END)
        text, served = lib.wait_main_end("sess", timeout=1)
        assert text == CLEAN_MAIN_END
        assert served is False

    def test_wait_main_end_accepts_unknown_window_cost_line(self, monkeypatch):
        monkeypatch.setattr(lib, "pane_text", lambda sess: NA_WINDOW_MAIN_END)
        text, served = lib.wait_main_end("sess", timeout=1)
        assert text == NA_WINDOW_MAIN_END
        assert served is False

    def test_wait_routed_clean_transcript_unchanged(self, monkeypatch):
        monkeypatch.setattr(lib, "pane_text", lambda sess: CLEAN_ROUTED)
        text, marker = lib.wait_routed("sess", 1, "routed-line")
        assert text == CLEAN_ROUTED
        assert marker is None

    def test_fail_fast_diagnostic_truncates_long_failed_line(self, monkeypatch):
        long_line = "Turn failed (" + "E" * 300 + ")"
        monkeypatch.setattr(lib, "pane_text", lambda sess: long_line + "\n> ")
        with pytest.raises(AssertionError) as excinfo:
            lib.wait_main_end("sess", timeout=1)
        echoed = str(excinfo.value).split("main-end: ", 1)[1]
        assert echoed == long_line[:200]
        assert len(echoed) == 200

    def test_cost_line_shape_contract(self):
        assert lib.COST_RE.findall(CLEAN_MAIN_END) != []
        assert lib.COST_RE.findall(NA_WINDOW_MAIN_END) != []
        assert lib.COST_RE.findall("turn output\n> ") == []
        assert lib.COST_RE.findall("estimate (soon) $5\n> ") == []
        assert lib.COST_RE.findall("(12) $0.0012\n> ") == []


class TestWaitForNewBaseline:
    def test_caller_baseline_catches_instant_reply(self, monkeypatch):
        # Instant local reply already in the pane (it beat the
        # post-send snapshot): a pre-send baseline still detects it.
        monkeypatch.setattr(lib, "pane_text", lambda sess: "Routing on\n> ")
        text = lib.wait_for_new("sess", r"Routing on", 1, "on", before=0)
        assert "Routing on" in text

    def test_default_snapshot_unchanged(self, monkeypatch):
        panes = iter(["none\n> ", "Routing on\n> "])
        monkeypatch.setattr(
            lib, "pane_text", lambda sess: next(panes, "Routing on\n> ")
        )
        text = lib.wait_for_new("sess", r"Routing on", 5, "on", poll=0)
        assert "Routing on" in text


class TestR3CostBaselines:
    def test_no_post_wait_cost_snapshot(self):
        src = inspect.getsource(routing.scenario_r3)
        assert "after=len(COST_RE.findall(pane_text(sess)))" not in src

    def test_off_baseline_is_pre_send(self):
        src = inspect.getsource(routing.scenario_r3)
        assert src.index("after_cost = ") < src.index('"Reply with exactly: offcheck"')


class TestRoutingScenarios:
    def test_dispatch_lists_routing_scenarios(self):
        src = DRIVER.read_text()
        assert '"r1"' in src and '"r2"' in src and '"r3"' in src and '"r4"' in src
