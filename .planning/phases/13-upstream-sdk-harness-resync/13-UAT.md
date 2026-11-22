---
status: complete
phase: 13-upstream-sdk-harness-resync
source: [13-01-SUMMARY.md, 13-02-SUMMARY.md, 13-SECURITY.md]
started: 2026-11-21T20:42:00Z
updated: 2026-11-21T21:11:30Z
driver: scripts/uattest/driver.py
scenarios: [u1, u2, u3]
region: us-west-2
---

# Phase 13 User Acceptance Testing (`UPSTREAM-01`)

All three Phase 13 verification smokes are automated in [scenarios_upstream.py](file:///home/csaba/repos/AWS/strands-code/scripts/uattest/scenarios_upstream.py), dispatched via [driver.py](file:///home/csaba/repos/AWS/strands-code/scripts/uattest/driver.py), pinned by [test_uattest_upstream.py](file:///home/csaba/repos/AWS/strands-code/tests/rig/test_uattest_upstream.py), and executed live against AWS Bedrock (`us-west-2`, isolated per-scenario `XDG_CONFIG_HOME` workdirs under `/tmp/uatr8/`).

## Current Test

[testing complete — `U1 PASS`, `U2 PASS`, `U3 PASS`]

## Tests

### 1. Live Bedrock Unary Tool Mode & Llama 4 Notes (`D-03` — `driver.py u1`)
expected:
- Opening and switching to `_NO_STREAMING_TOOLS` (`us.meta.llama4-scout-17b-instruct-v1:0`) configure `streaming=False`, emit `"Note: streaming disabled for <model> (Bedrock unary tool mode)."` without obsolete warnings, and omit the note when switching to `bedrock/us.amazon.nova-2-lite-v1:0`.
- Live Bedrock non-streaming `Converse` tool execution runs `read` end-to-end and returns `LLAMA_UNARY_SENTINEL_13` with zero streaming failures.
result: pass
evidence:
- Initial run with `us.meta.llama4-scout-17b-instruct-v1:0` printed the unary launch note and dispatched Bedrock's unary `Converse` operation (`calling the Converse operation`), where AWS Bedrock returned `ResourceNotFoundException` because all `meta.llama3*`/`meta.llama4*` models in `us-west-2` have `modelLifecycle.status = LEGACY` unless invoked in the last 30 days.
- Reproducible `driver.py u1` (`U1 PASS`, exit `0`) verified:
  1. Launch note and clean `/model` toggle (`nova-2-lite` silent → `llama4-scout` unary note) captured in `/tmp/uatr8/u1-llama.log`.
  2. Live unary `Converse` tool execution on `ACTIVE` `bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0` (via isolated `XDG_CONFIG_HOME` `model-capabilities.yaml` override `streaming_tools: false`): printed launch unary note, executed `[Tool] read` on `/tmp/uatr8/u1/sentinel.txt`, replied `LLAMA_UNARY_SENTINEL_13`, and printed `7.71K (4%) $0.01` / `interface: tool` (`/tmp/uatr8/u1.log`).

### 2. Cross-Family `--session-id` Resume (`#5166`), SDK `model_info` `/context` (`D-02`), & `InjectedBlock` (`D-05` — `driver.py u2`)
expected:
- Sonnet 4.6 boots with `.agent/MEMORY.md` (`InjectedBlock`), `/context` reports the SDK `model_info` `1.00M` window, and Turn 1 computes `391` and flushes on `Ctrl-D`.
- Resuming the same `--session-id` onto `bedrock/us.amazon.nova-2-lite-v1:0` recalls `391` cleanly with zero `ValidationException`, reflects injected/resumed token counts, and reports the `1.00M` window in `/context`.
result: pass
evidence:
- `driver.py u2` (`U2 PASS`, exit `0`):
  - Session 1 (`bedrock/us.anthropic.claude-sonnet-4-6`, `/tmp/uatr8/u2-s1.log`): `/context` reported `0 (0% of 1.00M)`; Turn 1 answered `391` (`161 (0%) $0.00`).
  - Session 2 (`--session-id 246df756-d980-4816-830f-69bae929b85c` on `bedrock/us.amazon.nova-2-lite-v1:0`, `/tmp/uatr8/u2.log`): recalled `391` (`3.83K (0%)`, zero `ValidationException`), and `/context` reported `Context — bedrock/us.amazon.nova-2-lite-v1:0`, `input tokens: 236 (0% of 1.00M)`, `messages: 4`.

### 3. Live `strands-agents==1.65.0` `PolicyHumanInTheLoop`, Policy `[deny]`, & Plan Mode (`driver.py u3`)
expected:
- Interactive `Approve? [main] shell` dialog accepts `Up` + `Enter` (`Proceed`), executing `echo HITL_OK_13`.
- Explicit `[deny]` rule (`uname`) short-circuits without prompting, prints `Denied by policy rule`, and sends `DENIED: DENY:shell command "uname"` back to the model.
- `/mode plan` blocks both `shell` and `write` with `Plan mode is read-only — ... skipped, continuing.` without prompting and leaves `plan_blocked.txt` absent.
result: pass
evidence:
- `driver.py u3` (`U3 PASS`, exit `0`, `bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0`, `/tmp/uatr8/u3.log`):
  - Turn 1 popped `Approve? [main] shell — echo HITL_OK_13`; `Up` + `Enter` approved once and executed `{"output": "HITL_OK_13\n", "exit_code": 0}` (`7.67K (4%) $0.01`).
  - Turn 2 ran `[Tool] shell - command: uname -a`; printed `Denied by policy rule [deny shell command "uname"] — skipped, continuing.` and returned `[Tool Result] Status: error / DENIED: DENY:shell command "uname"` with zero prompts.
  - Turn 3 after `/mode plan` blocked both `[Tool] shell` and `[Tool] write` with `DENIED: Plan mode is read-only — ... skipped, continuing.`, zero approval dialogs, and no `plan_blocked.txt` created.

### 4. Hermetic Suite, Rig Contracts, & CI Gates
expected:
- Contract tests in `tests/rig/test_uattest_upstream.py` and existing suites + CI gates stay green with `strands_code_agent/` untouched (`D-24`).
result: pass
evidence:
- `.venv/bin/pytest tests/rig/ -q`: `37 passed in 0.07s`
- `.venv/bin/ruff check strands_code_cli tests scripts` & `ruff format --check`: `All checks passed!`, `112 files already formatted`
- `.venv/bin/xenon --max-absolute C strands_code_cli tests scripts`: exit `0`
- `.venv/bin/lint-imports`: `Contracts: 1 kept, 0 broken.` (`39 files, 81 dependencies`)
