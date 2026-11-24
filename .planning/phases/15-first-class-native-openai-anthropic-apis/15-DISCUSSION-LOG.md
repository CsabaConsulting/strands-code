# Phase 15: First-Class Native OpenAI & Anthropic APIs - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `15-CONTEXT.md` — this log preserves the questions asked and options selected.

**Date:** 2026-11-23
**Phase:** `15-first-class-native-openai-anthropic-apis`
**Areas discussed:** Cache-aware `/cost` & usage display (`D-03`), Custom `base_url` routing & `strands-harness` alignment (`D-04`), Same-provider thinking-signature & `SummaryBlock` safety (`D-05`), API extras & ambient auto-pick defaults (`D-06`/`D-07`), Verification & live UAT posture (`D-08`)

*(Pre-decided anchors from Roadmap, Issues `#17` & `#22`, and `v2.0` patterns not re-asked: `openai` with `openai>=2.0.0` & `anthropic` optional extras + `_SDK_EXTRA_HINTS`, `caching`/`web_search` preservation across `/model` and `/route` switches, bare-tail lookup in `litellm_entry()`, static fallbacks for Claude 5.5 / Fable 5.2 / GPT-5.4..6.1 / o3 / o4-mini, credential-gated `/v1/models` discovery, `_vendor_family()` grouping for `openai` & `anthropic`, non-prefix env checks strictly in `first_run.py`, and pristine `strands_code_agent/`.)*

---

## Cache-Aware `/cost` & Usage Display (`D-03`)

Q1: How should cache-aware token & cost metrics appear in the post-turn usage line and `/cost`?

| Option | Description | Selected |
|--------|-------------|----------|
| Compact cache suffix when > 0 | Post-turn `165.60K (17%, 75% cached) $0.14`; `/cost` `in 165.60K (125.00K cached, 40.50K write), out 305`; zero-cache turns stay byte-identical. | ✓ |
| Silent math fix only | Silently fix total context `%` and cache-discounted USD math without showing cache stats. | |
| Always 3-bucket breakdown | Always display uncached / cache-read / cache-write buckets on every `/cost` row even when 0. | |

**User's choice:** Compact cache suffix only when cache tokens > 0 (zero-cache turns stay byte-identical).

---

## Custom `base_url` Routing & `strands-harness` Alignment (`D-04`)

Q2: How should custom `base_url` endpoints work for `openai/` and `anthropic/`?

*(User asked: "How does Strands Harness handle first class support for those? I'd lean towards your recommended choice, but I wonder how much we deviate from the Strands Harness provided goodies (originally we wanted to use as much what it can provide as possible), although I understand if we may need to diverge, for example for potential real time cost extras or similar things.")*

**Verification & follow-up:** Inspecting `strands_harness/models.py` showed that `_openai()` and `_anthropic()` honor `OPENAI_BASE_URL`/`ANTHROPIC_BASE_URL` (and `_CUSTOM_ENDPOINT_VARS` fallback in `resolve_web_fetch_model`), whereas passing a pre-built `Model` instance from `model_for_config()` causes `resolve_model()` to strip harness `effort`, `CacheConfig`, and native `web_search`. Passing the `"openai/..."`/`"anthropic/..."` string into `create_harness` and post-applying `config.base_url` (plus `web_fetch` model override) keeps 100% of harness goodies intact.

Q2b: Confirm the harness-preserving `base_url` approach for Phase 15?

| Option | Description | Selected |
|--------|-------------|----------|
| Pass strings through `create_harness` + post-apply `base_url` + opt-in `api_mode: chat` | 100% harness goodies intact (`effort`, `CacheConfig`, `web_search`), post-apply `config.base_url` onto `OpenAIResponsesModel`/`AnthropicModel`, and keep optional `api_mode: chat` in `config.yaml` only for legacy Chat-Completions proxies. | ✓ |
| Env-var-only (`OPENAI_BASE_URL` / `ANTHROPIC_BASE_URL`) | Pass strings through `create_harness` and restrict `config.base_url` to `litellm/` gateways only. | |

