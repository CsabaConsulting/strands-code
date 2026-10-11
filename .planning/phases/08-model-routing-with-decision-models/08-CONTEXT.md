# Phase 8: Model Routing with Decision Models - Context

**Gathered:** 2026-10-11
**Status:** Ready for planning

## Phase Boundary

Per ask, the CLI routes to the right model and thinking budget via a cheap decision model, with manual override kept. In scope: user-configured routing strategy (candidate model set + scenario directives, global and workspace), OpenRouter decision-model API as the default engine with local-model alternative, models-only fallback chain (pause/hold, never heuristic picks), main + `/btw` side coverage, silent switches with always-on transcript notes, session toggle + `/model` override with routing-off warning, guided strategy setup with validation. Out of scope: CodeAct (Phase 9), cost budgets/enforcement (locked: display only), heuristic model-picking (rejected — a short ask can mean deep work), fully automatic routing with no override (locked out).

## Implementation Decisions

### Routing scope and strategy config
- **D-01:** Routing is auto-on only when a strategy is configured (candidate model set + directives). Without config there is not enough information to route, so routing stays off. — **Reversibility:** costly — the default posture shapes the turn loop and config surface; flipping it later changes every-turn behavior and the setup contract.
- **D-02:** Strategy shape is candidate models plus freeform scenario directives (e.g. "trivial asks go cheap, deep refactors go big"). Candidate entries may carry model descriptors — relative size/role notes (Sol=mega / Terra=mid / Luna=small; Opus/Sonnet/Haiku tiers) — potentially with pulled compound benchmarks to help ranking.
- **D-03:** Strategy lives both globally and per workspace; repo wins on conflict (Phase 3 D-08 policy precedence).
- **D-04:** Main turns and `/btw` side questions both route through the same strategy; side asks are flagged as side so directives can discriminate (closes the Phase 7 D-07 revisit).
- **D-05:** Thinking-level routing within thinking-capable models is in scope: the router picks a thinking level automatically, not just the model.

### Decision engine and fallback
- **D-06:** OpenRouter's decision-model API is the default decision engine until Bedrock offers decision models; local models are supported as the alternative. Setup enumerates OpenRouter's open-model selection for user choice (Laya/Kev are candidates within it, not the whole menu).
- **D-07:** Directives plus candidate stats feed every decision call, API or local. Directives shape all decisions; they never sit idle while the model decides without them.
- **D-08:** Fallback chain is models-only: decision API → local model → pause and hold the current model, retrying next ask. No heuristic ever picks a model. Roadmap SC2's "deterministic heuristic fallback" is satisfied by deterministic hold-current (a fixed rule, not a heuristic pick) — planner/researcher note this reinterpretation.
- **D-09:** Fully offline behavior is local decision model if configured, otherwise routing pauses and the current model is used (AWS-optional posture holds: no network, no API, no guessing).

### Override and visibility
- **D-10:** Routing has a session-sticky toggle (Phase 4/6 precedent). `/model` re-points immediately but warns the switch turns routing off and offers cancel to keep routing; a slash command turns routing back on. More routing slash commands are expected (planner scopes them).
- **D-11:** Routed switches are silent plus a transcript note; model choice never raises an approval prompt. Deny-first stays for tool side effects, not for routing.
- **D-12:** Every routed ask gets one transcript line (model, why, cost impact), suppressible via config to cut noise; `/cost` carries the fuller routing detail.

### Strategy setup
- **D-13:** Guided setup flow creates the strategy (enumerate OpenRouter models, capture directives). Example strategies ship in the docs, manual file edits are allowed, and a slash command validates the configuration's validity.

### the agent's Discretion
- Routing slash command names and subcommand shapes (toggle on/off, setup, validate, status).
- Strategy file format, filenames, and exact global/workspace paths.
- Transcript line format and the /cost routing section shape.
- Hold-current retry/notify behavior (silent hold vs transcript note on failure).
- Descriptor/benchmark schema for candidate entries (researcher confirms sources first).
- Side-ask decision-call mechanics (per-ask call vs derived) within D-04.

## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project definition
- `.planning/PROJECT.md` — product vision, core value, constraints (manual override always wins; AWS-optional; no keys in repo)
- `.planning/REQUIREMENTS.md` — MODEL-03 (this phase)
- `.planning/ROADMAP.md` — Phase 8 goal, success criteria (note: SC2 "deterministic heuristic fallback" is reinterpreted by D-08 as deterministic hold-current), depends on Phase 7 sequencing + Phase 5 almanac

