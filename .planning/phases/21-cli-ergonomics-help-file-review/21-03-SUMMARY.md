---
phase: 21-cli-ergonomics-help-file-review
plan: "03"
subsystem: dispatch-review-loop-docs
tags: [review, read-only, git-diff, turn-interface, quickstart]
requires:
  - phase: 21-cli-ergonomics-help-file-review
    plan: "01"
    provides: BUILTIN_SLASH_HEADS and declarative command registry
  - phase: 21-cli-ergonomics-help-file-review
    plan: "02"
    provides: Extracted _run_routed_attachment_turn seam and @file toggle
provides:
  - Read-only /review diff collector and ref validator in strands_code_cli/dispatch/review.py
  - Turn-scoped PolicyGateHandler.enter_read_only/exit_read_only and forced turn_interface = "tool" isolation in loop/core.py
  - Updated docs/QUICKSTART.md documenting /help, @file / /file, and /review
affects:
  - 22-EVAL-01 (can exercise /help, @file / /file, and /review invariants directly)
tech-stack:
  added: []
  patterns:
    - Ref validation before git diff (--verify --end-of-options ^{commit}, shell=False)
    - <untrusted_git_diff> boundary with sanitized ask_text routing isolation
key-files:
  created:
    - strands_code_cli/dispatch/review.py
    - tests/dispatch/test_review.py
    - tests/loop/test_loop_review.py
  modified:
    - strands_code_cli/dispatch/core.py
    - strands_code_cli/loop/core.py
    - docs/QUICKSTART.md
key-decisions:
  - "D-09: /review collects HEAD, --staged, or validated <base-ref> diffs with optional focus text via shell=False and short-circuits on empty diff or non-git dir."
  - "D-10: Diff bodies truncate cleanly at 256 KiB inside <untrusted_git_diff>; /route receives sanitized command/focus ask_text only."
  - "D-11: PolicyGateHandler.enter_read_only/exit_read_only runs turn-scoped on turn_interface='tool' without mutating sticky ModeState or CodeactState."
patterns-established:
  - "_is_review_turn isolates /review from PLAN_PREFIX, note_plan_proposed(), CodeactStint swap, and @file scanning."
requirements-completed:
  - REVIEW-01
  - LOOP-06
  - TOOL-05
duration: 14min
completed: 2026-11-27
---

# Phase 21 Plan 03: Read-Only `/review`, Docs & Full Verification Summary

**Read-only `/review` with fail-closed `<base-ref>` validation, `256 KiB` `<untrusted_git_diff>` framing, sanitized `/route` `ask_text`, turn-scoped read-only Plan gate, and forced `turn_interface = "tool"` shipped.**

## Performance

- **Duration:** ~14 min
- **Completed:** 2026-11-27
- **Tasks:** 2 / 2
- **Files modified:** 6

## Accomplishments
- Added [review.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/review.py) supporting `/review`, `/review --staged`, `/review <base-ref>`, and optional trailing focus instructions (`--`), rejecting leading-dash/whitespace/control/`..` refs before `git rev-parse --verify --end-of-options <ref>^{commit}`, short-circuiting empty diffs or non-git folders cleanly, and bounding diffs at `256 KiB` inside `<untrusted_git_diff>`.
- Wired `/review` in [dispatch/core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/core.py) and [loop/core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/core.py) (`run_loop` `CC 18`) with turn-scoped `PolicyGateHandler.enter_read_only`/`exit_read_only` (`finally:`), forced `turn_interface = "tool"`, no sticky `ModeState`/`pending_plan`/`CodeactState` mutation, and zero `@file` scanning on diffs.
- Documented `/help`, `@file` / `/file`, and `/review` in [QUICKSTART.md](file:///home/csaba/repos/AWS/strands-code/docs/QUICKSTART.md).

## Deviations from Plan
- Extracted `_run_routed_attachment_turn`, `_is_review_turn`, `_make_skill_words_getter`, `_make_harness_skills_refresher`, `_make_arm_revise`, `_compose_turn_inputs`, `_handle_prefill_or_reply`, and `_finish_model_switch` in `loop/core.py` so `run_loop` remains at `C (18)` while preserving existing `inspect.getsource(run_loop)` assertions in `tests/policy/test_codeact.py` and `tests/memory/test_memory_curate.py`.

## Verification
- `2069 passed` full non-integration suite + `44 passed` rig contracts + `uv lock --check` + `ruff format --check` (`147 files`) + `ruff check` + `xenon --max-absolute C` + `lint-imports` (`1 kept, 0 broken`) + empty `git diff ee42ea2 -- strands_code_agent/`.
