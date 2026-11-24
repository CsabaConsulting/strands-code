# Phase 15 Codebase Patterns & Extension Seams

**Created:** 2026-11-23
**Purpose:** Concrete architectural seams, helper extractions, and CI guardrails for Plans `15-01`, `15-02`, and `15-03`.

---

## 1. Entry, Config & Harness-Preserving `base_url` (`strands_code_cli/entry/`)

- **Credential gate confinement (`test_no_credential_persistence_sinks`):**
  - Keep ALL `os.environ.get(...)` calls inside `strands_code_cli/entry/first_run.py`:
    - `has_openai_credentials(env=None) -> bool` (`OPENAI_API_KEY` non-empty)
    - `has_anthropic_credentials(env=None) -> bool` (`ANTHROPIC_API_KEY` non-empty)
  - Never validate API key prefixes (`sk-`, `sk-ant-`); check `.strip()` truthiness only (`Strands Box` phantom compatibility).
  - Bump `_AMBIENT_DEFAULT_MODELS` to `("anthropic/claude-sonnet-5-5", ("ANTHROPIC_API_KEY",))` and `("openai/gpt-6.1-sol", ("OPENAI_API_KEY",))`.
- **`ProviderConfig` extension (`entry/provider_config.py`):**
  - Add `"api_mode"` to `_KNOWN_KEYS` and `api_mode: str | None = None` (`VALID_API_MODES = ("responses", "chat")`) to `ProviderConfig`.
  - Because `load()` is `C (16)` and `save()` is `C (15)`, extract shared `_validate_config_values(...)` before validating `api_mode` so complexity stays comfortably below `C (12)`.
- **Harness-preserving `base_url` (`entry/main.py`, `model_switch.py`, `loop/btw.py`, `loop/core.py`):**
  - Pass `"openai/..."` and `"anthropic/..."` as **strings** into `create_harness(model=...)` unless `api_mode == "chat"` (or `prefix == "litellm"` with `base_url`).
  - Only when `api_mode == "chat"` or `prefix == "litellm"` with `base_url`: construct `OpenAIModel(model_id=tail, client_args={"base_url": base_url})` (fixing the unstripped `"openai/"` prefix bug).
  - When `base_url` is set with default `api_mode` on `openai/` or `anthropic/`:
    - Pass `"web_fetch": {"model": effective_model}` in `builtin_tools` inside `build_agent()` so `web_fetch` does not probe a missing vended summarizer on the custom proxy.
    - Call `configure_base_url_for_model(target_id, resolved_model, base_url=base_url)` right after `create_harness` / `resolve_harness_model` (`build_agent`, `apply_switch`, `build_btw_agent`, `_route_side_spawn`):
      - `OpenAIResponsesModel`: `resolved.client_args["base_url"] = base_url` (since `_get_client()` instantiates `openai.AsyncOpenAI(**self._resolve_client_args())` per call; guard against overwriting `bedrock_mantle_config`).
      - `AnthropicModel`: rebind `resolved.client = anthropic.AsyncAnthropic(base_url=base_url)` when client is `AsyncAnthropic` (do not overwrite `AsyncAnthropicBedrock` / `AsyncAnthropicVertex`).
  - Attach `agent._base_url = base_url` (or forward `base_url` cleanly from `ProviderConfig`) so mid-session switches keep working on the configured endpoint.

---

## 2. Model Resolution, Post-Config Guards & Switching (`strands_code_cli/model/model_switch.py`)

- **Shared `resolve_harness_model()` helper (`D-02`):**
  - Extract `resolve_harness_model(model_ref: str, default: str | None = None, *, effort: str | None = None) -> Any` calling `resolve_model(normalized, default or normalized, caching=True, caching_explicit=False, **({"web_search": True} if supports_web_search(normalized) else {}), **({"effort": effort} if effort is not None else {}))`.
  - Reuse in both `apply_switch()` (`model_switch.py`) and `_route_side_spawn()` (`loop/core.py`), eliminating duplicated `wrap_for_openrouter` + `configure_*_for_model` chains!
- **OpenAI reasoning guard (`configure_openai_for_model`):**
  - Mirror `configure_gemini_for_model(model_id, resolved)` and invoke at all 4 sites (`apply_switch`, `build_agent`, `build_btw_agent`, `_route_side_spawn`).
  - When normalized provider is `"openai"`:
    - Strip `params["reasoning"]` if base model is non-reasoning (`gpt-4o`, `gpt-4.1`, `gpt-4-turbo`, `chat-latest`, excluding reasoning families).
    - Clamp/drop `params["reasoning"]["effort"]` on subset models (`o1`/`o3`/`o4-mini` keep `low|medium|high`; `gpt-5`/`gpt-5.1`/`gpt-5.2` disallow `none`/`xhigh`; `gpt-6-astra`/`gpt-6.1-sol` clamp `none`/`minimal` -> `low` or remove on `off`). Call `resolved.update_config(params=updated_params)` fail-soft.
