---
phase: 08-model-routing-with-decision-models
plan: "05"
subsystem: routing
tags: [decision-api, calibration, probe-runner, promptfoo-fallback, live-tests, pytest]

requires:
  - phase: 08-04
    provides: Split-catalog setup, decisions-cache validate, Decision-API docs, r1-r4 rig
provides:
  - Calibration probe runner (dry-run, run, compare) over the production decision stack
  - 20 labeled probes in AI-SPEC composition with fault injection
  - Probe-derived shipped knob defaults (0.62/0.04) with recorded baseline
  - Env-gated live engine tests on the Decision APIs
affects: [model-routing, cost-display, uattest]

actuals:
  tokens: 17000
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns: [compare-mode-regression-fallback, fault-injection-probes, shared-threshold-calibration]

key-files:
  created:
    - scripts/route-probe.py
    - evals/routing-probe/probes.jsonl
    - evals/routing-probe/baseline.json
  modified:
    - strands_code_cli/routing.py
    - tests/test_routing.py
    - tests/test_loop_routing.py
    - tests/test_routing_strategy.py
    - docs/ROUTING.md

key-decisions:
  - "Shipped knobs 0.62/0.04 derive from probe distributions (gap midpoint, near-tie max plus grid step)"
  - "One shared threshold serves both engines; no per-engine split (no dangerous-direction misfire)"
  - "Compare fails on model-verdict drift but warns on effort flips (ungated reads jitter by design)"
  - "Run exit measures transport health only; invalid-table holds are legitimate verdicts"
  - "Compare-mode fallback documented; no promptfoo install (CLI absent, T-08-SC)"

patterns-established:
  - "Calibration verdicts: JSONL per probe (table, top-1, margin, snapshot, gated, match)"
  - "Baseline re-gates recorded tables deterministically; fresh runs prove live stability"

requirements-completed:
  - MODEL-03

coverage:
  - id: D1
    description: "Probe runner with dry-run, run, and compare modes over production transports"
    requirement: "MODEL-03"
    verification:
      - kind: other
        ref: "python3 scripts/route-probe.py --dry-run (20 ids, exit 0)"
        status: pass
      - kind: e2e
        ref: "scripts/route-probe.py --run openrouter + --run local (20 verdicts each, exit 0)"
        status: pass
    human_judgment: false
  - id: D2
    description: "20 labeled probes in 6/6/5/3 AI-SPEC composition with fault injection"
    requirement: "MODEL-03"
    verification:
      - kind: other
        ref: "evals/routing-probe/probes.jsonl composition count + per-probe fields"
        status: pass
    human_judgment: false
  - id: D3
    description: "Probe-derived knob defaults 0.62/0.04 with recorded baseline and distributions"
    requirement: "MODEL-03"
    verification:
      - kind: other
        ref: "scripts/route-probe.py --compare (clean, exit 0) + constants equal baseline derived"
        status: pass
    human_judgment: false
  - id: D4
    description: "Env-gated live engine tests (typed tables, snapshot, cost/zero-spend, loud failures)"
    requirement: "MODEL-03"
    verification:
      - kind: integration
        ref: "tests/test_routing.py#TestLiveEngines (2 passed live; skip + bad-key paths)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Promptfoo regression config or documented compare-mode fallback"
    requirement: "MODEL-03"
    verification: []
    human_judgment: true
    rationale: "Fallback is a documented prose decision (CLI absent), not a runnable config — a human confirms the tradeoff"

duration: 24min
completed: 2026-10-12
status: complete
---

# Phase 08 Plan 05: Probe Calibration Summary

**Probe-derived gate defaults (0.62/0.04) from 40 live verdicts across both pinned engines, with a recorded baseline, compare-mode regression, and env-gated live tests.**

## Performance

- **Duration:** 24 min
- **Started:** 2026-10-12T06:29:06Z
- **Completed:** 2026-10-12T06:52:50Z
- **Tasks:** 3
- **Files modified:** 8
- **Execution mode:** SEQUENTIAL via generic-agent workaround (typed GSD dispatch unavailable in this session)

## Accomplishments

