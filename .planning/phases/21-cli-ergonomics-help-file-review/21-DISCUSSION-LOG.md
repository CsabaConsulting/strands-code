# Phase 21: CLI Ergonomics (`/help`, `@file` / `/file`, `/review`) - Discussion Log

**Date:** 2026-11-27
**Phase:** 21 (`LOOP-06`, `TOOL-05`, `REVIEW-01`)
**Baseline `HEAD`:** `da05423` (Phase 20 validated, working tree clean)

---

## Pre-Discussion Scouting & Peer Parity Matrix

Verified on `HEAD` (`da05423`) before asking questions per `GEMINI.md` § 1 and `.planning/INVARIANTS.md`:

- **Live `radon cc -s -n C` complexity baselines:**
  - `strands_code_cli/loop/core.py`: `run_loop` = `C (18)`, `_route_side_spawn` = `C (18)`, `_invoke_agent` = `C (15)`
  - `strands_code_cli/dispatch/core.py`: `_setup_pick_candidates_typed` = `C (18)`, `_skills_remove_cmd` = `C (17)`
  - `strands_code_cli/entry/main.py`: `model_for_config` = `C (18)`, `build_agent` = `C (15)`, `_root` = `C (15)`
  - `strands_code_cli/model/model_switch.py`: `resolve_harness_model` = `C (18)`, `_canonical_block` = `C (15)`, `_convert_block` = `< C (11)`
- **Upstream `.venv` SDK contracts inspected:**
  - `strands.types.media`: `ImageFormat = Literal["png", "jpeg", "gif", "webp"]`, `DocumentFormat = Literal["pdf", "csv", "doc", "docx", "xls", "xlsx", "html", "txt", "md"]`
  - `strands.hooks.events`: `BeforeInvocationEvent` exposes writable `messages` and `cancel` fields checked before `event_loop_cycle` executes.

### Peer Parity Matrix Shown to User

| Cross-Cutting Axis | Existing Peers on `HEAD` (`da05423`) | Phase 21 Alignment Target |
|---|---|---|
| **Slash commands & `USAGE_HINT`** | 22 heads in `memory/skills.py:21-46`; hardcoded `USAGE_HINT` in `dispatch/core.py:68-78`; `print_plain` | Add `help`, `file`, `review` to `BUILTIN_SLASH_HEADS`; single table in `dispatch/help.py` |
| **Tab completion & TTY pickers** | `SlashCompleter` (`ui/completer.py:19-53`) for `/` only; TTY pickers; `PromptSession.prompt_async(..., default=buf)` (`loop/core.py:815`) | Composite `/` + `@<path>` completer; `/file` pre-fills `@<relpath> ` via `default=buf` |
| **File-read scope & safety floor** | `read` (`policy/core.py:877-959`) & `codeact_read` (`policy/codeact.py`): `effective_roots(..., tool_name="read")`, symlink/`O_NOFOLLOW`, `.env*`/`.ssh`/`.aws`, `[[deny]]`, `4 MiB` cap | Align `@file` / `/file` reads in `ui/attachments.py` identically |
| **Multimodal blocks & model switch** | `model_switch.py:263-438` converts `image`/`video` only; `_route_pre_turn` (`loop/core.py:2933`) reads `ask_text=text` only | Add `"document"` to `model_switch.py`; evaluate `supports_media` post-routing; allowlist `text`/`image`/`document` blocks |
| **Read-only turn & CodeAct isolation** | `PolicyGateHandler.enter_read_only`/`exit_read_only` (`policy_gate.py:604-620`) blocking `PLAN_MUTATING_TOOLS`; `resolve_turn_interface` (`loop/core.py:2919`) | Turn-scoped read-only gate + `turn_interface = "tool"` on `/review` without mutating `ModeState` or `CodeactState` |
| **Hook & security coverage** | 3 CLI agent factories (`entry/main.py`, `loop/btw.py`, `entry/subagent.py`) | Attach `RejectCallerToolUseHook` across all 3 sites |
| **Complexity headroom (`radon cc`)** | `run_loop` `C (18)` vs `xenon <= 20` | Isolate logic in `dispatch/help.py`, `ui/attachments.py`, `dispatch/review.py` |

---

## Round 1 — Questions & Selections

1. **Q1 (`/help <name>` resolution scope):**
   - *Options:* (A, Recommended) Look up both built-in commands and loaded skills (showing namespace, description, source path, and shadow status); (B) Built-in commands only; direct users to `/skills show` for skills (`⚠️ Breaks parity with slash completer & /<skill> discovery`).
   - **Selected:** **(A)** Look up both built-in commands and loaded skills.
