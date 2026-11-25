# Roadmaps & Milestones

## Milestones

- ✅ **v1.0 Conversational Coding CLI** — Phases 1–12 (shipped 2026-10-16) — [Archive](milestones/v1.0-ROADMAP.md)
- 🚧 **v2.0 Ecosystem Alignment, Marketplaces, Sandbox & Evals** — Phases 13–22 (in progress)

---

## Overview (`v2.0`)

`v2.0` brings `strands-code` into alignment with the evolved Strands ecosystem (`strands-py >=1.65`, `harness-py >=0.4.0`, `strands-agents/box` Linux, `pydantic-monty`, `strands-agents-evals >=1.10`), adds first-class Google AI Gemini support (compatible with personal Google AI Ultra Developer Program credits), first-class native OpenAI, Anthropic, and Meta (`api.meta.ai` / Muse) API support, and provider-aware startup, introduces deny-first remote skills marketplaces with SHA/hash lockfiles, layers Strands Box OS containment beneath HITL approvals alongside a crash-isolated Monty Rust Python VM for `python_repl` & CodeAct, delivers `/help` + `@file` + `/review`, and closes with an automated `strands-evals` regression & red-team suite.

## Phases

- [x] **Phase 13: Upstream SDK & Harness Resync** — Lock `strands-agents >=1.65` & `strands-harness >=0.4`, retire `#5166`/`#5158` workarounds, adapt `InjectedBlock` & `Model.model_info`, enable non-streaming Bedrock Llama tools (completed 2026-11-21)
- [x] **Phase 14: First-Class Google Gemini & Provider-Aware Startup** — `gemini` extra, Box-compatible provider-aware preflight, cross-provider `reasoningSignature` & `_vendor_family` fixes, `/model` Gemini discovery, `/cost` tables, AI Studio Ultra credit docs (completed 2026-11-22)
- [x] **Phase 15: First-Class Native OpenAI & Anthropic APIs** (`#17`, `#22`) — `openai` & `anthropic` extras, cache-aware `/cost` & context `%`, `caching`/`web_search` switch preservation, live `/v1/models` discovery & Anthropic metadata cache, API mannerisms, UAT & docs
- [x] **Phase 16: First-Class Meta Model API (`api.meta.ai` / Muse) & Upstream Enablement** (`#21`) — Live `/v1/responses` vs `/v1/messages` probe, upstream `strands-agents/harness-sdk` `meta/` proposal, thin `meta/` adapter, `MODEL_API_KEY` preflight, `/model` discovery, multimodal `_MEDIA_LESS` fix & contributor cache `/cost`
- [x] **Phase 17: Decision Routing Convergence (`DecisionModel`)** — Migrate `routing/` engine transports onto `strands.decisions.DecisionModel` while preserving `apply_model_action`, `0.62`/`0.04` gate, two-call effort flow & `/cost` actuals
- [x] **Phase 18: Skills Marketplaces & Lockfile Installer** — `/skills marketplace|browse|install|update|sync|remove`, `./.agent/skills-marketplaces/` + `./.agent/skills-lock.json`, dynamic `<ns>:` completion & deny-first supply-chain guards (completed 2026-11-24)
- [ ] **Phase 19: Strands Box Linux Sandbox Floor & Dogwood Policy** — `box.toml` + `policy.dw` generator, 7-provider egress profiles, temporal Dogwood rule + scoped `D-05` revisit, `STRANDS_BOX=1` `codeact_shell` alignment & Ubuntu 24.04 AppArmor docs
- [ ] **Phase 20: Monty Python VM for `python_repl` & CodeAct** — Crash-isolated Rust Python VM (`pydantic-monty`) replacing in-process `smolagents` in `strands_code_cli`, explicit host callbacks (`read`/`write`/`edit`/`shell`), memory/timeout caps, worker teardown, `box.toml` compatibility & optional Strands Box Monty alignment
- [ ] **Phase 21: CLI Ergonomics (`/help`, `@file` / `/file`, `/review`)** — Isolated UX modules respecting `xenon C <= 20`, `"document"` history conversion & Python-collected read-only `/review`
- [ ] **Phase 22: Strands Evals & Red-Team Suite** — `strands-agents-evals >=1.10` in `scripts/evals/` + `tests/evals/`, offline CI trajectory/canary invariants + `@pytest.mark.integration` `ActorSimulator` & Crescendo/GOAT/PAIR red-teaming

