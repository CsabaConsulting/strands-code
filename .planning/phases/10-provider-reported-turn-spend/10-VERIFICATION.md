---
phase: 10-provider-reported-turn-spend
verified: 2026-10-12T23:39:04Z
status: gaps_found
score: 14/17 must-haves verified
covered_files:
  - .planning/phases/10-provider-reported-turn-spend/10-01-PLAN.md
  - .planning/phases/10-provider-reported-turn-spend/10-02-PLAN.md
  - .planning/phases/10-provider-reported-turn-spend/10-03-PLAN.md
  - .planning/phases/10-provider-reported-turn-spend/10-01-SUMMARY.md
  - .planning/phases/10-provider-reported-turn-spend/10-02-SUMMARY.md
  - .planning/phases/10-provider-reported-turn-spend/10-03-SUMMARY.md
  - .planning/phases/10-provider-reported-turn-spend/10-CONTEXT.md
  - .planning/phases/10-provider-reported-turn-spend/10-RESEARCH.md
  - .planning/phases/10-provider-reported-turn-spend/10-REVIEW.md
  - strands_code_cli/reported_cost.py
  - strands_code_cli/cost_context.py
  - strands_code_cli/loop.py
  - strands_code_cli/btw.py
  - strands_code_cli/main.py
  - strands_code_cli/model_switch.py
  - tests/test_reported_cost.py
  - tests/test_cost_context.py
  - tests/test_model_switch.py
behavior_unverified: 0
dispatch: generic-agent workaround — typed gsd-verifier dispatch unavailable; results labeled accordingly
gaps:
  - id: G-01
    root: review CR-01, confirmed by independent reproduction
    failing_path: main-turn drain via record_turn_metrics(model=agent)
    files:
      - strands_code_cli/loop.py:1914
      - strands_code_cli/loop.py:2338
      - strands_code_cli/loop.py:278
---

# Phase 10: Provider-Reported Turn Spend Verification Report

**Phase Goal:** `/cost` shows provider-reported actuals for main turns where the provider supplies them, estimates elsewhere
**Verified:** 2026-10-12T23:39:04Z
**Status:** gaps_found
**Dispatch:** generic-agent workaround (typed gsd-verifier dispatch unavailable); results labeled accordingly.

## Goal Achievement

### Observable Truths

