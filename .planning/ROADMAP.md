# Roadmaps & Milestones

## Milestones

- ✅ **v1.0 Conversational Coding CLI** — Phases 1–12 (shipped 2026-10-16) — [Archive](milestones/v1.0-ROADMAP.md)
- 🚧 **v2.0 Ecosystem Alignment, Marketplaces, Sandbox & Evals** — Phases 13–19 (in progress)

---

## Overview (`v2.0`)

`v2.0` brings `strands-code` into alignment with the evolved Strands ecosystem (`strands-py >=1.65`, `harness-py >=0.4.0`, `strands-agents/box` Linux, `strands-agents-evals >=1.10`), adds first-class Google AI Gemini support (compatible with personal Google AI Ultra Developer Program credits) and provider-aware startup, introduces deny-first remote skills marketplaces with SHA/hash lockfiles, layers Strands Box OS containment beneath HITL approvals, delivers `/help` + `@file` + `/review`, and closes with an automated `strands-evals` regression & red-team suite.

## Phases

- [x] **Phase 13: Upstream SDK & Harness Resync** — Lock `strands-agents >=1.65` & `strands-harness >=0.4`, retire `#5166`/`#5158` workarounds, adapt `InjectedBlock` & `Model.model_info`, enable non-streaming Bedrock Llama tools (completed 2026-11-21)
- [x] **Phase 14: First-Class Google Gemini & Provider-Aware Startup** — `gemini` extra, Box-compatible provider-aware preflight, cross-provider `reasoningSignature` & `_vendor_family` fixes, `/model` Gemini discovery, `/cost` tables, AI Studio Ultra credit docs (completed 2026-11-22)
- [ ] **Phase 15: Decision Routing Convergence (`DecisionModel`)** — Migrate `routing/` engine transports onto `strands.decisions.DecisionModel` while preserving `apply_model_action`, `0.62`/`0.04` gate, two-call effort flow & `/cost` actuals
- [ ] **Phase 16: Skills Marketplaces & Lockfile Installer** — `/skills marketplace|browse|install|update|sync|remove`, `./.agent/skills-marketplaces/` + `./.agent/skills-lock.json`, dynamic `<ns>:` completion & deny-first supply-chain guards
- [ ] **Phase 17: Strands Box Linux Sandbox Floor & Dogwood Policy** — `box.toml` + `policy.dw` generator, 5-provider egress profiles, temporal Dogwood rule + scoped `D-05` revisit, `STRANDS_BOX=1` `codeact_shell` alignment & Ubuntu 24.04 AppArmor docs
- [ ] **Phase 18: CLI Ergonomics (`/help`, `@file` / `/file`, `/review`)** — Isolated UX modules respecting `xenon C <= 20`, `"document"` history conversion & Python-collected read-only `/review`
- [ ] **Phase 19: Strands Evals & Red-Team Suite** — `strands-agents-evals >=1.10` in `scripts/evals/` + `tests/evals/`, offline CI trajectory/canary invariants + `@pytest.mark.integration` `ActorSimulator` & Crescendo/GOAT/PAIR red-teaming

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

### Phase 15: Decision Routing Convergence (`DecisionModel`)

**Goal**: Converge custom Decision-API HTTP engine boilerplate onto `strands.decisions.DecisionModel` while preserving `strands-code`'s calibrated routing decisions, pre-turn `apply_model_action`, and `/cost` accounting
**Depends on**: Phase 13 (benefits from Phase 14 Gemini router candidates)
**Requirements**: `UPSTREAM-02`
**Success Criteria** (what must be TRUE):
  1. `strands_code_cli/routing/` executes TypeSafe (`TypeSafeDecisionModel`), OpenRouter (`OpenRouterDecisionModel` with 64 KiB body fit & inline `usage.cost`), Ollama (`OllamaDecisionModel` with preflight & `keep_alive`), and optional `LLMDecisionModel` through unified `DecisionModel` interfaces bridged safely into synchronous pre-turn & `/btw` routing
  2. All `DecisionModel` checks guard `isinstance(val, Uncertain)` explicitly, run with `uncertainty=False` over `result.metadata.probabilities`, and reproduce `v1.0`'s `0.62` confidence threshold and `0.04` tie-margin gate without `candidates[0]` fallback regressions
  3. Pre-turn `apply_model_action` keeps `convert_history()`, `RichHistory` stashes, hold-on-failure (`D-08`), two-call model + effort routing, `/route`, and `/cost` decision spend totals intact