- Built `scripts/route-probe.py` importing the production state builders, both transports, validation, and gate (no duplicated logic): `--dry-run` lists the 20 probe ids offline, `--run {openrouter,local}` writes 20 JSONL verdicts with tables, top-1, margins, snapshots, and gated outcomes, and `--compare` diffs runs against the baseline with nonzero exit on model-verdict drift.
- Created the 20 labeled probes in AI-SPEC composition (6 critical, 6 edge, 5 failure, 3 adversarial), each with id, ask, side flag, acceptable tier set, and expected outcome; failure probes inject real faults (bad key, unknown model, timeout, oversize ask, missing creds/dead port) through the production transports.
- Calibrated live on both pinned engines: re-verified the decisions catalog (19 entries, `typesafe/jev-1.13` still listed, no drift), pulled `nimble` (9.5GB, no tev1 fallback needed), and derived `confidence_threshold 0.62` (midpoint of the observed 0.51/0.73 gap) plus `tie_margin 0.04` (max near-tie margin 0.03 plus one grid step) — one shared threshold, no per-engine split.
- Recorded `evals/routing-probe/baseline.json` (per-engine verdicts, snapshots, distributions, derivation note) and proved stability: fresh runs of both engines compare clean (exit 0, one top-1-jitter warning).
- Rewrote `TestLiveEngines` for the Decision APIs: typed-table plus sum-to-1 plus snapshot asserts, positive reported cost on OpenRouter, zero spend on Ollama, integration-marked with skip-on-absence and fail-loud on present-but-rejecting; the stub-server hermetic case is untouched.

## Task Commits

Each task was committed atomically:

1. **Task 1: Probe runner plus 20 labeled probes plus regression path** - `f922984` (feat)
2. **Task 2: Live calibration run fixing the shipped knob defaults** - `0e3bc06` (feat)
3. **Task 3: Env-gated live engine tests on the Decision APIs** - `a19d322` (test)

## Files Created/Modified

- `scripts/route-probe.py` - Probe runner: dry-run, run (fault injection, local warm-up/resolve), compare (drift fails, effort/top-1/snapshot warns)
- `evals/routing-probe/probes.jsonl` - 20 labeled probes in 6/6/5/3 composition with faults and deterministic ask padding
- `evals/routing-probe/baseline.json` - Per-engine verdicts, snapshots, distributions, derived defaults, derivation note
- `strands_code_cli/routing.py` - Shipped defaults 0.62/0.04 with probe-derivation docstrings, no provisional markers
- `tests/test_routing.py` - Rewritten live tests plus mandate-driven default updates (62% notes, 0.62 boundary, pinned tie-margin)
- `tests/test_loop_routing.py` - Hold-note 62% update plus pinned tie-margin on the near-tie test
- `tests/test_routing_strategy.py` - Defaults report asserts 0.04/0.62
- `docs/ROUTING.md` - Example knobs updated to the shipped defaults (stale "current defaults" comment)

## Decisions Made

