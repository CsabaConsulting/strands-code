---
phase: "04"
slug: "plan-act-modes-steering"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-09-26"
---

# Phase 04 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Plan turn→side effect | Every mutation in Plan mode is denied by the classifier mode flag (above trust_delegated) using mode vocabulary; the prompt prefix instructs read-only as defense-in-depth only | Tool calls / file writes |
| Steering text→turn | Typed mid-task text reaches the model only as a BeforeToolCallEvent cancel_tool redirect message at the next boundary; never as a re-entrant invocation, never as y/n input | Keystrokes / redirect text |
| Gate prompt→approval | While the ask prompt is open the reader buffers keystrokes; steering can never answer y/n; Ctrl-C at a prompt cancels the run via the broker, never denies silently | y/n + rule answers |
| Ctrl-C→turn | First press requests graceful stop via caller-owned event (in-flight step finishes); second press confirms intent; cancel flushes the session so partial work survives | SIGINT / cancel event |
| /approve→mode | Approval is an explicit router reply gated on a pending plan; it flips session-sticky mode to act and is logged in history | Mode flag / plan text |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-04-01 | Tampering | Model jailbreaks Plan prompt prefix to mutate | high | mitigate | Classifier-deny is the enforcement core (`policy_gate.py:334` Plan-deny above all); prefix is defense-in-depth only. Plan-deny tests green (`tests/test_mode.py`). | closed |
| T-04-02 | Tampering | trust_delegated bypasses Plan-deny for subagent turns | high | mitigate | Mode check sits above the trust_delegated early return (`policy_gate.py:331-348`); ordering test pins it. | closed |
| T-04-03 | Tampering | Second HITL added for Plan/Act approval | high | mitigate | Exactly one `HumanInTheLoop` — `policy_gate.py:516` stays the only construction site; /approve is a router reply, never a handler. Single-spine + kwargs tests green. | closed |
| T-04-04 | Tampering | Steering keystrokes leak into gate y/n prompt and approve a mutation | high | mitigate | `gate_open` flag (`policy_gate.py:58,423-430`; reader checks in `steering.py:294,306,344`): reader buffers while any ask prompt is open — typed input and arrow-key dialog alike. Leak tests green. | closed |
| T-04-05 | Tampering | Steering hook re-enters agent() causing ConcurrencyException / turn corruption | medium | mitigate | Hook only sets `cancel_tool`; no invocation from hook or reader thread (`steering.make_steering_hook`). No-reentrancy test green. | closed |
| T-04-06 | Tampering | python_repl admitted as read-only in Plan, writes via interior code | high | mitigate | `python_repl` default-deny in Plan (`PLAN_MUTATING_TOOLS`, `policy_gate.py:66`); read-only set is read+search+GET-fetch only. Deny test green. | closed |
| T-04-07 | Tampering | Cancel/steer kills the in-flight tool → half-written file | medium | mitigate | Finish-then-redirect/stop by construction (hook fires before the NEXT call; cancel observed at safe points via caller-owned event). No kill primitive on the path. | closed |
| T-04-08 | Tampering | Scope widening smuggled in as "Plan needs to read X" | medium | mitigate | No `effective_roots` change in this phase — `scope.py` untouched by the phase commit (`1c015e2` file list). | closed |
| T-04-09 | Spoofing | Stale pending-plan approves the wrong proposal (/approve with no plan) | medium | mitigate | /approve requires a pending plan (`mode.py` pending_plan flag, `APPROVE_EMPTY` guidance); flag cleared on approve and on mode switch. Tests green. | closed |
| T-04-10 | Spoofing | Vocabulary confusion: Plan denial reads as policy rule, or /act misread as approval | low | mitigate | Vocabulary lock: mode words only in Plan copy ("Plan mode is read-only", never the deny-rule wrapper); approve command is /approve, never /act. Reviewed in code. | closed |
| T-04-11 | Repudiation | Approve handoff leaves no trace of what was approved | low | mitigate | /approve is a transcript reply in session history (`APPROVE_OK`, `mode.py:30,92`); step list already in the turn transcript. | closed |
| T-04-12 | Denial of service | Input thread survives the turn and steals stdin from the idle prompt | medium | mitigate | Explicit shutdown + join per turn, never daemon-only (`SteeringReader.stop`); turn-end test asserts no live reader. Phase-added pump worker joined the same way (`ThreadPoolExecutor` context in `loop._invoke_agent`); broker pump exits per turn. See execution notes for the parked-worker variant found and closed. | closed |
| T-04-13 | Denial of service | Cancel without flush loses completed steps on subsequent kill | medium | mitigate | `explicit_save` + `index.ensure` on every cancel path (`loop.py:71,191,198,319`); kill-after-cancel replay test green. | closed |
| T-04-14 | Information disclosure | Steering echo leaks pending y/n answer or secret into transcript | low | accept | Echo only reader-captured lines (buffered-during-prompt lines are applied post-prompt, never the prompt answer itself); documented in `steering.py` docstring. See Accepted Risks Log. | closed |
| T-04-15 | Elevation | programmatic_tool_caller re-enabled, inner calls bypass Plan-deny | high | mitigate | Pin stays off (`main.py:113`); pinned-off test green. Any re-enable must re-prove Plan-deny against inner calls per residual T-03-05. | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| R-04-01 | T-04-14 | Steering echo prints captured lines to the transcript; prompt answers can never be captured (reader gated), so worst case is the user's own steering text appearing verbatim — inherent to the feature, documented. | Phase 04 plan | 2026-09-26 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-09-26 | 15 | 15 | 0 | $gsd-secure-phase 4 (State B, L1 grep-depth; short-circuit, ASVS 1) |

### Execution-discovered issues (found live, closed in-commit `1c015e2`)

These were not in the plan-time register; all are closed and covered by committed tests:

- **Deny-marked-covered fail-open.** Denials marked the batch signature covered, so a model retry of a denied call executed silently in-turn. Fixed: only approvals cover (`BatchState.record` vs `mark`); denials re-prompt. Test: `test_deny_retry_reprompts`.
- **Parked SDK worker steals stdin (double-Ctrl-C wedge).** `ask` ran in the SDK worker thread; SIGINT lands in main, so the worker parked in the stdin read while main unwound — executor shutdown stalled until Enter, and a second press leaked the worker, which ate all later input. Fixed: `ApprovalBroker` serves prompts on the main pump thread; the worker aborts via `TurnCancelled`. Tests: `tests/test_broker.py`.
- **Dialog crash in worker thread.** `asyncio.run` cannot nest in the SDK loop (`run_async was never awaited` → fail-closed deny). Fixed by the same broker routing; dialogs never run off-main.
- **Carried to Phase 5 (not a Phase 4 threat):** `reasoningContent` in resumed opus history fails validation on non-reasoning Bedrock models (observed with `us.openai.gpt-6-luna`). Workaround is a fresh session; durable fix (strip on restore for incompatible model IDs) is a Phase 5 candidate alongside `/model`.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-09-26
