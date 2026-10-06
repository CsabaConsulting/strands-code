# Phase 7: Subagents + /btw Side Channel - Context

**Gathered:** 2026-10-06
**Status:** Ready for planning

## Phase Boundary

Users can fire a side question mid-task via a `/btw` escape; a spawned subagent answers in parallel while the main task continues untouched, and the answer lands as a fenced side block in the transcript. In scope: `/btw` mid-turn carve-out from steering, parallel subagent with full tools on the shared tagged approval gate, fenced delivery with queueing, shared history/memory with the main task. Out of scope: other mid-turn slash commands (still idle-only refusal), fast/cheap side-agent model selection (waits for Phase 8 routing), general multi-agent orchestration beyond one main + one queued side channel.

## Implementation Decisions

### Escape gesture
- **D-01:** `/btw` with no running task degrades to a normal inline turn. No special casing, no refusal — the escape only matters mid-task.
- **D-02:** Only `/btw` escapes steering mid-turn; every other slash keeps the Phase 5 idle-only refusal. Smallest carve-out from D-12 (anything typed is steering).
- **D-03:** Main task and side answer run in parallel; the main task never pauses for `/btw`. — **Reversibility:** costly — parallel turn machinery (concurrent prompt ownership, fenced rendering) shapes the loop; falling back to pause-and-answer re-opens the core design.
- **D-04:** Input stays free while the side answer streams: plain text still steers the main task, another `/btw` queues. Locking input would contradict the parallel design.

