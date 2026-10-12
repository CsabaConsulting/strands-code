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
| **Estimated runtime** | ~5s quick / ~41s full (1245 passed, 8 deselected) |

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
| 08-04-03 | 04 | 4 | MODEL-03 | — | no key material in strategy files | e2e | `python3 scripts/uattest/driver.py rN` | ✅ | ⚠️ partial (r1 green; r2/r3/r4 blocked — see BLOCKER) |
| 08-05-01 | 05 | 5 | MODEL-03 | T-08-36 | key at call time; verdicts carry no secrets | unit | `uv run pytest tests/test_routing_calibration.py::TestProbeRunner tests/test_routing_calibration.py::TestProbeComposition tests/test_routing_calibration.py::TestRegressionPath -q` | ✅ audit-added | ✅ green |
| 08-05-02 | 05 | 5 | MODEL-03 | T-08-37 | reviewed baseline; compare fails on drift | unit + manual | `uv run pytest tests/test_routing_calibration.py::TestCalibrationBaseline -q` + manual `--run/--compare` | ✅ audit-added | ✅ green |
| 08-05-03 | 05 | 5 | MODEL-03 | T-08-38 | header-only key; present-but-broken fails loudly | integration | `uv run pytest tests/test_routing.py::TestLiveEngines -m integration -q` | ✅ | ✅ green (2 passed live 2026-10-12) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky/partial*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements (pytest suite predates the rework; no stubs or installs needed).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| r2/r3/r4 live rig runs | MODEL-03 | BLOCKED on loader bug (see below); needs tmux + OPENROUTER_API_KEY + Ollama + Bedrock | Fix BLOCKER, then `python3 scripts/uattest/driver.py r2`, `r3`, `r4` — expect `R2/R3/R4 PASS` |
| Probe live run + compare (`--run openrouter`, `--run local`, `--compare`) | MODEL-03 | Needs live engines + spend; nondeterministic effort reads | `python3 scripts/route-probe.py --run openrouter && python3 scripts/route-probe.py --run local && python3 scripts/route-probe.py --compare` — expect 20+20 verdicts, exit 0 (maintenance contract: re-run on decision-model id change, directive edit, or criteria rewrite) |

*Static contract guards for the rig scenarios (`TestRigScenarioContracts`: py_compile, zero-spend/both-confidences/side-line asserts, levels advertisement, no-key-material) run hermetically in `tests/test_routing_calibration.py`.*

### BLOCKER (escalated, not fixed — auditor is read-only on impl)

**Unquoted YAML-1.1 `off` in candidate `levels` SKIPs the candidate, failing r2/r3/r4 at validate.**
`levels: [auto, off]` parses to `['auto', False]`; `_candidate_skip_reason`
(`strands_code_cli/routing.py:192-197`) rejects non-string lists, so the rig
strategies (and any hand-written strategy using the legitimate `off` effort
level from `_EFFORT_NO_THINKING`) validate INVALID with "no usable candidates".
The engine-key loader already honors YAML-bool intent (`routing.py:258-260`);
the candidate loader does not — an inconsistency. Observed live 2026-10-12:
`python3 scripts/uattest/driver.py r2` → `TIMEOUT waiting for valid`
(transcript `/tmp/uatr8/r2.log` shows INVALID + SKIP lines). r3/r4 share the
identical strategy shape and are deterministically blocked by the same root
cause (not run, to avoid burning live-model time re-proving it). Fix direction:
normalize YAML bools in `levels` to `"on"`/`"off"` strings in the loader (both
`_candidate_skip_reason` and `_parse_candidate` read the raw entry), mirroring
the engine-key handling; no existing test pins the SKIP behavior for bool
levels. Debug iterations: 1 (reproduced live, root-caused via transcript +
loader source).

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (no Wave 0 needed)
- [x] No watch-mode flags
- [x] Feedback latency < 41s (quick ~5s)
- [ ] `nyquist_compliant: true` set in frontmatter — PARTIAL: r2/r3/r4 live runs blocked on the escalated loader bug

**Approval:** partial 2026-10-12 (generic-agent workaround audit)

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
