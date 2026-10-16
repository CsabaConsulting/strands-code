---
gsd_state_version: "1.0"
milestone: v1
current_phase: 12
current_phase_name: Structural Review + Hygiene
status: discussing
stopped_at: Hindsight Removal retired as no-op (scrub committed); Structural Review renumbered 13 -> 12
last_updated: "2026-10-16T04:45:00Z"
last_activity: 2026-10-16
last_activity_desc: Phase renumber (13 -> 12); hindsight shell archived
progress:
  total_phases: 12
  completed_phases: 11
  total_plans: 38
  completed_plans: 38
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-10-12)

**Core value:** A single ask — spec it, build it, test it, open the PR — completes end to end without the user leaving the conversation.
**Current focus:** Phase 12 — structural-review-hygiene

## Current Position

Phase: 12 (Structural Review + Hygiene) — DISCUSSING
Plan: 0 of TBD
Status: Hindsight shell retired as no-op — ready to discuss Phase 12 scope
Last activity: 2026-10-16 — Phase renumber (Structural Review 13 -> 12); hindsight shell archived

Progress: [█████████░] 92%

## Performance Metrics

**Velocity:**

- Total plans completed: 26
- Average duration: -
- Total execution time: -

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 3 | - | - |
| 2 | 1 | - | - |
| 3 | 1 | - | - |
| 4 | 1 | - | - |
| 5 | 1 | - | - |
| 6 | 4 | - | - |
| 07 | 5 | - | - |
| 08 | 7 | - | - |
| 09 | 3 | - | - |
| 10 | 5 | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
**Per-Plan Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 6 P02 | 8min | 3 tasks | 7 files |
| Phase 6 P03 | 18min | 3 tasks | 10 files |
| Phase 6 P04 | 6min | 3 tasks | 6 files |
| Phase 7 P01 | 6min | 3 tasks | 10 files |
| Phase 7 P02 | 14min | 3 tasks | 7 files |
| Phase 7 P03 | 36min | 2 tasks | 5 files |
| Phase 7 P04 | 7min | 4 tasks | 7 files |
| Phase 7 P05 | 24min | 4 tasks | 10 files |
| Phase 08 P01 | 11min | 3 tasks | 8 files |
| Phase 08 P02 | 15min | 3 tasks | 6 files |
| Phase 08 P03 | 16min | 3 tasks | 6 files |
| Phase 08 P01 | 26min | 2 tasks | 7 files |
| Phase 08 P02 | 11min | 3 tasks | 3 files |
| Phase 08 P03 | 25min | 3 tasks | 5 files |
| Phase 08 P04 | 17min | 3 tasks | 8 files |
| Phase 08 P05 | 24min | 3 tasks | 8 files |
| Phase 08 P06 | 4min | 3 tasks | 4 files |
| Phase 08 P07 | 24min | 3 tasks | 5 files |
| Phase 09 P01 | 15min | 3 tasks | 5 files |
| Phase 09 P02 | 17min | 3 tasks | 8 files |
| Phase 09 P03 | 25min | 3 tasks | 7 files |
| Phase 10 P01 | 7min | 2 tasks | 6 files |
| Phase 10 P02 | 3min | 2 tasks | 2 files |
| Phase 10 P03 | 7min | 3 tasks | 6 files |
| Phase 10 P04 | 4min | 3 tasks | 3 files |
| Phase 10 P05 | 7min | 3 tasks | 3 files |
| Phase 11 P01 | 11 min | 2 tasks | 7 files |
| Phase 11 P02 | 6 min | 3 tasks | 5 files |
| Phase 11 P03 | 6 min | 2 tasks | 4 files |
| Phase 11 P04 | 2 min | 2 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Approval prompts served on main thread via ApprovalBroker (Phase 4).
- Denials never cover batch signatures; only approvals do (Phase 4).
- Choice dialogs use a bespoke owned-keys control, not stock RadioList (Phase 4).
- Switch-first convert + mid-turn slash refusal for /model (Phase 5).
- Display-only cost with automatic most-precise-first pricing + provenance line (Phase 5).
- Local skills: builtin slash heads always win collisions with shadow warnings; BUILTIN_SLASH_HEADS single-sourced in skills.py; loop passes its SkillIndex to dispatch (Phase 6-01).
- [Phase 6]: Memory injector: corrupt frontmatter keeps full body plus transcript note; empty dual load renders no block; /memory joins BUILTIN_SLASH_HEADS (Phase 6-02) — Defaults-plus-note satisfies never-crash without content loss; shadow entry fulfills the D-02 collision contract recorded in 06-01
- [Phase 6]: Curate approve routing: init-sourced proposals replace-or-append the full section plus upsert the root pointer (merge-never-clobber); every other source appends (Phase 6-03) — Without routing, init approvals would duplicate stale sections and never touch root; the D-10 split requires the approve verb to dispatch by proposal source
- [Phase 6]: Revise/init rounds ride session-sticky in-memory holders; router returns (agent, text) with armed state and the loop consumes fenced blocks post-turn, never the router (Phase 6-03) — Keeps the reply-only router contract while giving revise iterate loops and init one-shot drafts a clean turn-boundary owner; interrupts disarm first so files stay byte-identical
- [Phase 6]: D-13 renders as accept-echo (post-dispatch console line), not inline buffer highlight — Per planner resolution: no prompt_toolkit lexer surgery for the same decision value; the echo shows match vs typo at accept time
- [Phase 6]: Committed gap-closure work directly on main under branching_strategy none — Sequential dispatch on the main working tree; the #3819 protected-branch guard targets branch workflows and all milestone commits share this line
- [Phase 6]: Task-2 explicit-approve kept-pending assertion landed in task 3 commit — Pop-first approve (WR-03) drops p1 before the write raises, so the pending half of the criterion required the apply-first reorder; reply-prefix half verified in task 2
- [Phase 6 UAT]: build_agent owns the AgentSkills instance; /skills reload refreshes the harness registry first via set_available_skills, then the CLI index — failed refresh leaves both stale, never disagreeing (live-verified)
- [Phase 6 UAT]: print_plain (markup off, style kwarg) for all dynamic transcript prints; callback str paths use markup=False inline — WR-06 class closed without escapes
- [Phase 6 UAT]: Explicit invocation frames skill trust (follow as the task, no skills-tool re-check); distrust scoped to embedded third-party directives; deny-first gate stays the hard control (live-verified)
- [Phase 7]: Side agent built via create_harness factory rebuild over stashed parent kwargs with the live resolved model; forked history passes as the invocation prompt, never pre-seeded (avoids double user turn)
- [Phase 7]: Tracer join holds the turn boundary until side work completes; boundary flush (history) on success path only — failed main turns keep the live-rendered side answer transcript-only
- [Phase 7]: Tagged `[main]`/`[btw]` approvals from event.agent identity with tag-keyed ask stash plus thread-local tag; batch coverage namespaced per agent with denials never covering; trust_delegated btw auto-trust prints a transcript note naming the tool
- [Phase 7]: Per-request broker cancel registry (main/btw events); shared PendingStore audited not-proven-safe and lock-guarded across load-mutate-save
- [Phase 7]: Cancel chooser runs inside the dual pump on the main thread (executor shutdown would park on uncancelled workers otherwise); Ctrl-C in the chooser escalates to both; main-only pick drains the side answer through the served pump; tagged cancel lines via print_plain (markup off, WR-06)
- [Phase 7]: Unbounded FIFO BtwQueue with visible depth echoes; pump spawns only when no side run is live; queue owns its submit echo (BtwContext.submit)
- [Phase 7]: D-11 ships as bounded-wait, not async-multiplex — spike proved sync prompt_toolkit dialogs cannot run inside the multiplex loop; idle side approvals announced once and served by the next turn's pump
- [Phase 7]: Tracer join removed; BtwContext is session-scoped so new turns adopt a live side future and queued questions start across the idle gap
- [Phase 7]: Gap closure 07-04 — nesting-refcount pump, ONLY-framed plus context-marked side fork (exclusion fallback held), dead-tag pump drain plus SDK-wrap cancel mapping plus ack-before-join, tagged dialog titles with byte-identical typed path
- [Phase 7]: Gap closure 07-05 — E multiplex ships per live-pty GO verdict; dialog Ctrl-C at idle cancels the side run and re-issues with the buffer; prompt()-only doubles keep the sync prompt
- [Phase 7]: Gap closure 07-05 — exit names a live side via fenced render_btw_dropped (waiting/running) with the next-turn promise suppressed on the exit path
- [Phase 7]: Gap closure 07-05 — reentrant StdinGuard in steering.py shared by ask/chooser/radio_choice choke point; typeahead cleared on dialog entry; reader polls held()
- [Phase 08]: Routed effort validates on the switch path only; same-model no-op picks skip validation and effort application — Effort has no sticky companion to compare and re-resolving every ask would churn; the no-op fast path wins
- [Phase 08]: Hold-note engine slot uses resolve for resolve failures and the producing engine for validation rejects — Keeps the slot truthful: switch-stage cause vs rejected engine output, same attribution as parse failure
- [Phase 08]: Bare /route reports status mirroring bare /mode; symlinked strategy degrades to routing-off with a note — Bare-status mirrors the ModeState precedent; the loader keeps fail-loud while the loop keeps the session alive
- [Phase 08]: Held routing events record the serving model with empty effort/why; zero-usage decisions print no cost part and add no provenance — Keeps held /cost lines truthful and stops failed calls from flipping the Prices provenance line
- [Phase 08]: YAML 1.1 on/off bools map to openrouter/off at strategy load — Unquoted primary off parses as boolean False; without normalization an explicit off warn-defaulted back to openrouter (fail-open)
- [Phase 08]: Side holds append held side-flagged events with no transcript note; spawns refresh to the live parent model only on the routing-attempted path — Every decided ask appends an event so side decision spend cannot hide; the live-model refresh is scoped so off/unconfigured spawns replay byte-identically
- [Phase 08]: Validate is the strict judge while load stays fail-soft: skipped entries fail validation, unknown top-level keys and empty directives stay valid notes — Skipped entries mean the file does not mean what the user wrote, so validate fails them with fixes; the loader keeps routing with the survivors
- [Phase 08]: Single-candidate strategies with advertised levels skip all decision engines via a pick-shaped fast-path verdict — Nothing to choose means no decision call to pay for; the unchanged hook takes its pick branch with zero-token spend recorded
- [Phase 08]: Live engine tests skip on absent credentials or daemon but fail loudly when a present endpoint rejects the call — Absence skips keep CI hermetic; failing on present-but-broken endpoints surfaces contract drift, proven by the live OpenRouter pass this run
- [Phase 08]: [Phase 08-01]: Threshold holds short-circuit the engine chain; model_confidence is the routed table probability; same-model picks skip effort validation — Below-threshold means the ask is ambiguous (retry next ask, never next engine); vendor confidence is engine-specific so the gate reads top-1 probability; the hook applies nothing on no-op picks so validation is meaningless there
- [Phase 08]: [Phase 08-01]: Reported decision cost verbatim into /cost line and totals; cost-absent local calls render zero, token-estimate branch deleted — usage.cost is exact input-token billing while cost_for re-estimates from tables; verbatim keeps /cost truthful and stops failed calls from flipping provenance
- [Phase 08]: [Phase 08-01]: Provisional gate defaults 0.70/0.05 ship marked for 08-05 probe calibration; lone candidate without levels holds with no engine call — Thresholds must come from real probe distributions never round numbers; a one-option choice is invalid (2-26) and no effort exists to pass through, so hold is the only models-only verdict
- [Phase 08]: [Phase 08-02]: Single-level picks skip call 2 with the lone level riding through; lone-single-level keeps a documented zero-call route exception — A one-option choice has nothing to judge and violates the documented 2-26 floor (Ollama rejects it); the exception is pinned by test_lone_single_level_routes_with_no_call
- [Phase 08]: [Phase 08-02]: Same-model picks run call 2 but skip validate_routed_effort; call-2 failures hold; outside-levels reads hold via validate_routed_effort — Preserves the locked 08-01 no-op decision (hook applies nothing on same-model picks); a failed effort read carries no level to route, and membership rejects keep the unsupported-effort detail
- [Phase 08]: [Phase 08-03]: Unready daemons yield an inert zero-POST link; 4xx/schema keep falling through; pause fires only when every attempted link fails at connection level — Inert link keeps the _chain_for signature while the distinct detail flows through the error channel; fall-through is the existing tested contract the plan does not revoke; neutral skipped/unready/errorless links keep mixed failures informative
- [Phase 08]: [Phase 08-03]: Pause is turn-scoped on RoutingState and only the ask tightens under the 64 KiB body cap — Pre-turn resumes every ask per D-08 retry-next-ask while side spawns skip with zero POSTs; ask-only tightening keeps the guard simple and criteria overshoot degrades to a 413 hold with the engine-plus-code detail
- [Phase 08]: [Phase 08-04]: Split-catalog setup with decisions-cache validate; empty local tag takes nimble; rig levels [auto, off] — Decisions catalog drives the decider pick and the validate check (D-06); nimble is the RESEARCH default local tag; reasoning-free levels keep scripted live runs deterministic on any boot model
- [Phase 08]: [Phase 08-05]: Probe-derived gate defaults 0.62/0.04 ship with recorded baseline; one shared threshold, compare-mode regression, env-gated live tests — Threshold 0.62 is the midpoint of the observed 0.51/0.73 gap and tie margin 0.04 is the max near-tie margin plus one grid step; neither engine misfires dangerously so no per-engine split; effort flips warn since weak effort reads route ungated
- [Phase 08]: [Phase 08-06]: GAP-01/02/03 closed — YAML-bool levels fold to on/off strings in the loader (identity checks, int still skips), non-string choice holds at both membership checks, probe local tag resolves on the local path only — Hand-edited unquoted off must parse per D-13, every failure class holds per D-08, and cloud calibration never needs a daemon per D-06
- [Phase 08]: [Phase 08-07]: FENCE — routed picks never persist the global default; only explicit /model choices persist
- [Phase 08]: [Phase 08-07]: Rig waits match (n/a) cost lines and snapshot all baselines pre-send; live R2/R3/R4 PASS closes G-08-1
- [Phase 09]: Empty effective order (explicit [] or legacy off) yields the off-equivalent hold via _effective_order in decide and _decide_effort — Explicit order [] must disable routing exactly like primary off, including the single-candidate fast-path guard
- [Phase 09]: decision_model_for names the native model for native — Otherwise production native events record decision_model None and real /cost output never carries the computed-rate marker (Rule 2 adjunct)
- [Phase 09]: Unknown primary is not judged when engine.order is present — An ignored value judges nothing; the both-present validate test pins it
- [Phase 09]: Non-list engine.order fails validation with a fix line — Mirrors the candidates not-a-list precedent; loader stays warn-and-default
- [Phase 09]: Setup stdout never prints the TYPESAFE_API_KEY literal (uses 'TypeSafe key' phrasing), keeping test_setup_never_prompts_for_keys green unweakened
- [Phase 09]: Validate ping flips the report head to INVALID on key/model failures — appended lines alone would not fail bad keys
- [Phase 09]: Ping gate reads strategy.engine.order directly — the loader coerces primary, so native reaches the effective order only via explicit order
- [Phase 09]: Off-tty order builder aborts on the second unknown engine — an order is positional, so a partial write would silently reorder the chain
- [Phase 09]: Native fault keys added to the probes.jsonl fault maps — Without native keys _fault_for returns None, the fault arms never fire live, and fault probes record routed verdicts (mirrors the local-keys precedent)
- [Phase 09]: Fresh openrouter plus local runs precede compare — Compare diffs all three run files and reports missing ones as drift, so a native-only run can never exit 0; the fresh runs double as a drift check
- [Phase 09]: N4 asks the debug ask, not the r2 trivial ask — Jev holds the trivial ask 2/2 at 50 percent under the rig strategy while the debug ask routes current at 0.92-0.95 (genuine model judgment, reproduced)
- [Phase 09]: N4 asserts the via-native spend cell, not the Prices marker — Live turns fold the unit-pinned single-source marker into Prices mixed (shipped 09-01 behavior)
- [Phase 09]: R1 branches on the native radio — Alternation wait keeps r1 green key-present and key-absent
- [Phase 10]: Tracer: reported_cost row key stored only when present; actual-wins branches check is-not-None; marker text is the literal word actual — Conditional key keeps the existing exact-dict row assertion green without weakening it; is-not-None keeps a present 0.0 an actual per Ruling 1; literal-word marker matches the D-08 split vocabulary with one marker everywhere
- [Phase 10]: Display: lane-opens is presence-based (present 0.0 actual opens the actuals lane, derived zeros never do); split sits beneath Total as '  (actual $X + estimated $Y)' — Direct reading of the planner lock that a lane opens only on a present reported value or a computed estimate; keeps marker-iff-reported crisp and D-11 restraint symmetric
- [Phase 10]: Side builds fresh-copy cost-aware models (plain pass through identical); routed side wrap sits inside the resolve try so a wrap failure holds to the live model like a resolve failure — Keeps main-vs-btw drains separate per D-09 with zero drift on non-wrapped paths; preserves the side-hold contract with no new failure mode
- [Phase 10]: Live proof constructs LiteLLMModel directly with the env key in client_args instead of going through resolve_model — The harness litellm builder only forwards LITELLM_API_KEY/LITELLM_BASE_URL env, so resolve_model would not carry OPENROUTER_API_KEY; direct construction follows the verified harness client_args shape
- [Phase 10]: Re-wrap unconditionally resets _reported_costs to [] (supersedes the 10-01 preserve-on-rewrap decision per D-09) — Absent/None/empty/non-empty converge on one outcome; costs gathered without per-turn drain discipline belong to no single turn, so discarding once prevents misattribution
- [Phase 10]: Nested-model fallback in _drain_reported_cost drains agent.model when the passed object lacks take_reported_costs — Keeps agent-shaped callers draining even if a future site passes the Agent again; fail-soft try/except still returns None on drain errors
- [Phase 10]: Single-inheritance ReportedCostModel(base) with capture methods defined directly (mixin removed) — CPython rejects in-place promotion to a multi-inheritance subclass on the slotted SDK chain; closes UAT G-10-1/G-10-3 with the keyed live proof and c1 rig C1 PASS as evidence
- [Phase 11]: Turn-setup lives in testable codeact.py seams (resolve_turn_interface, shape_turn_text, codeact_label); loop.py calls them at the mode/routing hook site — The plan's turn_setup/label/tracer tests are untestable against loop-inline code, so the seams carry the behavior and the loop holds thin glue
- [Phase 11]: Both-holder turns resolve to tool-shaped until per-ask routing lands in 11-02 — Plan shapes only code turns with the prefix; both stays a legal holder value with tool behavior pinned by test
- [Phase 11]: Remember-last gates the read path only; every /codeact switch persists the last choice unconditionally — Plan persist step has no gating condition; unconditional persist keeps the saved value fresh for a later remember opt-in
- [Phase 11]: Run-loop codeact config read stays fail-loud like the model line; load/save validation is the boundary — Config-file errors are already fatal at startup; a guarded read here would still crash one line later at the unguarded model read
- [Phase 11]: Interior codeact_* functions are cwd-first module functions bound via functools.partial; swap/restore are explicit seams with the turn-local flag restored in the loop's outer turn finally — Probe-verified partials in smolagents; one finally covers attempts, revise rounds, and cancel
- [Phase 11]: stint.tool evaluates only on code turns; new swap tests carry turn_setup in method names — Preserves stint laziness on the tool path; pre-existing TestTurnSetup never matched the -k turn_setup filter
- [Phase 11]: Syntax preview replaces the Detail line in place for python_repl only; revise hint rides the policy-rule denial, plan-deny stays byte-identical — No duplicated half-preview; mode-vocabulary lock keeps plan-deny untouched
- [Phase 11]: D-07 pins use single-line blocks; the pre-existing multi-line TOML serialise gap is deferred, not fixed — Task 2 is tests-only; probe-verified the gap predates CodeAct (multi-line shell rules break identically); logged to 11/deferred-items.md
- [Phase 11]: Bare --codeact implies code via pure argv pre-normalization in main() — the pinned typer never forwards flag_value/is_flag to click, so the helper rewrite is the mechanism; BadParameter pre-gate check byte-identical before the credential gate

