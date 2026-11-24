---
status: complete
phase: 15-first-class-native-openai-anthropic-apis
source: [15-01-SUMMARY.md, 15-02-SUMMARY.md, 15-03-SUMMARY.md, 15-VERIFICATION.md]
started: 2026-11-24T06:34:00Z
updated: 2026-11-24T07:44:00Z
---

# Phase 15 User Acceptance Testing (`MODEL-07`, `MODEL-08`)

## Current Test

[testing complete]

## Tests

### 1. Zero-AWS Ambient Auto-Pick, Session-Scoped `--model`, & `ProviderConfig.api_mode` (`D-01`, `D-04`, `D-07`)
expected: With AWS and other provider env vars stripped under a clean XDG_CONFIG_HOME, launching `strands-code` without `--model` auto-picks `openai/gpt-6.1-sol` (1.05M) when only `OPENAI_API_KEY` is set and `anthropic/claude-sonnet-5-5` (1.00M) when only `ANTHROPIC_API_KEY` is set, leaving `config.yaml` absent; explicit `anthropic/` + `base_url` passes preflight without `ANTHROPIC_API_KEY`; `ProviderConfig.api_mode` (`responses` vs `chat`) persists cleanly without secrets.
result: pass
evidence:
- Executed via live `run_uat15_test1.py` (`exit 0`, 2026-11-24T06:39:31Z, AWS and competing provider env vars stripped, isolated `XDG_CONFIG_HOME`):
  - `1a` (`OPENAI_API_KEY` alone, no `--model`): booted to REPL and `/context` reported `openai/gpt-6.1-sol` / `input tokens: 0 (0% of 1.05M)` with `config_yaml_exists: False`.
  - `1b` (`ANTHROPIC_API_KEY` alone, no `--model`): booted to REPL and `/context` reported `anthropic/claude-sonnet-5-5` / `input tokens: 0 (0% of 1.00M)` with `config_yaml_exists: False`.
  - `1c`: `preflight_credentials(model="anthropic/claude-sonnet-5-5", base_url="https://proxy.example/v1")` with empty `os.environ` succeeded cleanly without `ANTHROPIC_API_KEY`.
  - `1d`: `ProviderConfig` round-tripped `api_mode="chat"` (`{'api_mode': 'chat', 'base_url': 'https://proxy.example/v1', 'model': 'openai/gpt-6.1-sol'}`) and `api_mode="responses"`, and raised `ValueError` on `api_mode="legacy"`.

### 2. Live Native OpenAI & Anthropic Tool Turns, Cache-Aware `/cost`, & Same-Provider Switches (`D-02`, `D-03`, `D-08` — `driver.py o1` & `an1`)
expected: Zero-AWS `driver.py o1` (`openai/gpt-6.1-sol` -> `openai/gpt-6.1-terra`) and `driver.py an1` (`anthropic/claude-sonnet-5-5` -> `anthropic/claude-haiku-5-5`) boot cleanly, display normalized cache-aware usage lines (`cached`) and discounted `/cost` rows (`cached` + `write`, `Display only`), and keep messages across same-provider `/model` switches with zero `Dropping reasoningContent` warnings.
result: pass
evidence:
- Fresh live runs against `HEAD` (`fa51c2d`, 2026-11-24T07:11Z–07:14Z, zero-AWS + isolated `XDG_CONFIG_HOME`):
  - `driver.py o1` -> `O1 PASS` (`/tmp/uatr8/o1.log`): `/context` `openai/gpt-6.1-sol` `0% of 1.05M`, `read` turn returned `OPENAI_SENTINEL_15`, usage `13.39K (1%, 49% cached) $0.02`, `/cost` `turn 1: in 13.39K (6.62K cached, 6.68K write), out 51, $0.0181` (`Display only — no budgets or enforcement.`), `/model openai/gpt-6.1-terra` kept 4 messages with zero `Dropping reasoningContent` warnings.
  - `driver.py an1` -> `AN1 PASS` (`/tmp/uatr8/an1.log`): `/context` `anthropic/claude-sonnet-5-5` `0% of 1.00M`, `read` turn returned `ANTHROPIC_SENTINEL_15`, usage `14.40K (1%, 49% cached) $0.02`, `/cost` `turn 1: in 14.40K (7.06K cached, 7.16K write), out 89, $0.0199` (`Display only — no budgets or enforcement.`), `/model anthropic/claude-haiku-5-5` kept 4 messages with zero `Dropping reasoningContent` warnings.

