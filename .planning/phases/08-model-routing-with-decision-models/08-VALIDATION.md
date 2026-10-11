---
phase: "8"
slug: "model-routing-with-decision-models"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-10-11"
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Seeded from `08-RESEARCH.md` §Validation Architecture (generic-agent workaround for `gsd-phase-researcher`; no plan task IDs exist yet, so rows are Req-ID → behavior).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 (locked in `uv.lock`) |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, `integration` marker deselected by default) |
| **Quick run command** | `uv run pytest tests/test_routing.py tests/test_routing_strategy.py tests/test_loop_routing.py -x -q` |
| **Full suite command** | `uv run pytest -q` |
| **Estimated runtime** | ~10 seconds (quick subset; full suite ~40s per repo baseline) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_routing.py tests/test_routing_strategy.py tests/test_loop_routing.py -x -q`
- **After every plan wave:** Run `uv run pytest -q`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Req ID | Behavior (D-lock) | Test Type | Automated Command | File Exists | Status |
|--------|-------------------|-----------|-------------------|-------------|--------|
| MODEL-03 | Routing off without a configured strategy (D-01); unconfigured behavior byte-identical | unit + regression | `uv run pytest tests/ -q` (full suite: no strategy → no behavior change) | ✅ existing suite | ✅ green (1070 passed; R3 off-leg proves toggle live) |
| MODEL-03 | Strategy load: models + directives + descriptors; fail-soft, warn-and-skip, repo wins (D-02/D-03) | unit | `uv run pytest tests/test_routing_strategy.py -x -q` (missing/corrupt/unknown-keys/merge-precedence/validate output) | ✅ TestStrategyLoad | ✅ green |
| MODEL-03 | Decision prompt contains directives + full candidate table; strict parse; pick applied with routed effort (D-07) | unit | `uv run pytest tests/test_routing.py -x -q` (mocked engines, canned JSON) | ✅ TestRoutingPrompt+TestParsePick | ✅ green |
| MODEL-03 | Engine chain: API success short-circuits; API fail → local; both fail → hold-current; offline → local-or-hold (D-08/D-09) | unit | `uv run pytest tests/test_routing.py -x -q` (2× success+failure at API/local/parse/validate seams) | ✅ TestEngineChain+TestLocalEngine | ✅ green |
| MODEL-03 | No heuristic ever picks: malformed JSON/unknown id/empty candidates/timeout → hold (D-08) | unit (negative) | `uv run pytest tests/test_routing.py -x -q` (exact-id match, no fuzzy fallback) | ✅ TestParsePick negatives | ✅ green |
| MODEL-03 | Pre-turn hook at idle; toggle stickiness; /model warn path (cancel keeps routing, confirm disables) (D-10) | unit | `uv run pytest tests/test_loop_routing.py -x -q` | ✅ TestPreTurnHook+TestRoutingToggle | ✅ green |
| MODEL-03 | Transcript note every routed ask (model/why/cost) + suppression flag; /cost routing section (D-11/D-12) | unit | `uv run pytest tests/test_loop_routing.py -x -q` + cost-context assertions | ✅ TestCostRouting | ✅ green |
| MODEL-03 | /btw side asks route through same strategy, side-flagged (D-04); guided setup + validate slash (D-13) | unit + rig | `uv run pytest tests/test_loop_routing.py tests/test_routing_strategy.py -x -q` + `driver.py r4`/`r1` | ✅ TestSideRouting+TestRouteSetup+TestRouteValidate | ✅ green (R1+R4 PASS live) |
| MODEL-03 | Live decision call against OpenRouter/Ollama | integration (gated) | `uv run pytest -m integration -q` (env-key gated skips; stdlib stub HTTP server for local) | ✅ TestLiveEngines (stub + 2 live) | ✅ green (both live tests pass; R2/R3 double-prove) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_routing.py` — NEW: prompt build, strict parse, engine chain order, hold-current transitions, negative no-heuristic tests
- [x] `tests/test_routing_strategy.py` — NEW: strategy file load/merge/validate + guided-setup coverage
- [x] `tests/test_loop_routing.py` — NEW: pre-turn hook, toggle stickiness, /model warn path, transcript lines, side-flag routing
- [x] Integration tests env-gated (no live OpenRouter key in CI → clean skip; Ollama via stub HTTP server or URL-mocked urlopen)
- [x] Descriptors as user-editable snapshot schema with `pulled:` date (live benchmark pull is stretch, not gate)

*Existing infrastructure covers the runner/markers; Wave 0 creates the three routing test files above.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Served turn on a setup-picked catalog id | MODEL-03 | Catalog ids vary; servability of an arbitrary `openrouter/*` pick is product exploration, not a fixed behavior | `/route setup`, pick a candidate, route an ask, confirm the picked model serves (mechanism proven by R1+R3 on bedrock ids) |

(Retired 2026-10-11 — now scripted in `scripts/uattest/driver.py`: guided setup vs live catalog → R1 PASS; local-engine cold start → R2 PASS 16.1s `via local`; e2e routed turn on Bedrock → R3 PASS; live side-flagged /btw decision → R4 PASS. Transcripts in `/tmp/uatr8/`, never committed.)

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validate-phase audit 2026-10-11 (inline; typed gsd-nyquist-auditor dispatch unavailable in this runtime — generic-agent workaround precedent per phase summaries)

---

## Validation Audit 2026-10-11

| Metric | Count |
|--------|-------|
| Gaps found | 1 |
| Resolved | 1 |
| Escalated | 0 |

Gap G-08-V1 (side-spawn routing held every stay pick): `_route_side_spawn`
resolved unconditionally through `resolve_model` with the raw pick effort,
so live junk efforts (`?`, `-`) on same-model picks raised into a silent
hold — the main hook's no-op fast path was never mirrored. Fixed by gating
on `pick.model != current_model` plus `validate_routed_effort` (loop.py),
locked by `test_same_model_pick_skips_resolve_and_still_routes` and
`test_unreasoned_effort_holds_to_parent_silently`, proven live by rig R4
(`Routed (btw)` + side-flagged `/cost` entry). Suite: 1070 passed,
8 deselected; integration 7/7 (incl. `OLLAMA_LIVE` daemon test).
