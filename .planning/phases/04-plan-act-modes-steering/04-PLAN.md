---
phase: 04-plan-act-modes-steering
plan: 04
type: execute
wave: 1
depends_on: []
files_modified:
  - strands_code_cli/mode.py
  - strands_code_cli/steering.py
  - strands_code_cli/policy_gate.py
  - strands_code_cli/main.py
  - strands_code_cli/loop.py
  - strands_code_cli/router.py
  - strands_code_agent/code_agent.py
  - tests/test_mode.py
  - tests/test_steering.py
  - tests/test_plan_cancel.py
autonomous: true
requirements: [MODE-01, MODE-02, LOOP-02, LOOP-04]
estimate:
  tokens: 48000
  raw_tokens: 32000
  tasks: 6
  confidence: med
must_haves:
  truths:
    - User can work in Plan mode (read-only step-list proposal), approve it, and watch Act execute it (per MODE-01, D-01/D-02/D-03/D-04)
    - User can cycle between plan and act mid-session via /mode without restarting (per MODE-02, D-05/D-06/D-07/D-08)
    - User can type freeform steering mid-task and see it applied at the next tool-call boundary with the in-flight call finishing first (per LOOP-02, D-09/D-10/D-11/D-12)
    - User can cancel a running task with two-press Ctrl-C, keep partial work, and stay in the CLI (per LOOP-04, D-13/D-14/D-15/D-16)
  artifacts:
    - strands_code_cli/mode.py (session-sticky mode holder + Plan prompt prefix + step-list copy)
    - strands_code_cli/steering.py (SteeringState + BeforeToolCallEvent hook + raw-readline input thread)
    - strands_code_cli/policy_gate.py (Plan classifier-deny flag, mode vocabulary only)
    - strands_code_cli/loop.py (input-thread lifecycle, two-press Ctrl-C, cancel flush)
    - strands_code_cli/router.py (/mode + /approve reply branches)
    - tests/test_mode.py
    - tests/test_steering.py
    - tests/test_plan_cancel.py
  key_links:
    - main.py build_agent registers the steering hook via agent.add_hook and passes the classifier mode flag; single agent instance, bind_main_agent invariant preserved
    - policy_gate.py Plan-deny sits above the trust_delegated early return (policy_gate.py:164-170) and emits mode vocabulary only, never policy-rule words
    - loop.py run_loop owns per-turn SteeringState lifecycle plus the caller-owned cancel event; input thread is raw sys.stdin.readline daemon with explicit shutdown, paused while the gate ask is open
    - router.py /mode and /approve are reply-only; approval handoff is the explicit command logged in history
  prohibitions:
    - MUST NOT construct a second HumanInTheLoop for Plan/Act (name collision; RESEARCH §1; 03-SECURITY residual #6)
    - MUST NOT reuse policy rule/mode vocabulary for Plan/Act denials or help text, and MUST NOT reuse /diff auto/approve-each/on-demand terms for Plan (vocabulary lock)
    - MUST NOT add general auto/yolo mode, effort presets (MODE-03), /btw side-channel (Phase 7), model/cost/context commands (Phase 5), skills/memory (Phase 6), rollback journals, or resume-of-cancelled-task
    - MUST NOT call agent(text) re-entrantly from the steering path (ConcurrencyException); steering redirects from inside the BeforeToolCallEvent hook only
    - MUST NOT kill the in-flight tool call on steering or first Ctrl-C; finish-then-redirect/stop always
    - MUST NOT widen scope roots or add confinement exceptions as a Plan side effect (residual #6 scope rule)
    - MUST NOT re-enable programmatic_tool_caller (main.py:103-107 pinned off, residual T-03-05)
  assumptions:
    - FLAGGED ASSUMPTION (hook-order probe): the steering BeforeToolCallEvent hook can be ordered before the HITL approval prompt via HookOrder so a redirected call is never approval-prompted; tracer verifies live, documents observed order
    - FLAGGED ASSUMPTION (SIGINT probe): during the synchronous turn no prompt app runs so SIGINT surfaces as KeyboardInterrupt in the main thread at loop.py:131; tracer confirms empirically
    - FLAGGED ASSUMPTION (readline probe): a raw sys.stdin.readline daemon thread coexists with output_context StdoutProxy without corrupting transcript output; tracer verifies visually, prompt_toolkit background prompt is the documented fallback spike only
---

<objective>
Tracer slice first: prove the whole Phase 4 stack end to end with one production-quality path — a replay-model turn in Plan mode that proposes a numbered step list, denies a write via the classifier with mode vocabulary, flips to Act on /approve, redirects at a tool boundary on steering text, and stops gracefully on two-press Ctrl-C with a session flush — then flesh out mode state, gate enforcement, steering machinery, and cancel around that proven spine.

Purpose: Land read-only Plan with explicit approve-to-Act, session-sticky /mode cycling, boundary steering, and two-press cancel (MODE-01, MODE-02, LOOP-02, LOOP-04) on the Phase 3 single-HITL spine without a second handler.
Output: mode holder + Plan prompt prefix, classifier Plan-deny, steering hook + input thread, two-press cancel with flush, /mode + /approve routes, and passing replay-model tests per task (no live Bedrock needed).
</objective>

<execution_context>
@$HOME/.codex/gsd-core/workflows/execute-plan.md
@$HOME/.codex/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/REQUIREMENTS.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/04-plan-act-modes-steering/04-CONTEXT.md
@.planning/phases/04-plan-act-modes-steering/04-RESEARCH.md
@.planning/phases/03-permissions-gate/03-CONTEXT.md
@.planning/phases/03-permissions-gate/03-SECURITY.md
@.planning/codebase/ARCHITECTURE.md
@.planning/codebase/STACK.md
</context>

<resolved_open_items>
Planner resolutions. Executor implements exactly these; no re-derivation.

1. Approve command name (D-02) → `/approve`. Rejected `/act`: it collides with the `/mode act` target word and would read ambiguously in history ("did /act mean approve, or switch?"). `/approve` logs intent unambiguously. No alias in v1 — one name, discoverable via USAGE_HINT. Semantics: valid only when a pending plan exists for this session (set when a Plan-mode turn proposes steps); otherwise reply "No pending plan — switch to Plan with /mode plan first." On success: reply "Plan approved — switched to act." and set mode act (session-sticky per D-07). The approval itself is a router reply, not a gate prompt (established reply-only pattern, router.py:73-78).
2. Step-list rendering shape + revise-round messaging (D-01/D-04) → numbered step list `1. <verb> <target> — <one-line why>`, grouped as `Files to touch:` then `Commands to run:`, closed with `Reply with revisions in plain words, or /approve to execute.` Revise rounds: any non-slash reply while mode is plan AND a plan is pending re-plans (normal agent turn with the Plan prefix re-asserted); freeform, no syntax. Rendering lives in the Plan system-prompt prefix (mode.py PLAN_PREFIX), not in router/loop code, so copy changes never touch machinery.
3. Enforcement primary (§1) → classifier-deny (RESEARCH Option B) as the enforcement core, Plan system-prompt prefix as defense-in-depth. Single agent instance; mode flips via a setter on the classifier. Explicitly NOT tool removal (Option A: confusing unknown-tool errors + rebuild/dual-agent cost) and NOT a scoped second agent (Option C: duplicates bind_main_agent identity per policy_gate.py:144-147, unproven session-write contention). No double-refusal layering: shell stays `True` in the builtin mapping; the classifier is the one denial voice. Read-only boundary: read-only = `read`, `search` (gate allowlist, policy_gate.py:269) + GET-shaped `web_fetch`/`web_search` (pre-allowed, harmless in Plan, keep allowed). Deny in Plan: `write`, `edit` wrappers, `shell`, `python_repl` (default-deny: interior `open()`/write per residual T-03-08). Deny reason uses mode vocabulary ONLY: `Plan mode is read-only — <tool> skipped, continuing.` Never a fake policy rule, never diff-mode words.
4. Plan-deny placement vs trust_delegated (RESEARCH risk 2) → the mode check sits ABOVE the `trust_delegated` early return (policy_gate.py:164-170). Delegated turns do not escape read-only. Default trust_delegated False (policy.py:130) keeps this latent until the option is used; the ordering test pins it regardless.
5. First-press Ctrl-C copy + second-press window (§4) → press #1 prints via console inside output_context: `Cancelling after the current step… press Ctrl-C again to confirm.` Timeout window 5 s: press #2 inside the window is confirmed-cancel (idempotent — graceful stop already requested); after the window lapses with no second press print `Still cancelling — graceful stop already requested; the current step finishes first.` Honest framing only: press #1 REQUESTS graceful stop (caller-owned event set, observed at the next cancellation-safe point); press #2 CONFIRMS intent (prevents accidental single-press kills, the user's stated motive). Never promise resume-after-cancel — the SDK offers no un-cancel; remainder is dropped per D-15. Copy must name the boundary gap: steering/cancel apply at the next step, not mid-tool-call.
6. Input-thread design (§3) → raw `sys.stdin.readline` daemon thread (recommended v1), NOT a second prompt_toolkit app. Rationale: two concurrent prompt apps race terminal ownership and StdoutProxy repaint is unproven here (RESEARCH risk 3); D-12 demands zero-friction capture, not full REPL fidelity — line editing/history loss on the steering line is accepted v1. Lifecycle owned by run_loop per turn: start before `agent(text)`, stop after (explicit shutdown event + join, never daemon-only); must not survive into the next idle `session.prompt` (stdin contention). Echo captured lines through output_context so they land in the transcript. Spike gate: if the tracer shows readline corrupting output under load, fall back to `prompt(in_thread=True)` only after a visual check — executor records the observation, does not redesign.
7. Gate-open coordination (RESEARCH risk 1) → the gate ask sets a flag (module `gate_open` threading.Event in policy_gate.py, set around the blocking `input()` at policy_gate.py:215, cleared on return) that the steering reader checks: while open, the reader buffers keystrokes instead of feeding SteeringState.pending, so a steering line can never be consumed as a y/n answer. Explicit test: open prompt + background keystrokes → approval unaffected, steering buffered and applied at the next boundary after the prompt closes.
8. Ctrl-C-during-approval semantics (§4) → deny-this-tool (current behaviour preserved). Rationale: least surprise, preserves D-02 turn-continues; the ask's broad except (policy_gate.py:240-242) already converts it to deny-and-continue and it never reaches loop.py:131. Run-cancel applies outside open prompts only. Documented in the first-press copy footnote and in the cancel test docstring — not discovered in review.
9. SteeringState ownership (§7) → explicit object threaded through `run_loop` → hook closure. New module strands_code_cli/steering.py owns `SteeringState` (pending string + threading.Event, `bind_turn` reset mirroring BatchState policy_gate.py:53-87) and the hook factory; run_loop constructs one per turn and closes over it. Rejected module-level `_ACTIVE` registry (test-hostile). BatchState remains the per-turn-state template only — no shared mutable global for steering.
10. Mode ownership + persistence (D-07) → `mode: str` holder object (`ModeState`, default `"act"` per D-05) constructed in run_loop and passed into `dispatch` + classifier setter + steering hook. In-memory session-sticky only; new sessions default Act. No disk persistence in this phase (DiffConfig shape is the template IF persistence is ever wanted — explicitly not now). `/mode` with no arg replies current mode; `/mode plan|act` switches and announces in transcript (`Mode: plan — read-only, proposes steps for /approve.` / `Mode: act — executing with approvals.`); bogus arg → usage reply, never an agent turn.
11. Cancel flush (D-15) → cancel path calls `explicit_save(agent)` (loop.py:53-66) plus `index.ensure(session_id)` at cancel time, not only at exit — so killed-CLI-after-cancel still keeps partial work. Completed tool results are already in the session; no rollback journal (explicitly out). After cancel: fall through to the prompt in the same session with mode unchanged (D-07/D-16). Kill-after-cancel replay test pins the flush.
12. Hook choice + ordering (§2) → `BeforeToolCallEvent.cancel_tool` steering hook registered via `agent.add_hook` in build_agent, HookOrder chosen so steering-cancel runs BEFORE the HITL approval prompt (tracer records observed relative order; if SDK order cannot be forced, the hook instead marks pending-consumed and the classifier treats a steering-armed boundary as skip-prompt — executor implements whichever the tracer proves, no redesign). `AfterToolCallEvent` result mutation is NOT used (provenance risk); `AfterInvocationEvent.resume` is fallback-only (next-turn, fails D-09 alone). Long model-streaming stretches with no tool call are a named limit in UX copy (`Steering noted — applies at the next step.`), not machinery.
</resolved_open_items>

<tasks>

<task type="tracer">
  <name>[~] Tracer — Plan-deny + /mode + /approve + boundary-steer + two-press cancel on replay model</name>
  <files>strands_code_cli/mode.py, strands_code_cli/steering.py, strands_code_cli/policy_gate.py, strands_code_cli/loop.py, strands_code_cli/router.py, tests/test_mode.py</files>
  <read_first>.venv/lib/python3.14/site-packages/strands/agent/agent.py:1100-1160 (add_hook + HookOrder); .venv/lib/python3.14/site-packages/strands/hooks/events.py:208-232 (BeforeToolCallEvent.cancel_tool writable fields); .venv/lib/python3.14/site-packages/strands/agent/agent.py:604-653 (cancel + cancel_signal); tests/test_kill_resume.py (offline _ReplayModel pattern — copy it, no live Bedrock)</read_first>
  <action>Tracer-first: prove the spine with a replay model before building on it. (a) Classifier Plan-deny: set mode plan on a PolicyClassifier double, fire fake BeforeToolCallEvent for write/shell/python_repl → assert Deny with mode-vocabulary reason (`Plan mode is read-only`), placed above the trust_delegated early return (delegated agent + trust_delegated=true still denied). (b) Hook order: register a BeforeToolCallEvent hook that sets cancel_tool alongside the real HITL intervention on a replay agent → record which runs first and whether a steering-cancelled call skips the approval prompt; document the observed order in the test docstring. (c) Steering redirect: pending steering text + replay tool call → assert cancel_tool carries the redirect message and the turn continues toward the revised goal (no re-entrant agent() call). (d) SIGINT probe: assert KeyboardInterrupt during synchronous agent(text) surfaces at loop.py:131 (no prompt app active); record yes/no empirically. (e) Cancel: caller-owned threading.Event per turn, first Ctrl-C sets it + prints first-press copy, second within 5 s confirms; assert explicit_save called on the cancel path. (f) /mode + /approve dispatch tri-state on the real router (reply-only, never agent turn). Record ALL observations (hook order, SIGINT behaviour, readline-vs-StdoutProxy visual check) in tests/test_mode.py module docstring.</action>
  <verify>
    <automated>uv run pytest tests/test_mode.py -x -q</automated>
    <fails_when>exit code != 0 or output contains FAILED or ERROR</fails_when>
  </verify>
  <done>Tracer green: Plan-deny, hook order, steering redirect, SIGINT surface, cancel flush, and /mode+/approve routing all evidenced with replay model; observations recorded.</done>
  <acceptance_criteria>Module docstring holds hook-order + SIGINT + readline observations; no live Bedrock touched; no second HumanInTheLoop; all reasons use mode vocabulary.</acceptance_criteria>
  <reversibility>Reversible — probe tests plus scratch modules; deleting restores Phase 3 wiring.</reversibility>
</task>

<task type="auto">
  <name>[P1] Mode state + /mode + /approve + Plan prompt prefix</name>
  <files>strands_code_cli/mode.py, strands_code_cli/router.py, strands_code_agent/code_agent.py, tests/test_mode.py</files>
  <read_first>strands_code_cli/router.py:30-70 (dispatch tri-state), 73-78 (reply-only pattern); strands_code_cli/diff_config.py:37-94 (DiffConfig shape — template only, no persistence here); strands_code_agent/code_agent.py (CODE_AGENT_INSTRUCTIONS assembly)</read_first>
  <action>Per MODE-01/MODE-02, D-01/D-02/D-04/D-05/D-06/D-07/D-08 and resolved items 1+2+10: create strands_code_cli/mode.py with `ModeState` (default "act", `set/get`, validates plan|act only — no auto/yolo words anywhere) + `PLAN_PREFIX` (read-only instruction + numbered step-list shape `Files to touch:` / `Commands to run:` + `Reply with revisions in plain words, or /approve to execute.` close) + pending-plan flag (set when a Plan turn proposes, cleared on /approve or mode switch to act). Router: `/mode [plan|act]` and `/approve` branches returning "reply" only; `/mode` bare reports current mode; switch announces in transcript; bogus args → usage reply; extend USAGE_HINT (router.py:17-21). dispatch gains a `mode: ModeState | None` kwarg (None → Act default, keeps standalone/test behaviour). Plan turns prepend PLAN_PREFIX to the agent input in loop.py (prefix at the call site, not baked into CODE_AGENT_INSTRUCTIONS — Act turns unchanged); keep the code_agent.py touch to a comment unless the tracer saw looping. TDD (replay-model): default act; /mode plan → sticky across turns; new ModeState defaults act; bogus mode → usage never agent turn; /approve with no pending plan → guidance reply; /approve with pending plan → approved reply + mode act; revise reply in plan re-plans.</action>
  <verify>
    <automated>uv run pytest tests/test_mode.py -x -q</automated>
    <fails_when>exit code != 0 or output contains FAILED or ERROR</fails_when>
  </verify>
  <done>Session-sticky plan/act cycling works; /approve hands off explicitly; Plan turns carry the step-list prefix.</done>
  <acceptance_criteria>Tests pin default-act, stickiness, approve-with/without-plan, revise re-plans; help text uses mode vocabulary only (no policy-rule or diff-mode words); no Phase 5/6/7 surface added.</acceptance_criteria>
  <reversibility>Reversible — new module plus two reply branches; removing restores Phase 3 dispatch.</reversibility>
</task>

<task type="auto">
  <name>[P1] Classifier Plan-deny enforcement</name>
  <files>strands_code_cli/policy_gate.py, tests/test_mode.py</files>
  <read_first>strands_code_cli/policy_gate.py:118-188 (PolicyClassifier.__call__ + trust_delegated return + Deny short-circuit)</read_first>
  <action>Per MODE-01, D-03 and resolved items 3+4: add a mode flag to PolicyClassifier (`set_mode("plan"|"act")`, default "act") checked FIRST in __call__ — above the trust_delegated early return (policy_gate.py:164-170). In plan mode every mutating tool (write, edit, shell, python_repl) returns the Deny short-circuit shape (requires_human_in_the_loop=True, reason `DENY:Plan mode is read-only — <tool> skipped, continuing.`) so the existing ask path prints the refusal and returns "n" without prompting (policy_gate.py:206-210 untouched). Reads/search/GET-fetch flow unchanged. BatchState collapses repeat Plan denials to one refusal per turn by construction (existing signature keying). Expose a build_agent-wired setter (mode state → classifier.set_mode on every /mode switch and at turn start). TDD with fake events: plan denies write/edit/shell/python_repl with mode-vocabulary reason; plan allows read/search; plan denial sits above trust_delegated (delegated + trusted still denied); act mode behaviour byte-identical to Phase 3 (existing test_policy_gate.py stays green unmodified).</action>
  <verify>
    <automated>uv run pytest tests/test_mode.py tests/test_policy_gate.py -q</automated>
    <fails_when>exit code != 0 or output contains FAILED or ERROR</fails_when>
  </verify>
  <done>Plan mode is technically read-only through the single HITL spine; Act is Phase-3-identical.</done>
  <acceptance_criteria>Denial strings contain `Plan mode is read-only` and no policy-rule/diff-mode words; ordering test pins above-trust_delegated; Phase 3 gate suite unmodified-green.</acceptance_criteria>
  <reversibility>Reversible — one flag plus one early check; unsetting restores Phase 3 verdicts.</reversibility>
</task>

<task type="auto">
  <name>[P2] Steering hook + SteeringState + raw-readline input thread</name>
  <files>strands_code_cli/steering.py, strands_code_cli/main.py, strands_code_cli/loop.py, strands_code_cli/policy_gate.py, tests/test_steering.py</files>
  <read_first>strands_code_cli/loop.py:100-138 (run_loop + agent(text) call site + bind_turn); strands_code_cli/policy_gate.py:53-87 (BatchState bind_turn template), 190-242 (ask input site for gate_open flag); strands_code_cli/output.py:21-30 (output_context)</read_first>
  <action>Per LOOP-02, D-09/D-10/D-11/D-12 and resolved items 6+7+9+12: create strands_code_cli/steering.py with `SteeringState` (pending: str|None + threading.Event, `bind_turn` reset mirroring BatchState) + `make_steering_hook(state)` (BeforeToolCallEvent callback: if state.pending, set event.cancel_tool to `Steering redirected by user: <text> — continue toward the revised goal from the next step; the skipped call was not executed.` and clear the flag; else no-op) + raw-readline reader (`start_steering_reader(state, gate_open)` → daemon thread on sys.stdin.readline, stopped via shutdown event + join; while gate_open is set, buffer keystrokes instead of arming pending; echo captured lines through output_context). Wire: build_agent (main.py:74-121) registers the hook via agent.add_hook with tracer-proven HookOrder; run_loop constructs SteeringState per turn, starts the reader before agent(text), stops after, calls bind_turn alongside existing bind_turn (loop.py:129); policy_gate ask sets/clears the gate_open event around input() (policy_gate.py:215). In-flight call always finishes (hook fires before the NEXT call — D-10 by construction). UX copy on capture: `Steering noted — applies at the next step.` plus the named streaming limit (long no-tool stretches delay redirect). TDD (replay-model, no live Bedrock): hook cancels-with-redirect and clears; hook no-ops when empty; reader arming sets pending; gate-open buffering never arms pending (open prompt + background keystrokes → approval unaffected); turn-end join leaves no live thread; no re-entrant agent() call anywhere on the path.</action>
  <verify>
    <automated>uv run pytest tests/test_steering.py -x -q</automated>
    <fails_when>exit code != 0 or output contains FAILED or ERROR</fails_when>
  </verify>
  <done>Typed mid-task input redirects the turn at the next tool boundary; in-flight calls finish; gate prompts are keystroke-safe.</done>
  <acceptance_criteria>Reader lifecycle, gate-open buffering, boundary-redirect, and no-reentrancy tests green; copy names the streaming limit; prompt_toolkit background prompt NOT introduced.</acceptance_criteria>
  <reversibility>Costly — boundary-interrupt needs turn machinery (input thread + hook); falling back to next-turn queueing later re-opens the core design (CONTEXT D-09). No checkpoint (code-reversible, no data contract).</reversibility>
</task>

<task type="auto">
  <name>[P2] Two-press Ctrl-C cancel + cancel-time flush</name>
  <files>strands_code_cli/loop.py, tests/test_plan_cancel.py</files>
  <read_first>strands_code_cli/loop.py:100-138 (idle vs turn KeyboardInterrupt sites); tests/test_kill_resume.py (replay-model + flush assertions to mirror)</read_first>
  <action>Per LOOP-04, D-13/D-14/D-15/D-16 and resolved items 5+8+11: grow the turn KeyboardInterrupt branch (loop.py:131-132) into a two-press state machine owned by run_loop. Caller-owned `threading.Event` per turn passed as the agent invocation cancel_signal (never agent.cancel() global mutation; agent observes, never sets — agent.py:773-811): press #1 sets the event + prints `Cancelling after the current step… press Ctrl-C again to confirm.` inside output_context; press #2 within 5 s is confirmed-cancel (idempotent — stop already requested); window lapse prints `Still cancelling — graceful stop already requested; the current step finishes first.` Cancel path calls explicit_save(agent) + index.ensure(session_id) at cancel time (D-15 partial-work survival), drops the remainder (no rollback, no resume-of-task), falls through to the prompt in the same session with mode unchanged. Idle branch (loop.py:114-115) untouched — Ctrl-C at idle still clears the line (D-14). Ctrl-C inside an open gate prompt stays deny-this-tool (ask broad except, policy_gate.py:240-242) and never reaches this branch. TDD (replay-model): single-press requests stop + first-press copy; second-press-inside-window confirms; window-lapse copy is honest (no resume promise); cancel flushes session (kill-after-cancel keeps partial work); idle Ctrl-C still line-cancels; post-cancel mode unchanged.</action>
  <verify>
    <automated>uv run pytest tests/test_plan_cancel.py -x -q</automated>
    <fails_when>exit code != 0 or output contains FAILED or ERROR</fails_when>
  </verify>
  <done>Two-press cancel stops gracefully, keeps partial work via cancel-time flush, and returns to the prompt in-session.</done>
  <acceptance_criteria>Copy matches resolved item 5 exactly; flush-on-cancel tested; no un-cancel promise anywhere; idle behaviour pinned unchanged.</acceptance_criteria>
  <reversibility>Reversible — one branch grows a state machine; collapsing restores single-interrupt message.</reversibility>
</task>

<task type="auto">
  <name>[P2] Wiring + build_agent hook registration + full-suite green</name>
  <files>strands_code_cli/main.py, strands_code_cli/loop.py, strands_code_cli/router.py, tests/test_mode.py</files>
  <read_first>strands_code_cli/main.py:74-121 (build_agent mapping + interventions + bind_main_agent); strands_code_cli/router.py:17-21 (USAGE_HINT)</read_first>
  <action>Close the loop with pure wiring (no new behaviour): build_agent registers the steering hook (agent.add_hook, tracer-proven HookOrder), threads ModeState → classifier.set_mode, keeps the single-HITL interventions list and the programmatic_tool_caller pin untouched; run_loop threads ModeState into dispatch, prefixes Plan-turn input, binds SteeringState per turn, owns the cancel event; USAGE_HINT gains `/mode [plan|act], /approve`. Extend the tracer kwargs test: interventions still single-HITL + steering hook registered + classifier mode setter reachable. Run the FULL suite (all Phase 1-3 suites must stay green unmodified). Grep the diff for scope bleed (`yolo`, `auto.*mode`, `/model`, `/cost`, `/compact`, `/context`, `/clear`, `skills`, `/init`, `/memory`, `/btw`, `subagent.*side`, `MODE-03`, `enable_trust`, `smart`, `cedar`) and remove any hit before merge.</action>
  <verify>
    <automated>uv run pytest tests/ -q</automated>
    <fails_when>exit code != 0 or output contains FAILED or ERROR</fails_when>
  </verify>
  <done>All wiring lands; full suite green; scope-bleed grep clean.</done>
  <acceptance_criteria>Full suite exit 0; kwargs test covers single-HITL + hook + mode setter; bleed grep empty; no Phase 2/3 test modified.</acceptance_criteria>
  <reversibility>Reversible — wiring-only edits; dropping them restores Phase 3 behaviour.</reversibility>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Plan turn→side effect | Every mutation in Plan mode is denied by the classifier mode flag (above trust_delegated) using mode vocabulary; the prompt prefix instructs read-only as defense-in-depth only |
| Steering text→turn | Typed mid-task text reaches the model only as a BeforeToolCallEvent cancel_tool redirect message at the next boundary; never as a re-entrant invocation, never as y/n input |
| Gate prompt→approval | While the ask input() is open the reader buffers keystrokes; steering can never answer y/n; Ctrl-C at a prompt denies-that-tool, never cancels the run |
| Ctrl-C→turn | First press requests graceful stop via caller-owned event (in-flight step finishes); second press confirms intent; cancel flushes the session so partial work survives |
| /approve→mode | Approval is an explicit router reply gated on a pending plan; it flips session-sticky mode to act and is logged in history |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-04-01 | Tampering | Model jailbreaks Plan prompt prefix to mutate | high | mitigate | Classifier-deny is the enforcement core, not the prompt; prefix is defense-in-depth only. BLOCKING until Plan-deny tests green. |
| T-04-02 | Tampering | trust_delegated bypasses Plan-deny for subagent turns | high | mitigate | Mode check above the trust_delegated early return; ordering test pins it. BLOCKING until green. |
| T-04-03 | Tampering | Second HITL added for Plan/Act approval | high | mitigate | Exactly one HumanInTheLoop (policy_gate.build_interventions stays the only site); /approve is a router reply, never a handler. BLOCKING until kwargs test green. |
| T-04-04 | Tampering | Steering keystrokes leak into gate y/n prompt and approve a mutation | high | mitigate | gate_open flag: reader buffers while ask input() is open; leak test (prompt + keystrokes → approval unaffected). BLOCKING until green. |
| T-04-05 | Tampering | Steering hook re-enters agent() causing ConcurrencyException / turn corruption | medium | mitigate | Hook only sets cancel_tool; no invocation from the hook or reader thread; no-reentrancy test. BLOCKING until green. |
| T-04-06 | Tampering | python_repl admitted as read-only in Plan, writes via interior code | high | mitigate | python_repl default-deny in Plan (residual T-03-08 extended); read-only set is read+search+GET-fetch only. BLOCKING until deny test green. |
| T-04-07 | Tampering | Cancel/steer kills the in-flight tool → half-written file | medium | mitigate | Finish-then-redirect/stop by construction (hook fires before NEXT call; cancel observed at safe points); no kill primitive on the path. |
| T-04-08 | Tampering | Scope widening smuggled in as "Plan needs to read X" | medium | mitigate | No effective_roots change in this phase; bleed grep covers scope.py. |
| T-04-09 | Spoofing | Stale pending-plan approves the wrong proposal (/approve with no plan) | medium | mitigate | /approve requires a pending plan for this session, else guidance reply; flag cleared on approve and on mode switch. |
| T-04-10 | Spoofing | Vocabulary confusion: Plan denial reads as policy rule, or /act misread as approval | low | mitigate | Vocabulary lock: mode words only in Plan copy; approve command is /approve, never /act; review lint by eye. |
| T-04-11 | Repudiation | Approve handoff leaves no trace of what was approved | low | mitigate | /approve is a transcript reply in session history; step list already in the turn transcript. |
| T-04-12 | Denial of service | Input thread survives the turn and steals stdin from the idle prompt | medium | mitigate | Explicit shutdown event + join per turn (never daemon-only); turn-end test asserts no live reader thread. |
| T-04-13 | Denial of service | Cancel without flush loses completed steps on subsequent kill | medium | mitigate | explicit_save + index.ensure on the cancel path; kill-after-cancel replay test. BLOCKING until green. |
| T-04-14 | Information disclosure | Steering echo leaks pending y/n answer or secret into transcript | low | accept+document | Echo only reader-captured lines (buffered-during-prompt lines are applied post-prompt, never the prompt answer itself); documented in steering.py docstring. |
| T-04-15 | Elevation | programmatic_tool_caller re-enabled, inner calls bypass Plan-deny | high | mitigate | Pin stays off (main.py:103-107); any re-enable must re-prove Plan-deny against inner calls per residual T-03-05. |
</threat_model>

<verification>
- `uv run pytest tests/ -q` stays green (TDD per task; new tests/test_mode.py, tests/test_steering.py, tests/test_plan_cancel.py; Phase 1-3 suites unmodified).
- Live REPL check (YOLO run): /mode plan → read-only step list; write attempt refused with `Plan mode is read-only`; /approve → `Plan approved — switched to act.`; mid-task typing redirects at next step with `Steering noted`; Ctrl-C twice cancels with partial work kept and prompt back.
- Planner scans: hook-order + SIGINT + readline observations recorded in test docstrings; assumption-delta — no new external API (threading + stdin stdlib only, no new dependency); schema-gate — no ORM files (ModeState/SteeringState are in-memory only, no migration needed).
- Scope-bleed audit: no auto/yolo mode, no /btw, no model/cost/context, no skills/memory — grep the diff for `yolo`, `auto.*mode`, `/model`, `/cost`, `/compact`, `/context`, `/clear`, `skills`, `/init`, `/memory`, `/btw`, `MODE-03`, `enable_trust`, `smart`, `cedar` before merge.
</verification>

<success_criteria>
- Roadmap §Phase 4 criterion 1: Plan mode proposes read-only, approval executes (MODE-01, D-01..D-04).
- Roadmap §Phase 4 criterion 2: mode cycling mid-session without restart (MODE-02, D-05..D-08).
- Roadmap §Phase 4 criterion 3: freeform mid-task steering applied at next tool-call boundary (LOOP-02, D-09..D-12).
- Roadmap §Phase 4 criterion 4: two-press Ctrl-C cancel keeps partial work and stays in CLI (LOOP-04, D-13..D-16).
- Full suite green; Plan denials use mode vocabulary; residuals (streaming boundary gap, readline fidelity, Ctrl-C-in-prompt hole) documented, not silently closed.
</success_criteria>

<output>
Create `.planning/phases/04-plan-act-modes-steering/04-PLAN-SUMMARY.md` when done
</output>

## Artifacts This Phase Produces

New symbols: `strands_code_cli.mode.ModeState/PLAN_PREFIX`, `strands_code_cli.steering.SteeringState/make_steering_hook/start_steering_reader`, `PolicyClassifier.set_mode` + `gate_open` flag, `run_loop` per-turn steering lifecycle + two-press cancel, router `/mode` + `/approve`.
New commands: `/mode [plan|act]`, `/approve`.
New files: `strands_code_cli/mode.py`, `strands_code_cli/steering.py`, `tests/test_mode.py`, `tests/test_steering.py`, `tests/test_plan_cancel.py`.
Decisions for downstream: single agent + classifier-deny is the mode spine (Phase 7 /btw subagents inherit Plan-deny automatically, still above trust_delegated); raw-readline reader is the v1 input shape (prompt_toolkit upgrade only after a visual spike); 5 s two-press window and deny-this-tool-in-prompt are pinned UX; no persistence for mode (in-memory session-sticky).
