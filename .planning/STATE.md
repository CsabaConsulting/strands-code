---
gsd_state_version: "1.0"
milestone: v2.0
current_phase: 17
current_phase_name: Decision Routing Convergence (DecisionModel)
current_plan: 3
status: completed
stopped_at: Phase 17 UAT & security audit complete (`17-UAT.md` 6/6 pass, `17-SECURITY.md` 10/10 closed / threats_open 0, `17-VERIFICATION.md` 7/7 PASS, `17-VALIDATION.md` validated) — ready for `/gsd-discuss-phase 18`
last_updated: "2026-11-25T00:25:00Z"
last_activity: 2026-11-24
last_activity_desc: Completed Phase 17 ASVS L1 security audit (`17-SECURITY.md` 10/10 closed, `threats_open: 0`; hardened `valid_base_url`, `preflight_get`/`local_engine_ready`, `_is_loopback_host`, `follow_redirects=False`, strict `NaN`/`Infinity` rejection, `read_env_api_key`, `valid_model_id`, and `_sanitize_uncertain_reason`; all 6 CI gates + 1745+1 suite + 44 rig green)
state_head: c05f89e
progress:
  total_phases: 9
  completed_phases: 5
  total_plans: 14
  completed_plans: 14
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-11-21)

**Core value:** A single ask — spec it, build it, test it, open the PR — completes end to end without the user leaving the conversation.
**Current focus:** Milestone `v2.0` · Phase 17 Complete (`DecisionModel`, `UPSTREAM-02`) — queued: Phase 18 (`SKILL-03`)

## Current Position

Phase: 17 of 21 (Decision Routing Convergence (`DecisionModel`)) — Complete (`17-VERIFICATION.md` PASS)
Plan: 3 of 3 complete in Phase 17 (`17-01`, `17-02`, `17-03`)
Status: Complete (`UPSTREAM-02` verified; ready for Phase 18)
Last activity: 2026-11-24 — Completed Phase 17 (`f6d8651`, `a8e9993`, `b474041`, `17-VERIFICATION.md`, `17-VALIDATION.md`)

Progress: [█████░░░░░] 56%

## Performance Metrics

- `v1.0` shipped 2026-10-16: 12 phases, 41 plans, 129 tasks ([v1.0 Archive](.planning/MILESTONES.md))
- `v2.0` active: 5/9 phases complete (Phases 13–17 done; Phases 18–21 queued)

## Accumulated Context

### Decisions

