---
phase: 03-permissions-gate
plan: 03
type: execute
wave: 1
depends_on: []
files_modified:
  - strands_code_cli/main.py
  - strands_code_cli/loop.py
  - strands_code_cli/router.py
  - strands_code_cli/scope.py
  - strands_code_cli/diff_gate.py
  - strands_code_cli/policy.py
  - strands_code_cli/policy_gate.py
  - strands_code_agent/code_agent.py
  - tests/test_policy.py
  - tests/test_policy_gate.py
autonomous: true
requirements: [TOOL-03]
estimate:
  tokens: 55000
  raw_tokens: 37000
  tasks: 8
  confidence: med
must_haves:
  truths:
    - User is prompted to approve or deny before the agent edits files, runs shell commands, or touches the network, via exactly one HumanInTheLoop instance (per TOOL-03, D-01/D-02, RESEARCH §1.2 collision rule)
    - Routine actions stop prompting once named by standing TOML allow/deny rules while dangerous ones stay gated, deny-wins on conflict (per TOOL-03, D-05/D-06/D-07)
    - Gate approval and /diff never double-prompt: one prompt total covers a write (per D-10)
    - python_repl executions prompt with the code shown, closing the Phase 2 bypass (per D-11)
  artifacts:
    - strands_code_cli/policy.py (DiffConfig-mirror TOML store + match engine + network classification)
    - strands_code_cli/policy_gate.py (custom classifier + custom ask + evaluate + BatchState + build_interventions)
    - strands_code_cli/main.py (interventions=[single HITL] wiring)
    - strands_code_cli/router.py (/policy show branch)
    - tests/test_policy.py
    - tests/test_policy_gate.py
  key_links:
    - main.py build_agent passes interventions=[HumanInTheLoop(allowed_tools, classifier, ask)] to create_harness; never "ask"/"smart"/NL-string/Cedar
    - policy_gate.py classifier owns TOML matching (sees BeforeToolCallEvent tool name + input); ask owns rendering only
    - diff_gate.py approve-each branch passes through when gate_active=True; no second prompt by construction
    - scope.py confine admits union(cwd, /tmp, allow-rule-granted roots); policy match runs before confine
    - router.py /policy show is reply-only; approval prompts live in the gate layer, never as router replies
  prohibitions:
    - MUST NOT construct two HumanInTheLoop instances (SDK name collision raises; RESEARCH §6.1 BLOCKING)
    - MUST NOT use "smart", NL-policy strings, LLMClassifierConfig, or Cedar (D-05 determinism; RESEARCH §1.3 ruled out)
    - MUST NOT add Phase 4 mode-system vocabulary (plan/act/yolo/auto, effort presets) to the policy schema (RESEARCH risk 10)
    - MUST NOT build semantic/LLM risk classification or a host allowlist (deferred; D-16)
    - MUST NOT route approval prompts through router reply actions (races the prompt; router.py:70-75)
    - MUST NOT use enable_trust=True as the D-03/D-04 mechanism (per-tool granularity, wrong shape; RESEARCH §1.4)
  assumptions:
    - FLAGGED ASSUMPTION (deny-continuation probe): Deny surfaces as a tool-cancellation message the agent explains mid-turn and continues (D-02); tracer verifies live, Guide-action fallback if the agent loops
    - FLAGGED ASSUMPTION (inner-call probe): programmatic_tool_caller inner tool calls route through before_tool_call interventions; tracer verifies, pins the builtin off if not
    - FLAGGED ASSUMPTION (fetch-transport probe): web_fetch runs the default "curl" (sandboxed) transport in this repo; tracer records the observed transport
---

<objective>
Tracer slice first: prove the whole Phase 3 stack end to end with one production-quality path — a live turn where a shell mutation prompts with full detail, a deny skips-and-continues, and an allow-ruled read proceeds silently — then flesh out the TOML policy store, classifier/ask gate layer, /diff coordination, scope ordering, and network classification around that proven spine.

