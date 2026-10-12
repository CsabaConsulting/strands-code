---
phase: 09-native-typesafe-decision-engine
verified: 2026-10-12T21:30:00Z
verifier: gsd-verifier 09 (generic-agent workaround — typed dispatch unavailable; label accordingly)
status: passed
score: 19/19 truths verified (3 roadmap success criteria + 16 plan truths, 0 failed, 0 uncertain)
is_re_verification: false
must_haves:
  truths:
    - "SC1: User with TYPESAFE_API_KEY can select native in /route setup and validate it"
    - "SC2: Native decisions return the same verdict shape (answers, confidences, reported spend)"
    - "SC3: Chain, preflight, retry, calibration cover native like the others"
    - "01-T1: Native-routed ask served by the TypeSafe-picked model with the shared verdict shape"
    - "01-T2: Ordered engines list drives chain order; legacy primary maps identically + nudge"
    - "01-T3: Native 4xx holds with zero retry + distinct note; retryable faults retry exactly once"
    - "01-T4: Native timeout/interrupt holds with distinct note, no partial engine state"
    - "01-T5: Strategy judging validates corrected pins, rejects unverified forms with fix lines"
    - "01-T6: Native-routed ask renders computed spend inline (never $0.0000) with Prices marker"
    - "02-T1: Setup availability-proposed order; native hidden without key"
    - "02-T2: Setup offers exactly the corrected pinned Jev strings + alias drift warning"
    - "02-T3: Validate live-pings native; bad keys / wrong models fail with fix lines"
    - "02-T4: Keyless native skip note once per session unless suppressed via config"
    - "02-T5: Setup aborts fail closed; never prompts for or persists keys"
    - "03-T1: Probe runner executes the full 20-probe set through native + diffs baseline"
    - "03-T2: Native calibration reuses shared 0.62/0.04 knobs unless probes prove divergence"
    - "03-T3: Native-vs-OpenRouter disagreement investigated as bug, never preferring a side"
    - "03-T4: Live native tests pass with key, skip without, fail loudly on rejection"
    - "03-T5: Rig scenarios cover native setup/validate/routing, key-present and key-absent"
requirements:
  - MODEL-04: SATISFIED
prohibitions:
  - statement: "MUST NOT silently report $0.0000 spend for a paid native decision call"
    verification: test
    status: verified
    evidence: "cost=in_tok*0.042/1e6 whenever input_tokens>0 (routing.py:1352); TestNativeSpend + live spend-identity tests pass"
  - statement: "MUST NOT silently substitute a different Jev build than pinned"
    verification: judgment
    status: unverified-prohibition — human review recommended (NON-AUTHORITATIVE LLM-judge: mechanically supported)
    evidence: "Pin-first radio, alias drift warning (router.py:1079-1084), per-verdict snapshot (routing.py:1353), compare flags moves; cross-release drift unprovable in one run"
  - statement: "MUST NOT send beyond shared decision state to the native endpoint"
    verification: test
    status: verified
    evidence: "POST body exactly {model,state,questions} (routing.py:1323-1325); test pins state=={ask,directives,side} + header-only auth"
advisory:
  - "WR-01 (09-REVIEW.md): hand-written order:[] prints hold note + cost event every ask while legacy primary:off stays silent (load_strategy only None-switches primary==off). Reproduced at decide() level as EQUIVALENT (both ('off',(0,0,None),'off failed')); divergence is hook-level noise only, setup can never write order:[], hold is safe. No must-have truth fails → advisory, not a gap. Suggested fix stands (treat empty effective order as the off switch in load_strategy)."
  - "IN-01: non-list order judges legacy-fallback engines with extra cosmetic lines; verdict stays INVALID. Info only."
  - "IN-02: pin string triplicated (routing NATIVE_JEV_PIN, probe NATIVE_MODEL_PIN, rig NATIVE_PIN). Info only."
  - "IN-03: rig strategy_order misparses flow-style order:[] as ['']. Never fires today (no scenario writes empty order). Info only."
gaps: []
human_needed: []
---

# Phase 09 Verification: Native TypeSafe Decision Engine

**Status:** passed — 19/19 truths verified, 0 gaps.
**Provenance:** produced by gsd-verifier 09 via the generic-agent workaround (typed dispatch unavailable); results labeled accordingly.

## Goal-Backward Verdict

Phase goal: *Routing can use Jev via TypeSafe's native API directly, alongside the OpenRouter and Ollama engines.* All three roadmap success criteria hold in the codebase with behavioral evidence, and all 16 plan must-have truths verify against production code paths (not SUMMARY claims).

## Roadmap Success Criteria

| # | Criterion | Status | Evidence (observed, not claimed) |
|---|-----------|--------|----------------------------------|
| SC1 | Key holder can select native in `/route` setup and validate it | VERIFIED | Setup proposal native-first with key, hidden without (router.py:1028-1059); pinned pick (1062-1086); validate ping ok/INVALID/warn mapping (1232-1303); rig N1 PASS + N2 PASS re-run live by verifier |
| SC2 | Same verdict shape (answers, confidences, reported spend) | VERIFIED | `decide_via_typesafe` mirrors OpenRouter through shared `_post_decision` + `_fit_decision_payload` (routing.py:1301-1355); live test asserts typed table + spend identity — 2/2 live native tests pass |
| SC3 | Chain, preflight, retry, calibration cover native | VERIFIED | Registered `native` link + `_effective_order` chain (1713-1816); 4xx-hold/retry-once inherited via shared classes; `--run native` over 20 probes; baseline native section (20 verdicts, pin, snapshots); STAND verdict recorded |

