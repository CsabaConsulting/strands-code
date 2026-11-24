---
status: complete
phase: 16-first-class-meta-model-api-muse
source: [16-01-SUMMARY.md, 16-02-SUMMARY.md, 16-03-SUMMARY.md, 16-VERIFICATION.md]
started: 2026-11-24T16:51:32Z
updated: 2026-11-24T19:23:13Z
---

# Phase 16 User Acceptance Testing (`MODEL-09`)

## Current Test

[testing complete]

## Tests

### 1. Zero-AWS Ambient Auto-Pick (`meta/muse-spark-1.3-contributor` & `openai/gpt-6.2-sol`), Env Precedence & `META_BASE_URL` Validation (`D-01`, `D-02`, `D-03`, `D-05`)
expected: With AWS and competing provider env vars stripped under an isolated XDG_CONFIG_HOME, launching `strands-code` without `--model` auto-picks `meta/muse-spark-1.3-contributor` (`1.05M`) when `MODEL_API_KEY` or `META_API_KEY` is set alone and `openai/gpt-6.2-sol` (`1.05M`) when `OPENAI_API_KEY` is set alone (leaving `config.yaml` absent); priority order gives OpenAI (`openai/gpt-6.2-sol`) precedence over Meta (`meta/muse-spark-1.3-contributor`) which beats OpenRouter; explicit `meta/` + custom `base_url` passes preflight with zero keys; malformed `META_BASE_URL` exits with code 2; and `_gpt_62_model_info_fallback()` is retired on `strands-agents==1.66.0`.
result: pass
evidence:
- Executed via `run_uat16_test1.py` (`exit 0`, 2026-11-24T17:08:15Z, user accepted `pass` 2026-11-24T17:33Z):
  - `1a` (`MODEL_API_KEY` alone): `/context` reported `meta/muse-spark-1.3-contributor` (`0% of 1.05M`), `config_yaml_exists: False`.
  - `1b` (`META_API_KEY` fallback alone): `/context` reported `meta/muse-spark-1.3-contributor` (`0% of 1.05M`), `config_yaml_exists: False`.
  - `1c` (`OPENAI_API_KEY` alone): `/context` reported `openai/gpt-6.2-sol` (`0% of 1.05M`), `config_yaml_exists: False`.
  - `1d`: `OPENAI_API_KEY`+`MODEL_API_KEY` -> `openai/gpt-6.2-sol`; `MODEL_API_KEY`+`OPENROUTER_API_KEY` -> `meta/muse-spark-1.3-contributor`; zero-key explicit `meta/`+`base_url` passed; malformed `META_BASE_URL` (`ftp://...`, embedded creds, whitespace) raised `typer.Exit(code=2)`; `hasattr(model_switch, "_gpt_62_model_info_fallback")` is `False`.

### 2. Live Meta Model API Tool Turn, Cache-Aware Contributor `/cost`, Same-Provider Switch & Live OpenAI `gpt-6.2-sol` Regression (`D-04`, `D-05`, `D-07`, `D-08` — `driver.py m1` & `driver.py o1`)
expected: Zero-AWS `driver.py m1` (`meta/muse-spark-1.3-contributor` -> `meta/muse-ember-1.0`) and `driver.py o1` (`openai/gpt-6.2-sol` -> `openai/gpt-6.1-terra`) boot with `--model` without writing `config.yaml`, show `of 1.05M` in `/context`, execute live `read` tool turns (`META_SENTINEL_16` / `OPENAI_SENTINEL_15`), render cache-aware `/cost` output (`Display only`), and keep conversation history across same-provider `/model` switches with zero `Dropping reasoningContent` warnings.
result: pass
evidence:
- Fresh live runs against current `HEAD` (zero-AWS + isolated `XDG_CONFIG_HOME`, user accepted `pass` 2026-11-24T18:39Z):
  - `driver.py m1` -> `M1 PASS` (`/tmp/uatr8/m1.log`, session `ffb25051-a7a9-49cf-87e7-bab33f95708c`): `/context` `meta/muse-spark-1.3-contributor` `0 (0% of 1.05M)`, `read` returned `META_SENTINEL_16` (`8.24K (1%) $0.00`), `/cost` `turn 1: in 8.24K, out 192, $0.0009` (`Prices: LiteLLM bundled.`, `Display only — no budgets or enforcement.`), `/model meta/muse-ember-1.0` kept `4` messages (zero `Dropping reasoningContent`).
  - `driver.py o1` -> `O1 PASS` (`/tmp/uatr8/o1.log`, session `497e79d1-b4d8-41e7-81d8-460a4528516e`): `/context` `openai/gpt-6.2-sol` `0 (0% of 1.05M)`, `read` returned `OPENAI_SENTINEL_15` (`13.70K (1%, 49% cached) $0.02`), `/cost` `turn 1: in 13.70K (6.78K cached, 6.84K write), out 51, $0.0185` (`Prices: LiteLLM bundled.`, `Display only — no budgets or enforcement.`), `/model openai/gpt-6.1-terra` kept `4` messages (zero `Dropping reasoningContent`).