Must-haves merged from ROADMAP success criteria (non-negotiable) plus PLAN frontmatter truths. 10-01 truth 1 restates roadmap SC-1 and is deduped into it per the merge rule.

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC-1: Main turns served via OpenRouter show the provider-reported USD cost in the usage line and `/cost` | ✗ FAILED | G-01: production call `record_turn_metrics(..., model=agent)` (loop.py:1914,2338) drains `None`; row stores no `reported_cost`, usage line renders bare `$0.00`. Reproduced live (see Gaps). |
| 2 | SC-2: Bedrock and offline turns keep the tokens x rate estimate with provenance labeled | ✓ VERIFIED | `wrap_for_openrouter` returns non-OpenRouter ids identical (reported_cost.py:102-103); `TestBedrockOfflineParity` goldens green, proven byte-identical against pre-phase module. |
| 3 | SC-3: Mixed sessions total actuals and estimates without double counting | ✓ VERIFIED | Actual-wins branches all `is not None` (cost_context.py:278,306); lane accumulation tested incl. present-zero and 2-row `$0.0034` total. Caveat: mechanism correct; main-turn actuals are starved by G-01 (side/routing actuals still blend correctly). |
| 4 | Bare dollar amounts stay estimate-only; only provider-reported values carry the actual marker (D-03) | ✓ VERIFIED | Estimate cells bare (cost_context.py:288), marker only on `is not None` branches (179,235,282); estimate-only reports assert zero marker occurrences. |
| 5 | OpenRouter turn with no reported cost falls back to the estimate; tokens-only when no price exists (D-05, D-06) | ✓ VERIFIED | `else` branch keeps `cost_for` path byte-identical; no-price rows append no money cell (cost_context.py:283-291); both pinned by tests. |
| 6 | A turn contributes either its reported actual or its estimate, never both; present 0.0 is a marked actual zero (D-09) | ✓ VERIFIED | One lane per row (cost_context.py:277-291); `0.0` renders `$0.0000 actual` and contributes 0.0; any-rule drain `sum_reported_costs` (reported_cost.py:76-83). |
| 7 | Non-OpenRouter model ids pass through wrapping untouched (D-07) | ✓ VERIFIED | Identity gate (reported_cost.py:102-103); `is`-comparison tests for bedrock + plain openai ids green. |
| 8 | Mixed sessions show a blended headline total plus an actual/estimated split beneath it (D-08) | ✓ VERIFIED | Blended Total + `  (actual $X + estimated $Y)` iff both lanes non-empty (cost_context.py:323-327); exact-string test green. Same G-01 supply caveat as #3. |
| 9 | Routing/decision spend lines carry the same actual marker and fold into the actuals lane (D-04, D-10) | ✓ VERIFIED | Marker-iff-reported (cost_context.py:233-236); routing fold into `total_actual` (306-311); marked `$0.0006 actual` test green. |
| 10 | Sessions with no actuals show today's plain total with no split line (D-11) | ✓ VERIFIED | Split guarded by `has_actual and has_estimated` (cost_context.py:326); estimate-only and actuals-only no-split tests green. |
| 11 | Bedrock and offline turns render byte-identical to today (D-07) | ✓ VERIFIED | Full-report Bedrock golden + usage-line pin + offline golden, diffed against pre-phase module; suite green. |
| 12 | Session totals count each turn exactly once with actual winning over estimate (D-09) | ✓ VERIFIED | Presence-flag lanes (`has_actual`/`has_estimated`), single accumulation per row + reported routing spend only; derived zeros never open the lane. |
| 13 | Side-agent (btw) turns on OpenRouter capture with a fresh wrapper per build, never sharing the main agent's instance | ✓ VERIFIED | `fresh_side_model` shallow-copy + emptied list (reported_cost.py:114-125), replay-path call (btw.py:421-428), routed-spawn wrap (loop.py:753-755); independence test (drain one, other intact, distinct objects) green. |
| 14 | Sessions starting on an OpenRouter model capture reported cost from the first turn without a manual switch | ✗ FAILED | Initial-build wrap itself is correct (main.py:174-190, test-pinned), but captured costs are never drained on the main path — same root cause G-01. Observable outcome fails. |
| 15 | Reported spend from main and side turns never double counts and never misattributes across agents (D-09) | ✓ VERIFIED | Drain-once at `_finish_btw_turn` carried on the pending 4-tuple (loop.py:373-376); explicit-reported-wins `_UNSET` rule blocks re-drain (loop.py:313-316); all 4-tuple producer/consumers consistent (loop.py:374,636,1051,2327; btw.py:305). G-01 causes silent loss, not misattribution — no path drains the orphaned main list. |
| 16 | Effort/thinking configuration survives wrapping on routed picks | ✓ VERIFIED | In-place `__class__` promotion preserves all attributes (reported_cost.py:108); config-equality + `apply_switch` effort-forwarding tests green. |
| 17 | Live OpenRouter turn captures a real reported cost end to end; skips cleanly otherwise; deselected from the default suite | ? UNCERTAIN | Skip + deselect observed: integration-marked (test_reported_cost.py:410), `SKIPPED: litellm extra not installed` reproduced here. Positive-float assertion never executed (no litellm extra in this env). Needs keyed run — see Human Verification. |

**Score:** 14/17 truths verified (2 failed sharing one root cause, 1 uncertain awaiting a keyed live run)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `strands_code_cli/reported_cost.py` | Capture mixin, wrap gate, drain helpers | ✓ EXISTS + SUBSTANTIVE | 126 lines; mixin, `take_reported_costs`, any-rule sum, gate, fresh-side helper; fail-soft capture. Consumer-side defect is in loop.py call sites, not this module. |
| `strands_code_cli/cost_context.py` | Marked usage line, actual-wins rows, blended total + split, routing marker | ✓ EXISTS + SUBSTANTIVE | Marker/actual-wins/lanes/split all `is not None`-guarded; display-only posture kept. |
| `strands_code_cli/loop.py` | Per-turn drain, 4-tuple carrier, routed side wrap | ✓ EXISTS + SUBSTANTIVE | Drain helper, `_UNSET` rule, side drain, 4-tuple set all correct — except the two main-turn `model=agent` arguments (G-01). |
| `strands_code_cli/model_switch.py` | `apply_switch` wrap | ✓ EXISTS + SUBSTANTIVE | Wrap between resolve and `agent.model` assignment (line 656). Unguarded — see WR-01. |
| `strands_code_cli/main.py` | Initial-build wrap | ✓ EXISTS + SUBSTANTIVE | Post-construction promotion with fail-soft guard (174-190); stash keeps the model string. |
| `strands_code_cli/btw.py` | Fresh-copy on replay path | ✓ EXISTS + SUBSTANTIVE | `fresh_side_model` on kwargs model (421-428); 4-tuple docstring (305). |
| `tests/test_reported_cost.py` | Hermetic capture/drain/gate/tracer + wrap-scope + live tests | ✓ EXISTS + SUBSTANTIVE | 27 tests incl. tracer, side carrier, explicit-wins, initial wrap, live proof. No agent-shaped main-drain test — the hole that masks G-01. |
| `tests/test_cost_context.py` | Reported-row, blended-total, parity tests | ✓ EXISTS + SUBSTANTIVE | `TestReportedRows`, `TestBlendedTotalsAndSplit`, `TestBedrockOfflineParity` all green. |
| `tests/test_model_switch.py` | Wrap-scope tests | ✓ EXISTS + SUBSTANTIVE | `TestReportedWrapScope` (openrouter wraps, others identical, effort forwarding) green. |

