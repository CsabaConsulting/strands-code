---
phase: "20"
slug: "monty-python-vm-for-python-repl-codeact"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-11-27"
---

# Phase 20 — Security

> Per-phase security contract: threat register, remediation verification, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| `Agent Python Code -> MontyPythonInterpreter (sandbox/monty.py)` | Untrusted LLM-generated Python snippets across main REPL (`entry/main.py`), CodeAct (`policy/codeact.py`), and `/btw` + `subagent` delegates (`loop/btw.py`, `entry/subagent.py`) | AST denied-import check (`os`, `pathlib`, `subprocess`, `__import__`, `importlib`) + `pydantic-monty` `os=None` Rust VM process isolation (`256 MiB` RAM, `60s` wall duration, `200` recursion, `4 MiB` stdout cap, `TimeoutError` / `MontyCrashedError` session reset & salvage), zero fallback to in-process `smolagents` |
| `Monty VM Callbacks -> Host FS & Shell (policy/codeact.py)` | Host callbacks (`read`, `write`, `edit`, `shell`) exposed to `CodeactStint` via `external_lookup` | Un-collapsed raw-segment symlink traversal walk (`_refuse_raw_symlink_traversal`), `confine()` + `refuse_symlink_under_roots()`, `O_NOFOLLOW \| O_NONBLOCK` + `os.fstat` + `CODEACT_MAX_FILE_BYTES` (`4 MiB`) strict UTF-8 read, `atomic_write_text`, sensitive-read (`.env*`, `.ssh/*`, `.aws/*`) & protected-path blocks, active non-interactive `PolicyConfig` `[[deny]]` rules (fail-closed on symlinked `.agent/policy.toml`, wrapper-unwrapped shell commands), and `4 MiB` shell output cap |
| `Shared Worker Pool & Delegate Teardown (sandbox/monty.py, entry/subagent.py, loop/core.py)` | Process-wide `Monty()` pool, per-interpreter sessions, `/btw` side agents, and pending/completed `subagent` children | Safe `os.X_OK` + `Cc`/`Cf` `binary_path` validation before swapping `_SHARED_POOL`; deterministic cleanup across `_close_loop_session()`, `CodeactStint.close()`, `_teardown_btw_agent()`, `_wrap_subagent_cleanup()` (incl. pending child `_close_children()`), and `atexit` |
| `Strands Box Exec Grant & Upstream Boundary (sandbox/box.py, strands_code_agent/)` | Generated `box.toml` / `policy.dw` containment mounts for `monty` worker binary + fork boundary (`D-24`) | Canonical `realpath`, `os.X_OK`, non-root parent (`_valid_nonroot_dir`), and `Cc`/`Cf` validation on `MONTY_BIN` / `.venv/bin/monty` / `PATH` before `[agent.filesystem].exec` & `[agent.env].MONTY_BIN`; embedded `[tool.python]` omitted; `strands_code_agent/` byte-identical to `ee42ea2` |

---

## Threat Register

