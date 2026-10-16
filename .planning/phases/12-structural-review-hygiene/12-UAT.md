---
status: complete
phase: 12-structural-review-hygiene
source: [12-01-SUMMARY.md, 12-02-SUMMARY.md, 12-03-SUMMARY.md, 12-04-SUMMARY.md, 12-05-SUMMARY.md]
started: 2026-10-16T00:00:00Z
updated: 2026-10-16T00:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: Start the CLI from scratch (uv run strands-code); it boots without errors and a basic turn runs. The entry point moved this phase.
result: pass
evidence: User transcript — booted to REPL, tribonacci turn ran with interface: tool. Model voluntarily used always-on python_repl with a self-authored "CodeAct mode" comment (session-history mimicry from Phase 11 UAT in the same session, not harness shaping — label confirms tool mode). No regression.

### 2. STRUCTURE.md report review (12-01 D4)
expected: docs/STRUCTURE.md records the complexity/coupling numbers with cited breakup rationale — read it and confirm it is coherent and complete.
result: pass
evidence: User read docs/STRUCTURE.md — giants justified by numbers, smaller files relatively calm; accepts the numbers.

### 3. Loop package shape + loud break (12-02 derived)
expected: strands_code_cli/loop/ holds core/pump/steering/btw with absolute imports only; old flat paths (strands_code_cli.loop, .steering, .btw) break loudly with ImportError/ModuleNotFoundError; strands_code_agent/ untouched.
result: pass
evidence: Orchestrator commands — loop/ holds 5 files, zero relative imports, old paths ImportError/ModuleNotFoundError, agent lib history is upstream + D-15 deletion only. User confirmed.

### 4. Repackage complete + entry works (12-03 derived)
expected: Every flat CLI module lives in its feature package (only __init__.py at root); strands-code --help exits 0; search_tool.py diff is exactly the carve-out line (AGENT-BOUND-OK); tests mirrored with no test_*.py at root.
result: pass
evidence: Orchestrator commands — 10 packages + __init__ only, ENTRY OK, phase-12 agent diff is knowledge/ deletion + one-line carve-out, ROOT-CLEAR. User confirmed.

### 5. Agent instructions describe new tree (12-05 D2)
expected: AGENTS.md and CONVENTIONS.md describe the ruff-governed repackaged tree, not the removed flat modules — read and confirm.
result: pass
retest: 2026-10-16 after 12-06 fix + retest tweak (user chose to drop the GitHub parenthetical entirely rather than keep/extend it; applied to PROJECT.md source + AGENTS.md block)

### 6. Dev tooling fork-scoped (12-01 D1)
expected: Dev tooling installed and configured for fork-owned paths only.
result: pass
source: automated
coverage_id: 12-01-D1

### 7. D-15 dead code deleted (12-01 D2)
expected: D-15 dead code deleted with no dangling references.
result: pass
source: automated
coverage_id: 12-01-D2

### 8. Tree ruff-clean, upstream pristine (12-01 D3)
expected: Fork-owned tree ruff-clean and ruff-formatted, upstream byte-identical.
result: pass
source: automated
coverage_id: 12-01-D3

### 9. Suite green after hygiene spine (12-01 D5)
expected: Full test suite passes after cleanup, format, and measurement.
result: pass
source: automated
coverage_id: 12-01-D5

### 10. Shared rig lib owns plumbing (12-04 D1)
expected: Shared uattest_lib.py owns tmux/send/wait/save plumbing; scenarios import it.
result: pass
source: automated
coverage_id: 12-04-D1

### 11. Per-area scenarios, same command (12-04 D2)
expected: Five per-area scenario files behind a thin driver with identical command surface.
result: pass
source: automated
coverage_id: 12-04-D2

### 12. Contract tests mirrored, none dropped (12-04 D3)
expected: Contract tests split to mirror with every assertion re-homed, none dropped.
result: pass
source: automated
coverage_id: 12-04-D3

### 13. Suite + gates green on split tree (12-04 D4)
expected: Full suite and all gates green on the split tree.
result: pass
source: automated
coverage_id: 12-04-D4

### 14. README ships-only (12-05 D1)
expected: README describes only shipped surfaces with working pinned examples.
result: pass
source: automated
coverage_id: 12-05-D1

### 15. Blocking gates wired fork-scoped (12-05 D3)
expected: Blocking CI workflow and pre-commit config wired with fork-only scoping.
result: pass
source: automated
coverage_id: 12-05-D3

### 16. Final tree proven green (12-05 D4)
expected: Final tree proven green: full suite, gates, live rig spots, hygiene.
result: pass
source: automated
coverage_id: 12-05-D4

## Summary

total: 16
passed: 16
issues: 0
pending: 0
skipped: 0

## Gaps

- gap_id: G-12-1
  truth: "AGENTS.md and its convention source contain no stale references (GitHub loop, OKF examples, flat test paths)"
  status: closed-2026-10-16-test-5-retest-pass
  reason: "User reported: AGENTS.md says 'working the full GitHub loop' but the GitHub phase was scrapped (GITHUB-01/02 covered with no phase). Follow-up sweep found more: OKFBundle-family examples (module deleted) and flat tests/test_*.py paths (tests now mirrored) in AGENTS.md + CONVENTIONS.md source."
  severity: minor
  test: 5
  root_cause: "AGENTS.md GSD project block (source:PROJECT.md) is stale — PROJECT.md already says 'no dedicated loop' but the block was generated from an older revision and never re-synced; the 12-05 refresh also missed OKF examples and flat test paths in the conventions block and its CONVENTIONS.md source."
  artifacts: ["AGENTS.md:7 (GitHub loop)", "AGENTS.md:88,92,221 (OKF examples)", "AGENTS.md:85,87,91 (flat test paths)", ".planning/codebase/CONVENTIONS.md:14,19,20,26,30,110,114,118 (same staleness at source)", ".planning/PROJECT.md:5 (correct source for project block)"]
  missing: ["Re-sync AGENTS.md project block from PROJECT.md", "Replace OKF examples + flat test paths in CONVENTIONS.md source and AGENTS.md block with current-tree equivalents"]
