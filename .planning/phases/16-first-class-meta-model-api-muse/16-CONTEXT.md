# Phase 16: First-Class Meta Model API (api.meta.ai / Muse) & Upstream Enablement - Context

**Gathered:** 2026-11-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver first-class support for Meta's Model API (`https://api.meta.ai/v1` — Muse Spark, contributor tiers, Muse Wonder, and Muse Ember) (`MODEL-09`, tracking `CsabaConsulting/strands-code#21` and upstream `strands-agents/harness-sdk#6521`), **plus** fold in the intentional upstream dependency resync to `strands-agents >= 1.66.0` / `strands-harness >= 0.5.0`:
- Empirical live probe against `https://api.meta.ai/v1` (`/v1/responses` vs `/v1/messages`, `prompt_cache_key` / `prompt_cache_options` tolerance, `web_search` support, encrypted reasoning replay, `GET /v1/models`) and a held follow-up comment draft in `docs/upstream/harness_comment_6521_meta_probe.md` for `strands-agents/harness-sdk#6521`.
- Dedicated `meta` optional packaging extra alias (`pyproject.toml`) + `_SDK_EXTRA_HINTS["meta"] = "meta"`, Box-compatible zero-AWS preflight accepting `MODEL_API_KEY` (primary) and `META_API_KEY` (fallback) + validated optional `META_BASE_URL` (default `https://api.meta.ai/v1`), and ambient auto-pick defaulting to `meta/muse-spark-1.3-contributor` placed after Google, Anthropic, and OpenAI.
- Thin, retireable `meta/` adapter backed by `OpenAIResponsesModel` (auto-retiring once upstream `strands-harness` natively adds `"meta"` to `_PROVIDERS`), wired cleanly across startup, `/model`, `/route`, and `/btw` side-agents without breaking `scoped_base_url()` or `T-15-02`/`T-15-03` isolation.
- Scoped `_MEDIA_LESS` rules so multimodal `meta/muse-*` models retain native image/media support while Bedrock Llama remains protected; credential-gated `GET /v1/models` discovery filtering out non-chat entries (`muse-voice-transcribe-*`, `sam-*`, etc.) with curated offline fallback and `("meta", "muse")` `_vendor_family()` grouping.
- Cache-aware `/cost` and 1M context window accounting for `meta/muse-*` (LiteLLM bundled entries + static fallbacks for `muse-ember-1.0` and `-contributor` 50× cached input discount).
- Intentional upstream resync of `pyproject.toml` / `uv.lock` onto `strands-agents>=1.66.0` & `strands-harness>=0.5.0` (no upper pins), cleanly retiring the temporary `_gpt_62_model_info_fallback()` bridge, bumping `_AMBIENT_DEFAULT_MODELS["openai"]` from `openai/gpt-6.1-sol` to `openai/gpt-6.2-sol`, and adapting/verifying any `1.66.0`/`0.5.0` upstream changes (`#6265`, `#6396`, `#6284`, `#5698`, `#6291`, `#5997`, `#4683`).
- Repeatable `scripts/uattest/` Meta tmux UAT scenario (`driver.py m1`) with offline rig contract tests, live UAT verification using `MODEL_API_KEY` from `.env`, and a Meta Model API section in `docs/QUICKSTART.md`.

Out of scope: `DecisionModel` routing convergence (**Phase 17**, `UPSTREAM-02`), remote skills marketplaces (**Phase 18**, `SKILL-03`), Strands Box `box.toml`/`policy.dw` egress generator including `api.meta.ai` (**Phase 19**, `SANDBOX-01`), `/help`/`@file`/`/review` (**Phase 20**, `LOOP-06`/`TOOL-05`/`REVIEW-01`), `strands-agents-evals` (**Phase 21**, `EVAL-01`), and unreviewed posting to upstream GitHub issues (`team/AI_USAGE_POLICY.md`).

</domain>

<decisions>
## Implementation Decisions

