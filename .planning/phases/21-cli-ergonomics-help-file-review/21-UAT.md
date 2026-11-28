---
status: complete
phase: 21-cli-ergonomics-help-file-review
source: [21-01-SUMMARY.md, 21-02-SUMMARY.md, 21-03-SUMMARY.md, 21-VERIFICATION.md]
started: 2026-11-28T00:17:00Z
updated: 2026-11-27T16:52:52Z
---

# Phase 21 User Acceptance Testing (`LOOP-06`, `TOOL-05`, `REVIEW-01`)

## Current Test

[testing complete]

## Tests

### 1. /help Declarative Registry, USAGE_HINT Sync & Live Skill + Warning Rendering (LOOP-06, D-01, D-02)
expected: Single declarative command table in `strands_code_cli/dispatch/help.py` (`COMMANDS`, 25 heads matching `BUILTIN_SLASH_HEADS` 1:1) drives both `/help` and `USAGE_HINT`; bare `/help` renders grouped built-in commands plus live loaded skills (`[shadowed by built-in]` when applicable) and sanitized shadow/drift warnings via `print_plain`; `/help <command|skill>` resolves both built-in commands and loaded skills cleanly.
result: pass
evidence: |
  - Functional probe on `HEAD` `dc2da22`:
    - `COMMANDS` (25 specs) matches `BUILTIN_SLASH_HEADS` 1:1 (`help`, `file`, `review` included) and `USAGE_HINT == build_usage_hint()`.
    - Live `dispatch()` succeeded across all active `COMMANDS` heads, `/help` works under `CodeactState("both")` and `ModeState("plan")`, and bare `/`, `///review`, extra args, ambiguous multi-namespace skills (`mp1:dup`, `mp2:dup`), ANSI/Bidi (`\u202e`) sanitization, and `SlashCompleter` `/help` + shadowed-skill filtering all cleared.
  - Adversarial pre-check gap found on `dc2da22` & fixed in commit `fb8ab32` (`strands_code_cli/dispatch/help.py:225-228` + `tests/dispatch/test_help.py:120-132`):
    - `[Code/UX Gap]` Aligned `_format_skill_detail` note with `SkillIndex.warnings` / `_dispatch_skill_turn` (`Note: Built-in '/review' takes precedence — rename the skill to invoke it.`) and added regression assertions verifying `/help local:help` and `/local:help extra` (`Unknown command`).
  - Re-verified on fix `HEAD` `fb8ab32` (`Gaps found: None`): `68 passed` (`tests/dispatch/test_help.py`, `tests/memory/test_skills.py`), `ruff format --check` (`147 files`), `ruff check`, `xenon --max-absolute C`, `lint-imports` (`1 kept, 0 broken`), and live `help_message("local:review", skills)` output (`Note: Built-in '/review' takes precedence — rename the skill to invoke it.`).

### 2. RejectCallerToolUseHook (CVE-2026-18830 3-Site Guard) & "document" Block Model-Switch / Cost Parity (TOOL-05, D-07, D-08)
expected: `RejectCallerToolUseHook` attaches at all 3 CLI agent factories (`entry/main.py`, `loop/btw.py`, `entry/subagent.py`) cancelling caller-supplied `"toolUse"` fail-closed on `BeforeInvocationEvent`; `validate_content_blocks` strictly allowlists `text`/`image`/`document`; `model_switch.py` converts `"document"` blocks to `[document: <name>/<format>, <N> bytes]` on media-less targets while preserving `RichHistory` stashes and `canonical_prefix_hash`; `cost_context._block_chars` accounts safely without inflating binary bytes.
result: pass
evidence: |
  - Functional probe on `HEAD` `fb8ab32`:
    - 3-site hook registration verified across `entry/main.py`, `loop/btw.py`, and `entry/subagent.py`; both `agent(...)` and `agent.stream_async(...)` (`loop/pump.py`) cancel caller-supplied `"toolUse"` (`ContentBlock` list, `user` `Message` list, and `assistant` `Message` list) before model execution (`calls == 0`), while Turn 2 after historical assistant `toolUse` + user `toolResult` executes cleanly (zero false positives).
    - `validate_content_blocks` strictly allowlists `text`/`image`/`document`; `to_stash_json`/`from_stash_json` round-trips `"document"` bytes; multi-hop `claude -> deepseek -> away turn -> claude` restores `RichHistory` stash (`restored=True`, `len=4`, original bytes intact); `_block_chars` accounts for 4 MiB document + 4 MiB image without inflating token estimate (`2` tokens).
  - Adversarial pre-check gap found on `fb8ab32` & fixed in commit `084cb37` (`strands_code_cli/model/model_switch.py:398-420` + `tests/model/test_model_switch.py:5745-5775`):
    - `[Code/Robustness Gap]` Extracted `_safe_placeholder_token()` and guarded `_media_placeholder_block()` against `None`/non-dict payloads and `source` dicts across `"document"`, `"image"`, and `"video"`, stripping `,` and `]` from both `format` and `name`.
  - Re-verified on fix `HEAD` `084cb37` (`Gaps found: None`): `276 passed` (`tests/model/test_model_switch.py`, `tests/policy/test_tool_use_guard.py`, `tests/cost/test_cost_context.py`), `ruff format --check` (`147 files`), `ruff check`, `xenon --max-absolute C`, `lint-imports` (`1 kept, 0 broken`), and live probe across all 6 malformed/punctuated payloads (`source_none`, `doc_none`, `img_none`, `img_source_none`, `doc_weird_format`, `doc_non_dict_source`) with `matches_re=True hash_inv=True`.

