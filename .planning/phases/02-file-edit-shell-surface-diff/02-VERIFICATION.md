# Phase 2 Verification: File/Edit/Shell Surface + /diff

**Verified:** 2026-09-25 (gsd-verifier, independent read of code, not test descriptions)
**Scope:** 02-PLAN.md must_haves (4 truths, 8 artifacts, 5 key_links, 5 prohibitions) + TOOL-01/02/04
**Test runs (this session):** focused `tests/test_tool_surface.py tests/test_diff_gate.py tests/test_search.py tests/test_cli_entry.py` → **90 passed**; full `tests/` → **317 passed, 5 deselected**

## Truths

### T1 — Agent reads, writes, edits files and runs shell through harness builtins in a live turn (TOOL-01, D-02): PASS
- `strands_code_cli/main.py:90-102` — `build_agent` passes `tools=[python_repl, search, gated_write, gated_edit]` plus explicit `builtin_tools` MAPPING (`shell: True, read: True, write: False, edit: False`), so read/shell are harness builtins and write/edit flow through same-named gated wrappers.
- Test docstring `tests/test_tool_surface.py:1-11` records the live-turn tracer observation (harness defaults already live before pinning).
- Shell bypass advisory documented in code (`strands_code_cli/scope.py:8-12`, `strands_code_cli/diff_gate.py:17-22`), per D-06 — not a T1 failure.

### T2 — User reviews pending changes via /diff in approve-each, on-demand, or auto mode before they apply (TOOL-02, D-04): PASS
- `strands_code_cli/diff_gate.py:229-272` (`_gate_and_apply`) implements all three modes: approve-each prompts per hunk via `ask` (251-257), on-demand stashes sidecar JSON (258-264), auto applies directly (265-272).
- `strands_code_cli/diff_gate.py:266-270` re-reads before apply and raises `ValueError` on stale preview (exact-once, never silent misapply); `apply_stashed` (275-310) keeps stale entries pending per file.
- `strands_code_cli/diff_config.py:26-27,37-42` — `MODES = (approve-each, on-demand, auto)`, default `on-demand`.
- `strands_code_cli/router.py:63-64,70-105` — `/diff` mode switch / show / apply / discard all return `reply` actions only.

### T3 — Agent and user navigate repos with grep plus on-the-fly symbol context, no index (TOOL-04, D-08, D-09): PASS
- `strands_code_agent/search_tool.py:24-46` — `run_search` shells out to `rg --line-number --no-heading` via argv list (pattern is one argv element, never shell-interpolated), falls back to `os.walk`+`re` when rg is absent (44-46); no index file created anywhere in the module.
- `strands_code_agent/search_tool.py:65-87` — stdlib fallback; `_cap` (90-97) truncates with a note; empty pattern refused (38-39).
- `strands_code_cli/router.py:65-66,108-117` — `/search` runs synchronously and returns a `reply`; never triggers a model turn.
- `strands_code_agent/callback_handler.py:65-71,109-110` — search tool calls render as plain `path:line` text.

### T4 — File mutations outside cwd+subdirs+/tmp refused by app code, expansion left to Phase 3 (D-07): PASS
- `strands_code_cli/scope.py:21-32` (`resolve`: relative→cwd, `~` expansion) and `35-52` (`confine`: admits only cwd+subdirs and /tmp+subdirs, resolves symlinks via `realpath`, raises `ValueError` naming allowed roots).
- Gate enforces it: `diff_gate.py:245` (`_gate_and_apply` confines every mutation) and `gated_write:345`, `gated_edit:388`; search confines its path too (`search_tool.py:43`).
- Shell/python_repl bypass documented as advisory (`scope.py:8-12`), airtight mediation deferred to Phase 3 — matches plan assumption, not a T4 failure.

## Artifacts (all present)

