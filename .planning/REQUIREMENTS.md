# Requirements: Strands Code

**Defined:** 2026-11-21
**Milestone:** `v2.0` (Ecosystem Alignment, Marketplaces, Sandbox & Evals)
**Core Value:** A single ask — spec it, build it, test it, open the PR — completes end to end without the user leaving the conversation.

---

## v2.0 Requirements

### Upstream & Routing

- [x] **UPSTREAM-01**: Resync `uv.lock` onto `strands-agents >=1.65` and `strands-harness >=0.4`, adapt `estimate_messages_tokens` and `canonical_prefix_hash` for `ContextInjector` `InjectedBlock`, consume `Model.model_info.limits.context_window`, close the Phase 4 restore-reasoning blocker (`#5166` / `drop_block`), preemptively configure `streaming=False` for `_NO_STREAMING_TOOLS` (Bedrock Llama 3/4), and audit `todos` plugin removal while preserving `steering.py` boundary steering
- [x] **UPSTREAM-02**: Migrate `strands_code_cli/routing/` engine transports onto `strands.decisions.DecisionModel` (`TypeSafeDecisionModel`, `OpenRouterDecisionModel` keeping 64 KiB body caps & inline USD `cost`, `OllamaDecisionModel`, and optional `LLMDecisionModel`), keeping `uncertainty=False` raw probability reading, `0.62`/`0.04` gate, two-call model + effort routing, `apply_model_action`, `/route` UX, and `/cost` actuals

### Models & Auth

- [x] **MODEL-06**: First-class `google/` Gemini provider support (`gemini` optional extra + `_SDK_EXTRA_HINTS`), Box-compatible provider-aware startup preflight replacing the unconditional `Bedrock-or-stop` STS gate, `google/` reasoning support via `_harness_supports_thinking`, cross-vendor `toolUse["reasoningSignature"]` stripping in `convert_history()`, `_vendor_family()` dot-split fix, `litellm_entry` `gemini/` lookup + Gemini discovery/cost tables, and Google AI Studio + Google AI Ultra (\$40–\$100/mo Developer Program credit) setup docs
- [x] **MODEL-07**: First-class native `openai/` API support (`CsabaConsulting/strands-code#17` — `openai = ["strands-agents[openai]", "openai>=2.0.0"]` extra + `_SDK_EXTRA_HINTS`, forwarding `caching=True` & `web_search=True` in `apply_switch()`/`/route`, `litellm_entry` bare-tail lookup + static fallbacks for `GPT-5.4`/`5.6`/`6`/`6.1` & `o3`/`o4-mini`, cache-aware inclusive-`input_tokens` `/cost` discounts, `_vendor_family` `openai` grouping, credential-gated `GET /v1/models` filtered to Responses-capable chat models + curated fallback, non-reasoning / effort-subset guards, Responses-compatible `base_url` handling in `model_for_config()`, documented `use_native_token_count` / `prompt_cache_retention` / `service_tier` / `#3389` replay notes, repeatable UAT & `docs/QUICKSTART.md`)
- [x] **MODEL-08**: First-class native `anthropic/` API support (`CsabaConsulting/strands-code#22` — `anthropic` optional extra + `_SDK_EXTRA_HINTS`, cache-aware exclusive-`input_tokens` `/cost` & context `%` accounting for `cacheReadInputTokens` & `cacheWriteInputTokens`, forwarding `caching=True` & `web_search=True` in `apply_switch()`/`/route`, `litellm_entry` bare-tail lookup + static fallbacks for `Claude 5.5` & `Fable 5.2` 1M, `_vendor_family` `anthropic` grouping, credential-gated `GET /v1/models` caching live `max_input_tokens`/`max_tokens`/`capabilities`/`retires_at`, cross-provider Bedrock↔Direct thinking-signature gating, `SummaryBlock` (`compact-2026-09-04`) & `temporary_messages` switch safety, `anthropic-version: 2026-10-21` / `max_tokens` / PDF-text doc constraints & `use_native_token_count` coverage, repeatable UAT & `docs/QUICKSTART.md`)
- [x] **MODEL-09**: First-class Meta Model API (`api.meta.ai` / Muse) support (`CsabaConsulting/strands-code#21` — empirical `/v1/responses` vs `/v1/messages` protocol probe, upstream `strands-agents/harness-sdk` feature proposal for `meta/` provider + `shared/model-info.json` Muse entries + `#3389` reasoning replay linkage, thin retireable `meta/` adapter on `OpenAIResponsesModel`, Box-compatible `MODEL_API_KEY` zero-AWS preflight, credential-gated `GET /v1/models` discovery & `("meta", "muse")` grouping, `_MEDIA_LESS` Bedrock Llama scoping so multimodal Muse retains media, cache-aware contributor-tier `/cost` & 1M windows, repeatable UAT & `docs/QUICKSTART.md`)

### Skills & Extensibility

- [x] **SKILL-03**: Remote skills marketplace management and lockfile installer (`/skills marketplace add|list|update|remove`, `/skills browse|install|update|sync|remove`), supporting `.agent-plugin/marketplace.json`, `.claude-plugin/marketplace.json`, and direct GitHub `owner/repo[@ref]` sources into `./.agent/skills-marketplaces/<ns>/<skill>/` with `./.agent/skills-lock.json` 40-char `commit_sha` + SHA-256 `computed_hash` pinning, dynamic `/<ns>:` tab completion, and deny-first symlink/zip-slip/protected-path/`allowed-tools` safeguards

### Sandbox & Policy