- **Same-provider thinking & `SummaryBlock` conversion (`D-05`):**
  - Keep `same_vendor()` untouched (pinned by existing test `test_same_vendor_across_id_forms`).
  - Add `same_provider(first_id, second_id)` (`_provider_of(...) == _provider_of(...)`) and require `supports_reasoning(new_id) and same_vendor(old_id, new_id) and same_provider(old_id, new_id)` inside `convert_history()` and `_should_restore_rich()`.
  - Add `_convert_summary_block(block, new_id)`: keep `{"summary": ...}` only when target provider is `"anthropic"` and `summary.get("provider") in (None, "anthropic")`; otherwise emit `{"text": f"{SUMMARY_LABEL}\n{text}"}` (while stashing raw `"summary"` blocks in `RichHistory` and normalizing `"summary"` / `SUMMARY_LABEL` inside `_canonical_block`).
- **`_vendor_family(base)` grouping (`D-06`):**
  - Keep `"x"` -> `("x", "x")` for dotless unknown Bedrock IDs (`test_dotless_id_groups_under_itself`), `"openai.gpt-oss-120b"` -> `("openai", "gpt-oss")`, `"gemini-2.5-pro"` -> `("google", "gemini")`.
  - Map bare Anthropic tails `claude-*` -> `("anthropic", "claude")` and OpenAI tails `gpt-*` -> `("openai", "gpt")` / `gpt-oss-*` -> `("openai", "gpt-oss")` / `o1-*`, `o3-*`, `o4-*` (and exact `"o1"`, `"o3"`, `"o4"`) -> `("openai", tokens[0])`.
- **Credential-gated live `/model` discovery & retirement notes (`D-06`):**
  - Extract `_discover_openai_models()` (checks `first_run.has_openai_credentials()`, filters via `_is_openai_chat_model()`, falls back to `CURATED_OPENAI_MODELS` when keyed) and `_discover_anthropic_models()` (checks `first_run.has_anthropic_credentials()`, calls `client.models.list()`, persists 24h metadata via `live_pricing.store_anthropic_models()`, falls back to `CURATED_ANTHROPIC_MODELS` when keyed).
  - Annotate `route_label()` with `(retires YYYY-MM-DD)` from cached Anthropic metadata without altering selectable `route` strings returned by `normalize_model_ref()`.

---

## 3. Cache-Aware `/cost`, Context `%` & Pricing (`strands_code_cli/cost/`, `strands_code_cli/loop/core.py`)

- **Vocabulary guardrail (`test_no_budgets_or_enforcement_vocabulary`):**
  - NEVER introduce `"budget"`, `"enforce"`, `"quota"`, or `"halt"` substrings in `model_switch.py`, `cost_context.py`, `dispatch/core.py`, `loop/core.py`, `loop/pump.py`, or `utils.py`!
- **Byte-pristine `strands_code_agent/` (`D-24`):**
  - Do NOT edit `strands_code_agent/utils.py`. Extract `_extract_prompt_usage(result, model_id)` in `strands_code_cli/loop/core.py` to read `cacheReadInputTokens` and `cacheWriteInputTokens` from `result.metrics.get_summary()["accumulated_usage"]`, compute inclusive vs exclusive `total_prompt_tokens` (`input + output == total` -> inclusive, else exclusive with provider fallback), and populate optional `cache_read_tokens` / `cache_write_tokens` on `session_turns` entries only when `> 0`.
- **Complexity extraction in `cost_context.py`:**
  - Because `cost_report()` is currently `C (20)`, extract `_format_input_cell(row)` and `_format_turn_row(row, model_id, provenances)` BEFORE adding cache-read/write cost math and `(X cached, Y write)` display!
  - Zero-cache turns MUST render byte-identically to existing tests (`in 1.23K, out 456, $0.0123`, `1.23K (1%) $0.01`).
  - Only when `cache_read > 0` or `cache_write > 0`:
    - `usage_line()`: append `, <N>% cached` inside `(...)` when `cache_read > 0` and window known (or `(N% cached)` if window `n/a`), e.g. `165.60K (17%, 75% cached) $0.14`.
    - `_format_input_cell()`: `in 165.60K (125.00K cached, 40.50K write)` (omit `write` clause when `cache_write == 0`).
- **LiteLLM & 24h Anthropic metadata cache (`live_pricing.py`):**
  - Extract `_litellm_keys(model_id)` and `_parse_litellm_entry(raw)` so `litellm_entry()` drops from `C (15)` below `10`, resolving bare `tail` / provider-prefixed keys and returning `"cache_read"` and `"cache_write"` (`* 1_000_000`) when present.
  - Add `store_anthropic_models()`, `anthropic_models_cache()`, and `anthropic_model_entry()` using `_cache_dir() / "anthropic-models.json"`, integrated into `_sdk_window` / `_live_window` in `cost_context.py` so freshly discovered Anthropic models get exact `max_input_tokens`.

---

## 4. UAT Rig & Verification (`scripts/uattest/`, `tests/rig/`, `docs/`)

- **Scenario slots:** `a1`/`a2` are used by CodeAct (`scenarios_codeact.py`), so register `o1` (`scenario_o1`) and `an1` (`scenario_an1`) in `scripts/uattest/scenarios_openai_anthropic.py`, wired into `scripts/uattest/driver.py` and `scripts/uattest/README.md` and pinned offline in `tests/rig/test_uattest_openai_anthropic.py`.
- **CI gates after every wave:** `.venv/bin/pytest tests/...`, `.venv/bin/ruff check strands_code_cli tests scripts`, `.venv/bin/ruff format --check strands_code_cli tests scripts`, `.venv/bin/xenon --max-absolute C strands_code_cli tests scripts`, `.venv/bin/lint-imports`, `git diff ee42ea2 -- strands_code_agent/` empty.
