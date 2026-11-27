"""Suite-wide hermetic guard: live price layers stay off unless a test opts in."""

import pytest

_PROVIDER_ENV_VARS = (
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_GENAI_USE_ENTERPRISE",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "MODEL_API_KEY",
    "META_API_KEY",
    "META_BASE_URL",
    "OPENROUTER_API_KEY",
    "LITELLM_API_KEY",
    "TYPESAFE_API_KEY",
    "JEV_API_KEY",
    "STRANDS_BOX",
    "STRANDS_BOX_BIN",
    "EXPERIMENTAL_X86_SUPPORT",
    "AWS_BEARER_TOKEN_BEDROCK",
    "GITHUB_TOKEN",
    "GH_TOKEN",
)


@pytest.fixture(autouse=True)
def _no_live_pricing(monkeypatch):
    """Disable network price/window layers for every test by default.

    Tests for the live layers themselves (tests/test_live_pricing.py)
    delete this variable and fake the fetchers; everything else keeps
    the pre-live static behavior hermetically.
    """
    monkeypatch.setenv("STRANDS_CODE_NO_LIVE_PRICING", "1")
    yield


@pytest.fixture(autouse=True)
def _hermetic_provider_env(monkeypatch, request):
    """Strip ambient provider credentials so host env keys never leak into tests."""
    if request.node.get_closest_marker("integration") is not None:
        yield
        return
    for name in _PROVIDER_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    yield
