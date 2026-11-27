# Phase 21: CLI Ergonomics (`/help`, `@file` / `/file`, `/review`) - Implementation Patterns

**Created:** 2026-11-27
**Scope:** Canonical patterns mirrored across Phase 21 Waves 1–3 (`21-01`..`21-03`).

---

## Pattern 1: Declarative Command Registry Driving `USAGE_HINT` & `/help` (`D-01`, `D-02`)

- **Target files:** `strands_code_cli/dispatch/help.py` (new), `strands_code_cli/dispatch/core.py`, `strands_code_cli/memory/skills.py`.
- **Pattern:**
  - Define `@dataclass(frozen=True) class CommandSpec` (`head`, `usage`, `category`, `summary`, `details`) and ordered tuple `COMMANDS: tuple[CommandSpec, ...]`.
  - Categories (`Session`, `Modes & Execution`, `Models & Cost`, `Context & Memory`, `Files, Search & Review`, `Skills & Help`) match logical CLI groupings cleanly.
  - `build_usage_hint() -> str` emits `"Available commands: " + ", ".join(spec.usage for spec in COMMANDS)` — replacing the static `USAGE_HINT` literal in `dispatch/core.py:68-78` while preserving every existing assertion substring (`/diff`, `/search`, `/mode [plan|act]`, `/approve`, `/route [on|off|status|setup|validate]`, `/codeact [tool|code|both]`, `/code <ask>`, `/tool <ask>`, `/btw <side question>`, `/skills [...]`, `/memory [mode [curate|silent]|list|approve <id>|deny <id>|...]`, `/init [deeper]`).
  - `format_help(arg: str, skills: SkillIndex | None)` strips optional leading `/`, normalizes lowercase for built-ins, checks built-ins first (mirroring built-in-wins rule), then resolves `SkillIndex.resolve(...)` and `SkillIndex.ambiguous_matches(...)` (`namespace`, sanitized `description`, `path`, `[shadowed by built-in]` if shadowed). Bare `/help` lists grouped commands + loaded skills + `skills.warnings` sanitized via `sanitize_display()`.
  - `BUILTIN_SLASH_HEADS` in `memory/skills.py` adds `"help"`, `"file"`, `"review"`, and a unit test verifies exact 1:1 parity between `BUILTIN_SLASH_HEADS` and `{spec.head.lstrip("/") for spec in COMMANDS}`.

---

## Pattern 2: Idempotent 3-Site `BeforeInvocationEvent` Guard (`D-08`)

- **Target files:** `strands_code_cli/policy/tool_use_guard.py` (new), `strands_code_cli/entry/main.py`, `strands_code_cli/loop/btw.py`, `strands_code_cli/entry/subagent.py`.
- **Mirror from:** `strands_code_cli/loop/steering.py:258-291` (`register_steering_hook`).
- **Pattern:**
  - `contains_caller_tool_use(messages: Any) -> bool` scans message dicts/lists for any content block with `"toolUse" in block` and exposes `validate_content_blocks(blocks)` (raising `ValueError` if any block is not a dict or contains `"toolUse"` or keys outside `{"text", "image", "document"}`).
  - `register_reject_caller_tool_use_hook(agent: Any) -> None` checks `getattr(agent, "_reject_tool_use_hook_registered", False)` and `callable(getattr(agent, "add_hook", None))`, registers a `BeforeInvocationEvent` callback at `HookOrder.SDK_FIRST` that sets `event.cancel = "Rejected caller-supplied toolUse block (CVE-2026-18830 guard)."` when `contains_caller_tool_use(event.messages)` is `True`.
  - Wired in all 3 agent factories:
    1. `entry/main.py:build_agent` (right next to `register_steering_hook(agent)`)
    2. `loop/btw.py:_configure_btw_agent`
    3. `entry/subagent.py:_configure_child_agent` (alongside existing `BeforeModelCallEvent` hook)

---

## Pattern 3: `"document"` Block Conversion & Accounting (`D-07`)

