# Phase 7: Subagents + /btw Side Channel - Research

**Researched:** 2026-10-06
**Domain:** Parallel user-triggered subagent turn inside a single-threaded-pump REPL (Strands SDK + strands-harness)
**Confidence:** HIGH (all load-bearing claims read in-repo or in the locked venv this session)
**Note:** Produced by a generic-agent workaround for `gsd-phase-researcher` (typed GSD dispatch unavailable this session). Section contract and claim-provenance rules from `gsd-phase-researcher.toml` were followed; the `gsd-tools.cjs` research-plan/package-legitimacy seams were unavailable, so no external packages are recommended and no web sources were needed — every finding below is verified against repo or venv source.

## Summary

Phase 7 adds a user-triggered parallel side channel, not model-triggered delegation. That one distinction drives the whole design: the harness already ships a `subagent` delegation tool, but it is model-invoked and runs sequentially inside the parent's turn, so it is the wrong trigger and the wrong concurrency shape for `/btw`. The harness-first spawn recipe is instead the factory-rebuild pattern the harness itself uses for children: build the side agent through `create_harness` with the parent's configuration (same model, same consumer tools, same single `HumanInTheLoop` instance, session forced off), run it on its own worker thread with its own invocation, and fork the parent's history into its first prompt.

The three hard problems are all in the CLI layer, not the SDK: (1) the shared approval gate has per-turn/per-request state (`_last` single slot, `BatchState` coverage, `ApprovalBroker` single cancel) that assumes one running turn and must be made agent-aware; (2) the main-thread broker pump in `_invoke_agent` assumes one future and must serve two workers plus handle side-channel completion mid-turn; (3) a side answer that outlives its main task (D-11) needs approvals and fenced delivery while the idle `PromptSession` owns stdin — the hardest sub-problem, with an async-multiplex recommendation below. Fenced concurrent rendering is feasible without Rich Live: the callback handler renders whole messages (not token streams), so a shared render lock around each message block plus a fencing wrapper handler gives clean `[btw]`-fenced output while main output flows outside.

**Primary recommendation:** Spawn the side agent via a `create_harness` rebuild (same kwargs as `build_agent`, session off, shared HITL instance, no steering hook), run it on a second worker thread under one extended broker pump, tag approvals via `event.agent` identity in the classifier, and fence side output with a render-locked wrapper callback handler.

## User Constraints

> Copied verbatim from `.planning/phases/07-subagents-btw-side-channel/07-CONTEXT.md`. The planner MUST honor these.

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

### Deferred Ideas (out of scope — ignore completely)
- Fast/cheap side-agent model selection once Phase 8 routing lands (revisit D-07 when MODEL-03 exists)
- Other mid-turn slash commands (D-02 keeps them idle-only; no demand yet)
- General multi-agent orchestration beyond one main + one queued side channel

## Project Constraints (from AGENTS.md)

Directives the planner must not contradict (harness-first gaps-only posture is the load-bearing one for this phase):

- **Pad the CLI, don't fork the platform:** Python ≥3.10, `uv` toolchain, Strands SDK + harness. Compose `create_harness`/session/hooks/models/memory; hand-roll only what the harness lacks.
- **AWS-optional, never AWS-required;** `agentcore` stays an optional extra with lazy imports.
- **No upper pins** during the experimental phase; resync upstream deliberately.
- **Constructor-kwarg configuration, never env sniffing** (no `os.environ` reads in library/CLI config paths).
- **No formatter/linter configured** — match surrounding style by hand (4-space, double quotes, `snake_case`, `PascalCase` classes, `UPPER_SNAKE_CASE` constants).
- **Absolute imports** rooted at package top; no relative imports.
- **Rich only for human-facing transcript rendering;** agent-visible output flows through data, not prints.
- **Single-threaded synchronous model** is the repo's prior assumption (CONVENTIONS/ARCHITECTURE predate the CLI's worker-thread turn) — the CLI already broke this with `_invoke_agent`'s worker thread; Phase 7 extends that to two workers, so thread-safety of every shared object must be audited per site (see Pitfalls).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Side-agent construction | Harness (`create_harness` factory rebuild) | CLI `main.py` (kwargs capture) | Same-model/same-tools/same-gate child "built the way the parent was" is exactly the harness delegate recipe |
| History fork into side agent | CLI (replicated fork helper) | Harness `_fork_messages` as the reference algorithm | Harness fork is private API; replicate ~30 lines rather than import private names across packages |
| Parallel turn execution | CLI (`loop.py` pump + worker threads) | SDK (per-instance concurrency guard) | SDK guards one instance, not two instances; the CLI already owns the worker-thread pattern |
| Tagged approvals | CLI (`policy_gate.py` classifier + ask) | SDK HITL (`event.agent` identity) | Tag source is SDK-provided; rendering and state scoping are CLI-owned |
| Fenced rendering | CLI (wrapper callback handler + render lock) | Rich (`Console.print` atomicity) | Message-level callback makes fencing a print-sequencing problem, not a layout problem |
| `/btw` carve-out from steering | CLI (`steering.py` reader + `router.py` dispatch) | — | Both seams already exist; `/btw` becomes a third reader outcome (note / refuse / spawn) |
| Queue + lifecycle (D-10/D-11) | CLI (loop-owned session state) | — | No harness concept of a user-visible side queue; session-sticky holder like `BatchState` precedent |
| History append-back (D-14) | CLI (direct `agent.messages` extend) | — | Main agent's list is the store of record; same in-place discipline as `/clear`/`/compact` |
| Cost merge (D-15) | CLI (`record_turn_metrics` reuse) | — | Appending a btw row to `session_turns` melts into totals with zero `cost_report` changes |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `strands-agents` | 1.57.0 (locked) | Agent runtime: `Agent.__call__`, `ConcurrencyException` per-instance guard, `BeforeToolCallEvent` hooks, HITL intervention events | Already the runtime; parallel shape needs no new SDK feature [VERIFIED: `.venv/.../strands/types/exceptions.py:118-124`] — quote: `"Exception raised when concurrent invocations are attempted on an agent instance."` / `"Agent instances maintain internal state that cannot be safely accessed concurrently."` / `"This exception is raised when an invocation is attempted while another invocation is already in progress on the same agent instance."` |
| `strands-harness` | 0.1.2 (locked) | `create_harness` factory for the side-agent rebuild; `build_default_subagent` builder as the reference recipe; `resolve_memory(..., writable=False)` for the recall-only delegate memory shape | The harness-first spawn path; the delegate builder is the in-house precedent for "child built the way the parent was" [VERIFIED: `.venv/.../strands_harness/tools/subagent.py:687-696`] — quote: `"The ``subagent`` tool the harness wires by default: the ``generalist`` preset and a builder that rebuilds the child through ``build_agent`` (the ``create_harness`` factory...)"` |
| `rich` | 15.0.0 (locked) | Fenced side-block rendering via the existing `Console` + `print_plain` path | Established transcript renderer; `console.print` calls serialize on Rich's internal lock [ASSUMED — lock behavior is Rich-documented, not re-verified this session; the plan still needs the CLI-side render lock for multi-print atomicity regardless] |
| `prompt_toolkit` | 3.x (locked) | `PromptSession` idle input, `StdoutProxy(raw=True)` via `output_context` | Existing I/O spine; no second session needed (side channel never prompts for free text) |