Purpose: Land deny-first enforced approval (TOOL-03) on the single-HITL seam so Phase 4 builds Plan/Act on top of a proven gate.
Output: TOML policy store + match engine, single-instance gate layer with batching and remember-me, build_agent wiring, /diff subsumption, /policy show, and passing tests per task.
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
@.planning/phases/03-permissions-gate/03-CONTEXT.md
@.planning/phases/03-permissions-gate/03-RESEARCH.md
@.planning/phases/02-file-edit-shell-surface-diff/02-CONTEXT.md
@.planning/phases/02-file-edit-shell-surface-diff/02-SECURITY.md
@.planning/codebase/ARCHITECTURE.md
@.planning/codebase/STACK.md
</context>

<resolved_open_items>
Planner resolutions. Executor implements exactly these; no re-derivation.

1. repo-vs-home merge-vs-override → LAYERED UNION (merge, not replace). Home `~/.config/strands-code/policy.toml` (platformdirs user-config dir, same as `default_diff_config_path`, diff_config.py:32-34) provides defaults; repo `./.agent/policy.toml` layers over it. Evaluation collects matching rules across both files + builtins; deny-wins across the union (D-07). Rationale: replacing home entirely would silently drop the user's home denies — unsafe. Repo rules are checked first only for explanation order.
2. deny-rule prompt-vs-hard-deny → HARD-DENY, no prompt. A deny match refuses immediately with the matched rule shown (`Denied by policy rule [deny shell "curl*"] — skipped, continuing.`). Rationale: prompting on an explicit deny defeats deny-first; D-01 transparency is satisfied by naming the rule; D-02 skip-and-continue applies unchanged.
3. sh -c normalisation level → NORMALISE-THEN-SPLIT: strip leading whitespace; unwrap one level of `sh -c` / `bash -c` / `sh -lc` with matching quotes (once, not recursively); then (a) allow-rules match on PREFIX of the normalised command, (b) network detection scans the normalised string for SUBSTRING binary names. Residual documented, not closed: `VAR=curl; $VAR x`, pipes into interpreters (`curl x | sh` — still contains the `curl` substring, so it prompts as network, but intent is unreadable), exotic binaries (accepted per D-14), `python_repl` socket code (all-or-nothing prompt, risk 5).
4. batcher location (risk 8) → TURN-SCOPED CACHE in the gate layer (`BatchState` in `policy_gate.py`), NOT in the HITL handler and NOT in the router. Honest constraint: tool calls execute sequentially, so upfront listing of future actions is impossible; D-04 is implemented as one prompt per (matched-rule-key, turn) — the first matching call prompts with full detail naming the covering rule, later same-key calls in the turn proceed silently and are recorded. `bind_turn(turn_id)` is called from `loop.py` before each `agent(text)`; `BatchState` also keeps the covered-action descriptions retrievable for `/policy last`. No time-window collector (unverifiable timing coupling).
5. ask-contract reconciliation (diff_gate bool vs HITL response) → KEEP BOTH, divided by layer. `diff_gate.py:41 AskCallable = Callable[[str], bool]` stays unchanged (Phase 2 locked). The HITL ask is a separate `policy_ask(prompt, **kwargs) -> str` returning a canonical `"y"`/`"n"`; `evaluate` stays `default_evaluate` (already accepts `True`/`"y"`); the D-03 remember-write happens INSIDE `policy_ask` (which closes over tool name + input), never in `evaluate`. Subsumption (item 6) means production `approve-each` never calls the bool ask when the gate is active — the two contracts never wrap each other.
6. /diff coordination (§5) → OPTION 1: gate subsumes approve-each. `make_gated_write`/`make_gated_edit` take a `gate_active: bool = False` constructor kwarg (repo constructor-kwarg convention); when True the `approve-each` branch skips its own `ask` and falls through to the exact-once apply path, keeping diff rendering + stash/apply machinery. `build_agent` wires `gate_active=True`. `on-demand`/`auto` are orthogonal by construction (stash-vs-apply is not approval). Invariant: `/diff apply` never re-prompts (`apply_stashed` uses `_fs_write`, not a tool call — the intervention never sees it; state in code comment). Options 2 (verdict threading) rejected as coupling; 3 (retire mode) rejected — Phase 2 modes are locked.
7. corrupt-policy fail direction (risk 11) → FAIL-CLOSED. Any parse/schema violation (bad TOML, unknown key, unknown tool name, malformed rule) → log warning + fall back to built-in defaults, i.e. prompt-on-everything-mutating. Missing files → defaults. Symlinked policy PATH (repo or home) → `ValueError` fail-loud (mirror `DiffConfig.load`, diff_config.py:51-52). Never fail-open (allow-all on corrupt file inverts deny-first).
8. programmatic_tool_caller live-or-not (risk 9) → TRACER DECIDES (conditional task 1): probe whether its inner tool calls pass through `before_tool_call`. If gated → leave on, record evidence. If bypassed/unverifiable → pin `programmatic_tool_caller: False` in the `builtin_tools` mapping with a comment; convenience yields to airtightness. `web_fetch`/`web_search`/`subagent` are live today (default set, harness agent.py:313-314; mapping pins only shell/read/write/edit) and ARE seen by the intervention (every tool call fires `before_tool_call`): `web_fetch`+`web_search` are covered by built-in fetch-class allow rules (any host per D-16; default transport `"curl"` sandboxed); `subagent` inherits the gate automatically (D-12).