Key `v1.0` decisions remain archived in `.planning/PROJECT.md`. Active `v2.0` alignment anchors:
- Keep `apply_model_action` + pre-turn `convert_history()` + `RichHistory` stashes (do not replace with `ModelRouter`).
- Keep `BeforeToolCallEvent.cancel_tool` in `steering.py` for mid-turn redirection (`Agent.cancel()` aborts full turns).
- Pure Python stack (`harness-py` + `strands-py`, zero TypeScript); byproduct-only upstream PRs to `harness-sdk` / `sample-strands-code-agent`.
- Consumer OAuth piggybacking on Gemini CLI / Code Assist rejected (ToS violation); personal Google AI Ultra works via AI Studio API keys funded by \$40–\$100/mo Developer Program credits.
- Scoped revisit of `D-05` queued for Phase 19 (`SANDBOX-01`): host-side deterministic Dogwood (`policy.dw`) inside Strands Box only.
- Phase 13 (`31ecc3e`, `8c8b70f`): `strands-agents>=1.65.0` / `strands-harness>=0.4.0` locked with no upper pins (`D-01`); route-aware `window_for` (`D-02`); preemptive Bedrock `streaming=False` for `_NO_STREAMING_TOOLS` (`D-03`); hybrid session restore via `prepare_resumed_history` + `#5166` wire stripping (`D-04`); `InjectedBlock` token/hash/fork handling (`D-05`); `PolicyHumanInTheLoop` preserves `[deny]` / Plan-mode `Deny.reason` under 1.65 inline HITL actions.
- Phase 13 post-verify hardening & live UAT (`51b15b6`, `9fecb81`, `900a7d9`, `073c9e1`): closed `T-13-02` stale `_last_by_tag` HITL window (`13-SECURITY.md`); added Bedrock-scoped unary `_NO_STREAMING_TOOLS` rows for verified Mistral Large 24.02/24.07, Pixtral Large 25.02, and Writer Palmyra X4/X5 (plus `"bedrock"` scoping on Meta Llama 3/4); added repeatable `u1`/`u2`/`u3` tmux UAT scenarios in `scripts/uattest/scenarios_upstream.py`.
- Phase 14 (`947c5a7`, `52b0963`, `a2395d4`): added `gemini` optional extra + `_SDK_EXTRA_HINTS["google"]`; replaced unconditional STS preflight with Box-compatible presence-only multi-provider gate + `--model` session flag; added `google/` `supports_reasoning`, cross-vendor `toolUse["reasoningSignature"]` stripping with `RichHistory` / `canonical_prefix_hash` preserve, decimal-safe `_vendor_family`, Gemini 2.5 `thinking_budget` adapter (`configure_gemini_for_model` across 4 sites), credential-gated `/model` discovery, `litellm_entry` `gemini/` + static Gemini tables + non-Bedrock Price List skip, `driver.py g1` rig, and `docs/QUICKSTART.md` Ultra credit guide + `docs/upstream/harness_issue_gemini25_thinking.md` (filed `strands-agents/harness-sdk#6510`).
- Phase 14 post-verify UAT, security audit & Nyquist validation (`05c68a2`, `82f3760`, `3a4912c`): `14-UAT.md` `6/6 PASS`; closed `T-14-02` (third-party `smolagents.remote_executors:48` / `litellm._process_defaults:24` calling `dotenv.load_dotenv()` on CWD `.env` at import time) via `disable_cwd_dotenv()` in `entry/first_run.py` + `strands_code_cli/__init__.py` (`TestCwdDotenvGuard`, `14-SECURITY.md` `10/10 closed`); filled 7 Nyquist branch tests (`14-VALIDATION.md` `1654 passed`).
- Roadmap expansion (2026-11-23): inserted Phase 15 (`MODEL-07`/`MODEL-08` native OpenAI `#17` & Anthropic `#22`) and Phase 16 (`MODEL-09` Meta Model API `api.meta.ai` / Muse `#21`, upstream draft `docs/upstream/harness_issue_meta_model_api.md`) right after Phase 14, and cleanly renumbered unstarted Phases 15–19 -> 17–21 (expanding Phase 19 Strands Box egress profiles to 7 providers).
- Phase 15 (`27bedc5`, `15d98a4`, `eeceb59`, `b102735`, `3b8ab4f`): added `openai` (`openai>=2.0.0`) & `anthropic` extras + `_SDK_EXTRA_HINTS`, bumped `_AMBIENT_DEFAULT_MODELS` (`claude-sonnet-5-5`, `gpt-6.1-sol`), added `ProviderConfig.api_mode` & harness-preserving `base_url`, shared `resolve_harness_model()` preserving `caching` + `web_search`, normalized inclusive/exclusive `/cost` & cache-discounted usage accounting, added 24h `anthropic-models.json` cache feeding `window_for()` & retiring `route_label()`, gated signed thinking & `SummaryBlock` on `same_provider() and same_vendor()`, added fail-soft `configure_openai_for_model()` guard (filed `strands-agents/harness-sdk#6522`), added `driver.py o1`/`an1` rigs (`O1 PASS`, `AN1 PASS`) + `docs/QUICKSTART.md`, and filed Meta Model API feature proposal `strands-agents/harness-sdk#6521`.
- Phase 15 UAT & GPT-6.2 bridge (`fa51c2d`, `15-UAT.md` `6/6 PASS`): added `gpt-6.2-sol` (\$2/\$10/\$0.10) & `gpt-6.2-astra` (\$8/\$40/\$0.40) pricing, `1.05M` window, effort guard, and retireable `model_info` bridge while keeping `openai/gpt-6.1-sol` as the ambient default until an intentional upstream resync to `strands-agents>=1.66.0` / `strands-harness>=0.5.0` (which ships `#6265` GPT-6.2 `model-info` and `#6396` Responses system-prompt caching fix).
- Phase 15 security audit (`8368ddb`, `15-SECURITY.md` `10/10 closed`): closed `T-15-02` (scoped `base_url` by `_base_url_provider` across `build_agent`, `_root`, `apply_switch`, `_route_side_spawn`, `build_btw_agent`, and `ProviderConfig.save_model_choice()`), `T-15-03` (strict `_validate_base_url()`, `0o600` temp-symlink-safe config write, and OpenAI `sk-(?:proj-|svcacct-)?` redaction in `scrub_credentials()`), and `T-15-04` (`_ISO_DATE_RE` sanitization in `route_label()` + symlink-refusing `0o600` atomic cache helpers in `live_pricing.py`).
- Phase 15 Nyquist validation (`638bc2e`, `15-VALIDATION.md` `validated`): filled remaining branch tests across `entry/`, `cost/`, and `model/` (`1694/1694` default suite + `42/42` rig green).
- Phase 16 discussion (`16-CONTEXT.md` `D-01`–`D-08`): locked ambient default `meta/muse-spark-1.3-contributor` ordered `Google -> Anthropic -> OpenAI -> Meta -> OpenRouter -> Bedrock`, `meta` optional extra alias + `MODEL_API_KEY`/`META_API_KEY`/`META_BASE_URL`, live `api.meta.ai/v1` probe + retireable `meta/` adapter + live `driver.py m1` UAT, folded `strands-agents>=1.66.0` / `strands-harness>=0.5.0` upstream resync retiring `_gpt_62_model_info_fallback()` and bumping OpenAI ambient default to `openai/gpt-6.2-sol`, `_MEDIA_LESS` Bedrock Llama scoping, cache-aware contributor `/cost`, and held `docs/upstream/harness_comment_6521_meta_probe.md` draft for `#6521`.
- Phase 16 (`cc99d5a`, `4857960`, `44b9aa4`): resynced to `strands-agents==1.66.0` & `strands-harness==0.5.0` (retired `_gpt_62_model_info_fallback()`, gated native `web_search` on `_web_search_kind == "native"`, adapted Claude-on-Bedrock `AnthropicModel(AsyncAnthropicBedrock)` tests, bumped OpenAI default to `openai/gpt-6.2-sol`); added `meta` extra + `_SDK_EXTRA_HINTS["meta"]` + `first_run` helpers + auto-retiring `build_meta_model()` (`CacheConfig()`, `prompt_caching="auto"`, omitted `reasoning` on `"none"`/`"off"`, `_strands_model_ref`); narrowed `_MEDIA_LESS` for multimodal Muse + added filtered `GET /v1/models` Meta discovery (`("meta", "muse")` grouping), LiteLLM/static `muse-ember-1.0` & 50× contributor pricing + `LLM_...`/`LLM|...` scrubbing, repeatable `driver.py m1` (`M1 PASS`), `docs/QUICKSTART.md` guide, and held `docs/upstream/harness_comment_6521_meta_probe.md`.
- Phase 16 UAT & `#6521` update (`1e07618`, `aab271f`, `2247b47`, `16-UAT.md` `6/6` passed): merged empirical probe findings into `docs/upstream/harness_issue_meta_model_api.md`, updated `strands-agents/harness-sdk#6521` title and body in place (`0` comments), and completed `16-UAT.md` (`6/6` passed).
- Phase 16 security audit (`4d32cbc`, `16-SECURITY.md` `10/10 closed`, `threats_open: 0`): closed `T-16-02` (isolated Meta `OpenAIResponsesModel` / discovery client args via `_meta_openai_client_args()` overriding `OPENAI_API_KEY`/`OPENAI_ADMIN_KEY`/`OPENAI_ORG_ID`/`OPENAI_PROJECT_ID`/`OPENAI_WEBHOOK_SECRET`/`OpenAI-*` headers), `T-16-03` (`_validate_base_url()` in `configure_base_url_for_model()`, `_has_unsafe_model_chars()` guard on Meta IDs, and `timeout=5.0, max_retries=0` on discovery), and `T-16-04` (widened `LLM_...`/`LLM|...` scrubbing regex + `MODEL_API_KEY` canary isolation test).
- Phase 16 Nyquist validation (`16-VALIDATION.md` `validated`, `nyquist_compliant: true`): closed 12 edge branches across `tests/model/`, `tests/entry/`, `tests/dispatch/`, `tests/cost/`, and `tests/loop/` (`1711/1711` default suite + `44/44` rig green, zero runtime edits).
- Phase 17 discussion (`17-CONTEXT.md` `D-01`–`D-07`): converged `native` onto upstream `TypeSafeDecisionModel` (`state: str` + folded `Question["question"]`), `openrouter` & `local` onto CLI `DecisionModel` subclasses (`OpenRouterDecisionModel`, `OllamaDecisionModel`) in `routing/transports.py`, wired config-only opt-in `"decisions_api"` (`DecisionsAPIDecisionModel` / `JEV_API_KEY`) and `"llm"` (`LLMDecisionModel` / `uncertainty=True` hold on `Uncertain` / `cost_for()`), async-to-sync bridge + per-call `httpx.AsyncClient(timeout=10s)`, preserving `0.62`/`0.04` gating, two-call routing, `apply_model_action`, `/cost` actuals, and offline + opportunistic live verification.
- Phase 17 planning (`17-RESEARCH.md`, `17-PATTERNS.md`, `17-01..03-PLAN.md`, `17-VALIDATION.md`, `17-PLAN-CHECK.md` PASS): mapped Waves 1–3 with `tests/routing/test_routing_transports.py` as Wave 0 file, 4-decimal grid tolerance alignment, `ConnectError` zero-retry preservation, `resolve_harness_model(..., web_search=False, caching=False)`, `cost_context` estimated lane for `llm` routing spend, `conftest.py` key scrubbing (`TYPESAFE_API_KEY`/`JEV_API_KEY` + `@pytest.mark.integration` exemption), and `TYPESAFE_API_KEY` vs `JEV_API_KEY` docs.
- Phase 17 (`f6d8651`, `a8e9993`, `b474041`, `c05f89e`, `1ea2872`): converged `routing/transports.py` onto `strands.decisions.DecisionModel` (`OpenRouterDecisionModel`, `OllamaDecisionModel`, `TypeSafeDecisionModel` bridge, config-only `decisions_api`/`DecisionsAPIDecisionModel` + `JEV_API_KEY` defaulting to `~typesafe/jev-latest`, config-only `llm`/`LLMDecisionModel` with `uncertainty=True` hold on `Uncertain`, `effort="off"`, `web_search=False`, `caching=False`, and `cost_for()` estimated `/cost` lane); preserved `0.62`/`0.04` gating, two-call routing, `apply_model_action`/`convert_history()`/`RichHistory`, `save_strategy` (`CC 20`), `_setup_decision_entries` (`CC 20`), `price_table` (`CC 20`), and pristine `strands_code_agent/`; verified live `-m integration` (`5 passed, 1 skipped` across OpenRouter, TypeSafe x2, `decisionapi.net`, and Gemini), `44/44` rig contract tests, `1737 + 1` full suite, all 6 CI gates (`17-VERIFICATION.md` 7/7 PASS, `17-VALIDATION.md` validated), and interactive UAT (`17-UAT.md` `6/6` passed, observing upstream `GeminiModel.structured_output` omits usage while `AnthropicModel.structured_output` emits live tokens for `/cost`).
- Phase 17 security audit (`17-SECURITY.md` `10/10 closed`, `threats_open: 0`, `status: verified`): remediated `T-17-03` HIGH (`valid_base_url()` creds/controls/query/fragment/port checks, `preflight_get()`/`local_engine_ready()` URL pre-check, full IPv4/IPv6 `_is_loopback_host()` loopback suppression), `T-17-06` HIGH (`follow_redirects=False` on `make_async_client`/`make_sync_client`, strict `parse_constant` rejection of `NaN`/`Infinity`), `T-17-07` MEDIUM (`valid_model_id()` whitespace/control-char rejection in `_assign_engine_string`/`_validate_engine_model_ids`/`run_*_decision`), `T-17-01` (`read_env_api_key()` whitespace/control-char filtering + `disable_cwd_dotenv()` verified for `TYPESAFE_API_KEY`/`JEV_API_KEY`), and `T-17-02` (`_sanitize_uncertain_reason()` control-char strip + canary-free OTel spans/errors + `scrub_credentials()`), verified across `1745 + 1` non-integration suite + `44/44` rig + all 6 CI gates (`_parse_engine` `16 -> 12`).

