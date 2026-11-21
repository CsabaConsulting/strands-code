# Phase 2 Research: File/Edit/Shell Surface + /diff

**Written:** 2026-09-25 (gsd-phase-researcher)
**Phase:** 02 — File/Edit/Shell Surface + /diff (TOOL-01, TOOL-02, TOOL-04)

## 1. Tool surface: what to wire and where it lives

### 1.1 Headline finding: do NOT add `strands-agents-tools`

`strands-agents-tools` (`from strands_tools import file_read, file_write, editor`) is the
upstream community tool pack ([strands-agents/tools](https://github.com/strands-agents/tools)),
but it is **not installed** in this repo's venv, is **not in** `pyproject.toml`, and its own
README now marks `editor` and `shell` as **deprecated** ("see Deprecations"). Its file/shell
surface has been absorbed into two places we already depend on:

- `strands-agents 1.57.0` SDK vended tools: `strands.vended_tools.make_shell` /
  `make_file_editor` (`.venv/.../strands/vended_tools/shell/shell.py:30`,
  `file_editor/file_editor.py:35`).
- `strands-harness 0.1.2` built-in tools: `shell`, `read`, `write`, `edit`, enabled by
  default via `create_harness(builtin_tools=...)`
  (`.venv/.../strands_harness/agent.py:308-316`, defaults at `defaults.py:25`).

Recommendation: wire the harness builtins (they route through the same
`tool_context.agent.sandbox` seam as the SDK editor — `tools/file_tools.py:1-11`), and
only reach for SDK `make_file_editor` if a multi-command editor (view/create/str_replace/
insert — `file_editor.py:343-405`) is wanted instead of the minimal `read`/`write`/`edit`
trio. No new dependency, no `strands_tools.*` import paths.

### 1.2 Exact import paths (verified in `.venv`)

| Tool | Import path | Factory / signature |
|------|-------------|---------------------|
| `read` | `from strands_harness.tools import read, make_read` | `make_read(media: bool = True)`; `read(path, offset=None, limit=None)`, text returns `cat -n` numbered lines, default 2000-line window (`tools/file_tools.py:62-130`) |
| `write` | `from strands_harness.tools import write` | `write(path, content)` full-overwrite (`tools/file_tools.py:133-145`) |
| `edit` | `from strands_harness.tools import edit` | `edit(path, old_str, new_str)`, `old_str` must appear exactly once (`tools/file_tools.py:148-165`) |
| `shell` | vended via harness `make_shell` | `shell_tool(command, timeout=120)`; default timeout `_DEFAULT_TIMEOUT = 120` (`vended_tools/shell/shell.py:30-64`) |
| `file_editor` (alt.) | `from strands.vended_tools import make_file_editor` | view/create/str_replace/insert/undo commands (`file_editor/file_editor.py:35-98`) |
| grep/search | **none in harness builtins** | `BuiltinToolName` is only `shell/read/write/edit/web_fetch/web_search/programmatic_tool_caller/subagent` (`harness/types/agent.py:26-36`). TOOL-04 grep must be a small local tool (ripgrep subprocess or stdlib) or `shell("rg …")` convention — planner's call |

### 1.3 How enabling works in `create_harness`

- `builtin_tools` accepts a list (pins exactly) or a mapping (edits the default set);
  `"*": False` starts from nothing: `{"*": False, "read": True}` is a pin
  (`harness/agent.py:308-316`, `harness/options.py:80-138`).
- Per-tool config: `{"read": {"media": ...}, "shell": {"description": ...}}`
  (`harness/types/agent.py:60-80`, `ReadConfig`/`ShellConfig`).
- `BuiltinToolName` has **no `environment`** entry: the context decision (D-01 says file/shell
  come from tools, not `python_repl`) is satisfiable with builtins, but there is no
  upstream "environment" file tool to import — any cwd-scope guard (D-07) is app code.
- Today `build_agent` passes `tools=[interpreter.get_tool()]` and never touches
  `builtin_tools`, so the harness **default set is already on** (shell/read/write/edit live
  today unless pinned off) — Phase 2 work is scoping, gating (`/diff`), and UX, not first
  enablement. Verify with a live turn before planning assumes otherwise.

### 1.4 Built-in path guards (relevant to D-07)

Harness `read`/`write`/`edit` share `_validate_path`: path must be **absolute** and contain
no `..` segment (`tools/file_tools.py:30-34`). That blocks traversal but does **not**
implement the D-07 scope (cwd + subdirs + `/tmp`); sibling-dir confinement needs a wrapper
or a `Sandbox` implementation choice (see §5).

## 2. Codebase map: where tool integration connects

| File | Lines | Role for Phase 2 |
|------|-------|------------------|
| `strands_code_cli/main.py` | `build_agent` 66-80 | **Tool registration point.** `tools=[interpreter.get_tool()]` + `create_harness(**kwargs)`; add `builtin_tools={...}` mapping or explicit tool list here. Constructor-kwarg config pattern (no env sniffing) already established |
| `strands_code_cli/router.py` | `dispatch` 17-42 | **`/diff` + `/search` route here.** Returns `(action, message)` tri-state (`agent`/`exit`/`reply`); new commands are new `cmd ==` branches plus `USAGE_HINT` update (line 12). `/diff` likely needs richer actions (approve/deny per hunk) than `reply` supports — planner to decide |
| `strands_code_cli/loop.py` | `run_loop` 98-135 | REPL owns `PromptSession`, `output_context()` wrap of `agent(text)` (126-127), Ctrl-C-cancels-line (112-113). Diff approval prompts must live inside the turn (tool/intervention layer), **not** as router replies, or they race the prompt |
| `strands_code_cli/output.py` | `output_context` 21-30 | All turn output flows through raw-stdout `StdoutProxy`; diff rendering must print inside this context (Rich works — `loop.py` already prints Rich via `console`) |
| `strands_code_cli/session_index.py` | 192 lines | **Sidecar-JSON pattern** for `/diff` pending-change state if the gate outlives one turn (Context §Existing Code Insights explicitly blesses this reuse) |
| `strands_code_cli/provider_config.py` | `ProviderConfig` 28-89 | Precedent for persisted user choice (fail-soft load, 0o700 dirs, symlink refusal, atomic tmp+replace save) — the template for persisting diff mode (approve-each/on-demand/auto, D-04) |
| `strands_code_agent/code_agent.py` | `CodeAgent` 39-149 | Owns `python_repl` tool assembly + system prompt. D-03 decision point: keep `python_repl` alongside new tools (note `tools.append` mutates the caller's list, line 140 — pre-existing aliasing hazard when adding more tools) |
| `strands_code_agent/callback_handler.py` | 80 lines | Renders `[Tool] name` + inputs and `[Tool Result]` via Rich (`Syntax` for code tools). **Extension point for diff display**: add a `write`/`edit` branch rendering `difflib.unified_diff` through Rich `Syntax("diff")` |
| `strands_code_agent/python_environments/` | `base.py:11`, `local_sandboxed.py:13-34` | `timeout_seconds` constructor pattern (default 60; `CodeAgent` sets 180, `code_agent.py:82`) + smolagents allowlist sandbox — the in-repo precedent §5 copies for shell |

## 3. Existing tests for tools (`tests/`)

| File | Lines | Covers — reuse as pattern |
|------|-------|---------------------------|
| `test_code_agent.py` | 277 | Tool-wiring contract: `Agent.__init__` mocked, asserts on `system_prompt`/`tools` kwargs (`_make_agent` helper, 23-33; `test_python_repl_tool_always_present` 197, `test_additional_tools_preserved` 204). **Copy this pattern** for asserting read/write/edit/shell reach `create_harness` |
| `test_sandboxed_python_interpreter.py` | 244 | Allowlist + execution behavior of the sandbox |
| `test_exec_python_interpreter.py` | 130 | Unrestricted interpreter baseline |
| `test_agentcore_python_interpreter.py` | 495 | Remote-session interpreter (idle `session_timeout_seconds=900`, `python_environments/agentcore.py:48`) — not Phase 2 scope, but shows timeout-plumbing test style |
| `test_cli_entry.py` | 271 | Router dispatch tri-state + resume picker (`test_unknown_slash_hints_never_agent_turn` 66 is the template for `/diff`/`/search` routing tests) |
| `test_kill_resume.py` | 147 | Kill-safety/session flush (SES-03, locked) |
| `test_output.py` / `test_repl_history.py` / `test_session_index.py` | 13/31/168 | Output proxy contract, history perms, sidecar index — all adjacent to `/diff` state work |
| `test_toolkits.py` | 150 | Toolkit assembly |

Gap: **no test today touches `builtin_tools`, `create_harness` kwargs, or any file/shell
tool** — Phase 2 needs new tests, and `test_code_agent.py`'s mock-`Agent.__init__` style is
the established way to write them without a live model.

## 4. Diff-gate patterns (TOOL-02 + D-04)

Two separable problems: (a) **rendering** the diff, (b) **blocking** the write until approved.

### 4.1 Rendering: stdlib + already-installed Rich

- Compute with stdlib `difflib.unified_diff` (old vs new text). For `edit`, old text is
  `read`-then-predicted-new — note the TOCTOU edge (§6.3).
- Display through Rich inside `output_context()`: `callback_handler.py` already renders
  tool calls with `rich.syntax.Syntax` (code_tools map, lines 29-33, 52-63); add
  `{"write": "diff", "edit": "diff"}`-style branch rendering unified diff. No new dependency
  (`rich>=13.0` is already one, `pyproject.toml`).
- Granularity follows D-04: per-hunk (approve-each), whole-change (normal), none (auto).
  `difflib` hunk splitting is available via `unified_diff(n=...)` context lines; per-hunk
  apply needs exact-match `edit`-style application per hunk — planner to scope.

### 4.2 Gating: three candidate mechanisms (planner picks)

1. **Harness `interventions`** (approval-native, least code): `create_harness(interventions="ask")`
   approves every call, `"smart"` LLM-classifies risk, or a natural-language policy string
   becomes the classifier prompt (`harness/interventions.py:1-60`, `agent.py:388-392`).
   `HumanInTheLoop(ask="stdio")` prompts on the terminal (`vended_interventions/hitl/hitl.py:53-84`);
   a custom `ask` callable can render the diff first and return the verdict
   (`AskCallback` contract, `hitl.py:27-34`). Subagent children **inherit** interventions
   (`agent.py:331-333`) — delegates can't bypass the gate. Caveat: this is Phase 3's
   (`TOOL-03`) machinery; Phase 2 should use it minimally (diff-gate only) without building
   the deny-first policy file, or it will bleed into Phase 3 scope.
2. **Wrapper tools** (diff-native, more code): wrap harness `write`/`edit` in app-level
   `@tool` functions that compute the diff, stash pending state (sidecar-JSON per
   `session_index.py` pattern), and consult the persisted diff mode from a
   `ProviderConfig`-style store (§2). Full control of approve-each/on-demand/auto (D-04);
   must also handle the name-collision rule (§6.1).
3. **SDK hooks** (`BeforeToolCallEvent`): `strands/hooks/` (`events.py`, `registry.py`) +
   `HumanInTheLoopClassifier(event: BeforeToolCallEvent)` (`hitl/classifier.py:29-32`)
   allow observe-and-veto at the event layer. Most flexible, least precedented in this repo —
   prefer 1 or 2 unless the planner finds 1 insufficient for per-hunk granularity.

### 4.3 Mode persistence precedent

Diff mode (D-04: approve-each / on-demand / auto; mode-switch mechanics are the planner's
call) maps 1:1 onto `ProviderConfig` (`provider_config.py:28-89`): dataclass + fail-soft
`load()` + atomic `save()`, platformdirs home, never repo-relative. Reuse, don't invent.

## 5. Shell sandboxing / timeout patterns

| Concern | Established pattern | Location |
|---------|---------------------|----------|
| Per-call timeout | `shell_tool(command, timeout=120)` default 120s (`vended_tools/shell/shell.py:54-64`); `SandboxTimeoutError` on expiry (`sandbox/errors.py:9`) | SDK vended shell |
| Interpreter timeout | `timeout_seconds` constructor kwarg: base default 60 (`base.py:11`), `CodeAgent` default 180 (`code_agent.py:82`), threaded through `LocalPythonExecutor` (`local_sandboxed.py:30`) | In-repo |
| Execution seam | Everything routes via `tool_context.agent.sandbox`: `read_text`/`write_text`/`execute` (`sandbox/base.py:219-310`); backends `PosixShellSandbox`, `DockerSandbox`, `SshSandbox` (`sandbox/docker.py:19`, `ssh.py`) | SDK |
| D-07 scope (cwd+subdirs+`/tmp`) | **Not provided by any layer**: harness guards are absolute-path + no-`..` only (§1.4). Enforce with a wrapper tool or a `Sandbox` subclass honoring constructor-kwarg config (repo convention). Sibling-repo expansion stays permission-gated (Phase 3) | Planner's call |
| Output capture | Salvage-partial-stdout-on-error precedent in `local_sandboxed.py:39-49` — copy for shell results so timeouts still show progress | In-repo |

## 6. Risky areas for TOOL-01 / TOOL-02 / TOOL-04

1. **Tool-name collisions abort construction.** Duplicate registration (e.g. wrapping `write`
   while the builtin `write` is still enabled) triggers the harness remedy path: rename or
   drop the builtin via `builtin_tools` (`agent.py:203`). Every wrapper plan must name which
   builtin it replaces and pins off.
2. **Shell bypasses the diff gate.** `echo … > file` or `sed -i` through `shell` mutates
   files without touching `write`/`edit`/any wrapper. D-06 mandates full shell from day one,
   so a `/diff` gate on write-tools only is **advisory, not airtight** — state this in the
   plan; airtight mediation is Phase 3 (`interventions` cover *all* tools including shell).
3. **`edit` TOCTOU.** Harness `edit` requires `old_str` exactly-once in the *current* file
   content; a `/diff` preview computed from a stale `read` can misapply. Preview-then-apply
   must re-read (or apply failures must surface cleanly) — check `_handle_str_replace`
   exact-once semantics carry over to whichever edit path is chosen.
4. **Absolute-path UX friction.** Harness file tools reject relative paths (`_validate_path`).
   The REPL is cwd-centric; either the prompt teaches absolute paths, a wrapper resolves
   against cwd (within D-07 scope), or every turn errors. Decide explicitly.
5. **Subagent tool inheritance cuts both ways.** Children inherit tools + interventions
   (`agent.py:331-333`): the diff gate propagates (good), but an approve-each mode will
   prompt inside delegated turns (potentially noisy; LOOP-01 subagents are the core loop).
6. **`python_repl` overlap (D-03).** `python_repl` can already write files via stdlib
   `open()` inside executed code — same bypass class as (2) for both diff and D-07 scope.
   The planner must define `python_repl`'s remaining role (read-only compute? unrestricted?)
   or the gate has a second hole.
7. **TOOL-04 has no upstream tool.** No grep/search builtin exists (§1.2); a new local tool
   means new input schema, tests, and callback-handler rendering — smallest scope is a thin
   `rg` wrapper (repo already depends on subprocess-capable shell) plus `/search` router
   branch, lexical only, no index (Out of Scope table, REQUIREMENTS.md).
8. **Phase-boundary bleed into TOOL-03/Phase 3 and MODE/Phase 4.** `interventions="ask"`
   is a general approval gate and diff-mode "auto" resembles a mode; D-05 explicitly keeps
   general auto/yolo out of Phase 2. Scope the gate to *file mutations pending `/diff`
   review* and leave the policy file + mode system to their phases.

## 7. Planning inputs checklist (from 02-CONTEXT.md, resolved where research decides)

- Tool provenance (D-01/D-02): **resolved** — harness builtins `shell/read/write/edit`,
  no new dependency. Open: SDK `make_file_editor` vs harness `edit` (recommend harness).
- `python_repl` role (D-03): open — see risk 6.
- Diff mode-switch mechanics (D-04): open — recommend `ProviderConfig`-pattern store +
  `/diff [mode]` router extension.
- Shell scope enforcement (D-07): open — wrapper or Sandbox subclass; harness alone is
  insufficient (§1.4, §5).
- Grep UX (D-08/D-09): both agent tool + `/search`; lexical `rg` wrapper recommended (§6.7).

*State update: research complete; `02-RESEARCH.md` written. No change to STATE.md status
fields needed (Phase 2 remains "Ready to plan").*
