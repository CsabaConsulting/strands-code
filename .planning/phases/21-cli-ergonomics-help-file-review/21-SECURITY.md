---
phase: "21"
slug: "cli-ergonomics-help-file-review"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-11-28"
---

# Phase 21 — Security

> Per-phase security contract: threat register, remediation verification, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| `Skill Metadata & Help Query -> Terminal Output (dispatch/help.py)` | User `/help [command\|skill]` queries plus local/third-party `SKILL.md` descriptions, paths, namespaces, and drift warnings rendered via `print_plain` | Single declarative `COMMANDS` table synced 1:1 with `BUILTIN_SLASH_HEADS` and `USAGE_HINT`; all skill names, paths, warnings, and unknown targets pass through `sanitize_display()` stripping ECMA-48/ANSI/C1/Bidi controls |
| `Caller Input & Stashed History -> Strands Event Loop (policy/tool_use_guard.py, model/model_switch.py, cost/cost_context.py)` | Multimodal prompt lists across `entry/main.py`, `loop/btw.py`, and `entry/subagent.py` plus `"document"` blocks across `/model` switches and `/cost` | `validate_content_blocks()` enforces strict single-key `text`/`image`/`document` dicts; 3-site `RejectCallerToolUseHook` (`HookOrder.SDK_FIRST` on `BeforeInvocationEvent`) walks messages recursively (`_depth <= 6`) and cancels caller `"toolUse"` blocks before model execution (`CVE-2026-18830`); `model_switch.py` converts `"document"` blocks safely without crashing on malformed payloads |
| `@file / /file Discovery & Attachments -> Agent Prompt (ui/attachments.py, ui/completer.py, loop/core.py)` | Untrusted workspace paths, filenames, `@token` references, TTY picker selections, and file bytes crossing into inline XML text or `ImageContent`/`DocumentContent` | Gitignore-aware `git -c core.fsmonitor=false ls-files` + bounded `os.walk`; filenames with `"` or `Cc`/`Cf` controls and symlink ancestors excluded; `effective_roots(tool_name="read")` confinement, `_refuse_token_symlinks()`, `O_NOFOLLOW \| O_NONBLOCK`, `S_ISREG`, NUL-byte rejection, `.env*`/`.ssh`/`.aws` + active `PolicyConfig` `[[deny]]` fail-closed checks, `4 MiB`/`16 MiB`/`8`-file bounds; post-routing `supports_media()` gate |
| `Git Diff & Repo Config -> Read-Only /review Turn (dispatch/review.py, loop/core.py)` | Adversarial `.git/config` / `.gitattributes`, git CLI refs, and untrusted repository diffs entering a review turn and `/route` pre-turn hook | Strict `<base-ref>` validation (`--verify --end-of-options <ref>^{commit}`), `-c core.fsmonitor=false -c core.pager=cat -c diff.external=`, `--no-ext-diff --no-textconv --no-color`, bounded streaming `_run_git_bounded()` (`256 KiB` diff / `64 KiB` stat), `sanitize_multiline()`, case-insensitive closing-tag escaping, diff-free `routing_ask`, `@file` diff skip, `PolicyGateHandler.enter_read_only`/`exit_read_only` (`finally:`), and `turn_interface="tool"` |

---

## Threat Register

