---
phase: 01-session-wiring-repl-skeleton
reviewed: 2026-09-24T07:10:46Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - .gitignore
  - pyproject.toml
  - strands_code_cli/__init__.py
  - strands_code_cli/first_run.py
  - strands_code_cli/loop.py
  - strands_code_cli/main.py
  - strands_code_cli/provider_config.py
  - strands_code_cli/router.py
  - strands_code_cli/session_index.py
  - tests/test_cli_entry.py
  - tests/test_first_run.py
  - tests/test_kill_resume.py
  - tests/test_session_index.py
  - tests/test_session_resume.py
findings:
  critical: 1
  warning: 7
  info: 5
  total: 13
status: issues
---

# Phase 01: Code Review Report

**Reviewed:** 2026-09-24T07:10:46Z
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues

## Summary

Standard-depth review of the Phase 1 tracer + expansion + durability slices (REPL entry, session wiring via `create_harness`, sidecar index, Bedrock-or-stop gate, kill-resume). All 67 tests across the five in-scope test files pass. The threat-model mitigations were checked against the installed SDK/harness and mostly hold: `--session-id` traversal is blocked twice (SDK `validate_identifier` rejects `/`, harness `_sanitize_session_id` maps `[^a-z0-9_-]` to `-`), per-message saves are real (`save_latest_on="message"` in harness), `explicit_save` matches the async `save_snapshot(agent, *, is_latest=True)` signature, and the `session/<id>` picker join matches the on-disk layout.

One critical robustness bug (any transient model error kills the REPL without saving) and seven warnings remain, led by: titles containing `[..]` silently mangled by Rich markup in the picker, picker-selected ids bypassing CLI validation, and REPL history written without the 0o700 standard the phase applies everywhere else. No credential-handling defects found: the probe never reads credentials directly, only the exception type name is logged, and the config file holds only the model string.

## Critical Issues

### CR-01: Unhandled agent-turn exception kills the REPL, skipping the exit save

**File:** `strands_code_cli/loop.py:114-118`
**Issue:** `run_loop` wraps `agent(text)` in `patch_stdout` but catches only `KeyboardInterrupt`. Any other failure from a turn — Bedrock throttling, credential expiry mid-session, model output errors — propagates out of `run_loop`, so `explicit_save(agent)` and `index.ensure(session_id)` at the end never run and the CLI exits with a traceback. The D-08 per-message saves limit the damage, but the deterministic clean-exit flush (the stated purpose of `explicit_save`) is skipped on exactly the failure path where it matters most, and a transient API error ends the whole conversation instead of showing an error and re-prompting.
**Fix:**
```python
        try:
            with patch_stdout():
                agent(text)
        except KeyboardInterrupt:
            console.print("[yellow]Turn interrupted; earlier turns are saved.[/yellow]")
        except Exception as exc:
            logger.warning("Agent turn failed: %s", exc)
            console.print(f"[red]Turn failed ({type(exc).__name__}); earlier turns are saved.[/red]")
```

## Warnings

### WR-01: REPL history file written without restrictive permissions

**File:** `strands_code_cli/loop.py:27-37`
**Issue:** `_history()` creates the platformdirs cache dir with default permissions and stores raw user prompts (which may contain secrets, per the phase threat model) in `repl_history` with umask-default modes. Every other Phase 1 store (session dir in `main.py:70`, index root in `session_index.py:44`, config parent in `provider_config.py:85`) is explicitly chmodded `0o700` per T-01-03, but the history path was missed, so on a shared machine or typical `022` umask other users can read prompt history.
**Fix:**
```python
        cache = Path(platformdirs.user_cache_dir("strands-code"))
        cache.mkdir(parents=True, exist_ok=True)
        os.chmod(cache, 0o700)
        return FileHistory(str(cache / "repl_history"))
```

### WR-02: Rich markup silently swallows `[..]` sequences in session titles

