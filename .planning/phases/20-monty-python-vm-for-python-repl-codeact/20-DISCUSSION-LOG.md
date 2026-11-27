# Phase 20: Monty Python VM for `python_repl` & CodeAct - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `20-CONTEXT.md` — this log preserves the questions asked and options selected.

**Date:** 2026-11-27
**Phase:** `20-monty-python-vm-for-python-repl-codeact`
**Peer Parity Matrix Reviewed:**
- **Execution Peers:** Main tool-turn `python_repl` (`entry/main.py:237`), `CodeactStint` (`policy/codeact.py:306`), `/btw` + `subagent` delegates (`loop/btw.py:438`, `entry/subagent.py:73`), untouched upstream `CodeAgent` (`strands_code_agent/code_agent.py:141` per `D-24`), and Strands Box `box.toml` (`sandbox/box.py:587-609`).

---

## Gray Areas Selected

| Selection | Description | Selected |
|---|---|---|
| *(Recommended)* Discuss all 5 gray areas one decision at a time | Packaging & fallback, stdlib/limits/recovery, CodeAct host callbacks, pool lifecycle & teardown, Strands Box alignment | ✓ |

---

## Area 1: Packaging, Fallback & Peer Scope (`D-01`, `D-02`, `D-03`)

### Q1: Where should `pydantic-monty` live in `pyproject.toml`? (`D-01`)

| Option | Description | Selected |
|---|---|---|
| *(Recommended)* Core `[project.dependencies]` | Matches `smolagents`/`httpx`; every install gets crash-isolated Monty out of the box | ✓ |
| Optional `[project.optional-dependencies]` `monty` extra | Smaller base install; requires `.[monty]` extra | |

### Q2: If `pydantic-monty` is missing or its worker binary cannot launch, how should `python_repl` behave? (`D-02`)

| Option | Description | Selected |
|---|---|---|
| *(Recommended)* Fail closed | Return an explicit `STDERR` error rather than silently downgrading to in-process `smolagents` | ✓ |
| Fail soft with visible warning | Fall back to in-process `SandboxedPythonInterpreter` (⚠️ Weakens crash/memory isolation if runtime is missing) | |

### Q3: Which CLI `python_repl` sites should migrate to `MontyPythonInterpreter`? (`D-03`)

| Option | Description | Selected |
|---|---|---|
| *(Recommended)* All 3 CLI peer sites together | Main REPL, CodeAct stint, and `/btw` + `subagent` delegates (`strands_code_agent/` stays untouched per `D-24`) | ✓ |
| Main REPL + CodeAct only | Leave `/btw` and `subagent` delegates on `smolagents` (⚠️ Breaks peer parity across CLI REPL sites) | |

---

## Area 2: Stdlib Surface, Resource Caps & Crash Recovery (`D-04`, `D-05`, `D-06`)

### Q4: Which stdlib imports should `MontyPythonInterpreter` allow inside the VM? (`D-04`)

| Option | Description | Selected |
|---|---|---|
| *(Recommended)* Pure-computation Monty stdlib with `os`/`pathlib`/`subprocess` explicitly rejected | Allows `math`, `json`, `re`, `collections`, `itertools`, `datetime`, `base64`, `dataclasses`, `random`, etc. across all 3 CLI sites with `os=None`, while rejecting OS/subprocess imports fail-closed | ✓ |
| Keep legacy `smolagents` allowlists | `set()` for main/delegate REPL, `{"math"}` for `CodeactStint` | |
| Allow all Monty built-ins with `os=None` only | `import os` succeeds as inert stub, only OS calls fail | |

### Q5: What `ResourceLimits` and stdout capture bounds should `MontyPythonInterpreter` enforce by default? (`D-05`)

| Option | Description | Selected |
|---|---|---|
| *(Recommended)* `128 MiB` `max_memory`, `60s` timeout, recursion depth `200`, `1 MiB` stdout cap | Matches existing 60s timeout with 128 MiB / 1 MiB bounds | |
| `256 MiB` `max_memory`, `60s` timeout, recursion depth `200`, `4 MiB` stdout cap | Matches existing 60s timeout with generous 256 MiB heap / 4 MiB output room | ✓ |
| `64 MiB` `max_memory`, `30s` timeout, recursion depth `100`, `256 KiB` stdout cap | ⚠️ Breaks parity with existing 60s CodeAct timeout | |

