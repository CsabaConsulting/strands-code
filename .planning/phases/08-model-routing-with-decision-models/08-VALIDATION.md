---
phase: "8"
slug: "model-routing-with-decision-models"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
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
| MODEL-03 | Routing off without a configured strategy (D-01); unconfigured behavior byte-identical | unit + regression | `uv run pytest tests/ -q` (full suite: no strategy → no behavior change) | ✅ existing suite | ⬜ pending |
| MODEL-03 | Strategy load: models + directives + descriptors; fail-soft, warn-and-skip, repo wins (D-02/D-03) | unit | `uv run pytest tests/test_routing_strategy.py -x -q` (missing/corrupt/unknown-keys/merge-precedence/validate output) | ❌ Wave 0 (task creates) | ⬜ pending |
| MODEL-03 | Decision prompt contains directives + full candidate table; strict parse; pick applied with routed effort (D-07) | unit | `uv run pytest tests/test_routing.py -x -q` (mocked engines, canned JSON) | ❌ Wave 0 (task creates) | ⬜ pending |
| MODEL-03 | Engine chain: API success short-circuits; API fail → local; both fail → hold-current; offline → local-or-hold (D-08/D-09) | unit | `uv run pytest tests/test_routing.py -x -q` (2× success+failure at API/local/parse/validate seams) | ❌ Wave 0 (task creates) | ⬜ pending |
| MODEL-03 | No heuristic ever picks: malformed JSON/unknown id/empty candidates/timeout → hold (D-08) | unit (negative) | `uv run pytest tests/test_routing.py -x -q` (exact-id match, no fuzzy fallback) | ❌ Wave 0 (task creates) | ⬜ pending |
| MODEL-03 | Pre-turn hook at idle; toggle stickiness; /model warn path (cancel keeps routing, confirm disables) (D-10) | unit | `uv run pytest tests/test_loop_routing.py -x -q` | ❌ Wave 0 (task creates) | ⬜ pending |
| MODEL-03 | Transcript note every routed ask (model/why/cost) + suppression flag; /cost routing section (D-11/D-12) | unit | `uv run pytest tests/test_loop_routing.py -x -q` + cost-context assertions | ❌ Wave 0 (task creates) | ⬜ pending |
| MODEL-03 | /btw side asks route through same strategy, side-flagged (D-04); guided setup + validate slash (D-13) | unit | `uv run pytest tests/test_loop_routing.py tests/test_routing_strategy.py -x -q` | ❌ Wave 0 (task creates) | ⬜ pending |
| MODEL-03 | Live decision call against OpenRouter/Ollama | integration (gated) | `uv run pytest -m integration -q` (env-key gated skips; stdlib stub HTTP server for local) | ❌ Wave 0 (task creates) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_routing.py` — NEW: prompt build, strict parse, engine chain order, hold-current transitions, negative no-heuristic tests
- [ ] `tests/test_routing_strategy.py` — NEW: strategy file load/merge/validate + guided-setup coverage
- [ ] `tests/test_loop_routing.py` — NEW: pre-turn hook, toggle stickiness, /model warn path, transcript lines, side-flag routing
- [ ] Integration tests env-gated (no live OpenRouter key in CI → clean skip; Ollama via stub HTTP server or URL-mocked urlopen)
- [ ] Descriptors as user-editable snapshot schema with `pulled:` date (live benchmark pull is stretch, not gate)

*Existing infrastructure covers the runner/markers; Wave 0 creates the three routing test files above.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Guided setup flow against live OpenRouter catalog | MODEL-03 | Needs real key + network; catalog content varies | Run setup with a real key, confirm enumerated models match `/models`, complete a strategy |
| Local-engine cold start via real Ollama daemon | MODEL-03 | Daemon timing/behavior unprobed in CI | `ollama serve`, route an ask with local engine, observe latency + pick |
| End-to-end routed turn on Bedrock | MODEL-03 | Live spend + real model switch | Configure strategy, ask, confirm routed model serves the turn and transcript note matches |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
