# CLI Structure Report

Measurement-first structural review of the fork-owned CLI tree (STRUCT-01).
These numbers describe the post-cleanup, ruff-formatted tree at the Phase 12
hygiene baseline; the package breakup cites them as its forcing function, and
the persistent gates keep them green once the breakup lands.

## Method

Scope is fork-owned paths only — `strands_code_cli/`, `tests/`, `scripts/` —
per D-24. Inherited upstream code (`strands_code_agent/`) is neither measured,
gated, formatted, nor fixed. Measured 2026-10-16 on Python 3.14.8 with
radon 6.0.1, xenon 0.9.3, ruff 0.17.1, import-linter 2.15, suite 1532 passed.

Exact invocations (thresholds per D-03, absolute-only per the Q5 resolution):

```bash
uv run radon cc strands_code_cli tests scripts -s -a
uv run xenon --max-absolute C strands_code_cli tests scripts
uv run lint-imports
uv run ruff check strands_code_cli tests scripts
uv run ruff format --check strands_code_cli tests scripts
```

Grade scale: A 0–5, B 6–10, C 11–20, D 21–30, E 31–40, F 41+.
D-03 fails blocks worse than C (complexity above 20) and warns on C;
xenon has no warn switch, so C-rank blocks are recorded as warnings here.

## Numbers

2706 blocks analyzed, average complexity A (3.87). Rank histogram:
A 2244, B 358, C 87, D 10, E 2, F 5.

Gate verdicts at baseline: xenon exit 1 (17 blocks worse than C, expected —
CF-03 stages enforcement after the breakup); ruff check and format-check
exit 0 (77 files); lint-imports exit 0 (1 contract kept).

### Red blocks (worse than C — must reshape in the breakup)

| File | Block | Rank (cc) |
|---|---|---|
| strands_code_cli/loop.py:2007 | run_loop | F (75) |
| strands_code_cli/routing.py:683 | validate_strategy | F (62) |
| strands_code_cli/router.py:348 | _model_message | F (58) |
| strands_code_cli/loop.py:471 | _pump_parallel | F (46) |
| strands_code_cli/memory_file.py:574 | scan_repo | F (46) |
| strands_code_cli/router.py:113 | dispatch | E (35) |
| strands_code_cli/routing.py:1881 | decide | E (35) |
| strands_code_cli/router.py:1132 | _route_setup_message | D (28) |
| strands_code_cli/loop.py:1444 | _route_pre_turn | D (25) |
| strands_code_cli/model_switch.py:277 | convert_history | D (24) |
| strands_code_cli/router.py:621 | _setup_catalog_entries | D (23) |
| strands_code_cli/router.py:1519 | _memory_message | D (23) |
| scripts/route-probe.py:282 | run_probe | D (23) |
| strands_code_cli/routing.py:276 | _parse_engine | D (22) |
| tests/test_routing_strategy.py:481 | test_full_run_writes_repo_scope_in_pick_order | D (22) |
| strands_code_cli/policy.py:497 | decide | D (21) |
| strands_code_cli/router.py:1652 | _skills_message | D (21) |

### The three giants (red plus C warnings)

loop.py (2523 lines, 48 blocks): F run_loop (75), F _pump_parallel (46),
D _route_pre_turn (25); C apply_model_action (19), _route_side_spawn (17),
_invoke_agent (15), review_memory_queue (13), _drain_idle_btw (12),
RichHistory.load (12), consume_revise_turn (11), _drain_revise_rounds (11).

router.py (2130 lines, 63 blocks): F _model_message (58), E dispatch (35),
D _route_setup_message (28), D _setup_catalog_entries (23),
D _memory_message (23), D _skills_message (21); C _setup_decision_entries (20),
_setup_pick_candidates_typed (16), _setup_pick_decision (15),
_setup_pick_order_typed (15), _diff_message (13), _route_validate_message (12),
_setup_ask (11), _setup_pick_order_tty (11).

routing.py (2318 lines, 83 blocks): F validate_strategy (62), E decide (35),
D _parse_engine (22); C save_strategy (20), _candidate_skip_reason (18),
local_engine_ready (16), _decide_effort (14), _validate_choice_shape (12).

### Per-module CLI table (lines | blocks | worst | worse-than-C | C)