Full TOML schema (user-facing contract, costly reversibility — print exactly this):

```toml
[options]
trust_delegated = false  # D-12: true skips prompts inside delegated (subagent) turns

[[allow]]                # proceed silently
tool = "shell"           # required: known tool name or "*"
command = "git status"   # shell/python_repl: prefix of normalised command/code

[[allow]]
tool = "write"           # file tools: write | edit (read/search need no rules)
path = "docs/*.md"       # glob via fnmatch; matched against repo-relative AND absolute realpath

[[deny]]                 # hard-deny, no prompt, rule named in refusal
tool = "shell"
command = "curl"
```

Schema rules: `tool` required (known name or `"*"`); exactly one of `path` (file tools) or `command` (shell, python_repl) per rule; the D-03 appender emits narrow rules only (never `tool = "*"`). Built-in defaults shipped in code (no first-run file creation, `DEFAULT_MODE` precedent diff_config.py:27): allow `read`, `search`; fetch-class allows (`curl` GET-shaped, `git fetch`); everything mutating prompts.
</resolved_open_items>

<tasks>

<task type="tracer">
  <name>[~] Live gate spine — one HITL, deny-continues, builtin liveness probes</name>
  <files>strands_code_cli/main.py, strands_code_cli/policy_gate.py, tests/test_policy_gate.py</files>
  <read_first>.venv/lib/python3.14/site-packages/strands/vended_interventions/hitl/hitl.py:135-145 (allowed_tools), 232-276 (ask semantics, approval precedence); .venv/lib/python3.14/site-packages/strands_harness/agent.py:329-337 (subagent inheritance), 313-314 (default builtin set)</read_first>
  <action>Prove the spine before building on it. (a) Construct `HumanInTheLoop(allowed_tools=["read"], classifier=<stub>, ask=<stub>)` and pass as `interventions=[...]` through `create_harness` — record that construction succeeds and that adding a second instance raises (collision rule, RESEARCH §6.1). (b) Live turn: agent attempts a shell mutation, stub ask denies → observe the agent explains what it skipped and CONTINUES the turn (D-02); if it retries identically in a loop, record the Guide-action/steering fallback need, do not build it yet. (c) Liveness probes: assert `web_fetch`/`web_search`/`programmatic_tool_caller`/`subagent` are live under the current mapping; check `web_fetch` transport value; drive one `programmatic_tool_caller` inner mutation and observe whether `before_tool_call` fires for the inner call — if bypassed/unverifiable, pin `programmatic_tool_caller: False` in the mapping with a comment citing risk 9, else leave on with evidence in the test docstring. (d) TDD: kwargs assertion that `interventions` reaches `create_harness` as a single-element list holding one HumanInTheLoop (copy the test_code_agent.py mock-Agent kwargs-assertion pattern). Record all observations in tests/test_policy_gate.py module docstring.</action>
  <verify>
    <automated>uv run pytest tests/test_policy_gate.py -x -q</automated>
    <fails_when>exit code != 0 or output contains FAILED or ERROR</fails_when>
  </verify>
  <done>Single-HITL construction proven; deny-continue observed live (or fallback recorded); programmatic_tool_caller pinned-off-or-proven-gated; kwargs test green.</done>
  <acceptance_criteria>Deny live-turn behaviour evidenced in test docstring; no second HumanInTheLoop anywhere; conditional pin decision documented with observation.</acceptance_criteria>
  <reversibility>Reversible — probe code plus one mapping line; deleting restores Phase 2 wiring.</reversibility>
