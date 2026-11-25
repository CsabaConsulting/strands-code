---
phase: 19-strands-box-linux-sandbox-floor-dogwood-policy
plan: "01"
completed: 2026-11-25
requirements:
  - SANDBOX-01
files_modified:
  - strands_code_cli/sandbox/__init__.py
  - strands_code_cli/sandbox/box.py
  - tests/conftest.py
  - tests/sandbox/__init__.py
  - tests/sandbox/test_box.py
---

# Plan 19-01 Summary: Strands Box Generator, Egress Profiles, Dogwood Policy & Wave 0 Tests

## Implemented
- **[box.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/box.py)** (new package `strands_code_cli/sandbox/`):
  - Implemented `is_in_strands_box()`, `repo_config_id()`, `default_box_config_dir()`, and `default_box_data_dir()` storing per-repo `box.toml` and `policy.dw` host-only under `~/.config/strands-box/repos/<slug>-<hash8>/` (`0o700` dirs, `0o600` files, symlink-refused atomic writes) and `box_dir` under `~/.local/share/strands-box/repos/<slug>-<hash8>/`.
  - Implemented `resolve_runtime_paths()` resolving `.venv`, `Path(sys.executable).resolve()`, `uv` Python runtime prefixes (`~/.local/share/uv/python`), system libs, dev tools (`git`, `pytest`, `rg`, `ruff`, `uv`, `python`), and writable paths strictly excluding `~/.config/strands-box`.
  - Implemented `detect_active_providers()` + `_egress_specs_for_providers()` + `render_box_toml()` (`tomllib`-validated cleanly) across all 7 core providers (`bedrock` SigV4 without `sts.amazonaws.com`, `google` `x-goog-api-key`, `anthropic` `x-api-key`, `openai`, `meta`, path-scoped `openrouter` `/api/v1/chat/*` + `/api/alpha/decisions`, `typesafe`) and opt-in profiles (`--allow-decisions-api`, `--allow-github-skills` with `api.github.com` token scoping separate from `codeload`/`objects`).
  - Implemented `render_policy_dw()` with default-deny egress, `.env`/`.ssh`/`.aws` read forbids, non-push dev `shell:spawn` permits, canonical MFOTL temporal `git push` rule (`formerly within 900s` `pytest`), and scoped `D-05` revisit header.
  - Implemented `init_box_config()` (`--out` self-tamper warning on writable targets + control-char/injection guards), `discover_box_binaries()` (3-binary co-location), `run_box_doctor()` (`x86_64` `EXPERIMENTAL_X86_SUPPORT=TRUE` + Ubuntu AppArmor `userns` sysctl/profile checks), `format_doctor_report()`, and `launch_box_run()`.
- **[conftest.py](file:///home/csaba/repos/AWS/strands-code/tests/conftest.py):** Added `"STRANDS_BOX_BIN"` and `"EXPERIMENTAL_X86_SUPPORT"` to `_PROVIDER_ENV_VARS`.
- **[test_box.py](file:///home/csaba/repos/AWS/strands-code/tests/sandbox/test_box.py):** Wave 0 hermetic & adversarial test suite (`T-19-01`..`T-19-08`).

## Verification & Complexity
- `radon cc` max in `sandbox/box.py`: `C (15)` (`resolve_runtime_paths`, `init_box_config`).
- `.venv/bin/ruff format` & `.venv/bin/ruff check strands_code_cli/sandbox tests/sandbox tests/conftest.py`: passed.
- `.venv/bin/xenon --max-absolute C strands_code_cli/sandbox tests/sandbox`: passed.
- `.venv/bin/lint-imports`: `Contracts: 1 kept, 0 broken` (`43 files, 93 dependencies`).
- `.venv/bin/pytest tests/sandbox/ tests/cost/test_cost_context.py -q`: `95 passed`.
- `git diff ee42ea2 -- strands_code_agent/`: empty (`D-24`).
