# Phase 19: Strands Box Linux Sandbox Floor & Dogwood Policy - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `19-CONTEXT.md` — this log preserves the questions asked and options selected.

**Date:** 2026-11-25
**Phase:** `19-strands-box-linux-sandbox-floor-dogwood-policy`
**Areas discussed:** CLI surface (`D-01`), Config storage boundary (`D-02`), Provider egress auto-detection (`D-04`), Dogwood `policy.dw` rules & `[tool.*]` posture (`D-05`)

*(Pre-decided anchors from Roadmap, Requirement `SANDBOX-01`, `19-CONTEXT.md` codebase constraints, and `v2.0` alignment not re-asked: external 3-binary Linux Strands Box model with zero Rust/platform fork, `uv`/`.venv` realpath resolution and explicit `TERM`/`HOME`/`PATH`/`STRANDS_BOX=1`, all 7 core provider egress profiles including Bedrock SigV4 with no `sts.amazonaws.com` hole and path-scoped OpenRouter, formal scoped `D-05` revisit keeping Python `interventions` deterministic TOML+Python, `STRANDS_BOX=1` `codeact_shell` `sh -c` alignment, Linux `x86_64` `EXPERIMENTAL_X86_SUPPORT=TRUE` + Ubuntu 24.04 AppArmor documentation, zero `os.environ` or banned enforcement words inside `dispatch/core.py`/`entry/main.py`, `xenon C <= 20`, `lint-imports`, and `strands_code_agent/` immutability under `D-24`.)*

---

## Round 1: CLI Surface, Storage Boundary, Egress Selection & Dogwood Policy

### Q1: CLI Surface (`D-01`)

Which CLI surface should expose Strands Box config generation, Linux diagnostics, and launching?

| Option | Description | Selected |
|--------|-------------|----------|
| *(Recommended)* Typer subcommand group `strands-code box init\|doctor\|run` + `/policy` indicator | Subcommand group while bare `strands-code` stays REPL; read-only `[sandbox: Strands Box]` note in `/policy` when `STRANDS_BOX=1`. | ✓ |
| Generator & diagnostics only (`strands-code box init\|doctor`) | Omit `box run` wrapper; user runs `box run --config ...` manually. | |
| Standalone console script `strands-code-box` | Keep `strands-code` Typer app single-command with zero subcommands. | |

**User's choice:** Typer subcommand group `strands-code box init|doctor|run` (bare `strands-code` stays REPL) + read-only `[sandbox: Strands Box]` note in `/policy` when `STRANDS_BOX=1`.

---

### Q2: Config Storage Boundary (`D-02`)

Where should generated `box.toml` and `policy.dw` files live by default to prevent in-session self-tampering?

| Option | Description | Selected |
|--------|-------------|----------|
| *(Recommended)* Host-only `~/.config/strands-box/repos/<slug>-<hash8>/` | Stored with `0o700`/`0o600`, excluded from `[agent.filesystem].write` and protected in `policy/core.py`; `--out <dir>` warns if inside writable paths. | ✓ |
| In-repo `./.agent/box/{box.toml,policy.dw}` | Easier to commit, protected only by `policy/core.py` `Prompt` downgrade (weaker against direct `python_repl`/kernel writes). | |
| Inside `~/.config/strands-code/box/<slug>-<hash8>/` | Shares `strands-code` config tree, which is RW inside the box for `/model` and `/policy` saves. | |

**User's choice:** Host-only `~/.config/strands-box/repos/<slug>-<hash8>/` (`0o700`/`0o600`, outside `[agent.filesystem].write` + protected in `policy/core.py`), with optional `--out <dir>` that warns if inside writable workspace.

---

### Q3: Provider Egress Profile Selection (`D-04`)

How should `box init` select which of the 7 provider egress profiles (and Phase 17/18 optional endpoints) to enable?

| Option | Description | Selected |
|--------|-------------|----------|
| *(Recommended)* Auto-detect minimal least-privilege profiles | Inspect active `ProviderConfig` + `routing.yaml` + set host env keys (overridable via `--provider`), keeping `decisions_api` (`decisionapi.net`) and GitHub skills (`--allow-github-skills`) opt-in flags. | ✓ |
| Enable all 7 core provider egress profiles by default | Smoother mid-session `/model` switching with a broader outbound allowlist. | |
| Require explicit `--provider` flags with zero auto-detection | Strict manual flag selection on every `box init`. | |

**User's choice:** Auto-detect minimal least-privilege profiles from active `ProviderConfig` + `routing.yaml` + set env keys (overridable via `--provider`), keeping `decisions_api` (`decisionapi.net`) and GitHub skills (`--allow-github-skills`) opt-in flags.

---

### Q4: Dogwood `policy.dw` Rules & `[tool.*]` Posture (`D-05`)

What Dogwood `policy.dw` rule set and `[tool.*]` posture should the generated policy ship with by default?

| Option | Description | Selected |
|--------|-------------|----------|
| *(Recommended)* Default-deny egress + `.env`/secret read forbid + canonical MFOTL temporal rule + standard dev `[tool.*]` | Canonical MFOTL rule (`git push` requires `formerly within 900s` `pytest`) plus `git`, `pytest`, `rg`, `ruff`, `uv`, `python` in `[tool.*]`. | ✓ |
| Same rules + temporal non-LLM HTTP exfil guard | Forbid all non-LLM HTTP egress after any sensitive-file read attempt. | |
| Minimal read-heavy floor | Forbid `git push` unconditionally, keep temporal rule commented, allow only `git`/`pytest`/`rg`. | |

**User's choice:** Default-deny egress + `.env`/secret-file read forbid + canonical MFOTL temporal rule (`git push` requires `formerly within 900s` `pytest`) + standard dev `[tool.*]` (`git`, `pytest`, `rg`, `ruff`, `uv`, `python`).

---

*Discussion closed cleanly in 1 round (4 questions); all selected options match `19-CONTEXT.md` `D-01`–`D-07`.*
