---
phase: 10-provider-reported-turn-spend
reviewed: 2026-10-12T23:33:54Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - strands_code_cli/reported_cost.py
  - strands_code_cli/cost_context.py
  - strands_code_cli/loop.py
  - strands_code_cli/btw.py
  - strands_code_cli/main.py
  - strands_code_cli/model_switch.py
  - tests/test_reported_cost.py
  - tests/test_cost_context.py
  - tests/test_model_switch.py
findings:
  critical: 1
  warning: 4
  info: 3
  total: 8
status: issues
---

# Phase 10: Code Review Report

**Reviewed:** 2026-10-12T23:33:54Z
**Depth:** standard
**Files Reviewed:** 9 (6 source + 3 test, all commits since `77a6ab9` touching `strands_code_cli/` and `tests/`)
**Status:** issues
**Dispatch:** generic-agent workaround — typed gsd-code-reviewer dispatch unavailable; results labeled accordingly. Advisory only, never blocks.

## Summary

Reviewed the provider-reported turn-spend slice end to end: capture mixin and wrap factory (`reported_cost.py`), drain and wrap-site wiring (`loop.py`, `btw.py`, `main.py`, `model_switch.py`), and the actual-wins render contract (`cost_context.py`), cross-checked against the 10-01/10-02/10-03 acceptance criteria, the installed Strands SDK/harness, and repo contracts. Row/split/routing-marker logic is correct and test-pinned; `uv run pytest tests/test_reported_cost.py tests/test_cost_context.py -q` is green (87 passed, 1 deselected).

One critical defect breaks the phase's headline criterion: the main-turn drain passes the Agent instead of its model, so main OpenRouter turns never capture in production while tests pass (test/prod shape mismatch). Four warnings cover fail-soft gaps against the display-only posture, NaN poisoning, and a live-test assertion that contradicts the present-zero rule. Repo contracts hold: no new dependencies, key read from env at call time only, live test deselected offline, stdlib-only capture path.

## Critical Issues

### CR-01: Main-turn drain passes the Agent, not the model — main-path capture silently dead

**File:** `strands_code_cli/loop.py:1914` (`_drain_revise_rounds`) and `strands_code_cli/loop.py:2338` (`run_loop`)
**Issue:** Both main-turn sites call `record_turn_metrics(..., model=agent)`, and `_drain_reported_cost` (loop.py:278) resolves the drain via `getattr(model, "take_reported_costs", None)`. The mixin lives on `agent.model`, and a real Agent exposes no `take_reported_costs`: verified against the installed tree that `strands.Agent` defines no `__getattr__` (the only `__getattr__` is the module-level lazy-import hook in `strands/agent/__init__.py`), so the lookup returns `None` and every main-turn drain yields `None`. Every main OpenRouter turn therefore renders the estimate fallback, violating the 10-01 headline truth ("an OpenRouter main turn with reported usage.cost shows that cost as a marked actual"). The side path is correct (`_finish_btw_turn` drains `btw_agent.model`), and the routed-main wrap is covered (routing swaps via `apply_switch`, loop.py:1326) — only the main drain argument is wrong. Tests mask this: the tracer passes the wrapped model directly (`tests/test_reported_cost.py:213,224`), so no test exercises the agent-shaped production call. Second-order damage: `agent.model._reported_costs` accumulates unboundedly for the whole session since nothing ever drains it; a later naive fix that starts draining it would misattribute the session's entire spend to one turn (D-09 violation), so the fix must drain-and-discard once.
**Fix:**
```python
# loop.py:1914 and loop.py:2338 — drain the serving model, not the agent
usage = record_turn_metrics(
    follow_result, current_model, session_turns,
    model=getattr(agent, "model", None),
)
```
Add a regression test passing an agent-shaped `SimpleNamespace(model=wrapped)` to `record_turn_metrics`, and consider a defensive fallback inside `_drain_reported_cost` (`model.model` when `take_reported_costs` is absent).

## Warnings

### WR-01: `apply_switch` wrap is not fail-soft, unlike the other two wrap sites

