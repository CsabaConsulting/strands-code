---
gsd_state_version: "1.0"
milestone: v2.0
current_phase: 16
current_phase_name: First-Class Meta Model API (api.meta.ai / Muse) & Upstream Enablement
current_plan: 3
status: passed
stopped_at: Phase 16 complete + verified (`16-VERIFICATION.md` 7/7, `44b9aa4`, live `m1` M1 PASS, 1705/1705 default suite + 44/44 rig green) — ready for `/gsd-verify-work 16` or `/gsd-discuss-phase 17`
last_updated: "2026-11-24T09:40:00Z"
last_activity: 2026-11-24
last_activity_desc: Executed & verified Phase 16 (`cc99d5a`, `4857960`, `44b9aa4`, `1705/1705` suite + live `driver.py m1` PASS)
state_head: 44b9aa4
progress:
  total_phases: 9
  completed_phases: 4
  total_plans: 11
  completed_plans: 11
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-11-21)

**Core value:** A single ask — spec it, build it, test it, open the PR — completes end to end without the user leaving the conversation.
**Current focus:** Milestone `v2.0` · Phase 16 — First-Class Meta Model API (`api.meta.ai` / Muse) & Upstream Enablement (`MODEL-09`)

## Current Position

Phase: 16 of 21 (First-Class Meta Model API (`api.meta.ai` / Muse) & Upstream Enablement) — Complete (`16-VERIFICATION.md` `7/7`, live `m1` `M1 PASS`)
Plan: 3 of 3 complete in Phase 16 (`cc99d5a`, `4857960`, `44b9aa4`)
Status: Passed (`1705/1705` default suite + `44/44` rig + live `m1` `M1 PASS` + live Meta discovery 7 models)
Last activity: 2026-11-24 — Executed & verified Phase 16 (`cc99d5a`, `4857960`, `44b9aa4`)

Progress: [████░░░░░░] 44%

## Performance Metrics

- `v1.0` shipped 2026-10-16: 12 phases, 41 plans, 129 tasks ([v1.0 Archive](.planning/MILESTONES.md))
- `v2.0` active: 4/9 phases complete (Phases 13–16 done; Phases 17–21 queued)

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

### Pending Todos

- Run `/gsd-verify-work 16` / `/gsd-secure-phase 16` / `/gsd-validate-phase 16` to finish Phase 16 UAT, security & Nyquist sign-off, or advance to Phase 17 (`UPSTREAM-02` `DecisionModel`).
- Review and optionally post held `docs/upstream/harness_comment_6521_meta_probe.md` to `strands-agents/harness-sdk#6521`; monitor `#6510`, `#6521`, and `#6522`.

### Blockers/Concerns

- ✅ ~~[Phase 4→] `reasoningContent` in resumed opus history fails validation on non-reasoning Bedrock models~~ — **Closed in Phase 13** (`strands-agents==1.65.0` `#5166` `BedrockModel._rejects_reasoning_block` + `drop_block` wire strip + `model_switch.prepare_resumed_history()` hybrid restore on non-Bedrock / media-less launches; pinned offline in `TestUpstreamReasoningWireStrip` and `TestPrepareResumedHistory`).
- ✅ ~~[v2.0 Coordination] Phase 14 (`MODEL-06` `first_run.py` preflight) must check non-empty key presence only (no vendor prefix checks) and skip `sts.get_caller_identity()` when `STRANDS_BOX=1`~~ — **Closed in Phase 14** (`first_run.py` checks non-empty env presence only, skips STS for non-AWS providers and `STRANDS_BOX=1`).
- ⚠️ [v2.0 Complexity Budget] `run_loop` (`C 18`) and `_setup_decision_entries` (`C 20`) sit near the `xenon --max-absolute C` ceiling (`CC <= 20`) — Phase 18 & Phase 20 features MUST live in isolated helper modules (`dispatch/help.py`, `dispatch/review.py`, `ui/attachments.py`, `memory/marketplace.py`).
- ⚠️ [Phase 20 / Future LOOP-05 Security] CVE-2026-18830 / CoreBreak boundary — `strands-agents` `event_loop_cycle` executes trailing `toolUse` blocks without model mediation; Phase 20 (`TOOL-05` `@file`/`document`) MUST build `list[ContentBlock]` strictly from allowlisted `text`/`image`/`document` dicts, and any future JSON/headless input (`LOOP-05`) or untrusted snapshot loader must reject/strip caller-supplied `toolUse` blocks.
- ⚠️ [v1.0 Carryover] Silent memory mode can memorialize model rationalizations; `PendingStore` dual-stream lock safety relies on turn discipline (`Phase 6/7` residual notes).

## Session Continuity

Last session: 2026-11-24T09:40:00Z
Stopped at: Phase 16 complete + verified (`16-VERIFICATION.md` 7/7, `44b9aa4`, live `m1` M1 PASS, 1705/1705 default suite + 44/44 rig green) — ready for `/gsd-verify-work 16` or `/gsd-discuss-phase 17`
Resume file: .planning/phases/16-first-class-meta-model-api-muse/16-VERIFICATION.md