### Ambient Default & Provider Priority
- **D-01 (Ambient Auto-Pick Default — `meta/muse-spark-1.3-contributor`):** Auto-pick `meta/muse-spark-1.3-contributor` when Meta credentials are selected as the ambient provider (cheapest default; 50× cached input discount at \$0.10 in / \$0.002 cached / \$0.20 out per 1M, `1,048,576` context window). Document clearly in `docs/QUICKSTART.md` that `-contributor` is the ambient default for cost efficiency and that non-contributor `meta/muse-spark-1.3`, `meta/muse-wonder-1.0`, and `meta/muse-ember-1.0` are selectable via `--model` or `/model`. — *Reversibility: easy — single entry in `_AMBIENT_DEFAULT_MODELS`.*
- **D-02 (Ambient Auto-Pick Priority Order):** Place Meta **after Google, Anthropic, and OpenAI**: `Google -> Anthropic -> OpenAI -> Meta -> OpenRouter (explicit --model error) -> Bedrock`, so adding `MODEL_API_KEY` or `META_API_KEY` never preempts existing Google, Anthropic, or OpenAI defaults. — *Reversibility: easy — ordering inside `preflight_credentials()` / `_AMBIENT_DEFAULT_MODELS`.*

### Packaging Extra & Environment Variables
- **D-03 (`meta` Optional Extra Alias & `MODEL_API_KEY` / `META_API_KEY` / `META_BASE_URL`):**
  - Add `meta = ["strands-agents[openai]", "openai>=2.0.0"]` to `[project.optional-dependencies]` in `pyproject.toml` (zero new third-party dependencies, no upper pins) and map `"meta": "meta"` in `_SDK_EXTRA_HINTS` (`strands_code_cli/dispatch/core.py`).
  - Accept `MODEL_API_KEY` as primary credential (matching Meta docs & `strands-agents/harness-sdk#6521`) with `META_API_KEY` as secondary fallback, using Box-compatible presence-only `.strip()` checks (zero vendor prefix checks) strictly encapsulated inside `strands_code_cli/entry/first_run.py` (preserving `test_no_credential_persistence_sinks`).
  - Support optional `META_BASE_URL` override (defaulting to `https://api.meta.ai/v1`), validated through strict `http`/`https` + host URL hygiene (rejecting embedded `user:pass@`, whitespace, and control chars — mirroring `T-15-03` `_validate_base_url()`).
  - Update `BEDROCK_SETUP_POINTER` in `strands_code_cli/entry/first_run.py` to mention `MODEL_API_KEY` / `META_API_KEY`. — *Reversibility: easy — additive extra, dict entries, and preflight helpers.*

### Live Probe, Retireable Adapter & Live UAT
- **D-04 (Live Empirical Protocol Probe, Thin Retireable `meta/` Adapter & Live `m1` UAT):**
  - Run a live empirical probe against `https://api.meta.ai/v1` (using `MODEL_API_KEY` from `.env` without ever reading `.env` verbatim or printing/logging key values) verifying `/v1/responses` vs `/v1/messages`, `prompt_cache_key` / `prompt_cache_options` tolerance, native `web_search` support, encrypted reasoning / thinking replay behavior, tool calling, and `GET /v1/models` payload shape.
  - Implement a thin, retireable `meta/` adapter backed by `OpenAIResponsesModel` (reading credentials/base URL via `first_run.py` helpers, honoring empirical probe findings for `CacheConfig` / `web_search` / `reasoning` / `effort`, and automatically yielding to upstream `strands_harness.models` once `"meta"` appears in `strands_harness.models._PROVIDERS`). Wire across startup (`entry/main.py`), `/model` (`apply_switch`), `/route` (`resolve_harness_model`), and `/btw` (`build_btw_agent`), keeping `scoped_base_url()` cross-provider isolation intact.
  - Add a repeatable `driver.py m1` tmux UAT scenario in `scripts/uattest/` (pinned by offline contract tests under `tests/rig/`) and execute live UAT verification against `api.meta.ai/v1`. — *Reversibility: easy — isolated adapter auto-retires on upstream enablement.*

