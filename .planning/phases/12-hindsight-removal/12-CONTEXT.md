# Phase 12: Hindsight Removal - Context

**Gathered:** 2026-10-16
**Status:** Ready for planning
**Supersedes:** 12-CONTEXT.md as written for "OpenViking Recall Backend" (same file, prior revision) — the OpenViking scope was abandoned during plan-phase research when the researcher proved D-01 embedded-in-process impossible (server required) and the user rejected the AGPL-licensed server. The OpenViking discussion (D-01..D-20) and 12-RESEARCH.md are preserved as rejection evidence, not as scope.

<domain>
## Phase Boundary

Remove Hindsight as a planned/supported integration and record the rejection rationale for both evaluated recall backends. In scope: restating SKILL-05, scrubbing live Hindsight references (REQUIREMENTS, ROADMAP, docs), preserving 12-RESEARCH.md as the OpenViking rejection record. Out of scope: any recall-backend implementation; touching historical audit trails (Phase 6 artifacts, .planning/research/* stay verbatim).

</domain>

<decisions>
## Implementation Decisions

- **D-01:** Hindsight is out: Postgres/pgvector + continuous background worker loop is too heavy for a terminal coding harness (user judgment, confirmed 2026-10-16).
- **D-02:** OpenViking is out: requires a running server (no embedded mode exists) and the server package is AGPL-licensed, which the user rejects.
- **D-03:** SKILL-05 is restated as a negative requirement (no Hindsight integration ships; heavy recall backends explicitly out of scope) so Phase 12 keeps its requirement trace.
- **D-04:** Live references are scrubbed (REQUIREMENTS.md, ROADMAP.md, docs/competitive-gap-analysis.md); historical references (Phase 6 artifacts, .planning/research/*, this phase's own discussion log) stay as audit trail.
- **D-05:** 12-RESEARCH.md is kept as the OpenViking rejection record — it must not be deleted or rewritten into a plan basis.
- **D-06:** Strands native memory stays the only recall backend; no replacement backend is in scope for this phase.

### the agent's Discretion
Wording of the SKILL-05 restatement and the docs supersede note are left to the executor within D-03/D-04.

</decisions>

<canonical_refs>
## Canonical References

- `.planning/REQUIREMENTS.md` — SKILL-05 (to restate)
- `.planning/ROADMAP.md` — Phase 12 entry (to rewrite)
- `.planning/phases/12-hindsight-removal/12-RESEARCH.md` — OpenViking rejection evidence (keep, do not re-scope)
- `docs/competitive-gap-analysis.md` — live doc recommending Hindsight (supersede note required)

</canonical_refs>

---

*Phase: 12-Hindsight Removal (re-scoped 2026-10-16; formerly OpenViking Recall Backend)*
