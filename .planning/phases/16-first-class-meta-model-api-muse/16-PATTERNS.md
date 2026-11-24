# Phase 16 Codebase Patterns & Extension Seams

**Created:** 2026-11-24
**Purpose:** Concrete architectural seams, helper decompositions, and CI guardrails for Plans `16-01`, `16-02`, and `16-03`.

---

## 1. Entry, Packaging & Env Helpers (`pyproject.toml`, `strands_code_cli/entry/`)

- **`pyproject.toml` dependencies & extras (`D-03`, `D-05`):**
  - Bump floors (zero upper pins): `"strands-agents>=1.66.0"`, `"strands-harness>=0.5.0"`.
  - Add `[project.optional-dependencies]` entry: `meta = ["strands-agents[openai]", "openai>=2.0.0"]`.
- **Single-source env boundary (`strands_code_cli/entry/first_run.py`):**
  - Add `META_DEFAULT_BASE_URL = "https://api.meta.ai/v1"`.
  - Update `_PROVIDER_ENV_KEYS["meta"] = ("MODEL_API_KEY", "META_API_KEY")`.
  - Update `_AMBIENT_DEFAULT_MODELS` (ordered after `has_google_credentials()`):
    1. `("anthropic/claude-sonnet-5-5", ("ANTHROPIC_API_KEY",))`
    2. `("openai/gpt-6.2-sol", ("OPENAI_API_KEY",))` *(bumped from `6.1-sol`)*
    3. `("meta/muse-spark-1.3-contributor", ("MODEL_API_KEY", "META_API_KEY"))`
  - Append `"MODEL_API_KEY"` and `"META_API_KEY"` to `_LITELLM_ANY_KEYS` and mention them in `BEDROCK_SETUP_POINTER`.
  - Export clean helpers accepting optional `env: Mapping[str, str] | None = None`:
    - `has_meta_credentials(env=None) -> bool` (non-empty `.strip()` truthiness only; zero prefix checks for Strands Box compatibility).
    - `meta_api_key(env=None) -> str | None` (`MODEL_API_KEY` primary, `META_API_KEY` fallback).
    - `meta_base_url(env=None) -> str` (reads `META_BASE_URL`, defaults to `META_DEFAULT_BASE_URL`, validates non-default URLs via `provider_config._validate_base_url()` raising `ValueError` on bad scheme / embedded `user:pass@` / whitespace / control chars).
    - Also allow `provider == "meta"` + `base_url` in `_check_explicit_provider()` alongside `openai`/`anthropic` when `STRANDS_BOX=1` or explicit gateway is configured (wait: require credentials OR `STRANDS_BOX=1`? Keeping `"meta"` in `_PROVIDER_ENV_KEYS` naturally checks `MODEL_API_KEY`/`META_API_KEY` and skips when a custom `base_url` is set in `config.yaml`, matching `"openai"`/`"anthropic"`!).
- **Entry wiring (`strands_code_cli/entry/main.py`):**
  - `model_for_config(model, base_url=None, api_mode=None)`: when `normalize_model_ref(model)` starts with `"meta/"` and `not upstream_supports_meta()`, delegate to `build_meta_model(model, base_url=base_url)` (failing soft to `model` on `ImportError` so `_sdk_hint` / harness messages report the `[meta]` extra cleanly, wait — at startup if `openai` is missing, passing `"meta/..."` into `create_harness` raises `ValueError: Unknown model provider 'meta'`, whereas raising `ImportError` or formatting clean install hint is even nicer? Wait: in `_model_message` importing `openai` raises `ImportError` and triggers `_sdk_hint("meta/...") -> "pip install strands-code-agent[meta]"`!).
  - `build_agent()`: when resolved `model` carries `_strands_model_ref` (`"meta/..."`), pass `kwargs["caching"] = False` alongside `kwargs["model"] = model` so `create_harness()` skips the `prompt caching not applied to a pre-built Model instance` warning while `CacheConfig()` remains active on the instance.

---