### 3. Credential-Gated Multi-Provider `/model` Discovery, `_vendor_family` Grouping & Retiring Labels (`D-06`)
expected: Live `discover_models()` / `/model` picker discovers Responses-capable OpenAI chat models (excluding embeddings/whisper/tts/image/realtime/moderation/instruct) under `openai` (`gpt`, `o3`/`o4`, `gpt-oss`) and Anthropic models under `anthropic` (`claude`), caches Anthropic `/v1/models` metadata in `anthropic-models.json` for 24h, appends `(retires YYYY-MM-DD)` in `route_label()` for retiring models (e.g., `claude-sonnet-4-5-20250929`, `claude-opus-4-5-20251101`), and omits OpenAI/Anthropic completely when unkeyed.
result: pass
evidence:
- Executed via live `run_uat15_test3.py` (`exit 0`, 2026-11-24T07:22:42Z, AWS & Google env stripped, isolated `STRANDS_CODE_CACHE_DIR`):
  - `3a`: `offline=False`, discovered `52` OpenAI models (including `openai/gpt-6-astra`, `openai/gpt-6-luna`, `openai/gpt-6-sol`, `openai/gpt-6.1-sol`, `openai/gpt-6.1-terra`, `openai/gpt-6.2-astra`, `openai/gpt-6.2-sol`; zero non-chat token leaks) and `15` Anthropic models (including `anthropic/claude-sonnet-5-5`).
  - `3b`: `build_model_tree()` grouped `vendors=['anthropic', 'openai']`, `openai_families=['gpt', 'o3']`, `anthropic_families=['claude']`; `_vendor_family` verified `gpt-oss-120b` -> `('openai', 'gpt-oss')`, `gpt-6.2-sol` -> `('openai', 'gpt')`, `o3`, `o4-mini`, `claude-sonnet-5-5`.
  - `3c`: Wrote 24h `anthropic-models.json` (`15` entries, `2` retiring), `route_label()` rendered `anthropic/claude-opus-4-5-20251101 (retires 2027-01-22)` and `anthropic/claude-sonnet-4-5-20250929 (retires 2026-11-30)` with `normalize_model_ref()` verbatim; `window_for("anthropic/claude-sonnet-5-5") == 1_000_000`, `window_for("openai/gpt-6.2-sol") == 922_000` (LiteLLM live `max_input_tokens`) and `window_for("openai/gpt-6.2-sol", model=real_62) == 1_050_000`.
  - `3d`: With provider keys stripped and `boto3=None`, `discover_models(configured=["bedrock/x"])` returned `( ['bedrock/x'], True )` with zero OpenAI/Anthropic/Google leakage.

