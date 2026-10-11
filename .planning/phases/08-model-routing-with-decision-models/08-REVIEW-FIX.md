---
phase: 08-model-routing-with-decision-models
fixed_at: 2026-10-11T08:06:51Z
review_path: /home/csaba/repos/AWS/strands-code/.planning/phases/08-model-routing-with-decision-models/08-REVIEW.md
iteration: 1
findings_in_scope: 7
fixed: 7
skipped: 0
status: all_fixed
---

# Phase 8: Code Review Fix Report

- Phase: 08-model-routing-with-decision-models
- Fixed: 2026-10-11T08:06:51Z (iteration 1)
- Fixer: gsd-code-fixer (generic-agent workaround — typed gsd-code-fixer dispatch unavailable in this runtime)
- Scope: critical_warning (CR + WR findings; IN findings out of scope)
- Verification: all fixes verified in the main checkout (re-read + `ast.parse`; no full suite run between fixes per protocol)

## Summary

- In scope: 7 (1 critical, 6 warnings)
- Fixed: 7
- Skipped: 0
- Info findings (IN-01..IN-07): out of scope, not attempted

## Fixed Issues

### CR-01: `save_strategy` follows a symlinked temp file — arbitrary file overwrite

- Files: `strands_code_cli/routing.py`
- Commit: `07d2a9a` — fix(08): CR-01 refuse symlinked temp file in save_strategy
- Applied fix: `save_strategy` now refuses to write when the temp path is a symlink or already exists (`ValueError: Refusing to write through existing temp file`), matching the module's fail-loud symlink policy; the `Raises` docstring lists the new case. Applied the review's suggested guard verbatim (refuse, not unlink).

### WR-01: Pre-turn hook lets pricing/validation exceptions escape and kill the session

- Files: `strands_code_cli/loop.py`, `strands_code_cli/routing.py`
- Commit: `b87a2c5` — fix(08): WR-01 hold instead of crash in routing hook
- Applied fix: `_route_pre_turn` wraps `decide` (hold with event + hold note on failure), `validate_routed_effort` (gate failure degrades to hold), and `format_routed_line` (note failure logs, switch stands); `_route_side_spawn` wraps `decide` (silent hold with event). Both the hook-level hold and the review's defense-in-depth option were applied: `_candidate_row` degrades price/window lookup failures to `n/a` cells and `route_cost_delta` returns `n/a` on pricing failure. Follows the `cost_context.py` `try/except Exception` precedent and each file's local comment convention.

### WR-02: Composed prompts with untrusted content are sent to the external decision model

- Files: `strands_code_cli/loop.py`
- Commit: `7029e84` — fix(08): WR-02 route on raw typed text, not composed message
- Applied fix: the `run_loop` call site now passes `ask_text=text` (raw typed line) instead of the composed skill/revise/init message, with a comment citing the exfiltration risk. The agent still receives the composed `agent_text`; only the routing decision input changed.

### WR-03: Routed switch discards the streaming-tools advisory reply

- Files: `strands_code_cli/loop.py`
- Commit: `41c2d71` — fix(08): WR-03 surface streaming-tools advisory on routed path
- Applied fix: after a successful routed switch (`resolved_id is not None`), the hook checks `supports_streaming_tools(pick.model)` and prints a yellow warning. Adapted to the in-loop session-start wording ("turns will fail; /model to switch") rather than the longer `apply_model_action` reply text, since the full reply would duplicate the Routed line.

### WR-04: Unknown `engine.primary` values are silently accepted as openrouter

- Files: `strands_code_cli/routing.py`
- Commit: `194e248` — fix(08): WR-04 reject unknown engine.primary at parse and validate
- Applied fix: `_parse_engine` warns and falls back to `"openrouter"` for any primary outside `openrouter|local|off`; `validate_strategy` inspects the raw value and reports `engine: INVALID — unknown primary ...` with a manual-edit fix. Bool primaries (YAML on/off) are exempt from the validate check since the parser honors them intentionally.

### WR-05: Invalid `local_base_url` silently overrides the env chain with the default

- Files: `strands_code_cli/routing.py`
- Commit: `73941d8` — fix(08): WR-05 flag invalid local_base_url in validate
- Applied fix: validate-only fix per the review's second option — `validate_strategy` inspects the raw `local_base_url` and reports `engine: INVALID — local_base_url ... is not an http/https URL` with a manual-edit fix. Parse behavior (invalid → `OLLAMA_DEFAULT_HOST` with warning) intentionally unchanged: existing test `test_non_http_base_url_warns_and_uses_default_host` pins it as the contract, so the fall-through-to-env alternative was rejected.

### WR-06: `/route setup` does not catch `OSError` from the strategy save

- Files: `strands_code_cli/router.py`
- Commit: `0152115` — fix(08): WR-06 catch OSError from strategy save in setup
- Applied fix: the `save_strategy` call in `_route_setup_message` now catches `(ValueError, OSError)`, returning the existing "Setup failed — ... (nothing written)" reply instead of letting the traceback escape `run_loop`.

## Skipped Issues

None. All in-scope findings were fixed and committed. IN-01 through IN-07 were out of scope for this run (`fix_scope: critical_warning`) and were not attempted.

---

*End of Phase 8 code review fix report. Verification ran in the main checkout (workflow.use_worktrees=false — edits and commits made directly, no worktree). REVIEW-FIX.md itself left uncommitted for the orchestrator.*