**Artifacts:** 9/9 exist and are substantive (1 with a defective call shape at its call sites)

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `wrap_for_openrouter` | capture mixin | in-place `__class__` promotion | ✓ WIRED | reported_cost.py:108-111; effort/caching/client_args preserved. |
| wrapped model | `record_turn_metrics` (main path) | `model=` drain argument | ✗ NOT WIRED | loop.py:1914 + 2338 pass `model=agent` (the Agent); `take_reported_costs` lives on `agent.model`. G-01. |
| drain | `reported_cost` row key | `_drain_reported_cost` + row store | ✓ WIRED | loop.py:278-288, 313-335; drain-first ordering keeps failed turns from bleeding. |
| row key | marked render | `usage_line` + `cost_report` row loop | ✓ WIRED | cost_context.py:178-179, 277-282; actual-wins throughout. |
| lanes | blended Total + split | `total_actual`/`total_estimated` + presence flags | ✓ WIRED | cost_context.py:264-267, 323-327. |
| side build | per-side-turn drain | `fresh_side_model` + `_finish_btw_turn` drain + pending 4-tuple | ✓ WIRED | btw.py:428, loop.py:373-376; all consumers unpack 4 elements. |
| routed side spawn | fresh wrapper | `wrap_for_openrouter` inside resolve try | ✓ WIRED | loop.py:752-755; failure holds to live model like any resolve failure. |
| initial build | promoted model | post-`create_harness` wrap | ✓ WIRED | main.py:174-190. Downstream main drain broken by G-01. |

**Wiring:** 7/8 connections verified

## Requirements Coverage

| Requirement | Status | Blocking Issue |
|-------------|--------|----------------|
| MODEL-05: `/cost` shows provider-reported actuals for main turns where supplied (OpenRouter), estimates elsewhere, without double counting | ✗ BLOCKED | G-01: main-turn actuals never reach rows/display in production. Side/routing actuals, estimates, fallbacks, and no-double-count logic all work. |

**PLAN requirements cross-reference:** 10-01, 10-02, and 10-03 each declare `MODEL-05` — the single ID in scope. REQUIREMENTS.md maps MODEL-05 to Phase 10 (Pending). No orphaned IDs: no other requirement is mapped to this phase and no plan claims an ID outside REQUIREMENTS.md.

**Coverage:** 0/1 requirements satisfied

## Context Decisions (D-01..D-11)

| Decision | Honored? | Evidence |
|----------|----------|----------|
| D-01 inline marker on rows | Yes (display logic) | `, $X actual` (cost_context.py:282); exact-string tests. Starved of main-turn data by G-01. |
| D-02 usage line same marking | Yes (display logic) | ` $X actual` (cost_context.py:179); tracer asserts `$0.00 actual`. Same supply caveat. |
| D-03 bare `$` = estimate | Yes | Bare cells (cost_context.py:288, 236); zero-marker assertions on estimate-only reports. |
| D-04 routing lines same marker | Yes | Marker-iff-reported (cost_context.py:233-236). |
| D-05 absent cost → estimate fallback | Yes | Unchanged `cost_for` path (cost_context.py:283-291). |
| D-06 no price → tokens-only | Yes | No money cell appended when `cost_for` is None. |
| D-07 Bedrock/offline untouched | Yes | Identity gate + byte-parity goldens. |
| D-08 blended total + split | Yes | cost_context.py:323-327; exact split-string test. |
| D-09 actual-wins, never both; 0.0 = marked actual | Yes | `is not None` everywhere; `$0.0000 actual` pinned. |
| D-10 routing spend in total as actuals | Yes | Actuals-lane fold (cost_context.py:306-311). |
| D-11 no actuals → plain total, no split | Yes | `has_actual and has_estimated` guard + symmetric restraint. |

