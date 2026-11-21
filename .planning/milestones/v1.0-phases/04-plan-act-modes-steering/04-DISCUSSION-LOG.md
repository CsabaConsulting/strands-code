# Phase 4: Plan/Act Modes + Steering - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-25
**Phase:** 4-Plan/Act Modes + Steering
**Areas discussed:** Plan mode shape, Mode identity & switching, Steering mechanics, Cancel semantics

---

## Plan mode shape

| Option | Description | Selected |
|--------|-------------|----------|
| Step list + approve | Numbered steps (files, commands); approve/edit/discard | ✓ |
| Freeform proposal | Prose proposal of what it will do | |

| Option | Description | Selected |
|--------|-------------|----------|
| Approve command | `/approve` or `/act`; explicit, logged in history | ✓ |
| y/n prompt | Inline approve/deny like the permission gate | |

| Option | Description | Selected |
|--------|-------------|----------|
| Hard read-only | Mutating tools blocked in Plan mode | ✓ |
| Honor system | Instructed only, not enforced | |

| Option | Description | Selected |
|--------|-------------|----------|
| Freeform revise round | Reply in words; agent re-plans | ✓ |
| Take as-is or discard | Approve or throw away only | |

**User's choice:** Step list, approve command, hard read-only, freeform revise.
**Notes:** All first-round picks, no clarification needed.

---

## Mode identity & switching

| Option | Description | Selected |
|--------|-------------|----------|
| Act by default | Current behavior; Plan opt-in per task | ✓ |
| Plan by default | Every task starts as a proposal | |

| Option | Description | Selected |
|--------|-------------|----------|
| /mode command | `/mode plan` / `/mode act`, announced in transcript | ✓ |
| Natural request | Say 'plan first', model switches itself | |

| Option | Description | Selected |
|--------|-------------|----------|
| Session sticky | Mode persists once set; new sessions default | ✓ |
| Per-task reset | Every ask starts in default mode | |

| Option | Description | Selected |
|--------|-------------|----------|
| plan / act only | No further modes; D-05 auto stays deferred | ✓ |
| Allow auto mode too | Add general auto/yolo now | |

**User's choice:** Act default, /mode command, session sticky, plan/act only.
**Notes:** All first-round picks.

---

## Steering mechanics

| Option | Description | Selected |
|--------|-------------|----------|
| Interrupt at boundary | Typed input redirects at next tool-call boundary | ✓ |
| Queue for next turn | Input waits until turn finishes | |

| Option | Description | Selected |
|--------|-------------|----------|
| Finish then redirect | In-flight call completes; steering from next step | ✓ |
| Kill it immediately | Cancel the running call on the spot | |

| Option | Description | Selected |
|--------|-------------|----------|
| Redirect the plan | Turn continues toward revised goal | ✓ |
| One-shot aside | Answered once, task resumes unchanged | |

| Option | Description | Selected |
|--------|-------------|----------|
| Plain typing | Anything typed mid-run is steering | ✓ |
| Explicit key first | Keypress opens a steering line | |

**User's choice:** Boundary interrupt, finish-then-redirect, redirect-the-plan, plain typing.
**Notes:** All first-round picks.

---

## Cancel semantics

| Option | Description | Selected |
|--------|-------------|----------|
| One press cancels task | Single Ctrl-C stops the task | |
| Two-press confirm | First asks, second confirms | ✓ |

| Option | Description | Selected |
|--------|-------------|----------|
| Keep line-cancel | Idle Ctrl-C still clears the line | ✓ |
| Unify the behavior | Ctrl-C always means cancel-task | |

| Option | Description | Selected |
|--------|-------------|----------|
| Keep partial work | Completed steps stay; remainder dropped | ✓ |
| Roll back the turn | Undo everything the turn did | |

| Option | Description | Selected |
|--------|-------------|----------|
| Stay in CLI, prompt back | Return to REPL in same session | ✓ |
| Offer resume-of-task | Offer to resume dropped remainder later | |

**User's choice:** Two-press cancel (against recommendation — chose safety for long tasks), keep line-cancel, keep partial work, stay in CLI.
**Notes:** Only override of the session: user picked two-press over one-press.

---

## the agent's Discretion

Approve command name, step-list rendering, read-only enforcement mechanism, first-press Ctrl-C UX, boundary-interrupt machinery.

## Deferred Ideas

- General auto/yolo mode (still deferred).
- Resume-of-cancelled-task (rejected for now).
- `/btw` side-channel (Phase 7).