---

## Phase Details

### Phase 13: Upstream SDK & Harness Resync

**Goal**: Re-base `strands-code` cleanly onto `strands-agents >=1.65` and `strands-harness >=0.4.0`, closing the Phase 4 cross-family restore blocker and adopting native `ModelInfo` and `InjectedBlock` contracts without breaking existing CLI guarantees
**Depends on**: Milestone `v1.0`
**Requirements**: `UPSTREAM-01`
**Success Criteria** (what must be TRUE):
  1. `uv.lock` resolves `strands-agents >=1.65.0` and `strands-harness >=0.4.0` with all existing unit/contract suites passing (`pytest tests/ -q`, `ruff`, `xenon`, `import-linter`)
  2. Resuming a persisted Opus/reasoning session onto a non-reasoning Bedrock model succeeds via `#5166` / `drop_block` without `ValidationException`, while explicit `/model` switches continue preserving `[Thinking trace]` text
  3. `estimate_messages_tokens` and `canonical_prefix_hash` account for `InjectedBlock` (`{"injected": {"text": ...}}`), `window_for()` consults `model.model_info.limits.context_window` before `MODEL_LIMITS`, Bedrock `_NO_STREAMING_TOOLS` models instantiate with `streaming=False`, and `todos` plugin removal leaves zero prompt surprises

**Plans**: 2 plans

Plans:
**Wave 1**

- [x] `13-01-PLAN.md` — Tracer: lockfile & floor bump (`strands-agents>=1.65.0`, `strands-harness>=0.4.0`) plus `InjectedBlock` accounting (`31ecc3e`)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] `13-02-PLAN.md` — SDK `model_info` windows, Bedrock unary tool mode (`streaming=False`), and hybrid session restore + gates (`8c8b70f`)

### Phase 14: First-Class Google Gemini & Provider-Aware Startup

**Goal**: Make `google/` Gemini models first-class across startup, `/model`, reasoning/effort routing, and `/cost` without requiring AWS credentials or violating `Strands Box` phantom/egress assumptions
**Depends on**: Phase 13
**Requirements**: `MODEL-06`
**Success Criteria** (what must be TRUE):
  1. Launching `strands-code` with `GOOGLE_API_KEY`, `GEMINI_API_KEY`, Vertex ADC, or `OPENROUTER_API_KEY` succeeds with zero AWS credentials configured, checking non-empty key presence only (never vendor key prefixes) and skipping `sts.get_caller_identity()` when `STRANDS_BOX=1`
  2. Switching between `google/gemini-*` and Anthropic/OpenRouter (`LiteLLMModel`) strips `toolUse["reasoningSignature"]` on cross-vendor switches while preserving it in `RichHistory`, `_vendor_family("gemini-2.5-pro")` groups under `("google", "gemini")`, and `supports_reasoning("google/...")` delegates to `_harness_supports_thinking`
  3. `/model` discovers `google/` models when keyed (`gemini` extra), `live_pricing.litellm_entry` resolves `gemini/<tail>`/`<tail>` pricing & context windows, and `docs/QUICKSTART.md` documents the Google AI Studio + Google AI Ultra (\$40–\$100/mo Developer Program credit) setup

**Plans**: 3 plans

Plans:
**Wave 1**

- [x] `14-01-PLAN.md` — Tracer: `gemini` optional extra, Box-compatible provider-aware preflight, Vertex conflict gate, ambient auto-pick & `--model` CLI flag (`947c5a7`)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] `14-02-PLAN.md` — `GeminiModel` `reasoningSignature` stripping, `_vendor_family` fix, Gemini 2.5 thinking guard, credential-gated `/model` discovery & `/cost` tables (`52b0963`)
- [x] `14-03-PLAN.md` — Repeatable `driver.py g1` UAT rig, `docs/QUICKSTART.md` Ultra credit guide, upstream Gemini 2.5 issue draft & full CI gates (`a2395d4`)

### Phase 15: First-Class Native OpenAI & Anthropic APIs

