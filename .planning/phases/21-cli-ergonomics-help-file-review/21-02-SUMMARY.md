---
phase: 21-cli-ergonomics-help-file-review
plan: "02"
subsystem: ui-attachments-completer-loop
tags: [attachments, at-file, slash-file, completer, supports-media, security]
requires:
  - phase: 21-cli-ergonomics-help-file-review
    plan: "01"
    provides: validate_content_blocks and RejectCallerToolUseHook
provides:
  - Gitignore-aware workspace file discovery, /file TTY picker pre-fill, fail-closed @file reader, and post-routing supports_media gate in strands_code_cli/ui/attachments.py
  - Composite SlashCompleter + AtFileCompleter in strands_code_cli/ui/completer.py
  - Loop pre-fill buffering (default=buf), text-only _route_pre_turn isolation, and list[ContentBlock] turn plumbing in loop/core.py & loop/pump.py
affects:
  - 21-03-PLAN.md (disables @file scanning on untrusted /review diffs and builds on extracted _execute_turn_cycle)
tech-stack:
  added: []
  patterns:
    - Reused effective_roots(tool_name="read"), refuse_symlink_under_roots, _is_sensitive_read_path, and PolicyConfig [[deny]] checks fail-closed
    - Extracted _execute_turn_cycle from run_loop keeping run_loop at radon C (17)
key-files:
  created:
    - strands_code_cli/ui/attachments.py
    - tests/ui/test_attachments.py
    - tests/loop/test_loop_attachments.py
  modified:
    - strands_code_cli/ui/completer.py
    - strands_code_cli/dispatch/core.py
    - strands_code_cli/loop/core.py
    - strands_code_cli/loop/pump.py
key-decisions:
  - "D-03: Composite completer fuzzy-completes @<path> mid-line while preserving /slash & /<ns>: completion; /file pre-fills @<relpath> via default=buf."
  - "D-04/D-05: Real-file-only @token resolution injects UTF-8 inline inside <attached_file> and binary images/docs via ImageContent/DocumentContent under 4 MiB / 16 MiB / 8-file bounds."
  - "D-06: supports_media(current_model) evaluates after _route_pre_turn (routing sees ask text only) and aborts cleanly before calling the model on media-less targets."
patterns-established:
  - "_execute_turn_cycle isolates turn execution from run_loop without moving save_model_choice out of the action == 'model' block."
requirements-completed:
  - TOOL-05
duration: 12min
completed: 2026-11-27
---

# Phase 21 Plan 02: `@file` / `/file` & Post-Routing Media Gate Summary

**Gitignore-aware `@file` fuzzy completion, `/file` TTY picker pre-fill, fail-closed `read`-parity attachment resolution, and post-routing `supports_media` gating shipped.**

## Performance

- **Duration:** ~12 min
- **Completed:** 2026-11-27
- **Tasks:** 2 / 2
- **Files modified:** 7

## Accomplishments
- Added [attachments.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/ui/attachments.py) with `git ls-files` + bounded non-git discovery filtered by symlinks, secrets, and `[[deny]]` rules; `/file` `radio_choice` pre-fill (`default=buf`); real-file-only `@token` parsing (`@dataclass`/`@pytest.mark` untouched); fail-closed symlink/`O_NOFOLLOW`/`S_ISREG`/`_is_sensitive_read_path`/`[[deny]]`/`4 MiB`/`16 MiB`/`8`-file bounds; Bedrock-safe `sanitize_document_name()`; and post-routing `supports_media` abort checks.
- Extended [completer.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/ui/completer.py) with `AtFileCompleter` + `merge_completers`, wired `/file` in [dispatch/core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/core.py), and extracted `_execute_turn_cycle` in [loop/core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/core.py) (`run_loop` `CC 17`) so `/route` sees raw ask text only before post-routing attachment construction.

## Deviations from Plan
- Extracted `_execute_turn_cycle` in `loop/core.py` instead of extracting `_handle_model_switch_action` so `test_sole_persist_call_site_is_inside_model_branch` keeps seeing `save_model_choice` within 20 lines of `action == "model"` while `run_loop` drops to `C (17)`.

## Verification
- Targeted Wave 2 suites (`356 passed`), `ruff format --check`, `ruff check`, `xenon --max-absolute C`, `lint-imports` (`1 kept, 0 broken`), and `git diff ee42ea2 -- strands_code_agent/` (empty) all passed after the final edit.
