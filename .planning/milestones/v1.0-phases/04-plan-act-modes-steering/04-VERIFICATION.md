---
phase: 04-plan-act-modes-steering
verified: 2026-09-26T09:15:39Z
status: passed
score: 4/4 must-haves verified
covered_files:
  - .planning/phases/04-plan-act-modes-steering/04-CONTEXT.md
  - .planning/phases/04-plan-act-modes-steering/04-PLAN-SUMMARY.md
  - .planning/phases/04-plan-act-modes-steering/04-PLAN.md
  - .planning/phases/04-plan-act-modes-steering/04-RESEARCH.md
  - .planning/phases/04-plan-act-modes-steering/04-UAT.md
  - strands_code_agent/code_agent.py
  - strands_code_cli/choice.py
  - strands_code_cli/loop.py
  - strands_code_cli/main.py
  - strands_code_cli/mode.py
  - strands_code_cli/policy_gate.py
  - strands_code_cli/router.py
  - strands_code_cli/steering.py
covered_digest: "v1:sha256:16de9f161b4c79b1ae0d073b24e8001be135c6f0e91f80c861e08408106a62f5"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: passed
  previous_score: 4/4
  gaps_closed: [reply-only-/approve, approval-input-vs-nonblocking-stdin, answer-echo-placement, stdin-flip-parked-reader-terminal-wedge, dialog-asyncio-nesting-deny, deny-batch-cover-fail-open, parked-worker-stdin-wedge, done-without-answer-assert, missing-last-dialog-option]
  gaps_remaining: []
  regressions: []
---

# Phase 4 Verification: Plan/Act Modes + Steering (MODE-01, MODE-02, LOOP-02, LOOP-04)

**Verified:** 2026-09-25 (gsd-verifier, independent read of code, not test descriptions)
**Scope:** 04-PLAN.md must_haves (4 truths, 8 artifacts, 4 key_links, 7 prohibitions) + MODE-01/02, LOOP-02/04

## Truths

### T1 — PASS — Plan mode proposes read-only step list, approve hands to Act (MODE-01, D-01..D-04)
- `strands_code_cli/mode.py:14-25` — `PLAN_PREFIX` renders `Files to touch:` / `Commands to run:` numbered shape, closes with `Reply with revisions in plain words, or /approve to execute.`
- `strands_code_cli/mode.py:34-91` — `ModeState` default `act`, plan|act only, `pending_plan` flag armed via `note_plan_proposed`, cleared on `set()`/`approve()`; `APPROVE_OK`/`APPROVE_EMPTY` copy exact.
- `strands_code_cli/policy_gate.py:220-230` — Plan-deny for `write/edit/shell/python_repl` via `PLAN_DENY_TEMPLATE` (`policy_gate.py:70`), reason `Plan mode is read-only — <tool> skipped, continuing.`
- `strands_code_cli/policy_gate.py:277-282` — ask short-circuits Plan denials to printed refusal + `"n"`, mode vocabulary only.
- `strands_code_cli/loop.py:223-224,236-237` — Plan turns prepend `PLAN_PREFIX`; completed Plan turn arms `pending_plan`.
- `strands_code_cli/router.py:77-78,102-113` — `/approve` is reply-only, gated on `pending_plan`, flips to act.

### T2 — PASS — Session-sticky /mode cycling without restart (MODE-02, D-05..D-08)
- `strands_code_cli/mode.py:45-49` — new `ModeState()` defaults `act` (D-05); `set()` validates plan|act, raises `ValueError` otherwise (no third mode).
- `strands_code_cli/router.py:75-76,87-99` — `/mode` bare reports via `announce()`; `/mode plan|act` switches with transcript announcement; bogus arg returns usage, never an agent turn.
- `strands_code_cli/router.py:18-22` — `USAGE_HINT` gains `/mode [plan|act], /approve`.
- `strands_code_cli/loop.py:189,209,221` — loop owns one `ModeState`, threads into `dispatch` and `set_gate_mode` at start, after every reply, and every turn.
- `strands_code_cli/policy_gate.py:172-180` — `PolicyClassifier.set_mode` validates plan|act; `loop.py:209` re-syncs after `/mode` flips.