**Goal**: Make native `openai/` (Responses API) and `anthropic/` (Messages API) first-class across packaging, startup, `/model`, caching, `/cost` & context accounting, API mannerisms, and live verification without leaking choices or credentials to other providers
**Depends on**: Phase 14
**Requirements**: `MODEL-07`, `MODEL-08`
**Tracks**: `CsabaConsulting/strands-code#17`, `CsabaConsulting/strands-code#22`
**Success Criteria** (what must be TRUE):
  1. `pyproject.toml` declares `openai = ["strands-agents[openai]", "openai>=2.0.0"]` and `anthropic = ["strands-agents[anthropic]"]` with matching `_SDK_EXTRA_HINTS`; `apply_switch()` and `/route` preserve `caching` and native `web_search` on switches; and `live_pricing.litellm_entry()` resolves bare-tail native OpenAI/Anthropic IDs alongside updated static fallbacks (`GPT-5.4`/`5.6`/`6`/`6.1`, `o3`/`o4-mini`, `Claude 5.5`, `Fable 5.2`)
  2. `/cost` and context `%` accurately account for `cacheReadInputTokens` and `cacheWriteInputTokens` (handling Anthropic's exclusive `input_tokens` vs OpenAI's inclusive `input_tokens`), while credential-gated `GET /v1/models` discovery (caching Anthropic's live `max_input_tokens`, `max_tokens`, `capabilities`, `retires_at`) and `_vendor_family()` cleanly group `openai` and `anthropic` models
  3. Provider mannerisms and switch safety are guarded and verified via repeatable `scripts/uattest/` scenarios and `docs/QUICKSTART.md`: non-reasoning / subset-effort OpenAI guards and Responses-compatible `base_url` handling; Anthropic `anthropic-version: 2026-10-21` / `max_tokens` / PDF-text doc limits / `SummaryBlock` & `temporary_messages` / cross-provider Bedrock↔Direct thinking-signature gating; plus documented API extras (`use_native_token_count`, `prompt_cache_retention`/`options`, `service_tier`)

**Plans**: 3 plans

Plans:
**Wave 1**

- [x] `15-01-PLAN.md` — Tracer: `openai` (`openai>=2.0.0`) & `anthropic` extras, `_SDK_EXTRA_HINTS`, `first_run` helpers + bumped ambient defaults, switch `caching`/`web_search` preservation & harness-preserving `base_url` + opt-in `api_mode: chat` (`27bedc5`)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] `15-02-PLAN.md` — Cache-aware inclusive/exclusive `/cost` & compact cache display, bare-tail `litellm_entry` & 24h Anthropic metadata cache, `same_provider` thinking & `SummaryBlock` safety, `_vendor_family` grouping, `configure_openai_for_model` guard & credential-gated live `/model` discovery (`15d98a4`)

**Wave 3** *(blocked on Wave 1 & Wave 2 completion)*

- [x] `15-03-PLAN.md` — Repeatable `driver.py o1` / `an1` UAT rigs + offline rig contracts, `docs/QUICKSTART.md` OpenAI/Anthropic guides, held upstream OpenAI reasoning-guard draft & all 6 CI gates (`eeceb59`, rig updates `b102735`, `3b8ab4f`)

### Phase 16: First-Class Meta Model API (`api.meta.ai` / Muse) & Upstream Enablement

