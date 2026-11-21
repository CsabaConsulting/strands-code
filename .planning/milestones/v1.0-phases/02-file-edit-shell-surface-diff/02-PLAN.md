---
phase: 02-file-edit-shell-surface-diff
plan: 02
type: execute
wave: 1
depends_on: []
files_modified:
  - strands_code_cli/main.py
  - strands_code_cli/router.py
  - strands_code_cli/diff_config.py
  - strands_code_cli/scope.py
  - strands_code_cli/diff_gate.py
  - strands_code_agent/code_agent.py
  - strands_code_agent/callback_handler.py
  - strands_code_agent/search_tool.py
  - tests/test_tool_surface.py
  - tests/test_diff_gate.py
  - tests/test_search.py
autonomous: true
requirements: [TOOL-01, TOOL-02, TOOL-04]
estimate:
  tokens: 60000
  raw_tokens: 40000
  tasks: 7
  confidence: med
must_haves:
  truths:
    - Agent reads, writes, edits files and runs shell commands through harness builtins in a live turn (per TOOL-01, D-02)
    - User reviews pending changes via /diff in approve-each, on-demand, or auto mode before they apply (per TOOL-02, D-04)
    - Agent and user navigate repos with grep plus on-the-fly symbol context, no index maintained (per TOOL-04, D-08, D-09)
    - File mutations outside cwd+subdirs+/tmp are refused by app code, with expansion left to Phase 3 policy (per D-07)
  artifacts:
    - strands_code_cli/main.py (builtin_tools mapping)
    - strands_code_cli/scope.py
    - strands_code_cli/diff_config.py
    - strands_code_cli/diff_gate.py
    - strands_code_agent/search_tool.py
    - strands_code_agent/callback_handler.py (diff + search rendering)
    - strands_code_cli/router.py (/diff, /search branches)
    - tests/test_tool_surface.py
    - tests/test_diff_gate.py
    - tests/test_search.py
  key_links:
    - main.py build_agent passes builtin_tools mapping to create_harness; never imports strands_tools
    - scope.py resolve+confine wraps every file-tool path before the harness _validate_path absolute check
    - diff_gate.py wrappers replace builtin write/edit (pinned off) and consult diff_config.py mode
    - router.py /diff and /search dispatch; approval prompts live in the gate layer, never as router replies
    - callback_handler.py renders unified diffs via Rich Syntax("diff") inside output_context
  prohibitions:
    - MUST NOT add strands-agents-tools as a dependency or import strands_tools.* (deprecated editor/shell, not installed; RESEARCH §1.1)
    - MUST NOT build the Phase 3 deny-first policy file, general approval prompts, or network gating (TOOL-03 bleed; RESEARCH §6.8)
    - MUST NOT build a general auto/yolo mode covering all tool calls (D-05, deferred to Phase 4 mode system)
    - MUST NOT build a persistent code index or embeddings (Out of Scope table; D-09)
    - MUST NOT route diff approval through router reply actions (races the prompt; loop.py:118-124)
  assumptions:
    - FLAGGED ASSUMPTION (harness defaults probe): build_agent today inherits the harness default builtin set (shell/read/write/edit live) since it never touches builtin_tools (RESEARCH §1.3); tracer verifies with a live turn before pinning
    - FLAGGED ASSUMPTION (rg availability probe): ripgrep binary present where the CLI runs; search tool falls back to stdlib walk when rg is absent
    - FLAGGED ASSUMPTION (shell-advisory probe): /diff gate covers write/edit tools only; shell redirection (echo >/sed -i) and python_repl open() bypass it — documented advisory, airtight mediation is Phase 3 interventions (RESEARCH §6.2, §6.6)
---

<objective>
Tracer slice first: prove the whole Phase 2 stack end to end with one production-quality path — live agent turn reading a file, editing it through the diff gate, running shell, grepping via the new tool — then flesh out scope enforcement, /diff modes, /search UX, and prompt/callback rendering around that proven spine.

Purpose: Land real actuation (TOOL-01/02/04) on the harness builtin seam with the diff gate proven before Phase 3 builds approval policy on top of it.
Output: builtin_tools wiring, cwd+/tmp scope guard, rg-wrapper search tool, /diff + /search commands, wrapper-based diff gate with persisted mode, python_repl role definition, and passing tests per task.
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
@.planning/phases/02-file-edit-shell-surface-diff/02-CONTEXT.md
@.planning/phases/02-file-edit-shell-surface-diff/02-RESEARCH.md
@.planning/research/SUMMARY.md
@.planning/codebase/ARCHITECTURE.md
@.planning/codebase/STACK.md
</context>

