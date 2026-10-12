---
phase: 08-model-routing-with-decision-models
verified: 2026-10-12T08:00:00Z
verifier: gsd-verifier 08 re-run (generic-agent workaround — typed gsd-verifier dispatch unavailable in this runtime)
status: human_needed
score: 26/27 must-haves verified
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
  - .planning/phases/08-model-routing-with-decision-models/08-CONTEXT.md
  - .planning/phases/08-model-routing-with-decision-models/08-RESEARCH.md
  - .planning/phases/08-model-routing-with-decision-models/08-REVIEW.md
  - .planning/phases/08-model-routing-with-decision-models/08-VALIDATION.md
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
behavior_unverified: 1
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 23/24
  gaps_closed:
    - "GAP-01: unquoted YAML-bool off in candidate levels SKIPs the candidate (truth 20 blocker)"
    - "GAP-02: unhashable choice raises TypeError instead of holding (truth 4 warning)"
    - "GAP-03: --run openrouter aborts without a local Ollama daemon (truth 21 warning)"
  gaps_remaining: []
  regressions: []
behavior_unverified_items:
  - truth: "UAT scenarios r1 through r4 exercise the Decision-API flow against live engines"
    test: "Run `python3 scripts/uattest/driver.py r1`, `r2`, `r3`, `r4` (tmux + OPENROUTER_API_KEY + Ollama + Bedrock)"
    expected: "R1/R2/R3/R4 PASS — live local-engine route, /model override respect, side-ask parity against real engines"
    why_human: "Live-engine round-trips with real latency/spend; hermetic suite cannot cover them. Code blocker fixed and validate now passes, but r2/r3/r4 have never run live and r1 needs a post-fix regression run."
human_verification:
  - test: "Run `python3 scripts/uattest/driver.py r2`, `r3`, `r4` (tmux + OPENROUTER_API_KEY + Ollama + Bedrock)"
    expected: "R2/R3/R4 PASS — live local-engine route, /model override respect, side-ask parity against real engines"
    why_human: "First live acceptance of the unblocked flow; hermetic suite proves validate passes but cannot cover live round-trips with real latency/spend (08-VALIDATION.md Manual-Only)."
  - test: "Re-run `python3 scripts/uattest/driver.py r1` after the GAP-01 loader fix (regression)"
    expected: "R1 PASS (was green pre-fix; confirms the loader change did not regress the cloud path)"
    why_human: "Live smoke after a loader change; hermetic tests cover the loader but not the rig end to end."
  - test: "Run `python3 scripts/route-probe.py --run openrouter && python3 scripts/route-probe.py --run local && python3 scripts/route-probe.py --compare`"
    expected: "20+20 JSONL verdicts, exit 0, no model-verdict drift vs evals/routing-probe/baseline.json"
    why_human: "Live calibration stability + nondeterministic effort reads need live engines with spend; re-run contract on decision-model id change, directive edit, or criteria rewrite (08-VALIDATION.md Manual-Only)."
---

# Phase 08: Model Routing with Decision Models Verification Report (Re-verification)

**Phase Goal:** The CLI picks the right model and thinking budget per ask via a cheap decision model, with manual override kept.
**Verified:** 2026-10-12
**Status:** human_needed
**Re-verification:** Yes — after 08-06 gap closure
**Verifier:** gsd-verifier 08 re-run (generic-agent workaround — typed dispatch unavailable; results labeled accordingly)

## Verdict

All three prior gaps are closed in source, each re-probed by execution
against the exact prior failure mode — not by trusting SUMMARY claims.
The full suite is green (1253 passed, 8 deselected — re-run this
session), no regressions, no debt markers in the changed files, and the
08-06 gap plan's three must-haves verify with behavioral evidence. No
code gap remains.

Status is `human_needed`, not `passed`, per the ordered decision tree:
live UAT (rig r1–r4, probe run/compare) requires human runs against
live engines with real latency/spend, and truth 20 asserts exactly that
live exercise — r2/r3/r4 have never run live (previously blocked by
GAP-01), and r1 needs a post-fix regression run. Truth 20 is therefore
PRESENT_BEHAVIOR_UNVERIFIED: present and wired, behavior unexercised. It
is excluded from the verified score. Everything a hermetic check can
prove is proven; only live-engine confirmation is outstanding.

## Goal Achievement

Roadmap Success Criteria (unchanged from prior verification; MODEL-03):