**File:** `strands_code_cli/model_switch.py:656`
**Issue:** The wrap call sits outside any `try/except`, while `main.py:174-190` wraps in `try/except` and `_route_side_spawn` (loop.py:750-753) sits inside the existing resolve `try`. If `__class__` promotion ever raises (non-standard model implementation, `__slots__` layouts), a previously working model switch breaks — violating the display-only posture (actuals change numbers shown, never behavior).
**Fix:** Guard once at the choke point inside `wrap_for_openrouter` so all present and future call sites inherit it:
```python
try:
    resolved.__class__ = _composed_class(LiteLLMModel)
except Exception:
    return resolved
```

### WR-02: `fresh_side_model` shallow copy is unguarded

**File:** `strands_code_cli/reported_cost.py:124`
**Issue:** `copy.copy(model)` has no `try/except`. If a model implementation ever defeats shallow copying, `build_btw_agent` raises and the side turn fails outright — again a display concern breaking behavior. There is a genuine tradeoff (falling back to the shared instance risks side-channel misattribution), but a broken turn is worse than a degraded number.
**Fix:** `try/except` around the copy returning the input unchanged on failure, with a why-comment naming the tradeoff.

### WR-03: Non-finite costs pass the extractor and poison session totals

**File:** `strands_code_cli/reported_cost.py:22-28`
**Issue:** `_extract_cost` accepts any `int`/`float`, including `NaN` and `Inf` (Python's `json` accepts both, and the value arrives from provider JSON via the SDK). One `NaN` cycle renders `$nan actual` and poisons `total_actual` (and the blended Total) for the whole session; `Inf` renders `$inf actual`. The bool guard shows the author thought about hostile numerics — finiteness is the missing half.
**Fix:**
```python
import math
if isinstance(value, (int, float)) and math.isfinite(value):
    return float(value)
```

### WR-04: Live test asserts a positive cost, but a legitimate 0.0 actual would fail it

**File:** `tests/test_reported_cost.py` (`TestLiveReportedCost`, `assert isinstance(reported, float) and reported > 0`)
**Issue:** Test-reliability defect: D-09 explicitly blesses a present `0.0` as a marked actual zero (promo/free-tier turns), yet the live proof fails on exactly that valid outcome. The assertion is plan-mandated (10-03 acceptance), so this flags a plan/test inconsistency rather than an implementation slip — but as written the test can red-bar a correct provider response.
**Fix:** Assert `isinstance(reported, float) and reported >= 0`, keeping the `actual`-marker row assertion as the end-to-end proof.

## Info

### IN-01: Explicit `reported_cost` is unvalidated

**File:** `strands_code_cli/loop.py:314-317`
**Issue:** The explicit-wins branch stores any value verbatim; a non-numeric explicit value raises in `usage_line`'s format spec after the row is appended. Unreachable from production callers (drained `float | None` only). Consider routing explicit values through the `_extract_cost` shape for defense in depth.
**Fix:** `reported = _extract_cost(reported_cost)` in the explicit branch (keeps explicit-None-wins; coerces stray numerics; demotes garbage to the estimate path).

### IN-02: `wrap_for_openrouter` does not verify the instance is a `LiteLLMModel`

**File:** `strands_code_cli/reported_cost.py:108`
**Issue:** Promotion assigns a `LiteLLMModel`-subclass `__class__` to whatever instance arrives with an openrouter id. All current call sites pass matching pairs (harness `litellm/` ids always resolve to `LiteLLMModel`; bare `openrouter/` ids fail in `resolve_model` before reaching the wrap), but a future mismatched call would silently re-dispatch every `LiteLLMModel`-overridden method.
**Fix:** `if not isinstance(resolved, LiteLLMModel): return resolved` after the import.

### IN-03: Sub-cent actuals render as `$0.00 actual` on the usage line

**File:** `strands_code_cli/cost_context.py:179`
**Issue:** The locked 2-decimal usage-line precision renders e.g. `0.0024` as `$0.00 actual`, which reads like zero spend (the `/cost` row shows the true 4-decimal value). Plan-locked and test-pinned (`tests/test_reported_cost.py:193`), so no action required — recorded as an accepted UX tradeoff.

---

_Verified: 2026-10-12T23:33:54Z_
_Reviewer: the agent (gsd-code-reviewer via generic-agent workaround)_
_Depth: standard_