</task>

<task type="auto">
  <name>[P1] Policy store — DiffConfig-mirror TOML, layered merge, fail-closed</name>
  <files>strands_code_cli/policy.py, tests/test_policy.py</files>
  <read_first>strands_code_cli/diff_config.py:37-94 (dataclass, fail-soft load, symlink refusal, atomic save, 0o700, platformdirs); strands_code_cli/scope.py:21-52 (resolve+confine, ValueError-naming-roots shape)</read_first>
  <action>Per D-05/D-08 and resolved items 1+7 create strands_code_cli/policy.py: `PolicyConfig{options: PolicyOptions{trust_delegated: bool = False}, allow: list[Rule], deny: list[Rule]}` mirroring the DiffConfig shape exactly (dataclass, platformdirs home `strands-code/policy.toml`, repo `./.agent/policy.toml` layered over home as UNION, symlink refusal fail-loud ValueError on either path, atomic tmp+replace save, 0o700 home dir) but TOML via stdlib `tomllib` (no new dependency); D-03 append serialises the repo's own narrow rule schema by hand (no TOML writer dep). Load posture: missing → built-in defaults; ANY parse/schema violation (bad TOML, unknown key, unknown tool, missing path-and-command) → warning + built-in defaults = prompt-all-mutating (fail-closed, never allow-all). TDD: home+repo layering union, deny-wins needs no store test (engine task), corrupt-file prompts-all, symlink raises, append round-trips, missing files yield defaults.</action>
  <verify>
    <automated>uv run pytest tests/test_policy.py -x -q</automated>
    <fails_when>exit code != 0 or output contains FAILED or ERROR</fails_when>
  </verify>
  <done>Store loads/merges/appends per schema; corrupt means prompt-all; symlink means raise.</done>
  <acceptance_criteria>Tests cover layering, fail-closed corruption, symlink refusal, append round-trip; zero new dependencies; schema vocabulary contains no plan/act/yolo/auto words.</acceptance_criteria>
  <reversibility>Costly — TOML schema and repo-over-home layering are user-facing contracts (CONTEXT D-05/D-08); migratable, not one-way: no checkpoint.</reversibility>
</task>

<task type="auto">
  <name>[P1] Match engine + normalisation + network classification</name>
  <files>strands_code_cli/policy.py, tests/test_policy.py</files>
  <read_first>strands_code_cli/policy.py (store task output); .venv/.../strands/vended_interventions/hitl/classifier.py:19-33 (HumanInTheLoopClassifier protocol, ClassifierResult)</read_first>
  <action>Per D-06/D-07/D-13/D-14/D-15 and resolved items 2+3 implement pure functions in policy.py (no HITL imports here): `normalise_command(cmd)` (strip, unwrap one `sh -c`/`bash -c`/`sh -lc` quote level); `match_rule(rule, tool_name, input)` (path rules: fnmatch against repo-relative + absolute realpath; command rules: prefix on normalised command/code); `decide(tool_name, input, policy)` → `Allow | Prompt(reason) | Deny(rule)` with deny-wins across union, built-in read/search allows, fetch-class allows (curl GET-shaped: no `-X POST/PUT/DELETE/PATCH`, no `-d/--data*/--upload-file/-T/--form`; `git fetch`), uploads/mutations → Prompt; network binaries substring-scanned (`curl wget aria2c ssh scp rsync ftp sftp`), `git push/pull`, `gh` → at least Prompt. Outside-scope file paths with no covering allow rule → Deny naming allowed roots (preserve test_tool_surface.py:91 shape). TDD: deny-wins conflict, allow-proceeds, no-rule-prompts, GET-allowed vs POST-prompted, `sh -c "curl …"` detected as network, outside-path-denied-names-roots, python_repl code prefix match. Document the accepted residuals in the module docstring (VAR indirection, exotic binaries, python_repl interior confinement).</action>
  <verify>
    <automated>uv run pytest tests/test_policy.py -x -q</automated>
    <fails_when>exit code != 0 or output contains FAILED or ERROR</fails_when>
  </verify>
  <done>Decision matrix green; normalisation level pinned by tests; residuals documented.</done>
  <acceptance_criteria>Every D-06/D-07/D-13/D-14/D-15 behaviour has a test; no LLM/NL classification anywhere; no host allowlist.</acceptance_criteria>
  <reversibility>Reversible — pure functions; pattern list is the agent's-discretion content, freely extendable.</reversibility>