<tasks>

<task type="tracer">
  <name>[~] Live builtin spine — verify defaults, pin mapping, smoke read/shell/edit</name>
  <files>strands_code_cli/main.py, tests/test_tool_surface.py</files>
  <read_first>.venv/lib/python3.14/site-packages/strands_harness/agent.py:300-340 (builtin_tools enablement); .venv/.../strands_harness/tools/file_tools.py:1-60 (validate_path); strands_code_cli/main.py:66-80 (build_agent)</read_first>
  <action>Per RESEARCH §1.3 first run one live turn against the UNMODIFIED build_agent proving shell/read/write/edit already answer (harness defaults on), and record the observed default set in the test module docstring. Then in main.py:66-80 pass an explicit builtin_tools MAPPING (not a pin list, so future upstream defaults still flow) enabling exactly shell/read/write/edit plus the new local search tool from a later task, with per-tool constructor-kwarg config only (no env sniffing, repo convention). Copy the test_code_agent.py mock-Agent.__init__ kwargs-assertion pattern (test_python_repl_tool_always_present, line 197) into tests/test_tool_surface.py asserting builtin_tools reaches create_harness and python_repl stays present. TDD: write the kwargs assertion first, watch it fail on the unmodified build_agent, then add the mapping.</action>
  <verify>
    <automated>uv run pytest tests/test_tool_surface.py -x -q</automated>
    <fails_when>exit code != 0 or output contains FAILED or ERROR</fails_when>
  </verify>
  <done>Live turn confirms default builtin set; build_agent passes an explicit mapping; kwargs test green.</done>
  <acceptance_criteria>Test asserts builtin_tools mapping content AND python_repl presence; no strands_tools import anywhere; live-turn observation recorded in test docstring.</acceptance_criteria>
  <reversibility>Reversible — deleting the mapping restores harness defaults; no state written.</reversibility>
</task>

<task type="auto">
  <name>[P1] Scope guard — cwd+subdirs+/tmp confinement plus relative-path resolution</name>
  <files>strands_code_cli/scope.py, tests/test_tool_surface.py</files>
  <read_first>.venv/.../strands_harness/tools/file_tools.py:30-34 (_validate_path absolute+no-dotdot); strands_code_agent/python_environments/local_sandboxed.py:13-34 (timeout/allowlist precedent)</read_first>
  <action>Per D-07 and RESEARCH §5 create strands_code_cli/scope.py with resolve(path, cwd) mapping relative paths against the REPL cwd then confine(path) admitting only cwd+subdirs and /tmp+subdirs, refusing symlinks escaping scope and sibling dirs with a ValueError naming the allowed roots. Constructor takes cwd (kwarg pattern); never env-sniffs. Resolve BEFORE the harness absolute-path check so cwd-centric REPL input stops erroring (RESEARCH §6.4). TDD: absolute-in-scope, relative-in-scope, sibling-refused, /tmp-admitted, symlink-escape-refused, ..-traversal-refused. Shell commands pass through unscoped (D-06 full shell); the shell/diff bypass is documented, not closed here.</action>
  <verify>
    <automated>uv run pytest tests/test_tool_surface.py -x -q</automated>
    <fails_when>exit code != 0 or output contains FAILED or ERROR</fails_when>
  </verify>
  <done>Six scope cases green; every file-tool path flows through resolve+confine.</done>
  <acceptance_criteria>Sibling-repo write refused with allowed-roots message; relative path resolves against cwd; /tmp admitted; symlink escape refused.</acceptance_criteria>
  <reversibility>Reversible — pure function module; removal restores harness-only absolute+no-.. guards.</reversibility>
</task>

