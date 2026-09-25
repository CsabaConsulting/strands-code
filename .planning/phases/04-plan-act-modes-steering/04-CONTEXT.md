# Phase 4: Plan/Act Modes + Steering - Context

**Gathered:** 2026-09-25
**Status:** Ready for planning

## Phase Boundary

Users get read-only Plan mode with an explicit approve-to-Act handoff, session-sticky mode cycling via `/mode`, true anytime-steering (typed input interrupts at the next tool-call boundary and redirects the turn), and two-press Ctrl-C cancel that keeps partial work and stays in the CLI. In scope: hard-enforced read-only Plan, step-list proposals with freeform revise rounds, `/mode plan|act`, boundary steering with finish-then-redirect, two-press cancel with partial-state survival. Out of scope: general auto/yolo mode (D-05 stays deferred), `/btw` side-channel (Phase 7), one-shot asides, task rollback, resume-of-cancelled-task.

## Implementation Decisions

### Plan mode shape
- **D-01:** Plan mode renders a numbered step list (files to touch, commands to run); the user approves, revises, or discards. Concrete and reviewable over prose.
- **D-02:** Approval hands off via an explicit command (`/approve` or `/act` — planner picks the name). Explicit, discoverable, logged in history — not an inline y/n.
- **D-03:** Plan mode is technically read-only: mutating tools are blocked, not merely discouraged. A plan can never claim writes it already ran. — **Reversibility:** costly — the enforcement mechanism (tool removal vs classifier-deny vs separate agent) shapes the gate integration; changing it later re-opens reviewed gate decisions.
- **D-04:** Plans get freeform revise rounds: reply in plain words, the agent re-plans until approval. No syntax to learn.

### Mode identity & switching
- **D-05:** Sessions start in Act (current behavior preserved); Plan is opt-in per task. Zero friction for quick asks.
- **D-06:** `/mode plan` / `/mode act` switches mid-session, announced in the transcript. Explicit command over model-noticed natural requests.
- **D-07:** Mode is session-sticky once set; new sessions start in the default (Act). Predictable within a conversation.
- **D-08:** Only `plan` and `act` are modes. No general auto/yolo mode in this phase (D-05 from Phase 2 stays deferred); diff modes and policy rules keep their distinct names per the Phase 3 vocabulary lock.

### Steering mechanics
- **D-09:** Typed input mid-task interrupts at the next tool-call boundary and redirects the turn. True anytime-steering, not next-turn queueing. — **Reversibility:** costly — boundary-interrupt needs turn Machinery (input thread + boundary check); falling back to queueing later would re-open the core design.
- **D-10:** The in-flight tool call finishes first; steering applies from the next step. No killed commands, no half-written files.
- **D-11:** Steering redirects the task (skip steps, new direction); the turn continues toward the revised goal. One-shot asides are Phase 7 `/btw` territory, explicitly not here.
- **D-12:** No signal key: anything typed while a task runs is steering. Lowest friction; mistyped input can't be unsent (accepted).

### Cancel semantics
- **D-13:** Two-press Ctrl-C cancels a running task: first press asks/confirms, second confirms. Protects long tasks over one-press speed. (Overrode the recommendation — user chose safety.)
- **D-14:** Idle-prompt Ctrl-C keeps current behavior (clears the line). Run-cancel applies only while a task runs.
- **D-15:** Cancel keeps partial work: completed steps stay (files written, session flushed); only the unfinished remainder is dropped. No rollback journal.
- **D-16:** After cancel, return to the REPL prompt in the same session. Continue, steer, or switch modes freely. No resume-of-task machinery.

### the agent's Discretion
- The approve command name (`/approve` vs `/act`).
- Step-list rendering shape and revise-round agent messaging.
- Read-only enforcement mechanism (tool removal vs classifier-deny vs scoped agent).
- First-press Ctrl-C UX (message text, timeout window for the second press).
- Boundary-interrupt machinery (input thread design, boundary check placement).

## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project definition
- `.planning/PROJECT.md` — product vision, core value, constraints
- `.planning/REQUIREMENTS.md` — MODE-01, MODE-02, LOOP-02, LOOP-04 (this phase); all other REQ-IDs belong elsewhere
- `.planning/ROADMAP.md` — Phase 4 goal, success criteria, dependencies

### Prior phases (locked)
- `.planning/phases/01-session-wiring-repl-skeleton/01-CONTEXT.md` — straight-to-REPL, loop owns PromptSession, Ctrl-C-cancels-line, `output_context` raw stdout, Bedrock-or-stop
- `.planning/phases/02-file-edit-shell-surface-diff/02-CONTEXT.md` — D-04/D-05 diff modes (auto/yolo deferred to mode system), D-06 full shell
- `.planning/phases/03-permissions-gate/03-CONTEXT.md` — single-HITL gate spine (D-01..D-16); Phase 4 builds Plan/Act on it
- `.planning/phases/03-permissions-gate/03-SECURITY.md` — residual #6: no second HumanInTheLoop, no policy/mode vocabulary reuse for Plan/Act, scope widening re-opens D-13

### Codebase orientation
- `.planning/codebase/ARCHITECTURE.md` — agent/composition vs execution layers
- `.planning/codebase/STACK.md` — `strands-agents` 1.57.0, `strands-harness` 0.1.2, `uv` toolchain, pytest gate
- `strands_code_cli/loop.py` — `run_loop`, PromptSession ownership, `agent(text)` inside `output_context`; the turn Machinery steering/cancel plugs into
- `strands_code_cli/router.py` — `dispatch` tri-state; `/mode` and `/approve` route here as reply actions

## Existing Code Insights

### Reusable Assets
- `policy_gate.py` (`strands_code_cli/`): single-HITL classifier+ask+BatchState spine — Plan read-only enforcement composes with it (deny-by-mode), no second handler
- `BatchState` turn-cache with `bind_turn` — the per-turn state pattern steering/cancel state can mirror
- `SessionIndex` sidecar-JSON + session flush on exit — partial-work survival (D-15) rides on existing flush
- `output_context` (`strands_code_cli/output.py`) — all turn output including steering echoes flows through it

### Established Patterns
- Constructor-kwarg configuration, never env sniffing
- Reply-only router actions; prompts and approvals live in the gate/turn layer
- DiffConfig-shape persisted user choice (if mode persistence ever needs disk; default is in-memory session-sticky per D-07)

### Integration Points
- `loop.py run_loop`: prompt loop + `agent(text)` call site — steering input thread, boundary check, and two-press Ctrl-C all attach here
- `router.py dispatch`: `/mode`, `/approve` (name TBD) branches + USAGE_HINT
- `main.py build_agent`: mode-aware tool scoping (Plan = mutating tools removed/denied) + interventions wiring

## Specific Ideas

Claude Code's Plan mode (read-only proposal → approve → execute) and its Esc-interrupt steering are the reference models.

## Deferred Ideas

- General auto/yolo mode (D-05) — still deferred, not in this phase per D-08.
- Resume-of-cancelled-task — rejected for now (stale partial state); revisit if cancel-then-continue proves painful.
- `/btw` side-channel — Phase 7, explicitly distinguished from steering (D-11).

---

*Phase: 4-Plan/Act Modes + Steering*
*Context gathered: 2026-09-25*