### Subagent scope
- **D-05:** The side agent gets full tools (shell, edits, everything), not read-only Q&A. Side work can change files while the main task runs. (Overrode the recommendation — user chose capability.)
- **D-06:** Approvals share the single-HITL gate (no second handler per Phase 3 residual #6); every prompt is tagged `[main]` or `[btw]` so the user knows who's asking.
- **D-07:** Side agent uses the same model as the main task. Fast/cheap selection waits for Phase 8 routing — revisit when MODEL-03 lands.
- **D-08:** Ctrl-C with both running asks which to cancel (main / btw / both), extending the Phase 4 two-press safety-first cancel.

### Result delivery
- **D-09:** Side answers render as a fenced side block (own header/border) while main output flows outside it. Inline interleave was rejected as unreadable; queue-at-end was rejected for hiding the live answer.
- **D-10:** One side answer at a time; further `/btw` questions queue in order. Parallel side agents and replace-latest were both rejected (cost/attention bounds, no silent loss).
- **D-11:** A side answer outliving its main task keeps running and lands when ready, even at the idle prompt. Independent lifecycle, never cut.
- **D-12:** Side-agent failures render as a fenced error block in the same shape. Silent drops were rejected — failures stay visible in history.

### Main-task isolation
- **D-13:** The side agent starts with the shared main-task history. Side questions are usually about the main task; reading history disturbs nothing.
- **D-14:** The side Q&A is appended to the main conversation history so the main agent can reference it. (Overrode the recommendation — user chose continuity over strict isolation.)
- **D-15:** Side-channel spend melts into the session total in `/cost`; no separate btw rows. (Overrode the recommendation — user chose the simpler view.)
- **D-16:** The side agent shares repo memory (same conventions injected, same fact store). One memory across main and side.

### the agent's Discretion
- Fenced block rendering shape (header text, border style, streaming behavior).
- Queue visibility (whether queued btw questions echo on submit).
- Tagged approval prompt layout within the shared gate.
- History-append format for side Q&A (verbatim vs summarized turns).

## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project definition
- `.planning/PROJECT.md` — product vision, core value, constraints (harness-first gaps-only; AWS-optional; deny-first approvals; no keys in repo)
- `.planning/REQUIREMENTS.md` — LOOP-03 (this phase); all other REQ-IDs belong elsewhere
- `.planning/ROADMAP.md` — Phase 7 goal, success criteria, depends on Phase 4

### Prior phases (locked)
- `.planning/phases/04-plan-act-modes-steering/04-CONTEXT.md` — D-11 one-shot asides deferred here; D-12 anything-typed-is-steering (this phase carves out `/btw`); D-13/D-14 two-press cancel (D-08 extends it); finish-then-redirect steering
- `.planning/phases/03-permissions-gate/03-CONTEXT.md` — single-HITL gate spine; deny-first approvals; tagged prompts compose with it
- `.planning/phases/03-permissions-gate/03-SECURITY.md` — residual #6: no second HumanInTheLoop handler (D-06 shares the gate for this reason)
- `.planning/phases/05-model-cost-context-commands/05-CONTEXT.md` — mid-turn slash idle-only refusal (D-02 carves out `/btw` only); transcript-first UX; `/cost` per-task breakdown shape (D-15 deliberately does not extend it)
- `.planning/phases/06-skills-memory-file/06-CONTEXT.md` — session-sticky patterns; curate-by-default memory posture

### Codebase orientation
- `strands_code_cli/loop.py` — `run_loop`, PromptSession ownership, steering reader + boundary check, two-press Ctrl-C; parallel turn machinery and fenced rendering attach here
- `strands_code_cli/router.py` — `dispatch` tri-state; `/btw` branch + mid-turn carve-out from the idle-only refusal
- `strands_code_cli/policy_gate.py` — single-HITL classifier+ask spine; tagged `[main]`/`[btw]` prompts compose here, no second handler
- `strands_code_cli/cost_context.py` — `/cost` breakdown + session totals; btw spend stays in the total per D-15
- `.planning/codebase/ARCHITECTURE.md` — agent/composition vs execution layers (note: maps predate `strands_code_cli/`; CLI orientation above supersedes)

## Existing Code Insights

### Reusable Assets
- Steering reader + boundary check (`strands_code_cli/loop.py`): the mid-turn input path `/btw` carves out of — slash detection happens here, steering redirect stays the default
- `dispatch` tri-state (`strands_code_cli/router.py`): `/btw` routes as a new action kind (side-spawn), alongside reply/agent/exit
- Single-HITL gate (`strands_code_cli/policy_gate.py`): tagged prompts ride the existing classifier+ask spine; `BatchState` turn-cache is the per-turn state precedent for btw queue state
- `print_plain` (`strands_code_cli/output.py`): all fenced side-block rendering routes through markup-off printing (established Phase 6 UAT)
- Harness subagent seam (`strands-harness`): researcher confirms the spawn API — harness-first, no hand-rolled agent threads

### Established Patterns
- Constructor-kwarg configuration, never env sniffing
- Reply-only router actions; prompts and approvals live in the gate/turn layer
- Denials never cover; only approvals silence retries — tagged btw prompts follow the same fail-closed shape
- Session-sticky in-memory state by default; disk persistence only via DiffConfig-shape config when explicitly decided
- Transcript-first UX: everything visible in history, nothing silent (D-12 fenced errors continue this)

### Integration Points
- `loop.py run_loop`: prompt loop + `agent(text)` call site — parallel btw turn, fenced renderer, btw queue, and which-to-cancel Ctrl-C attach here
- `router.py dispatch`: `/btw` branch + USAGE_HINT; mid-turn carve-out from the idle-only refusal
- `main.py build_agent`: subagent construction (same model per D-07) + shared history/memory wiring
- `policy_gate.py`: `[main]`/`[btw]` prompt tags on the shared handler

## Specific Ideas

- Claude Code's Esc-interrupt steering was the Phase 4 reference; `/btw` is explicitly the complement for one-shot asides (Phase 4 D-11).
- No specific visual reference for the fenced block — open to standard approaches (the agent's discretion).

## Deferred Ideas

- Fast/cheap side-agent model selection once Phase 8 routing lands (revisit D-07 when MODEL-03 exists)
- Other mid-turn slash commands (D-02 keeps them idle-only; no demand yet)
- General multi-agent orchestration beyond one main + one queued side channel

---

*Phase: 7-Subagents + /btw Side Channel*
*Context gathered: 2026-10-06*
