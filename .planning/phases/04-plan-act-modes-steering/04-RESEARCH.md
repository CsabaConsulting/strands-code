# Phase 4: Plan/Act Modes + Steering — Research

**Researcher:** gsd-phase-researcher | **Date:** 2026-09-25 | **Status:** ready for planning
**Scope:** MODE-01, MODE-02, LOOP-02, LOOP-04 (D-01..D-16). Plan only — no code.

SDK ground truth: `strands-agents` 1.57.0 (in `.venv`), prompt_toolkit 3.0.53.
Single-HITL spine and vocabulary lock per
`.planning/phases/03-permissions-gate/03-SECURITY.md` residual #6 are hard
constraints on every option below.

---

## 1. Read-only Plan enforcement (MODE-01, D-03)

Three candidate mechanisms. All must compose with the single-HITL spine —
no second `HumanInTheLoop` instance (name-collision rule, `name =
"strands:human-in-the-loop"`; only construction site is
`strands_code_cli/policy_gate.py:259` `build_interventions`, wired once in
`strands_code_cli/main.py:112`).

### Option A — Tool removal (mode-aware scoping in `build_agent`)

In Plan mode, build the agent without mutating tools: drop the gated
write/edit wrappers from `tools` (`main.py:92-97`) and set
`builtin_tools["shell"] = False` (currently `True` at `main.py:99`), keep
`read: True`. `python_repl` (`SandboxedPythonInterpreter`, `main.py:87`) and
`search` stay.

- Pros: enforcement is structural — a plan *cannot* mutate even if the model
  tries; no prompt text to jailbreak; zero per-tool-call overhead; simplest
  to test offline (assert tool list per mode).
- Cons: model sees tool-call failures ("unknown tool") rather than a clean
  refusal, so the Plan system prompt must explain read-only scope or the
  model wastes turns retrying; switching modes mid-session (D-06/MODE-02)
  requires either rebuilding the agent (loses nothing — session state is in
  the session dir, but `bind_main_agent` at `main.py:120` must be re-run) or
  keeping two agent instances (plan-agent + act-agent sharing one
  `session_id` — doubles construction cost, risks session-write races).
