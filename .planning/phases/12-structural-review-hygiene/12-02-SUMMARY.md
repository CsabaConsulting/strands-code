---
plan: 12-02
phase: 12-structural-review-hygiene
status: complete
started: 2026-10-16T06:55:18Z
ended: 2026-10-16T07:33:17Z
duration: 38m
commits: 12
tests_added: 0
tests_passed: 1532 passed, 11 deselected
docs_updated: STATE.md, ROADMAP.md
---

# Plan 12-02 Summary: Repackage door checkpoint + loop-area breakup

**Status:** Complete — `strands_code_cli/loop/` package created via pure moves, dual-future pump split to `loop/pump.py`, all import sites rewritten, and every block in the loop package decomposed to cyclomatic grade C or better (`xenon --max-absolute C` exits 0). Full suite green at every non-move commit (1532 passed, 11 deselected — identical to the 12-01 baseline).

## Checkpoint decision (Task 1) — RECORDED, auto-approved under user lock

**Selected option (verbatim):** "Approve the repackage plus the one-line carve-out"

**Auto-approval rationale (recorded before the first move commit):** the checkpoint carries no `gate` attribute, so per the checkpoints reference the gate is default `blocking` — NOT `blocking-human` — which the protocol marks auto-approvable (front-loaded recommended option). D-05 (full repackage, one-way) was explicitly locked by the user in discuss-phase (12-CONTEXT.md), so the door half re-asks a decided question; the carve-out half follows the researcher's front-loaded recommendation (CF-02). Its implementation lands in 12-03 per the research resolution — **this plan touches no file under `strands_code_agent/`** (verified: zero commits in range touch that path), so no irreversible agent-package action was taken here.

**For 12-03:** implement the recorded choice — amend D-12 with the one-line carve-out and repoint `strands_code_agent/search_tool.py:18` (`from strands_code_cli.scope import confine`) at the new scope package path when scope moves. D-12's ban on all other agent-package coupling stands.

## Task Commits

| Task | Name | Commit | Notes |
|------|------|--------|-------|
| 1 | Repackage door + one-line carve-out | (decision, no code) | Option (a) recorded above before any move commit |
| 2 | Feature-package skeleton + loop-area pure moves | `f335aa7` | `loop.py` → `loop/core.py` (pure move, 100% rename, 0/0) |
| 2 | (move) | `6756bd3` | `steering.py` → `loop/steering.py` (pure move, 0/0) |
| 2 | (move) | `d15ffc7` | `btw.py` → `loop/btw.py` (pure move, 0/0) |
| 2 | (split) | `c49ce57` | Extract `_invoke_parallel` + `_pump_parallel` (verbatim) into `loop/pump.py`; deferred pump edge in `_invoke_agent` |
| 2 | (rewrite) | `4e3ba86` | `loop/__init__.py` skeleton + all import-site rewrites; suite 1532 green; import-linter KEPT |
| 3 | Decompose `_route_pre_turn` | `2aba0e6` | D(25) → B(9) + 4 helpers (all ≤ B(8)); suite green |
| 3 | Pump reap/attach/spawn | `2baf369` | `_pump_parallel` F(46) → E(37); suite green |
| 3 | Pump main-done/service-side | `b12feab` | E(37) → D(29); suite green |
| 3 | Pump interrupt/drain/collect | `1ffc635` | D(29) → B(9), all pump helpers ≤ B(10); suite green |
| 3 | `run_loop` idle phase | `6db3b29` | F(75) → F(62); suite green |
| 3 | `run_loop` turn execution | `966505b` | F(62) → E(39); suite green |
| 3 | `run_loop` cancel/exit/prologue | `c0603c6` | E(39) → C(18); xenon exits 0; suite green |

## Decisions

