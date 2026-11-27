---
phase: "21"
slug: "cli-ergonomics-help-file-review"
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-11-27"
---

# Phase 21 — Validation Strategy

> Per-phase Nyquist validation contract for feedback sampling during Phase 21 execution (`LOOP-06`, `TOOL-05`, `REVIEW-01`).

---

## Test Infrastructure

| Property | Value |
| :--- | :--- |
| **Framework** | `pytest` (installed in `.venv`) via `/home/csaba/.local/bin/uv run pytest` or `.venv/bin/pytest` |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, `addopts = "-m 'not integration'"`) |
| **Quick run command** | `.venv/bin/pytest tests/dispatch/test_help.py tests/policy/test_tool_use_guard.py tests/ui/test_attachments.py tests/dispatch/test_review.py -rs -q` |
| **Full suite command** | `TERM=xterm-256color GITHUB_ACTIONS=true .venv/bin/pytest tests/ -k "not test_stub_server_systemone_decision_routes" -rs -q` + standalone `test_stub_server_systemone_decision_routes` |
| **Static / complexity gates** | `ruff check`, `ruff format --check`, `xenon --max-absolute C`, `lint-imports`, `uv lock --check`, restricted-module check, empty `git diff ee42ea2 -- strands_code_agent/` |

---

## Sampling Rate

