# Phase 7: Subagents + /btw Side Channel - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-06
**Phase:** 7-subagents-btw-side-channel
**Areas discussed:** Escape gesture, Subagent scope, Result delivery, Main-task isolation

---

## Escape gesture

**Q1: You type /btw with no task running. What should happen?**

| Option | Description | Selected |
|--------|-------------|----------|
| Answer inline | No special casing: with nothing running, the question just becomes a normal turn. | ✓ |
| Refuse when idle | Refuse with a hint — /btw only exists as a mid-task escape. | |

**User's choice:** Answer inline
**Notes:** None.

**Q2: Mid-task, anything typed is steering (D-12). How wide is the slash carve-out?**

| Option | Description | Selected |
|--------|-------------|----------|
| /btw only | Smallest change: /btw works mid-turn, everything else keeps the idle-only refusal. | ✓ |
| All slashes escape | Any slash command works mid-turn; plain text stays steering. | |

**User's choice:** /btw only
**Notes:** None.

**Q3: While the side answer streams, what does the main task do?**

| Option | Description | Selected |
|--------|-------------|----------|
| Parallel | Matches the phase goal: main task visibly continues while the side answer streams in. | ✓ |
| Pause main task | Main task pauses at the next boundary, resumes after the side answer. Simpler, but the task stops. | |

**User's choice:** Parallel
**Notes:** None.

**Q4: While the side answer streams, can you keep typing?**

| Option | Description | Selected |
|--------|-------------|----------|
| Type freely | Plain text still steers the main task, /btw queues another side question. A parallel design that locks input would be incoherent. | ✓ |
| Lock input | Prompt locks until the side answer lands. Simpler output, but you can't steer mid-flight. | |

**User's choice:** Type freely
**Notes:** None.

---

## Subagent scope

**Q1: What can the side agent touch?**

| Option | Description | Selected |
|--------|-------------|----------|
| Read-only | Read, grep, memory — enough to answer questions, nothing to approve, nothing to break. | |
| Full tools | Shell, edits, everything. Side work can change files while the main task runs. | ✓ |

**User's choice:** Full tools
**Notes:** Overrode the recommendation — user chose capability.

**Q2: The side agent hits an approval-gated action. Who prompts?**

| Option | Description | Selected |
|--------|-------------|----------|
| Shared gate, tagged | One handler (no second HITL per residual #6), but each prompt tagged [main] or [btw] so you know who's asking. | ✓ |
| Auto-deny in btw | Gated actions in btw fail closed; the side answer reports what it couldn't do. Zero interruption. | |

**User's choice:** Shared gate, tagged
**Notes:** None.

**Q3: Which model answers the side question?**

| Option | Description | Selected |
|--------|-------------|----------|
| Fast/cheap | Side Q&A is small; a fast model answers while the main task breathes, and costs less. | |
| Same as main | Same voice, same capability, no model juggling. Costs more per side question. | ✓ |

**User's choice:** Same as main
**Notes:** Fast/cheap selection deferred until Phase 8 model routing lands; revisit then.

**Q4: Ctrl-C while both main task and side answer run. What cancels?**

| Option | Description | Selected |
|--------|-------------|----------|
| Ask which | First press lists what's running; you pick main, btw, or both. Matches the safety-first cancel chosen in Phase 4. | ✓ |
| btw first, then main | First Ctrl-C kills the side answer, main continues. Second Ctrl-C kills main. | |

**User's choice:** Ask which
**Notes:** None.

---

## Result delivery

**Q1: Where does the side answer land in the transcript?**

| Option | Description | Selected |
|--------|-------------|----------|
| Fenced block | Visually fenced side block (own header/border) while main output flows outside it. Scannable, streams stay clean. | ✓ |
| Inline interleave | Side answer lines mix into the main transcript as they arrive. Simplest, messiest. | |
| Queued at end | Side answer held back and printed when the main task ends. Cleanest output, no live side answer. | |

**User's choice:** Fenced block
**Notes:** None.

**Q2: You fire a second /btw while the first still streams. What happens?**

| Option | Description | Selected |
|--------|-------------|----------|
| Queue | One side answer at a time; extras wait their turn. Bounded cost and attention. | ✓ |
| Parallel | Each /btw spawns immediately, all stream in parallel. Maximum concurrency, maximum mess. | |
| Replace latest | A new /btw kills the running side answer and starts over. Latest question wins. | |

**User's choice:** Queue
**Notes:** None.

**Q3: The main task finishes while the side answer still streams. Then what?**

| Option | Description | Selected |
|--------|-------------|----------|
| Lands when ready | The side agent is independent — its fenced answer lands whenever ready, even at the idle prompt. | ✓ |
| Cut with main | Main task end kills any running side answer. Clean lifecycle, lost answers. | |

**User's choice:** Lands when ready
**Notes:** None.

**Q4: The side agent errors out. How do you hear about it?**

| Option | Description | Selected |
|--------|-------------|----------|
| Fenced error | Same fenced shape, error inside. Failures stay visible in history like everything else. | ✓ |
| Silent drop | Failed side answers vanish. Quiet, but you'd never know what happened. | |

**User's choice:** Fenced error
**Notes:** None.

---

## Main-task isolation

**Q1: What does the side agent know when it starts?**

| Option | Description | Selected |
|--------|-------------|----------|
| Shared history | Side questions are usually about the main task ('why did it pick X?'). Reading history disturbs nothing. | ✓ |
| Fresh + question | Only the question travels. Cheapest, purest — but blind to anything you asked before. | |
| Summary + question | A compacted brief instead of full history. Middle ground on cost and context. | |

**User's choice:** Shared history
**Notes:** None.

**Q2: Does the side Q&A enter the main conversation history?**

| Option | Description | Selected |
|--------|-------------|----------|
| Kept out | Main conversation stays exactly as if btw never happened. Relay anything useful via steering. | |
| Appended to main | The side Q&A lands in main history so the main agent can reference it directly. | ✓ |

**User's choice:** Appended to main
**Notes:** Overrode the recommendation — user chose continuity over strict isolation.

**Q3: How does side-channel spend show in /cost?**

| Option | Description | Selected |
|--------|-------------|----------|
| Separate rows | Matches the per-task breakdown shape from Phase 5 — side spend stays visible and auditable. | |
| Session total only | Side spend melts into the session total. Simpler view, no btw visibility. | ✓ |

**User's choice:** Session total only
**Notes:** Overrode the recommendation — user chose the simpler view.

**Q4: Does the side agent share repo memory?**

| Option | Description | Selected |
|--------|-------------|----------|
| Shared memory | Same conventions injected, same fact store. One memory across main and side. | ✓ |
| No memory | Side agent runs without repo memory — pure sidecar, no memory reads or writes. | |

**User's choice:** Shared memory
**Notes:** None.

---

## the agent's Discretion

- Fenced block rendering shape (header text, border style, streaming behavior).
- Queue visibility (whether queued btw questions echo on submit).
- Tagged approval prompt layout within the shared gate.
- History-append format for side Q&A (verbatim vs summarized turns).

## Deferred Ideas

- Fast/cheap side-agent model selection once Phase 8 routing lands (revisit D-07 when MODEL-03 exists)
- Other mid-turn slash commands (stay idle-only; no demand yet)
- General multi-agent orchestration beyond one main + one queued side channel