</task>

<task type="auto">
  <name>[P1] Gate layer — classifier + ask + BatchState + single HITL builder</name>
  <files>strands_code_cli/policy_gate.py, tests/test_policy_gate.py</files>
  <read_first>.venv/.../strands/vended_interventions/hitl/hitl.py:27-84 (AskCallback, stdio ask — do NOT reuse), 232-251 (None=fail-closed deny, raise=abort); strands_code_cli/output.py:21-30 (output_context proxy); strands_code_cli/diff_gate.py:318-320 (_default_ask prototype)</read_first>
  <action>Per D-01/D-02/D-03/D-04/D-12 and resolved items 4+5 create strands_code_cli/policy_gate.py: `PolicyClassifier` (custom classifier: reads BeforeToolCallEvent name+input, calls decide(); Deny → requires_approval False + reason carrying the hard-deny so ask short-circuits to refusal text; Allow → no approval; Prompt → approval with full-detail pre-format); `policy_ask(prompt, **kwargs) -> str` rendering inside output_context (exact command or diff + one-line risk reason per D-01; answers y/n/always/never; always/never appends the narrow derived rule to the REPO policy file atomically then returns canonical y/n — D-03 write lives here, evaluate stays default); `BatchState` turn-cache keyed by matched-rule signature with `bind_turn(turn_id)` + covered-action log for `/policy last`; `build_interventions(policy_loader)` returning EXACTLY ONE `HumanInTheLoop(allowed_tools=["read", "search"], classifier=..., ask=...)`; `bind_main_agent(agent)` for D-12 `trust_delegated` detection (unbound/unknown agent → prompt, fail-closed). Custom ask catches internally and returns `"n"` on error (callback raise aborts the run — must not leak). TDD with fake events: allow-silent, prompt-once-per-rule-per-turn, deny-short-circuit-names-rule, always-appends-narrow-rule, trust_delegated skips only non-main agent, ask-error returns deny.</action>
  <verify>
    <automated>uv run pytest tests/test_policy_gate.py -x -q</automated>
    <fails_when>exit code != 0 or output contains FAILED or ERROR</fails_when>
  </verify>
  <done>One HITL carries allowlist+classifier+ask; batching, remember-me, and delegation flag behave per D-03/D-04/D-12.</done>
  <acceptance_criteria>Tests prove single-instance construction, per-turn single-prompt, rule-naming denials, narrow-rule append; no enable_trust, no second handler.</acceptance_criteria>
  <reversibility>Reversible — new module; removing build_interventions restores ungated wiring.</reversibility>
</task>