- **Pump membership (minimal):** `loop/pump.py` owns only the dual-future pump (`_invoke_parallel`, `_pump_parallel`); the cancel trio, `_poll_live`, `_finish_btw_turn`, and `CANCEL_*` stay in core — this kept every existing test import grouped (notably `test_plan_cancel.py`'s chooser patching) and limited test re-homing to two tests.
- **Acyclic package, one deferred edge:** pump imports its core helpers at module level; core reaches back via a single documented function-level import in `_invoke_agent` (precedent: existing lazy imports in the same file). Import order verified both ways; no cycle.
- **No root re-exports (D-09 clean break):** `loop/__init__.py` is docstring + empty `__all__`. Re-exporting `run_loop` would have kept the old `strands_code_cli.loop.run_loop` import string working — a prohibited re-export shim. Missed sites break loudly.
- **Plan-necessitated test re-homings (intent unchanged):** `test_codeact.py` no-swap test getattr homes (pump ×2, core ×1); `test_loop_cancel.py` ack spy repointed to `pump.print_plain` (the moved print site); `test_cost_context.py` file lists extended to `loop/core.py` + `loop/pump.py` (vocabulary + credential-sink scans keep full coverage); `_loop_source()` path readers → `loop/core.py`; `test_repl_history.py` → `loop.core` alias.
- **Review-call pin kept inline:** `test_loop_boundary_wires_sweep_and_review` asserts the exact 16-space-indented `review_memory_queue(` call shape (the suite's only indent pin), so the call plus its try/except stay in `run_loop`; only the sweep and note-print moved out. Likewise the model branch stays inline (20-line `action == "model"` window pin) and the codeact swap/restore lines stay in `run_loop` (getsource pins).
- **Decomposition style:** verbatim code motion into same-module private helpers with explicit params/returns (control flow via `_PUMP_RESUME`/`_PUMP_RAISE` and `_INPUT_LINE`/`_SKIP`/`_EXIT` verdict constants); no logic change, no test-assertion change.

## Deviations (minor, all suite-proven)

- **[Plan tension] Pure-move commits are red by construction:** a commit containing only renames necessarily dangles importers, so "suite green at every commit" cannot hold for M1/M2/S1 (verified each fails only on the expected `ImportError`/`ModuleNotFoundError` — the clean break biting). Green was restored at the rewrite commit and holds for every non-move commit plus all task end states.
- **[Verify-window artifact] Task 2 pure-move grep:** the literal `-8` window returns 0 at plan end because Task 3's 7 same-path commits aged the moves out. The check passed (count 3) at Task 2 completion; the full plan window still shows all three `(pure move, no edits)` commits at 0/0 purity (`f335aa7`, `6756bd3`, `d15ffc7`).
- **Test files touched beyond pure path rewrites (4):** the two re-homings + two file-list extensions above. Required by the plan-mandated split (old patch targets/scan paths cease to exist); no assertion intent changed; full suite green is the proof.

## Issues Encountered

- Two self-inflicted transcription errors during the rewrite (sed double-rewrite of the hand-edited `test_repl_history` import; dropped `session_id` param in `_handle_reply_action`) — both caught immediately by the suite/ruff (F821) and fixed before commit.
- My first `_run_memory_boundary` extraction tripped the 16-space review-call pin; reworked to keep the call inline (see Decisions). Final grade still reaches C(18) with margin to spare (radon reads exactly; no ± risk at 18 vs the 20 limit).

## Test Report

- `uv run pytest tests/ -q`: **1532 passed, 11 deselected** at every non-move commit (R1, route, P1, P2, P3, L-A, L-B, L-C) — identical counts to the 12-01 baseline; zero new tests, 6 test files re-homed.
- `uv run --group dev xenon --max-absolute C strands_code_cli/loop`: exit 0; `radon cc` red-block count (`- [DEF]`) = 0. Worst survivors: `run_loop` C(18), `apply_model_action` C(19, pre-existing, untouched).
- `uv run ruff check` + `ruff format --check` (79 files): clean. `uv run lint-imports`: 1 kept, 0 broken.

## UAT

- `strands_code_cli/loop/` contains `__init__.py`, `core.py`, `pump.py`, `steering.py`, `btw.py` with absolute imports and zero relative-import lines; no other feature packages created; `main.py` unmoved (import lines only).
- Old paths break loudly: `from strands_code_cli.loop import run_loop` → ImportError; `import strands_code_cli.steering` / `strands_code_cli.btw` → ModuleNotFoundError.
- `strands_code_agent/` untouched (0 commits in plan range touch it); carve-out choice recorded above for 12-03.

## Self-Check: PASSED

- [x] All 3 tasks executed (decision recorded; moves + rewrite; decomposition to xenon-clean)
- [x] Each task committed (12 atomic commits; pure moves contain only renames at 0/0)
- [x] SUMMARY.md created (this file)
- [x] STATE.md + ROADMAP.md updated (12-02 marked complete; checkpoint choice + position recorded)