**Goal**: Deliver first-class support for Meta's Model API (`https://api.meta.ai/v1` — Muse Wonder, Muse Spark, contributor tiers, and Muse Ember) while driving upstream `meta/` provider & Muse `model_info.json` enablement in `strands-agents/harness-sdk`
**Depends on**: Phase 15
**Requirements**: `MODEL-09`
**Tracks**: `CsabaConsulting/strands-code#21`, `strands-agents/harness-sdk#6521`, `docs/upstream/harness_issue_meta_model_api.md`
**Success Criteria** (what must be TRUE):
  1. An empirical live probe validates `https://api.meta.ai/v1` (`/v1/responses` vs `/v1/messages`, `prompt_cache_key`/`prompt_cache_options` tolerance, encrypted reasoning replay, `GET /v1/models`), and a held follow-up empirical probe comment (`docs/upstream/harness_comment_6521_meta_probe.md`) is drafted for human review before posting to `strands-agents/harness-sdk#6521`
  2. `strands-code` ships a thin, retireable `meta/` adapter backed by `OpenAIResponsesModel` (`https://api.meta.ai/v1`), `meta` extra + `_SDK_EXTRA_HINTS["meta"]`, Box-compatible `MODEL_API_KEY`/`META_API_KEY`/`META_BASE_URL` zero-AWS preflight (`meta/muse-spark-1.3-contributor` ambient default ordered `Google -> Anthropic -> OpenAI -> Meta -> OpenRouter -> Bedrock`), credential-gated `GET /v1/models` discovery with `("meta", "muse")` grouping, and scoped `_MEDIA_LESS` rules so multimodal Muse retains media support while Bedrock Llama remains protected
  3. Cache-aware `/cost` resolves `meta/muse-*` cached/uncached rates (LiteLLM bundled + static fallbacks including `muse-ember-1.0` & `-contributor` 50× cached discount) and 1M context windows, backed by a repeatable `scripts/uattest/` (`driver.py m1`) live UAT scenario and `docs/QUICKSTART.md` guide
  4. `pyproject.toml` and `uv.lock` resync onto `strands-agents>=1.66.0` and `strands-harness>=0.5.0` (no upper pins), retiring `_gpt_62_model_info_fallback()` cleanly, bumping OpenAI ambient default to `openai/gpt-6.2-sol`, and adapting any upstream `1.66.0`/`0.5.0` behavior changes with all CI gates green

**Plans**: 3 plans

Plans:
**Wave 1**

- [x] `16-01-PLAN.md` — Tracer: Upstream `1.66.0`/`0.5.0` resync (`_gpt_62_model_info_fallback` retired, `openai/gpt-6.2-sol` default), `meta` extra + `MODEL_API_KEY`/`META_API_KEY`/`META_BASE_URL` helpers, and thin auto-retiring `meta/` adapter on `OpenAIResponsesModel` (`cc99d5a`)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] `16-02-PLAN.md` — `_MEDIA_LESS` Bedrock Llama scoping for multimodal Muse, filtered Meta `GET /v1/models` discovery + `("meta", "muse")` grouping, LiteLLM/static `/cost` + 50× contributor caching & `LLM_...`/`LLM|...` key scrubbing (`4857960`)

**Wave 3** *(blocked on Wave 1 & Wave 2 completion)*

- [x] `16-03-PLAN.md` — Repeatable `driver.py m1` live UAT rig (`OPENAI_PRIMARY` → `gpt-6.2-sol`) + live `m1` run, `docs/QUICKSTART.md` guide, held `#6521` empirical probe comment draft & all 6 CI gates (`44b9aa4`)

### Phase 17: Decision Routing Convergence (`DecisionModel`)

**Goal**: Converge custom Decision-API HTTP engine boilerplate onto `strands.decisions.DecisionModel` while preserving `strands-code`'s calibrated routing decisions, pre-turn `apply_model_action`, and `/cost` accounting
**Depends on**: Phase 13 (benefits from Phases 14–16 multi-provider router candidates)
**Requirements**: `UPSTREAM-02`
**Success Criteria** (what must be TRUE):
  1. `strands_code_cli/routing/` executes TypeSafe (`TypeSafeDecisionModel`), OpenRouter (`OpenRouterDecisionModel` with 64 KiB body fit & inline `usage.cost`), Ollama (`OllamaDecisionModel` with preflight & `keep_alive`), and optional `LLMDecisionModel` through unified `DecisionModel` interfaces bridged safely into synchronous pre-turn & `/btw` routing
  2. All `DecisionModel` checks guard `isinstance(val, Uncertain)` explicitly, run with `uncertainty=False` over `result.metadata.probabilities`, and reproduce `v1.0`'s `0.62` confidence threshold and `0.04` tie-margin gate without `candidates[0]` fallback regressions
  3. Pre-turn `apply_model_action` keeps `convert_history()`, `RichHistory` stashes, hold-on-failure (`D-08`), two-call model + effort routing, `/route`, and `/cost` decision spend totals intact

**Plans**: 3 plans

Plans:
**Wave 1**

