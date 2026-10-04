"""Suite-wide hermetic guard: live price layers stay off unless a test opts in."""

import os

import pytest


@pytest.fixture(autouse=True)
def _no_live_pricing(monkeypatch):
    """Disable network price/window layers for every test by default.

    Tests for the live layers themselves (tests/test_live_pricing.py)
    delete this variable and fake the fetchers; everything else keeps
    the pre-live static behavior hermetically.
    """
    monkeypatch.setenv("STRANDS_CODE_NO_LIVE_PRICING", "1")
    yield