| Module | Lines | Blocks | Worst | >C | C |
|---|---|---|---|---|---|
| loop.py | 2523 | 48 | F 75 | 3 | 8 |
| routing.py | 2318 | 83 | F 62 | 3 | 5 |
| router.py | 2130 | 63 | F 58 | 6 | 8 |
| memory_file.py | 820 | 33 | F 46 | 1 | 3 |
| policy_gate.py | 809 | 50 | C 17 | 0 | 4 |
| model_switch.py | 672 | 25 | D 24 | 1 | 2 |
| cost_context.py | 648 | 26 | C 20 | 0 | 4 |
| live_pricing.py | 583 | 31 | C 12 | 0 | 2 |
| policy.py | 553 | 23 | D 21 | 1 | 5 |
| steering.py | 505 | 29 | B 6 | 0 | 0 |
| diff_gate.py | 490 | 26 | C 13 | 0 | 2 |
| btw.py | 453 | 28 | C 17 | 0 | 1 |
| memory_modes.py | 422 | 31 | C 12 | 0 | 1 |
| codeact.py | 403 | 24 | C 11 | 0 | 1 |
| main.py | 281 | 8 | B 7 | 0 | 0 |
| session_index.py | 223 | 15 | B 9 | 0 | 0 |
| skills.py | 216 | 11 | B 8 | 0 | 0 |
| choice.py | 200 | 3 | B 6 | 0 | 0 |
| model_capabilities.py | 157 | 6 | C 12 | 0 | 1 |
| provider_config.py | 144 | 6 | C 16 | 0 | 2 |
| reported_cost.py | 129 | 5 | A 4 | 0 | 0 |
| scope.py | 113 | 8 | B 7 | 0 | 0 |
| diff_config.py | 94 | 4 | B 9 | 0 | 0 |
| mode.py | 92 | 8 | A 3 | 0 | 0 |
| completer.py | 71 | 4 | B 9 | 0 | 0 |
| first_run.py | 50 | 2 | A 4 | 0 | 0 |
| output.py | 42 | 2 | A 1 | 0 | 0 |

### Tests and scripts

Only two files carry red: tests/test_routing_strategy.py (D 22, one test) and
scripts/route-probe.py (D 23, run_probe). C concentrations: test_btw.py (11),
test_routing.py (5), test_cost_context.py / test_loop_routing.py /
test_memory_curate.py / route-probe.py / driver.py (3 each). All other test
and script modules are A/B only. scripts/uattest/driver.py (1135 lines,
37 blocks) peaks at C 19 (scenario_r1) — size without complexity.

## Contracts

One import-linter contract, KEPT (28 files, 74 dependencies analyzed):

- Name: "Feature modules never import the entry module (composition root)"
- Type: forbidden — source `strands_code_cli`, forbidden `strands_code_cli.main`,
  ignoring the package-root re-export (`__init__.py:3`, the only internal
  importer of `main`). main.py is the composition root; feature modules
  must not depend on it.

A D-15 "never reintroduce knowledge" contract is inexpressible in
import-linter (subpackages of external packages are rejected, and the module
no longer exists), so CLEANUP-01 stays guarded by the path-absence plus
anchored-grep CI step instead. The known backwards import
(`search_tool.py:18`, agent → CLI) is pending the 12-02 boundary decision;
layer contracts for the new feature packages land with the breakup.

## Breakup rationale

The numbers force the package boundaries plans 12-02 and 12-03 implement:

- `loop/` package: loop.py is the largest module (2523 lines) and holds two
  of the five F blocks — run_loop F (75) and _pump_parallel F (46) — plus
  D _route_pre_turn (25) and 8 C warnings. The turn loop, pump, and routing
  hooks separate into own modules; the F blocks split, not move whole.
- `routing/` package: routing.py (2318 lines) holds F validate_strategy (62),
  E decide (35), D _parse_engine (22). Strategy load/validate, engine chain,
  and decide paths separate; validate_strategy splits.
- `dispatch/` package: router.py (2130 lines) holds the most red blocks (6:
  F 58, E 35, four D 21–28) plus 8 C warnings, all slash/setup message
  builders. Per-area message modules plus a thin dispatch entry.
- Memory feature: memory_file.py scan_repo F (46) is the only red block
  outside the giants' orbit — it reshapes within its feature package, as do
  policy.py decide D (21) and model_switch.py convert_history D (24).
- Tests mirror the new layout (D-07); the single test D (22) splits with its
  module. The rig split is mechanical — driver.py peaks at C 19, so no
  complexity forcing function, just lib extraction plus per-area files.
- scripts/route-probe.py run_probe D (23) reshapes alongside the routing move.
- Enforcement stays staged (CF-03): xenon is RED at baseline by measurement,
  so CI/pre-commit flip to blocking only after the breakup lands (12-05).