Audited against Phase 21 Waves 1–3 (`dff1004`, `a721feb`, `fd5dfff`), UAT hardening commits (`fb8ab32`, `084cb37`, `5ab4746`, `174c56b`, `d10c6fd`), security remediation commit (`b5bd321`), [help.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/help.py), [tool_use_guard.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/tool_use_guard.py), [attachments.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/ui/attachments.py), [completer.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/ui/completer.py), [review.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/review.py), [dispatch/core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/core.py), [loop/core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/core.py), [loop/pump.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/pump.py), [model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py), [cost_context.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/cost/cost_context.py), `21-UAT.md` (`6/6` passed), and ASVS Level 1 remediations verified on `HEAD` at `security_block_on: high`.

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| `T-21-01` | CVE-2026-18830 Direct `"toolUse"` Execution Without Model Mediation | [tool_use_guard.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/tool_use_guard.py), [main.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/main.py), [btw.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/btw.py), [subagent.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/subagent.py) | high | mitigate | `register_reject_caller_tool_use_hook()` attaches idempotently at `HookOrder.SDK_FIRST` across all 3 CLI agent sites cancelling `BeforeInvocationEvent` fail-closed on both `agent(...)` and `agent.stream_async(...)`; historical assistant `toolUse` turns stay intact. | closed |
| `T-21-02` | `"document"` Block Switch Crash / Stash Tampering / Token Inflation | [model_switch.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/model/model_switch.py#L398-L455), [cost_context.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/cost/cost_context.py#L826-L828) | medium | mitigate | Extended `_MEDIA_PLACEHOLDER_RE`, `_canonical_block()`, `_media_placeholder_block()`, and `_convert_block()` for `"document"` parity; guarded `_media_placeholder_block()` against `None`/non-dict payloads and `,`/`]` across `"document"`/`"image"`/`"video"` (`084cb37`); excluded binary bytes from `_block_chars`. | closed |
| `T-21-03` | Terminal Escape Injection / Command Shadow Drift in `/help` | [help.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/help.py#L205-L296), [skills.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/memory/skills.py#L21-L50) | low | mitigate | Single declarative `COMMANDS` table synced 1:1 with `BUILTIN_SLASH_HEADS` and `USAGE_HINT`; sanitized all dynamic skill metadata/warnings/unknown targets via `sanitize_display()`, and aligned shadowed-skill guidance (`fb8ab32`). | closed |
| `T-21-04` | Arbitrary File Read / Symlink / FIFO / Secret / `[[deny]]` Bypass via `@file` | [attachments.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/ui/attachments.py#L57-L390) | high | mitigate | Enforces `effective_roots(tool_name="read")`, `_refuse_token_symlinks()` un-collapsed walk, `refuse_symlink_under_roots()`, NUL-byte refusal (`174c56b`), `O_NOFOLLOW \| O_NONBLOCK` + `os.fstat` `S_ISREG`, `.env*`/`.ssh/*`/`.aws/*` sensitive checks, and fail-closed home+repo `PolicyConfig` `[[deny]]` rules. | closed |
| `T-21-05` | Memory / Context DoS via Large or Flooded `@file` Attachments | [attachments.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/ui/attachments.py#L24-L32), [attachments.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/ui/attachments.py#L365-L505) | medium | mitigate | Enforces `4 MiB` per-file cap (checked at `os.fstat` and chunked `os.read`), `16 MiB` cumulative per-turn cap, `8` distinct attachment cap, and strict UTF-8 / extension allowlist refusal. | closed |
| `T-21-06` | Binary Attachment Routing Leak / Media-Less Model Crash / Unsafe Doc Labels | [attachments.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/ui/attachments.py#L253-L260), [loop/core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/core.py#L2745-L2768) | medium | mitigate | `_route_pre_turn()` receives raw ask text only (never file bodies/binary bytes); `supports_media(current_model)` aborts turn cleanly post-routing before model call; `sanitize_document_name()` strips unsafe Bedrock doc name characters (`<= 64` chars). | closed |
| `T-21-07` | Non-File `@token` False Positives & Spurious Diff Expansion | [attachments.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/ui/attachments.py#L315-L355), [loop/core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/core.py#L3131-L3137) | low | mitigate | Resolves only real existing regular files (unless explicit traversal/secret/symlink triggers fail-closed refusal), leaving `@dataclass`/`@pytest.mark`/emails untouched; sets `scan_attachments=False` on `/review` turns. | closed |
| `T-21-08` | Git Ref & Config RCE Injection via `/review` & `@file` Discovery | [review.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/review.py), [attachments.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/ui/attachments.py#L91-L120) | high | mitigate | Rejects leading `-`, `..`, whitespace, and `Cc`/`Cf` controls before `git rev-parse --verify --end-of-options <ref>^{commit}`; runs with `shell=False`, `-c core.fsmonitor=false -c core.pager=cat -c diff.external=`, and `--no-ext-diff --no-textconv --no-color` (`d10c6fd`, verified against live `diff.external`, `GIT_EXTERNAL_DIFF`, `textconv`, and `core.fsmonitor` RCE PoCs). | closed |
| `T-21-09` | `/review` Untrusted-Diff Prompt Injection & `/route` Body Exfiltration | [review.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/review.py), [loop/core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/core.py#L2647-L2660) | medium | mitigate | Wraps diff & `--stat` inside `<untrusted_git_diff>` data-only frame (`256 KiB` cap), sends diff-free `routing_ask` to `_route_pre_turn`, disables `@file` expansion, and runs under `PolicyGateHandler.enter_read_only(agent)` blocking mutating tools across main and delegated subagents. | closed |
| `T-21-10` | Sticky `ModeState` / `pending_plan` / `CodeactState` Corruption After `/review` | [loop/core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/core.py#L3102-L3176) | medium | mitigate | Pairs `enter_read_only`/`exit_read_only` across a `finally:` boundary, forces `turn_interface="tool"` without mutating sticky `CodeactState` or swapping `CodeactStint`, and keeps `note_plan=False` so `pending_plan` is never armed on normal exit, error, or `KeyboardInterrupt`. | closed |
| `T-21-11` | Control/Quote Filename Injection & Directory-Symlink Exposure in Discovery/Completer + Case-Variant `<attached_file>` Breakout | [attachments.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/ui/attachments.py#L53-L99), [completer.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/ui/completer.py#L87-L95) | **medium** | mitigate | **Discovered & remediated in this audit (`b5bd321`):** added `_has_unsafe_filename_chars()` (`"` and `Cc`/`Cf`) + `_refuse_token_symlinks()` inside `_is_candidate_safe()`, added `"`/`Cc`/`Cf` filter in `AtFileCompleter.get_completions()`, and replaced literal `</attached_file>` replace with case/whitespace-insensitive `_ATTACHED_CLOSE_RE`. | closed |
| `T-21-12` | Unbounded `/review` `git diff` Memory Read, Case-Variant Tag Breakout & Raw ANSI/Bidi Escape Injection | [review.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/review.py) | **medium** | mitigate | **Discovered & remediated in this audit (`b5bd321`):** replaced unbounded `subprocess.run` on `diff` / `--stat` with streaming `_run_git_bounded()` terminating git on overflow (`256 KiB` / `64 KiB`), added `sanitize_multiline()` on diff output, and escaped closing tags via `_DIFF_CLOSE_RE` / `_FOCUS_CLOSE_RE` (`re.IGNORECASE`). | closed |
| `T-21-13` | Multi-Key `ContentBlock` Craft & Nested `toolUse` Bypass in `tool_use_guard.py` | [tool_use_guard.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/tool_use_guard.py#L13-L61) | **high** | mitigate | **Discovered & remediated in this audit (`b5bd321`):** enforced single-key tagged union (`len(keys) == 1`) in `validate_content_blocks()` and bounded recursive `"toolUse"` traversal (`_depth <= 6`) in `contains_caller_tool_use()` catching nested smuggling (e.g., inside `toolResult.content`). | closed |
| `T-21-14` | REPL Crash on Ctrl-C During `/file` Picker | [attachments.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/ui/attachments.py#L230-L237) | low | mitigate | Caught `KeyboardInterrupt` cleanly inside `pick_file_for_prompt()` returning `(None, "File picker cancelled.")` (`5ab4746`) instead of unwinding past `_dispatch_turn_input`. | closed |

*Status: `open` · `closed`*
*Severity: `critical` > `high` > `medium` > `low` — only `open` threats at or above `workflow.security_block_on` (`high`) count toward `threats_open`*
*Disposition: `mitigate` (implementation verified) · `accept` (documented risk) · `transfer` (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| `R-21-01` | `T-21-01` | `strands_code_agent/` remains byte-identical to upstream `ee42ea2` (`D-24`); CLI `RejectCallerToolUseHook` covers all 3 CLI agent factories (`entry/main.py`, `loop/btw.py`, `entry/subagent.py`) while library-only `CodeAgent` relies on upstream `strands-agents` handling until an intentional resync. | secure-phase L1 audit | 2026-11-28 |
| `R-21-02` | `T-21-04`, `T-21-09` | `/review` collects git-tracked diff hunks (`HEAD` / `--staged` / `<base-ref>...HEAD`) inside `<untrusted_git_diff>` without blocking filenames matching `.env*` because `.env*` secrets belong untracked/gitignored; untracked `.env*` files are never included in `git diff`, whereas `@file` blocks `.env*` outright even if tracked. | secure-phase L1 audit | 2026-11-28 |
| `R-21-03` | `T-21-04` | Outside Strands Box, `effective_roots(cwd, policy, tool_name="read")` intentionally admits `/tmp` alongside `cwd` (consistent with `read` and `codeact_read`), bounded by `@file` symlink/ancestor refusal, `O_NOFOLLOW`, `S_ISREG`, and `.env*` sensitive-path denial; under `STRANDS_BOX=1`, host `/tmp` is unmounted (`TMPDIR=~/.cache/strands-code/tmp`). | secure-phase L1 audit | 2026-11-28 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-28 | 14 | 14 | 0 | `gsd-secure-phase` ASVS L1 audit (discovered & closed `T-21-11` MEDIUM control/quote filename + dir-symlink filter + case-insensitive `</attached_file>` escaping, `T-21-12` MEDIUM streaming bounded `_run_git_bounded()` + `sanitize_multiline()` diff sanitization + case-insensitive closing-tag escaping, and `T-21-13` HIGH single-key `validate_content_blocks` + recursive nested `"toolUse"` detection in `b5bd321`; verified on final code `b5bd321`: all live ASVS L1 red-team PoCs blocked, `uv lock --check` `Resolved 142 packages in 2ms`, `ruff format --check` `147 files already formatted`, `ruff check` `All checks passed!`, `xenon --max-absolute C --max-modules C --max-average C strands_code_cli tests scripts` exit `0` [`run_loop` `C 18`], `lint-imports` `Contracts: 1 kept, 0 broken` [`51` files, `165` deps], `git diff ee42ea2 -- strands_code_agent/` empty [`D-24`], restricted-module zero-`os.environ` audit clean, `pytest tests/rig/ -rs -q` `44 passed in 0.13s`, `TERM=xterm-256color GITHUB_ACTIONS=true pytest tests/ -k "not test_stub_server_systemone_decision_routes" -rs -q` `2077 passed, 16 deselected in 75.83s`, loopback stub `1 passed, 202 deselected in 2.49s` [`2078` total default tests], and `21-UAT.md` `6/6` passed) |

---

## Sign-Off

- [x] All threats have a disposition (`mitigate` / `accept` / `transfer`)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-28