- [ ] **SANDBOX-01**: First-class Strands Box (`strands-agents/box` `v0.2.3+`) Linux wrapper workflow (`box.toml` + deterministic Dogwood `policy.dw` generator and 7-provider egress profiles with `x-goog-api-key` / `x-api-key` / `Authorization: Bearer` for OpenAI & `api.meta.ai` / OpenRouter path-scoping), protected outside `[agent.filesystem].write`, at least one canonical MFOTL temporal rule (with formal `v2.0` scoped revisit of `D-05`), `STRANDS_BOX=1` `codeact_shell` `sh -c` alignment, and Linux `x86_64` + Ubuntu 24.04 AppArmor setup docs
- [ ] **SANDBOX-02**: Crash-isolated Rust Python VM (`pydantic-monty`) for `strands_code_cli`'s `python_repl` and `CodeactStint` (`sandbox/monty.py`) with stateful multi-turn `feed_run`, explicit narrow host callbacks (`read`/`write`/`edit`/`shell`), memory/timeout caps, `MontyCrashedError` recovery, deterministic worker-pool teardown, `box.toml` runtime compatibility (plus Strands Box embedded Monty evaluation), and clean packaging/fallback while keeping `strands_code_agent/` pristine (`D-24`)

### Interaction & Review

- [ ] **LOOP-06**: Explicit `/help` command (`dispatch/help.py`) registered in `BUILTIN_SLASH_HEADS` sharing a single declarative command table with `USAGE_HINT` and listing loaded skills + shadow warnings via `print_plain`
- [ ] **TOOL-05**: `@file` inline fuzzy attachment picker and `/file` TTY picker (`ui/attachments.py`) confined to gitignore-aware `effective_roots`, only resolving real existing files (never `@dataclass` / `@pytest.mark` code tokens), attaching images and binary docs (`ImageContent`/`DocumentContent`) when `supports_media(current_model)` holds post-routing via strictly allowlisted content-block construction (`text`/`image`/`document` only, never caller-supplied `"toolUse"` blocks; CVE-2026-18830 guard), and extending `model_switch.py` to convert `"document"` blocks across switches
- [ ] **REVIEW-01**: Read-only `/review` command (`dispatch/review.py`) pre-collecting uncommitted (`git diff HEAD`), `--staged`, or `<base-ref>` diffs in Python inside an untrusted-diff boundary and running under a turn-scoped read-only Plan gate (`turn_interface = "tool"`) without mutating sticky `ModeState`

### Evaluation & Red-Teaming

- [ ] **EVAL-01**: Automated evaluation and red-team suite on `strands-agents-evals >=1.10` (`[dependency-groups] dev`) split cleanly under `scripts/evals/` and `tests/evals/` (passing `ruff`, `xenon --max-absolute C`, `import-linter`), running offline deterministic/mocked `TrajectoryEvaluator` + OTel span invariant and prompt-injection canary tests in default CI alongside `@pytest.mark.integration` live `ActorSimulator` + `RedTeamExperiment` (Crescendo/GOAT/PAIR) runs

---

## Future Requirements (`v2.1+`)

- **SKILL-04**: CLI consumes MCP servers as tools via user config (`create_harness(mcp_servers=...)`)
- **LOOP-05**: Non-interactive headless / JSON output mode for scripts and CI (any JSON/headless input loader must explicitly strip or reject caller-supplied `"toolUse"` blocks; CVE-2026-18830 / CoreBreak boundary)
- **TOOL-06**: Export trimmed session content to text file via `/copy`
- **MODE-03**: Fast/thorough effort presets layered over Plan/Act
- **REVIEW-02**: Headless / CI review runner modes

---

## Out of Scope

| Feature | Reason |
|---------|--------|
| Persistent semantic code index | Separate multi-phase project; grep-first suffices |
| Enforced token budgets | Display builds trust; halting mid-task is a separate policy decision |
| Consumer OAuth piggybacking on Gemini CLI / Code Assist | Violates Google ToS; personal Google AI Pro/Ultra plans already provide \$10–\$100/mo Developer Program credits usable via a standard AI Studio API key |
| Replacing `apply_model_action` with `strands.models.routing.ModelRouter` | `ModelRouter` pre-instantiates all candidate models, skips `convert_history()` + `RichHistory` stashes, and falls back to candidate 0 instead of holding current model |
| Replacing `BeforeToolCallEvent.cancel_tool` with `Agent.cancel()` | `Agent.cancel()` terminates the entire turn rather than redirecting at the next tool boundary |
| Honoring remote skill `allowed-tools` as permission grants | Remote `SKILL.md` frontmatter cannot bypass deny-first `PolicyClassifier` or diff gates |
| TypeScript runtime dependency (`@strands-agents/cli`) | `strands-code` remains 100% Python on `harness-py` + `strands-py` |
| Heavy external recall backends (Hindsight / OpenViking) | Rejected in `v1.0` Phase 12; Strands native markdown memory stays the backend |

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| UPSTREAM-01 | Phase 13 | Complete |
| MODEL-06 | Phase 14 | Complete |
| MODEL-07 | Phase 15 | Complete |
| MODEL-08 | Phase 15 | Complete |
| MODEL-09 | Phase 16 | Complete |
| UPSTREAM-02 | Phase 17 | Complete |
| SKILL-03 | Phase 18 | Complete |
| SANDBOX-01 | Phase 19 | Pending |
| SANDBOX-02 | Phase 20 | Pending |
| LOOP-06 | Phase 21 | Pending |
| TOOL-05 | Phase 21 | Pending |
| REVIEW-01 | Phase 21 | Pending |
| EVAL-01 | Phase 22 | Pending |

**Coverage:**
- `v2.0` requirements: 13 total
- Mapped to phases: 13
- Unmapped: 0 ✓

---
*Requirements defined: 2026-11-21 (Milestone v2.0)*