<task type="auto">
  <name>[P1] build_agent wiring — interventions + gate_active + turn binding</name>
  <files>strands_code_cli/main.py, strands_code_cli/loop.py, tests/test_policy_gate.py</files>
  <read_first>strands_code_cli/main.py:73-109 (build_agent mapping + consumer tools); strands_code_cli/loop.py:98-135 (agent(text) inside output_context)</read_first>
  <action>Wire the gate in build_agent: add `interventions=build_interventions(...)` to kwargs (one line plus construction; keep the builtin_tools mapping shape, add only the tracer-decided programmatic_tool_caller pin); pass `gate_active=True` into make_gated_write/make_gated_edit; call `bind_main_agent(agent)` post-construction (D-12 detection); call `bind_turn(new id)` in loop.py before each `agent(text)` inside the existing output_context wrap so BatchState resets per turn (custom ask already renders inside output_context — no loop rendering change). Deny-skip-and-continue needs no loop change (tracer-proven). Extend the tracer kwargs test: interventions single-HITL + gate_active reaching wrappers.</action>
  <verify>
    <automated>uv run pytest tests/test_policy_gate.py tests/test_tool_surface.py tests/test_diff_gate.py -q</automated>
    <fails_when>exit code != 0 or output contains FAILED or ERROR</fails_when>
  </verify>
  <done>Production agent prompts once per rule per turn; reads/search silent; loop binds turns.</done>
  <acceptance_criteria>Existing Phase 2 suites stay green; kwargs test covers interventions + gate_active; no router changes here.</acceptance_criteria>
  <reversibility>Reversible — three small wiring edits; dropping them restores Phase 2 behaviour.</reversibility>
</task>

<task type="auto">
  <name>[P2] /diff subsumption — approve-each pass-through, no-double-prompt proof</name>
  <files>strands_code_cli/diff_gate.py, tests/test_diff_gate.py</files>
  <read_first>strands_code_cli/diff_gate.py:229-272 (_gate_and_apply mode branch); strands_code_cli/diff_gate.py:323-416 (wrapper factories)</read_first>
  <action>Per resolved item 6 add `gate_active: bool = False` kwarg to make_gated_write/make_gated_edit (default False keeps standalone/test behaviour = Phase 2 contract); when True the `approve-each` branch skips its per-hunk `ask` and falls through to the exact-once re-read+apply path, keeping diff rendering, on-demand stash, auto, and TOCTOU failure untouched. Comment the invariant: `/diff apply` never re-prompts (router-side `_fs_write`, invisible to interventions). TDD: gate_active write prompts exactly once total (counting HITL ask invocations with gate on + approve-each mode = 1); gate_inactive approve-each still prompts per hunk (Phase 2 lock); on-demand stash then `/diff apply` applies silently.</action>
  <verify>
    <automated>uv run pytest tests/test_diff_gate.py tests/test_policy_gate.py -q</automated>
    <fails_when>exit code != 0 or output contains FAILED or ERROR</fails_when>
  </verify>
  <done>D-10 holds: one prompt total per write under gate + approve-each; modes otherwise unchanged.</done>
  <acceptance_criteria>No-double-prompt test counts ask invocations == 1; Phase 2 mode matrix still green; AskCallable bool contract untouched.</acceptance_criteria>
  <reversibility>Costly — touches the Phase 2 gate every mutation flows through; default-False kwarg keeps it back-compatible. No checkpoint (code-reversible).</reversibility>
</task>

<task type="auto">
  <name>[P2] Scope-policy ordering + /policy show</name>
  <files>strands_code_cli/scope.py, strands_code_cli/router.py, tests/test_tool_surface.py</files>
  <read_first>strands_code_cli/scope.py:35-67 (confine + ScopeGuard); strands_code_cli/router.py:29-67 (dispatch tri-state), 70-105 (_diff_message reply-only pattern)</read_first>
  <action>Per D-13 and risk 6: policy match runs BEFORE confine — implement `effective_roots(cwd, policy)` = cwd + /tmp + realpaths of absolute allow-rule `path` globs' base dirs; `confine` keeps its ValueError-naming-roots shape (test_tool_surface.py:91 stays green). Order per action: resolve → policy decide (may grant roots) → confine against union → prompt unless allowed. Router: add `/policy show` (effective rules: builtins + home + repo, deny-wins note) and `/policy last` (BatchState covered-action log) as REPLY-ONLY branches following the _diff_message pattern; update USAGE_HINT. Approval prompts MUST NOT live here. TDD: outside-path-with-allow-rule admitted, without → denied naming roots; /policy tri-state (show/last/bogus → usage, never agent turn).</action>
  <verify>
    <automated>uv run pytest tests/test_tool_surface.py tests/test_cli_entry.py -q</automated>
    <fails_when>exit code != 0 or output contains FAILED or ERROR</fails_when>
  </verify>
  <done>Policy-owned expansion works; scope error shape preserved; /policy is inspect-only.</done>
  <acceptance_criteria>Ordering tests green; router tests mirror the unknown-slash-hints-never-agent-turn pattern; no prompt code in router.</acceptance_criteria>
  <reversibility>Reversible — additive roots computation plus two reply branches.</reversibility>
