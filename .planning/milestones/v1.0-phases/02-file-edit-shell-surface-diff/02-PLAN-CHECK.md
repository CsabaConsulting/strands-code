# Phase 02 Plan Check: File/Edit/Shell Surface + /diff

**Verdict: PASS** (minor notes only; no blocking defect)

**Checked:** `02-PLAN.md` (+ `02-PLAN-SUMMARY.md`) against ROADMAP Phase 2, CONTEXT D-01..D-09, RESEARCH findings/risks, REQUIREMENTS TOOL-01/02/04.

## Coverage

- TOOL-01 (read/write/edit/shell): tracer task pins `builtin_tools` mapping in `main.py:66-80`, scope guard, gate wrappers. Covered.
- TOOL-02 (`/diff` before apply): diff_config + diff_gate + rendering + `/diff` routing with approve-each/on-demand/auto. Covered.
- TOOL-04 (grep/READ, no index): search_tool (rg + stdlib fallback) + `/search` routing + no-index prohibition. Covered.
- ROADMAP success criteria 1/2/3 map 1:1 onto plan success_criteria. Covered.
- RESEARCH risks §6.1–§6.8 all addressed (collision test, shell/python_repl advisories, TOCTOU re-read, cwd resolve, subagent note, local grep, bleed prohibitions). Threat model T-02-01..T-02-08 present.
- D-02..D-09 honored; D-03/D-04 planner's-call items decided (repl stays compute + prompt steering; ProviderConfig-pattern mode store + per-hunk/whole/none granularity).

## Scope bleed: none

- Prohibitions explicitly fence out Phase 3 (policy file, general approval, network gating, `interventions`) and Phase 4 (general auto/yolo mode system), plus index/embeddings and `strands_tools` import. Gate `auto` is file-mutation-scoped per D-04, not a general mode; vocabulary-collision risk is recorded for Phase 4. Verification ends with a grep audit for `strands_tools`/`interventions`/`policy`.

## Ordering and executability

- Tracer-first: task 1 is `type="tracer"`, verifies live defaults before pinning, with TDD kwargs assertion. Good.
- Every task has `read_first` with file:line grounding, TDD action, `uv run pytest` verify with fails_when, acceptance criteria, and `<reversibility>` rating (6 reversible + gate marked costly with rationale). Good.

## Issues (all minor, non-blocking)

1. D-01 literal deviation (justified): CONTEXT D-01 names `strands-agents-tools`; plan follows RESEARCH §1.1 (not installed; editor/shell deprecated) and wires harness 0.1.2 builtins instead, with an explicit MUST-NOT prohibition. Correct call, but downstream readers should know the context line was superseded by research evidence.
2. Parallel wave markers incoherent: tasks 2–3 marked `[P1]`, tasks 4/6/7 `[P2]`, gate task unmarked, while frontmatter says single `wave: 1`. Gate task depends on scope (task 2) + DiffConfig (task 4) yet carries no sequencing marker; suggested order tracer → (scope, search, diff-config) → gate → (rendering, repl-role) is only implicit.
3. Shared-file writers: `main.py:66-80` is touched by tracer, gate, and repl-role tasks; `tests/test_tool_surface.py` by tracer/scope/repl-role; `tests/test_diff_gate.py` by diff-config/gate/rendering. If `[P1]`/`[P2]` are executed as parallel waves, same-file tasks need sequencing.
4. `/search [--glob]` gap: summary artifacts advertise `/search <pattern> [--glob]`, but the router task only wires `/search <pattern>` with no `--glob` passthrough to the tool's `file_glob` param.
5. Loose grounding paths: several `read_first` entries use `.venv/.../` ellipsis rather than a directly openable path (contrast the fully-grounded `agent.py:300-340` entry).
6. D-07 reversibility nuance: D-07 rates the scope decision costly; the scope task rates itself reversible (true for the module, costly for widening later). No action, just note the two senses differ.
