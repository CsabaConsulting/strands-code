---
phase: 09-native-typesafe-decision-engine
reviewed: 2026-10-12T21:13:35Z
depth: standard
files_reviewed: 15
files_reviewed_list:
  - strands_code_cli/routing.py
  - strands_code_cli/router.py
  - strands_code_cli/loop.py
  - strands_code_cli/cost_context.py
  - scripts/route-probe.py
  - scripts/uattest/driver.py
  - evals/routing-probe/baseline.json
  - evals/routing-probe/probes.jsonl
  - tests/test_routing.py
  - tests/test_routing_strategy.py
  - tests/test_loop_routing.py
  - tests/test_router_setup.py
  - tests/test_cost_context.py
  - tests/test_routing_calibration.py
  - tests/test_uattest_driver.py
findings:
  critical: 0
  warning: 1
  info: 3
  total: 4
status: issues
---

# Phase 09: Code Review Report

**Reviewed:** 2026-10-12T21:13:35Z
**Depth:** standard
**Files Reviewed:** 15
**Status:** issues
**Scope:** all commits `ee64636..HEAD` touching `strands_code_cli/`, `tests/`, `scripts/`, `evals/` (09-01/09-02/09-03 executor work). `docs/ROUTING.md` changed in-phase but is outside the requested scope and was not reviewed.
**Provenance:** produced by gsd-code-reviewer 09 via the generic-agent workaround (typed dispatch unavailable); advisory only, never blocks.

## Summary

The native TypeSafe engine slice is sound: `decide_via_typesafe` mirrors the OpenRouter verdict shape through the shared `_post_decision` (stdlib urllib, call-time-only key, header-only auth), so the 4xx-hold / retry-once matrix is inherited rather than reimplemented; the ordered chain, legacy-primary mapping, skip-note helper, computed spend, setup order builder, validate ping, probe `--run native`, and rig scenarios all match the plan acceptance criteria, and the full suite is green (1363 passed, 10 deselected). No secrets in the repo, no new dependencies, live tests skip cleanly without a key. One Warning: an explicit empty `order: []` — which validate blesses as "routing disabled by config" — prints a hold note and appends a cost event on every ask, while legacy `primary: off` stays silent, because the load-layer off switch only maps the legacy shape. Three Info-grade notes below it.

## Warnings

### WR-01: Explicit empty order nag-spams holds instead of disabling silently like legacy off

**File:** `strands_code_cli/routing.py:428-453`
**Issue:** `load_strategy` returns `None` (hook takes the skip-silently branch) only when `engine.primary == "off"`. A hand-written file with explicit `order: []` has `primary` defaulting to `"openrouter"`, so it loads as a live strategy, `decide` hits the empty-chain branch returning `(None, "off", (0, 0, None), "off failed")`, and the pre-turn hook prints a hold note plus appends a routing event on every ask. Meanwhile `validate_strategy` reports the byte-identical "routing disabled by config" line for `order: []`, and the 09-01 plan claims "an empty order disables routing exactly like primary off does today". Equivalence holds at `decide()`/`_chain_for` level but not at the hook level. Setup can never write `order: []` (builder requires >= 1 engine; typed empty aborts), so only hand-edited files hit this — safe hold, but per-ask noise plus `/cost` event spam contradicting the validated "disabled" verdict.
**Fix:**
```python
# in load_strategy, both return points: treat an empty effective order
# as the off switch too, so order: [] degrades exactly like primary: off
if strategies is not None:
    if strategies.engine.primary == "off" or not _effective_order(strategies.engine):
        return None
    return strategies
```
Update the `load_strategy` docstring off-switch paragraph accordingly, and add a hook test asserting `order: []` returns silently with no routing event.

## Info

### IN-01: Non-list `order` judges legacy-fallback engines with confusing extra lines

**File:** `strands_code_cli/routing.py:838-852`
**Issue:** When `engine.order` is present but not a list (e.g. `order: "native"`), the validator correctly sets `valid = False` with an INVALID line, but then still judges `_effective_order(engine)` — which falls back to the legacy `primary` mapping — appending openrouter/local/native lines about engines the user never listed. The verdict stays INVALID (nothing resets `valid` to True), so this is cosmetic only.
**Fix:** Skip the per-engine judging loop when `raw_order` is not a list:
```python
if not isinstance(raw_order, list):
    valid = False
    lines.append("engine: INVALID — engine.order is not a list ...")
    lines.append("fix: ...")
else:
    for entry in raw_order:
        ...
    order = _effective_order(engine)
    ...  # existing per-engine judging moves under the else
```

### IN-02: Native pin string triplicated across routing, probe runner, and rig driver

**File:** `scripts/route-probe.py:59`, `scripts/uattest/driver.py:633-636`
**Issue:** The `jev-1.13.0` pin exists as `NATIVE_JEV_PIN` in `strands_code_cli/routing.py`, `NATIVE_MODEL_PIN` in `scripts/route-probe.py`, and `NATIVE_PIN`/`NATIVE_SNAPSHOT` in `scripts/uattest/driver.py`. A pin rotation must touch three files; drift between them fails silently (probe records a different pin than setup offers). The probe runner already imports production names from `strands_code_cli.routing`.
**Fix:** In `route-probe.py`, `from strands_code_cli.routing import NATIVE_JEV_PIN` and alias `NATIVE_MODEL_PIN = NATIVE_JEV_PIN` (keep the local name for the `--native-model` default/readability). In `driver.py`, import the pin from `strands_code_cli.routing` too, keeping `NATIVE_SNAPSHOT` as the deliberate drift-detector it is.

### IN-03: Rig `strategy_order` misparses flow-style empty order

**File:** `scripts/uattest/driver.py:259-274`
**Issue:** For `order: []`, the flow branch computes `"[]"[1:-1].split(",")` → `[""]`, returning `[""]` instead of `[]`. No current scenario writes an empty order, so this never fires today; it would only mislead a future assertion.
**Fix:**
```python
inner = flow[1:-1].strip()
return [piece.strip() for piece in inner.split(",")] if inner else []
```

---

_Verified during review: full suite `uv run pytest tests/ -q` → 1363 passed, 10 deselected; routing-file subset → 459 passed, 4 deselected; `route-probe.py --dry-run` lists native with 20 probes; baseline carries 20 native verdicts with pin/snapshot keys; repo-wide scan finds no key material (reads, bogus fixtures, and message text only) and no `jev-preview`/short-form ids in `router.py`._
_Reviewed: 2026-10-12T21:13:35Z_
_Reviewer: the agent (gsd-code-reviewer 09, generic-agent workaround)_
_Depth: standard_
