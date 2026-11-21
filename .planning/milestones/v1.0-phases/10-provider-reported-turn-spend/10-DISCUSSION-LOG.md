# Phase 10: Provider-Reported Turn Spend - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-12
**Phase:** 10-provider-reported-turn-spend
**Areas discussed:** Actual-vs-estimate marking, Missing-cost fallback, Session totals

---

## Actual-vs-estimate marking

**Q1: How should /cost per-turn rows distinguish reported actuals from estimates?**

| Option | Description | Selected |
|--------|-------------|----------|
| Inline marker | Appends a marker like (actual) to reported rows, keeps estimates bare — cheapest change to cost_report rows. | ✓ |
| Separate column | Adds an actual/estimated column to /cost tables — most explicit, widest layout change. | |
| Footer note only | No per-row marking; explain sourcing once in a Prices/provenance footer line. | |

**User's choice:** Inline marker
**Notes:** None.

**Q2: Should the post-turn usage line carry the same actual/estimate marking?**

| Option | Description | Selected |
|--------|-------------|----------|
| Same marker | Usage line shows $ only on estimate-hit today; keep that rule and add the same inline marker when the figure is an actual. | ✓ |
| Usage line unchanged | Leave the usage line as-is (bare $ either way); sourcing visible only in /cost. | |
| You decide | Let the planner pick the usage-line treatment during planning. | |

**User's choice:** Same marker
**Notes:** None.

**Q3: Which side gets the marker — actuals, estimates, or both?**

| Option | Description | Selected |
|--------|-------------|----------|
| Mark actuals | Bare $ keeps today's meaning (an estimate); only actuals get marked. Matches the Phase 9 computed-rate marker precedent. | ✓ |
| Mark estimates | Bare $ means actual; estimates get marked. Flips today's implicit meaning of the usage-line $. | |
| Mark both | Both sides get explicit markers; no bare $ remains anywhere. | |

**User's choice:** Mark actuals
**Notes:** None.

**Q4: Should routing/decision spend lines adopt the same marking?**

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, unify | Decision spend lines adopt the same actual marker for consistency across /cost. | ✓ |
| Main turns only | Leave routing lines as-is; only main-turn rows get the new marking. | |
| You decide | Let the planner decide during planning. | |

**User's choice:** Yes, unify
**Notes:** None.

---

## Missing-cost fallback

**Q1: An OpenRouter main turn reports no usage.cost — what should /cost show?**

| Option | Description | Selected |
|--------|-------------|----------|
| Estimate fallback | When usage.cost is absent, compute tokens × almanac rate and show it as an estimate — main turns stay informative. | ✓ |
| Render zero | Mirror the Phase 8 decision rule exactly: cost-absent rows render $0, never an estimate. | |
| Show n/a | Show n/a for the money cell when no cost is reported and no estimate applies. | |

**User's choice:** Estimate fallback
**Notes:** Explicitly diverges from the Phase 8 decision rule — main turns stay informative.

**Q2: If neither a reported cost nor an almanac price exists for the turn, what shows?**

| Option | Description | Selected |
|--------|-------------|----------|
| Tokens-only | Keep today's rule: money appears only on price hit; otherwise tokens-only. No change from current behavior. | ✓ |
| Explicit zero/n/a | Show an explicit $0 or n/a money cell so the row shape stays uniform. | |
| You decide | Let the planner decide during planning. | |

**User's choice:** Tokens-only
**Notes:** None.

**Q3: How should Bedrock and offline turns behave under the new rules?**

| Option | Description | Selected |
|--------|-------------|----------|
| Estimates stay | Bedrock/local turns keep tokens × rate estimates exactly as today — only OpenRouter-reported turns change. | ✓ |
| Report where possible | Bedrock turns also attempt a reported-cost path this phase (e.g. via a billing API). | |
| Unify fallback | Treat Bedrock turns like cost-absent OpenRouter turns under the same new rule. | |

**User's choice:** Estimates stay
**Notes:** None.

**Q4: OpenRouter reports usage.cost of exactly 0.0 — actual zero or missing?**

| Option | Description | Selected |
|--------|-------------|----------|
| Show marked zero | A literal 0.0 reported cost displays as an actual (marked), distinct from a missing cost. | |
| Estimate instead | Treat 0.0 like a missing cost and fall back to the estimate path. | |
| You decide | Let the planner decide during planning. | ✓ |

**User's choice:** You decide
**Notes:** Agent's discretion item for planner/researcher.

---

## Session totals

**Q1: In a mixed session, what should the /cost session total look like?**

| Option | Description | Selected |
|--------|-------------|----------|
| Blended + split | Headline total blends both, with an actual/estimated split shown beneath — one number plus full transparency. | ✓ |
| Blended only | Only the blended total shows; per-row markers carry the sourcing detail. | |
| Split only | No blended number; show separate actual and estimated subtotals only. | |

**User's choice:** Blended + split
**Notes:** User note: "Except when OpenRouter is not used at all (no actual cost available) — then don't convolute the display with unnecessary not available parts." Led to Q4.

**Q2: What is the no-double-counting rule when a turn has both an actual and an estimate?**

| Option | Description | Selected |
|--------|-------------|----------|
| Actual wins | A turn contributes either its reported actual or its estimate to the total, never both — actual wins when present. | ✓ |
| Estimates in total | Totals always use estimates for comparability; actuals show per-row only. | |
| You decide | Let the planner decide the precedence rule during planning. | |

**User's choice:** Actual wins
**Notes:** None.

**Q3: Should routing/decision spend stay included in the session total?**

| Option | Description | Selected |
|--------|-------------|----------|
| Include | Decision spend rolls into the session total as reported actuals alongside main-turn actuals. | ✓ |
| Exclude | Decision spend shows on routing lines only, excluded from the session total. | |
| Unchanged | Keep today's behavior unchanged for routing spend in totals. | |

**User's choice:** Include
**Notes:** None.

**Q4: When a session has no actuals at all, how should the total display?**

| Option | Description | Selected |
|--------|-------------|----------|
| Hide split | Hide the actual/estimated split entirely; show today's plain total. | ✓ |
| Show zero split | Show the split with a zero actual part for layout consistency. | |
| You decide | Let the planner decide during planning. | |

**User's choice:** Hide split
**Notes:** Follows from the user's Q1 note on avoiding clutter.

---

## the agent's Discretion

- Literal `0.0` reported cost: marked actual zero vs estimate fallback (Missing-cost fallback Q4).
- Exact marker text/symbol for actuals; exact split layout beneath the headline total.

## Deferred Ideas

None — discussion stayed within phase scope.