## 2. Retireable Meta Adapter, Discovery & Media Scoping (`strands_code_cli/model/model_switch.py`, `dispatch/core.py`)

- **Auto-retiring adapter seam (`D-04`):**
  - `upstream_supports_meta() -> bool`: checks `"meta" in getattr(strands_harness.models, "_PROVIDERS", {})` fail-soft (`False` on import/attr error).
  - `_normalize_meta_effort(effort: str | None) -> str | None`: `None` or `"auto"` → `"high"`; `"none"` or `"off"` → `None` (MUST omit `reasoning` to avoid HTTP 400); `"minimal"|"low"|"medium"|"high"|"xhigh"|"max"` → lowercase unchanged; anything unrecognized → `"high"`.
  - `_meta_model_info() -> ModelInfo`: returns `ModelInfo(capabilities=ModelCapabilities(prompt_caching="auto"), limits=ModelLimits(context_window=1_048_576, max_output_tokens=131_072))` (never `"cache_points"`, which triggers invalid `prompt_cache_options` on `api.meta.ai/v1`).
  - `build_meta_model(model_ref, *, effort=None, web_search=True, caching=True, base_url=None)`:
    - Lazily imports `OpenAIResponsesModel`, `CacheConfig`, and calls `first_run.meta_api_key()` / `first_run.meta_base_url()`.
    - Validates explicit `base_url` if passed, else uses `meta_base_url()`.
    - Builds `client_args={"base_url": endpoint, **({"api_key": key} if key else {})}`.
    - Builds `params`: attaches `"reasoning": {"effort": mapped}` when `mapped is not None`, and `"tools": [{"type": "web_search"}]` when `web_search` is True.
    - Passes `cache_config=CacheConfig()` (no `strategy="auto"`, avoiding `UserWarning`!) when `caching` is True.
    - Sets `resolved._strands_model_ref = f"meta/{tail}"` so `model_id_of(resolved, ...)` returns `"meta/<tail>"`.
- **Unified call sites:**
  - `model_switch.model_id_of()`: check `ref = getattr(model, "_strands_model_ref", None); if isinstance(ref, str) and ref: return ref` FIRST.
  - `model_switch.configure_base_url_for_model()`: allow `"meta"` alongside `"openai"` (`provider in ("openai", "meta")`) so pre-built / future upstream Meta `OpenAIResponsesModel` respects persisted `base_url`.
  - `model_switch.resolve_harness_model()`: before calling `resolve_model()`, check `if _provider_of(normalized) == "meta" and not upstream_supports_meta(): return build_meta_model(normalized, effort=effort, base_url=base_url)`.
  - `dispatch/core.py:_SDK_EXTRA_HINTS["meta"] = "meta"` and in `_model_message()`: before `resolve_model(...)`, if `_provider_of(normalized) == "meta" and not upstream_supports_meta()`: validate via `build_meta_model(normalized)` (or verify `import openai`) catching `ImportError` → `_sdk_hint(selection)`!
- **Retire Phase 15 GPT-6.2 bridge (`D-05`):**
  - Remove `_gpt_62_model_info_fallback()` and its call from `configure_openai_for_model()` once `strands-agents>=1.66.0` ships native `gpt-6.2-*` `model_info.json`. Keep `_target_openai_effort()` `gpt-6.2-` clamping!
- **`_MEDIA_LESS` scoping (`D-06`):**
  - Replace `(None, "meta", None, None)` at `model_switch.py:59` with Bedrock-scoped Llama rows `("bedrock", "meta", "llama3", None)` and `("bedrock", "meta", "llama4", None)` (matching `_NO_STREAMING_TOOLS`; `(None, None, None, "llama")` stays untouched for OpenRouter/other Llama routes).
