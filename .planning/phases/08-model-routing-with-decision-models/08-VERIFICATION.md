---
phase: 08-model-routing-with-decision-models
verified: 2026-10-12T09:30:00Z
verifier: gsd-verifier 08 final (generic-agent workaround — typed gsd-verifier dispatch unavailable in this runtime)
status: passed
score: 31/31 must-haves verified
covered_digest: "v1:sha256:b107882fe7c8162c733d84a9670fd7bdac42e2407273451a17fe9d011cb245fc"
covered_files:
  - .planning/REQUIREMENTS.md
  - .planning/phases/08-model-routing-with-decision-models/08-01-PLAN.md
  - .planning/phases/08-model-routing-with-decision-models/08-01-SUMMARY.md
  - .planning/phases/08-model-routing-with-decision-models/08-02-PLAN.md
  - .planning/phases/08-model-routing-with-decision-models/08-02-SUMMARY.md
  - .planning/phases/08-model-routing-with-decision-models/08-03-PLAN.md
  - .planning/phases/08-model-routing-with-decision-models/08-03-SUMMARY.md
  - .planning/phases/08-model-routing-with-decision-models/08-04-PLAN.md
  - .planning/phases/08-model-routing-with-decision-models/08-04-SUMMARY.md
  - .planning/phases/08-model-routing-with-decision-models/08-05-PLAN.md
  - .planning/phases/08-model-routing-with-decision-models/08-05-SUMMARY.md
  - .planning/phases/08-model-routing-with-decision-models/08-06-PLAN.md
  - .planning/phases/08-model-routing-with-decision-models/08-06-SUMMARY.md
  - .planning/phases/08-model-routing-with-decision-models/08-07-PLAN.md
  - .planning/phases/08-model-routing-with-decision-models/08-07-SUMMARY.md
  - .planning/phases/08-model-routing-with-decision-models/08-CONTEXT.md
  - .planning/phases/08-model-routing-with-decision-models/08-RESEARCH.md
  - .planning/phases/08-model-routing-with-decision-models/08-REVIEW.md
  - .planning/phases/08-model-routing-with-decision-models/08-UAT.md
  - .planning/phases/08-model-routing-with-decision-models/08-VALIDATION.md
  - .planning/debug/rig-bedrock-model-id.md
  - strands_code_cli/routing.py
  - strands_code_cli/loop.py
  - strands_code_cli/cost_context.py
  - strands_code_cli/live_pricing.py
  - strands_code_cli/router.py
  - scripts/route-probe.py
  - scripts/uattest/driver.py
  - docs/ROUTING.md
  - evals/routing-probe/probes.jsonl
  - evals/routing-probe/baseline.json
  - tests/test_routing.py
  - tests/test_loop_routing.py
  - tests/test_routing_strategy.py
  - tests/test_cost_context.py
  - tests/test_live_pricing.py
  - tests/test_routing_calibration.py
  - tests/test_uattest_driver.py
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 26/27
  gaps_closed:
    - "G-08-1: rig Bedrock id (UAT test 1 blocker) — profile-form id, fail-fast waits, persistence fence, rig timing fixes; live R2/R3/R4 PASS"
  gaps_remaining: []
  regressions: []
---

# Phase 08: Model Routing with Decision Models Verification Report (Final Re-verification)

**Phase Goal:** The CLI picks the right model and thinking budget per ask via a cheap decision model, with manual override kept.
**Verified:** 2026-10-12
**Status:** passed
**Re-verification:** Yes — after 08-07 UAT gap closure (G-08-1)
**Verifier:** gsd-verifier 08 final (generic-agent workaround — typed dispatch unavailable; results labeled accordingly)

## Verdict

G-08-1 is genuinely closed. The 08-07 diff (`efc2874..2dad781`,
SUMMARY `368cfb1`) was verified by source inspection plus execution,
and the fresh live transcripts (`/tmp/uatr8/r2.log`, `r3.log`,
`r4.log`, all written after the last fix commit) contain every marker
each rig scenario asserts — real Bedrock turns served through the
profile-form id, both confidences on every routed line, the D-16 hold
plus retry path, and the side-headed `(btw)` flow. Zero `Turn failed`
lines across all three transcripts. The global default is still the
haiku profile id after routed turns, proving the fence held live.