### T3 — PASS — Freeform mid-task steering applied at next tool-call boundary, in-flight finishes (LOOP-02, D-09..D-12)
- `strands_code_cli/steering.py:63-121` — `SteeringState` per-turn mailbox (`pending` + one-shot arm set, `bind_turn` reset mirroring BatchState).
- `strands_code_cli/steering.py:144-166` — `make_steering_hook` only sets `event.cancel_tool` to redirect template; never calls `agent()` (no re-entrancy by construction; no `agent(` invocation in module outside docstrings).
- `strands_code_cli/steering.py:204` — registered at `HookOrder.SDK_FIRST` via `register_steering_hook`; `main.py:131` wires it in `build_agent`.
- `strands_code_cli/policy_gate.py:209-216` — steering-armed boundary returns skip-prompt allow above everything, so redirected calls are never approval-prompted.
- `strands_code_cli/policy_gate.py:290-294` — `gate_open` set around blocking `input()`; `steering.py:296-299,334-337` — reader never consumes stdin while open (keystrokes buffered for post-prompt pickup).
- `strands_code_cli/loop.py:222` — reader started before `agent(text)`; `loop.py:233-235` — explicit `stop()` + join per turn, `slot.state = None`.
- `strands_code_cli/steering.py:51` — capture copy `Steering noted — applies at the next step.`; `steering.py:52-55` names the streaming limit.

### T4 — PASS — Two-press Ctrl-C cancel keeps partial work, stays in CLI (LOOP-04, D-13..D-16)
- `strands_code_cli/loop.py:109-114` — `CANCEL_WINDOW_S = 5.0`; first-press/second-press copy matches resolved item 5 exactly.
- `strands_code_cli/loop.py:117-127` — caller-owned `threading.Event` passed as per-invocation `cancel_signal`; never `agent.cancel()` global mutation (no `.cancel()` call in loop.py/steering.py).
- `strands_code_cli/loop.py:130-162` — `_handle_turn_cancel`: press #1 sets event + flush; press #2 in-window confirms (idempotent); lapsed window prints honest still-cancelling copy (no un-cancel promise).
- `strands_code_cli/loop.py:153-154,160-161` — cancel path calls `explicit_save(agent)` + `index.ensure(session_id)` at cancel time.
- `strands_code_cli/loop.py:227-231` — `KeyboardInterrupt` during turn routes to cancel machine and falls through to prompt, mode unchanged; `loop.py:197-198` idle Ctrl-C still line-cancels; gate-prompt Ctrl-C stays deny-this-tool via `policy_gate.py:319-321` broad except.

## Key links — all hold
- K1 single agent + hook registration + mode flag: `main.py:118,126,131-133` — one `interventions`, `bind_main_agent`, steering hook, `set_mode("act")`; `bind_main_agent` invariant preserved (`policy_gate.py:167-170`).
- K2 Plan-deny above trust_delegated, mode vocabulary: `policy_gate.py:217-239` — mode check precedes `trust_delegated` return; `PLAN_DENY_TEMPLATE`/`ask` contain no policy-rule or diff-mode words.
- K3 loop owns lifecycle + caller-owned cancel; raw reader daemon with explicit shutdown, paused while gate open: `loop.py:211-235`, `steering.py:231-350`, `policy_gate.py:53-59,290-294`.
- K4 /mode + /approve reply-only; approval handoff explicit in history: `router.py:75-78`, `loop.py:206-210`.

## Prohibitions (7/7 hold)
- P1 single HITL — PASS: exactly one `HumanInTheLoop(` construction site (`policy_gate.py:347`); `/approve` is a router reply, never a handler.
- P2 vocabulary lock — PASS: Plan copy (`mode.py:14-31`, `policy_gate.py:70,277-282`) uses mode words only; `approve-each`/`on-demand` appear in `mode.py:9` solely to forbid them; no `/diff` terms in Plan denial strings. (`auto` in `mode.py:6` is the D-08 "no general auto mode" exclusion note, not a mode.)
- P3 no scope bleed — PASS: no auto/yolo mode, no `/btw`, no `/model /cost /compact /context /clear /init /memory`, no skills surface in `router.py` (grep clean); `code_agent.py:12-15` touch is a comment only, no second agent.
- P4 no re-entrant `agent()` from steering — PASS: no invocation in `steering.py` (only docstring mentions of the forbidden pattern).
- P5 no in-flight kill — PASS: no `.cancel()`/`terminate` primitive on the path; hook fires before the NEXT call, cancel observed at safe points.
- P6 no scope widening — PASS: no `effective_roots`/scope edits in `loop.py`/`mode.py`/`steering.py`.
- P7 `programmatic_tool_caller` pinned off — PASS: `main.py:113` stays `False`.