- Gate interplay: clean — the HITL gate is untouched; fewer tools means
  fewer gate evaluations. But note the gate's `allowed_tools=["read",
  "search"]` (`policy_gate.py:269`) already encodes "reads are free",
  which aligns with Plan's needs.

### Option B — Classifier-deny (mode flag inside `PolicyClassifier`)

Add a mode flag to the existing `PolicyClassifier` (`policy_gate.py:126`):
when mode is Plan, every mutating tool verdict becomes `Deny` regardless of
policy file. The deny path already exists and is fail-closed: `Deny` →
`ClassifierResult(requires_human_in_the_loop=True, reason="DENY:…")`
(`policy_gate.py:183-187`) → ask short-circuits to printed refusal +
returns `"n"` without prompting (`policy_gate.py:206-210`). Denied tools
are skipped and the turn continues.

- Pros: single agent instance, mode flips with a setter (ideal for
  session-sticky `/mode` cycling, D-06/D-07); refusal message is
  human-readable and names the mode, not a rule; `BatchState` signature
  (`policy_gate.py:89-94`) naturally collapses repeat Plan denials to one
  refusal per turn; `/policy last` log records what the plan *attempted*.
- Cons: enforcement lives one layer above structural — a bug in the flag
  check (or the `trust_delegated` early-return at `policy_gate.py:164-170`,
  which bypasses `decide` entirely) could let a mutation through; every
  blocked call still costs a model→tool→deny round trip; the classifier
  `__call__` signature must gain mode state, and residual #6 forbids
  reusing policy rule vocabulary — the Plan-deny reason string must be
  mode-vocabulary (`"Plan mode is read-only"`), never a fake policy rule.
- Gate interplay: best fit — it *is* the spine, extended. The `DENY:`
  short-circuit was built for exactly this shape.

### Option C — Scoped agent (separate read-only agent instance)

A second agent built with read-only tools + a "propose steps, do not act"
system prompt, sharing the session. Effectively Option A with a distinct
identity and prompt.

- Pros: cleanest prompt separation (planner prompt vs coder prompt);
  mirrors the Phase 7 `/btw` subagent pattern, so machinery may be reusable.
- Cons: heaviest — two agents, two `bind_main_agent` bindings (D-12
  delegated-trust detection assumes exactly one main agent;
  `policy_gate.py:144-147`); session-dir write contention between two
  harness instances is unproven; overkill for a binary mode flag.
- Verdict: not recommended for this phase. Revisit only if revise rounds
  (D-04) prove to need a genuinely different planner prompt that can't live
  as an instruction prefix on the main agent.

### Recommendation for planner

**Option B (classifier-deny) as the enforcement core**, with the Plan
system-prompt prefix as defense-in-depth (prompt says read-only; classifier
guarantees it). Rationale: single agent preserves `bind_main_agent`/`bind_turn`
invariants, mode switching is a setter (MODE-02), and the DENY short-circuit
already implements finish-safe refusal. If the planner wants structural
backing too, Option A's `builtin_tools["shell"] = False` toggle can be added
per-turn without rebuilding — but pick one as primary; running both risks
confusing double-refusals (unknown-tool error + DENY message).

Read-only tool boundary (whichever option): read-only = `read`, `search`
(gate allowlist, `policy_gate.py:269`) plus whatever read-shaped surface
`python_repl` is deemed to have — default must be **deny**: `python_repl`
can `open()`/write via interior code (residual T-03-08, all-or-nothing
approval), so Plan mode must deny or remove it. `web_fetch`/`web_search`
are GET-shaped and pre-allowed (residual T-03-09); harmless in Plan, keep
allowed. Shell is unambiguously mutating (full `sh`, Phase 2 D-06) — deny.

---

## 2. Turn-interrupt machinery for boundary steering (LOOP-02, D-09/D-10)

Requirement: typed input mid-task redirects the turn at the next tool-call
boundary (D-09); the in-flight tool call finishes first (D-10); the turn
continues toward the revised goal (D-11).

### The seam: `BeforeToolCallEvent` / `AfterToolCallEvent` hooks

The SDK exposes a hook registry on the agent: `agent.add_hook(callback,
event_type)` (`agent.py:1100-1160` in `.venv/.../strands/agent/agent.py`).
Relevant events (`strands/hooks/events.py`):

- `BeforeToolCallEvent` (`events.py:208`) — fields: `selected_tool`,
  `tool_use`, `invocation_state`, plus writable **`cancel_tool`** (`bool |
  str`): "when set, will cancel the tool call. The message will be placed
  into a tool result with an error status" (`events.py:213-224`). Writable
  fields are exactly `cancel_tool`, `selected_tool`, `tool_use`
  (`events.py:231-232`). This is the boundary checkpoint: a hook here can
  observe pending steering text and cancel the upcoming tool call with a
  redirect message, which the model then sees as a tool result.
- `AfterToolCallEvent` (`events.py:248`) — fields include `result`,
  `exception`, `duration`, writable `result`/`retry`. A hook here can append
  steering text to the result or force `retry`. Prefer Before-hook
  cancellation over After-hook result mutation: cancel-before-execute is the
  documented path; rewriting a completed result risks confusing provenance.
- `AfterInvocationEvent.resume` (`events.py:86-99`): "when set to a
  non-None agent input by a hook callback, the agent will automatically
  re-invoke itself" — a full new invocation cycle. This is the fallback if
  mid-turn injection proves unworkable: let the turn end, then auto-resume
  with steering text. But it is *next-turn*, not mid-turn, so it does not
  satisfy D-09 alone; keep as fallback.
- `event.agent.cancel_signal` is readable from hooks (documented on
  `Agent.cancel_signal`, `agent.py:642-653`): "hooks can check
  `event.agent.cancel_signal.is_set()`". A steering hook can also poll a
  local `threading.Event` set by the input thread — simpler and decoupled
  from SDK cancel semantics (which set `stop_reason="cancelled"` and end
  the turn; steering must *continue* the turn per D-11, so SDK-level cancel
  is the wrong primitive for steering).

### Proposed machinery (planner to confirm)

1. A `SteeringState` object mirroring the `BatchState`/`bind_turn` pattern
   (`policy_gate.py:53-87`, reset per turn from `loop.py:129`): holds an
   optional pending steering string + a `threading.Event`.
2. An input thread (see §3) sets `SteeringState.pending` as the user types.
3. A `BeforeToolCallEvent` hook, registered via `agent.add_hook` in
   `build_agent`, checks `SteeringState` at each boundary: if steering is
   pending, set `event.cancel_tool = <redirect message embedding the user
   text>` and clear the flag. The in-flight call already finished (the hook
   fires *before the next* call — D-10 falls out naturally). The model
   receives the redirect as a tool error result and continues toward the
   revised goal (D-11).
4. Ordering vs the HITL gate: the HITL `before_tool_call` is an
   *intervention* handler, hooks are a separate registry; verify relative
   order in implementation — steering-cancel should run before the approval
   prompt so the user isn't asked to approve a call that's about to be
   redirected. `HookOrder` constants (`SDK_FIRST`/`DEFAULT`/…) exist on
   `add_hook` (`agent.py:1100`).

### What the SDK cannot do (constraints)

- No mid-tool-call preemption hook exists: `cancel_tool` cancels *before*
  execution; once a tool runs, only `agent.cancel()` (graceful, stops at
  "cancellation-safe points", `agent.py:604-639`) applies, and it ends the
  turn with `stop_reason="cancelled"` — right for LOOP-04 cancel, wrong
  for steering-continue. D-10 (finish-then-redirect) matches this
  constraint exactly; D-10 is not just a UX choice but the only safe shape.
- Long model-streaming stretches have no tool boundary: if the model emits
  60s of text with no tool call, steering waits. Mitigation is UX (echo
  "steering noted, applies at next step"), not machinery. Name this limit
  in the plan.
- `ConcurrencyException`: "another invocation is already in progress"
  (`agent.py` `__call__` docstring) — so steering must *not* call
  `agent(text)` re-entrantly. The hook-injection design above respects this
  (one invocation, redirected from inside).

---

## 3. prompt_toolkit input while a turn runs (LOOP-02 input thread)

Current state (`strands_code_cli/loop.py:100-138`): one `PromptSession`
owns input (`loop.py:109`); `session.prompt("> ")` blocks; the agent turn
`agent(text)` runs synchronously *after* the prompt returns, inside
`output_context()` (`loop.py:127-130`). While the turn runs there is **no
active prompt** — keystrokes go nowhere (terminal buffers them, or they
are lost to the cooked-mode line discipline). D-12 ("anything typed
mid-task is steering") therefore requires a live reader during the turn.

### Key facts

- `PromptSession.prompt()` accepts `in_thread=True` ("run the prompt in a
  background thread", `prompt.py:931-957` in prompt_toolkit 3.0.53) — but
  that flag is for running the *prompt UI* off-thread, not for background
  reading while the main thread works. More relevant: prompt_toolkit apps
  own the terminal event loop; two concurrent `prompt()` calls race.
- `output_context` (`strands_code_cli/output.py:21-30`) swaps `sys.stdout /
  sys.stderr` for a `StdoutProxy(raw=True)` bound to the *currently active*
  app session (`patch_stdout.py:110-119`). It assumes no prompt app is
  running during the turn (proxy prints "above" the prompt). If an input
  thread runs a second prompt app concurrently, `StdoutProxy`'s app-session
  binding and repaint behavior are untested in this repo — expect flicker
  or misrouted output; the plan must include a visual test.
- The HITL ask path uses blocking `input()` inside `output_context()`
  (`policy_gate.py:199,215`), serialized by nothing except turn
  sequentiality. A steering reader thread + a gate `input()` racing on
  stdin is the sharpest edge: two readers on one stdin. The gate prompt
  must win (approval is blocking and modal); the steering reader must pause
  while a gate prompt is open, or steering keystrokes leak into a y/n
  answer (danger: a steering "y…" typed at the wrong moment approves a
  mutation). Concrete mitigation: gate ask sets a flag (or holds a lock)
  that the steering reader checks; steering typed during an open approval
  is buffered, not fed to the pending y/n `input()`.
- `session.prompt("> ")` raising `KeyboardInterrupt` on Ctrl-C
  (`loop.py:114`) only applies at idle. During the turn there is no prompt,
  so Ctrl-C raises in the main thread wherever `agent(text)` is —
  currently caught at `loop.py:131-132` ("Turn interrupted"). Both the
  two-press design (§4) and the steering reader attach here.

### Design inputs for planner

- Simplest viable reader: a daemon thread doing blocking `sys.stdin.readline`
  (raw stdin, *not* a second prompt_toolkit app) started before
  `agent(text)`, stopped after. Loses line editing/history for the steering
  line (acceptable v1; D-12 demands zero-friction capture, not full REPL
  fidelity). Echo the captured line through `output_context` so it lands in
  the transcript.
- Richer alternative: `prompt_toolkit`'s `patch_stdout`-aware background
  input (a second `PromptSession.prompt(in_thread=True)`). Better UX, but
  concurrent-app risk above; spike before committing.
- Either way: the reader thread must be joined/cancelled deterministically
  at turn end (turn-boundary lifecycle owned by `run_loop`), must not
  survive into the next idle `session.prompt` (stdin contention), and must
  coordinate with the gate-ask lock. Daemon + explicit shutdown event, not
  daemon-only.

---

## 4. Two-press Ctrl-C (LOOP-04, D-13/D-14/D-15/D-16)

Decisions: first press asks/confirms, second confirms (D-13, user overrode
one-press recommendation); idle Ctrl-C keeps line-cancel (`loop.py:114`,
D-14); cancel keeps partial work, drops the remainder (D-15); return to
REPL in-session (D-16).

### Current handling and SDK seams

- Today: `KeyboardInterrupt` during `agent(text)` is caught once at
  `loop.py:131` → prints "Turn interrupted" → loop continues. No
  confirmation, no partial-work messaging. Idle Ctrl-C → `continue`
  (`loop.py:114-115`).
- No `signal.signal(SIGINT, …)` exists in the CLI today (grep: only the two
  `KeyboardInterrupt` sites in `loop.py`). prompt_toolkit installs its own
  SIGINT handling while a prompt is active; during the synchronous turn no
  prompt app runs, so SIGINT surfaces as `KeyboardInterrupt` in the main
  thread — the plan should confirm this empirically rather than assume it.
- SDK cancel primitive: `agent.cancel()` (`agent.py:604-639`) — thread-safe,
  stops "at the next cancellation-safe point (model streaming, before tool
  execution, during MCP tool execution, after tool execution)", result
  carries `stop_reason="cancelled"`. Plus per-invocation `cancel_signal:
  threading.Event` passed into `agent(...)` (`agent.py:773,804-811`) — the
  agent observes both, never sets/clears the caller's event. A caller-owned
  event is the cleaner fit here (loop creates it per turn, first Ctrl-C
  sets it, no global mutation).
- Caveat from the HITL source, directly applicable: "a worker thread
  blocked on `input` cannot be cancelled… if the agent run is cancelled
  mid-prompt the thread stays parked" (`hitl.py: _create_stdio_ask`
  docstring). Our gate's ask is sync `input()` (`policy_gate.py:215`), not
  offloaded — a Ctrl-C during an open approval prompt raises
  `KeyboardInterrupt` inside `ask`, which the ask catches *broadly*
  (`policy_gate.py:240-242`, returns `"n"`). Consequence: pressing Ctrl-C
  at an approval prompt currently denies-and-continues, it does NOT reach
  `loop.py:131`. The two-press design must decide: does Ctrl-C at a gate
  prompt count as press #1 (cancel the turn) or as deny-this-tool (current)?
  Recommend: keep deny-this-tool (least surprise, preserves D-02
  turn-continues), and document that run-cancel applies outside open
  prompts. This needs an explicit planner decision.

### First-press UX inputs (the agent's discretion per CONTEXT)

- On press #1: set the caller-owned cancel event (or call
  `agent.cancel()`), print via `console.print` inside `output_context`:
  "Cancelling after the current step… press Ctrl-C again to confirm."
  The in-flight tool finishes (mirrors D-10; no killed commands).
- Timeout window: if press #2 arrives within N seconds (suggest 5s;
  planner picks), treat as confirmed-cancel (idempotent — cancel already
  requested); if the window lapses with no second press, print "Continuing
  to listen for cancel…" — but note the turn is *already* cancelling
  (SDK cancel is one-way; there is no un-cancel). Honest framing: press #1
  *requests* graceful stop; press #2 *confirms you mean it* (prevents
  accidental single-press kills — the user's stated motive) rather than
  toggling. Do not promise "press once more to resume" — the SDK offers no
  resume-after-cancel; remainder is dropped per D-15.
- Partial-work survival (D-15) rides on existing machinery: session flush
  on exit (`loop.py:136-137` `explicit_save` + `index.ensure`), per-message
  saves (SES-03, `test_kill_resume.py`). The plan must add: flush
  *at cancel time* (not only at exit), so killed-CLI-after-cancel still
  keeps partial work; completed tool results are already in the session.
  No rollback journal (explicitly out).
- After cancel: fall through to the prompt (`loop.py` while-loop,
  D-16) with mode unchanged (session-sticky, D-07).

---

## 5. Codebase map (where Phase 4 plugs in)

| Area | File:line | Phase 4 touch |
|---|---|---|
| Turn call site | `strands_code_cli/loop.py:127-130` | Input-thread start/stop, per-turn cancel event, `bind_turn` already here (`loop.py:129`) — `SteeringState.bind_turn` mirrors it |
| Idle Ctrl-C / turn Ctrl-C | `strands_code_cli/loop.py:114`, `loop.py:131-132` | D-14 preserved idle branch; turn branch grows the two-press state machine |
| Slash dispatch | `strands_code_cli/router.py:30-70` | New `/mode [plan\|act]` + `/approve` (name TBD) branches returning `"reply"`; extend `USAGE_HINT` (`router.py:17-21`); reply-only, no prompts here (established pattern, `router.py:73-78` docstring) |
| Mode-aware scoping | `strands_code_cli/main.py:74-121` `build_agent` | Plan enforcement (classifier flag and/or tool-list toggle), steering `add_hook` registration, cancel-event wiring; re-run `bind_main_agent` (`main.py:120`) if agent is ever rebuilt |
| Gate spine | `strands_code_cli/policy_gate.py:156-188` classifier, `policy_gate.py:190-242` ask | Plan-deny verdict (mode vocabulary, not policy vocabulary); ask-level gate-open flag for the steering reader; `BatchState` (`policy_gate.py:53-87`) as the per-turn-state template |
| Output | `strands_code_cli/output.py:21-30` | Steering echoes, first-press UX, Plan step-list rendering all flow through `output_context` (raw ANSI preserved) |
| Session state | `strands_code_cli/loop.py:109-110`, `main.py:143-150` | Mode is session-sticky in memory (D-07): a `mode: str` owned by `run_loop` (default `"act"`, D-05) or a tiny session-scoped holder passed to `dispatch` + classifier; new sessions default Act. `DiffConfig` (`router.py:73-92`) is the shape template *if* persistence is ever wanted — default is in-memory per CONTEXT |
| Step-list + revise | new planner-prompt prefix + `/approve` branch | Plan rendering shape and revise-round messaging are the agent's discretion (D-01/D-04); approval handoff is the explicit command (D-02), logged in history via the normal turn transcript |
| Tests | `tests/test_policy_gate.py`, `tests/test_kill_resume.py`, `tests/test_repl_history.py` | Offline doubles exist (`_ReplayModel` in `test_kill_resume.py`); steering/cancel tests follow the same replay-model pattern — no live Bedrock needed |

`/mode` announcement: D-06 requires the switch to be announced in the
transcript — a `"reply"` message suffices ("Mode: plan — read-only…").

---

## 6. Risks for MODE-01/02/LOOP-02/04

1. **Steering keystrokes leak into gate y/n prompts.** Highest interaction
   risk (§3): a steering line typed during an open approval `input()` is
   consumed as the approval answer. Mitigate with a gate-open flag/lock;
   test explicitly (open prompt + background keystrokes → approval
   unaffected).
2. **`trust_delegated` bypasses Plan-deny.** The early return at
   `policy_gate.py:164-170` skips `decide` for non-main agents when
   `trust_delegated` is set. Plan-deny must sit *above* that return or
   delegated turns escape read-only. (Default `False` per
   `policy.py:130`, so latent until the option is used.)
3. **Second-prompt-app instability.** If the planner chooses a
   prompt_toolkit reader over raw `readline`, concurrent apps +
   `StdoutProxy` repaint is unproven here — spike with a visual check
   before committing; fall back to raw `readline`.
4. **Ctrl-C inside `input()` never reaches the loop.** The ask's broad
   `except` (`policy_gate.py:240`) converts it to deny-and-continue.
   Two-press cancel therefore has a hole during open approvals — decide and
   document (§4), don't discover in review.
5. **Boundary gaps during long model streams.** Steering waits for the next
   tool call; long no-tool stretches delay redirect with no machinery fix.
   Set the expectation in UX copy ("applies at the next step"), and do not
   let the plan promise true anytime-preemption.
6. **`programmatic_tool_caller` re-enable re-opens Plan.** Pinned off
   (`main.py:103-107`, residual T-03-05); inner tool calls are "unverifiable
   through before_tool_call without a live model". Any future re-enable
   must re-prove Plan-deny against inner calls.
7. **Vocabulary lock violation.** Residual #6: "must not reuse policy
   rule/mode vocabulary for Plan/Act modes" — Plan denials, `/mode` help
   text, and step-list copy must use mode vocabulary only. Also avoid
   `/diff`'s `auto`/`approve-each`/`on-demand` terms (Phase 2 D-04/D-05)
   for anything Plan-related. Easy to trip in refusal strings; lint by eye
   in review.
8. **Scope widening re-opens D-13.** Residual #6: Plan work must not add
   scope roots or confinement exceptions as a side effect (e.g. "Plan needs
   to read X" → widening `effective_roots`). Reads already cover the repo;
   hold the line.
9. **Two-agent temptation (Option C).** Duplicates `bind_main_agent`
   identity, risks session-write races, and doubles construction cost for a
   binary flag. Keep one agent; the steering hook + classifier flag are
   designed for exactly that.
10. **Cancel-without-flush loses D-15's promise.** Partial work survives
    only if cancel triggers an explicit session save (today's save is
    exit-only, `loop.py:136`). Plan the cancel-path flush; verify with a
    kill-after-cancel replay test.

---

## Open questions for the planner (the agent's discretion)

- Approve command name: `/approve` vs `/act` (D-02).
- Step-list rendering shape + revise-round agent messaging (D-01/D-04).
- Enforcement primary: classifier-deny (recommended, §1 Option B) vs tool
  removal, or both layered.
- First-press Ctrl-C copy + second-press timeout window (suggest ~5s, §4).
- Input-thread design: raw `readline` (recommended v1) vs prompt_toolkit
  background prompt (§3).
- Ctrl-C-during-approval semantics: deny-this-tool (recommended) vs
  counts-as-press-#1 (§4).
- `SteeringState` ownership: module-level `_ACTIVE`-style registry (as
  `policy_gate.py:256`) vs explicit object threaded through
  `run_loop` → hook closure (prefer explicit; `_ACTIVE` is test-hostile).

*Plan only — no code written.*
