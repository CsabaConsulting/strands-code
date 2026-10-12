# Phase 10: Provider-Reported Turn Spend - Context

**Gathered:** 2026-10-12
**Status:** Ready for planning

<domain>
## Phase Boundary

`/cost` shows provider-reported actuals for main turns where the provider supplies them (OpenRouter `usage.cost`), estimates elsewhere, without double counting. Bedrock and offline turns keep tokens × rate estimates with provenance labeled. Display-only; no enforcement, no budget behavior.

</domain>

<decisions>
## Implementation Decisions

### Actual-vs-estimate marking
- **D-01:** Per-turn `/cost` rows distinguish reported actuals from estimates with an inline marker (no separate column, no footer-only note).
- **D-02:** The post-turn usage line carries the same marking as `/cost` rows.
- **D-03:** Bare `$` keeps today's meaning (an estimate); only actuals get marked. Follows the Phase 9 computed-rate marker precedent.
- **D-04:** Routing/decision spend lines adopt the same actual marker for consistency across `/cost`.

### Missing-cost fallback
- **D-05:** An OpenRouter main turn with no reported `usage.cost` falls back to the tokens × almanac-rate estimate (NOT the Phase 8 decision rule of rendering zero — main turns stay informative).
- **D-06:** When neither a reported cost nor an almanac price exists, the row stays tokens-only (today's money-only-on-hit rule, unchanged).
- **D-07:** Bedrock and offline turns keep estimates exactly as today; only OpenRouter-reported turns change. No billing-API reach for Bedrock this phase.

### Session totals
- **D-08:** Mixed sessions show a blended headline total plus an actual/estimated split beneath it.
- **D-09:** No-double-counting rule: a turn contributes either its reported actual or its estimate to the total, never both — actual wins when present.
- **D-10:** Routing/decision spend stays included in the session total as reported actuals.
- **D-11:** When a session has no actuals at all, the split is hidden entirely and today's plain total shows (no not-available clutter).

### the agent's Discretion
- Literal `0.0` reported cost: whether a `usage.cost` of exactly 0.0 displays as a marked actual zero or falls back to the estimate path — planner/researcher decides (user said "you decide").
- Exact marker text/symbol for actuals; exact split layout beneath the headline total.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Cost display (current behavior)
- `strands_code_cli/cost_context.py` — `usage_line`, `cost_for`, `cost_report`, `_routing_line`, `_reported_spend`; money-only-on-hit rule
- `strands_code_cli/loop.py` — per-turn token rows and usage-line emission

### Prior decisions
- `.planning/phases/08-model-routing-with-decision-models/08-CONTEXT.md` — D-12 cost line shape; reported decision cost verbatim; cost-absent local calls render zero (NOT carried to main turns per D-05)
- `.planning/phases/09-native-typesafe-decision-engine/09-CONTEXT.md` — computed-rate spend marker precedent (D-03 context)
- `.planning/phases/05-model-cost-context-commands/05-CONTEXT.md` — display-only cost posture; provenance labeling; `/cost` breakdown shape
- `.planning/REQUIREMENTS.md` — MODEL-05 requirement text
- `.planning/ROADMAP.md` — Phase 10 goal and success criteria

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_reported_spend(event)`: reported-USD extraction pattern (None when absent/non-numeric) — the main-turn analog starts here
- `cost_report(session_turns, model_id, routing)`: per-turn rows plus session totals — the surface D-01/D-08 extend
- `price_provenance` / Prices line: provenance labeling the split display must stay consistent with

### Established Patterns
- Display-only, never enforcement (Phase 5) — actuals change numbers shown, never behavior
- Money appended only on hit (`usage_line`) — D-06 preserves this for the no-price case
- Reported-over-estimated precedence already exists for decisions (verbatim `decision_cost`) — D-09 extends the precedence idea to main turns

### Integration Points
- Turn event records (where `usage.cost` must be captured from the provider response)
- `cost_report` totals accumulation (where the actual-wins rule and split apply)
- Usage-line emission in the turn loop (where the D-02 marker appears)

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches. User emphasized restraint: when OpenRouter is not used at all, the display must not be convoluted with not-available parts (D-11).

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 10-Provider-Reported Turn Spend*
*Context gathered: 2026-10-12*