<task type="auto">
  <name>[P1] Search tool — local rg-wrapper plus stdlib fallback (TOOL-04 agent side)</name>
  <files>strands_code_agent/search_tool.py, tests/test_search.py</files>
  <read_first>.venv/.../strands_harness/types/agent.py:26-36 (BuiltinToolName has no grep entry — RESEARCH §1.2); tests/test_sandboxed_python_interpreter.py:1-60 (in-repo tool test style)</read_first>
  <action>Per D-08/D-09 and RESEARCH §6.7 create strands_code_agent/search_tool.py as a thin @tool named search (no collision: grep/search absent from BuiltinToolName): search(pattern, path?, file_glob?, limit?) shells out to rg --line-number --no-heading with a timeout, falling back to os.walk+re when rg is missing; output is path:line:match lines capped at limit with a truncation note; symbol navigation is on-the-fly rg for def/class plus references (plain text match), no index, no embeddings. Input schema validates pattern non-empty and confines path via scope.py. TDD: rg-hit shape, no-match empty, missing-rg fallback (monkeypatch shutil.which to None), path-out-of-scope refused, limit truncation note.</action>
  <verify>
    <automated>uv run pytest tests/test_search.py -x -q</automated>
    <fails_when>exit code != 0 or output contains FAILED or ERROR</fails_when>
  </verify>
  <done>Agent can grep an unfamiliar repo and cite path:line hits; no index files created.</done>
  <acceptance_criteria>Tests cover hit shape, fallback, scope refusal, truncation; rg binary never required for suite green.</acceptance_criteria>
  <reversibility>Reversible — single new tool file; unregistering restores prior tool set.</reversibility>
</task>

<task type="auto">
  <name>[P2] Diff mode store — ProviderConfig-pattern persistence plus /diff + /search routing</name>
  <files>strands_code_cli/diff_config.py, strands_code_cli/router.py, tests/test_diff_gate.py</files>
  <read_first>strands_code_cli/provider_config.py:28-89 (fail-soft load, 0o700 dirs, symlink refusal, atomic save); strands_code_cli/router.py:17-42 (dispatch tri-state + USAGE_HINT line 12)</read_first>
  <action>Per D-04 and RESEARCH §4.3 create strands_code_cli/diff_config.py DiffConfig{mode: approve-each|on-demand|auto, default on-demand} copying the ProviderConfig shape exactly (dataclass, fail-soft load, symlink refusal, atomic tmp+replace save, platformdirs home, never repo-relative). In router.py:17-42 add /diff [approve-each|on-demand|auto|show] persisting the mode and rendering pending-change status, and /search <pattern> running the search tool synchronously and returning formatted hits — both as reply actions only (approval prompts MUST NOT live here; loop.py:118-124 race). Update USAGE_HINT (line 12) and copy the test_unknown_slash_hints-never-agent-turn pattern (test_cli_entry.py:66) for /diff, /diff bogus-mode, /search empty-pattern. TDD: mode round-trip, corrupt-file fail-soft default, symlink refusal, router tri-state per branch.</action>
  <verify>
    <automated>uv run pytest tests/test_diff_gate.py tests/test_cli_entry.py -q</automated>
    <fails_when>exit code != 0 or output contains FAILED or ERROR</fails_when>
  </verify>
  <done>/diff show reports mode plus pending count; mode survives restart; /search answers from REPL.</done>
  <acceptance_criteria>Persisted mode loads fail-soft; bogus mode returns usage not an agent turn; /search never triggers a model turn.</acceptance_criteria>
  <reversibility>Reversible — new config file under platformdirs home; deleting it restores on-demand default.</reversibility>
</task>

<task type="auto">
  <name>Diff gate — wrapper tools over write/edit with approve-each/on-demand/auto (TOOL-02)</name>
  <files>strands_code_cli/diff_gate.py, strands_code_cli/main.py, tests/test_diff_gate.py</files>
  <read_first>.venv/.../strands_harness/agent.py:195-215 (duplicate-registration remedy); .venv/.../strands/vended_tools/shell/shell.py:30-64 (shell bypasses file tools — RESEARCH §6.2); strands_code_cli/session_index.py:1-60 (sidecar-JSON pattern)</read_first>
  <action>Per RESEARCH §4.2 option 2 (wrapper tools — chosen over harness interventions to avoid building Phase 3 TOOL-03 machinery early, and over SDK hooks as least precedented): create strands_code_cli/diff_gate.py wrapping harness write/edit in app-level @tools with the SAME names that (a) resolve+confine paths via scope.py, (b) compute stdlib difflib.unified_diff old-vs-new, (c) consult DiffConfig mode — approve-each prompts per hunk inside the turn via the ask callable, on-demand stashes pending state as sidecar JSON (session_index.py pattern) for later /diff review, auto applies directly — (d) re-read before apply so stale-preview edit TOCTOU surfaces as exact-once failure, never silent misapply (RESEARCH §6.3). In main.py:66-80 pin OFF builtin write/edit via the builtin_tools mapping (name-collision rule, RESEARCH §6.1) and register the wrappers instead; builtin read/shell stay pinned on. Subagent turns inherit the gate (agent.py:331-333); note approve-each noise in code. TDD: approve-applies, deny-discards, on-demand-stash-then-/diff-apply, auto-applies, stale-file exact-once failure, wrapper-name collision test proving builtin write/edit pinned off.</action>
  <verify>
    <automated>uv run pytest tests/test_diff_gate.py tests/test_tool_surface.py -q</automated>
    <fails_when>exit code != 0 or output contains FAILED or ERROR</fails_when>
  </verify>
  <done>Each mode behaves per D-04 granularity (per-hunk / whole-change / none); no duplicate-registration error at construction.</done>
  <acceptance_criteria>Mode matrix green; TOCTOU case fails loudly; shell-bypass advisory documented in module docstring; zero Phase 3 policy-file code.</acceptance_criteria>
  <reversibility>Costly — the gate shapes every file mutation and the Phase 3 policy file builds on its pending-state schema; changing mechanisms later re-opens reviewed decisions. No checkpoint: still code-reversible (re-enable builtins, drop wrappers), only expensive, not one-way.</reversibility>