All 31 must-haves verify (27 prior + 4 new from 08-07). The full
suite is green (1270 passed, 8 deselected — re-run this session),
both negative gates hold (zero bare-form ids, exactly one
`save_model_choice` call site), no debt markers in the changed
files, and the scoped re-review reports 0 critical / 0 warning /
8 info with a fence PASS. No code gap remains and no live run
remains outstanding: UAT tests 2 (r1 regression) and 3 (probe
run/compare) passed by human run, and test 1 (r2/r3/r4) is now
evidenced by the live transcripts. Status is `passed`.

## Goal Achievement

Roadmap Success Criteria (MODEL-03):

- SC1 ("per ask, a decision model selects the model and thinking budget
  from almanac candidates") — VERIFIED via truths 1–3, 6–8, 20
  (now live-exercised), 25–26, 28, 31.
- SC2 ("deterministic heuristic fallback plus manual /model override",
  reinterpreted by D-08 as deterministic hold-current) — VERIFIED
  via truths 2, 4, 5, 11–13, 26, 30.
- SC3 ("routing decisions visible in transcript or /cost") — VERIFIED
  via truths 1, 9, and live /cost entries in all three transcripts.

### Observable Truths

| # | Truth (plan) | Status | Evidence |
|---|--------------|--------|----------|
| 1 | 08-01: routed ask served by the picked model; line shows choice, confidence, ~$/ask delta | ✓ VERIFIED | Regression: full suite green; live transcripts show Routed lines with deltas (r2:34, r3:32, r4:21) |
| 2 | 08-01: below-threshold pick holds with a distinct note naming both numbers | ✓ VERIFIED | Regression + live: r3:81 `Routing held ... (confidence 56% < 62%; retrying next ask)` |
| 3 | 08-01: near-tie top-two routes the cheaper candidate with a noted substitution | ✓ VERIFIED | Regression: unchanged; tie tests pass in full suite |
| 4 | 08-01: malformed answers (wrong type, bad sum, stale choice) hold instead of routing | ✓ VERIFIED | Regression: `TestUnhashableChoiceHolds` passes; guards untouched |
| 5 | 08-01: toggle-off, missing strategy, manual pins skip decision calls silently | ✓ VERIFIED | Regression + live: r3 off-section routes zero new picks (lines 53-75) |
| 6 | 08-02: thinking level from a second decision call over picked-model levels only | ✓ VERIFIED | Regression: two-POST scoping tests pass |
| 7 | 08-02: weak effort read still routes; only model confidence gates | ✓ VERIFIED | Regression: weak-read tests pass |
| 8 | 08-02: single-candidate strategy skips model call but still asks effort | ✓ VERIFIED | Regression: `TestSingleCandidateFastPath` passes |
| 9 | 08-02: transcript line shows model + effort confidence inline | ✓ VERIFIED | Regression + live: every Routed line carries both (r2:34, r3:32/110, r4:21/25) |
| 10 | 08-02: /btw side ask routes through the same strategy flagged side with its own line | ✓ VERIFIED | Regression + live: r4:24-25 `Side question noted` + `Routed (btw) → ... (off): model 65%, effort 99%` |
| 11 | 08-03: local engine attempted only when daemon meets floor and tag is pulled | ✓ VERIFIED | Regression + live: r2 routes via local engine (r2:43 `via local $0.0000`) |
| 12 | 08-03: retryable failures retry once then fall through; 4xx/schema hold zero-retry | ✓ VERIFIED | Regression: `TestEngineChain` POST-count assertions pass |
| 13 | 08-03: offline pauses routing, serves current with a distinct note | ✓ VERIFIED | Regression: pause tests pass |
| 14 | 08-03: oversized payloads truncated code-side with a note, never sent to 413 | ✓ VERIFIED | Regression: truncation tests pass |
| 15 | 08-03: hold/failure notes print under quiet; routed lines suppressible | ✓ VERIFIED | Regression: quiet-matrix tests pass |
| 16 | 08-04: setup offers chat models for candidates, decision models for the decider | ✓ VERIFIED | Regression: split-catalog tests pass |
| 17 | 08-04: setup never offers alias/zero-context deciders, never assumes a default | ✓ VERIFIED | Regression: `TestRouteSetup` passes |
| 18 | 08-04: /route validate judges the decider against the decisions catalog | ✓ VERIFIED | Regression + live: r2:18-26, r3:21-28 validate outputs |
| 19 | 08-04: docs ship example strategies with criteria + knobs that validate | ✓ VERIFIED | Regression: verbatim-docs test passes; docs example now profile-form (ROUTING.md:62) |
| 20 | 08-04: UAT r1–r4 exercise the Decision-API flow against live engines | ✓ VERIFIED | r1 PASS (UAT test 2, human run, /tmp/uatr8/r1.log); r2/r3/r4 live transcripts contain every asserted marker (see G-08-1 evidence below), zero `Turn failed` |
| 21 | 08-05: labeled 20-probe set runs through both engines with JSONL verdicts | ✓ VERIFIED | Regression: lazy-tag gate intact; UAT test 3 (human run/compare) passed |
| 22 | 08-05: shipped tie_margin + confidence_threshold derive from observed probe distributions | ✓ VERIFIED | Regression: baseline equals shipped constants |
| 23 | 08-05: probe regressions fail loudly via baseline comparison | ✓ VERIFIED | Regression: `TestRegressionPath` + `TestCalibrationBaseline` pass |
| 24 | 08-05: live engine tests pass with credentials, skip without, fail loudly on broken | ✓ VERIFIED | Regression: integration-gated (2 deselected by default); prior live pass stands |
| 25 | 08-06: strategies with unquoted YAML-bool off in candidate levels load as usable candidates with on/off string levels | ✓ VERIFIED | Regression: `TestBoolLevelNormalization` passes; rig strategies use unquoted `levels: [auto, off]` live |
| 26 | 08-06: malformed decision answers with a non-string choice hold instead of raising TypeError | ✓ VERIFIED | Regression: guards untouched, tests pass |
| 27 | 08-06: cloud-only probe runs resolve no local tag and never require an Ollama daemon | ✓ VERIFIED | Regression: lazy gate untouched |
| 28 | 08-07: rig r2/r3/r4 strategies route to the invokable Bedrock profile-form id, never the throughput-incompatible bare id | ✓ VERIFIED | `RIG_NOVA_MICRO = "bedrock/us.amazon.nova-micro-v1:0"` (driver.py); all 3 blocks build from it (efc2874); bare-form gate 0 occurrences; live: r3:32 routes to and is served by the profile id (also closes the debug blind spot — profile form now live-invoked, not inferred) |
| 29 | 08-07: rig waits abort fast with a diagnostic naming the failed turn instead of hanging to timeout | ✓ VERIFIED | `FAIL_RE` + raise in `wait_main_end` (driver.py:127-131) and `wait_routed` (:300-304), 30f58b6; `TestFailFast` passes (raise shape + no-false-positive); live runs never hung (no TIMEOUT, 3/3 transcripts complete) |
| 30 | 08-07: routed picks never rewrite the global default model; explicit /model choices still persist | ✓ VERIFIED | `save_model_choice` removed from routed-pick branch (loop.py:1544-1554, a275cb8); exactly one call site remains (explicit /model, loop.py:2183); `TestRoutedPickNoPersist` passes; live: `~/.config/strands-code/config.yaml` still haiku profile id after routed turns |
| 31 | 08-07: live r3/r4 PASS against real engines, or the exact live-run step documented for a human run | ✓ VERIFIED | Live r3 + r4 transcripts contain every asserted marker (plus r2 regression); no human step needed — see G-08-1 evidence |

**Score:** 31/31 truths verified (0 present-behavior-unverified, 0 failed).

### G-08-1 Closure Evidence (transcript marker audit)

Each rig scenario prints its PASS only after all asserts hold; the
pane transcripts below were checked assert-by-assert against
`scenario_r2`/`scenario_r3`/`scenario_r4` in `scripts/uattest/driver.py`:

- **R2 (local engine):** validate `candidate #0 bedrock/us.amazon.nova-micro-v1:0: ok` + haiku ok (r2:20-21);
  `Routing: on` + strategy source (r2:30-32); `Routed → haiku (off):
  model 62%, effort 55%` (r2:34); turn served (r2:36); /cost
  `ask 1: haiku (off) [model 62%, effort 55%] via local $0.0000`
  (r2:43), no `[held]`. Zero `Turn failed`.
- **R3 (cloud engine + toggle + hold/retry):** validate profile-form ok
  (r3:23-24); `Routed → bedrock/us.amazon.nova-micro-v1:0 (off):
  model 75%, effort 99%` served with `(n/a)` cost line (r3:32-40);
  /cost openrouter entry with both confidences + spend (r3:46);
  off-section routes nothing new (r3:53-75); on-section holds
  `56% < 62%` with the `HOLD_NOTE_RE` shape (r3:81), retry routes to
  haiku with confidences (r3:110). Zero `Turn failed`.
- **R4 (side channel):** main `Routed → haiku (off): model 89%,
  effort 68%` (r4:21); mid-turn `Side question noted` (r4:24) +
  `Routed (btw) → haiku (off): model 65%, effort 99%` (r4:25);
  fenced side block served (r4:30-34); /cost `ask 2 (btw)` with
  both confidences via openrouter (r4:514). Zero `Turn failed`.
- **Freshness:** r2/r3/r4 logs written 01:56–01:57 local, after the
  last fix commit `2dad781` (01:55); w2/w3/w4 strategies all carry
  the profile-form id; global default confirmed haiku post-run.
- **Debug falsification test satisfied:** replacing the rig candidate
  with `us.amazon.nova-micro-v1:0` removed the ValidationException —
  r3 routes to it and the turn is served.

### CONTEXT Decisions (D-01..D-16) Honored

- D-01 (auto-on only with strategy): rig enables explicitly; unchanged.
- D-04 (side asks route flagged side): r4 `Routed (btw)` + `(btw)` cost entry live.
- D-05/D-15 (second effort call; single-candidate still asks effort): both confidences on every live routed line.
- D-08 (models-only fallback, hold + retry next ask): r3 hold/retry path exercised live; fail-fast only shortens rig diagnosis, never adds a heuristic pick.
- D-10 (session toggle; /model persists with warning): toggle round-trip live (r3); fence keeps /model the sole `save_model_choice` writer — no D-XX mandates routed-pick persistence.
- D-12 (one line: choice + both confidences + ~$/ask delta; /cost entry): present in all three transcripts.
- D-13 (setup + docs examples + structural validate): docs example updated to the invokable id; validate still structural-only (unchanged, by design).
- D-14/D-16 (tie_margin + confidence_threshold knobs): defaults in every validate output; 56%<62% hold live.
- D-02/D-03/D-06/D-07/D-09/D-11: untouched by the gap diff; prior verification stands.

### RESEARCH Pitfalls

Load-bearing pitfalls (vendor-specific confidence, 2–26 cap,
quantities ban, Ollama 413 bound, fast-path rewrite, none-vs-HOLD)
are unchanged by the gap diff, which touches only the rig id,
rig waits, docs example, and the persistence fence. No pitfall
regressed: full suite green, no new decision-call construction.

### Advisory (New Scope, Unevidenced)

None. The 08-07 diff touches only the gap-closure scope (driver.py,
loop.py fence hunk, ROUTING.md example, two test files); no debt
markers; the scoped re-review's 8 infos carry no blocking content.
IN-07 (stale `_route_pre_turn` docstring sentence claiming routed
persistence) and IN-08 (fail-fast not extended to `wait_for`/
`wait_for_new`) are recorded follow-ups, not gaps — both explicitly
info-level in 08-REVIEW.md.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| scripts/uattest/driver.py | RIG_NOVA_MICRO + FAIL_RE + (n/a) COST_RE + pre-send baselines | ✓ VERIFIED | Constant + 3 f-string blocks; fail-fast in both turn waits; `(?:\d+%|n/a)` gate; `before=` param + 7 pre-send sites; live-proven |
| docs/ROUTING.md | Profile-form cheap-default example | ✓ VERIFIED | Line 62 profile form; tier/criteria/levels byte-identical |
| strands_code_cli/loop.py | Fenced routed-pick branch | ✓ VERIFIED | In-memory apply only; single save_model_choice site (explicit /model); fence PASS in re-review |
| tests/test_uattest_driver.py | Profile + fail-fast + timing pins | ✓ VERIFIED | 12+ tests pass (RigModelId, FailFast, baselines) |
| tests/test_loop_routing.py | TestRoutedPickNoPersist + migrated assertions | ✓ VERIFIED | Zero-save + switch + note + call-site tripwire pass |
| Prior-phase artifacts (routing.py, cost_context.py, live_pricing.py, router.py, route-probe.py, probes, baseline) | Unchanged behavior | ✓ VERIFIED | No diff since prior verification except the 08-07 scope; full suite green |

### Key Links

| From | To | Via | Status |
|------|----|-----|--------|
| driver.py waits | loop.py `Turn failed` lines | FAIL_RE matches both emit sites (loop.py:1859, :2262) | ✓ WIRED (literal match; case-sensitive; no false vocabulary) |
| loop.py routed branch | provider_config.py | No call remains; only explicit /model calls save_model_choice | ✓ WIRED (fence; count == 1) |
| driver.py strategies | Bedrock Converse | RIG_NOVA_MICRO profile form, ACTIVE SYSTEM_DEFINED | ✓ WIRED (live: r3 served through it) |
| Prior key links | — | — | ✓ WIRED (regression: full suite green) |

### Requirements Coverage

- MODEL-03 ("CLI auto-selects model and thinking budget per ask via a
  decision model, with manual override") — SATISFIED: code path
  verified hermetically (truths 1–19, 21–27), live acceptance
  complete (r1–r4 PASS evidence, probe run/compare PASS per UAT),
  manual override fenced as the sole persistence path. No orphaned
  requirements (REQUIREMENTS.md maps only MODEL-03 to Phase 8).

## Behavioral Spot-Checks (this session, by execution)

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Routing + rig test files | `uv run pytest tests/test_uattest_driver.py tests/test_loop_routing.py tests/test_routing.py tests/test_routing_strategy.py -q` | 301 passed, 2 deselected | ✓ PASS |
| Full suite | `uv run pytest -q` | 1270 passed, 8 deselected | ✓ PASS |
| Bare-form negative gate | `grep -v '^#' driver.py ROUTING.md \| grep -c 'bedrock/amazon\.nova-micro-v1:0'` | 0 occurrences | ✓ PASS |
| Single call-site gate | `grep -c save_model_choice loop.py` | 1 (explicit /model branch) | ✓ PASS |
| Debt markers in changed files | `grep -E "TBD\|FIXME\|XXX\|TODO\|HACK\|PLACEHOLDER"` | no matches | ✓ PASS |
| Failure markers in live transcripts | `grep -c "Turn failed" r2/r3/r4.log` | 0/0/0 | ✓ PASS |
| R3 hold-note shape | `HOLD_NOTE_RE` vs r3:81 | matches | ✓ PASS |
| Global default post-live-runs | `grep '^model:' config.yaml` | haiku profile id (fence held) | ✓ PASS |
| Rig strategies on disk | `grep "id: bedrock" w2/w3/w4 routing.yaml` | profile form ×3 | ✓ PASS |

## Human Verification

None required. All live-engine items are evidenced: UAT test 2 (r1
regression) and test 3 (probe run/compare) passed by human run per
08-UAT.md, and test 1 (r2/r3/r4) is closed by the fresh live
transcripts audited above. No further billed runs are needed to
accept this phase.

## Gaps

None. G-08-1 closed; no new gaps found; no regressions.
