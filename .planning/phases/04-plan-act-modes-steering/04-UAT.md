# Phase 4 UAT — Plan/Act Modes + Steering

**Date:** 2026-09-25 (conversational, live CLI, repo cwd)
**Result: 5/5 passed (Test 3 passed after 2 gap fixes), 0 blockers remaining.**

| # | Test | Action | Observed | Verdict |
|---|------|--------|----------|---------|
| 1 | `/mode` switching | `/mode plan`, `/mode act` | `Mode: plan — read-only, proposes steps for /approve.` / `Mode: act — executing with approvals.` | PASS |
| 2 | Plan proposes read-only | Plan-mode ask to create `/tmp/planprobe.txt` | Read-only survey (`read` → FileNotFoundError), numbered Files/Commands step list, nothing mutated, closes with revise-or-`/approve`. | PASS |
| 3 | `/approve` executes | `/approve` after plan | See Gaps below. Final: mode flips AND the write executes under the gate (prompt waited, approved, 9 bytes written, read-back + shell byte-check verified). | PASS after fixes |
| 4 | Steering mid-task | 3× `sleep 5; echo` steps; typed `skip the rest…` during sleep 2 | `Steering noted — applies at the next step.` Third call cancelled with redirect message; agent closed with `steered-done`. Both `always` answers appended narrow standing rules (D-03 live). | PASS |
| 5 | Two-press Ctrl-C | `sleep 30` approved, Ctrl-C during sleep, Ctrl-C again | First press: `Still cancelling — graceful stop already requested; the current step finishes first.` Second press: back at REPL, same session. Ctrl-C at approval prompt = deny-this-tool (documented). | PASS with notes |
| R-A | Regression: shell approve | `echo retest > /tmp/gatetest/rt.txt`, approve `y` | Prompt waited (new `> ` line), ran exit 0. First attempt failed only because `/tmp/gatetest/` was missing (orchestrator's Phase 3 cleanup) — agent recreated via `mkdir -p` and succeeded. Environmental, not a gate defect. | PASS |
| R-B | Regression: shell deny | `echo no > /tmp/gatetest/no.txt`, answer `n` | Prompt on own `> ` line, denied, file absent, agent explained without retry. | PASS |

**Gaps found in UAT (both fixed, committed, regression-tested):**
1. **`/approve` was reply-only** — flipped to act but never ran a turn; the plan died in history. Fix: `/approve` returns an agent turn carrying the execute prompt; loop honors message payloads. Commit `3b164e8`, test `test_approve_runs_execution_turn_with_prompt`.
2. **Approval prompt auto-failed during steered turns** — the Phase 4 reader flips stdin non-blocking for the turn; the gate's blocking `input()` broke on it (`Policy ask failed closed`, empty cause). Fix: ask restores blocking around `input()`; reader re-checks gate-open post-select. Proven by choreographed race test (fails old, passes new). Commit `902440b` area.
3. **Answer echo placement** — `input()`'s prompt arg bypassed the output proxy and rendered lines early. Fix: print block through one stream, bare `input()`. Follow-up: test fakes updated to `lambda *args`. Commits `902440b` + `347d1da`.

**Observations (non-blocking):**
- Agent narration confabulated gate history again (5th–6th instances: "went through ungated", "gate did not fire", "inconsistent per-call") while transcripts show every mutation prompted. Recommend prompt steering for accurate gating self-reports (later phase).
- T5 copy nit: first Ctrl-C of a fresh turn printed "Still cancelling — graceful stop already requested", suggesting the armed state wording (or state) carried over from the pre-approval Ctrl-C. Behavior correct (finish step, second press lands at prompt); wording only.
- T5: Ctrl-C before the approval prompt takes immediate effect (deny path), after approval the step finishes first (D-10). Both as designed.
- Deferred idea recorded: arrow-key choice selection for approval prompts (future UX pass).
- Probe files: `/tmp/planprobe.txt` (9 B) and `/tmp/gatetest/rt.txt` left in place; `/tmp/gatetest/no.txt` and `denied.txt` correctly absent.

**Gap found in retest (fixed, uncommitted at time of writing):**
4. **Ctrl-C at open approval prompt wedged the terminal (input dead, kill required).** Root cause: the steering reader flipped the shared stdin fd nonblocking while the gate toggled it back mid-turn — the reader parked permanently in `os.read` (worker thread, immune to signals) and then ate the next prompt's keystrokes. Fix: the fd mode is never changed anywhere now — select-then-read on a blocking fd needs no flip; the 50 ms poll keeps shutdown prompt. The per-turn SIGINT handler (cancel_event set + chain) from the retest round is kept: it makes press #1 effective when the SDK absorbs KI internally. Tests: `TestFdModeInvariant::test_reader_preserves_blocking_mode`, `TestTurnSigintHandler` (5), choreographed no-steal test retained.