### 3. Inline @file Fuzzy Completion, /file TTY Picker Pre-Fill & Real-File-Only Text/Binary Encoding (TOOL-05, D-03, D-04)
expected: Composite `SlashCompleter` + `AtFileCompleter` fuzzy-completes `@<path>` mid-line from gitignore-aware `effective_roots` without breaking `/` or `/<ns>:`; `/file [filter]` opens a TTY picker pre-filling `@<relpath> ` via `default=buf` (non-TTY returns usage reply); only real regular files resolve (`@dataclass`, `@pytest.mark`, emails untouched), injecting UTF-8 text inline in `<attached_file>` and binary images/docs via `ImageContent`/`DocumentContent`.
result: pass
evidence: |
  - Functional probe on `HEAD` `084cb37`:
    - Gitignore-aware discovery (`discover_workspace_files`) excludes `.gitignore` entries (`ignored.txt`, `build/out.txt`) and deleted tracked files (`sub/deleted.py`) at both repo root and subdirectories.
    - Composite `build_completer` preserves `/hel`, `/rev`, `/local:aud`, completes `@`, `@att`, `@atmt`, `@ui/att`, `@notes`, `(@READ`, and ignores `email@example.com`; `Buffer.apply_completion` yields exact replacement strings.
    - Real-file-only resolution leaves `@dataclass`, `@pytest.mark.parametrize`, `user@example.com`, and `a.b@example.com` untouched while resolving `@README.md,` (trailing comma + `</attached_file>` escaping), `@"sub/my doc.PDF"` (quoted space + uppercase `.PDF` -> `document` block with sanitized `name='my doc'`), and `(@sub/pic.JPG)!` (uppercase `.JPG` -> `image/jpeg`); rejects unsupported `@sub/bin.zip`; `sanitize_document_name()` handles emoji fallback, collapsing, and 64-char cap; `format_at_reference` round-trips into `extract_at_tokens`.
  - Adversarial pre-check gaps found on `084cb37` & fixed in commit `5ab4746` (`strands_code_cli/ui/attachments.py:230-237`, `strands_code_cli/ui/completer.py:20-97`, `tests/ui/test_attachments.py:74-141`):
    1. `[Code/UX Bug]` Changed `pick_file_for_prompt()` `radio_choice(..., default=1)` to `default=0` so `/file` highlights the first match (`options[0]`).
    2. `[Code/Crash Gap]` Caught `KeyboardInterrupt` in `pick_file_for_prompt()` returning `(None, "File picker cancelled.")` so Ctrl-C inside `/file` never crashes the session.
    3. `[Code/UX Gap]` Updated `_AT_QUERY_RE` and `AtFileCompleter.get_completions` with `_is_subsequence` and open-quote `@"<query>` handling (`start_pos = -(len(quoted) + 2)`), supporting fuzzy cross-segment completion (`check @s_c/att`) and quoted paths with spaces (`check @"my notes`).
  - Re-verified on fix `HEAD` `5ab4746` (`Gaps found: None`): `81 passed` (`tests/ui/test_attachments.py`, `tests/loop/test_loop_attachments.py`, `tests/memory/test_skills.py`), `ruff format --check` (`147 files`), `ruff check`, `xenon --max-absolute C`, `lint-imports` (`1 kept, 0 broken`), and live `Buffer.apply_completion` probe across `check @s_c/att`, `check @"my`, `check @"my notes`, `check @"foo" `, `email@example.com`, and `/hel`.