**Plans**: TBD

### Phase 16: Skills Marketplaces & Lockfile Installer

**Goal**: Let users subscribe to remote skill catalogs or GitHub skill repos and install, verify, update, sync, and invoke third-party skills under `strands-code`'s deny-first posture
**Depends on**: Phase 13
**Requirements**: `SKILL-03`
**Success Criteria** (what must be TRUE):
  1. Users can manage catalogs (`~/.config/strands-code/marketplaces.yaml`), browse skills across `.agent-plugin/marketplace.json`, `.claude-plugin/marketplace.json`, and `owner/repo[@ref]` repos, and run `/skills install|update|sync|remove` synced atomically with `AgentSkills.set_available_skills`
  2. Remote skills install into `./.agent/skills-marketplaces/<marketplace>/<skill>/` (keeping `skill_dir.name == skill.name` and `./.agent/skills/` pure for `local:`), pinned in `./.agent/skills-lock.json` by 40-char `commit_sha` + SHA-256 `computed_hash`, with dynamic `/<marketplace>:` tab completion in `SlashCompleter`
  3. Installer and policy layer reject symlinks/submodules/zip-slip, enforce unpacked size/file caps, keep `allowed-tools` informational-only, warn on bundled `scripts/*`, block broad repo `[[allow]]` globs from mutating `.agent/skills*`, render metadata via `print_plain`, and frame third-party provenance explicitly

**Plans**: TBD

### Phase 17: Strands Box Linux Sandbox Floor & Dogwood Policy

**Goal**: Deliver an OS-enforced defense-in-depth containment floor using Strands Box (`strands-agents/box`) on Linux with deterministic Dogwood policies and out-of-band credential injection underneath HITL dialogs
**Depends on**: Phase 14 (uses provider-aware + `STRANDS_BOX=1` preflight)
**Requirements**: `SANDBOX-01`
**Success Criteria** (what must be TRUE):
  1. `strands-code` generates vetted repo-scoped `box.toml` and Dogwood `policy.dw` configurations (`uv` Python symlink realpaths resolved, `TERM`/`HOME`/`PATH`/`STRANDS_BOX=1` set, configs mounted outside `[agent.filesystem].write`) with working egress profiles for Bedrock SigV4 (no STS hole), Google (`x-goog-api-key`), Anthropic (`x-api-key`), OpenRouter (path-scoped `/api/v1/chat/*` + `/api/alpha/decisions`), and TypeSafe
  2. `policy.dw` enforces default-deny egress, `.env` read protection, and at least one canonical MFOTL temporal rule (with a logged, scoped revisit of `D-05` for host-side deterministic Dogwood), and `codeact_shell` routes via `["sh", "-c", shlex.join(argv)]` under `STRANDS_BOX=1` so CodeAct commands feed Dogwood's temporal log
  3. Documentation and diagnostics cover the 3-binary Linux layout, `EXPERIMENTAL_X86_SUPPORT=TRUE` on Linux `x86_64`, and Ubuntu 24.04+ `/etc/apparmor.d/strands-box` `userns` profile

**Plans**: TBD

### Phase 18: CLI Ergonomics (`/help`, `@file` / `/file`, `/review`)