| Artifact | Status | Evidence |
|---|---|---|
| `strands_code_cli/main.py` (builtin_tools mapping) | PASS | `main.py:97-102` |
| `strands_code_cli/scope.py` | PASS | `scope.py:21-67` incl. `ScopeGuard` ctor-kwarg, no env sniffing |
| `strands_code_cli/diff_config.py` | PASS | `diff_config.py:37-94` ProviderConfig-shape mirror |
| `strands_code_cli/diff_gate.py` | PASS | `diff_gate.py:51-416` |
| `strands_code_agent/search_tool.py` | PASS | `search_tool.py:24-118` |
| `strands_code_agent/callback_handler.py` (diff + search rendering) | PASS | `callback_handler.py:10-11,35-71,107-110`; diff via `Syntax(body, "diff")` (62), fall-through for unknown tools (111-113) |
| `strands_code_cli/router.py` (/diff, /search branches) | PASS | `router.py:17-24` USAGE_HINT, `63-66` branches, `70-141` handlers |
| `tests/test_tool_surface.py` | PASS | focused run green |
| `tests/test_diff_gate.py` | PASS | focused run green |
| `tests/test_search.py` | PASS | focused run green |

(`tests/test_cli_entry.py` router tests also green in the focused run.)

## Key links

1. main.py passes builtin_tools mapping to create_harness; never imports strands_tools: PASS — `main.py:10` imports `create_harness` from `strands_harness`; `97-102` mapping form (not pin list); repo-wide `strands_tools` grep hits only `tests/test_tool_surface.py:11,70,74` (the no-import assertion itself), zero source imports; `pyproject.toml` deps list only `strands-agents`, `strands-harness` (no `strands-agents-tools`).
2. scope.py resolve+confine wraps every file-tool path before harness absolute check: PASS — `diff_gate.py:245,345,388` and `search_tool.py:43`; `scope.py:26` docstring states resolve runs BEFORE the harness check.
3. diff_gate.py wrappers replace builtin write/edit (pinned off) and consult diff_config.py mode: PASS — `@tool(name="write")` (`diff_gate.py:337`) / `@tool(name="edit")` (`379`) with builtins pinned off (`main.py:100-101`); default `get_mode` reads `DiffConfig.load().mode` (`334,376`).
4. router.py /diff and /search dispatch; approval prompts in gate layer, never router replies: PASS — `router.py:63-66` return `("reply", ...)`; `_diff_message` docstring (71-75) states approvals never live there; `grep ask( router.py loop.py` → no hits; prompts only via gate `ask` callable (`diff_gate.py:251-256`, `_default_ask:318-320`).
5. callback_handler.py renders unified diffs via Rich Syntax("diff") inside output_context: PASS — `callback_handler.py:62` `Syntax(body, "diff")` with `---`/`+++` markers (60-61); no direct stdout writes in the handler (all `self.console.print`, consumed inside `loop.py` output_context wrap).

## Prohibitions

1. MUST NOT add strands-agents-tools dependency or import strands_tools.*: PASS — no `strands_tools` import in source; not in `pyproject.toml` dependencies.
2. MUST NOT build Phase 3 deny-first policy file, general approval prompts, or network gating: PASS — `ls strands_code_cli/` shows no policy file; no `interventions`/`policy` matches in `strands_code_cli`/`strands_code_agent`; only approval surface is the diff-gate `ask` callable scoped to write/edit hunks.
3. MUST NOT build general auto/yolo mode covering all tool calls: PASS — `auto` exists only as a `DiffConfig` file-mutation mode (`diff_config.py:6-7,26` docstring explicitly scopes it; D-05 cited); no global mode system (deferred to Phase 4).
4. MUST NOT build persistent code index or embeddings: PASS — `search_tool.py` greps the live tree every call; no index files, no embedding dependency; "index"/"embeddings" have no source matches.
5. MUST NOT route diff approval through router reply actions: PASS — `/diff` branches return `reply` status/persist/apply results only (`router.py:63-64`); per-hunk approval happens in-turn via the gate `ask` callable, consistent with `loop.py:118-124` race note.

## Assumptions spot-check (plan-flagged, advisory only)

- Harness-defaults probe recorded in `tests/test_tool_surface.py:3-10` docstring: OK.
- rg-availability probe: fallback covered in `search_tool.py:44-46`: OK.
- Shell-advisory probe: documented in `scope.py:8-12` and `diff_gate.py:17-22`: OK.
- `code_agent.py:12-24` instructions steer to dedicated tools (absolute paths, scope, search-before-read) and document the `open()`/redirection bypass; `code_agent.py:147-150` fixes the `tools.append` aliasing hazard by copying (`list(tools) + [...]`).

## Verdict

Phase 2 **PASSES** verification: all 4 truths, all artifacts, all 5 key links, and all 5 prohibitions hold against the actual code. Focused suite 90 passed; full suite 317 passed, 5 deselected. No code changes made (report only).