Locked versions confirmed from the installed environment: `strands_agents-1.57.0.dist-info` and `strands_harness-0.1.2.dist-info` present in `.venv/lib/python3.14/site-packages/` [VERIFIED: directory listing read this session].

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| stdlib `threading` + `concurrent.futures` | — | Second worker thread, per-agent cancel events, render lock, side queue | Throughout: the phase is a threading extension of the Phase 4 pattern |
| stdlib `queue` | — | btw question queue (D-10) and main-thread handoff from the steering reader thread | Reader thread must never spawn inline; it enqueues, the pump loop spawns |
| `strands.hooks` (`HookOrder.SDK_FIRST`) | (SDK) | Steering hook stays main-agent-only | Do NOT register the steering hook on the side agent (D-04: plain text steers main only) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `create_harness` rebuild | Harness `subagent` tool (`builtin_tools["subagent"]`) | REJECTED: model-triggered, sequential inside the parent turn — wrong trigger and wrong concurrency for a user-fired parallel channel. Its builder/fork internals are the reference, not the vehicle. |
| `create_harness` rebuild | `strands.multiagent` Swarm/Graph | REJECTED: orchestrated multi-agent runs with their own event loops and result shapes; no interactive-parallel, user-interruptible, shared-terminal concept. Importing it would fork the platform. |
| Shared HITL instance | Second `HumanInTheLoop` on the side agent | REJECTED by D-06 and by the construction name rule (`"strands:human-in-the-loop"` — "never a second instance (name-collision rule)" [VERIFIED: `strands_code_cli/main.py:147-149`]). The SDK itself anticipates instance reuse: "the same handler instance may be reused across agent invocations that each spin up their own event loop, and a threading lock is the only kind that spans them" [VERIFIED: `.venv/.../strands/vended_interventions/hitl/hitl.py:56-61`]. |
| Render lock + fencing wrapper | Rich `Live` split-screen layout | REJECTED: `Live` + `patch_stdout`/`StdoutProxy` + prompt_toolkit dialog ownership fight over the terminal; message-level callbacks make it unnecessary (see Architecture Patterns). |

**Installation:** none. No new packages. All dependencies are in `uv.lock` already.

## Package Legitimacy Audit

Not applicable — this phase installs zero external packages. All work composes `strands-agents`, `strands-harness`, `rich`, and `prompt_toolkit` already pinned in `uv.lock`, plus repo-owned modules. (The `gsd-tools.cjs` legitimacy seam was unavailable in this session; since nothing is installed, no audit is owed.)

## Architecture Patterns

### System Architecture Diagram

```text
                        ┌────────────────────────── main worker thread ──────────────────────────┐
                        │  agent(text) ──► model streams ──► BeforeToolCallEvent                 │
 idle PromptSession     │        │                              │                                │
   (owns stdin)         │        │                         steering hook (main only)              │
        │               │        │                              │                                │
        ▼               │        ▼                              ▼                                │
  ┌───────────┐   turn  │  ┌───────────┐   tool call    ┌────────────────┐   HITL verdict  ┌─────┴─────┐
  │ run_loop  │ ───────►│  │ turn pump │ ──────────────►│ shared Policy  │ ───────────────►│ Approval  │
  │           │  start  │  │  (main    │   needs        │ Classifier     │   Prompt task   │ Broker    │
  │           │  reader │  │  thread)  │   approval?    │ (tags [main]/  │   (tagged,      │ queue     │
  └───────────┘         │  │           │                │  [btw] via     │   namespaced    │ (thread-  │
        ▲               │  │  serves:  │                │  event.agent)  │   batch sig)    │  safe)    │
        │               │  │  • main   │                └────────────────┘                 └─────┬─────┘
   /btw at idle ────────┼──┤  • future │                      ▲                                 │
   = normal turn (D-01) │  │  • btw    │                      │ same HITL instance                │ run_prompt
                        │  │  • future │                      │ on BOTH agents                    │ on main
  ┌───────────┐  /btw   │  │  • broker │                ┌─────┴──────┐                            │ thread
  │ steering  │ ────────┼──┤  • poll   │   tool call    │ side agent │◄──────── spawn ────────────┘
  │ reader    │  spawn  │  │           │ ──────────────►│ (worker 2, │
  │ thread    │  queue  │  │  on btw   │   needs        │  no steer  │
  │ (stdin   │         │  │  done:    │   approval?    │  hook, own │
  │  fd)      │  /btw   │  │  fence +  │                │  cancel    │
  └───────────┘  while  │  │  append   │                │  event)    │
        │      btw busy │  │  history  │                └─────┬──────┘
        │      = queue  │  └───────────┘                      │
        ▼      (D-10)   │                                     │ message blocks
  ┌───────────┐         │  ┌────────────────────────┐         │ under render
  │ btw queue │         │  │ transcript (StdoutProxy│◄────────┘ lock:
  │ (loop-    │         │  │ + render lock): main   │   fenced [btw]
  │  owned)   │         │  │ lines + fenced btw    │   blocks vs
  └───────────┘         │  │ blocks, never torn    │   main flow
                        │  └────────────────────────┘
                        └────────────────────────────────────────────────────────────────────────┘
```

Trace the primary use case: user types `/btw <q>` mid-turn → steering reader classifies it as spawn (not steering, not refusal) → pump loop builds side agent via `create_harness` rebuild with forked history → side agent runs on worker 2 → its tool approvals arrive at the shared broker tagged `[btw]` → its message blocks render fenced under the render lock → on completion the Q&A appends to main history (D-14) and queued `/btw`s start in order (D-10).

