---
plan: 12-03
phase: 12-structural-review-hygiene
status: complete
started: 2026-10-16T07:36:25Z
completed: 2026-10-16T08:14:25Z
duration: 38m
tasks_completed: 3
tasks_total: 3
commits: 45
files_changed: 107
tests_status: green
---

# 12-03 Summary: Flag-day repackage — remaining moves, test mirror, entry re-sync

All 24 remaining flat CLI modules now live in 9 new feature packages (plus
`loop/` from 12-02), all 44 test files mirror the package tree, the console
entry is re-synced, and every tree-wide gate is green: suite 1532 passed,
xenon exit 0, ruff check + format clean, import-linter KEPT, agent-package
bound holds, no migration note.

## Tasks

| # | Name | Commit(s) | Files | Result |
|---|------|-----------|-------|--------|
| 1 | Remaining moves + import rewrite + entry re-sync | `0615f41` `31ed3bf` `6c3d62c` `e0b5873` `39a4671` `aae1d52` `44fdafa` `dde672d` `ec41eb2` `44ac697` (10) | 65 in rewrite | done |
| 2 | Test mirror + path re-homing | `9c3be96` `5158c8c` `9cf806a` `597708d` `de85d0e` `8b87406` `2d854f4` `110ee14` `4ea3899` `eb61f53` `d1f7d26` `bfd5d16` `31f5878` `f784853` `f5c9a08` `798810d` (16) | 44 moved + 14 | done |
| 3 | Tree-wide gate-green decomposition | `4e1269c` `8c38e65` `7408198` `1c0e981` `82d067d` `d5f8c72` `6269803` `86b7535` `8fdacee` `767b984` `581aab9` `622df27` `d75f6ea` `60ebcc9` `dad8688` `8dd99ed` `20fd5df` `0f4b124` `499876e` (19) | 7 | done |

## Package map (agent discretion, per CONTEXT)

| Package | Members (new name) |
|---|---|
| `routing/` | `core` ← routing.py |
| `dispatch/` | `core` ← router.py |
| `ui/` | choice, completer, output |
| `entry/` | main, first_run, provider_config |
| `memory/` | memory_file, memory_modes, skills |
| `policy/` | `core` ← policy.py, policy_gate, diff_gate, diff_config, mode, codeact, scope |
| `cost/` | cost_context, live_pricing, reported_cost |
| `model/` | model_switch, model_capabilities |
| `session/` | session_index |

Convention: a module that would stutter against its package name becomes
`core.py` (12-02 `loop/core.py` precedent); all other modules keep their
names. Package roots carry a docstring plus empty `__all__` — no re-export
shims (D-09). Ambiguous placements: `skills` → `memory/` (SKILL-01/02
`.agent/`-backed domain); `scope`/`mode`/`codeact` → `policy/` (confinement
plus behavioral policy); `provider_config` → `entry/` (launch path).

Test mirror: `tests/agent/` (9), `tests/loop/` (7), `tests/policy/` (7),
`tests/routing/` `tests/dispatch/` `tests/memory/` `tests/cost/` (3 each),
`tests/ui/` `tests/entry/` `tests/model/` `tests/session/` (2 each),
`tests/rig/` (1). Root keeps only `conftest.py` (byte-identical) plus
`__init__.py`. Ambiguous placements: `test_router_btw` → dispatch,
`test_session_resume` → entry, `test_readme_examples` → agent,
`test_tool_surface`/`test_broker` → policy.

## Complexity: before → after (radon, deterministic)

| Block | Before | After |
|---|---|---|
| routing `validate_strategy` | F (62) | C (14) |
| routing `decide` | E (35) | A (5) |
| routing `_parse_engine` | D (22) | C (17) |
| dispatch `_model_message` | F (58) | B (6) |
| dispatch `dispatch` | E (35) | C (12) |
| dispatch `_route_setup_message` | D (28) | A (5) |
| dispatch `_setup_catalog_entries` | D (23) | C (13) |
| dispatch `_memory_message` | D (23) | C (11) |
| dispatch `_skills_message` | D (21) | C (14) |
| memory `scan_repo` | F (46) | A (5) |
| model `convert_history` | D (24) | C (13) |
| policy `decide` | D (21) | C (13) |
| route-probe `run_probe` | D (23) | A (4) |
| strategy setup test | D (22) | A (1) |