**Goal**: Ship everyday interactive productivity ergonomics (`/help`, `@file` / `/file` picker, read-only `/review`) in cleanly factored modules within CI cyclomatic complexity bounds
**Depends on**: Phase 14 (for `supports_media` & `"document"` model switching alignment)
**Requirements**: `LOOP-06`, `TOOL-05`, `REVIEW-01`
**Success Criteria** (what must be TRUE):
  1. `/help` and `/help <cmd>` (`dispatch/help.py`) render grouped built-in commands + live loaded skills and shadow warnings via `print_plain`, sharing a single command table with `USAGE_HINT`, while `run_loop` and `_setup_decision_entries` remain within `xenon --max-absolute C` (`CC <= 20`)
  2. `@file` and `/file` (`ui/attachments.py`) provide gitignore-filtered fuzzy selection confined to `effective_roots`, leave non-file `@tokens` (`@dataclass`, `@pytest.mark`) untouched, attach `ImageContent`/`DocumentContent` when `supports_media(current_model)` holds after `/route`, construct `list[ContentBlock]` strictly from allowlisted `text`/`image`/`document` shapes (never caller-supplied `"toolUse"` blocks; CVE-2026-18830 / CoreBreak boundary), and `model_switch.py` converts `"document"` blocks safely across model switches
  3. `/review` (`dispatch/review.py`) pre-collects uncommitted, `--staged`, or validated `<base-ref>` git diffs in Python inside an untrusted-diff frame and runs under a turn-scoped read-only Plan gate with `turn_interface = "tool"` without mutating sticky `ModeState`

**Plans**: TBD

### Phase 19: Strands Evals & Red-Team Suite

**Goal**: Establish continuous agent behavioral evaluation and adversarial prompt-injection red-teaming on `strands-agents-evals` covering Plan/Act, CodeAct, `/review`, `/route`, and skills/memory defenses
**Depends on**: Phases 15, 16, 18
**Requirements**: `EVAL-01`
**Success Criteria** (what must be TRUE):
  1. `strands-agents-evals >=1.10` lives strictly in `[dependency-groups] dev` with eval suites organized under `scripts/evals/` and `tests/evals/`, passing `pytest tests/ -q`, `ruff`, `xenon --max-absolute C`, and `import-linter` with zero AWS credentials
  2. Offline deterministic & mocked-judge `Experiment` tests (using `StrandsInMemorySessionMapper`) verify Plan-mode read-only enforcement, `/review` `turn_interface = "tool"` invariants, `/route` hold behavior, and prompt-injection canaries against poisoned `SKILL.md` / `STRANDS.md` / `.agent/MEMORY.md` fixtures in default CI
  3. `@pytest.mark.integration` live suites and a CLI driver execute `TrajectoryEvaluator`, `ToolParameterAccuracyEvaluator`, `ActorSimulator`, and `RedTeamExperiment` (`CrescendoStrategy`, `GoatStrategy`, `PairStrategy`) with configurable `--model` judges (`bedrock/`, `google/`, `litellm/`)

**Plans**: TBD

---

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1–12 | `v1.0` | 41/41 | Complete | 2026-10-16 |
| 13. Upstream SDK & Harness Resync | `v2.0` | 2/2 | Complete | 2026-11-21 |
| 14. First-Class Google Gemini & Provider-Aware Startup | `v2.0` | 3/3 | Complete | 2026-11-22 |
| 15. Decision Routing Convergence (`DecisionModel`) | `v2.0` | 0/0 | Not started | - |
| 16. Skills Marketplaces & Lockfile Installer | `v2.0` | 0/0 | Not started | - |
| 17. Strands Box Linux Sandbox Floor & Dogwood Policy | `v2.0` | 0/0 | Not started | - |
| 18. CLI Ergonomics (`/help`, `@file` / `/file`, `/review`) | `v2.0` | 0/0 | Not started | - |
| 19. Strands Evals & Red-Team Suite | `v2.0` | 0/0 | Not started | - |