All display decisions are correctly implemented; D-01/D-02 fail observably on main turns only because G-01 starves them of data.

## Research Pitfalls

| Pitfall | Avoided? | Evidence |
|---------|----------|----------|
| P1 shared wrapper across main+btw | Yes | `fresh_side_model` per build + per-spawn wrap; independence test green. |
| P2 multi-cycle turns need summed cost | Yes | Any-rule `sum_reported_costs`; multi-cycle test green. |
| P3 mid-turn switch strands costs | Broken by G-01 | Drain-from-serving-instance intent defeated: main drains address the Agent, never the serving model. |
| P4 falsy-zero collapsing | Yes | `is not None` on every actual-wins branch; int-0/0.0 pinned. |
| P5 effort dropped on pre-built instances | Yes | In-place promotion; effort-survival tests green. |
| P6 `.cost` assumed present | Yes | `getattr` + bool-safe extractor + fail-soft capture; hostile-numerics test green. |
| Generation-id lookup transport | Correctly absent | Inline `usage.cost` only; no HTTP/lookup code in the capture path. |

## Code Review Rulings (10-REVIEW.md)

Each of the 1 critical + 4 warnings + 3 infos ruled explicitly against source. I re-verified every item rather than trusting the review text.

| ID | Severity | Ruling | Basis |
|----|----------|--------|-------|
| CR-01 | Critical | **CONFIRMED — BLOCKER (G-01)** | Reproduced independently: `hasattr(Agent, 'take_reported_costs')` is False on the installed SDK (no `__getattr__` on the class); production-shaped `record_turn_metrics(..., model=agent)` stores no `reported_cost` and renders bare `$0.00`, while unit-shaped `model=<wrapped>` stores `0.0024` and renders `$0.00 actual`. Undrained costs accumulate on `agent.model` (`[0.0024]` leftover after the call). No test passes an agent-shaped object as `model=` (the one agent-shaped double, test_reported_cost.py:262, exercises the correct side path). |
| WR-01 | Warning | **Confirmed as written — warning, not blocking** | `wrap_for_openrouter` call at model_switch.py:656 sits outside any `try/except`, and the caller (`apply_model_action`, loop.py:1290-1326) has no guard around it — unlike main.py:174-190 and loop.py:752-755. A promotion raise would break a working switch (display-only posture). No observed failure; harness-resolved instances promote cleanly. Recommend the review's choke-point guard. |
| WR-02 | Warning | **Confirmed as written — warning, not blocking** | `copy.copy(model)` at reported_cost.py:124 is unguarded; a copy failure would raise out of `build_btw_agent` and break a side turn. No observed failure. Recommend try/except returning the input unchanged. |
| WR-03 | Warning | **Confirmed as written — warning, not blocking** | `_extract_cost` (reported_cost.py:22-28) accepts NaN/Inf (`isinstance` passes; JSON transports both); one NaN cycle would render `$nan actual` and poison `total_actual` for the session. Follows directly from the code. Recommend `math.isfinite`. |
| WR-04 | Warning | **Confirmed as written — warning, test-only** | Live test asserts `reported > 0` (tests/test_reported_cost.py:453-455), which fails a legitimate present-`0.0` actual that D-09 blesses. Plan-mandated text, so a plan/test inconsistency, not an implementation slip. Recommend `>= 0`. |
| IN-01 | Info | **Confirmed as written — no action** | Explicit branch stores verbatim (loop.py:314-316); a non-numeric explicit value would raise in `usage_line` formatting after row append. Unreachable from production callers (all pass drained `float \| None`). Optional defense-in-depth only. |
| IN-02 | Info | **Confirmed as written — no action** | No `isinstance(resolved, LiteLLMModel)` check before promotion (reported_cost.py:108). All current call sites pass matching pairs (harness `litellm/` ids always resolve to `LiteLLMModel`). Future-proofing only. |
| IN-03 | Info | **Confirmed — accepted tradeoff, no action** | Sub-cent actuals render `$0.00 actual` on the 2-decimal usage line (cost_context.py:179). Plan-locked and test-pinned; `/cost` rows show the true 4-decimal value. |

## Prohibitions (must-NOT items, all 3 plans)