### Folded Upstream SDK & Harness Resync (`1.66.0` / `0.5.0`)
- **D-05 (Resync `strands-agents>=1.66.0` & `strands-harness>=0.5.0` + Bump OpenAI Ambient Default to `openai/gpt-6.2-sol`):**
  - Fold an intentional upstream resync into Phase 16: raise `pyproject.toml` floors to `strands-agents>=1.66.0` and `strands-harness>=0.5.0` (no upper pins) and relock `uv.lock`.
  - Retire the temporary `_gpt_62_model_info_fallback()` bridge in `strands_code_cli/model/model_switch.py` now that `1.66.0` ships `#6265` (GPT-6.2 `model_info.json`) and `#6396` (moving GPT-6.2 system prompt to leading `developer` message so Responses prompt caching works).
  - Bump `_AMBIENT_DEFAULT_MODELS["openai"]` in `strands_code_cli/entry/first_run.py` from `openai/gpt-6.1-sol` to **`openai/gpt-6.2-sol`** (updating affected tests and `docs/QUICKSTART.md`).
  - Audit and adapt for any other `1.66.0`/`0.5.0` upstream changes (`#6284` Haiku 5.5 injected text, `#5698` Anthropic `max_tokens` default from `model_info`, `#6291` Chat Completions tools for GPT-5.6/6, `#5997` Bedrock AgentCore `InvokeWebSearch`, `#4683` Bedrock Anthropic default to Claude Opus 5.5) while keeping all tests and CI gates green. — *Reversibility: moderate — lockfile bump + retiring Phase 15 fallback shim.*

### Media Capabilities, Discovery Filtering & Family Grouping
- **D-06 (`_MEDIA_LESS` Scoping, Filtered `/model` Discovery & `("meta", "muse")` Grouping):**
  - Narrow `_MEDIA_LESS` in `strands_code_cli/model/model_switch.py:59` so `(None, "meta", None, None)` no longer strips images/media from multimodal `meta/muse-spark-*` and `meta/muse-wonder-*` models while keeping Bedrock/Llama rows (`(None, None, None, "llama")` and/or explicit Bedrock Llama rows) text-only. Verify `muse-ember-1.0` media capability empirically during the probe.
  - Add credential-gated Meta `/model` discovery (`GET /v1/models` via lazy `openai.OpenAI(api_key=..., base_url=...)`), strictly filtering out non-chat models (`muse-voice-transcribe-*`, `sam-*`, audio/image/embedding entries) and falling back to curated `CURATED_META_MODELS` (`meta/muse-spark-1.3-contributor`, `meta/muse-spark-1.3`, `meta/muse-wonder-1.0`, `meta/muse-ember-1.0`) when offline or SDK missing.
  - Update `_vendor_family()` in `model_switch.py` so `muse-*` tails map cleanly to `("meta", "muse")` in `/model` trees. — *Reversibility: easy — fail-soft discovery and tuple-scoped rules.*

### Cache-Aware Pricing & Context Windows
- **D-07 (Cache-Aware `/cost` & 1M Context Accounting for `meta/muse-*`):**
  - Verify `live_pricing.litellm_entry()` resolves bundled `meta/muse-wonder-1.0` (\$4.00 in / \$0.20 cached / \$20.00 out, `1,048,576`), `meta/muse-spark-1.3` (\$1.25 / \$0.15 / \$4.25, `1,048,576`), `meta/muse-spark-1.3-contributor` (\$0.10 / \$0.002 / \$0.20 — 50× cached discount, `1,048,576`), and `meta/muse-spark-1.2*`.
  - Add static fallbacks in `MODEL_PRICING`, `MODEL_LIMITS` (`1_048_576`), and `_default_cache_rates()` in `strands_code_cli/cost/cost_context.py` for `muse-ember-1.0` (\$0.10 / \$0.004 cached / \$0.50 `<200K`; document `>200K` tier), `muse-spark-1.3-contributor` (50× cached = `0.02`), `muse-spark-1.3`, and `muse-wonder-1.0`, plus verify inclusive vs exclusive `inputTokens` cache-counter semantics for `meta/` during the live probe. — *Reversibility: easy — lookup tables and provider-normalized display accounting.*

