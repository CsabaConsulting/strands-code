---
phase: "08"
slug: "model-routing-with-decision-models"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: false
wave_0_complete: true
created: "2026-10-11"
validated: "2026-10-12"
audit_mode: "generic-agent workaround (typed gsd-nyquist-auditor dispatch unavailable)"
---

# Phase 08 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Covers the Decision-API rework (plans 08-01…08-05, 13 tasks, MODEL-03).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x via `uv run pytest` |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, `integration` marker deselected by default) |
| **Quick run command** | `uv run pytest tests/test_routing.py tests/test_loop_routing.py tests/test_routing_strategy.py tests/test_cost_context.py tests/test_live_pricing.py tests/test_routing_calibration.py -q` |
| **Full suite command** | `uv run pytest -q` |
| **Estimated runtime** | ~5s quick / ~42s full (1256 passed, 8 deselected) |

---

## Sampling Rate

- **After every task commit:** Run the quick run command above
- **After every plan wave:** Run `uv run pytest -q`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 41 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 1 | MODEL-03 | T-08-21/22/23/24/25 | typed validation; key header-only; ask/directives truncated; single retry | unit | `uv run pytest tests/test_routing.py tests/test_loop_routing.py -q` | ✅ | ✅ green |
| 08-01-02 | 01 | 1 | MODEL-03 | — | secret-drop-on-save; 26-cap; knob ranges | unit | `uv run pytest tests/test_routing_strategy.py tests/test_cost_context.py -q` | ✅ | ✅ green |
| 08-02-01 | 02 | 2 | MODEL-03 | T-08-26 | call-2 scoped to picked levels; bare-name fallback | unit | `uv run pytest tests/test_routing.py -q` | ✅ | ✅ green |
| 08-02-02 | 02 | 2 | MODEL-03 | T-08-27 | fast-path call-2 validated; no zero-call routes | unit | `uv run pytest tests/test_routing.py::TestSingleCandidateFastPath -q` | ✅ | ✅ green |
| 08-02-03 | 02 | 2 | MODEL-03 | T-08-28 | side state truncated; silent holds audited via events | unit | `uv run pytest tests/test_loop_routing.py::TestSideRouting tests/test_loop_routing.py::TestPreTurnHook -q` | ✅ | ✅ green |
| 08-03-01 | 03 | 3 | MODEL-03 | T-08-30 | preflight fails closed; unready skips with zero POSTs | unit | `uv run pytest tests/test_routing.py::TestLocalEngine -q` | ✅ | ✅ green |
| 08-03-02 | 03 | 3 | MODEL-03 | T-08-29/31 | details name engine+code only; pause on all-refused | unit | `uv run pytest tests/test_routing.py::TestEngineChain tests/test_loop_routing.py::TestPreTurnHook -q` | ✅ | ✅ green |
| 08-03-03 | 03 | 3 | MODEL-03 | T-08-32 | 64 KiB cap; ask tightening pre-send; truncation marker | unit | `uv run pytest tests/test_routing.py tests/test_loop_routing.py tests/test_routing_strategy.py -q` | ✅ | ✅ green |
| 08-04-01 | 04 | 4 | MODEL-03 | T-08-33/34 | no key prompt; alias/zero-context dropped | unit | `uv run pytest tests/test_live_pricing.py tests/test_routing_strategy.py -q` | ✅ | ✅ green |
| 08-04-02 | 04 | 4 | MODEL-03 | T-08-35 | decider judged vs decisions catalog; zero network | unit | `uv run pytest tests/test_routing_strategy.py -q` | ✅ | ✅ green |
| 08-04-03 | 04 | 4 | MODEL-03 | — | no key material in strategy files | unit + manual | `uv run pytest tests/test_routing_calibration.py::TestRigScenarioContracts -q` + manual `python3 scripts/uattest/driver.py rN` | ✅ | ✅ static green; live runs human-owned (08-UAT.md #1–2) |
| 08-05-01 | 05 | 5 | MODEL-03 | T-08-36 | key at call time; verdicts carry no secrets | unit | `uv run pytest tests/test_routing_calibration.py::TestProbeRunner tests/test_routing_calibration.py::TestProbeComposition tests/test_routing_calibration.py::TestRegressionPath -q` | ✅ audit-added | ✅ green |
| 08-05-02 | 05 | 5 | MODEL-03 | T-08-37 | reviewed baseline; compare fails on drift | unit + manual | `uv run pytest tests/test_routing_calibration.py::TestCalibrationBaseline -q` + manual `--run/--compare` | ✅ audit-added | ✅ green |
| 08-05-03 | 05 | 5 | MODEL-03 | T-08-38 | header-only key; present-but-broken fails loudly | integration | `uv run pytest tests/test_routing.py::TestLiveEngines -m integration -q` | ✅ | ✅ green (2 passed live 2026-10-12) |
| 08-06-01 | 06 | 6 | MODEL-03 | T-08-39 | YAML-bool levels fold to on/off strings; int still skips | unit | `uv run pytest tests/test_routing_strategy.py::TestBoolLevelNormalization -q` | ✅ | ✅ green (closes escalated BLOCKER) |
| 08-06-02 | 06 | 6 | MODEL-03 | T-08-40 | unhashable choice answers hold (None), never raise | unit | `uv run pytest tests/test_routing.py::TestUnhashableChoiceHolds -q` | ✅ | ✅ green |
| 08-06-03 | 06 | 6 | MODEL-03 | — | cloud probe runs skip local-tag resolution; local still resolves+warms | unit | `uv run pytest tests/test_routing_calibration.py::TestLazyLocalTag -q` | ✅ audit-added | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky/partial*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements (pytest suite predates the rework; no stubs or installs needed).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| r2/r3/r4 live rig runs + r1 regression | MODEL-03 | Human-owned live runs: need tmux + OPENROUTER_API_KEY + Ollama + Bedrock + spend (tracked in 08-UAT.md #1–2) | `python3 scripts/uattest/driver.py r2`, `r3`, `r4`, `r1` — expect `R1/R2/R3/R4 PASS` |
| Probe live run + compare (`--run openrouter`, `--run local`, `--compare`) | MODEL-03 | Human-owned live runs: need live engines + spend; nondeterministic effort reads (tracked in 08-UAT.md #3) | `python3 scripts/route-probe.py --run openrouter && python3 scripts/route-probe.py --run local && python3 scripts/route-probe.py --compare` — expect 20+20 verdicts, exit 0 (maintenance contract: re-run on decision-model id change, directive edit, or criteria rewrite) |

*Static contract guards for the rig scenarios (`TestRigScenarioContracts`: py_compile, zero-spend/both-confidences/side-line asserts, levels advertisement, no-key-material) and the probe runner (`TestProbeRunner`, `TestProbeComposition`, `TestCalibrationBaseline`, `TestRegressionPath`, `TestLazyLocalTag`) run hermetically in `tests/test_routing_calibration.py` (22 tests, green).*

### BLOCKER (RESOLVED — closed by gap plan 08-06, verified by automated tests)

**Unquoted YAML-1.1 `off` in candidate `levels` SKIPPED the candidate, failing r2/r3/r4 at validate.**
`levels: [auto, off]` parsed to `['auto', False]`; `_candidate_skip_reason`
rejected non-string lists, so the rig strategies validated INVALID with
"no usable candidates" (observed live 2026-10-12: `driver.py r2` →
`TIMEOUT waiting for valid`). Gap task 08-06-01 (commit `08d6d4a`) fixed
the loader: `_candidate_skip_reason` accepts bool levels entries and
`_parse_candidate` folds them to `on`/`off` strings (`is True`/`is False`
identity checks, so int levels still skip). Coverage:
`tests/test_routing_strategy.py::TestBoolLevelNormalization` (5 tests:
False→off, True→on, real-YAML load usable, skip-reason accepts bools,
int still skips) — all green. Wiring verified: the validator
(`routing.py:679`) and the loader (`routing.py:213`) share
`_candidate_skip_reason` as the single source of truth, so the fix
propagates to validate end-to-end. Nothing remains blocked; r1–r4 live
runs are human-owned via 08-UAT.md.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (no Wave 0 needed)
- [x] No watch-mode flags
- [x] Feedback latency < 41s (quick ~5s)
- [ ] `nyquist_compliant: true` set in frontmatter — PARTIAL: 0 blocked, 0 escalated; remaining manual-only rows are inherently live-engine runs (tmux + keys + spend) human-owned via 08-UAT.md #1–3

**Approval:** partial 2026-10-12 (generic-agent workaround audit, second pass — nothing blocked)

---

## Validation Audit 2026-10-12

| Metric | Count |
|--------|-------|
| Gaps found | 6 |
| Resolved | 5 |
| Escalated | 1 |

Gaps G1–G5-hermetic resolved by `tests/test_routing_calibration.py` (19 tests,
all green; full suite 1245 passed). Gap G5-live (r2/r3/r4 live runs) escalated
as BLOCKER (YAML-bool `off` loader bug). Fresh live evidence this session: r1
`R1 PASS`, `TestLiveEngines` 2 passed (`-m integration`), full suite green.

## Validation Audit 2026-10-12 (second pass, after 08-06 gap closure)

| Metric | Count |
|--------|-------|
| Gaps found | 2 |
| Resolved | 2 |
| Escalated | 0 |

Prior BLOCKER re-audited: COVERED — `TestBoolLevelNormalization` (5 tests,
green) pins the 08-06-01 loader fix; validator/loader share
`_candidate_skip_reason`, so validate propagates end-to-end. 08-06-02
audited: COVERED — `TestUnhashableChoiceHolds` (3 tests, green); both
decision paths share `_validate_choice_shape`, so the list/dict/tuple
model-path plus list effort-path coverage pins the fix. 08-06-03
audited: one durability gap found — GAP-03 was verified only by
`/tmp/lazy_tag_check.py` scratch plus `--dry-run` (neither committed
nor exercising `cmd_run`'s resolver path). Filled by
`tests/test_routing_calibration.py::TestLazyLocalTag` (3 tests: cloud
run completes with raising resolver + pin recorded, explicit
`local_model` honored on cloud path, local path still resolves + warms
— all green). Adversarial proof: the new cloud test logic fails with
`SystemExit` against the pre-fix `cmd_run` (checked via
`git show eb7db12^:scripts/route-probe.py`), and a negative control
confirms the raising resolver fires on the local path. Full suite:
1256 passed, 8 deselected. Live-engine items (rig r1–r4, probe
run/compare) recorded as Manual-Only, human-owned via 08-UAT.md —
not re-escalated.