All three plans carry the same three prohibitions with `status: unresolved` and no `verification` tier. Treated as judgment-tier: autonomous verdicts below are NON-AUTHORITATIVE — `unverified-prohibition — human review recommended` for each.

| # | Prohibition | Judge verdict | Basis |
|---|-------------|---------------|-------|
| P1 | MUST NOT present an estimated dollar amount as a provider-reported actual | Holds on all exercised paths (flagged) | Every marker branch is `is not None`-gated (cost_context.py:178,234,278,307); bare-`$` paths carry no marker; estimate-only zero-marker tests green. |
| P2 | MUST NOT attribute one turn's/agent's spend to another | Holds on all exercised paths (flagged) | Fresh wrapper per side build, per-turn drains, drain-once tuple carrier, explicit-wins rule. G-01 loses main-turn data rather than misattributing it (orphaned list is never drained anywhere). |
| P3 | MUST NOT let cost display gate/deny/redirect/cut short any turn | Holds on exercised paths with residual risk (flagged) | Capture and drains are fail-soft; display is pure. Residual risk is exactly WR-01/WR-02 (unguarded wrap/copy on behavior paths) — no observed failure. |

## Anti-Patterns Found

Debt-marker scan over all six touched source files: no `TBD`/`FIXME`/`XXX`/`TODO`/`HACK` (the only `PLACEHOLDER` hits are the pre-existing `_MEDIA_PLACEHOLDER_RE` media-tag regex in model_switch.py:207,257 — unrelated to this phase). No stub returns, no hardcoded empty data on render paths, no `console.log`-only handlers.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| strands_code_cli/loop.py | 1914, 2338 | `model=agent` drain argument (test/prod shape mismatch) | 🛑 Blocker | G-01: main-turn capture silently dead in production. |
| strands_code_cli/model_switch.py | 656 | unguarded wrap (WR-01) | ⚠️ Warning | Promotion raise would break a switch. |
| strands_code_cli/reported_cost.py | 124 | unguarded `copy.copy` (WR-02) | ⚠️ Warning | Copy failure would break a side turn. |
| strands_code_cli/reported_cost.py | 22-28 | no finiteness check (WR-03) | ⚠️ Warning | NaN/Inf would poison session totals. |
| tests/test_reported_cost.py | 453-455 | `reported > 0` live assertion (WR-04) | ⚠️ Warning | Fails legitimate 0.0 actuals; test-only. |

**Anti-patterns:** 5 found (1 blocker, 4 warnings)

## Behavioral Spot-Checks

| Behavior | Command / probe | Result | Status |
|----------|-----------------|--------|--------|
| Production main-turn drain (`model=agent`, loop.py:1914/2338 shape) | `record_turn_metrics(_Summary(12,1), MID, rows, model=agent)` with 0.0024 captured on `agent.model` | Row has NO `reported_cost`; usage `'12 (0%) $0.00'`; `[0.0024]` left undrained | ✗ FAIL (G-01) |
| Unit main-turn drain (`model=<wrapped>`, test shape) | Same with `model=model` | Row stores `0.0024`; usage `'12 (0%) $0.00 actual'` | ✓ PASS |
| Installed SDK delegation | `hasattr(Agent, 'take_reported_costs')` | `False`; no `__getattr__` on the class | ✓ PASS (confirms mechanism) |
| Phase test files | `uv run pytest tests/test_reported_cost.py tests/test_cost_context.py tests/test_model_switch.py -q` | 194 passed, 1 deselected | ✓ PASS |
| Full suite (phase gate) | `uv run pytest tests/ -q` | 1408 passed, 11 deselected, 0 failures | ✓ PASS |
| Live-test skip behavior | `pytest tests/test_reported_cost.py::TestLiveReportedCost -q -rs -m integration` | `SKIPPED: litellm extra not installed` | ✓ PASS (skip path; positive path unverified) |

## Human Verification Required

### 1. Live OpenRouter positive-path proof
**Test:** With `OPENROUTER_API_KEY` set and the litellm extra installed, run `uv run pytest tests/test_reported_cost.py::TestLiveReportedCost -q -rs -m integration`.
**Expected:** Pass with a drained positive float and an actual-marked row (after applying the WR-04 `>= 0` fix, a legitimate `0.0` must also pass).
**Why human:** Requires credentials + network + an optional extra absent from this environment; the assertion never executed here.