### Pending Todos

None yet.

### Blockers/Concerns

- ⚠️ [Phase 4→] `reasoningContent` in resumed opus history fails validation on non-reasoning Bedrock models; workaround is a fresh session — durable strip-on-restore still open (survived Phases 5–7; Phase 7 fork path strips, restore path untouched).
- ⚠️ [Phase 6 UAT] Silent memory mode can memorialize the model's own rationalizations as user preferences (observed: refusal principles stored as durable preferences) — curate default is the backstop; silent users should review MEMORY.md periodically.
- ⚠️ [Phase 7] PendingStore lock-guarded but not proven race-safe under dual-stream load; residual dialog-safety risk under concurrent main+side streaming remains.

### Roadmap Evolution

- Phase 07.1 inserted after Phase 7: CodeAct action interface (URGENT)
- Phase 07.2 inserted after Phase 7: Model routing with decision models (URGENT)
- Phase 8 inserted after Phase 7: CodeAct action interface (re-scoped from decimal 07.1 to integer 8 per user)
- Phase 9 inserted after Phase 8: Model routing with decision models (re-scoped from decimal 07.2 to integer 9 per user); GitHub loop renumbered 8 to 10
- Phase 8 inserted after Phase 7: Swap per user: 8 is now Model Routing, 9 is now CodeAct; CodeAct opt-in only (tool-calling default, both allowed, never mandatory)
- Phase 10 removed: GitHub loop deferred out of v1 to a future milestone per user; GITHUB-01/02 + REVIEW-01 moved to v2 backlog, v1 = phases 1-9
- GitHub loop dissolved (not just deferred): no dedicated phase — `gh` via general tool competence, GITHUB-01/02 marked covered/no-build, only `/review` stays a future slash; parity aim rescoped to best Bedrock-first terminal CLI, not Claude Code feature parity

## Deferred Items

Items acknowledged and deferred at milestone close, most recent first:

| Category | Item | Status | Deferred At | Milestone |
|----------|------|--------|-------------|-----------|
| *(none)* | | | | |

## Session Continuity

Last session: 2026-10-16T04:59:11.492Z
Stopped at: Phase renumber (13 -> 12)
Resume file: (none — run $gsd-discuss-phase 12)
