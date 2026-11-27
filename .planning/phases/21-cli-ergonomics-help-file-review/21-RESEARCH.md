# Phase 21: CLI Ergonomics (`/help`, `@file` / `/file`, `/review`) - Research

**Researched:** 2026-11-27
**Baseline `HEAD`:** `1915520` (clean working tree)
**Scope:** `LOOP-06`, `TOOL-05`, `REVIEW-01` (locked decisions `D-01`–`D-11` in `21-CONTEXT.md`)

---

## 1. Existing Codebase Seams & Live `radon cc` Baselines

### Command Dispatch, `BUILTIN_SLASH_HEADS` & `USAGE_HINT` (`LOOP-06`)
- [`strands_code_cli/memory/skills.py:21-46`](../../../strands_code_cli/memory/skills.py#L21-L46): `BUILTIN_SLASH_HEADS` currently holds 22 slash heads (`exit`, `resume`, `rename`, `forget`, `diff`, `search`, `policy`, `mode`, `approve`, `model`, `cost`, `compact`, `clear`, `context`, `skills`, `memory`, `init`, `btw`, `route`, `codeact`, `code`, `tool`). Adding `"help"`, `"file"`, and `"review"` brings it to 25 and automatically triggers built-in-wins / shadow warnings in `SkillIndex`.
- [`strands_code_cli/memory/skills.py:209-258`](../../../strands_code_cli/memory/skills.py#L209-L258): `SkillIndex.list_entries()`, `.resolve(text)`, `.ambiguous_matches(name)`, and `.warnings` already sanitize descriptions via `sanitize_display()` and compute `shadowed = skill.name.lower() in BUILTIN_SLASH_HEADS`.
- [`strands_code_cli/dispatch/core.py:68-78`](../../../strands_code_cli/dispatch/core.py#L68-L78): `USAGE_HINT` is currently a static string. Several existing tests assert exact substrings inside `USAGE_HINT`:
  - `tests/policy/test_diff_gate.py:169-170`: `"/diff"`, `"/search"`
  - `tests/policy/test_codeact.py:228,1424-1425`: `"/codeact [tool|code|both]"`, `"/code <ask>"`, `"/tool <ask>"`
  - `tests/policy/test_mode.py:399-400`: `"/mode [plan|act]"`, `"/approve"`
  - `tests/loop/test_loop_routing.py:770`: `"/route [on|off|status|setup"`
  - `tests/dispatch/test_router_btw.py:58`: `"/btw <side question>"`
  - `tests/memory/test_skills.py:240,390`: `f"Unknown command '/nope'. {USAGE_HINT}"` and `/skills [...]`
  - `tests/memory/test_memory_curate.py:423,1061`: `"approve <id>|deny <id>"`, `"/init [deeper]"`
  Deriving `USAGE_HINT` from the single declarative registry in `dispatch/help.py` (`D-01`) must preserve all of those signatures verbatim.
- [`strands_code_cli/dispatch/core.py:255-380`](../../../strands_code_cli/dispatch/core.py#L255-L380): `dispatch(...)` returns `(action, message)`. Today actions are `"agent"`, `"exit"`, `"reply"`, `"model"`. Adding `"prefill"` (for `/file` buffer pre-fill) and `"review"` (for `/review` read-only turn payload) keeps standalone unit callers working with an explicit tuple return.

### Completer & REPL Prompt Loop (`TOOL-05`)
- [`strands_code_cli/ui/completer.py:1-53`](../../../strands_code_cli/ui/completer.py#L1-L53): `SlashCompleter` completes only when `text.startswith("/") and " " not in text`; `build_completer(get_words)` wraps it in `DynamicCompleter(lambda: FuzzyCompleter(SlashCompleter(get_words)))`.
- [`tests/memory/test_skills.py:489`](../../../strands_code_cli/tests/memory/../memory/skills.py): Note that `tests/memory/test_skills.py:489` asserts `loop_source.count("completer=build_completer") == 1`, so `build_completer(get_words, get_files=None)` in `ui/completer.py` must keep the single call site in `loop/core.py:2750` (`completer=build_completer(_skill_words, _workspace_files)` or optional keyword) and keep `SlashCompleter` backward-compatible for single-arg test callers.
- [`strands_code_cli/loop/core.py:815,860-893`](../../../strands_code_cli/loop/core.py#L815): `_race_idle_episode` already passes `default=buf` to `session.prompt_async("> ", default=buf)`. Extending `_read_turn_input` / `_idle_prompt_multiplexed` with `initial_buf: str = ""` (and falling back cleanly to `session.prompt("> ", default=initial_buf)` or test doubles accepting `session.prompt("> ")` when `initial_buf` is empty) pre-fills `@<relpath> ` natively without spawning nested `prompt_toolkit` apps (`D-03`).

### Filesystem Confinement, Secrets & Policy Floor (`TOOL-05`)
- [`strands_code_cli/policy/scope.py:36-119`](../../../strands_code_cli/policy/scope.py#L36-L119): `effective_roots(cwd, policy, tool_name="read")` returns canonical `Path` roots (`cwd`, `/tmp`, plus read/`*` allow bases). Note that discovery for `@file` / `/file` should index gitignore-filtered files under `cwd` and non-`/tmp` configured read roots (avoiding indexing all of `/tmp` while still allowing explicit `@/tmp/...` paths confined under `effective_roots`).
- [`strands_code_cli/policy/core.py:877-959`](../../../strands_code_cli/policy/core.py#L877-L959): `_is_sensitive_read_path(raw, base)` refuses `.env*` (including `.envrc`), `~/.ssh/*`, `~/.aws/*`; `decide("read", ...)` evaluates active home + repo `PolicyConfig` (with fail-closed symlinked repo `policy.toml` refusal).
- [`strands_code_cli/policy/codeact.py:159-250`](../../../strands_code_cli/policy/codeact.py#L159-L250): Defines `CODEACT_MAX_FILE_BYTES = 4 * 1024 * 1024`, `_load_codeact_policy(real_base)`, `_refuse_raw_symlink_traversal(...)`, `refuse_symlink_under_roots(...)`, `O_NOFOLLOW | O_NONBLOCK`, and regular-file `os.fstat` verification. `ui/attachments.py` mirrors this exact fail-closed floor (`D-05`), plus `16 MiB` total per-turn bytes and `8`-attachment caps.

### Multimodal Blocks & Model Switching (`TOOL-05`)
- [`strands_code_cli/model/model_switch.py:263-319,397-438`](../../../strands_code_cli/model/model_switch.py#L263-L319):
  - `_MEDIA_PLACEHOLDER_RE = re.compile(r"\[(?:image|video): [^,\]]*, \d+ bytes\]")`
  - `_canonical_block(block)` drops `"image"` and `"video"` blocks and matching placeholders, **but does not drop `"document"` yet**.
  - `_media_placeholder_block(block)` and `_convert_block(block, new_id, reasoning_ok, media_ok)` only handle `"image"` and `"video"`, letting `"document"` pass verbatim to media-less targets!
  - Extending all 4 sites (`D-07`) to include `"document"` (`[document: <name>/<format>, <N> bytes]`) keeps switches onto media-less models safe and preserves `RichHistory` stashes + `canonical_prefix_hash`.
- [`strands_code_cli/cost/cost_context.py:799-840`](../../../strands_code_cli/cost/cost_context.py#L799-L840): `_block_chars` counts `text`, `toolUse`, `toolResult`, `reasoningContent`, `injected`, `summary` and safely ignores raw `bytes` on `"image"`/`"document"` blocks (avoiding counting raw PDF/PNG bytes as UTF-8 `chars / 4`). Explicitly adding/verifying `"document"` name metadata safety guarantees `estimate_messages_tokens` never inflates or fails on binary blocks.

### Read-Only Gate, CodeAct & Routing Order (`REVIEW-01`, `TOOL-05`)
- [`strands_code_cli/policy/policy_gate.py:75,604-620`](../../../strands_code_cli/policy/policy_gate.py#L604-L620): `PolicyGateHandler` exposes per-agent `enter_read_only(agent)` and `exit_read_only(agent)` (enforcing `PLAN_MUTATING_TOOLS = ("write", "edit", "shell", "python_repl")` via `event.cancel_tool`).
- [`strands_code_cli/loop/core.py:2913-2956`](../../../strands_code_cli/loop/core.py#L2913-L2956): Exact turn pipeline:
  `_set_gate_mode` -> `_compose_agent_text` -> `resolve_turn_interface` -> `shape_turn_text` -> `swap_for_code_turn` -> `_route_pre_turn(ask_text=...)` -> `_run_turn_attempts`.
  `_route_pre_turn` runs **before** `_run_turn_attempts`, which is the exact point to evaluate `supports_media(current_model)` post-routing (`D-06`), using text-only `ask_text` for routing (`D-06`/`D-10`), and only scanning user-typed ask text (never injected `/review` diffs, `PLAN_PREFIX`, `CODEACT_PREFIX`, or skill bodies) for `@file` tokens.
- [`strands_code_cli/loop/core.py:724-795`](../../../strands_code_cli/loop/core.py#L724-L795) and [`strands_code_cli/loop/pump.py:46-115`](../../../strands_code_cli/loop/pump.py#L46-L115): `_invoke_agent` and `_invoke_parallel` take `prompt: Any` (`str | list[dict[str, Any]]`) cleanly if annotated/typed cleanly and passed through to `agent(prompt, ...)`.

### Live `radon cc` Complexity Headroom (`HEAD` `1915520`)
- `loop/core.py`: `run_loop` **`C (18)`**, `_route_side_spawn` **`C (18)`**, `_extract_prompt_usage` `C (16)`, `_invoke_agent` `C (15)`. Ceiling is `xenon --max-absolute C` (`<= 20`)! Extracting non-turn dispatch helpers (`_handle_non_turn_action`) keeps `run_loop` at `<= 18`.
- `dispatch/core.py`: `_setup_pick_candidates_typed` **`C (18)`**, `_skills_remove_cmd` `C (17)`, `dispatch()` `< C (11)`.
- `entry/main.py`: `model_for_config` `C (18)`, `build_agent` **`C (15)`**, `_root` `C (15)`.
- `model/model_switch.py`: `resolve_harness_model` `C (18)`, `_canonical_block` **`C (15)`**, `_convert_block` `< C (11)`.

---

## 2. Live Upstream `.venv` SDK Verification

Verified via `.venv/bin/python` on `2026-11-27`:
1. **`Agent.__call__` prompt signature:** Accepts `str | list[ContentBlock] | ...`, passing `ContentBlock` lists into `BeforeInvocationEvent(messages=[{"role": "user", "content": prompt}])` before model or loop execution.
2. **Exact `strands.types.media` schemas:**
   - `ImageFormat = Literal["png", "jpeg", "gif", "webp"]`; `ImageContent = {"format": ..., "source": {"bytes": bytes}}`.
   - `DocumentFormat = Literal["pdf", "csv", "doc", "docx", "xls", "xlsx", "html", "txt", "md"]`; `DocumentContent = {"format": ..., "name": str, "source": {"bytes": bytes}}`.
   - Bedrock Converse API restricts `document.name` to `[A-Za-z0-9 \-()[\]]+` with no consecutive spaces; `sanitize_document_name()` in `ui/attachments.py` normalizes extensions/underscores/slashes/controls safely.
3. **`BeforeInvocationEvent.cancel` for CVE-2026-18830 (`RejectCallerToolUseHook`):**
   - Verified live on `strands.Agent`: registering a `BeforeInvocationEvent` callback at `HookOrder.SDK_FIRST` that inspects `event.messages` for any block with `"toolUse" in blk` and sets `event.cancel = "Rejected caller-supplied toolUse block"` halts execution **before** `model.stream` and **before** any tool executes (`model_called == False`, `tool_called == False`, `agent.messages` contains only the cancellation assistant message).
   - Must be attached idempotently across all 3 CLI agent factories (`entry/main.py:build_agent`, `loop/btw.py:_configure_btw_agent`, `entry/subagent.py:_configure_child_agent`).
4. **`FileSessionManager` media persistence:** Verified roundtrip of `ImageContent` and `DocumentContent` (`bytes` intact on session reload).

---

## 3. Security & Compatibility Risks Check

- **Restricted modules (`test_no_budgets_or_enforcement.py`):** `entry/main.py`, `dispatch/core.py`, `loop/core.py`, `loop/pump.py`, `model/model_switch.py`, `cost/cost_context.py` must contain **zero** `os.environ`/`os.getenv` tokens and **zero** unnegated `"budget"`, `"enforce"`, `"quota"`, `"halt"` substrings (watch docstrings and variable names carefully!).
- **`lint-imports`:** Feature modules must NEVER import `strands_code_cli.entry.main`.
- **Untrusted content hygiene:** Diff bodies (`/review`) and file bodies/paths (`@file`, `/help` skills) must be sanitized for ANSI/C1/Bidi escapes where rendered to terminal via `print_plain` / `sanitize_display`, and framed inside `<untrusted_git_diff>` / `<attached_file>` boundaries in prompts.
- **`D-24` Pristine Upstream Fork:** `git diff ee42ea2 -- strands_code_agent/` remains completely empty.