- **Discovery & `("meta", "muse")` grouping (`D-06`):**
  - Add `CURATED_META_MODELS = ("meta/muse-spark-1.3-contributor", "meta/muse-spark-1.3", "meta/muse-wonder-1.0", "meta/muse-ember-1.0")`.
  - Add `_META_NON_CHAT_TOKENS = ("image", "voice", "transcribe", "audio", "sam-", "embed", "tts", "video", "moderation")` and `_is_meta_chat_model(model_id)` requiring `lowered.startswith("muse-")`.
  - Add `_discover_meta_models()` gating on `first_run.has_meta_credentials()`, calling `openai.OpenAI(api_key=meta_api_key(), base_url=meta_base_url()).models.list()`, falling back to `CURATED_META_MODELS` when keyed & offline/SDK-missing, and wire into `discover_models()`.
  - Add `if lowered.startswith("muse-"): return ("meta", base)` in `_infer_bare_vendor(base)` so `"meta/muse-*"` and bare `"muse-*"` both group under `("meta", "muse")`.

---

## 3. Cost, Context Windows & Scrubbing (`strands_code_cli/cost/`)

- **`live_pricing.py`:** Extend `_litellm_keys()` with `elif lowered.startswith("meta/"): keys = [model_id, tail]` so LiteLLM's bundled `meta/muse-*` entries resolve both input/output and `cache_read` discounts automatically.
- **`cost_context.py`:**
  - Keep `price_table` untouched (`CC 20`)!
  - Add static entries in `MODEL_PRICING`:
    - `"muse-spark-1.3-contributor": (0.10, 0.20)`
    - `"muse-spark-1.2-contributor": (0.10, 0.20)`
    - `"muse-spark-": (1.25, 4.25)`
    - `"muse-wonder-": (4.00, 20.00)`
    - `"muse-ember-": (0.10, 0.50)` *(documented `<200K` tier; `>200K` tier noted in comment/quickstart)*
  - Add `"muse-": 1_048_576` in `MODEL_LIMITS`.
  - Update `_default_cache_rates(model_id, in_rate)`:
    - `"muse-" ... "-contributor"`: `(in_rate * 0.02, in_rate)` (50× cached discount)
    - `"muse-ember-"`: `(in_rate * 0.04, in_rate)` (25× cached discount)
    - `"muse-wonder-"`: `(in_rate * 0.05, in_rate)` (20× cached discount)
    - `"muse-spark-"`: `(in_rate * 0.12, in_rate)` (\$0.15 / \$1.25 = 0.12)
  - Update `_CRED_PATTERNS` (`scrub_credentials()`): add `re.compile(r"LLM[_|]\d+[_|][A-Za-z0-9\-_]{12,}")` and include `|` in `Bearer` pattern (`[A-Za-z0-9\-._~+/|]+=*`).
  - Verify `test_no_budgets_or_enforcement_vocabulary` and `test_no_credential_persistence_sinks` remain green.

---

## 4. Live UAT Rigs, Documentation & Held Upstream Comment (`scripts/uattest/`, `docs/`)

- **`scripts/uattest/scenarios_meta.py`:** Parameterize `_run_provider_rig` from `scenarios_openai_anthropic.py` for `scenario_m1()` (`RIG_META_PRIMARY = "meta/muse-spark-1.3-contributor"`, `RIG_META_SECONDARY = "meta/muse-ember-1.0"`, `sentinel="META_SENTINEL_16"`, `expected_window="of 1.05M"`, prints `"M1 PASS"`), registered in `driver.py` as `"m1": scenario_m1`, pinned by `tests/rig/test_uattest_meta.py`.
- **`scripts/uattest/scenarios_openai_anthropic.py`:** Bump `RIG_OPENAI_PRIMARY` to `"openai/gpt-6.2-sol"` (updating `tests/rig/test_uattest_openai_anthropic.py` accordingly).
- **`docs/QUICKSTART.md` & `docs/upstream/harness_comment_6521_meta_probe.md`:** Document Meta Model API (`--extra meta`, `MODEL_API_KEY`, `META_API_KEY`, `META_BASE_URL`, contributor ambient default vs standard/wonder/ember, 50× cache discount, priority after OpenAI, bumped `openai/gpt-6.2-sol` ambient default); write held probe comment draft with `HOLD BEFORE POSTING` banner + AI disclosure.