</task>

<task type="auto">
  <name>[P2] Rendering — diff + search display in callback handler inside output_context</name>
  <files>strands_code_agent/callback_handler.py, tests/test_diff_gate.py</files>
  <read_first>strands_code_agent/callback_handler.py:32-80 (code_tools map + toolResult branch); strands_code_cli/output.py:21-30 (raw-stdout proxy); strands_code_cli/loop.py:126-127 (output_context wrap of agent turn)</read_first>
  <action>Per RESEARCH §4.1 extend the callback handler code_tools map with a diff branch: write/edit/search tool calls render via rich.syntax.Syntax — unified_diff body as Syntax("diff"), search hits as plain path:line text — printed inside the existing output_context wrap (loop.py:126-127) so raw stdout holds; per-hunk approve-each rendering splits difflib hunks with hunk headers. Unit-test rendering with a fake message dict (no live model): diff body contains +++ / --- markers through Syntax("diff"), search hits contain path:line prefixes. No new dependency (rich>=13 already in pyproject.toml).</action>
  <verify>
    <automated>uv run pytest tests/test_diff_gate.py -q</automated>
    <fails_when>exit code != 0 or output contains FAILED or ERROR</fails_when>
  </verify>
  <done>Diffs and search hits render readably in-turn; no output outside output_context.</done>
  <acceptance_criteria>Rendering tests assert diff markers and hit prefixes; handler still falls through for unknown tools.</acceptance_criteria>
  <reversibility>Reversible — additive display branches; removal restores generic key: value dump.</reversibility>
</task>

<task type="auto">
  <name>[P2] python_repl role + prompt — compute-only steering, write ability preserved via tools (D-03)</name>
  <files>strands_code_agent/code_agent.py, strands_code_cli/main.py, tests/test_tool_surface.py</files>
  <read_first>strands_code_agent/code_agent.py:12-17 (CODE_AGENT_INSTRUCTIONS), 131-142 (tool assembly + tools.append aliasing hazard line 140); tests/test_code_agent.py:197-215 (repl-presence + additional-tools contracts)</read_first>
  <action>Per D-03 decide: python_repl REMAINS unrestricted-compute but its instructions steer file mutation to the dedicated read/write/edit/search/shell tools (source-code write ability preserved at least for cwd+subdirs via those tools, satisfying the CONTEXT constraint without generated-Python writes). Update CODE_AGENT_INSTRUCTIONS (code_agent.py:12-17) with a tools-first paragraph: absolute paths, cwd+/tmp scope, search-before-read navigation. Fix the tools.append caller-list mutation hazard (line 140) while touching assembly — copy before append. Extend test_code_agent.py-pattern assertions: repl present, prompt names the five tools, caller list unaliased.</action>
  <verify>
    <automated>uv run pytest tests/test_tool_surface.py tests/test_code_agent.py -q</automated>
    <fails_when>exit code != 0 or output contains FAILED or ERROR</fails_when>
  </verify>
  <done>Agent prefers dedicated tools; python_repl open()-bypass documented as known advisory hole alongside shell.</done>
  <acceptance_criteria>Prompt test asserts tool names present; aliasing test proves caller list untouched; no import allowlist change.</acceptance_criteria>
  <reversibility>Reversible — prompt text only; prior instructions restorable in one edit.</reversibility>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| REPL path input→filesystem | User/agent-supplied paths become file reads/writes constrained to cwd+subdirs+/tmp |