- SC1 ("per ask, a decision model selects the model and thinking budget
  from almanac candidates") — VERIFIED via truths 1–3, 6–8, 20
  (code path), 25–26.
- SC2 ("deterministic heuristic fallback plus manual /model override")
  — VERIFIED via truths 2, 4, 5, 11–13, 26.
- SC3 ("routing decisions visible in transcript or /cost") — VERIFIED
  via truths 1, 9.

### Observable Truths

| # | Truth (plan) | Status | Evidence |
|---|--------------|--------|----------|
| 1 | 08-01: routed ask served by the picked model; line shows choice, confidence, ~$/ask delta | ✓ VERIFIED | Regression: unchanged since prior verification; full suite green |
| 2 | 08-01: below-threshold pick holds with a distinct note naming both numbers | ✓ VERIFIED | Regression: unchanged; threshold-hold tests pass in full suite |
| 3 | 08-01: near-tie top-two routes the cheaper candidate with a noted substitution | ✓ VERIFIED | Regression: unchanged; tie tests pass in full suite |
| 4 | 08-01: malformed answers (wrong type, bad sum, stale choice) hold instead of routing | ✓ VERIFIED | GAP-02 closed: `not isinstance(choice, str)` guard at routing.py:1314 + :1335; executed probe: list/dict/tuple/int/None choice → None on both `_validate_choice_shape` and `validate_choice_answer`, no TypeError; string control still validates; `TestUnhashableChoiceHolds` passes |
| 5 | 08-01: toggle-off, missing strategy, manual pins skip decision calls silently | ✓ VERIFIED | Regression: unchanged; skip tests pass in full suite |
| 6 | 08-02: thinking level from a second decision call over picked-model levels only | ✓ VERIFIED | Regression: unchanged; two-POST scoping tests pass |
| 7 | 08-02: weak effort read still routes; only model confidence gates | ✓ VERIFIED | Regression: unchanged; weak-read tests pass |
| 8 | 08-02: single-candidate strategy skips model call but still asks effort | ✓ VERIFIED | Regression: unchanged; `TestSingleCandidateFastPath` passes |
| 9 | 08-02: transcript line shows model + effort confidence inline | ✓ VERIFIED | Regression: unchanged; line-shape tests pass |
| 10 | 08-02: /btw side ask routes through the same strategy flagged side with its own line | ✓ VERIFIED | Regression: unchanged; `TestSideRouting` passes |
| 11 | 08-03: local engine attempted only when daemon meets floor and tag is pulled | ✓ VERIFIED | Regression: unchanged; `TestLocalEngine` passes |
| 12 | 08-03: retryable failures retry once then fall through; 4xx/schema hold zero-retry | ✓ VERIFIED | Regression: unchanged; `TestEngineChain` POST-count assertions pass |
| 13 | 08-03: offline pauses routing, serves current with a distinct note | ✓ VERIFIED | Regression: unchanged; pause tests pass |
| 14 | 08-03: oversized payloads truncated code-side with a note, never sent to 413 | ✓ VERIFIED | Regression: unchanged; truncation tests pass |
| 15 | 08-03: hold/failure notes print under quiet; routed lines suppressible | ✓ VERIFIED | Regression: unchanged; quiet-matrix tests pass |
| 16 | 08-04: setup offers chat models for candidates, decision models for the decider | ✓ VERIFIED | Regression: unchanged; split-catalog tests pass |
| 17 | 08-04: setup never offers alias/zero-context deciders, never assumes a default | ✓ VERIFIED | Regression: unchanged; `TestRouteSetup` passes |
| 18 | 08-04: /route validate judges the decider against the decisions catalog | ✓ VERIFIED | Regression: unchanged; pass/fail tests green |
| 19 | 08-04: docs ship example strategies with criteria + knobs that validate | ✓ VERIFIED | Regression: unchanged; verbatim-docs test passes |
| 20 | 08-04: UAT r1–r4 exercise the Decision-API flow against live engines | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | Code blocker FIXED (see truth 25): rig-shape strategy with unquoted `levels: [auto, off]` now reports both candidates ok, no "no usable candidates". But r2/r3/r4 have never run live and r1 needs a post-fix regression run — live round-trips need human runs (see Human Verification) |
| 21 | 08-05: labeled 20-probe set runs through both engines with JSONL verdicts | ✓ VERIFIED | GAP-03 closed: `cmd_run` resolves the local tag only when `engine == "local"` (route-probe.py:477-479), `LOCAL_MODEL_PIN` recorded for cloud runs, `_warm_local` untouched on the local path; executed probe with raising resolver + raising warm: openrouter rc=0, 20 verdicts, daemon untouched; local path still resolves + warms; `--dry-run` exit 0 |
| 22 | 08-05: shipped tie_margin + confidence_threshold derive from observed probe distributions | ✓ VERIFIED | Regression: unchanged; baseline equals shipped constants |
| 23 | 08-05: probe regressions fail loudly via baseline comparison | ✓ VERIFIED | Regression: unchanged; `TestRegressionPath` + `TestCalibrationBaseline` pass |
| 24 | 08-05: live engine tests pass with credentials, skip without, fail loudly on broken | ✓ VERIFIED | Regression: unchanged; integration-gated (2 deselected by default); prior live pass stands |
| 25 | 08-06: strategies with unquoted YAML-bool off in candidate levels load as usable candidates with on/off string levels | ✓ VERIFIED | `_candidate_skip_reason` accepts `(str, bool)` levels (routing.py:191-195); `_parse_candidate` folds `is True/False` → on/off strings (routing.py:221-227); executed probe: YAML `levels: [auto, off]` → `['auto', False]` → skip_reason None → parsed `['auto', 'off']`; int levels (`3`, `1`) still SKIP; `TestBoolLevelNormalization` passes; commit 08d6d4a |
| 26 | 08-06: malformed decision answers with a non-string choice hold instead of raising TypeError | ✓ VERIFIED | Same evidence as truth 4 re-probe; `_validate_effort_answer` inherits via shared shape check; commit e27b322 |
| 27 | 08-06: cloud-only probe runs resolve no local tag and never require an Ollama daemon | ✓ VERIFIED | Same evidence as truth 21 re-probe (plan acceptance was a /tmp scratch check + --dry-run; re-probed here by execution since no committed test pins it); commit eb7db12 |

**Score:** 26/27 truths verified (1 present, behavior-unverified).

### Advisory (New Scope, Unevidenced)

None. No new-scope findings: the gap diff (`08d6d4a..0109ef6`) touches
only the three gap fixes plus tests, no debt markers (`TBD|FIXME|XXX|
TODO|HACK|PLACEHOLDER`) in `strands_code_cli/routing.py` or
`scripts/route-probe.py`, and the scoped re-review's 6 infos carry no
blocking content.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| strands_code_cli/routing.py | Bool-tolerant loader + str-guarded validation | ✓ VERIFIED | Skip gate + fold + both guards present, substantive, wired (validate + decide paths); full suite green |
| scripts/route-probe.py | Lazy local-tag resolution | ✓ VERIFIED | `engine == "local"` gate present and behaviorally proven; local path intact |
| tests/test_routing_strategy.py | `TestBoolLevelNormalization` | ✓ VERIFIED | False→off, True→on, unquoted-YAML usable, int still skips — pass |
| tests/test_routing.py | `TestUnhashableChoiceHolds` | ✓ VERIFIED | list/dict/tuple hold on both paths, string control validates — pass |
| Prior-phase artifacts (loop.py, cost_context.py, live_pricing.py, router.py, driver.py, ROUTING.md, probes, baseline) | Unchanged behavior | ✓ VERIFIED | Regression: full suite 1253 passed covers; no diff in these files since prior verification except none |

### Key Links

| From | To | Via | Status |
|------|----|-----|--------|
| routing.py `_candidate_skip_reason` | uattest/driver.py rig strategies | Accepts unquoted `levels` entries | ✓ WIRED (executed: rig-shape file validates, candidates ok) |
| route-probe.py `cmd_run` | routing.py `resolve_local_model` | Resolved only on the local-engine path | ✓ WIRED (executed: raising resolver never fires on openrouter path) |
| Prior key links (transports → decide → hook; setup → catalogs; probe → baseline) | — | — | ✓ WIRED (regression: full suite green) |

### Requirements Coverage

- MODEL-03 ("CLI auto-selects model and thinking budget per ask via a
  decision model, with manual override") — SATISFIED code-side; live
  acceptance (r1–r4 rig, probe run/compare) outstanding as human UAT.
  No orphaned requirements (REQUIREMENTS.md maps only MODEL-03 to
  Phase 8).

## Behavioral Spot-Checks (this session, by execution)

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| YAML `levels: [auto, off]` loads usable | `uv run python -c` loader probe | skip None, parsed `['auto','off']`; int still skips | ✓ PASS |
| list/dict/tuple choice holds | `uv run python -c` validation probe | None on both paths, no TypeError; string validates | ✓ PASS |
| openrouter run without daemon | importlib + raising resolver/warm, `cmd_run(engine='openrouter')` | rc=0, 20 verdicts, tag=`LOCAL_MODEL_PIN` | ✓ PASS |
| local run still resolves + warms | same harness, `cmd_run(engine='local')` | resolve + warm ran with resolved tag | ✓ PASS |
| Rig-shape strategy validates | `validate_strategy` on unquoted-levels file | both candidates ok, no "no usable candidates" (engine section invalid only for missing engine config in the minimal fixture — unrelated) | ✓ PASS |
| New pinning tests | `pytest TestUnhashableChoiceHolds TestBoolLevelNormalization` | 8 passed | ✓ PASS |
| Full suite | `uv run pytest -q` | 1253 passed, 8 deselected | ✓ PASS |
| Live rig r1–r4 / probe run+compare | — | Not run: live engines + spend need human runs per scope | ? SKIP → Human Verification |

## Human Verification

### 1. Rig r2/r3/r4 live runs (first acceptance)

**Test:** `python3 scripts/uattest/driver.py r2`, `r3`, `r4` (tmux + OPENROUTER_API_KEY + Ollama + Bedrock)
**Expected:** R2/R3/R4 PASS
**Why human:** Live-engine round-trips with real latency/spend; first live run of the unblocked flow.

### 2. Rig r1 live regression

**Test:** `python3 scripts/uattest/driver.py r1`
**Expected:** R1 PASS (was green pre-fix)
**Why human:** Live smoke after a loader change; hermetic tests cover the loader but not the rig end to end.

### 3. Probe live run + compare

**Test:** `python3 scripts/route-probe.py --run openrouter && python3 scripts/route-probe.py --run local && python3 scripts/route-probe.py --compare`
**Expected:** 20+20 JSONL verdicts, exit 0, no model-verdict drift vs baseline
**Why human:** Live calibration stability + nondeterministic effort reads need live engines with spend.

## Gaps

None. All prior gaps closed; no new gaps found; no regressions.