- Threshold 0.62 is the midpoint of the observed wrong/correct gap (0.51 wrong-catchable max on Jev e-long-ask, 0.73 correct min on e-short-deep-1 both engines), 0.11 margin each side; every routed verdict is correct-tier except the two confident a-length-trap under-routes (0.94/0.88) no threshold catches — a directives follow-up, recorded in the baseline derivation.
- Tie margin 0.04 is the max observed near-tie margin (0.03, Jev 0.51-vs-0.48) plus one 0.01 grid step; below every routed margin (0.34 min), so the tie-break is armed but silent on the probe set. Jev's 2-decimal rounding (observed) confirms the 0.01 grid floor.
- One shared threshold: neither engine misfires in the dangerous direction (holds are all safe-direction), so no per-engine split per the plan's preference.
- Compare fails on gated model-verdict drift but warns on effort flips: D-16 routes weak effort reads ungated, and the calibration observed a real 0.52/0.48 near-tie effort flip across runs — failing on that coin flip would train users to ignore the gate.
- Run exit measures transport health only (fails when a non-fault probe gets no answers); an invalid table with answers present is a legitimate production hold verdict, and behavior drift is compare's job.
- Promptfoo fallback: the CLI is not installed, so regression runs through `--compare` (documented in the runner docstring per the plan's either/or acceptance); no install per T-08-SC.
- The `OLLAMA_LIVE` extra gate is removed: the integration marker already deselects by default, and the plan mandates execute-when-present/skip-when-absent on daemon reachability. An explicitly named but unpulled `OLLAMA_TEST_MODEL` now fails loudly instead of skipping.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Runner re-execs under uv when the direct import fails**
- **Found during:** Task 1 (plan mandates bare `python3` invocation)
- **Issue:** `strands_code_cli/__init__.py` pulls the harness CLI, which exists only in the uv venv — bare `python3 scripts/route-probe.py` died with `ModuleNotFoundError: strands_harness`.
- **Fix:** The runner tries the production import and re-execs via `uv run --project <repo> python` on failure, with a `_ROUTE_PROBE_REEXEC` guard against loops.
- **Files modified:** scripts/route-probe.py
- **Verification:** `python3 scripts/route-probe.py --dry-run` exits 0 with 20 ids from a bare interpreter
- **Committed in:** f922984 (part of task commit)

**2. [Rule 3 - Blocking] Mandated default updates to tests and docs**
- **Found during:** Task 2 (constant change 0.70/0.05 → 0.62/0.04)
- **Issue:** Tests pinned the old defaults byte-identically (62% hold notes, defaults report, 0.70 boundary); two near-tie tests used default-margin 0.52/0.48 tables that now fall outside (0.52−0.48 > 0.04 in float); the docs example claimed the old values as "current defaults".
- **Fix:** Re-aimed the notes/report/boundary at the derived values, pinned explicit `tie_margin=0.05` on the two behavior (not default) tests, updated the docs example values.
- **Files modified:** tests/test_routing.py, tests/test_loop_routing.py, tests/test_routing_strategy.py, docs/ROUTING.md
- **Verification:** Full repo suite green (1226 passed)
- **Committed in:** 0e3bc06 (part of task commit)

**3. [Rule 1 - Bug] Compare warns (not fails) on effort flips; run fails only on missing answers**
- **Found during:** Task 2 (fresh-run stability proof)
- **Issue:** The plan assumes deterministic verdicts, but live runs observed a real 0.52/0.48 near-tie effort flip and a one-off invalid-table transient on an adversarial probe (3/3 reproductions valid) — strict rules would flake the gate.
- **Fix:** Effort gated drift warns (ungated by design); run exit fails only when a non-fault probe gets no answers; invalid tables record a truncated `raw_answer` for observability.
- **Files modified:** scripts/route-probe.py
- **Verification:** Fresh runs of both engines compare clean (exit 0); bad-key forced run still fails loudly at the transport level
- **Committed in:** 0e3bc06 (part of task commit)

---

**Total deviations:** 3 auto-fixed (2 blocking, 1 bug)
**Impact on plan:** All three keep the plan's acceptance criteria truthful against observed live behavior (interpreter reality, mandated constant change, engine nondeterminism). No scope creep.

## Issues Encountered

- One transient invalid-table payload from Jev on `a-injected-instruction` in run 2 (answers present, validation failed, production held correctly); 3/3 immediate reproductions returned valid tables, and run 3 was clean — recorded here as observed provider flakiness, not a systematic injection effect.
- `e-short-deep-2` top-1 jitters across runs (0.51 → 0.56 → 0.58) but holds under 0.62 every time — the compare top-1 warning (not failure) is designed exactly for this.
- Both engines confidently under-route `a-length-trap` ("Make it fast." → cheap at 0.94/0.88) and confidently cheap-route the degenerate `f-ambiguous-hold` — no threshold separates these; criteria/directives follow-up, noted in the baseline derivation.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 08 is complete: all five rework plans executed (decision core, two-call shape, hardening, setup/docs/rig, calibration). Provisional debt is closed — no placeholder knob, pin, or threshold remains.
- Calibration maintenance contract: re-run `route-probe.py --run` on both engines plus `--compare` on any decision-model id change, directive edit, or criteria rewrite; re-pin and re-probe when a serving snapshot drifts under a pinned id.
- Deferred follow-ups (flywheel, not blockers): a-length-trap under-routing (directives/criteria), `refresh_report` decisions-count display (from 08-04), unrun live r2/r3/r4 rig scenarios (only r1 proven green).
- Live spend for this plan's calibration: ~60 Jev calls at ~$0.00002 each (≈$0.001); local calls $0.

---
*Phase: 08-model-routing-with-decision-models*
*Completed: 2026-10-12*