</task>

<task type="auto">
  <name>[P2] python_repl gating proof + delegated-turn e2e + messaging check</name>
  <files>strands_code_agent/code_agent.py, tests/test_policy_gate.py</files>
  <read_first>strands_code_agent/code_agent.py:139-150 (python_repl assembly); strands_code_agent/callback_handler.py (tool display; D-01 full-detail prompts may reuse its Rich Syntax("diff") branch — coordinate, no second diff renderer)</read_first>
  <action>Per D-11/D-12 close the loop: (a) prove `python_repl` calls fire `before_tool_call` (prompt shows the code string, all-or-nothing per execution — state in test docstring that approval does NOT imply file/network confinement inside the snippet, risk 5); no tool-code change needed. (b) Delegated-turn e2e with fake child agent: default inherits-and-prompts; `trust_delegated=true` skips prompts for non-main agent only (never widens the child tool set). (c) Verify deny-skip agent messaging reads sanely (D-02 phrasing is the agent's discretion — assert the Deny reason reaches the model, not exact words). (d) One-line prompt-steering note in CODE_AGENT_INSTRUCTIONS only if the tracer saw looping; otherwise touch nothing here. TDD: repl-prompted-with-code, delegate-prompts-by-default, trust-flag-skips, deny-reason-propagates.</action>
  <verify>
    <automated>uv run pytest tests/test_policy_gate.py tests/test_code_agent.py -q</automated>
    <fails_when>exit code != 0 or output contains FAILED or ERROR</fails_when>
  </verify>
  <done>D-11/D-12 closed with tests; interior-confinement limit documented; no Phase 4 vocabulary added.</done>
  <acceptance_criteria>Four e2e tests green; code_agent.py prompt diff minimal-or-empty; callback handler gains no duplicate diff renderer.</acceptance_criteria>
  <reversibility>Reversible — tests plus at most a prompt comment.</reversibility>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Agent tool call→side effect | Every mutation (write/edit/shell/python_repl/web_fetch) passes one HumanInTheLoop: TOML decide → allow / prompt / hard-deny |
| Policy file→gate verdict | Home + repo TOML shape the verdict; corrupt input fails closed to prompt-all, symlinks fail loud |
| Approval prompt→mutation | One prompt verdict covers one (rule-key, turn); BatchState cache never crosses turns |
| Repo policy file→user trust | D-03 appends narrow derived rules only (never `*`); user reviews via `/policy show` |
| Shell text→OS | Prefix-matched allows, substring-scanned network detection; exotic-binary/VAR-indirection residual accepted per D-14 |
| Code snippet→interpreter | python_repl approval is all-or-nothing; interior `open()`/`socket` unconfined (stated, not closed) |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-03-01 | Tampering | Second HITL colliding at construction | high | mitigate | Exactly one HumanInTheLoop built in one site (policy_gate.build_interventions); tracer proves collision on two. BLOCKING until green. |
| T-03-02 | Tampering | Corrupt policy failing open to allow-all | high | mitigate | Any schema violation → built-in defaults (prompt-all-mutating); symlink → ValueError. BLOCKING until green. |
| T-03-03 | Tampering | Scope-check before policy-check voiding expansion grants | high | mitigate | Order resolve → decide → confine-against-union; ordering tests. BLOCKING until green. |
| T-03-04 | Tampering | Double-prompt fatigue → blind yes (approve-each + gate) | medium | mitigate | Gate subsumes approve-each (gate_active pass-through); ask-count test == 1. BLOCKING until green. |
| T-03-05 | Tampering | programmatic_tool_caller inner calls bypassing the gate | high | mitigate | Tracer probes inner-call gating; pin off if bypassed. BLOCKING until decided. |
| T-03-06 | Tampering | D-03 self-modifying policy (over-broad agent-driven rules) | medium | mitigate | Appender emits narrow derived rules only, atomic write, symlink refusal; `/policy show` review path. |
| T-03-07 | Tampering | `sh -c`/prefix evasion of command rules | medium | accept+document | One-level unwrap + prefix-allow/substring-deny split; VAR-indirection + exotic binaries accepted per D-14. |
| T-03-08 | Tampering | python_repl interior file/network acts post-approval | medium | accept+document | Prompt shows code (D-11); approval explicitly all-or-nothing (risk 5). |
| T-03-09 | Information disclosure | GET-URL param exfiltration under pre-allowed fetch | low | accept | Explicitly accepted in D-15/CONTEXT; host allowlist deferred. |
| T-03-10 | Denial of service | Shell long-run (curl/uploads, unpinned 120s default) | low | accept+document | Residual from 02-SECURITY #2 re-recorded; livelier with network, still upstream default. |
| T-03-11 | Spoofing | Batch cache crossing turns auto-approving stale actions | medium | mitigate | Cache keyed per turn, reset by bind_turn from loop.py; cross-turn reuse test refuses. BLOCKING until green. |
| T-03-12 | Spoofing | Delegated turn silently trusted | medium | mitigate | trust_delegated defaults False; unbound agent → prompt (fail-closed); never widens child tools. |
</threat_model>

<verification>
- `uv run pytest tests/ -q` stays green (TDD per task; new tests/test_policy.py, tests/test_policy_gate.py).
- Live REPL check: shell mutation prompts with full detail (command + risk reason); deny skips and the turn continues; `always` appends a narrow rule and the next identical action proceeds silently; `/diff show` + `/policy show` report; `/diff apply` never re-prompts.
- Planner scans: API-coverage — no external REST API (tomllib + fnmatch stdlib only, no new dependency); assumption-delta — deny-continuation, inner-call, and fetch-transport probes recorded in test docstrings; schema-gate — no ORM files (TOML policy + sidecar JSON are not ORM models, no migration needed).
- Scope-bleed audit: no Phase 4 mode vocabulary, no semantic classification — grep the diff for `smart`, `LLMClassifier`, `cedar`, `enable_trust`, `\bplan\b.*mode`, `\bact\b.*mode`, `yolo`, `strands_tools` before merge.
</verification>

<success_criteria>
- Roadmap §Phase 3 criterion 1: approval/deny prompt precedes edits, shell, and network actions (TOOL-03, D-01/D-02/D-11/D-14).
- Roadmap §Phase 3 criterion 2: standing allow/deny rules quiet routine actions while dangerous ones stay gated (TOOL-03, D-03/D-05/D-06/D-07/D-09).
- Full suite green; corrupt policy prompts-all; scope refusals name allowed roots; residuals documented, not silently closed.
</success_criteria>

<output>
Create `.planning/phases/03-permissions-gate/03-PLAN-SUMMARY.md` when done
</output>

## Artifacts This Phase Produces

New symbols: `strands_code_cli.policy.PolicyConfig/Rule/decide/normalise_command`, `strands_code_cli.policy_gate.PolicyClassifier/policy_ask/BatchState/build_interventions/bind_main_agent/bind_turn`.
New commands: `/policy show`, `/policy last`.
New files: `strands_code_cli/policy.py`, `strands_code_cli/policy_gate.py`, `tests/test_policy.py`, `tests/test_policy_gate.py`.
Decisions for downstream: single-HITL gate spine (Phase 4 Plan/Act approval checkpoint builds on BatchState/ask, not a second handler); `policy.toml` allow/deny vocabulary frozen (Phase 4 must not reuse rule/mode words); scope roots now policy-expandable (further widening re-opens D-13).