### 3. Credential-Gated Meta `/v1/models` Discovery, Non-Chat Filtering & `("meta", "muse")` Picker Grouping (`D-06`)
expected: Live `discover_models()` queries `https://api.meta.ai/v1/models` when Meta credentials are set, returns Meta chat/reasoning models (`muse-ember-1.0`, `muse-wonder-1.0`, `muse-spark-1.1..1.3`, `-contributor`), excludes non-chat assets (`muse-image-*`, `muse-voice-transcribe-*`, `sam-*`), groups under `("meta", "muse")` in `build_model_tree()`, and omits `meta/` completely when Meta keys are absent.
result: pass
evidence:
- Executed via live `run_uat16_test3.py` (`exit 0`, 2026-11-24T18:42Z, competing provider & AWS env stripped, user accepted `pass` 2026-11-24T19:10Z):
  - `3a`: `offline=False`, discovered `7` Meta models (`meta/muse-ember-1.0`, `meta/muse-wonder-1.0`, `meta/muse-spark-1.3-contributor`, `meta/muse-spark-1.3`, `meta/muse-spark-1.2-contributor`, `meta/muse-spark-1.2`, `meta/muse-spark-1.1`), excluded `meta/muse-image-1.0`, `meta/muse-voice-transcribe-1.0`, `meta/sam-3.1`, zero `_META_NON_CHAT_TOKENS` or non-Meta leakage.
  - `3b`: `build_model_tree()` grouped `vendors=['meta']` and `meta_families=['muse']` covering all `7` models; `_vendor_family` returned `('meta', 'muse')`; `window_for()` returned `1_048_576` for Spark Contributor, Wonder, and Ember.
  - `3c`: unkeyed isolation (`boto3=None`) returned `(['bedrock/x'], True)` with zero `meta/` leakage.