### Recommended Project Structure

No new top-level modules required; extend in place (gaps-only):

```text
strands_code_cli/
├── btw.py            # NEW: side-agent build (create_harness rebuild), history fork/append,
│                     #        btw queue holder, fenced callback wrapper  (one home for side-channel logic)
├── loop.py           # EXTEND: dual-future pump, spawn consumption, D-11 idle lifecycle, D-08 chooser
├── steering.py       # EXTEND: /btw carve-out → third reader outcome (spawn), not refusal
├── router.py         # EXTEND: /btw branch (idle → normal inline turn per D-01) + USAGE_HINT
├── policy_gate.py    # EXTEND: agent-aware _last, namespaced batch signatures, per-request cancel
├── main.py           # EXTEND: capture factory kwargs for the rebuild (smallest seam that replays them)
└── output.py         # EXTEND or btw.py: module-level render lock shared by both callback handlers
```

### Pattern 1: Factory-rebuild spawn (the harness-first child recipe)

**What:** Build the side agent by replaying the parent's `create_harness` kwargs with three overrides: session forced off, memory recall-only, and the same interventions list object. This mirrors exactly what the harness delegate builder does.

**When to use:** Every `/btw` spawn (and every queued-btw start).

**Reference — harness delegate builder contract** [VERIFIED: `.venv/.../strands_harness/tools/subagent.py:706-712,718-753`], key quotes:

- `"parent_config holds the parent's create_harness keyword arguments"` with `"session forced off so a throwaway delegate never persists session state"`.
- `"Recall-only manager: the delegate searches shared memory but never writes."`
- `"Consumer tools join the selectable set (same objects, same inherited interventions)"` — i.e. consumer tool objects and the interventions list are shared by reference, not rebuilt.

**Per-axis decisions for the btw rebuild (all locked by CONTEXT, none are choices):**

| Axis | btw value | Locked by |
|------|-----------|-----------|
| model | Parent's model object (same instance) | D-07 |
| tools (consumer) | Same objects (interpreter tool, search, gated write/edit) | D-05 full tools |
| builtin_tools | Same mapping (shell/read on, write/edit off, programmatic_tool_caller off) | D-05 + Risk-9 posture |
| interventions | THE SAME `HumanInTheLoop` instance (not a rebuild) | D-06 + name-collision rule |
| session | `False` (forced off) | Harness delegate recipe; side channel persists via D-14 append-back, never its own session |
| memory | Recall-only share of the parent's stores (`resolve_memory(..., writable=False)` shape) | D-16 (see note below) |
| skills | Same `AgentSkills` plugin instance (harness passes instances through verbatim) | D-16 same-conventions spirit + G-6-R2-6 |
| instructions | `CODE_AGENT_INSTRUCTIONS` + a btw framing line (side-task role, return-a-report shape) | D-13/D-14 continuity |
| hooks | Parent's consumer hooks EXCEPT the steering hook is never registered on the child | D-04 (plain text steers main only) |
| memory injector | Call `register_memory_plugin(btw_agent, load_memory)` (idempotent per agent) | D-16 same conventions injected |

**D-16 memory note:** "same fact store" is satisfied for recall by the harness recall-only shape (search + inject, never extract or write) [VERIFIED: `.venv/.../strands_harness/memory.py:65-70` — read via `resolve_memory` docstring: `"writable ... False builds a recall-only manager ... That is the shape for a subagent delegate, which reads the shared memory without promoting its throwaway subtask into the store."` — observed via bash; treat as CITED]. Writable sharing would let the side task's throwaway reasoning enter curate review (the Phase 6 UAT silent-memory hazard: "can memorialize the model's own rationalizations"). Recommend recall-only; if the planner wants writable, that needs a fresh decision, not an inference from D-16.

**History fork (D-13):** The harness `"all"` context mode is the reference algorithm [VERIFIED: `.venv/.../strands_harness/tools/subagent.py:361-371`], quote: `"The parent's messages for "all" mode — real content blocks (tool calls, results, images), not a text rendering. Tool calls still in flight ... are dropped so the history stays valid, and so are reasoningContent blocks ... The blocks are copies, so nothing the child's SDK does to its history can reach the parent's."` Replicate (do not import — `_fork_messages`/`_with_history` are private): deep-copy parent messages, drop unanswered `toolUse` blocks and all `reasoningContent` blocks, then append the framed btw question as the trailing user turn (absorb into a trailing user message when roles require it, per `_with_history`). Fork is a spawn-time snapshot — the main task keeps running, so later main turns are invisible to the side agent; that is inherent to parallel design (D-03), not a gap.