### Upstream Coordination & Documentation
- **D-08 (Held Upstream `#6521` Empirical Probe Comment & `docs/QUICKSTART.md`):**
  - After running the live empirical probe against `https://api.meta.ai/v1`, draft a held follow-up comment in `docs/upstream/harness_comment_6521_meta_probe.md` (with `HOLD BEFORE POSTING` banner and AI disclosure per upstream `team/AI_USAGE_POLICY.md`) for explicit human review before posting to `strands-agents/harness-sdk#6521`.
  - Add a **Meta Model API (`api.meta.ai` / Muse)** section to `docs/QUICKSTART.md` covering `uv sync --extra meta`, `MODEL_API_KEY` / `META_API_KEY` / `META_BASE_URL`, the `meta/muse-spark-1.3-contributor` ambient default vs non-contributor `--model` choices, contributor caching/cost notes, and update OpenAI ambient default references to `openai/gpt-6.2-sol`. — *Reversibility: easy — held markdown draft and documentation section.*

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `.planning/REQUIREMENTS.md` — `MODEL-09` (`#21`)
- `.planning/ROADMAP.md` — Phase 16 goal & 4 success criteria
- `docs/upstream/harness_issue_meta_model_api.md` — Filed upstream proposal (`strands-agents/harness-sdk#6521`)
- `pyproject.toml` — Optional extras (`openai`, `anthropic`; add `meta`), `strands-agents` / `strands-harness` dependency floors & CI gates
- `strands_code_cli/entry/first_run.py` — `BEDROCK_SETUP_POINTER`, `_PROVIDER_ENV_KEYS`, `_AMBIENT_DEFAULT_MODELS`, `_check_explicit_provider`, `preflight_credentials`
- `strands_code_cli/entry/provider_config.py` — `_validate_base_url` (`L38`), `ProviderConfig` (`model`, `base_url`, `api_mode`, `save_model_choice`)
- `strands_code_cli/entry/main.py` — `model_for_config` (`L98`), `build_agent` (`L131`), `_root`
- `strands_code_cli/model/model_switch.py` — `_MEDIA_LESS` (`L53-69`), `discover_models` (`L744`), `_vendor_family` (`L875`), `_gpt_62_model_info_fallback` (`L1129`), `configure_openai_for_model` (`L1155`), `scoped_base_url` (`L1260`), `resolve_harness_model` (`L1309`), `apply_switch` (`L1340`)
- `strands_code_cli/dispatch/core.py` — `_SDK_EXTRA_HINTS` (`L77-99`), `_model_message`
- `strands_code_cli/loop/core.py` — `record_turn_metrics` & pre-turn `/route` `resolve_harness_model` wiring
- `strands_code_cli/loop/btw.py` — `build_btw_agent` (`L421`)
- `strands_code_cli/cost/live_pricing.py` — `litellm_entry`, `cached_tables`
- `strands_code_cli/cost/cost_context.py` — `MODEL_PRICING` (`L28`), `MODEL_LIMITS` (`L82`), `_default_cache_rates` (`L308`), `cost_for`, `scrub_credentials` (`L823`)
- `tests/cost/test_cost_context.py` — `test_no_budgets_or_enforcement_vocabulary` (`L959`), `test_no_credential_persistence_sinks` (`L988`)
- `scripts/uattest/` — `driver.py`, `scenarios_openai_anthropic.py`, `scenarios_gemini.py`
- `docs/QUICKSTART.md` — Provider quickstart & setup guides

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `resolve_harness_model()` and `scoped_base_url()` (`model_switch.py:1260-1339`) already unify `resolve_model` invocation, `caching` / native `web_search` forwarding, post-config guards, and cross-provider `base_url` isolation across startup, `/model`, `/route`, and `/btw`.
- `first_run.py` credential helpers (`_nonempty`, `_PROVIDER_ENV_KEYS`, `_AMBIENT_DEFAULT_MODELS`) provide the single compliant place for `os.environ` checks (`MODEL_API_KEY`, `META_API_KEY`, `META_BASE_URL`).
- `provider_config._validate_base_url()` (`provider_config.py:38`) can be reused or mirrored for strict `META_BASE_URL` validation.
- `scripts/uattest/scenarios_openai_anthropic.py` and `scenarios_gemini.py` provide exact tmux rig conventions ready to mirror for `driver.py m1`.