- [x] `17-01-PLAN.md` — Tracer: `routing/transports.py` `DecisionModel` convergence (`OpenRouterDecisionModel`, `OllamaDecisionModel`, `TypeSafeDecisionModel`, `run_decision_sync`) + `routing/core.py` wiring + `conftest.py` key scrubbing + `httpx.MockTransport` migration (`f6d8651`)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] `17-02-PLAN.md` — Opt-in `"decisions_api"` (`DecisionsAPIDecisionModel`, `JEV_API_KEY`) & `"llm"` (`LLMDecisionModel`, `uncertainty=True` hold) engines + `resolve_harness_model` `web_search`/`caching` switches + `/cost` estimated lane & end-to-end loop/`/btw` tests (`a8e9993`)

**Wave 3** *(blocked on Wave 1 & Wave 2 completion)*

- [x] `17-03-PLAN.md` — `@pytest.mark.integration` live probes (`decisions_api`, `llm`), `docs/ROUTING.md` + `docs/QUICKSTART.md` (`TYPESAFE_API_KEY` vs `JEV_API_KEY`), and all 6 CI gates (`b474041`)

### Phase 18: Skills Marketplaces & Lockfile Installer

**Goal**: Let users subscribe to remote skill catalogs or GitHub skill repos and install, verify, update, sync, and invoke third-party skills under `strands-code`'s deny-first posture
**Depends on**: Phase 13
**Requirements**: `SKILL-03`
**Success Criteria** (what must be TRUE):
  1. Users can manage catalogs (`~/.config/strands-code/marketplaces.yaml`), browse skills across `.agent-plugin/marketplace.json`, `.claude-plugin/marketplace.json`, and `owner/repo[@ref]` repos, and run `/skills install|update|sync|remove` synced atomically with `AgentSkills.set_available_skills`
  2. Remote skills install into `./.agent/skills-marketplaces/<marketplace>/<skill>/` (keeping `skill_dir.name == skill.name` and `./.agent/skills/` pure for `local:`), pinned in `./.agent/skills-lock.json` by 40-char `commit_sha` + SHA-256 `computed_hash`, with dynamic `/<marketplace>:` tab completion in `SlashCompleter`
  3. Installer and policy layer reject symlinks/submodules/zip-slip, enforce unpacked size/file caps, keep `allowed-tools` informational-only, warn on bundled `scripts/*`, block broad repo `[[allow]]` globs from mutating `.agent/skills*`, render metadata via `print_plain`, and frame third-party provenance explicitly

**Plans**: 3 plans

Plans:
**Wave 1**

- [x] `18-01-PLAN.md` — Tracer: `memory/marketplace.py` catalog registry, pure-HTTPS GitHub/tarball fetcher (`MockTransport`), deny-first unpack, SHA-256 `./.agent/skills-lock.json` verifier, `conftest.py` token scrub & Wave 0 security suite (`e8db593`)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] `18-02-PLAN.md` — Multi-namespace `SkillIndex` + hash-drift exclusion, dynamic `/<ns>:` `SlashCompleter`, protected-path `Prompt` policy downgrade (`policy/core.py`), `/skills marketplace|browse|install|update|sync|remove` dispatch, provenance framing & `AgentSkills` startup/reload sync (`f160706`)

**Wave 3** *(blocked on Wave 1 & Wave 2 completion)*

- [x] `18-03-PLAN.md` — `@pytest.mark.integration` live GitHub marketplace probe, `docs/QUICKSTART.md` guide, `tests/rig/` & all 6 CI gates (`d0562be`)

### Phase 19: Strands Box Linux Sandbox Floor & Dogwood Policy