### Prior phases (locked)
- `.planning/phases/05-model-cost-context-commands/05-CONTEXT.md` — D-01 one model per turn, idle-only switches (routing decides pre-turn, never mid-turn); D-02 per-id capability sets; D-06 provider-aware discovery + verbatim ARNs; transcript-first UX; /cost breakdown shape
- `.planning/phases/07-subagents-btw-side-channel/07-CONTEXT.md` — D-07 same-model rule revisited here (D-04 routes side asks); shared tagged gate; fenced side blocks
- `.planning/phases/04-plan-act-modes-steering/04-CONTEXT.md` — D-07 session-sticky modes (precedent for D-10 toggle); reply-only router actions
- `.planning/phases/03-permissions-gate/03-CONTEXT.md` — D-08 repo-overrides-home (precedent for D-03); deny-first approvals (D-11 keeps routing out of the gate); single-HITL spine
- `.planning/phases/06-skills-memory-file/06-CONTEXT.md` — D-07 session-sticky toggle precedent; explicit invocation patterns

### Codebase orientation
- `strands_code_cli/live_pricing.py` — live price/window layers over the static almanac (Bedrock Price List → OpenRouter → LiteLLM → static); fail-soft layering is the precedent for engine fallback
- `strands_code_cli/model_switch.py` — Bedrock discovery, verbatim IDs, history conversion on switch; routing re-points through this machinery
- `strands_code_cli/model_capabilities.py` — aider-style user capability overrides (precedent for user-correctable model metadata: D-02 descriptors)
- `strands_code_cli/provider_config.py` — persisted provider/model choice shape (`~/.config/strands-code/`); strategy config follows platformdirs-home + repo-file conventions
- `strands_code_cli/cost_context.py` — /cost breakdown + session totals; routing detail + decision-call spend attach here
- `strands_code_cli/router.py` — `dispatch` tri-state; new routing slashes route here as reply actions
- `strands_code_cli/loop.py` — turn machinery; the routing decision point sits pre-turn at idle (D-01)
- `strands_code_cli/main.py` — `build_agent` model wiring; routed switches re-point here
- `.planning/codebase/ARCHITECTURE.md` — agent/composition vs execution layers (note: maps predate `strands_code_cli/`; CLI orientation above supersedes)

## Existing Code Insights

### Reusable Assets
- Almanac stack (`live_pricing.py` + static tables + `model_capabilities.py` overrides): candidate stats source — prices, windows, override-correctable verdicts
- Bedrock discovery (`model_switch.py discover_models`): provider-aware candidate enumeration; OpenRouter enumeration for setup mirrors it
- `ProviderConfig` fail-soft YAML shape: template for the strategy file (warn-and-skip on malformed entries, never break startup)
- `/cost` breakdown (`cost_context.py`): per-session/per-task cost surface for routing detail
- Choice dialog (`choice.py`): owned-keys radio control for guided setup selection UX
- `print_plain` (`output.py`): transcript note rendering, markup-off

### Established Patterns
- Constructor-kwarg configuration, never env sniffing
- Reply-only router actions; prompts live in the gate/turn layer
- Fail-soft layering (live_pricing precedent): each source degrades to the next, nothing raises to callers
- Transcript-first UX: silent actions still log visibly (D-11/D-12 continue this)
- Session-sticky in-memory state by default; disk only via DiffConfig-shape config when explicitly decided
- Pair-atomic history ops on switch (Phase 5); verbatim ARN preservation

### Integration Points
- `loop.py` pre-turn at idle: routing decision point — decision call, hold/pause, transcript note all attach before `agent(text)`
- `router.py dispatch`: new routing slash branches (toggle, setup, validate) + USAGE_HINT
- `main.py build_agent`: routed model + thinking-level application via rebuild/re-point
- `model_switch.py`: conversion machinery reused when routed switches change model families
- `cost_context.py`: routing visibility + decision-call spend accounting

## Specific Ideas

- OpenRouter decision-model API until Bedrock offers decision models; enumerate OpenRouter's open-model selection (beyond just Kev/Laya) for user choice.
- Model descriptors on candidates: relative size/role notes where sizes are unknown (Sol-Terra-Luna trinity: mega/mid/small; Opus-Sonnet-Haiku tiers) — researcher confirms what metadata is actually available.
- Researcher explores pulling compound and detailed benchmarks to rank candidate models; rankings feed routing decisions.
- Guiding skepticism (locked): even a short ask can mean deep thinking work — this is why no heuristic picks models (D-08).

## Deferred Ideas

- CodeAct action interface (Phase 9).
- Cost budgets/enforcement (locked: display only).
- Heuristic model-picking — rejected, not deferred: directives + models only.
- Fully automatic routing with no override — locked out; manual switching + toggle always win.

---

*Phase: 8-Model Routing with Decision Models*
*Context gathered: 2026-10-11*
