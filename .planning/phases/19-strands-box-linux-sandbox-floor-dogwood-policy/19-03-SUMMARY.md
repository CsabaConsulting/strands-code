---
phase: 19-strands-box-linux-sandbox-floor-dogwood-policy
plan: "03"
completed: 2026-11-25
requirements:
  - SANDBOX-01
files_modified:
  - tests/sandbox/test_box.py
  - docs/QUICKSTART.md
---

# Plan 19-03 Summary: Opportunistic Host Probe, `QUICKSTART.md` Guide & Full CI Gates

## Implemented
- **[test_box.py](file:///home/csaba/repos/AWS/strands-code/tests/sandbox/test_box.py):** Appended `@pytest.mark.integration` test `test_host_strands_box_or_dogwood_validates_generated_policy(tmp_path)`, generating `box.toml` and `policy.dw` into isolated `tmp_path` directories (no host `.env` or real config reads) and validating against host `dogwood validate` / co-located `box run` when installed, or skipping cleanly via `pytest.skip(...)` when absent (`D-07`).
- **[QUICKSTART.md](file:///home/csaba/repos/AWS/strands-code/docs/QUICKSTART.md):** Added `## Strands Box Linux sandbox floor` covering the 3 co-located Linux binaries (`box`, `strands-box-contain-trampoline`, `strands-box-sock-alias`), mandatory `EXPERIMENTAL_X86_SUPPORT=TRUE` on Linux `x86_64`, Ubuntu 24.04+ `/etc/apparmor.d/strands-box` `userns` profile, `strands-code box init|doctor|run` + `/policy` indicator + `codeact_shell` `sh -c` alignment, host-only `~/.config/strands-box/repos/<slug>-<hash8>/` storage, the 7-provider egress matrix + `--allow-decisions-api` / `--allow-github-skills`, canonical MFOTL rule `push_requires_recent_tests` (`formerly within 900s` `pytest`), and the formal scoped `v2.0` revisit of `D-05`.

## Verification
- `uv run pytest tests/sandbox/ tests/rig/ -q`: `63 passed, 1 deselected` (`19` unit/CLI sandbox tests + `44` rig contract tests).
- `uv run pytest tests/sandbox/ -m integration -v`: `1 skipped, 19 deselected` (host `dogwood` / `box` absent on dev machine).
- `uv run ruff format --check strands_code_cli tests scripts`: `128 files already formatted`.
- `uv run ruff check strands_code_cli tests scripts`: `All checks passed!`.
- `uv run xenon --max-absolute C strands_code_cli tests scripts`: passed.
- `uv run lint-imports`: `Contracts: 1 kept, 0 broken` (`43 files, 97 dependencies`).
- `uv lock --check`: `Resolved 156 packages in 3ms` (exit 0).
- `uv run pytest tests/ -k "not test_stub_server_systemone_decision_routes" -q`: `1820 passed, 16 deselected`.
- Standalone loopback stub `uv run pytest tests/routing/test_routing.py -k test_stub_server_systemone_decision_routes -q` (`BypassSandbox: true`): `1 passed, 195 deselected` (combined non-integration total: `1821 passed`).
- `git diff ee42ea2 -- strands_code_agent/`: empty (`D-24`).