**Goal**: Deliver an OS-enforced defense-in-depth containment floor using Strands Box (`strands-agents/box`) on Linux with deterministic Dogwood policies and out-of-band credential injection underneath HITL dialogs
**Depends on**: Phases 14, 15, 16 (uses provider-aware + `STRANDS_BOX=1` preflight)
**Requirements**: `SANDBOX-01`
**Success Criteria** (what must be TRUE):
  1. `strands-code` generates vetted repo-scoped `box.toml` and Dogwood `policy.dw` configurations (`uv` Python symlink realpaths resolved, `TERM`/`HOME`/`PATH`/`STRANDS_BOX=1` set, configs mounted outside `[agent.filesystem].write`) with working egress profiles for Bedrock SigV4 (no STS hole), Google (`x-goog-api-key`), Anthropic (`x-api-key`), OpenAI (`Authorization: Bearer` `api.openai.com`), Meta (`Authorization: Bearer` `api.meta.ai`), OpenRouter (path-scoped `/api/v1/chat/*` + `/api/alpha/decisions`), and TypeSafe
  2. `policy.dw` enforces default-deny egress, `.env` read protection, and at least one canonical MFOTL temporal rule (with a logged, scoped revisit of `D-05` for host-side deterministic Dogwood), and `codeact_shell` routes via `["sh", "-c", shlex.join(argv)]` under `STRANDS_BOX=1` so CodeAct commands feed Dogwood's temporal log
  3. Documentation and diagnostics cover the 3-binary Linux layout, `EXPERIMENTAL_X86_SUPPORT=TRUE` on Linux `x86_64`, and Ubuntu 24.04+ `/etc/apparmor.d/strands-box` `userns` profile

**Plans**: 3 plans

Plans:
**Wave 1**

- [x] `19-01-PLAN.md` — Tracer: `sandbox/box.py` `box.toml`/`policy.dw` generator (host-only storage, `uv` realpaths, 7+2 egress profiles, canonical MFOTL temporal rule), Linux 3-binary/`x86_64`/AppArmor diagnostics, `conftest.py` env scrubs & Wave 0 security suite (`tests/sandbox/test_box.py`)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] `19-02-PLAN.md` — `STRANDS_BOX=1` `codeact_shell` `sh -c` alignment, `~/.config/strands-box` protected-path `Prompt` downgrade (`policy/core.py`), `/policy` read-only Box indicator (`dispatch/core.py`), and `strands-code box init|doctor|run` Typer subcommand group (`entry/main.py`)

**Wave 3** *(blocked on Wave 1 & Wave 2 completion)*

- [x] `19-03-PLAN.md` — `@pytest.mark.integration` host `box`/`dogwood` validation probe, `docs/QUICKSTART.md` Linux & AppArmor guide, `tests/rig/` & all 6 CI gates

### Phase 20: Monty Python VM for `python_repl` & CodeAct

**Goal**: Replace in-process `smolagents` AST execution in `strands_code_cli`'s `python_repl` and `CodeactStint` with a crash-isolated, memory-bounded Rust Python VM (`pydantic-monty`), eliminating in-process CLI tampering risk even when running unboxed while aligning cleanly with Strands Box
**Depends on**: Phase 19
**Requirements**: `SANDBOX-02`
**Success Criteria** (what must be TRUE):
  1. `strands_code_cli/sandbox/monty.py` provides a stateful `MontyPythonInterpreter` (`PythonInterpreter` interface via `pydantic-monty` `Monty` pool + `feed_run`) supporting `read`/`write`/`edit`/`shell` `external_lookup` host callbacks, `import math`, `print()` capture + error stdout salvage, memory/CPU/timeout caps, and clean `MontyCrashedError` pool recovery without crashing the CLI
  2. `entry/main.py` (`python_repl`) and `policy/codeact.py` (`CodeactStint`) run on the Monty backend (with documented packaging/optional-extra fallback posture and deterministic worker subprocess teardown on reset/exit) while passing existing CodeAct/scope/HITL/diff contracts and leaving `strands_code_agent/` untouched (`D-24`)
  3. `sandbox/box.py` grants `[agent.filesystem].exec` / containment compatibility for `pydantic-monty-runtime` (and documents/evaluates Strands Box embedded Monty Dogwood event-log alignment) with full offline unit/adversarial tests and all 6 CI gates green

**Plans**: TBD

### Phase 21: CLI Ergonomics (`/help`, `@file` / `/file`, `/review`)