### 4. Multimodal Muse Media Retention, Effort Normalization (`"none"` Omitted), Auto-Retiring Adapter Seam, `/btw` & Credential Scrubbing (`D-04`, `D-06`, `D-07`)
expected: `_MEDIA_LESS` restricts text-only conversion to Bedrock/OpenRouter Llama while keeping `supports_media == True` for `meta/muse-*` models; `build_meta_model()` sets `CacheConfig()` without `strategy="auto"`, `prompt_caching="auto"`, native `web_search`, preserves `model_id_of()` via `_strands_model_ref`, omits `reasoning` on `"none"`/`"off"`, works cleanly across `/btw` with `caching=False`, and redacts `LLM_...` / `LLM|...` tokens in `scrub_credentials()`.
result: pass
evidence:
- Executed via live `run_uat16_test4.py` (`exit 0`, 2026-11-24T19:15:50Z, user accepted `pass` 2026-11-24T19:16Z):
  - `4a`: `supports_media()` `True` for `meta/muse-spark-1.3-contributor`, `meta/muse-wonder-1.0`, `meta/muse-ember-1.0` and `False` for `bedrock/meta.llama3-3-70b-instruct-v1:0`, `bedrock/us.meta.llama4-scout-17b-instruct-v1:0`, `litellm/openrouter/meta-llama/llama-3.3-70b-instruct`; `supports_reasoning("meta/muse-spark-1.3-contributor") == False`.
  - `4b`: `upstream_supports_meta() == False`, `effort="none"`/`"off"` omitted `"reasoning"` (`params={'tools': [{'type': 'web_search'}]}`), `effort="high"` set `reasoning={"effort": "high"}`, `prompt_caching="auto"`, and `model_id_of() == "meta/muse-spark-1.3-contributor"`; live `Agent` turn returned `'7'` with `0` `UserWarning`s.
  - `4c`: live `build_btw_agent()` preserved `side_model_id=meta/muse-ember-1.0` (`caching=False`) and answered `'ORION'`.
  - `4d`: `scrub_credentials()` redacted `LLM|...`, `LLM_...`, and `Bearer LLM|...` to `[redacted]`.

### 5. `docs/QUICKSTART.md` & Live Updated Upstream Issue `strands-agents/harness-sdk#6521` Review (`D-08`)
expected: `docs/QUICKSTART.md` accurately documents `--extra meta`, `MODEL_API_KEY`/`META_API_KEY`/`META_BASE_URL`, priority order `Google -> Anthropic -> OpenAI -> Meta -> OpenRouter -> Bedrock`, Muse pricing/window guidance, and `openai/gpt-6.2-sol`; `docs/upstream/harness_issue_meta_model_api.md` reflects the updated title/body applied in place to `strands-agents/harness-sdk#6521` (with zero comments posted).
result: pass
evidence:
- User accepted review (`pass`, 2026-11-24T19:18Z): `docs/QUICKSTART.md` (lines 52–96, 188–224) and `docs/upstream/harness_issue_meta_model_api.md` (lines 1–83, `Updated: 2026-11-24`, zero `HOLD` banner, obsolete `harness_comment_6521_meta_probe.md` deleted) match live `https://github.com/strands-agents/harness-sdk/issues/6521` (`updatedAt: 2026-11-24T16:44:04Z`, `comments: []`).

### 6. Hermetic Suite, Rig Contracts & All 6 CI Gates on Current `HEAD` (`D-01`..`D-08`, `D-24`)
expected: `pytest tests/ -q` (+ standalone loopback stub), `pytest tests/rig/ -q`, `ruff check`, `ruff format --check`, `xenon --max-absolute C`, `lint-imports`, `uv lock --check`, and `git diff ee42ea2 -- strands_code_agent/` (empty) all pass on current `HEAD`.
result: pass
evidence:
- Verified against `HEAD` (`aab271f`, user accepted `pass` 2026-11-24T19:22Z):
  - `.venv/bin/pytest tests/ -k "not test_stub_server_systemone_decision_routes" -q` (sandboxed): `1704 passed, 12 deselected` in `63.00s`, plus `1 passed` (`190 deselected`, `2.42s`) standalone unsandboxed for `tests/routing/test_routing.py::TestLiveEngines::test_stub_server_systemone_decision_routes` (`1705/1705` default suite green).
  - `.venv/bin/pytest tests/rig/ -q`: `44 passed` in `0.10s`.
  - Static CI gates: `ruff format --check strands_code_cli tests scripts` (`119 files already formatted`), `ruff check strands_code_cli tests scripts` (`All checks passed!`), `xenon --max-absolute C strands_code_cli tests scripts` (`exit 0`), `lint-imports` (`Contracts: 1 kept, 0 broken`, `39` files / `86` deps), `uv lock --check` (`Resolved 156 packages in 2ms`), and `git diff ee42ea2 -- strands_code_agent/` (empty).

## Summary

total: 6
passed: 6
issues: 0
pending: 0
skipped: 0

## Gaps

[none yet]