### Q6: How should `MontyPythonInterpreter` recover from `MontyCrashedError` (OOM, timeout, or worker abort)? (`D-06`)

| Option | Description | Selected |
|---|---|---|
| *(Recommended)* Salvage partial pre-crash `print()` stdout, auto-replace dead session on a fresh worker, and report crash + explicit state-reset note in `STDERR` | Preserves partial diagnostics and avoids silent state loss | ✓ |
| Auto-replace dead session and return crash message in `STDERR` without partial stdout salvage or state-reset notice | Simpler error string without salvage or reset notice | |

---

## Area 3: CodeAct Host Callback Hardening (`D-07`, `D-08`)

### Q7: Should CodeAct `read`/`write`/`edit` host callbacks enforce Phase 19.1 symlink, sensitive-read, and protected-path guards? (`D-07`)

| Option | Description | Selected |
|---|---|---|
| *(Recommended)* Backport Phase 19.1 floor into `codeact_read`/`write`/`edit` | Refuse symlinks and block sensitive reads (`.env*`, `~/.ssh`, `~/.aws`) & protected writes (`.agent/**`, `.git/**`, `STRANDS.md`, `~/.config/strands-code\|box`) | ✓ |
| Keep Phase 11 `confine()`-only behavior | Rely solely on outer `python_repl` HITL approval (⚠️ Breaks parity with Phase 19.1 protected/sensitive path & symlink floor) | |

### Q8: Should CodeAct `read`/`write`/`edit`/`shell` host callbacks also enforce active `PolicyConfig` `[[deny]]` rules? (`D-08`)

| Option | Description | Selected |
|---|---|---|
| *(Recommended)* Enforce active `PolicyConfig` `[[deny]]` rules inside `codeact_read`/`write`/`edit`/`shell` callbacks | Return refusal strings, never prompting mid-VM | ✓ |
| Skip `PolicyConfig` `[[deny]]` checks inside CodeAct callbacks | ⚠️ Allows dynamically constructed paths/commands in approved CodeAct blocks to bypass file/shell `[[deny]]` rules | |

---

## Area 4: Worker Pool Ownership & Teardown (`D-09`)

### Q9: How should Monty worker subprocess pools be owned and torn down? (`D-09`)

| Option | Description | Selected |
|---|---|---|
| *(Recommended)* Process-wide lazy shared `Monty()` pool with per-interpreter isolated sessions | Closed deterministically on `clear_state()`, `CodeactStint.close()`, `_close_loop_session()`, delegate exit, and `atexit` | ✓ |
| Dedicated `Monty()` pool per interpreter instance | Separate worker subprocess per main REPL, `CodeactStint`, `/btw`, and `subagent` | |

---

## Area 5: Strands Box Runtime Grants & Embedded `[tool.python]` Scope (`D-10`, `D-11`)

### Q10: How should `sandbox/box.py` handle `pydantic-monty-runtime` compatibility inside Strands Box? (`D-10`)

| Option | Description | Selected |
|---|---|---|
| *(Recommended)* Discover and add `pydantic-monty-runtime` binary realpath to `[agent.filesystem].exec` in `box.py`, plus verify Monty execution live inside `strands-box 0.3.1` (`-m integration`) | Full runtime grant + live `CLONE_NEWUSER` verification | ✓ |
| Add `pydantic-monty-runtime` binary realpath to `box.py` only | Offline unit tests only, no live Box+Monty check | |

### Q11: Should `box.py` emit Strands Box's own embedded `[tool.python]` / Dogwood `python:execute` block? (`D-11`)

| Option | Description | Selected |
|---|---|---|
| *(Recommended)* Keep `[tool.python]` omitted from `box.toml` and document Strands Box embedded Monty evaluation in `docs/QUICKSTART.md` | `strands-code` runs `pydantic-monty` directly inside Box (callbacks already under Box FS + Dogwood `shell:spawn`) | ✓ |
| Emit an opt-in `--allow-box-python` flag generating `[tool.python]` and Dogwood `python:execute` rules | Separate Box-managed tool bridge | |
