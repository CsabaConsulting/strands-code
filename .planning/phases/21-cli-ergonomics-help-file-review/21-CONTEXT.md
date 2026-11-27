# Phase 21: CLI Ergonomics (`/help`, `@file` / `/file`, `/review`) - Context

**Gathered:** 2026-11-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver `LOOP-06`, `TOOL-05`, and `REVIEW-01` — everyday interactive productivity ergonomics in cleanly factored modules within CI cyclomatic complexity bounds (`xenon --max-absolute C`, `CC <= 20`) while keeping `strands_code_agent/` pristine (`D-24`):

- **`LOOP-06` (`/help`):** Explicit `/help` and `/help <name>` (`strands_code_cli/dispatch/help.py`) registered in `BUILTIN_SLASH_HEADS`, sharing a single declarative command table with `USAGE_HINT` and rendering grouped built-in commands plus live loaded skills and shadow/drift warnings via `print_plain`.
- **`TOOL-05` (`@file` / `/file` + `"document"` conversion + `CVE-2026-18830`):** Inline `@file` fuzzy attachment completion and `/file` TTY picker (`strands_code_cli/ui/attachments.py`, `strands_code_cli/ui/completer.py`) confined to gitignore-aware `effective_roots`, resolving only real existing regular files (never `@dataclass` / `@pytest.mark` code tokens), injecting UTF-8 text/code inline and attaching binary `ImageContent`/`DocumentContent` when `supports_media(current_model)` holds post-routing via strictly allowlisted `list[ContentBlock]` construction, extending `strands_code_cli/model/model_switch.py` for `"document"` conversion across switches, and attaching `RejectCallerToolUseHook` across all 3 CLI agent sites (`entry/main.py`, `loop/btw.py`, `entry/subagent.py`).
- **`REVIEW-01` (`/review`):** Read-only `/review` (`strands_code_cli/dispatch/review.py`) pre-collecting uncommitted (`git diff HEAD`), `--staged`, or validated `<base-ref>` git diffs in Python inside an untrusted-diff frame (plus optional trailing focus prompt) and running under a turn-scoped read-only Plan gate (`turn_interface = "tool"`) without mutating sticky `ModeState` or `CodeactState`.

Out of scope: modifying `strands_code_agent/` (`D-24`), Phase 22 (`EVAL-01`), Phase 23 (`STRUCT-02`, `CLEANUP-02`), `LOOP-05` headless/JSON input-output mode, `REVIEW-02` headless CI review runner, `TOOL-06` `/copy`, and `SKILL-04` MCP server consumption.

</domain>

<decisions>
## Implementation Decisions

### `/help` Command Registry & Skill Lookup (`LOOP-06`)
- **D-01 (Single Declarative Command Table & `BUILTIN_SLASH_HEADS`):** Define one declarative command registry in `strands_code_cli/dispatch/help.py` grouped by category, deriving `USAGE_HINT` in `strands_code_cli/dispatch/core.py` directly from that registry so `/help` and unknown-command hints never drift. Add `"help"`, `"file"`, and `"review"` to `BUILTIN_SLASH_HEADS` (`strands_code_cli/memory/skills.py:21-46`, 25 total built-in heads). — *Reversibility: easy — single source of truth in `dispatch/help.py`.*
- **D-02 (`/help` & `/help <name>` Built-ins + Skills Parity):** Bare `/help` renders grouped built-in commands plus live loaded skills (marked `[shadowed by built-in]` when applicable) and skill shadow/drift warnings via `print_plain` (sanitized via `sanitize_display`). `/help <name>` resolves both built-in commands and loaded skills (stripping an optional leading `/`, showing namespace, description, source path, and shadow status for skills), returning an actionable unknown message when neither matches. — *Reversibility: easy — localized in `dispatch/help.py` and `dispatch/core.py`.*

