"""Provider-aware startup credential preflight and ambient model auto-pick."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping
from typing import Any

import typer

logger = logging.getLogger(__name__)

BEDROCK_SETUP_POINTER = (
    "No AWS credentials found. strands-code runs its model on Amazon Bedrock.\n"
    "Set credentials via the ambient boto3 chain (env vars, ~/.aws/config, or an "
    "IAM role), or set a provider key (GOOGLE_API_KEY / GEMINI_API_KEY, "
    "ANTHROPIC_API_KEY, OPENAI_API_KEY, or OPENROUTER_API_KEY with --model "
    "litellm/openrouter/<vendor>/<model>), then relaunch."
)

_TRUTHY = frozenset({"1", "true", "yes"})

_PROVIDER_ENV_KEYS: dict[str, tuple[str, ...]] = {
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "openrouter": ("OPENROUTER_API_KEY", "LITELLM_API_KEY"),
}

_AMBIENT_DEFAULT_MODELS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("anthropic/claude-sonnet-5-5", ("ANTHROPIC_API_KEY",)),
    ("openai/gpt-6.1-sol", ("OPENAI_API_KEY",)),
)

_LITELLM_ANY_KEYS = (
    "OPENROUTER_API_KEY",
    "LITELLM_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
)


def _nonempty(name: str, env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return bool((source.get(name) or "").strip())


def _is_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def _fail_preflight(message: str) -> None:
    typer.secho(message, err=True, fg=typer.colors.RED)
    raise typer.Exit(code=2)


def _validate_google_env() -> None:
    """Reject mutually exclusive or incomplete Google Vertex configuration."""
    if not _is_truthy("GOOGLE_GENAI_USE_VERTEXAI"):
        return
    if _nonempty("GOOGLE_API_KEY") or _nonempty("GEMINI_API_KEY"):
        _fail_preflight(
            "GOOGLE_GENAI_USE_VERTEXAI and GOOGLE_API_KEY / GEMINI_API_KEY are "
            "mutually exclusive; unset one before launching."
        )
    if not _nonempty("GOOGLE_CLOUD_PROJECT"):
        _fail_preflight(
            "GOOGLE_CLOUD_PROJECT is required when GOOGLE_GENAI_USE_VERTEXAI is set "
            "(also set GOOGLE_CLOUD_LOCATION=global for Gemini 2.5/3.x models)."
        )


def has_google_credentials() -> bool:
    """Return True when valid Gemini API key or Vertex ADC configuration is set."""
    has_key = _nonempty("GOOGLE_API_KEY") or _nonempty("GEMINI_API_KEY")
    if _is_truthy("GOOGLE_GENAI_USE_VERTEXAI"):
        return not has_key and _nonempty("GOOGLE_CLOUD_PROJECT")
    return has_key


def has_openai_credentials(env: Mapping[str, str] | None = None) -> bool:
    """Return True when non-empty OpenAI API key presence is configured."""
    return _nonempty("OPENAI_API_KEY", env)


def has_anthropic_credentials(env: Mapping[str, str] | None = None) -> bool:
    """Return True when non-empty Anthropic API key presence is configured."""
    return _nonempty("ANTHROPIC_API_KEY", env)


def disable_cwd_dotenv() -> None:
    """Block implicit CWD .env auto-loading in third-party dependencies (T-14-02).

    ``smolagents.remote_executors`` and ``litellm._process_defaults`` invoke
    ``dotenv.load_dotenv()`` on import, letting an untrusted repository ``.env``
    populate credential and endpoint env vars silently into ``os.environ``.
    Explicit ``dotenv_path`` or ``stream`` loads still delegate normally.
    """
    try:
        import dotenv
        import dotenv.main as dotenv_main
    except ImportError:
        return

    original = dotenv_main.load_dotenv
    if getattr(original, "_strands_code_cwd_guarded", False):
        return

    def _guarded_load_dotenv(
        dotenv_path: Any = None,
        stream: Any = None,
        *args: Any,
        **kwargs: Any,
    ) -> bool:
        if dotenv_path is None and stream is None:
            return False
        return bool(original(dotenv_path, stream, *args, **kwargs))

    _guarded_load_dotenv._strands_code_cwd_guarded = True  # type: ignore[attr-defined]
    dotenv.load_dotenv = _guarded_load_dotenv
    dotenv_main.load_dotenv = _guarded_load_dotenv


def _provider_of(model: str) -> str:
    if model.startswith("arn:") or "/" not in model:
        return "bedrock"
    prefix, _, rest = model.partition("/")
    low = prefix.lower()
    if low != "litellm":
        return low
    sub = rest.partition("/")[0].lower()
    if sub in ("ollama", "ollama_chat"):
        return "ollama"
    if sub == "openrouter":
        return "openrouter"
    return "litellm"


def _default_probe() -> None:
    """Cheap STS call over the ambient chain; never reads credentials directly."""
    import boto3
    from botocore.config import Config

    sts = boto3.client(
        "sts",
        config=Config(connect_timeout=2, read_timeout=3, retries={"max_attempts": 0}),
    )
    sts.get_caller_identity()


def _run_bedrock_probe(probe: Callable[[], None] | None) -> None:
    if _is_truthy("STRANDS_BOX") or _nonempty("AWS_BEARER_TOKEN_BEDROCK"):
        return
    check = probe if probe is not None else _default_probe
    try:
        check()
    except typer.Exit:
        raise
    except Exception as exc:
        logger.warning("Credential preflight failed: %s", type(exc).__name__)
        _fail_preflight(BEDROCK_SETUP_POINTER)


def _check_explicit_provider(
    provider: str,
    base_url: str | None,
    probe: Callable[[], None] | None,
) -> None:
    if provider == "ollama":
        return
    if provider == "google":
        if not has_google_credentials():
            _fail_preflight(
                "Missing Google Gemini credentials. Set GOOGLE_API_KEY / "
                "GEMINI_API_KEY, or set GOOGLE_GENAI_USE_VERTEXAI=true with "
                "GOOGLE_CLOUD_PROJECT."
            )
        return
    if provider in _PROVIDER_ENV_KEYS:
        if provider in ("openai", "anthropic") and base_url:
            return
        keys = _PROVIDER_ENV_KEYS[provider]
        if not any(_nonempty(name) for name in keys):
            joined = " or ".join(keys)
            _fail_preflight(f"Missing credentials for {provider}. Set {joined}.")
        return
    if provider == "litellm":
        if (
            base_url
            or _is_truthy("STRANDS_BOX")
            or any(_nonempty(key) for key in _LITELLM_ANY_KEYS)
        ):
            return
        _fail_preflight(
            "Missing credentials for litellm model. Set OPENROUTER_API_KEY, "
            "LITELLM_API_KEY, or the target provider's API key."
        )
    _run_bedrock_probe(probe)


def preflight_credentials(
    probe: Callable[[], None] | None = None,
    *,
    model: str | None = None,
    base_url: str | None = None,
) -> str | None:
    """Validate credentials for the target provider or auto-pick from env.

    Checks non-empty env presence only (never key prefixes) so Strands Box
    ``strands_box_...`` phantom tokens pass. Skips ``sts.get_caller_identity()``
    for non-AWS providers and whenever ``STRANDS_BOX=1``.

    Args:
        probe: Injectable credential check for offline tests; the ambient
            STS probe is used when omitted.
        model: Explicit session/configured model reference, if any.
        base_url: Optional custom endpoint host from ProviderConfig.

    Returns:
        An auto-selected ``provider/model`` string inferred from ambient
        credentials when ``model`` is ``None``, else ``None``.
    """
    _validate_google_env()
    if model is not None:
        _check_explicit_provider(_provider_of(model), base_url, probe)
        return None
    if has_google_credentials():
        return "google/gemini-3.8-flash"
    for candidate, keys in _AMBIENT_DEFAULT_MODELS:
        if any(_nonempty(name) for name in keys):
            return candidate
    if _nonempty("OPENROUTER_API_KEY"):
        _fail_preflight(
            "OPENROUTER_API_KEY is set, but OpenRouter requires an explicit model id.\n"
            "Pass --model litellm/openrouter/<vendor>/<model> "
            "(for example: --model litellm/openrouter/anthropic/claude-sonnet-4.6)."
        )
    _run_bedrock_probe(probe)
    return None