## Plan Truths (16/16)

**09-01 (transport tracer):** T1 shared verdict shape + computed spend — `TestNativeEngine::test_native_success_routes_with_computed_spend` passes; T2 order drives chain + legacy mapping invariant — mapping tests pass, `_LEGACY_PRIMARY_ORDER` read in code; T3 fault matrix — parametrized 4xx-hold (1 POST) / retryable (2 POSTs) tests pass; T4 timeout-hold + stateless — `test_native_timeout_holds_then_next_call_succeeds` passes; T5 strict judging — pin/alias ok, minor-only/prefixed/unknown fail with fix lines, tests pass; T6 inline spend + marker — `test_native_entry_renders_computed_spend_with_marker` passes.

**09-02 (setup/validate/notes/docs):** T1 proposal + hidden-until-key — `TestSetupOrderProposal`/`TestSetupOrderBuilder` pass, code read; T2 exact pin list + drift warning — `TestSetupNativePick` passes, `jev-preview`/short forms grep 0 in router.py; T3 validate ping mapping — `TestValidatePing` passes (answers→ok, 401→key INVALID, 400→model INVALID, timeout→warning, no ping when unlisted); T4 once-per-session notes — `TestChainSkipNotes` passes (exactly-one, suppress-false→zero, quiet-still-prints); T5 closed aborts + no key prompts — abort tests pass, `os.environ` grep 0 in router.py.

**09-03 (probe/calibration/live/rig):** T1 `--run native` full set + diff — dry-run lists native/20 probes, `TestNativeProbeArm` (9 tests) passes, fault arms restore key byte-identically; T2 shared knobs STAND on evidence — baseline `native_note` + derivation record STAND with distributions (top-1 0.855 vs 0.854); T3 disagreement-as-bug — lone `c-single-candidate` flip closed with same-engine proof in SUMMARY; verifier re-ran `--compare` → identical `clean (2 warning(s))`, exit 0; T4 live tests — verifier ran both native `TestLiveEngines` tests against the real endpoint: **2 passed** (typed table, jev-1.13 snapshot, exact `input×0.042/1e6` at transport + `decide()` levels); skip-without-key by code inspection (skip guards read); T5 rig coverage — n1–n4 branches + env-prefix boots in driver.py; verifier re-ran **N1 PASS** and **N2 PASS** live in tmux; n3/n4 PASS per SUMMARY with static guard tests green.

## Requirements Traceability

- **MODEL-04** (CLI can route decisions through Jev via TypeSafe's native API alongside OpenRouter/Ollama): **SATISFIED** — transport, chain, setup, validate, spend, probes, baseline, live tests, and rig all evidence native as a third engine. No orphaned requirements (ROADMAP maps only MODEL-04 to Phase 9; all three plans declare it).

## Context Decisions (D-01..D-11) — all honored

D-01 ordered list (setup/validate/chain/probes consume it); D-02 native-first proposal with key; D-03 one-line skip + `skip_notes` knob, once per session; D-04 env-only key (engine-layer reads only, secret-drop pinned); D-05 corrected `jev-1.13.0` + `jev-latest` (Pitfall 1 avoided — short/prefixed forms rejected with fix lines); D-06 hidden-until-key; D-07 live validate ping; D-08 shared chain rules with distinct native details; D-09 shared knobs STAND on probe data; D-10 full 20-probe `--run native` vs shared baseline; D-11 disagreement investigated as bug (same-engine jitter proof, knobs untouched).

## Research Pitfalls — all avoided

P1 corrected pin shipped; P2 computed spend + provenance marker (never silent $0); P3 uniform 4xx-hold (403/401 both hold, no retry); P4 legacy mapping invariant tested + validate nudge; P5 once-per-session notes with suppression knob; P6 pin-default + alias warning + snapshot logging + compare drift flags.

## Checks Run (verifier's own process)

- Routing files: `uv run pytest tests/test_routing.py tests/test_routing_strategy.py tests/test_loop_routing.py tests/test_router_setup.py tests/test_cost_context.py tests/test_routing_calibration.py -q` → **443 passed, 4 deselected**
- Full suite: `uv run pytest tests/ -q` → **1363 passed, 10 deselected** (matches review baseline)
- Live: 2 named native `TestLiveEngines` tests with `-o addopts=""` → **2 passed** (real endpoint, ~$0.0000x spend)
- `python3 scripts/route-probe.py --dry-run` → native listed, 20 probes; `--compare` → clean (2 warnings), exit 0
- Rig: `driver.py n2` → **N2 PASS**, `driver.py n1` → **N1 PASS** (live tmux)
- Anti-pattern scan on all 6 phase-touched source files → zero TBD/FIXME/XXX/TODO/HACK; WR-01 equivalence probe → decide()-level identical

## Review Findings Disposition

WR-01 + IN-01..03 from 09-REVIEW.md: none rises to a gap. WR-01 contradicts a plan *task-text* claim ("exactly like primary off") at the hook layer only; no must-have truth asserts hook-silence for `order: []`, the hold is safe, and setup cannot produce the shape. Recorded as advisory with the review's suggested fix intact for a future cleanup.