| Diff approval prompt→mutation | One prompt verdict gates one file apply; stale reads must fail, never misapply |
| Shell text→OS | Full shell passes through; file mutations via shell bypass the diff gate (advisory) |
| rg pattern→subprocess | Pattern becomes an rg argv element, never shell-interpolated |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-02-01 | Tampering | scope.py path resolution | high | mitigate | Canonicalize (resolve symlinks), confine to cwd+subdirs and /tmp, refuse ..-escape and symlink-escape with allowed-roots error; negative tests per task. BLOCKING until green. |
| T-02-02 | Tampering | diff_gate.py stale preview (TOCTOU) | high | mitigate | Re-read target before apply; harness edit exact-once semantics surface mismatch as loud failure, never partial apply. BLOCKING until green. |
| T-02-03 | Tampering | Shell/sandbox escape via shell tool | medium | accept+document | D-06 mandates full shell; advisory documented in gate docstring and plan summary; airtight mediation is Phase 3 interventions covering all tools. |
| T-02-04 | Tampering | python_repl file writes via open() | medium | accept+document | Same bypass class as shell; prompt steers to dedicated tools; enforcement deferred to Phase 3. |
| T-02-05 | Tampering | search_tool pattern injection to shell | medium | mitigate | argv-list subprocess (no shell=True); pattern as single argv element; timeout-bounded; stdlib fallback shares no shell. BLOCKING until green. |
| T-02-06 | Information disclosure | Diff preview of sensitive files | low | accept | Preview renders only what the agent already read in-turn; no new exfiltration surface. |
| T-02-07 | Denial of service | rg over huge repos / shell long-run | low | mitigate | Result cap with truncation note; shell keeps harness 120s default timeout. |
| T-02-08 | Spoofing | Wrapper tool name collision bypassing gate | medium | mitigate | Pin off builtin write/edit in builtin_tools mapping; collision test asserts single registration. BLOCKING until green. |
</threat_model>

<verification>
- `uv run pytest tests/ -q` stays green (TDD per task; new files test_tool_surface.py, test_diff_gate.py, test_search.py).
- Live REPL check: read a repo file, edit it in approve-each mode (per-hunk prompt appears), run `ls` via shell, /search a symbol — all in one session.
- `/diff show` reports mode + pending count; mode persists across restart (DiffConfig round-trip).
- Planner scans: API-coverage — no external REST API in scope (rg subprocess + platformdirs config only); assumption-delta — harness-defaults, rg-availability, and shell-advisory probes recorded above; schema-gate — no ORM files (sidecar JSON pending state + YAML config are not ORM models, no migration needed).
- Scope-bleed audit: no policy file, no network gating, no mode system, no index, no strands-agents-tools import — grep the diff for `strands_tools`, `interventions`, `policy` before merge.
</verification>

<success_criteria>
- Roadmap §Phase 2 criterion 1: read/write/edit/shell work live in one session (TOOL-01).
- Roadmap §Phase 2 criterion 2: /diff shows pending changes per mode before apply (TOOL-02).
- Roadmap §Phase 2 criterion 3: agent answers a repo-navigation ask grounded in grep/READ with no index (TOOL-04).
- Full suite green; scope refusals name allowed roots; bypass advisories documented, not silently closed.
</success_criteria>

<output>
Create `.planning/phases/02-file-edit-shell-surface-diff/02-PLAN-SUMMARY.md` when done
</output>

## Artifacts This Phase Produces

New symbols: `strands_code_cli.scope.resolve/confine`, `strands_code_cli.diff_config.DiffConfig`, `strands_code_cli.diff_gate.{gated_write,gated_edit}`, `strands_code_agent.search_tool.search`.
New commands: `/diff [approve-each|on-demand|auto|show]`, `/search <pattern> [--glob]`.
New files: `strands_code_cli/scope.py`, `strands_code_cli/diff_config.py`, `strands_code_cli/diff_gate.py`, `strands_code_agent/search_tool.py`, `tests/test_tool_surface.py`, `tests/test_diff_gate.py`, `tests/test_search.py`.
Decisions for downstream: wrapper-gate mechanism (Phase 3 builds policy on its pending schema), DiffConfig mode vocabulary (Phase 4 must not clash its auto with mode-system auto), scope roots (widening re-opens D-07).