**Goal**: Ship everyday interactive productivity ergonomics (`/help`, `@file` / `/file` picker, read-only `/review`) in cleanly factored modules within CI cyclomatic complexity bounds
**Depends on**: Phases 14, 15, 16 (for `supports_media` & `"document"` model switching alignment across providers)
**Requirements**: `LOOP-06`, `TOOL-05`, `REVIEW-01`
**Success Criteria** (what must be TRUE):
  1. `/help` and `/help <cmd>` (`dispatch/help.py`) render grouped built-in commands + live loaded skills and shadow warnings via `print_plain`, sharing a single command table with `USAGE_HINT`, while `run_loop` and `_setup_decision_entries` remain within `xenon --max-absolute C` (`CC <= 20`)
  2. `@file` and `/file` (`ui/attachments.py`) provide gitignore-filtered fuzzy selection confined to `effective_roots`, leave non-file `@tokens` (`@dataclass`, `@pytest.mark`) untouched, attach `ImageContent`/`DocumentContent` when `supports_media(current_model)` holds after `/route`, construct `list[ContentBlock]` strictly from allowlisted `text`/`image`/`document` shapes (never caller-supplied `"toolUse"` blocks; CVE-2026-18830 / CoreBreak boundary), and `model_switch.py` converts `"document"` blocks safely across model switches
  3. `/review` (`dispatch/review.py`) pre-collects uncommitted, `--staged`, or validated `<base-ref>` git diffs in Python inside an untrusted-diff frame and runs under a turn-scoped read-only Plan gate with `turn_interface = "tool"` without mutating sticky `ModeState`

**Plans**: TBD

### Phase 22: Strands Evals & Red-Team Suite

**Goal**: Establish continuous agent behavioral evaluation and adversarial prompt-injection red-teaming on `strands-agents-evals` covering Plan/Act, CodeAct, `/review`, `/route`, and skills/memory defenses
**Depends on**: Phases 17, 18, 19, 20, 21
**Requirements**: `EVAL-01`
**Success Criteria** (what must be TRUE):
  1. `strands-agents-evals >=1.10` lives strictly in `[dependency-groups] dev` with eval suites organized under `scripts/evals/` and `tests/evals/`, passing `pytest tests/ -q`, `ruff`, `xenon --max-absolute C`, and `import-linter` with zero AWS credentials
  2. Offline deterministic & mocked-judge `Experiment` tests (using `StrandsInMemorySessionMapper`) verify Plan-mode read-only enforcement, `/review` `turn_interface = "tool"` invariants, `/route` hold behavior, and prompt-injection canaries against poisoned `SKILL.md` / `STRANDS.md` / `.agent/MEMORY.md` fixtures in default CI
  3. `@pytest.mark.integration` live suites and a CLI driver execute `TrajectoryEvaluator`, `ToolParameterAccuracyEvaluator`, `ActorSimulator`, and `RedTeamExperiment` (`CrescendoStrategy`, `GoatStrategy`, `PairStrategy`) with configurable `--model` judges (`bedrock/`, `google/`, `openai/`, `anthropic/`, `meta/`, `litellm/`)

**Plans**: TBD

---

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1–12 | `v1.0` | 41/41 | Complete | 2026-10-16 |
| 13. Upstream SDK & Harness Resync | `v2.0` | 2/2 | Complete | 2026-11-21 |
| 14. First-Class Google Gemini & Provider-Aware Startup | `v2.0` | 3/3 | Complete | 2026-11-22 |
| 15. First-Class Native OpenAI & Anthropic APIs | `v2.0` | 3/3 | Complete | 2026-11-24 |
| 16. First-Class Meta Model API (`api.meta.ai` / Muse) & Upstream Enablement | `v2.0` | 3/3 | Complete | 2026-11-24 |
| 17. Decision Routing Convergence (`DecisionModel`) | `v2.0` | 3/3 | Complete | 2026-11-24 |
| 18. Skills Marketplaces & Lockfile Installer | `v2.0` | 3/3 | Complete | 2026-11-24 |
| 19. Strands Box Linux Sandbox Floor & Dogwood Policy | `v2.0` | 3/3 | Complete | 2026-11-25 |
| 20. Monty Python VM for `python_repl` & CodeAct | `v2.0` | 0/0 | Not started | - |
| 21. CLI Ergonomics (`/help`, `@file` / `/file`, `/review`) | `v2.0` | 0/0 | Not started | - |
| 22. Strands Evals & Red-Team Suite | `v2.0` | 0/0 | Not started | - |