### Constraints & Watchpoints
- **`test_no_credential_persistence_sinks` (`tests/cost/test_cost_context.py:988`):** Strictly forbids `os.getenv` / `os.environ` inside `model/model_switch.py`, `cost/cost_context.py`, `dispatch/core.py`, `loop/core.py`, `loop/pump.py`, `entry/main.py`, and `entry/provider_config.py`! Reading `MODEL_API_KEY`, `META_API_KEY`, and `META_BASE_URL` MUST stay encapsulated in `strands_code_cli/entry/first_run.py` (zero vendor key-prefix checks; zero secret persistence or printing).
- **`test_no_budgets_or_enforcement_vocabulary` (`tests/cost/test_cost_context.py:959`):** Strictly forbids literal `"budget"`, `"enforce"`, `"quota"`, or `"halt"` substrings in protected modules without qualifying context.
- **Maintain `strands_code_agent/` byte-pristine (`D-24`):** Zero modifications to `strands_code_agent/`.
- **Complexity ceiling (`xenon --max-absolute C`, `CC <= 20`) & `import-linter`:** Keep helpers cleanly decomposed across `entry/`, `model/`, `cost/`, and `loop/`.
- **Upstream policy (`team/AI_USAGE_POLICY.md`):** Hold any upstream `#6521` comment draft in `docs/upstream/` with a `HOLD BEFORE POSTING` banner and AI-assistance disclosure until explicitly approved by the user.

</code_context>

<specifics>
## Specific Ideas

- Verify during the live empirical probe against `https://api.meta.ai/v1`:
  1. Whether `OpenAIResponsesModel` succeeds out of the box on `/v1/responses` or requires stripping/adjusting `prompt_cache_key`, `prompt_cache_options`, `reasoning`, or `web_search` tool fields.
  2. Whether `usage.input_tokens` returned by Meta's `/v1/responses` endpoint **includes** or **excludes** `input_tokens_details.cached_tokens` so `cost_context.py` handles `"meta"` with exact parity.
  3. Whether `meta/muse-ember-1.0` supports multimodal image inputs or is text-only (determining exact `_MEDIA_LESS` scoping alongside verified Bedrock Llama 3/4 rows).
  4. Whether Meta API keys use a recognizable prefix worth adding to `cost_context.scrub_credentials()` (without ever enforcing prefix validation in `first_run.py` preflight).
  5. What non-chat model IDs `GET https://api.meta.ai/v1/models` returns in practice so the discovery allowlist/denylist filter is exact.
- During the `strands-agents>=1.66.0` / `strands-harness>=0.5.0` resync (`D-05`), inspect installed package deltas directly in `.venv` after `uv lock --upgrade-package ...` / `uv sync` to confirm `#6265` (GPT-6.2 `model_info.json`) & `#6396` allow deleting `_gpt_62_model_info_fallback()` cleanly and check for any behavior changes in `AnthropicModel` (`#5698` `max_tokens`), `BedrockModel` (`#4683`), or `strands-harness` (`#5997`, `#6291`).

</specifics>

<deferred>
## Deferred Ideas

- `DecisionModel` routing convergence — **Phase 17 (`UPSTREAM-02`)**.
- Remote skills marketplaces and lockfile installer — **Phase 18 (`SKILL-03`)**.
- Strands Box `box.toml` / `policy.dw` egress profile for `api.meta.ai` (`Authorization: Bearer`) — **Phase 19 (`SANDBOX-01`)**.
- `/help`, `@file`, `/review` — **Phase 20 (`LOOP-06`, `TOOL-05`, `REVIEW-01`)**.
- `strands-agents-evals` & red-team suite — **Phase 21 (`EVAL-01`)**.

</deferred>

*Phase: 16-first-class-meta-model-api-muse*
*Context gathered: 2026-11-24*