## Tests
- Focused: `uv run pytest tests/test_mode.py tests/test_steering.py tests/test_plan_cancel.py tests/test_cli_entry.py tests/test_policy_gate.py tests/test_kill_resume.py -q` → **102 passed**.
- Full: `uv run pytest tests/ -q` → **429 passed, 5 deselected** (pre-existing deselects; warnings only).

## Re-verification (post-verification UAT gaps)

UAT found 3 real gaps after the initial PASS; all fixed with regression tests, full suite 434 green:

1. **`/approve` reply-only (UAT Test 3 FAIL → PASS).** Router returned `("reply", …)` so the mode flipped and the plan died. Now returns `("agent", APPROVE_OK + APPROVE_EXECUTE)`; loop runs the turn with the message payload (`loop.py` `agent_text`). Live-retested: plan executed under the gate. Tests: `test_approve_with_plan_hands_off`, `test_approve_runs_execution_turn_with_prompt`.
2. **Approval `input()` vs nonblocking stdin (UAT Test 3 retry FAIL → PASS).** The steering reader's turn-scoped nonblocking fd broke the gate's blocking `input()` (auto-fail, empty cause). Ask now restores blocking around `input()`; reader re-checks gate-open post-select (steal race closed). Proven by choreographed race test (fails pre-fix, passes post-fix). Tests: `test_gate_set_after_select_never_steals`, `TestBlockingStdinForPrompt` (3).
3. **Answer-echo placement.** `input()`'s prompt arg bypassed the output proxy. Prompt block now prints through one stream; bare `input()` echoes on the `> ` line. Test fakes updated to `lambda *args`.

Truths T1–T4 and all prohibitions re-confirmed unaffected: the fixes narrow the approve handoff and the prompt/reader sharing protocol without touching mode vocabulary, the single-HITL spine, or scope roots.

## Re-verification (dialog/broker delta, 2026-09-26)

Scope: `1c015e2` (arrow-key dialogs, ApprovalBroker main-thread pump, deny-never-covers) re-checked against current line anchors; prior truths stand, changed regions re-anchored:

- T1 — Plan-deny core unchanged, re-anchored: `policy_gate.py:66` (`PLAN_MUTATING_TOOLS`), `:75` (`PLAN_DENY_TEMPLATE`), `:334` (mode check above trust_delegated), `:391-397` (Plan/policy deny short-circuit, now record-only). Mode vocabulary intact.
- T2 — untouched (`mode.py`, `/mode` router paths unmodified by the delta).
- T3 — steering core unchanged; gate coordination extended: `gate_open` set/clear around broker handoff (`policy_gate.py:423,430`), reader checks unchanged (`steering.py:294,306,344`), dialog keystrokes owned at control level (`choice.py`), reader skips while gate open so arrows/Enter never leak into steering. Choice dialog renders to the real terminal, never the output proxy.
- T4 — cancel machine unchanged (`loop._handle_turn_cancel`); invocation now pumped: broker serves prompts on main (`loop.py:150-151` pump + worker pool), worker aborts via `TurnCancelled` (`policy_gate.py` broker), including done-without-answer after dialog Ctrl-C. No parked stdin readers: reader joined per turn (`loop.py:312`), worker joined via pool context.
- P1 single HITL — still exactly one construction site (`policy_gate.py:516`); `ApprovalBroker` is a prompt router, not an intervention.
- P2/P3/P4/P5/P6/P7 — re-grepped clean: vocabulary lock holds, no new commands surface, no re-entrant `agent()`, no kill primitive, `scope.py` untouched, `programmatic_tool_caller` still `False` (`main.py:113`).
- Tests: full suite `460 passed, 5 deselected` on the final tree (new `tests/test_choice.py` headless-dialog incl. all-options-rendered; new `tests/test_broker.py` handoff/cancel/deny-retry).
- Live UAT on the final tree (user-confirmed): session picker lists all sessions + Start-new; approval dialog shows all four options with fail-closed default; Ctrl-C in dialog cancels with no terminal damage and no residue line; deny-retry re-prompts (fail-closed observed end to end).
