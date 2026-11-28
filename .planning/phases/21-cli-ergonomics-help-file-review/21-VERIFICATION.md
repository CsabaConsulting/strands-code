---
phase: 21-cli-ergonomics-help-file-review
verified: "2026-11-28T00:08:00Z"
status: passed
score: 11/11 must-haves verified
overrides_applied: 0
---

# Phase 21: CLI Ergonomics (`/help`, `@file` / `/file`, `/review`) — Verification Report

**Phase Goal:** Ship everyday interactive productivity ergonomics (`/help`, `@file` / `/file` picker, read-only `/review`) in cleanly factored modules within CI cyclomatic complexity bounds.
**Verified:** 2026-11-28T00:08:00Z
**Commits:** Wave 1 `dff1004`, Wave 2 `a721feb`, Wave 3 `fd5dfff`
**Status:** passed

---

## Observable Truths & Requirement Verification

| # | Truth / Decision | Evidence | Status |
| :---: | :--- | :--- | :--- |
| 1 | `LOOP-06` (`D-01`) Single declarative command table in `dispatch/help.py` drives `/help` & `USAGE_HINT`; `BUILTIN_SLASH_HEADS` adds `help`, `file`, `review` | [help.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/help.py), [skills.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/memory/skills.py#L21-L50), [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/core.py#L69), [test_help.py](file:///home/csaba/repos/AWS/strands-code/tests/dispatch/test_help.py) | ✓ VERIFIED |
| 2 | `LOOP-06` (`D-02`) Bare `/help` lists grouped built-ins + loaded skills + sanitized warnings via `print_plain`; `/help <name>` resolves both built-ins and skills | [help.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/help.py), [test_help.py](file:///home/csaba/repos/AWS/strands-code/tests/dispatch/test_help.py) | ✓ VERIFIED |
| 3 | `TOOL-05` (`D-03`) Gitignore-aware `@file` fuzzy completion & `/file` TTY picker pre-fills `@<relpath> ` via `default=buf` while keeping `/` & `/<ns>:` intact | [completer.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/ui/completer.py), [attachments.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/ui/attachments.py), [test_loop_attachments.py](file:///home/csaba/repos/AWS/strands-code/tests/loop/test_loop_attachments.py) | ✓ VERIFIED |
| 4 | `TOOL-05` (`D-04`) Only real existing files resolve (`@dataclass`, `@pytest.mark`, emails untouched); UTF-8 text inlines inside `<attached_file>`, images/docs emit `ImageContent`/`DocumentContent` | [attachments.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/ui/attachments.py), [test_attachments.py](file:///home/csaba/repos/AWS/strands-code/tests/ui/test_attachments.py) | ✓ VERIFIED |
| 5 | `TOOL-05` (`D-05`) Fail-closed `read`/`codeact_read` security floor: `effective_roots(tool_name="read")`, symlink/`O_NOFOLLOW`/regular-file, `.env*`/`.ssh`/`.aws`, `[[deny]]`, `4 MiB`/`16 MiB`/`8`-file caps | [attachments.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/ui/attachments.py), [test_attachments.py](file:///home/csaba/repos/AWS/strands-code/tests/ui/test_attachments.py) | ✓ VERIFIED |
| 6 | `TOOL-05` (`D-06`) `supports_media(current_model)` evaluated AFTER `_route_pre_turn` (routing sees ask text only); media-less model aborts before model call; allowlisted `ContentBlock` dict validation | [loop/core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/core.py#L2732-L2756), [tool_use_guard.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/tool_use_guard.py), [test_loop_attachments.py](file:///home/csaba/repos/AWS/strands-code/tests/loop/test_loop_attachments.py) | ✓ VERIFIED |
| 7 | `TOOL-05` (`D-07`) `model_switch.py` converts `"document"` blocks to placeholders on media-less targets keeping `RichHistory` stashes & `canonical_prefix_hash` stable; `_block_chars` ignores binary bytes | [model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py#L263-L455), [cost_context.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/cost/cost_context.py#L826-L828), [test_model_switch.py](file:///home/csaba/repos/AWS/strands-code/tests/model/test_model_switch.py#L5703-L5743) | ✓ VERIFIED |
| 8 | `TOOL-05` (`D-08`) `RejectCallerToolUseHook` attaches across all 3 agent factories (`entry/main.py`, `loop/btw.py`, `entry/subagent.py`) cancelling caller `"toolUse"` fail-closed on `BeforeInvocationEvent` | [tool_use_guard.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/tool_use_guard.py), [test_tool_use_guard.py](file:///home/csaba/repos/AWS/strands-code/tests/policy/test_tool_use_guard.py) | ✓ VERIFIED |
| 9 | `REVIEW-01` (`D-09`, `D-10`) `/review` validates `HEAD` / `--staged` / `<base-ref>` + focus prompt (`shell=False`, empty-diff short-circuit, `256 KiB` `<untrusted_git_diff>` frame, sanitized `routing_ask`) | [review.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/review.py), [test_review.py](file:///home/csaba/repos/AWS/strands-code/tests/dispatch/test_review.py) | ✓ VERIFIED |
| 10 | `REVIEW-01` (`D-11`) `/review` enforces turn-scoped `PolicyGateHandler.enter_read_only`/`exit_read_only` (`finally:`) + `turn_interface="tool"` without mutating sticky `ModeState`, `pending_plan`, or `CodeactState` | [loop/core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/core.py#L2699-L2708), [test_loop_review.py](file:///home/csaba/repos/AWS/strands-code/tests/loop/test_loop_review.py) | ✓ VERIFIED |
| 11 | Static CI & architecture gates: `run_loop` `C (18)`, `_setup_decision_entries` `B (8)`, `ruff`, `xenon <= C`, `lint-imports` (`1 kept, 0 broken`), `uv lock --check`, restricted-module check, `D-24` pristine `strands_code_agent/` | Verified on `fd5dfff`: `2069 + 1 = 2070` default tests + `44/44` rig contracts | ✓ VERIFIED |

---

## Live Verification Outputs (on `fd5dfff`)

- `/home/csaba/.local/bin/uv lock --check` → `Resolved 142 packages in 2ms`
- `.venv/bin/ruff format --check strands_code_cli tests scripts` → `147 files already formatted`
- `.venv/bin/ruff check strands_code_cli tests scripts` → `All checks passed!`
- `.venv/bin/radon cc -s -n C strands_code_cli/loop/core.py` → `run_loop - C (18)` (ceiling `<= 20`)
- `.venv/bin/xenon --max-absolute C --max-modules C --max-average C strands_code_cli tests scripts` → exit `0`
- `.venv/bin/lint-imports` → `Contracts: 1 kept, 0 broken.`
- `git diff ee42ea2 -- strands_code_agent/` → empty (`D-24` preserved)
- `.venv/bin/pytest tests/rig/ -rs -q` → `44 passed in 0.13s`
- `TERM=xterm-256color GITHUB_ACTIONS=true .venv/bin/pytest tests/ -k "not test_stub_server_systemone_decision_routes" -rs -q` → `2069 passed, 16 deselected`
- `.venv/bin/pytest tests/routing/test_routing.py -k test_stub_server_systemone_decision_routes -rs -q` (`BypassSandbox: true`) → `1 passed`
