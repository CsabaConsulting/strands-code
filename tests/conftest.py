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
    "LITELLM_BASE_URL",
    "OLLAMA_HOST",
    "OLLAMA_API_KEY",
    "OLLAMA_TEST_MODEL",
    "TYPESAFE_API_KEY",
    "JEV_API_KEY",
    "STRANDS_BOX",
    "STRANDS_BOX_BIN",
    "EXPERIMENTAL_X86_SUPPORT",
    "AWS_BEARER_TOKEN_BEDROCK",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_PROFILE",
    "AWS_DEFAULT_PROFILE",
    "AWS_REGION",
    "AWS_DEFAULT_REGION",
    "AWS_CONFIG_FILE",
    "AWS_SHARED_CREDENTIALS_FILE",
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
def _hermetic_provider_env(monkeypatch, request, tmp_path_factory):
    """Strip ambient provider creds & redirect XDG/cache dirs outside tmp_path."""
    if request.node.get_closest_marker("integration") is not None:
        yield
        return
    for name in _PROVIDER_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    xdg_root = tmp_path_factory.mktemp("xdg")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_root / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(xdg_root / "cache"))
    monkeypatch.setenv("STRANDS_CODE_CACHE_DIR", str(xdg_root / "strands_cache"))
    yield