### 4. Fail-Closed @file Security Floor, Policy [[deny]] / Caps & Post-Routing supports_media Abort Gate (TOOL-05, D-05, D-06)
expected: `@file` / `/file` matches `read`/`codeact_read` security parity fail-closed (`effective_roots(tool_name="read")`, target & ancestor symlink refusal + `O_NOFOLLOW` + regular-file check, `.env*`/`~/.ssh/*`/`~/.aws/*` and `[[deny]]` refusal, symlinked `.agent/policy.toml` refusal, `4 MiB`/`16 MiB`/`8`-file caps); `/route` sees ask text only and `supports_media(current_model)` aborts cleanly post-routing on media-less targets before calling the model.
result: pass
evidence: |
  - Functional probe on `HEAD` `5ab4746`:
    - Symlinked workspace cwd (`ws_link -> work`) reads `@ok.txt` cleanly; directories (`@subdir`) and FIFOs (`@myfifo`) are refused (`not a regular file`) via `O_NOFOLLOW | O_NONBLOCK` + `os.fstat` `S_ISREG`.
    - Symlinked `.agent/policy.toml` fails closed in both `prepare_turn_prompt()` and `discover_workspace_files()` (`[]`); corrupt `.agent/policy.toml` keeps home `[[deny]]` rules (`secrets/**`, `home_secret.txt`) active.
    - Relative glob `[[deny]]` (`secrets/**`), nested `sub/.env.prod`, `/tmp/.env`, trailing-punctuated `@.env.` / `@.env.local,` / `@~/.ssh/id_rsa.`, non-existent `@~/.ssh/nonexistent_key`, `/tmp` symlink escape (`/tmp/sym -> /etc/hosts`), and traversal escaping `/tmp` (`@types/../../../../etc/hosts`) all refuse cleanly while benign `@types/node` stays untouched.
    - `16 MiB` cumulative cap (`5 x 3.5 MiB`) aborts cleanly, duplicate `@ok.txt` (x12) deduplicates to `1` attachment, and post-routing `supports_media` gate (`tests/loop/test_loop_attachments.py`) verifies `/route` receives ask text only before aborting on a media-less routed model.
  - Adversarial pre-check gap found on `5ab4746` & fixed in commit `174c56b` (`strands_code_cli/ui/attachments.py:298-330` + `tests/ui/test_attachments.py:331-339`):
    - `[Code/Crash Gap]` Rejected `"\x00"` upfront in `_trim_sentence_punct()` and `_resolve_attachment_target()`, returning `(None, "Refused @file attachment: invalid NUL byte in path.")` instead of propagating `ValueError` from `Path.exists()`.
  - Re-verified on fix `HEAD` `174c56b` (`Gaps found: None`): `19 passed` (`tests/ui/test_attachments.py`, `tests/loop/test_loop_attachments.py`), `ruff format --check` (`147 files`), `ruff check`, `xenon --max-absolute C`, `lint-imports` (`1 kept, 0 broken`), and live NUL-byte probe (`(None, 'Refused @file attachment: invalid NUL byte in path.')`).

