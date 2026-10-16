# Phase 12: Structural Review + Hygiene - Context

**Gathered:** 2026-10-16
**Status:** Ready for planning

<domain>
## Phase Boundary

A measurement-first structural review of the CLI tree plus dead-code hygiene. Complexity and coupling are measured with radon/xenon, the flat `strands_code_cli/` layout is repackaged by feature, the uattest driver is split into a shared lib plus per-area scenario files, ruff governs lint + format, and the dead OKF example (plus its knowledge module) is removed. No behavior changes — pure structure. Full suite and rig stay green throughout.

</domain>

<decisions>
## Implementation Decisions

### Measurement gate
- **D-01:** radon/xenon for cyclomatic complexity plus an import-graph coupling check (new dev deps, supply-chain review applies).
- **D-02:** Persistent gate — thresholds enforced on every run (CI + pre-commit), not a one-shot report.
- **D-03:** Standard grades — fail on functions worse than C (complexity > 20), warn on C.
- **D-04:** Committed report — the numbers live in a committed report the breakup cites.

### Breakup scope
- **D-05:** Full repackage — reorganize the whole flat `strands_code_cli/` layout into feature packages, not just the three giants. — **Reversibility:** one-way — the package layout is a published import contract; undoing it means a second flag-day move.
- **D-06:** By feature, keeping layers in mind — group by feature area (loop/, routing/, dispatch/) with layer sensibility, not strict layering.
- **D-07:** Tests mirror — `tests/` moves with the new package layout (all 45 files).
- **D-08:** CLI only — `strands_code_agent/` keeps its shape so the fork can still receive upstream updates. The sole exception is the knowledge-module removal (D-15), which is fork-added code.

### Import compatibility
- **D-09:** Clean break — old `strands_code_cli.<module>` paths break; all in-repo imports move; no re-export shims.
- **D-10:** Entry reorganization allowed if CLI-internal and upstream-merge safe (main.py moves with its feature).
- **D-11:** In-repo only — external importers break loudly; no migration note published.
- **D-12:** The CLI-internal bound is the merge-safety rule: nothing in the repackage may touch `strands_code_agent/` except D-15 or the repo-root layout.

### Rig split shape
- **D-13:** Shared lib — tmux/send/wait/save plumbing extracts into one uattest library; scenarios import it.
- **D-14:** Per area — one scenario file per area (side, routing, native, cost, codeact); `driver.py` stays a thin dispatch entry with the same command; contract tests split to mirror.

### Cleanup scope
- **D-15:** Remove both — `examples/pdf_to_okf_bundle` plus `strands_code_agent/knowledge` (fork-added per git history: "Feature Request: Document processing library set"; planner must confirm no upstream overlap before deleting).
- **D-16:** Full README rewrite of the features table for the post-cleanup tree (not just dropping the OKF row).
- **D-17:** Cleanup first — dead code is deleted before measurement, so the numbers describe the tree being repackaged.

### Lint and format (added post-discussion 2026-10-16)
- **D-18:** Ruff governs general lint + format (`ruff check` and `ruff format`); config lives in `pyproject.toml`. The whole tree is formatted once during the phase, and the persistent gate (D-02) enforces ruff-clean on every run alongside the complexity thresholds.
- **D-19:** Ruff formatting lands before the repackage moves (with cleanup first, D-17), so later diffs show moves, not reformatting.

### the agent's Discretion
Exact package names and boundaries, the coupling metric choice, report location and format, pre-commit wiring details, ruff rule selection and line length, and README prose are left to planner/executor judgment within the locked decisions above.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements and roadmap
- `.planning/REQUIREMENTS.md` — STRUCT-01 (measurement-first review, suite/rig green throughout), CLEANUP-01 (no dead example code, README ships-only)
- `.planning/ROADMAP.md` — Phase 12 goal, STRUCT-01/CLEANUP-01 requirements, 3 success criteria (measured + cited breakup, packages + rig split, example removed + README fixed)

### The tree under review
- `strands_code_cli/` — flat layout (~28 modules, ~15k lines); giants: `loop.py` (2517), `routing.py` (2345), `router.py` (2113)
- `scripts/uattest/driver.py` — 1069 lines: tmux plumbing + 12 scenarios (s/r/n/c/a areas)
- `tests/test_uattest_driver.py` — rig contract tests (split to mirror per D-14)
- `examples/pdf_to_okf_bundle/` + `strands_code_agent/knowledge/` — removal targets (D-15; verify fork-only provenance first)
- `pyproject.toml` — no lint/complexity tooling configured today; dev-dep + gate wiring goes here

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `uv run pytest tests/ -q` (1553 passed) + `driver.py {a1,a2,...}` — the green-throughout guardrails; every move must keep them green
- `.github/` workflows (if present) — CI wiring point for the persistent gate (D-02)
- `strands_code_cli/__init__.py` (5 lines) — the package root the repackage grows from

### Established Patterns
- Harness-first, stdlib instincts, uv-only runs (project constraints) — the measurement tooling is the sanctioned exception (D-01, dev deps only)
- Upstream-merge safety for the forked agent library (user constraint) — D-08/D-12/D-15 follow this

### Integration Points
- Every `strands_code_cli.*` import site (code, tests, scripts) — clean-break move target (D-09)
- `scripts/uattest/driver.py` dispatch table — stays as thin routing (D-14)
- README features table — full rewrite (D-16)
- CI + pre-commit config — persistent gate wiring (D-02)

</code>

<specifics>
## Specific Ideas

- User's driving constraint for the agent library: "The aim is to be able to receive updates from the forked upstream" — this outranks structural elegance for `strands_code_agent/`; only fork-added dead code (D-15) may go.
- Full repackage (not just giants) plus clean break (not shims) means this phase is a flag day for imports — planners should sequence moves to keep the suite green at every commit, not just at the end.

</specifics>

<deferred>
## Deferred Ideas

- Agent-library restructuring — out of scope for upstream-merge safety (D-08).
- External-importer migration note — rejected (D-11); break loudly instead.

None of the above belong in Phase 12 scope.

</deferred>

---

*Phase: 12-Structural Review + Hygiene*
*Context gathered: 2026-10-16*