### `@file` / `/file` Discovery, Encoding & Attachment Pipeline (`TOOL-05`)
- **D-03 (Inline `@file` Fuzzy Completion & `/file` TTY Picker Pre-Fill):** Extend `strands_code_cli/ui/completer.py` (preserving `DynamicCompleter(FuzzyCompleter(...))` for leading `/`) to fuzzy-complete `@<path>` mid-line from gitignore-aware `effective_roots` (`git ls-files --cached --others --exclude-standard` inside git repos, with a bounded `os.walk` fallback skipping `.git`/ignored/cache noise outside git repos). Bare `/file` (or `/file <filter>`) in an interactive TTY picks one file via TTY picker and pre-fills `@<relpath> ` into the next prompt buffer using existing `PromptSession.prompt_async(..., default=buf)` (`strands_code_cli/loop/core.py:815`); non-TTY returns a concise usage reply. — *Reversibility: easy — isolated in `ui/completer.py`, `ui/attachments.py`, and `loop/core.py` buffer handoff.*
- **D-04 (Real-File-Only `@token` Resolution & Text-vs-Binary Encoding):** Resolve only `@<token>` references (supporting `@path` and quoted `@"path with spaces"`) that match an existing regular file under `effective_roots`, leaving non-file `@tokens` (`@dataclass`, `@pytest.mark`, email addresses) completely untouched in the prompt text. Inject UTF-8 plain-text and source-code files (including `.md`, `.txt`, `.csv`, `.html`, `.py`, etc.) inline inside fenced untrusted-file text blocks (`<attached_file path="...">...</attached_file>`), reserving `ImageContent` (`png`, `jpeg`, `gif`, `webp`) and `DocumentContent` (`pdf`, `docx`, `xlsx`, `doc`, `xls` with provider-safe sanitized `name`) strictly for binary media/documents. — *Reversibility: easy — centralized extension/MIME classifier in `ui/attachments.py`.*
- **D-05 (Fail-Closed `@file` / `/file` Security Floor & Caps):** Match `read` (`strands_code_cli/policy/core.py:877-959`) and `codeact_read` (`strands_code_cli/policy/codeact.py`) security parity fail-closed: confine paths to `effective_roots(cwd, policy, tool_name="read")` (`strands_code_cli/policy/scope.py:81-119`), refuse target and ancestor symlinks (`refuse_symlink_under_roots` + `O_NOFOLLOW` + `os.fstat` regular-file check), refuse sensitive secret paths (`_is_sensitive_read_path`: `.env*`, `~/.ssh/*`, `~/.aws/*`) and active `PolicyConfig` `[[deny]]` rules (home-vs-repo precedence with fail-closed symlinked repo policy), and cap reads at `4 MiB` per file (`CODEACT_MAX_FILE_BYTES` parity), `16 MiB` total per turn, and `8` attachments per turn. — *Reversibility: moderate — security boundary aligned with `read`/`codeact_read`.*
- **D-06 (Post-Routing `supports_media` Abort Gate & Allowlisted `list[ContentBlock]`):** Evaluate `supports_media(current_model)` **after** `_route_pre_turn` (`strands_code_cli/loop/core.py:2930`), sending only raw/sanitized ask text (never file contents or binary bytes) to `_route_pre_turn`. When binary image/document attachments are present and `supports_media(current_model)` is `False`, abort the turn before calling the model with an actionable reply naming the model and unsupported files so the user can `/model` switch without wasting a turn. Construct `list[ContentBlock]` in `ui/attachments.py` strictly from allowlisted `text`/`image`/`document` dicts only (never caller-supplied `"toolUse"` blocks). — *Reversibility: easy — post-routing check before `_run_turn_attempts`.*