**History append-back (D-14):** On btw completion, extend `agent.messages` with a user message (the `/btw <q>` text) + assistant message (the side answer; verbatim-vs-summary is the agent's discretion). Do it on the main thread at a turn boundary or under the same discipline as `/clear` (in-place list mutation while no turn runs on main — but main MAY be running when btw lands; planner must serialize against the in-flight main turn: the SDK mutates `messages` during a turn, so append-back must either wait for the main turn boundary or hold an explicit history lock — see Pitfall 4).

### Pattern 2: One pump, two workers, one broker

**What:** Extend `_invoke_agent`'s pump loop from one future to a small future set. The main thread keeps doing the only two things it may do: block in `broker.poll()` and run prompts. Worker threads (main + btw) run `agent(text)` and callback rendering.

Current single-future shape [VERIFIED: `strands_code_cli/loop.py:254-274`]:

```python
broker = _active_broker()
if broker is None:
    ...
with broker.pump(cancel_event):
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(agent, text, **kwargs)
        while True:
            if future.done():
                ...
            req = broker.poll()
            if req is None:
                continue
            req.run_prompt()
```

Dual shape: submit both futures to one pool, loop until the MAIN future is done; when the btw future completes mid-turn, fence its result, append history (serialized — see Pitfall 4), record metrics, and start the next queued btw. `broker.poll()` already multiplexes both workers' prompts because `queue.Queue` is thread-safe and both workers' `ask` paths call `broker.request`.

**Three broker/gate changes this forces (all planner-must):**

1. **Per-request cancel.** `ApprovalBroker.pump(cancel)` holds ONE cancel event and `request()` answers with `self._cancel` [VERIFIED: `strands_code_cli/policy_gate.py:194-214`]. Two workers need two cancel events (D-08 cancels them independently). Change `request()` to take the caller's cancel event (the classifier knows the agent via `event.agent`; stash it in the ask context) and pass it to `wait_answer` (which already takes a per-request `cancel` parameter — the seam exists).
2. **Agent-aware ask context.** `PolicyClassifier._last` is a single slot written at classify time and read at ask time [VERIFIED: `strands_code_cli/policy_gate.py:360-365,380`]. Two concurrent classifiers interleave classify→ask, so key the stash by agent identity (or `toolUseId`), never a bare slot. The tag source is free: `agent = getattr(event, "agent", None)` already read at classify time [VERIFIED: `strands_code_cli/policy_gate.py:346`]; `agent is self._main_agent` → `[main]`, else `[btw]`.
3. **Namespaced batch signatures.** `BatchState` coverage is keyed `(prompt, tool, reason)` with no agent dimension [VERIFIED: `strands_code_cli/policy_gate.py:224-229`], and `bind_turn` resets per MAIN turn. Without namespacing, a main approval would silence the identical btw call and vice versa. Namespace the signature with the agent tag. `bind_turn` timing: btw turns are not main turns — never reset coverage mid-btw-turn; simplest correct shape is namespaced signatures + reset only on main-turn bind.

**D-11 (btw outlives main) — the hardest sub-problem.** When the main turn ends but btw still runs, the loop returns to the idle `PromptSession.prompt("> ")`, which blocks the main thread on stdin. Two things still need the main thread: btw approval prompts (the broker pump) and fenced delivery printing (needs `output_context` active or the prompt line corrupts). Recommended approach (MEDIUM confidence — needs a spike in Wave 0): drive the idle prompt with `prompt_async()` and multiplex it against `broker.poll()` in an `asyncio.wait` FIRST_COMPLETED loop — prompt-toolkit natively supports async prompting, and the broker queue is already poll-based. On prompt completion, handle the line normally (a new main turn re-enters the dual pump with btw still attached); on broker request, run the tagged prompt (the async prompt must be cancelled/suspended while the dialog owns the terminal, then re-issued — prompt_toolkit supports application invalidation/suspend patterns, but the exact dance is the spike). Fallback if the spike fails: btw approvals while main-idle wait until the next main turn starts (bounded wait, announced in the transcript) — degraded but never silent, and D-11's letter (keeps running, lands when ready) still holds for the non-approval path. Do NOT let btw's `ask` run inline on its worker thread at idle: the broker docstring proves prompt_toolkit + `asyncio.run` misbehave there [VERIFIED: `strands_code_cli/policy_gate.py:168-186`].

**D-08 (which-to-cancel chooser).** The turn SIGINT handler currently sets one event [VERIFIED: `strands_code_cli/loop.py:312-340`]. With both running, the first press must ask main/btw/both (radio_choice on the main thread — the handler itself stays side-effect-free per async-signal-safety; the chooser runs in the KeyboardInterrupt path, not the signal handler). Each worker's `wait_answer`/`agent()` observes only its own event after the per-request-cancel change. The two-press safety-first shape (press #1 graceful, press #2 confirm) extends per selected target; exact choreography is planner detail, but the invariant is: never set an event the user didn't name, and Ctrl-C during the chooser itself fails closed (cancel nothing, turn continues — or preserve Phase 4's line-cancel; planner picks, document it).

### Pattern 3: Render-locked fenced callback (D-09 without Rich Live)

**What:** The callback handler renders whole messages via sequential `console.print` calls (role header, body, tool blocks, results) — message-level, not token-streaming [VERIFIED: `strands_code_cli/../strands_code_agent/callback_handler.py:88-134` — `def __call__(self, **kwargs)` iterates `message['content']`, one `console.print` per block]. So "fenced while main flows outside" is a print-sequencing problem: give the btw agent a wrapper handler that prints a fence header, delegates to the shared handler, prints a fence footer — with ALL of it plus every main-handler message block under ONE shared `threading.Lock`.

**Why no Rich Live:** `Live`/split layouts assume they own the screen; here `StdoutProxy(raw=True)` owns stdout, prompt_toolkit dialogs seize the terminal for approvals mid-turn, and the steering reader echoes from a third thread. A `Live` session cannot survive a `radio_choice` dialog opening inside it. The lock makes each message block (main or fenced-btw) atomic in the transcript; blocks interleave at block granularity, never mid-block — which is exactly "fenced side block while main output flows outside it."

**Rules for the wrapper (planner must enforce):**

- Every dynamic-text print routes through `print_plain` (markup off) per the Phase 6 UAT lock [VERIFIED: `strands_code_cli/output.py:34-44`].
- The shared handler instance must be the same object (or share the lock): `DEFAULT_CODE_AGENT_CALLBACK_HANDLER` is currently a module-level singleton shared by all agents [VERIFIED: `strands_code_cli/main.py:153` passes it as `callback_handler`]. Either wrap the singleton with a lock-injecting proxy for BOTH agents, or give each agent a handler holding the same lock. Do not rely on Rich's internal lock alone — it serializes single calls, not header+body+footer sequences.
- Fence shape (header text, border style) is the agent's discretion; recommend `rich.Panel` or rule lines, streaming behavior = per-message blocks as they arrive (live, per D-09's rejection of queue-at-end).
- D-12: exceptions from the btw future render through the same wrapper as a fenced error block (never silent, never raised into the main turn).

### Pattern 4: `/btw` carve-out — third reader outcome + idle dispatch branch

**What:** The steering reader currently maps every mid-turn line to note (steer) or refuse (slash) [VERIFIED: `strands_code_cli/steering.py:65-82,299-311` — `mid_turn_slash_reply` refuses ALL slash heads; `_emit` routes refusal vs `state.note`]. `/btw` becomes a third outcome: spawn-request. And idle `/btw` (D-01) is a plain `router.dispatch` branch returning `("agent", text)`.

**When to use:** Reader side for mid-turn (D-02 carve-out — ONLY `/btw`; every other slash keeps the refusal verbatim); router side for idle.

**Mechanics:**

- `mid_turn_slash_reply("/btw ...")` must return `None`-for-spawn rather than a refusal — cleanest is a dedicated classifier returning an enum (`steer | refuse | btw`) instead of overloading the `str | None` return; keep `mid_turn_slash_reply`'s signature for the other heads (tests pin it).
- The reader thread must NEVER spawn inline: agent construction + `future.submit` happen on the main pump thread. Add an `on_btw` callback (same seam style as `on_line`/`on_refusal` [VERIFIED: `strands_code_cli/steering.py:259-292`]) that enqueues into a `queue.Queue` the pump loop drains each iteration (alongside `broker.poll()`).
- Echo on submit (queue visibility) is the agent's discretion; transcript-first UX says echo something (`> /btw ...` + `Side question noted — answering in parallel.` / `— queued behind the running side answer.`).
- `gate_open` coordination is inherited for free: the reader pauses while ANY approval prompt is open [VERIFIED: `strands_code_cli/steering.py:25-28,333-336`], so a `/btw` typed during a `[btw]` approval prompt is picked up after the prompt closes — never consumed as a y/n answer. No change needed; add a regression test.
- Idle `/btw` (D-01): `dispatch` returns `("agent", <the question text>)` — normal inline turn, no spawn machinery. Also add `/btw` to `USAGE_HINT` and to `BUILTIN_SLASH_HEADS` so skills can't shadow it (Phase 6-01 collision rule: builtin heads always win).

### Anti-Patterns to Avoid

- **Spawning or prompting from the reader thread:** it owns the stdin fd; any blocking call there (agent construction is fine, but `input()`/dialogs/`broker.request`) wedges the terminal. Enqueue, return, let the pump act.
- **Nesting `output_context` from a second thread:** the steering module documents this corruption explicitly ("swapping the global sys.stdout proxy from a second thread would corrupt the turn's active proxy on restore" [VERIFIED: `strands_code_cli/steering.py:33-37`]). The btw worker must print INTO the main turn's already-open proxy (plain prints), never open its own context while the main turn holds one. At idle (D-11, no turn context open), the delivery path needs its own open — exactly one opener at a time; the pump thread is the opener.
- **Sharing one `SteeringState` across main and btw:** states are per-turn by design (`bind_turn` drops pending [VERIFIED: `strands_code_cli/steering.py:99-104`]); btw gets no hook at all.
- **Appending btw Q&A into `agent.messages` from the btw worker thread:** the SDK owns that list during the main turn; append-back is a main-thread, serialized operation (see Pitfall 4).
- **`asyncio.run` in the btw worker for approvals:** same fatal nesting as the main worker — all prompts go through the broker to the main thread.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Child agent construction | Manual `Agent(...)` assembly copying parent fields | `create_harness(**parent_kwargs)` replay (the `build_default_subagent` builder recipe) | Factory owns defaults evolution, tool-name collision checks, plugin wiring; a hand copy rots on every upstream default change |
| History fork | Ad-hoc "last N messages" slice | Replicated `_fork_messages` + `_with_history` algorithm (drop in-flight toolUse, strip reasoningContent, deep-copy, role-alternation frame) | A naive slice produces invalid histories (unanswered toolUse, reasoning blocks a Bedrock model rejects — the known `reasoningContent` resume hazard) |
| Recall-only memory share | Custom read-only store wrapper | `resolve_memory(stores=..., writable=False)` (harness seam) | The harness already defines the delegate memory shape; wrapping stores by hand duplicates its read-only-view logic |
| Approval serialization | Second prompt loop / second broker | The ONE `ApprovalBroker` queue + extended pump | stdin has one owner; the SDK's own stdio ask serializes behind one `threading.Lock` for the same reason |
| Concurrent terminal regions | Rich `Live` layout, curses, alternate-screen panes | Render lock + sequential fenced blocks | Dialogs seize the terminal mid-turn; no layout survives that. Message-level callbacks make the lock sufficient |
| Per-agent cancel | Killing threads / `future.cancel()` on a running worker | Caller-owned `threading.Event` per agent observed at SDK checkpoints (the Phase 4 pattern) | Threads can't be killed; the SDK's `cancel_signal` checkpoints are the only graceful stop |

**Key insight:** Every concurrency primitive this phase needs already exists in-repo (worker thread, broker queue, cancel event, gate_open flag, render path) or in-harness (factory rebuild, fork algorithm, recall-only memory). The phase is an extension problem (one→two workers, one→two cancel domains, untagged→tagged prompts), not an invention problem. The only genuinely new mechanism is the D-11 idle-multiplex pump.

## Common Pitfalls

### Pitfall 1: `_last` race tags the wrong approval

**What goes wrong:** Main classifies (stash=main ctx), btw classifies (stash=btw ctx), main's `ask` runs first and renders btw's tool detail under a `[main]` tag — the user approves the wrong action.
**Why it happens:** Single-slot stash + two concurrent classify→ask pipelines.
**How to avoid:** Key the ask context by agent identity (or `toolUseId`) — planner-must item #2 in Pattern 2. Regression test: interleave two classifications, assert each ask renders its own context.
**Warning signs:** Approval detail lines that don't match the action the agent then takes.

### Pitfall 2: Batch coverage leaks across agents

**What goes wrong:** User approves `shell: pytest` for main; the identical btw call proceeds silently (or a btw denial forces a main re-prompt loop).
**Why it happens:** `BatchState` signatures have no agent dimension and `bind_turn` follows the main turn only.
**How to avoid:** Namespace signatures with the agent tag (planner-must #3). Keep "denials never cover, only approvals silence" per agent.
**Warning signs:** Missing approval prompts during parallel runs; `/policy last` entries that don't name their agent.

### Pitfall 3: Shared mutable tool/hook state across threads

**What goes wrong:** Data races or `ConcurrencyException`-adjacent corruption in objects shared by reference between main and btw agents.
**Why it happens:** The factory-rebuild shares consumer tool objects, the HITL instance, the skills plugin, and the callback handler across two threads running two event loops.
**How to avoid:** Audit each shared object: HITL instance reuse is SDK-anticipated (threading-lock discipline); `AgentSkills` plugin instances are shared with children by harness design ("Plugin instances are shared with children, so one that keeps per-agent state must keep it in agent.state, not on self" — harness `agent.py` docstring, observed via bash, CITED); the gated write/edit tools share a `PendingStore` + `bind_session` — verify `PendingStore` is thread-safe or serialize diff-gate access with a lock (Wave 0 spike if unclear); the callback handler must be stateless across calls or lock-guarded (it holds only config + a Console — verify no per-message mutable fields).
**Warning signs:** Flaky parallel-run tests; diff-store entries attributed to the wrong agent.

### Pitfall 4: History torn by concurrent mutation

**What goes wrong:** btw completion appends Q&A to `agent.messages` while the main turn's SDK event loop is mid-mutation → torn list, duplicated roles, or lost tool results.
**Why it happens:** `agent.messages` is a plain list mutated in place by the SDK during a turn; D-14 append-back lands whenever btw finishes, including mid-main-turn.
**How to avoid:** Serialize append-back on the main thread AND against main-turn activity: simplest correct shape is to hold completed btw Q&A in a pending slot and flush it at the next main-turn boundary (end of `_invoke_agent` pump, before `maybe_auto_compact`). If live-append is wanted, it needs an explicit history lock held by both the append path and every in-place mutation site (`/clear`, `/compact`, model-switch convert) — heavier; recommend boundary-flush.
**Warning signs:** Role-order SDK validation errors after parallel runs; missing tool results in resumed sessions.

### Pitfall 5: `trust_delegated=true` silently un-gates btw

**What goes wrong:** A user who enabled `trust_delegated` (D-12: skip prompts inside delegated turns) gets ZERO btw approval prompts — btw tools run unapproved.
**Why it happens:** The classifier early-returns `delegated-trusted` for any agent that `is not self._main_agent` [VERIFIED: `strands_code_cli/policy_gate.py:346-353`], and the btw agent is never the main agent. Default is `False` [VERIFIED: `strands_code_cli/policy.py:129-133`], so this bites only opt-in users — but for them it contradicts D-06's "every prompt is tagged" expectation silently.
**How to avoid:** Decide in planning: either btw counts as delegated (document that `trust_delegated` covers it — coherent: it IS a delegate) or btw is excluded from the early-return (tag + prompt always). Recommend documenting-as-delegated (simplest, matches the name) + a transcript note when a btw call is auto-trusted so it never looks silent.
**Warning signs:** UAT "btw edited files without asking" on a trust_delegated-enabled config.

### Pitfall 6: Idle-time delivery corrupts the prompt line

**What goes wrong:** btw finishes at the idle prompt; the fenced block prints while `PromptSession` is mid-render → garbled input line, lost keystrokes.
**Why it happens:** No `output_context` is open at idle, and prompt_toolkit owns the cursor.
**How to avoid:** Part of the D-11 spike: deliver via `patch_stdout`-wrapped print (open `output_context` around the delivery on the pump thread) or defer delivery to the next input boundary. Verify with a live idle-delivery test, not just unit tests.
**Warning signs:** UAT reports of scrambled `> ` lines when a side answer lands.

### Pitfall 7: Nested `broker.pump` clobbers the cancel domain

**What goes wrong:** Calling the existing `_invoke_agent` twice (once per agent) nests `pump()` contexts; the inner `finally` restores the outer cancel and ident while the inner worker still runs → approvals answered against the wrong cancel event, `TurnCancelled` misfires.
**Why it happens:** `pump()` save/restore assumes nesting on ONE thread [VERIFIED: `strands_code_cli/policy_gate.py:194-206`], not two concurrent pumps.
**How to avoid:** Exactly ONE pump for the whole parallel episode, owned by the main thread, spanning both workers; per-request cancel (Pattern 2 #1) replaces the single pump cancel. Never call `_invoke_agent` recursively for btw.
**Warning signs:** Cancelling main also kills btw (or vice versa); approvals hanging after a cancel.

## Code Examples

Verified patterns from repo/venv sources read this session:

### Dual-future pump sketch (extends `_invoke_agent`)

```python
# Source: extends strands_code_cli/loop.py:254-274 (single-future pump, VERIFIED above)
# One pool, one pump, main thread serves broker + btw lifecycle.
with broker.pump():  # pump WITHOUT single cancel after per-request-cancel change
    with ThreadPoolExecutor(max_workers=2) as pool:
        main_future = pool.submit(agent, main_text, **main_kwargs)
        btw_future = pool.submit(btw_agent, btw_prompt) if btw_agent else None
        while not main_future.done():
            if btw_future is not None and btw_future.done():
                btw_future = drain_btw_result(btw_future, btw_queue)  # fence, metrics, start next queued
            req = broker.poll()
            if req is None:
                continue
            req.run_prompt()
        # main done; btw may still run -> D-11 idle-multiplex takes over the pump
```

### Agent-aware classifier tag (extends `PolicyClassifier.__call__`)

```python
# Source: strands_code_cli/policy_gate.py:346-353 (event.agent read, VERIFIED above)
agent = getattr(event, "agent", None)
tag = "main" if (agent is None or agent is self._main_agent) else "btw"
# ... stash under key including agent identity, NOT the bare self._last slot:
self._last_by_agent[agent_key(agent)] = {..., "tag": tag}
# ask() renders f"[{tag}] Approval needed: {tool_name}" (exact layout: the agent's discretion)
```

### Fenced wrapper callback (extends the singleton handler)

```python
# Source: strands_code_agent/callback_handler.py:88-104 (message-level __call__, VERIFIED above)
_render_lock = threading.Lock()  # ONE lock, shared by main + btw handlers

class FencedBtwHandler:
    def __init__(self, inner): self._inner = inner  # the shared CodeAgentCallbackHandler
    def __call__(self, **kwargs):
        with _render_lock:
            print_plain(console, "┌─ btw: <question short> ──")
            self._inner(**kwargs)   # body renders inside the fence, atomically
            print_plain(console, "└─ end btw ──")
# Main-turn prints wrap each message block in the same _render_lock.
```

### Idle `/btw` dispatch (D-01)

```python
# Source: extends strands_code_cli/router.py dispatch() tri-state (VERIFIED: router.py:102-222)
# In dispatch(), alongside the other slash branches:
if cmd == "/btw":
    if not rest:
        return ("reply", "Usage: /btw <side question>")
    return ("agent", rest)  # no running task at idle -> normal inline turn
```

### Mid-turn `/btw` reader outcome (D-02 carve-out)

```python
# Source: extends strands_code_cli/steering.py:299-311 (_emit refuse/note split, VERIFIED above)
def _emit(line: str) -> None:
    if is_btw_line(line):                       # "/btw ..." (case-insensitive head)
        btw_queue.put(line.strip()[4:].strip()) # enqueue; NEVER spawn on the reader thread
        emit_btw_noted(line.strip())            # transcript echo (visibility: the agent's discretion)
        return
    refusal = mid_turn_slash_reply(line)        # unchanged for every other slash head
    ...
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Harness without delegation | `subagent` builtin tool + `make_subagent` custom roles + `AgentSpec`/`Preset` config axes | strands-harness 0.1.x (locked 0.1.2) | Spawn vocabulary (builder, fork, recall-only memory) exists to mirror — but the tool itself is model-triggered, so Phase 7 mirrors the recipe, not the tool |
| CLI single worker + single cancel | CLI dual worker + per-agent cancel domains | This phase | Broker/gate state must become agent-aware (Pattern 2) |
| Slash mid-turn = always refuse | `/btw` = third reader outcome | This phase | Smallest carve-out from D-12; refusal text for other heads stays byte-identical |
| `agent.messages` mutated only at boundaries | btw append-back lands mid-main-turn | This phase | Boundary-flush serialization (Pitfall 4) |

**Deprecated/outdated:**
- Importing harness privates (`_fork_messages`, `_with_history`, `_SubagentTool`) across the package boundary: fragile against the "no upper pins / resync deliberately" posture — replicate the ~30-line algorithm with a version-pinned comment instead.
- Rich `Live` for concurrency: wrong tool under prompt_toolkit dialog ownership (see Alternatives Considered).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Rich `Console.print` serializes single calls on an internal lock (multi-print sequences still need the CLI render lock) | Standard Stack, Pattern 3 | LOW: the render lock makes this belt-and-braces; worst case is redundant locking |
| A2 | `prompt_async()` + `asyncio.wait` FIRST_COMPLETED can multiplex the idle prompt against `broker.poll()` (D-11 spike) | Pattern 2 | MEDIUM: if the spike fails, fallback is bounded-wait approvals (documented) — D-11 letter survives, approval latency degrades |
| A3 | `PendingStore` + gated write/edit tools are safe (or cheaply made safe) for concurrent use by two agents | Pitfall 3 | MEDIUM: if the store has per-turn mutable state, btw edits need a lock or a second store; Wave 0 spike |
| A4 | Two `Agent` instances in two threads, each running `asyncio.run` in its own worker, don't contend on SDK-global state (telemetry, registry) | Pattern 2 | LOW-MEDIUM: SDK background-tasks machinery already runs concurrent tool execution; breakage would show in the first live parallel test |
| A5 | `radio_choice` dialogs from the main thread remain safe while a second worker streams callback output (render lock held across dialog + prints) | Pattern 2/3 | LOW: same shape as today's worker-streaming + main-dialog; lock extends it |

## Open Questions

1. **D-11 idle-multiplex exact mechanics**
   - What we know: `PromptSession.prompt()` blocks; broker needs main-thread polling; delivery needs `output_context`. `prompt_async` exists in prompt_toolkit 3.x [ASSUMED — standard API, not verified against the locked version this session].
   - What's unclear: suspend/resume dance for the async prompt when a tagged approval dialog must seize the terminal; cursor behavior on fenced delivery.
   - Recommendation: Wave 0 spike (live terminal test, not unit): async prompt + broker poll + forced btw approval + idle delivery. Timebox; fallback documented in Pattern 2.

2. **History append-back timing (D-14)**
   - What we know: boundary-flush is simplest-correct; live-append needs a history lock across all mutation sites.
   - What's unclear: whether UAT will accept the answer appearing in history only at the main-turn boundary (transcript shows it immediately either way).
   - Recommendation: implement boundary-flush; note as a demo checkpoint in UAT, not a pre-decision.

3. **Queue-depth bound**
   - What we know: D-10 says queue in order, unbounded in principle.
   - What's unclear: whether an unbounded in-memory `queue.Queue` needs a cap (attention/cost bound spirit of D-10's rejection of parallel side agents).
   - Recommendation: unbounded `queue.Queue` (no silent loss per D-10) + echo depth on submit; revisit only on demand. the agent's discretion covers the echo.

4. **`trust_delegated` coverage of btw**
   - What we know: default False → btw prompts normally; True → btw fully un-gated via the existing early-return.
   - What's unclear: which the user expects (D-06 says "every prompt is tagged" — under trust, there are no prompts to tag).
   - Recommendation: document-as-delegated + transcript note on auto-trust (Pitfall 5). No code branch needed.

## Environment Availability

This phase has no new external dependencies (code + locked-deps only). Relevant environment facts:

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python + uv + pytest | All work, validation | ✓ | Python 3.14.7 observed dev interpreter; pytest 9.1.1 locked | — |
| strands-agents / strands-harness | Spawn recipe, fork reference | ✓ (venv) | 1.57.0 / 0.1.2 | — |
| Live Bedrock model | Parallel-run verification (worker threads, approvals, rendering) | Runtime-dependent | — | Unit tests with doubles for logic; mark live parallel test `integration` (deselected by default per `pyproject.toml` [VERIFIED: `pyproject.toml:63-67`]) |
| Interactive terminal | D-11 spike, Ctrl-C chooser, fence visuals | Developer machine | — | None — these are inherently live; plan explicit manual checks |

**Missing dependencies with no fallback:** none blocking; live-model + live-terminal checks gate UAT, not planning.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 (locked) |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`, `addopts = "-m 'not integration'"`) |
| Quick run command | `uv run pytest tests/test_btw.py tests/test_steering.py tests/test_policy_gate.py tests/test_broker.py -x -q` |
| Full suite command | `uv run pytest -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LOOP-03 | Idle `/btw <q>` runs a normal inline turn (D-01) | unit | `pytest tests/test_router_btw.py -x` (dispatch returns `("agent", rest)`) | ❌ Wave 0 |
| LOOP-03 | Mid-turn `/btw` spawns; other slashes still refused (D-02) | unit | `pytest tests/test_steering.py::...btw... -x` (third reader outcome; refusal text unchanged) | ❌ Wave 0 (extend existing file) |
| LOOP-03 | Main never pauses for btw; input free; second btw queues (D-03/D-04/D-10) | unit (doubles) + integration (live) | `pytest tests/test_btw.py -x` + live parallel marker test | ❌ Wave 0 |
| LOOP-03 | Tagged `[main]`/`[btw]` prompts; no second HITL (D-06) | unit | `pytest tests/test_policy_gate.py -x` (agent-keyed context, namespaced batch, single construction) | ❌ Wave 0 (extend existing file) |
| LOOP-03 | Fenced btw block incl. error shape; no torn interleavings (D-09/D-12) | unit (lock/ordering) | `pytest tests/test_btw.py -x` (wrapper + render-lock tests) | ❌ Wave 0 |
| LOOP-03 | btw outlives main, lands at idle (D-11) | live spike + manual | integration-marked + terminal checklist | ❌ Wave 0 |
| LOOP-03 | History fork at spawn; Q&A appended back (D-13/D-14) | unit | `pytest tests/test_btw.py -x` (fork purity: no reasoningContent, no dangling toolUse; append-back shape) | ❌ Wave 0 |
| LOOP-03 | Spend in session total, no btw rows (D-15) | unit | `pytest tests/test_cost_context.py -x` (`record_turn_metrics` reuse) | ❌ Wave 0 (extend existing file) |
| LOOP-03 | Ctrl-C chooser main/btw/both (D-08) | unit (state machine) + manual | `pytest tests/test_plan_cancel.py -x` style + terminal checklist | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_btw.py tests/test_steering.py tests/test_policy_gate.py -x -q`
- **Per wave merge:** `uv run pytest -q` (full suite green)
- **Phase gate:** Full suite green + live parallel smoke (main + btw + one approval each) before `$gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_btw.py` — NEW: spawn/queue/lifecycle/fork/append/fence unit tests (covers LOOP-03 core)
- [ ] `tests/test_router_btw.py` — NEW (or fold into existing router tests if present): idle `/btw` dispatch + USAGE_HINT + BUILTIN_SLASH_HEADS membership
- [ ] Extend `tests/test_steering.py` — third reader outcome + gate_open regression (btw typed during open prompt)
- [ ] Extend `tests/test_policy_gate.py` + `tests/test_broker.py` — agent-keyed ask context, namespaced batch, per-request cancel, single-HITL-construction assertion
- [ ] Extend `tests/test_cost_context.py` — btw row melts into totals
- [ ] D-11 async-multiplex spike — live terminal spike before planning locks the idle design
- [ ] Framework install: none (`uv sync` reproduces `.venv`)

## Security Domain

(`security_enforcement` is enabled in `.planning/config.json`; ASVS Level 1.)

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | — (no new auth surface; model credentials unchanged) |
| V3 Session Management | Partial | Side agent built with `session: False` — it must never persist or resume session state; verify no session files written for btw turns |
| V4 Access Control | Yes | SAME deny-first TOML gate for btw (D-05 full tools + D-06 shared gate); namespaced batch must not weaken fail-closed (denials never cover, per agent) |
| V5 Input Validation | Yes | `/btw` line parsing (empty question → usage, not an empty spawn); queued-question handling; history fork/append role-shape validation |
| V6 Cryptography | No | — |
| V8 Data Protection | Partial | Forked history contains the full main transcript incl. tool results — it stays in-process (same trust boundary); no new exfiltration surface beyond the side agent's own full tools (user-accepted via D-05) |
| V10 Malicious Code | Partial | btw prompt injection: the side question is USER text (trusted); the forked history may contain untrusted tool output — same posture as main turns, no new control needed |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Side agent escapes approval (silent mutation) | Elevation of privilege | Shared gate + namespaced batch + Pitfall 5 `trust_delegated` documentation; regression test: every btw mutation prompts (default config) |
| Approval confusion (approve wrong agent's action) | Spoofing | `[main]`/`[btw]` tags from `event.agent` identity + agent-keyed ask context (Pitfall 1); never tag from mutable turn state |
| History injection via crafted btw answer | Tampering | D-14 append-back is verbatim model output into history — same trust as any assistant turn; no special control, but the append format must preserve role alternation or the next turn fails validation |
| Terminal-state corruption (DoS on own session) | Denial of service | Single `output_context` opener, render lock, reader-thread discipline (Anti-Patterns); failures render fenced, never raise into the main turn |

Residual #6 from Phase 3 (`03-SECURITY.md`: no second HumanInTheLoop handler) is satisfied by construction: the plan shares THE SAME instance (D-06), and the SDK documents instance reuse across invocations as anticipated.

## Sources

### Primary (HIGH confidence — read this session)

- Repo: `strands_code_cli/loop.py` (`_invoke_agent` 238-274, `run_loop` 888-1219, `record_turn_metrics` 190-219, cancel machine 277-340)
- Repo: `strands_code_cli/steering.py` (module contract 1-43, `mid_turn_slash_reply` 65-82, reader 259-399)
- Repo: `strands_code_cli/policy_gate.py` (broker 168-221, classifier 253-371, ask 373-436, `build_interventions` 507-526)
- Repo: `strands_code_cli/main.py:105-177` (`build_agent` factory kwargs — the replay seam)
- Repo: `strands_code_cli/router.py:102-222` (`dispatch` tri-state), `strands_code_cli/output.py` (`output_context`, `print_plain`), `strands_code_cli/policy.py:129-133` (`trust_delegated` default False)
- Repo: `strands_code_agent/callback_handler.py:88-134` (message-level rendering)
- Venv: `.venv/.../strands_harness/tools/subagent.py` (full file: `AgentSpec`/`Preset`/`GENERALIST`, `_fork_messages` 361-390, `_with_history`, `make_subagent` 576-660, `build_default_subagent` 687-766)
- Venv: `.venv/.../strands/types/exceptions.py:118-124` (`ConcurrencyException` per-instance scope)
- Venv: `.venv/.../strands/vended_interventions/hitl/hitl.py:53-70` (handler-instance reuse anticipated)
- CONTEXT/REQUIREMENTS/STATE: `.planning/phases/07-subagents-btw-side-channel/07-CONTEXT.md`, `.planning/REQUIREMENTS.md` (LOOP-03), `.planning/STATE.md`

### Secondary (MEDIUM confidence — observed via targeted grep/sed, not full-file Read)

- Venv: `strands_harness/agent.py` (factory docstrings: `subagent` builtin semantics, plugin-instances-shared-with-children, `parent_config` session-off recipe) — CITED, quotes reproduced above
- Venv: `strands_harness/memory.py:38-74` (`resolve_memory` recall-only delegate shape) — CITED, quote reproduced above
- Venv: `strands/agent/agent.py` (~1290-1302, invocation-begin/concurrency-complete) — CITED

### Tertiary (LOW / assumed — flagged inline as [ASSUMED])

- Rich internal print lock (A1); `prompt_async` multiplex viability (A2, needs spike); `PendingStore` thread-safety (A3, needs spike); SDK-global thread-safety across two instances (A4); dialog safety under dual streaming (A5)