2. **Q2 (`@file` / `/file` text vs binary encoding):**
   - *Options:* (A, Recommended) Inject UTF-8 text/code files inline as fenced untrusted text blocks; use `ImageContent` (`png/jpeg/gif/webp`) and `DocumentContent` (`pdf/docx/xlsx/doc/xls`) only for binary media/docs; (B) Send supported text formats (`.md`, `.txt`, `.csv`, `.html`) as `DocumentContent` too (`⚠️ Breaks parity with media-less models & hits provider document-count/PDF-text limits`).
   - **Selected:** **(A)** UTF-8 text/code inline fenced blocks; binary `ImageContent`/`DocumentContent` only for binary media/docs.
3. **Q3 (Post-routing `supports_media(current_model) == False` handling):**
   - *Options:* (A, Recommended) Abort the turn before calling the model with an actionable reply naming the model and unsupported files so the user can `/model` switch without wasting a turn; (B) Downgrade binary attachments to a text placeholder and send the turn with a warning.
   - **Selected:** **(A)** Abort the turn before calling the model with an actionable reply.
4. **Q4 (`/file` TTY picker output integration):**
   - *Options:* (A, Recommended) Pick one file via TTY fuzzy/radio picker and pre-fill `"@<relpath> "` into the next prompt buffer (via existing `default=buf`), so the user immediately types their ask or adds more `@file`s; (B) Maintain an in-memory staged attachment list (`⚠️ Adds a new stateful queue not present in sibling pickers`).
   - **Selected:** **(A)** Pre-fill `"@<relpath> "` into the next prompt buffer via `default=buf`.

---

## Round 2 — Questions & Selections

5. **Q5 (`@file` / `/file` filesystem & secret security floor):**
   - *Options:* (A, Recommended) Enforce the same fail-closed floor as `read`/`codeact_read`: confine to `effective_roots(tool_name="read")`, refuse symlink escapes & `O_NOFOLLOW`, refuse `.env*`/`.ssh`/`.aws` and active `PolicyConfig` `[[deny]]` rules, and cap per-file size at `4 MiB`; (B) Allow user-typed `@.env` / sensitive files with a printed warning (`⚠️ Breaks parity with read/codeact_read secret floor`).
   - **Selected:** **(A)** Fail-closed `read`/`codeact_read` security floor (`4 MiB` cap, symlink/`O_NOFOLLOW`, sensitive paths, `[[deny]]`).
6. **Q6 (`/review` optional trailing focus prompt):**
   - *Options:* (A, Recommended) Allow an optional trailing focus prompt after the target (e.g. `/review --staged focus on auth`, `/review main -- check error paths`, or `/review -- focus on X`); (B) Accept only the diff target (`/review`, `/review --staged`, `/review <base-ref>`) with no inline focus text.
   - **Selected:** **(A)** Allow optional trailing focus prompt after target / `--`.
7. **Q7 (`/review` interaction with `/route on`):**
   - *Options:* (A, Recommended) Route normally when `/route on` is active, passing only the sanitized command/focus text (never the untrusted git diff body, matching `loop/core.py:2933` `ask_text=text` parity); (B) Skip `/route` on `/review` and always run on `current_model` (`⚠️ Breaks parity with /<skill> and /memory revise turns`).
   - **Selected:** **(A)** Route normally on sanitized command/focus string only (never untrusted diff body).
8. **Q8 (`RejectCallerToolUseHook` CVE-2026-18830 behavior):**
   - *Options:* (A, Recommended) Fail closed: cancel the invocation via `BeforeInvocationEvent.cancel` with an explicit error (attached across all 3 agent sites: `entry/main.py`, `loop/btw.py`, `entry/subagent.py`); (B) Silently strip caller-supplied `toolUse` blocks (`⚠️ Fails soft on an injection attempt rather than fail-closed`).
   - **Selected:** **(A)** Fail closed via `BeforeInvocationEvent.cancel` across all 3 CLI agent sites.

---

## Decision Mapping

| Question / Topic | Context Decision(s) |
|---|---|
| Command registry, `BUILTIN_SLASH_HEADS`, `/help` + `/help <name>` (Q1 + `ROADMAP.md` SC 1) | `D-01`, `D-02` |
| `@file` / `/file` completion, pre-fill, real-file resolution & encoding (Q2, Q4) | `D-03`, `D-04` |
| `@file` / `/file` fail-closed security floor & caps (Q5) | `D-05` |
| Post-routing `supports_media` abort gate & allowlisted `ContentBlock` (Q3 + `REQUIREMENTS.md` `TOOL-05`) | `D-06` |
| `model_switch.py` `"document"` conversion + `RejectCallerToolUseHook` 3-site guard (Q8 + `STATE.md:120`) | `D-07`, `D-08` |
| `/review` targets, focus prompt, untrusted diff framing, `/route` & read-only/tool isolation (Q6, Q7 + `ROADMAP.md` SC 3) | `D-09`, `D-10`, `D-11` |