### 4. Cross-Provider Thinking (`anthropic/` <-> `bedrock/anthropic.*`), `SummaryBlock` Safety & Live OpenAI Non-Reasoning Guard (`D-05`, `D-07`)
expected: Switching from `anthropic/claude-sonnet-5-5` (signed thinking) -> `bedrock/us.anthropic.claude-sonnet-4-6` or `openai/gpt-6.1-sol` converts raw signed thinking to `TRACE_LABEL` text without validation errors and restores stashed thinking on return to `anthropic/`; launching a live non-reasoning OpenAI model (`openai/gpt-4o` or `openai/gpt-4.1-mini`) completes a turn cleanly via `configure_openai_for_model()` stripping `params["reasoning"]` (`harness-sdk#6522`); `SummaryBlock` converts safely across non-Anthropic switches and `/btw`.
result: pass
evidence:
- Executed via live `run_uat15_test4.py` against `HEAD` (`fa51c2d`, 2026-11-24T07:31Z–07:34Z, AWS & Google env stripped, isolated workdir/XDG/cache):
  - `4a` (live Anthropic signed thinking -> Bedrock/OpenAI -> restore): `anthropic/claude-sonnet-5-5` solved CRT (`1347`) with live signed `reasoningContent` (`initial_thinking=1`), `convert_history(..., "bedrock/us.anthropic.claude-sonnet-4-6")` stripped raw thinking into `TRACE_LABEL` text (`bedrock_trace=1`), live switch to `openai/gpt-6.1-sol` answered `1347` cleanly, and live switch back to `anthropic/claude-sonnet-5-5` restored signed thinking (`4 messages kept, thinking restored`) and answered `RESTORED_OK`.
  - `4b` (live non-reasoning OpenAI guard `harness-sdk#6522`): `openai/gpt-4.1-mini` booted with `reasoning` stripped and answered `4`; live switch with `effort="high"` to `openai/gpt-4o` stripped `reasoning` cleanly and answered `7` (`4 messages kept`).
  - `4c` (`SummaryBlock` isolation): `anthropic/ -> anthropic/` kept `"summary"` verbatim (`1`); switches to `openai/gpt-6.1-sol` and `bedrock/us.anthropic.claude-sonnet-4-6` plus `fork_btw_history()` dropped raw `"summary"`/`"reasoningContent"` blocks and emitted `SUMMARY_LABEL` text cleanly.
  - `4d` (live `openai/gpt-6.2-sol` smoke check): booted with `context_window_limit=1_050_000` (`1.05M`), completed live arithmetic turn (`13`), and rendered cache-aware metrics (`13.61K (1%, 46% cached) $0.02`, `/cost` populated).

### 5. `docs/QUICKSTART.md` & Filed Upstream Issues Review (`D-07`, `D-08`)
expected: `docs/QUICKSTART.md` accurately covers ambient defaults (`claude-sonnet-5-5`, `gpt-6.1-sol`), `--extra openai`/`anthropic`, custom `base_url` + `api_mode: chat`, cache-aware `/cost`, and provider mannerisms; `docs/upstream/harness_issue_openai_reasoning_guard.md` (`#6522`) and `docs/upstream/harness_issue_meta_model_api.md` (`#6521`) record their filed URLs cleanly.
result: pass
evidence:
- User accepted review (`pass`, 2026-11-24T07:39:09Z): `docs/QUICKSTART.md` (lines 44–147, 223–243), `docs/upstream/harness_issue_openai_reasoning_guard.md` (`https://github.com/strands-agents/harness-sdk/issues/6522`), and `docs/upstream/harness_issue_meta_model_api.md` (`https://github.com/strands-agents/harness-sdk/issues/6521`) verified.

### 6. Hermetic Suite, Rig Contracts & All 6 CI Gates on `HEAD` (`D-01`..`D-08`, `D-24`)
expected: `pytest tests/ -q` (+ standalone loopback stub), `ruff check`, `ruff format --check`, `xenon --max-absolute C`, `lint-imports`, `uv lock --check`, and `git diff ee42ea2 -- strands_code_agent/` (empty) all pass on `HEAD`.
result: pass
evidence:
- Verified against `HEAD` (`fa51c2d`, user accepted `pass` 2026-11-24T07:43:56Z):
  - `uv run pytest tests/ -q` (sandboxed): `1682 passed`, 11 deselected (`integration`), plus `1 passed` standalone unsandboxed for `tests/routing/test_routing.py::TestLiveEngines::test_stub_server_systemone_decision_routes` (`1683/1683` default suite green).
  - `uv run pytest tests/rig/ -q`: `42 passed`.
  - Static CI gates: `ruff check` (`All checks passed!`), `ruff format --check` (`117 files already formatted`), `xenon --max-absolute C` (`exit 0`), `lint-imports` (`1 kept, 0 broken`), `uv lock --check` (`exit 0`), and `git diff ee42ea2 -- strands_code_agent/` (empty).

## Summary

total: 6
passed: 6
issues: 0
pending: 0
skipped: 0

## Gaps

[none yet]