- **Target files:** `strands_code_cli/model/model_switch.py`, `strands_code_cli/cost/cost_context.py`.
- **Mirror from:** `model_switch.py:263,294-319,397-438`.
- **Pattern:**
  - Extend `_MEDIA_PLACEHOLDER_RE` to `r"\[(?:image|video|document): [^,\]]*, \d+ bytes\]"`.
  - Extend `_canonical_block` to drop `"document" in block` alongside `"image"` and `"video"` (the regex update automatically strips `[document: ...]` placeholders too!).
  - Extend `_media_placeholder_block(block)`: for `"document"`, read `name = payload.get("name", "document")`, `fmt = payload.get("format", "unknown")`, `size = len(data) if data else 0`, and emit `{"text": f"[document: {sanitize_placeholder_name(name)}/{fmt}, {size} bytes]"}` matching `_MEDIA_PLACEHOLDER_RE`.
  - Extend `_convert_block`: trigger `_media_placeholder_block(block)` when `("image" in block or "video" in block or "document" in block) and not media_ok`.
  - Verify `cost_context.py:_block_chars` ignores binary `bytes` payloads in `"image"`/`"document"` blocks safely (`chars += 0` or small header only, never calling `len(str(bytes))`).

---

## Pattern 4: Fail-Closed `@file` / `/file`, Composite Completer & Post-Routing Gate (`D-03`–`D-06`)

- **Target files:** `strands_code_cli/ui/attachments.py` (new), `strands_code_cli/ui/completer.py`, `strands_code_cli/dispatch/core.py`, `strands_code_cli/loop/core.py`, `strands_code_cli/loop/pump.py`.
- **Mirror FS/policy floor from:** `strands_code_cli/policy/codeact.py:166-260` + `strands_code_cli/policy/scope.py:81-119`.
- **Pattern:**
  - **Discovery (`discover_workspace_files(cwd, policy, limit=5000)`):** Inside a git repo under `cwd`, invoke `git ls-files --cached --others --exclude-standard -z` (`shell=False`, short timeout); outside git repos, bounded `os.walk` skipping `.git`, `.venv`, `__pycache__`, `node_modules`. Plus extra non-`/tmp` configured `effective_roots(cwd, policy, tool_name="read")` when distinct from `cwd`. Filter symlinks & sensitive paths (`.env*`, `.ssh`, `.aws`) out of completion candidates too!
  - **Completion (`ui/completer.py`):** Add `AtFileCompleter(get_files)` activating when the cursor is inside a whitespace-delimited `@<prefix>` token (`re` scanning backward from cursor after start-of-line or whitespace, NOT inside `/slash` head before space). Compose `SlashCompleter(get_words)` + `AtFileCompleter(get_files)` inside `build_completer(get_words, get_files=None)` using `merge_completers([SlashCompleter(get_words), AtFileCompleter(get_files)])` wrapped by `DynamicCompleter(lambda: FuzzyCompleter(...))`.
  - **`/file` picker (`dispatch/core.py` -> `("prefill", "@<relpath> ")`):** Calls `ui.attachments.pick_file_for_prompt(rest, cwd=cwd)` using `radio_choice` (catching non-TTY `RuntimeError` cleanly with a reply), returning `("prefill", f"@{picked} ")` (quoted `@"{picked}" ` if whitespace in path) to re-enter `_read_turn_input(..., initial_buf=...)` on the next prompt turn (`default=buf`).
  - **Attachment resolution & allowlisted `ContentBlock` construction (`prepare_turn_prompt(raw_ask, composed_text, *, current_model, cwd)`):**
    1. Scan ONLY `raw_ask` (never `composed_text` prefixes, `SKILL.md` instructions, or `/review` diffs) for `@path` / `@"path with spaces"` tokens.
    2. For each token, resolve candidate against `effective_roots(cwd, policy, tool_name="read")`. **Non-existent tokens** (like `@dataclass`, `@pytest.mark`, `@user@example.com` without an existing file under scope) stay literal prompt text!
    3. **Existing tokens OR paths escaping/denied:** Run fail-closed checks: `_refuse_raw_symlink_traversal`, `confine(..., extra_roots=effective_roots(..., tool_name="read"))`, `refuse_symlink_under_roots`, `_is_sensitive_read_path`, `decide(policy, "read", ...)`, `O_NOFOLLOW | O_NONBLOCK`, `stat.S_ISREG(st.st_mode)`, `<= 4 MiB` per file, `<= 16 MiB` total, `<= 8` attachments. Note: if a path is an existing symlink or `.env` or `[[deny]]` match inside/relative to `cwd`, **abort the turn fail-closed** (never silently skip a symlink/denied `@secret`!).
    4. Classify by suffix: `png/jpeg/gif/webp` -> `ImageContent`; `pdf/docx/xlsx/doc/xls` -> `DocumentContent` (`sanitize_document_name(stem)`); everything else UTF-8 decoded (`errors="strict"` -> non-UTF8 unknown binaries refused clearly) wrapped in `<attached_file path="...">...</attached_file>` text blocks (also sanitized / escaped safely).
    5. **Post-routing `supports_media(current_model)` check:** If any binary `image`/`document` block is attached and `not supports_media(current_model)`, abort before `_run_turn_attempts` with an actionable error naming `current_model` and the unsupported filenames.
    6. Return `str` (if only text / no attachments) or `list[dict[str, Any]]` validated through `validate_content_blocks(...)` (`"text"` / `"image"` / `"document"` only).