**User's choice:** Pass strings through `create_harness` (100% harness goodies), post-apply `config.base_url` to `OpenAIResponsesModel` / `AnthropicModel`, and keep optional `api_mode: chat` in `config.yaml` only for legacy Chat-Completions proxies.

---

## Anthropic Direct ↔ Bedrock Thinking & `SummaryBlock` Safety (`D-05`)

Q3: How should `convert_history()` handle thinking signatures across `anthropic/` ↔ `bedrock/anthropic.*` and Anthropic server-side compaction `SummaryBlock`s?

| Option | Description | Selected |
|--------|-------------|----------|
| Fail-safe same-provider gating + `SummaryBlock` conversion | Require same provider AND same vendor for raw signed thinking round-trips (`anthropic/` ↔ `bedrock/anthropic.*` converts signed thinking to `TRACE_LABEL` text while stashing raw blocks in `RichHistory` for switch-back) AND convert Anthropic `SummaryBlock` (`"summary"`) to text on non-Anthropic targets. | ✓ |
| Same-vendor round-trip + `drop_block` fallback | Keep same-vendor thinking round-trip across `anthropic/` ↔ `bedrock/anthropic.*` and rely on `drop_block` recovery if rejected; convert `SummaryBlock` on non-Anthropic targets. | |

**User's choice:** Fail-safe same-provider gating + `SummaryBlock` conversion on non-Anthropic targets.

---

## API Extras & Ambient Auto-Pick Defaults (`D-06` / `D-07`)

Q4: How deeply should Phase 15 wire provider-specific API extras and ambient default model IDs?

**Initial selection:** Lean extras wiring (Anthropic `/v1/models` 24h metadata cache, harness defaults, local char/4 estimation, doc coverage for extras), **plus** bump ambient auto-pick defaults in `first_run.py` to newer models.

*(Follow-up verified in `strands.models/model_info.json` and `litellm.model_cost`: `claude-sonnet-5-5` = 1M / 128K output / `cachePoints` / \$2/\$10; `gpt-6.1-sol` = 1.05M / `cachePoints` / \$2/\$10; `gpt-6.1-terra` = 1.05M / `cachePoints` / \$1/\$5.)*

Q4b: Which pair of ambient auto-pick defaults should `first_run.py` use?

| Option | Description | Selected |
|--------|-------------|----------|
| `claude-sonnet-5-5` + `gpt-6.1-sol` | Both \$2/\$10 balanced tier, 1M+ window, `cachePoints` supported. | ✓ |
| `claude-sonnet-5-5` + `gpt-6.1-terra` | Sonnet 5.5 (\$2/\$10) + economy GPT-6.1 Terra (\$1/\$5), `cachePoints` supported. | |

**User's choice:** Same lean extras wiring + bump `_AMBIENT_DEFAULT_MODELS` to `anthropic/claude-sonnet-5-5` and `openai/gpt-6.1-sol`.

---

## Verification & Live UAT Posture (`D-08`)

Q5: What verification and live UAT posture should Phase 15 use?

| Option | Description | Selected |
|--------|-------------|----------|
| Hermetic CI + repeatable `o1` / `a1` `driver.py` scenarios (opportunistic live run) + OpenAI guards | Hermetic unit/contract CI + repeatable `driver.py` tmux scenarios for both OpenAI & Anthropic (run live whenever `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` is present) + fail-soft guards for OpenAI non-reasoning / effort-subset models (+ upstream issue draft if confirmed). | ✓ |
| Hermetic unit/contract tests only | No new live `driver.py` scenarios in Phase 15. | |
| Mandatory live UAT gate | Require live UAT runs against both real API keys before closing Phase 15. | |

**User's choice:** Hermetic CI + repeatable `o1` / `a1` `driver.py` scenarios (opportunistic live run) + fail-soft OpenAI reasoning/effort-subset guards.