### Cross-Model Document Conversion & `CVE-2026-18830` Boundary (`TOOL-05`)
- **D-07 (`model_switch.py` `"document"` Conversion & `cost_context.py` Alignment):** Extend `strands_code_cli/model/model_switch.py` (`_MEDIA_PLACEHOLDER_RE`, `_canonical_block`, `_media_placeholder_block`, `_convert_block`) to handle `"document"` blocks with full parity to `"image"`/`"video"` (converting to `[document: <name>/<format>, <N> bytes]` on media-less switches while preserving `RichHistory` stashes and `canonical_prefix_hash`). Ensure `_block_chars` (`strands_code_cli/cost/cost_context.py:799-826`) handles media/document blocks safely without crashing or inflating byte heuristics. — *Reversibility: easy — localized in `model/model_switch.py` and `cost/cost_context.py`.*
- **D-08 (`RejectCallerToolUseHook` — CVE-2026-18830 Fail-Closed 3-Site Guard):** Attach `RejectCallerToolUseHook` on `strands.hooks.events.BeforeInvocationEvent` across all 3 CLI agent sites (`entry/main.py`, `loop/btw.py`, `entry/subagent.py` — Phase 20 3-site symmetry). If any incoming message in `event.messages` contains a caller-supplied `"toolUse"` block, fail closed by setting `event.cancel` with an explicit security refusal before `event_loop_cycle` executes. — *Reversibility: moderate — security boundary hook attached at all 3 agent factories.*