---

## Pattern 5: Read-Only `/review` Pipeline (`D-09`, `D-10`, `D-11`)

- **Target files:** `strands_code_cli/dispatch/review.py` (new), `strands_code_cli/dispatch/core.py`, `strands_code_cli/loop/core.py`.
- **Pattern:**
  - **Parser (`parse_review_args(rest)` -> `ReviewSpec(mode, base_ref, focus)`):**
    - `/review` -> `mode="head"` (`git diff HEAD`)
    - `/review --staged [focus...]` -> `mode="staged"` (`git diff --cached`)
    - `/review -- <focus...>` -> `mode="head"`, `focus=...`
    - `/review <base-ref> [--] [focus...]` -> `mode="base"`, validated `<base-ref>` + optional `focus`
    - Reject unknown `--flags` cleanly (`Usage: /review [--staged | <base-ref>] [focus...]`).
  - **Ref validation (`validate_base_ref(ref, cwd)`):**
    - Reject empty, leading `"-"`, whitespace, control chars (`\x00-\x1f`, `\x7f`), `..` range confusion if disallowed or unsafe chars before executing `git rev-parse --verify --end-of-options f"{ref}^{commit}"` (`shell=False`, timeout=5s).
  - **Collector (`collect_review_turn(rest, cwd)`):**
    - Verify inside git repo (`git rev-parse --is-inside-work-tree`), run `git diff --stat ...` + `git diff ...` (`shell=False`, timeout=10s, `errors="replace"`).
    - If empty diff -> return plain `"reply"` (`"No changes to review for ..."`) without calling the model.
    - Truncate diff bytes/chars at `REVIEW_MAX_DIFF_BYTES = 256 * 1024` with explicit truncation marker; frame inside `<untrusted_git_diff target="..." ...>\n...\n</untrusted_git_diff>` with explicit data-only instructions + sanitized `focus`.
    - Return `ReviewTurnPayload(prompt_text=..., routing_ask=...)` where `routing_ask` is strictly `/review <target> <sanitized_focus>` (never the diff body!).
  - **Loop execution (`loop/core.py`):**
    - Add small extracted helper `_run_review_preflight(...)` so `run_loop` stays `<= C (18)`.
    - On `action == "review"`: force `turn_interface = "tool"` (never `CodeactStint` or sticky `CodeactState`), enter `gate.enter_read_only(agent)` and always call `gate.exit_read_only(agent)` in `finally:`, route via `_route_pre_turn(ask_text=review_routing_ask)` on sanitized command/focus string only, skip `PLAN_PREFIX`, skip `@file` expansion on the diff payload, and skip `mode.note_plan_proposed()` on finish so sticky `ModeState` (`mode` and `pending_plan`) remains untouched (`D-11`).