- **After every task commit:** Run the task's targeted verification command (`< 30s`).
- **After every plan wave:** Run wave regression suites + `ruff check` + `ruff format --check` + `xenon --max-absolute C` + `lint-imports`.
- **Before `/gsd-verify-work 21`:** All 6 CI workflow checks + `tests/rig/` + full non-integration suite + standalone loopback stub + `test_no_budgets_or_enforcement.py` must pass cleanly (`strands_code_agent/` diff empty).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Decision / Anchor | Correct / Secure Behavior | Test Type | Automated Command | File Exists | Status |
| :--- | :---: | :---: | :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| `21-01-T1` | 01 | 1 | `LOOP-06` | `D-01`, `D-02` | `dispatch/help.py` single command registry drives both `/help [name]` (built-ins + skills + warnings via `print_plain`/`sanitize_display`) and `dispatch/core.py` `USAGE_HINT`; `BUILTIN_SLASH_HEADS` adds `help`, `file`, `review` with 1:1 parity | unit (TDD Wave 0) | `.venv/bin/pytest tests/dispatch/test_help.py tests/policy/test_diff_gate.py tests/policy/test_codeact.py tests/policy/test_mode.py tests/loop/test_loop_routing.py tests/dispatch/test_router_btw.py tests/memory/test_skills.py tests/memory/test_memory_file.py tests/memory/test_memory_curate.py -rs -q` | ⬜ Wave 0 (`test_help.py`) | ⬜ pending |
| `21-01-T2` | 01 | 1 | `TOOL-05` | `D-06`, `D-07`, `D-08` | `RejectCallerToolUseHook` fails closed on `BeforeInvocationEvent` (`HookOrder.SDK_FIRST`) across all 3 CLI agent factories (`entry/main.py`, `loop/btw.py`, `entry/subagent.py`); `validate_content_blocks` strictly allowlists `text`/`image`/`document`; `model_switch.py` & `cost_context.py` handle `"document"` blocks across switches/stashes/prefix hashes | security + unit (TDD Wave 0) | `.venv/bin/pytest tests/policy/test_tool_use_guard.py tests/model/test_model_switch.py tests/cost/test_cost_context.py tests/loop/test_btw.py tests/entry/test_subagent.py -rs -q` | ⬜ Wave 0 (`test_tool_use_guard.py`) | ⬜ pending |
| `21-02-T1` | 02 | 2 | `TOOL-05` | `D-03`, `D-04`, `D-05`, `D-06` | `ui/attachments.py`: gitignore-aware discovery under `effective_roots`, `/file` TTY picker pre-fill formatting, real-file-only `@token` parsing (`@dataclass`/`@pytest.mark` untouched), fail-closed `read`/`codeact_read` security floor (symlink/`O_NOFOLLOW`, `.env*`/`.ssh`/`.aws`, `[[deny]]`, `4 MiB`/`16 MiB`/`8`-file caps), UTF-8 fenced text vs `ImageContent`/`DocumentContent`, allowlisted `ContentBlock` builder, and post-routing `supports_media` abort gate | unit + security (TDD Wave 0) | `.venv/bin/pytest tests/ui/test_attachments.py -rs -q` | ⬜ Wave 0 (`test_attachments.py`) | ⬜ pending |
| `21-02-T2` | 02 | 2 | `TOOL-05` | `D-03`, `D-06` | `AtFileCompleter` + composite `build_completer(get_words, get_files)`, `/file` `("prefill", "@<relpath> ")` dispatch & `initial_buf` `default=buf` handoff, post-routing `supports_media` check (routing sees raw ask only), multimodal `list[ContentBlock]` across `_invoke_agent` & `_invoke_parallel`, preserving `run_loop <= C (18)` | loop + UI integration (TDD) | `.venv/bin/pytest tests/loop/test_loop_attachments.py tests/ui/test_attachments.py tests/memory/test_skills.py tests/dispatch/test_cli_entry.py tests/loop/test_loop_routing.py tests/loop/test_btw.py tests/loop/test_idle_multiplex.py -rs -q` | ⬜ Wave 0 (`test_loop_attachments.py`) | ⬜ pending |
| `21-03-T1` | 03 | 3 | `REVIEW-01` | `D-09`, `D-10` | `dispatch/review.py`: parses `HEAD` / `--staged` / `<base-ref>` + optional trailing focus, fail-closed ref validation blocking flag/control injection (`git rev-parse --verify --end-of-options`), `shell=False` timeout-bounded git diff collector, empty-diff/non-git short-circuit, `256 KiB` `<untrusted_git_diff>` frame, sanitized `routing_ask` | unit + security (TDD Wave 0) | `.venv/bin/pytest tests/dispatch/test_review.py -rs -q` | ⬜ Wave 0 (`test_review.py`) | ⬜ pending |
| `21-03-T2` | 03 | 3 | `REVIEW-01`, `LOOP-06`, `TOOL-05` | `D-09`, `D-10`, `D-11` + Gates | `/review` wiring in `dispatch/core.py` + `loop/core.py` (turn-scoped `enter_read_only`/`exit_read_only`, `turn_interface="tool"`, sticky `ModeState`/`CodeactState` unchanged, no `PLAN_PREFIX`/`@file`/false `note_plan_proposed`, `ask_text` routing isolation), `docs/QUICKSTART.md`, and complete CI + full suite pass | loop integration + docs + full CI | `/home/csaba/.local/bin/uv lock --check && .venv/bin/ruff format --check strands_code_cli tests scripts && .venv/bin/ruff check strands_code_cli tests scripts && .venv/bin/xenon --max-absolute C --max-modules C --max-average C strands_code_cli tests scripts && .venv/bin/lint-imports && test -z "$(git diff ee42ea2 -- strands_code_agent/)" && .venv/bin/pytest tests/loop/test_loop_review.py tests/dispatch/test_review.py tests/rig/ -rs -q && TERM=xterm-256color GITHUB_ACTIONS=true .venv/bin/pytest tests/ -k "not test_stub_server_systemone_decision_routes" -rs -q` | ⬜ Wave 0 (`test_loop_review.py`) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- `tests/dispatch/test_help.py` — created TDD-first in Plan `21-01` Task 1 (`21-01-T1`) covering `BUILTIN_SLASH_HEADS` 1:1 parity, `USAGE_HINT`, grouped `/help`, `/help <cmd|skill|ns:skill>`, and sanitized warnings.
- `tests/policy/test_tool_use_guard.py` — created TDD-first in Plan `21-01` Task 2 (`21-01-T2`) covering `validate_content_blocks`, `RejectCallerToolUseHook` fail-closed cancellation on real `strands.Agent`, and 3-site registration (`entry/main.py`, `loop/btw.py`, `entry/subagent.py`).
- `tests/ui/test_attachments.py` & `tests/loop/test_loop_attachments.py` — created TDD-first in Plan `21-02` Tasks 1–2 covering gitignore discovery, `/file` pre-fill, real-file-only `@token` parsing, fail-closed FS/policy/size floor, post-routing `supports_media` abort, and `list[ContentBlock]` loop execution.
- `tests/dispatch/test_review.py` & `tests/loop/test_loop_review.py` — created TDD-first in Plan `21-03` Tasks 1–2 covering ref-injection rejection, real git repo diff collection, `256 KiB` `<untrusted_git_diff>` bounds, `/route` isolation, turn-scoped `PolicyGateHandler.enter_read_only`/`exit_read_only`, and `turn_interface = "tool"`.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands
- [x] Sampling continuity: every task verifies cleanly before moving forward
- [x] Wave 0 gaps explicitly mapped (`test_help.py`, `test_tool_use_guard.py`, `test_attachments.py`, `test_loop_attachments.py`, `test_review.py`, `test_loop_review.py`)
- [x] No watch-mode flags
- [x] Fast feedback latency (`< 30s` per targeted verification run)
- [ ] `nyquist_compliant: true` audited post-execution