### 2. Prohibition review (P1, P2, P3)
**Test:** Review the three must-NOT prohibitions above against the cited code and confirm each `status: unresolved` may move to resolved.
**Expected:** Explicit human acceptance per prohibition (or a blocking finding).
**Why human:** Judgment-tier items require explicit human resolution; autonomous verdicts are non-authoritative.

### 3. Post-fix main-turn capture (after G-01 is fixed)
**Test:** Run one real OpenRouter main turn and check the post-turn usage line and `/cost` row show the marked actual.
**Expected:** `$X actual` on both, matching the provider's reported cost for the turn.
**Why human:** End-to-end provider behavior; hermetic tests cannot see the real stream.

## Gaps Summary

### Critical Gaps (Block Progress)

1. **G-01: Main-turn drain passes the Agent instead of its model — main-path capture silently dead**
   - Failing production path: `run_loop` (loop.py:2337-2338) and `_drain_revise_rounds` (loop.py:1913-1914) call `record_turn_metrics(..., model=agent)`. `_drain_reported_cost` (loop.py:278-288) resolves `take_reported_costs` via `getattr(model, ...)` with fail-soft to `None`. The mixin lives on `agent.model`; the installed SDK `Agent` has no `take_reported_costs` and no `__getattr__` delegation (verified: `hasattr(Agent, 'take_reported_costs')` is `False`). Every main-turn drain yields `None`.
   - Expected vs actual: expected — an OpenRouter main turn with `usage.cost` 0.0024 stores `reported_cost: 0.0024` and renders `$0.00 actual` (as the unit-shaped call does); actual — row omits the key, usage renders bare `$0.00`, and the 0.0024 accumulates undrained on `agent.model` (`_reported_costs == [0.0024]` after the call).
   - Impact: Phase-goal-breaking. Roadmap SC-1 and the 10-01 headline truth fail on the only path that matters (real main turns); 10-03's initial-build truth fails observably for the same reason. A naive fix that merely starts draining would misattribute the session's accumulated spend to one turn (D-09 violation) — the fix must drain-and-discard once, then drain per turn.
   - Masking: all 27 tests in `test_reported_cost.py` pass the wrapped model directly (e.g. lines 212, 224); no test exercises the agent-shaped production call.
   - Fix: pass `model=getattr(agent, "model", None)` at both sites (optionally plus a defensive `model.model` fallback inside `_drain_reported_cost`); add a regression test passing an agent-shaped `SimpleNamespace(model=wrapped)` to `record_turn_metrics`; drain-and-discard any pre-fix accumulation once. See fix plan 10-04.

### Non-Critical Gaps (Can Defer)

None — WR-01..WR-04 are warnings with no observed failure; IN-01..IN-03 need no action. Recommend folding WR-01/WR-02/WR-03/WR-04 into the 10-04 fix round since it touches the same files (small, low-risk hardening), but they do not block the phase goal on their own.

## Recommended Fix Plans

### 10-04-PLAN.md: Main-drain repair + drain-path hardening

**Objective:** Make main OpenRouter turns capture provider-reported cost in production (close G-01) and harden the drain path per review warnings.

**Tasks:**
1. Fix the main-turn drain argument at loop.py:1914 and loop.py:2338 to `getattr(agent, "model", None)` (plus optional `model.model` fallback in `_drain_reported_cost`); drain-and-discard any accumulated pre-fix costs once to avoid one-turn misattribution. Add the agent-shaped regression test (must fail before, pass after).
2. Harden per warnings: choke-point try/except in `wrap_for_openrouter` (WR-01), guarded `copy.copy` in `fresh_side_model` (WR-02), `math.isfinite` in `_extract_cost` with a NaN/Inf test (WR-03), `>= 0` live assertion (WR-04).
3. Verify: new regression test green, full suite green (`uv run pytest tests/ -q`), and a production-shaped probe (`model=agent`) storing `reported_cost` with a marked usage line.

**Estimated scope:** Small

---

## Verification Metadata

**Verification approach:** Goal-backward (roadmap success criteria + PLAN frontmatter must-haves, deduped)
**Must-haves source:** ROADMAP.md Phase 10 success criteria + 10-01/10-02/10-03 PLAN.md frontmatter
**Automated checks:** 5 passed, 1 failed (production-path drain probe)
**Human checks required:** 3 (live positive path, prohibition acceptance, post-fix end-to-end)
**Total verification time:** ~25 min

---
*Verified: 2026-10-12T23:39:04Z*
*Verifier: the agent (gsd-verifier via generic-agent workaround)*
