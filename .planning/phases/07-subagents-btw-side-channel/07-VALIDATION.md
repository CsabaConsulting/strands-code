---
phase: "7"
slug: "subagents-btw-side-channel"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-06"
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Seeded from `07-RESEARCH.md` §Validation Architecture (generic-agent workaround for `gsd-phase-researcher`; no plan task IDs exist yet, so rows are Req-ID → behavior).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 (locked in `uv.lock`) |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, `integration` marker deselected by default) |
| **Quick run command** | `uv run pytest tests/test_btw.py tests/test_steering.py tests/test_policy_gate.py tests/test_broker.py -x -q` |
| **Full suite command** | `uv run pytest -q` |
| **Estimated runtime** | ~10 seconds (quick subset; full suite per repo baseline) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_btw.py tests/test_steering.py tests/test_policy_gate.py tests/test_broker.py -x -q`
- **After every plan wave:** Run `uv run pytest -q`
- **Before `$gsd-verify-work`:** Full suite green + live parallel smoke (main + btw + one approval each) before `$gsd-verify-work`
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Req ID | Behavior (D-lock) | Test Type | Automated Command | File Exists | Status |
|--------|-------------------|-----------|-------------------|-------------|--------|
| LOOP-03 | Idle `/btw <q>` runs a normal inline turn (D-01) | unit | `uv run pytest tests/test_router_btw.py -x -q` (dispatch returns `("agent", rest)`) | ❌ Wave 0 (task creates) | ⬜ pending |
| LOOP-03 | Mid-turn `/btw` spawns; other slashes still refused (D-02) | unit | `uv run pytest tests/test_steering.py -x -q` (third reader outcome; refusal text unchanged) | ✅ extend existing | ⬜ pending |
| LOOP-03 | Main never pauses for btw; input free; second btw queues (D-03/D-04/D-10) | unit (doubles) + integration (live) | `uv run pytest tests/test_btw.py -x -q` + live parallel marker test | ❌ Wave 0 (task creates) | ⬜ pending |
| LOOP-03 | Tagged `[main]`/`[btw]` prompts; no second HITL (D-06) | unit | `uv run pytest tests/test_policy_gate.py tests/test_broker.py -x -q` (agent-keyed context, namespaced batch, single construction) | ✅ extend existing | ⬜ pending |
| LOOP-03 | Fenced btw block incl. error shape; no torn interleavings (D-09/D-12) | unit (lock/ordering) | `uv run pytest tests/test_btw.py -x -q` (wrapper + render-lock tests) | ❌ Wave 0 (task creates) | ⬜ pending |
| LOOP-03 | btw outlives main, lands at idle (D-11) | live spike + manual | integration-marked test + terminal checklist (see Manual-Only) | ❌ Wave 0 (spike) | ⬜ pending |
| LOOP-03 | History fork at spawn; Q&A appended back (D-13/D-14) | unit | `uv run pytest tests/test_btw.py -x -q` (fork purity: no reasoningContent, no dangling toolUse; append-back shape) | ❌ Wave 0 (task creates) | ⬜ pending |
| LOOP-03 | Spend melts into session total, no btw rows (D-15) | unit | `uv run pytest tests/test_cost_context.py -x -q` (`record_turn_metrics` reuse) | ✅ extend existing | ⬜ pending |
| LOOP-03 | Ctrl-C chooser main/btw/both (D-08) | unit (state machine) + manual | `uv run pytest tests/test_plan_cancel.py -x -q` style + terminal checklist | ✅ extend existing | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_btw.py` — NEW: spawn/queue/lifecycle/fork/append/fence unit tests (covers LOOP-03 core)
- [ ] `tests/test_router_btw.py` — NEW (or fold into existing router tests if present): idle `/btw` dispatch + USAGE_HINT + BUILTIN_SLASH_HEADS membership
- [ ] Extend `tests/test_steering.py` — third reader outcome + gate_open regression (btw typed during open prompt)
- [ ] Extend `tests/test_policy_gate.py` + `tests/test_broker.py` — agent-keyed ask context, namespaced batch, per-request cancel, single-HITL-construction assertion
- [ ] Extend `tests/test_cost_context.py` — btw row melts into totals
- [ ] D-11 async-multiplex spike — live terminal spike before planning locks the idle design
- [ ] Framework install: none (`uv sync` reproduces `.venv`)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| btw outlives main and lands fenced at the idle prompt (incl. approval while idle) | LOOP-03 (D-11) | Async prompt + broker multiplex + cursor behavior are inherently live-terminal | Start a long main task, fire `/btw` needing approval, let main finish first; confirm tagged `[btw]` prompt serves at idle, fenced block lands without scrambling the `> ` line |
| Ctrl-C with both running asks main/btw/both | LOOP-03 (D-08) | Signal + dialog choreography needs a live terminal | Run main + btw, press Ctrl-C once, confirm chooser offers main/btw/both and cancels only the named target |
| Fenced side-block visuals while main streams | LOOP-03 (D-09) | Readability of interleaved output needs a human eye | Fire `/btw` mid-task, confirm fenced `[btw]` blocks arrive live with main output outside and no torn lines |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