Overall average complexity: **A (3.78)** across 2797 blocks. Worst block
tree-wide is the pre-existing `_setup_decision_entries` C (20). Every new
helper is C or better. Xenon `--max-absolute C` exits 0; `loop/` untouched.

## Must-have truths (verified)

- Every remaining flat CLI module lives in its feature package: `find`
  shows only `__init__.py` at `strands_code_cli/` root.
- Every `strands_code_cli.<name>` second component resolves to a directory
  (plan sweep prints nothing) and old paths break loudly
  (`ModuleNotFoundError` on `strands_code_cli.router` / `.scope`).
- `[project.scripts]` points at `strands_code_cli.entry.main:main`;
  `uv sync` regenerated the script; `strands-code --help` exits 0.
- `search_tool.py` diff is exactly the carve-out line
  (`strands_code_cli.policy.scope import confine`); agent-bound verify
  prints `AGENT-BOUND-OK`.
- No `tests/test_*.py` at root (`ROOT-CLEAR`); 12 subpackage markers
  present; `conftest.py` zero-diff.
- No `MIGRATION*` file at root; no behavior change (moves + verbatim
  extractions; suite green after every decomposition commit).
- Suite: **1532 passed, 11 deselected**; ruff check + format (100 files)
  clean; import-linter **1 kept, 0 broken**.

## Deviations (all auto-approved or plan-mandated)

- **[Rule A]** Pure-move commits are red by construction (9 CLI moves;
  6 of 12 test moves — the rest stay green). Plan-mandated purity, same
  as 12-02; each followed by a green commit.
- **[Rule B]** `entry/main.py` + `dispatch/core.py` now import
  `search_tool` at the use site (`798810d`). The mirror's collection
  order (`tests/agent/` first) exposed the pre-existing
  cli-root → feature → search_tool → cli-root cycle as an
  `ImportError`; both orders now import clean and the suite is green.
- **[Rule B]** Five test-to-test imports repointed to mirrored homes
  (`tests.session.test_kill_resume`, `tests.policy.test_mode`) —
  research claimed none exist; the suite proved otherwise.
- **[Rule B]** Eleven `__file__` repo-root anchors deepened one level
  (9 files) — mechanically mandated by the mirror.
- **[Rule B]** `9cf806a` accidentally deleted the routing tests (a batched
  `git reset` left old-path deletions staged). Repaired fix-forward
  (`597708d` restore, `de85d0e` drop dupes, `8b87406` proper move);
  `git log --follow` crosses the repair intact. No history rewritten.
- **[Rule B]** `7408198` committed with a format violation (a `;` split
  my `&&` guard chain); repaired by `1c0e981`; chain fixed after.
- **[Rule B]** `uv sync` pruned the documented `litellm` extra (1 skip);
  restored via the project's own `uv sync --extra litellm` (33 passed).
- **[Rule B]** Moved `warnings.warn` bumped `stacklevel` 2 → 3 (identical
  reported frame); `_validate_candidates` early-return and
  `_probe_attempt` elif→if+return restructures are behavior-identical.
- **[Rule B]** `code_agent.py:13` comment still names
  `strands_code_cli.mode` + `loop.py`: left untouched per D-12 (only
  the carve-out line may move; its `loop.py` half was already stale
  since 12-02).

## Decisions

- Import-linter composition-root contract tracks the moved entry
  (`strands_code_cli.entry.main`, root re-export stays the sole
  ignore). No new layer contracts: not tasked; the agent→CLI finding
  resolves per the checkpoint outcome (carve-out implemented).
- Deferred-import precedent (same-file `live_pricing`) used for the two
  cycle breaks; no public surface changed.

## Next steps

- 12-04 rig split inherits the new import paths (`cost.*`,
  `dispatch.core`, `routing.core`) — driver literals already updated.
- 12-05 README refresh must document the 10-package CLI layout and the
  mirrored tests; CI absence step stays pending there.
- Watch items: pre-existing C (20) blocks (`save_strategy`,
  `_setup_decision_entries`) if the bar ever tightens past C.

## Self-review

- **Correctness:** boundary audit — worst new block C (18) with margin;
  loud-break probes confirm D-09; warn-frame and cwd-laziness preserved
  by construction.
- **Completeness:** all three tasks, all 14 red blocks, every verify in
  the plan re-run green on the final tree.
- **On-request:** only the repackage + gates; `comparison_table.md`
  (untracked, not mine) untouched; `uv.lock` untouched.