Audited against Phase 20 Waves 1–3 (`bc28c40..f177e5e`), UAT fixes (`ea35d49..d813b0a`), [monty.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/monty.py), [codeact.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/codeact.py), [main.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/main.py), [btw.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/btw.py), [subagent.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/subagent.py), [loop/core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/core.py), [box.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/box.py), [QUICKSTART.md](file:///home/csaba/repos/AWS/strands-code/docs/QUICKSTART.md), `20-UAT.md` (`6/6` passed), and ASVS Level 1 remediations verified on `HEAD` at `security_block_on: high`.

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| `T-20-01` | In-Process Host-Memory Tampering | [main.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/main.py#L235-L237), [codeact.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/codeact.py#L406-L420), [btw.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/btw.py#L431-L439) | high | mitigate | Replaced `SandboxedPythonInterpreter` across all 3 CLI `python_repl` peer sites with `MontyPythonInterpreter` (`pydantic-monty` worker subprocesses), failing closed without `smolagents` fallback (`strands_code_agent/` untouched per `D-24`). | closed |
| `T-20-02` | Host OS / FS Module Bypass Inside VM | [monty.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/monty.py#L84-L124), [monty.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/monty.py#L315-L330) | high | mitigate | AST pre-execution gate blocks `os`, `pathlib`, `subprocess`, `__import__`, and `import_module` paired with `os=None` inside Monty (`builtins.open`, `exec`, `eval`, `posix`, `socket`, `ctypes`, `io` denied fail-closed). | closed |
| `T-20-03` | VM Memory, CPU, Recursion & Stdout Exhaustion | [monty.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/monty.py#L19-L82), [monty.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/monty.py#L330-L337) | medium | mitigate | Enforces `ResourceLimits(256 MiB, 60s, depth=200)`, bounded `_StdoutCollector` (`4 MiB`, dynamic cap label), and resets poisoned cumulative-duration sessions on `TimeoutError` (`ea35d49`). | closed |
| `T-20-04` | Worker Crash DoS & Pool Corruption | [monty.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/monty.py#L155-L202), [monty.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/monty.py#L320-L339) | medium | mitigate | `MontyCrashedError` salvages pre-crash `print()` stdout, resets dead session cleanly, and reports reset note; `_resolve_monty_binary_path()` validates `Cc`/`Cf` chars + `isfile` + `os.X_OK`, and `_get_shared_pool()` enters replacement pools before swapping `_SHARED_POOL` (`ea35d49`, `80ab751`). | closed |
| `T-20-05` | CodeAct Callback Symlink / FIFO / Sensitive / Protected Escape | [codeact.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/codeact.py#L179-L260) | high | mitigate | `_refuse_raw_symlink_traversal()` catches `a/../outside` escapes before `normpath` collapse (`533e587`), anchors symlinked `cwd`, enforces `refuse_symlink_under_roots()`, `O_NOFOLLOW \| O_NONBLOCK`, sensitive-read (`.env*`/`.ssh/*`/`.aws/*`) & protected-path blocks, and `atomic_write_text()`. | closed |
| `T-20-06` | Active `PolicyConfig` `[[deny]]` & Symlinked PolicyTamper Bypass | [codeact.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/codeact.py#L169-L176), [codeact.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/codeact.py#L256-L260) | high | mitigate | `_load_codeact_policy()` fails closed on symlinked `.agent/policy.toml` / symlinked `.agent/` dir, and enforces active `[[deny]]` rules non-interactively across `codeact_read`, `codeact_write`, `codeact_edit`, and `codeact_shell`. | closed |
| `T-20-07` | Cross-Agent / Pending-Child Worker State Leakage | [loop/core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/core.py#L985-L1001), [loop/core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/core.py#L2624-L2634), [subagent.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/subagent.py#L316-L343), [monty.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/monty.py#L381-L401) | medium | mitigate | `_close_loop_session()`, `CodeactStint.close()`, `_teardown_btw_agent()`, `_wrap_subagent_cleanup()`, `close_agent_repls()` (incl. unresumed pending `subagent` children via `_close_children()` in `12d9a28`), and `atexit` release sessions deterministically. | closed |
| `T-20-08` | Poisoned / Non-Executable / Root `MONTY_BIN` Box Grant | [box.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/box.py#L133-L143), [box.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/box.py#L469-L505), [box.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/box.py#L867-L872) | medium | mitigate | `_reject_control_chars()` (`Cc`/`Cf`), `os.path.realpath`, `os.access(real, os.X_OK)`, and `_valid_nonroot_dir(real.parent)` gate `[agent.filesystem].exec` / `read` and custom `[agent.env].MONTY_BIN` forwarding (`80ab751`). | closed |
| `T-20-09` | Strands Box `[tool.python]` Ambiguity & Unverified Boxed VM | [box.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/box.py#L880-L950), [QUICKSTART.md](file:///home/csaba/repos/AWS/strands-code/docs/QUICKSTART.md#L352-L386), [test_box.py](file:///home/csaba/repos/AWS/strands-code/tests/sandbox/test_box.py#L1330-L1380) | low | mitigate | Embedded `[tool.python]` / `python:execute` stays omitted and documented; live `strands-box 0.3.1` (`CLONE_NEWUSER`) test proves `MontyPythonInterpreter` & `CodeactStint` execute cleanly under `STRANDS_BOX=1`. | closed |
| `T-20-10` | Unbounded Host-Memory Exhaustion via Large `codeact_read` / `codeact_edit` Target | [codeact.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/codeact.py#L159-L160), [codeact.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/codeact.py#L260-L299) | **high** | mitigate | **Discovered & remediated in this audit:** live PoC read a 16 MiB file verbatim into host memory. Added `CODEACT_MAX_FILE_BYTES = 4 * 1024 * 1024` check on `os.fstat(fd).st_size` and incremental read total in `_read_regular_file_utf8()`, failing closed cleanly. | closed |
| `T-20-11` | `codeact_shell` `[[deny]]` Bypass via `env -u`/`-C`/`-S` Flags & `nice`/`timeout`/`nohup`/`stdbuf`/`command`/`exec` Wrappers | [codeact.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/codeact.py#L345-L450) | **high** | mitigate | **Discovered & remediated in this audit:** live PoC bypassed `[[deny]] tool = "shell" command = "rm"` and `"git push"` using `env -u`, `env -C`, `env -S`, `nice`, and `timeout`. Added `_unwrap_env_wrapper()`, `_unwrap_exec_wrapper()`, and bounded recursive `_codeact_shell_deny_candidates()` unwrapping chained wrappers before `decide()`. | closed |
| `T-20-12` | Unbounded `codeact_shell` Subprocess Output OOM / Context Flooding | [codeact.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/codeact.py#L162-L164), [codeact.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/codeact.py#L448-L515) | **medium** | mitigate | **Discovered & remediated in this audit:** `codeact_shell()` returned unbounded `proc.stdout` / `proc.stderr` back across the VM boundary. Added `_cap_shell_output()` capping each stream at `CODEACT_MAX_SHELL_OUTPUT_BYTES` (`4 MiB`) with `\n[output truncated at 4 MiB]` indicator. | closed |

*Status: `open` · `closed`*
*Severity: `critical` > `high` > `medium` > `low` — only `open` threats at or above `workflow.security_block_on` (`high`) count toward `threats_open`*
*Disposition: `mitigate` (implementation verified) · `accept` (documented risk) · `transfer` (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| `R-20-01` | `T-20-01` | `strands_code_agent/` remains byte-identical to upstream `ee42ea2` (`D-24`); upstream `CodeAgent` retains `SandboxedPythonInterpreter` until an intentional upstream sync, while all 3 CLI `python_repl` entrypoints run `MontyPythonInterpreter`. | secure-phase L1 audit | 2026-11-27 |
| `R-20-02` | `T-20-05`, `T-20-11` | `codeact_shell()` preserves CLI CodeAct's intentional non-interactive subprocess parity (`shlex.join` under `STRANDS_BOX=1` so host Dogwood mediates external binaries); shell script payloads interpreted by `sh -c`/`bash -c` remain further confined inside `strands-box` (`CLONE_NEWUSER`). | secure-phase L1 audit | 2026-11-27 |
| `R-20-03` | `T-20-09` | Strands Box's embedded `[tool.python]` stays omitted in favor of `strands_code_cli/sandbox/monty.py` inside `[agent.filesystem].exec` so stateful REPL turns, CodeAct callbacks, and crash salvage remain unified across boxed and unboxed launches. | secure-phase L1 audit | 2026-11-27 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-27 | 12 | 12 | 0 | `gsd-secure-phase` ASVS L1 audit (discovered & closed `T-20-10` HIGH `CODEACT_MAX_FILE_BYTES` `4 MiB` read/edit limit, `T-20-11` HIGH `env -u`/`-C`/`-S` & `nice`/`timeout`/`nohup`/`stdbuf`/`command`/`exec` shell `[[deny]]` wrapper unwrapping, and `T-20-12` MEDIUM `CODEACT_MAX_SHELL_OUTPUT_BYTES` `4 MiB` shell output cap; verified on final tree: live security PoCs all blocked/capped, `ruff format --check` `137 files already formatted`, `ruff check` `All checks passed!`, `xenon --max-absolute C strands_code_cli tests scripts` exit `0`, `lint-imports` `Contracts: 1 kept, 0 broken` [`47` files, `147` deps], `uv lock --check` `Resolved 142 packages in 2ms`, `git diff ee42ea2 -- strands_code_agent/` empty, restricted-module & zero-`SandboxedPythonInterpreter` `.py` audits clean, `pytest tests/rig/ -rs -q` `44 passed in 1.06s`, `TERM=xterm-256color GITHUB_ACTIONS=true pytest tests/ -k "not test_stub_server_systemone_decision_routes" -rs -q` `2013 passed, 16 deselected` [`0` skipped], loopback stub `1 passed, 202 deselected`, live host `strands-box 0.3.1` integration `1 passed, 30 deselected in 10.63s`, and `20-UAT.md` `6/6` passed) |

---

## Sign-Off

- [x] All threats have a disposition (`mitigate` / `accept` / `transfer`)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-27
