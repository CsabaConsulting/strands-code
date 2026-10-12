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

import pytest

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


FAILED_TURN = (
    "Routed \u2192 bedrock/us.amazon.nova-micro-v1:0 (off): model 68%, effort 100%\n"
    "Turn failed (ValidationException): Invocation of model ID "
    "amazon.nova-micro-v1:0 with on-demand throughput isn't supported.\n"
    "> "
)
CLEAN_MAIN_END = "turn output\n(12%) $0.0012\n> "
NA_WINDOW_MAIN_END = "turn output\n4.49K (n/a) $0.00\n> "
CLEAN_ROUTED = (
    "Routed \u2192 bedrock/us.amazon.nova-micro-v1:0 (off): model 68%, effort 100%\n"
    "> "
)


class TestFailFast:
    def test_wait_main_end_aborts_on_failed_turn(self, monkeypatch):
        monkeypatch.setattr(driver, "pane_text", lambda sess: FAILED_TURN)
        with pytest.raises(AssertionError) as excinfo:
            driver.wait_main_end("sess", timeout=1)
        msg = str(excinfo.value)
        assert "main-end" in msg
        assert "Turn failed (ValidationException)" in msg
        assert "TIMEOUT" not in msg

    def test_wait_routed_aborts_on_failed_turn(self, monkeypatch):
        monkeypatch.setattr(driver, "pane_text", lambda sess: FAILED_TURN)
        with pytest.raises(AssertionError) as excinfo:
            driver.wait_routed("sess", 1, "routed-line")
        msg = str(excinfo.value)
        assert "routed-line" in msg
        assert "Turn failed (ValidationException)" in msg
        assert "TIMEOUT" not in msg

    def test_wait_main_end_clean_transcript_unchanged(self, monkeypatch):
        monkeypatch.setattr(driver, "pane_text", lambda sess: CLEAN_MAIN_END)
        text, served = driver.wait_main_end("sess", timeout=1)
        assert text == CLEAN_MAIN_END
        assert served is False

    def test_wait_main_end_accepts_unknown_window_cost_line(self, monkeypatch):
        monkeypatch.setattr(driver, "pane_text", lambda sess: NA_WINDOW_MAIN_END)
        text, served = driver.wait_main_end("sess", timeout=1)
        assert text == NA_WINDOW_MAIN_END
        assert served is False

    def test_wait_routed_clean_transcript_unchanged(self, monkeypatch):
        monkeypatch.setattr(driver, "pane_text", lambda sess: CLEAN_ROUTED)
        text, marker = driver.wait_routed("sess", 1, "routed-line")
        assert text == CLEAN_ROUTED
        assert marker is None


class TestWaitForNewBaseline:
    def test_caller_baseline_catches_instant_reply(self, monkeypatch):
        # Instant local reply already in the pane (it beat the
        # post-send snapshot): a pre-send baseline still detects it.
        monkeypatch.setattr(driver, "pane_text", lambda sess: "Routing on\n> ")
        text = driver.wait_for_new("sess", r"Routing on", 1, "on", before=0)
        assert "Routing on" in text

    def test_default_snapshot_unchanged(self, monkeypatch):
        panes = iter(["none\n> ", "Routing on\n> "])
        monkeypatch.setattr(
            driver, "pane_text", lambda sess: next(panes, "Routing on\n> ")
        )
        text = driver.wait_for_new("sess", r"Routing on", 5, "on", poll=0)
        assert "Routing on" in text