**File:** `strands_code_cli/router.py:92-95`
**Issue:** The picker, `/resume` output, and rename confirmations print index-controlled titles through `Console.print`, which interprets `[...]` as Rich markup. Verified live: printing `Session renamed to [v2] plan.` renders as `Session renamed to  plan.` — the `[v2]` vanishes. Any title containing brackets (user rename allows them; `_validate_title` only rejects `/`, `\`, NUL, blanks) is misrendered, degrading the D-03 "picker stays readable" requirement. No crash (Rich tolerates unclosed tags), but titles are not shown faithfully.
**Fix:** Escape titles at every print site, e.g. `from rich.markup import escape` and `console.print(f"  {pos}. {escape(title)} [{entry['id'][:8]}]")`, or pass `markup=False` where the console supports it. Same treatment needed in `_resume_message` output printed at `loop.py:111-112` and `_rename_message` at `router.py:71`.

### WR-03: Picker-selected session ids bypass `_validate_session_id`

**File:** `strands_code_cli/main.py:103-107`
**Issue:** Explicit `--session-id` values pass through `_validate_session_id`, but ids coming back from `show_picker` go straight to `index.ensure(picked)`, whose `_validate_id` rejects only blank strings. A hand-edited or legacy `index.json` entry with a malformed id therefore flows into `build_agent`/`create_harness` without the CLI's usage-error path (T-02-02 treats the sidecar as untrusted, but only the read side is fail-soft). Related: an unknown-but-wellformed explicit id is silently registered as a fresh session via `ensure`, while the SES-01 flagged assumption leans toward a usage error — confirm which behavior is intended.
**Fix:**
```python
        picked = show_picker(index, session_dir=DEFAULT_SESSION_DIR)
        if picked is not None:
            try:
                picked = _validate_session_id(picked)
            except ValueError:
                logger.warning("Ignoring invalid session id in index: %r", picked)
                picked = None
        resolved = index.ensure(picked)["id"] if picked is not None else index.mint()
```

### WR-04: `list_recent` sort crashes on non-string `updated_at` in a tampered index

**File:** `strands_code_cli/session_index.py:132-143`
**Issue:** `_ensure_loaded` fail-softs on corrupt JSON but accepts any dict-shaped entries, and `list_recent` sorts with `key=lambda item: item[1].get("updated_at", "")`. A hand-edited index mixing a numeric and a string `updated_at` raises `TypeError: '<' not supported between 'int' and 'str'`, crashing the picker — the fail-soft read guarantee does not survive the sort. Low exploitability (needs local file write) but the phase explicitly treats the sidecar as untrusted (T-02-02).
**Fix:** Coerce the sort key, e.g. `key=lambda item: str(item[1].get("updated_at", ""))`, and drop entries that are not dicts with string titles at load time.

### WR-05: `ProviderConfig.load` failures escape `_root` as a traceback

**File:** `strands_code_cli/main.py:99`
**Issue:** `ProviderConfig.load()` raises `ValueError` for symlinked configs and unknown keys (pinned by `test_unknown_keys_rejected`), but `_root` calls it with no `try/except`, so a user with a stale/foreign `config.yaml` gets an unhandled traceback instead of a clean error. The T-03-02 mitigation (reject unknowns) is correct at the `load` layer; the CLI boundary needs to translate it.
**Fix:**
```python
    try:
        config = ProviderConfig.load()
    except ValueError as exc:
        raise typer.BadParameter(f"invalid provider config: {exc}") from exc
```

### WR-06: Session id case divergence between index, picker, and snapshot store

**File:** `strands_code_cli/main.py:37-46`, `strands_code_cli/router.py:108-112`
**Issue:** Verified against the installed SDK: `validate_identifier` accepts uppercase ids (`'ABC-123'` passes), while the harness sanitizes storage ids with `re.sub(r"[^a-z0-9_-]", "-", id.strip().lower())`. So `--session-id <UPPERCASE-uuid>` is accepted by the CLI, stored verbatim as the index key, but persisted on disk lowercased. The picker's `_has_snapshot` then checks the raw (uppercase) path, finds nothing, and hides the session as an orphan — the session works for direct resume (sanitization is deterministic) but is invisible in the picker. Same divergence applies to any id containing characters the harness remaps.
**Fix:** Normalize once at the CLI boundary, e.g. `return checked.lower()` (or at least the hex form) in `_validate_session_id` after validation, so index keys, picker joins, and snapshot prefixes agree.

### WR-07: Fail-soft read plus unconditional save can wipe the whole title index

**File:** `strands_code_cli/session_index.py:55-84`
**Issue:** A missing/corrupt index loads as `{}` (per spec), but the next `mint`/`ensure`/`rename` calls `_save()`, atomically replacing the file — any transient read failure (`EACCES`, torn write from a killed process) followed by any write silently discards every known title and rename flag. The corrupt-file test pins the read side; nothing guards the write side.
**Fix:** Track whether the load succeeded (e.g. `self._loaded_ok`); if the backing file existed but failed to parse, back it up (`index.json.corrupt.<ts>`) and either refuse to overwrite or proceed only after backup, plus a warning log.

## Info

### IN-01: Duplicate mixed-case pointer alias in `main.py`

**File:** `strands_code_cli/main.py:34`
**Issue:** `Bedrock_SETUP_POINTER = BEDROCK_SETUP_POINTER` re-exports the pointer under a second name that no in-scope file references (tests import `BEDROCK_SETUP_POINTER` from `first_run`). Dead alias with inconsistent capitalization invites import confusion.
**Fix:** Delete the alias and import `BEDROCK_SETUP_POINTER` from `first_run` at any future use site.

### IN-02: `_validate_id` docstring contradicts the picker path join

**File:** `strands_code_cli/session_index.py:177-182`, `strands_code_cli/router.py:108-112`
**Issue:** The docstring claims ids "are dict keys, never path segments," but `router._has_snapshot` joins them directly under `<session_dir>/session/<id>`. The claim is currently true only because upstream layers (SDK validation, harness sanitization) neutralize separators — not because this module enforces it.
**Fix:** Correct the docstring and consider an allowlist (`[a-z0-9_-]`, case-normalized) in `_validate_id` so the module upholds its own contract.

### IN-03: `assert` used for a real invariant in `_save`

**File:** `strands_code_cli/session_index.py:78`
**Issue:** `assert self._entries is not None` documents "callers run `_ensure_loaded` first," but asserts vanish under `python -O`, after which `_save` would serialize `None` and write `"null"` over the index. All current callers comply, so this is latent only.
**Fix:** Replace with an explicit guard: `if self._entries is None: raise RuntimeError(...)`.

### IN-04: All probe failures map to the same "no credentials" pointer

**File:** `strands_code_cli/first_run.py:42-50`
**Issue:** `except Exception` converts every probe failure — missing credentials, missing region, no network, proxy errors — into `BEDROCK_SETUP_POINTER`, which only advises on the credentials case. Correct fail-closed behavior; the message just misdiagnoses non-credential failures.
**Fix:** Keep exit code 2, but append the probed failure class already captured in the warning log, e.g. include a hint when the failure is not credential-shaped.

### IN-05: Config file itself inherits umask permissions; tmp file can litter

**File:** `strands_code_cli/provider_config.py:76-89`
**Issue:** The config parent dir is chmodded `0o700`, which is sufficient while the file holds only the model string — but the file itself is never chmodded, so if Phase 5 ever stores anything more sensitive here it will default to `0644`. A crashed save can also leave `config.yaml.tmp` behind.
**Fix:** `os.chmod(resolved, 0o600)` after replace (cheap future-proofing), and write the tmp file with `os.open(..., 0o600)` or clean up stale `.tmp` on load.

---

_Findings excluded by v1 scope: none (no performance-only issues raised)._
_Test files reviewed for reliability only; no test defects affecting the verdict were found. The clean-exit test (`test_explicit_save_round_trips_last_turn`) cannot distinguish the explicit flush from per-message saves, so it would stay green even if `explicit_save` silently no-op'd — worth strengthening when CR-01 is fixed._
_Reviewed: 2026-09-24T07:10:46Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