### Read-Only `/review` Command (`REVIEW-01`)
- **D-09 (`/review` Targets, Optional Focus Prompt & Empty-Diff Short-Circuit):** Support `/review` (`git diff HEAD`), `/review --staged` (`git diff --cached`), `/review <base-ref>` (`git diff <base-ref>...HEAD`), and optional trailing focus instructions (e.g. `/review --staged focus on auth`, `/review main -- check error paths`, `/review -- focus on X`). Validate `<base-ref>` fail-closed against flag/control-char/whitespace injection (`git rev-parse --verify --end-of-options <ref>^{commit}`), invoke `git` with `shell=False` and an explicit timeout, and return a plain `"reply"` (skipping any model call) on an empty diff or non-git directory. — *Reversibility: easy — argument parser and diff collector in `dispatch/review.py`.*
- **D-10 (Untrusted-Diff Framing, Truncation Bounds & `/route` Parity):** Frame collected `--stat` summary and diff output inside `<untrusted_git_diff ...>...</untrusted_git_diff>` instructing the model to treat the diff strictly as untrusted code data, bounded at `256 KiB` with an explicit truncation note if exceeded. When `/route on` is active, route normally using only the sanitized command/focus string (`ask_text`), never exposing the untrusted diff body to the decision model (matching `strands_code_cli/loop/core.py:2933`). — *Reversibility: easy — prompt framing and sanitized routing string in `dispatch/review.py` / `loop/core.py`.*
- **D-11 (Turn-Scoped Read-Only Plan Gate & `turn_interface = "tool"` Isolation):** Wrap `/review` turns in `PolicyGateHandler.enter_read_only(agent)` / `exit_read_only(agent)` inside a `finally:` block without mutating sticky `ModeState` (or falsely arming `ModeState.pending_plan`), and force `turn_interface = "tool"` without mutating sticky `CodeactState` or swapping in `CodeactStint`. — *Reversibility: easy — per-turn isolation around `_run_turn_attempts`.*

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `.planning/ROADMAP.md` — Phase 21 (`LOOP-06`, `TOOL-05`, `REVIEW-01`) goal & success criteria (`lines 288-298`)
- `.planning/REQUIREMENTS.md` — `LOOP-06`, `TOOL-05`, `REVIEW-01` (`lines 41-43`)
- `.planning/INVARIANTS.md` — `D-24` (`strands_code_agent/` immutability), restricted-module hygiene, Peer Parity Habits & UAT Adversarial Pre-Check Gate
- `.planning/STATE.md` — `v2.0` complexity ceiling warning & CVE-2026-18830 / CoreBreak note (`lines 119-120`)
- `strands_code_cli/memory/skills.py` — `BUILTIN_SLASH_HEADS` (`lines 21-46`), `SkillIndex`, `SkillEntry`
- `strands_code_cli/dispatch/core.py` — `USAGE_HINT` (`lines 68-78`), `dispatch()` (`lines 255-380`), picker/TTY patterns (`lines 2680-2892`); current max CC `_setup_pick_candidates_typed` `C (18)`
- `strands_code_cli/ui/completer.py` — `SlashCompleter`, `build_completer` (`lines 1-53`)
- `strands_code_cli/ui/console.py` & `strands_code_cli/ui/output.py` — `console`, `sanitize_display`, `sanitize_multiline`, `print_plain`
- `strands_code_cli/loop/core.py` — `_invoke_agent` (`lines 724-795`), `_race_idle_episode(..., default=buf)` (`line 815`), `_dispatch_turn_input` (`line 2126`), `build_completer(_skill_words)` (`line 2750`), turn pipeline `resolve_turn_interface` / `_route_pre_turn` / `_run_turn_attempts` (`lines 2909-2975`); live `radon cc`: `run_loop` `C (18)`, `_route_side_spawn` `C (18)`, `_invoke_agent` `C (15)`
- `strands_code_cli/policy/scope.py` — `resolve()`, `confine()`, `effective_roots(cwd, policy, tool_name=...)` (`lines 22-119`)
- `strands_code_cli/policy/core.py` — `PolicyConfig`, `decide()`, `_is_sensitive_read_path()` (`lines 877-959`)
- `strands_code_cli/policy/codeact.py` — `CODEACT_MAX_FILE_BYTES`, `_read_regular_file_utf8()`, Phase 20 read/deny/symlink parity
- `strands_code_cli/policy/policy_gate.py` — `PLAN_MUTATING_TOOLS` (`line 75`), `enter_read_only` / `exit_read_only` / `is_read_only` (`lines 604-620`)
- `strands_code_cli/policy/mode.py` — `ModeState` (`lines 35-92`)
- `strands_code_cli/model/model_switch.py` — `supports_media` (`lines 210-218`), `_MEDIA_PLACEHOLDER_RE`, `_canonical_block` (`lines 263-319`), `_media_placeholder_block`, `_convert_block` (`lines 397-438`)
- `strands_code_cli/cost/cost_context.py` — `_block_chars`, `estimate_messages_tokens` (`lines 799-840`)
- `strands_code_cli/entry/main.py`, `strands_code_cli/loop/btw.py`, `strands_code_cli/entry/subagent.py` — 3 CLI agent construction sites (`build_agent`, `build_btw_agent`, `build_cli_subagent`) for `RejectCallerToolUseHook`
- `strands.types.media` & `strands.hooks.events` in `.venv` — `ImageFormat`, `DocumentFormat`, `ImageContent`, `DocumentContent`, `BeforeInvocationEvent` (`messages`, `cancel`)

</canonical_refs>

<deferred>
## Deferred Ideas

- **`LOOP-05`:** Non-interactive headless / JSON input-output mode for scripts and CI (reuses `RejectCallerToolUseHook` + allowlisted block construction; deferred to `v2.1+`).
- **`REVIEW-02`:** Headless / CI `/review` runner modes (`v2.1+`).
- **`TOOL-06`:** Export trimmed session content via `/copy` (`v2.1+`).
- **Multi-file `/file` staged queue:** `/file list` / `/file clear` staged queue omitted in favor of direct `@<relpath> ` buffer pre-fill (`D-03`); easily revisit-able if users later ask for batch staging without typing `@`.
- **`EVAL-01` (Phase 22) & `STRUCT-02` / `CLEANUP-02` (Phase 23):** Evals suite and full 10-package DAG / monolith split belong to Phases 22–23.

</deferred>

---

*Phase: 21-cli-ergonomics-help-file-review*
*Context gathered: 2026-11-27*