### 5. Read-Only /review Diff Collection, Ref Validation, Untrusted-Diff Framing, /route Isolation & Turn-Scoped Read-Only Plan Gate (REVIEW-01, D-09–D-11)
expected: `/review [HEAD|--staged|<base-ref>] [-- <focus>]` validates `<base-ref>` fail-closed (`git rev-parse --verify --end-of-options <ref>^{commit}`, `shell=False`), short-circuits empty diffs/non-git dirs, bounds diffs at `256 KiB` inside `<untrusted_git_diff>`, sends diff-free `routing_ask` to `/route`, enforces turn-scoped `PolicyGateHandler.enter_read_only`/`exit_read_only` (`finally:`) + forced `turn_interface = "tool"` without mutating sticky `ModeState`, `pending_plan`, or `CodeactState` and without scanning diffs for `@file`.
result: pass
evidence: |
  - Functional probe on `HEAD` `174c56b`:
    - `PolicyGateHandler` denies all 4 `PLAN_MUTATING_TOOLS` (`write`, `edit`, `shell`, `python_repl`) during `enter_read_only(agent)`, leaves sticky `plan` mode intact after `exit_read_only(agent)` (`write` still denied), restores `act` cleanly on `KeyboardInterrupt`, and propagates read-only posture to delegated `subagent` children (`entry/subagent.py:187-188`).
    - Fail-closed `<base-ref>` validation rejects `--output=/tmp/x`, `-p`, `HEAD..HEAD`, `HEAD\nmain`, `HEAD\u202emain`, `HEAD\x00x`, and `nonexistent_ref_xyz`.
    - `256 KiB` truncation cleanly handles 4-byte UTF-8 emoji (`🚀 * 70000`, `truncated="true"`), produces diff-free `routing_ask` (`'/review staged check unicode'`), forces `turn_interface="tool"` without mutating `CodeactState`/`ModeState`/`pending_plan`, and skips `@file` scanning on diffs.
  - Adversarial pre-check gaps found on `174c56b` & fixed in commit `d10c6fd` (`strands_code_cli/dispatch/review.py:66-195`, `strands_code_cli/ui/attachments.py:91-118`, `tests/dispatch/test_review.py:162-179`):
    1. `[Code/Security Gap — Untrusted Repo Git RCE]` Added `-c core.fsmonitor=false -c core.pager=cat -c diff.external=` to `_run_git()` + `--no-ext-diff --no-textconv` to both `git diff` calls in `review.py`, and horizontally backported `-c core.fsmonitor=false` to sibling `_git_ls_files()` in `attachments.py`.
    2. `[Code/Hygiene Gap]` Added `--no-color` to both `git diff` calls in `review.py` so `color.diff=always` cannot inject raw ANSI escapes into `<untrusted_git_diff>`.
  - Re-verified on fix `HEAD` `d10c6fd` (`Gaps found: None`): `31 passed` (`tests/dispatch/test_review.py`, `tests/loop/test_loop_review.py`, `tests/ui/test_attachments.py`), `ruff format --check` (`147 files`), `ruff check`, `xenon --max-absolute C`, `lint-imports` (`1 kept, 0 broken`), and live probe verifying `diff.external` (`False`), `diff.<driver>.textconv` (`False`), and `color.diff=always` (`False`) neutralization.

### 6. Documentation (docs/QUICKSTART.md), Full Test Suite, Rig Contracts & All 6 CI Gates (D-24)
expected: `docs/QUICKSTART.md` documents `/help`, `@file` / `/file`, and `/review`; full non-integration suite + loopback routing test, `tests/rig/` contracts, restricted-module grep, `uv lock --check`, `ruff format --check`, `ruff check`, `xenon --max-absolute C`, `lint-imports`, and empty `git diff ee42ea2 -- strands_code_agent/` all pass on `HEAD`.
result: pass
evidence: |
  - Functional & full CI verification on `HEAD` `d10c6fd` (`Gaps found: None`):
    - `docs/QUICKSTART.md` (`## CLI Ergonomics (/help, @file / /file, /review)`, lines 466–481) accurately documents `/help` / `/help <command|skill>`, `@file` / `/file [filter]` (UTF-8 `<attached_file>`, native images/docs post-routing, fail-closed security floor & `4 MiB` cap), and `/review [--staged|<base-ref>] [focus...]` (`256 KiB` `<untrusted_git_diff>`, turn-scoped read-only tool interface).
    - Static & hygiene gates: `uv lock --check` (`142 packages`), `ruff format --check` (`147 files`), `ruff check`, `xenon --max-absolute C --max-modules C --max-average C` (`run_loop` `C (18)`), `lint-imports` (`51 files, 165 deps, 1 kept / 0 broken`), empty `git diff ee42ea2 -- strands_code_agent/` (`D-24`), and restricted-module zero-`os.environ`/`os.getenv` check all green.
    - `tests/rig/`: `44 passed in 0.15s`.
    - Full non-integration suite (`TERM=xterm-256color GITHUB_ACTIONS=true`): `2073 passed, 16 deselected in 73.48s`.
    - Standalone loopback stub (`test_stub_server_systemone_decision_routes`, `BypassSandbox: true`): `1 passed, 202 deselected in 2.37s` (`2074` total default tests passing).

## Summary

total: 6
passed: 6
issues: 0
pending: 0
skipped: 0

## Gaps

None open — all 8 adversarial pre-check gaps discovered across Tests 1–5 were fixed and re-verified on `HEAD` `d10c6fd` (commits `fb8ab32`, `084cb37`, `5ab4746`, `174c56b`, `d10c6fd`).