### Pending Todos

- Run `/gsd-discuss-phase 18` to start Phase 18 (`SKILL-03` Remote skills marketplace management and lockfile installer).
- Monitor upstream issues `strands-agents/harness-sdk#6510`, `#6521` (title and body updated in place on 2026-11-24 with empirical probe results), and `#6522`.

### Blockers/Concerns

- ✅ ~~[Phase 4→] `reasoningContent` in resumed opus history fails validation on non-reasoning Bedrock models~~ — **Closed in Phase 13** (`strands-agents==1.65.0` `#5166` `BedrockModel._rejects_reasoning_block` + `drop_block` wire strip + `model_switch.prepare_resumed_history()` hybrid restore on non-Bedrock / media-less launches; pinned offline in `TestUpstreamReasoningWireStrip` and `TestPrepareResumedHistory`).
- ✅ ~~[v2.0 Coordination] Phase 14 (`MODEL-06` `first_run.py` preflight) must check non-empty key presence only (no vendor prefix checks) and skip `sts.get_caller_identity()` when `STRANDS_BOX=1`~~ — **Closed in Phase 14** (`first_run.py` checks non-empty env presence only, skips STS for non-AWS providers and `STRANDS_BOX=1`).
- ⚠️ [v2.0 Complexity Budget] `run_loop` (`C 18`) and `_setup_decision_entries` (`C 20`) sit near the `xenon --max-absolute C` ceiling (`CC <= 20`) — Phase 18 & Phase 20 features MUST live in isolated helper modules (`dispatch/help.py`, `dispatch/review.py`, `ui/attachments.py`, `memory/marketplace.py`).
- ⚠️ [Phase 20 / Future LOOP-05 Security] CVE-2026-18830 / CoreBreak boundary — `strands-agents` `event_loop_cycle` executes trailing `toolUse` blocks without model mediation; Phase 20 (`TOOL-05` `@file`/`document`) MUST build `list[ContentBlock]` strictly from allowlisted `text`/`image`/`document` dicts, and any future JSON/headless input (`LOOP-05`) or untrusted snapshot loader must reject/strip caller-supplied `toolUse` blocks.
- ⚠️ [v1.0 Carryover] Silent memory mode can memorialize model rationalizations; `PendingStore` dual-stream lock safety relies on turn discipline (`Phase 6/7` residual notes).

## Session Continuity

Last session: 2026-11-25T00:25:00Z
Stopped at: Phase 17 UAT & security audit complete (`17-UAT.md` 6/6 pass, `17-SECURITY.md` 10/10 closed, `threats_open: 0`) — ready for `/gsd-discuss-phase 18`
Resume file: .planning/phases/17-decision-routing-convergence-decisionmodel/17-SECURITY.md
