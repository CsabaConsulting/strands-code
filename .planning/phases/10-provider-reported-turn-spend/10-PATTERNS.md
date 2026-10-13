# Phase 10: Provider-Reported Turn Spend - Pattern Map

**Mapped:** 2026-10-12
**Files analyzed:** 8 (2 new, 6 modified)
**Analogs found:** 8 / 8
**Dispatch note:** Produced via generic-agent workaround (typed `gsd-pattern-mapper` dispatch unavailable); follows the role contract. All analog paths verified git-tracked via `git ls-files`.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `strands_code_cli/reported_cost.py` (NEW) | service | transform | `strands_code_cli/main.py` (`model_for_config`) + `strands_code_cli/routing.py` (`_cost`) | role-match |
| `strands_code_cli/cost_context.py` (TOUCH) | utility | transform | itself (`_reported_spend`, `_routing_line`, `cost_report`) | exact |
| `strands_code_cli/loop.py` (TOUCH) | controller | request-response | itself (`record_turn_metrics`) | exact |
| `strands_code_cli/model_switch.py` (TOUCH) | service | request-response | itself (`apply_switch`) | exact |
| `strands_code_cli/main.py` (TOUCH) | config | request-response | itself (`model_for_config`) | exact |
| `tests/test_reported_cost.py` (NEW) | test | batch | `tests/test_model_switch.py` (`TestAggregatorIds`) | role-match |
| `tests/test_cost_context.py` (EXTEND) | test | batch | itself (`TestCostReport`, `TestRoutingEntries`, `_routed_event`) | exact |
| `tests/test_model_switch.py` (EXTEND) | test | batch | itself (`TestAggregatorIds`) | exact |

## Pattern Assignments

### `strands_code_cli/reported_cost.py` (NEW; service, transform)

**Analog:** `strands_code_cli/main.py` lines 83-103 (lazy SDK-model import + construction) and `strands_code_cli/routing.py` lines 1108-1114 (reported-cost extractor). No existing SDK-model subclass exists in the repo — this file is the first, so copy the *construction* precedent from `model_for_config` and the *extractor* precedent from `_cost`. The `format_chunk` override signature/contract itself comes from 10-RESEARCH.md §Strands surfacing (installed-SDK reads, not tracked source).

**Lazy-import + construction pattern** (`main.py` lines 93-103):

```python
if model is None:
    return None
prefix = model.partition("/")[0] if "/" in model else "bedrock"
if base_url and prefix in ("openai", "litellm"):
    try:
        from strands.models.openai import OpenAIModel

        return OpenAIModel(model_id=model, client_args={"base_url": base_url})
    except ImportError:
        pass  # provider SDK missing: harness resolve reports it
return model
```

Copy: function-local SDK import (keeps the module importable without the provider extra), `try/except ImportError` fallback to the plain string. The new module must stay importable without the `litellm` extra (10-RESEARCH.md Wave 0: hermetic tests use fake `Usage`, no litellm import) — so import `LiteLLMModel` lazily inside the wrap helper, and guard the subclass definition the same way.

**Extractor pattern** (`routing.py` lines 1108-1114):

```python
def _cost(value: object) -> float | None:
    """Reported USD spend verbatim (None when absent or non-numeric)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None
```

Copy verbatim shape for the `.cost` read: bool-safe, int-tolerant (int `0` → `0.0`), None-on-absent. Read via `getattr(data, "cost", None)` — never attribute access (Pitfall 6). Every actual-wins branch checks `is not None`, never truthiness (`0.0` is an actual per Ruling 1).

**Scope-gate pattern** (`live_pricing.py` lines 357-368):

```python
def _openrouter_id(model_id: str) -> str | None:
    """OpenRouter model id for aggregator-routed refs, else None."""
    lowered = model_id.lower()
    for prefix in ("litellm/openrouter/", "openrouter/"):
        if lowered.startswith(prefix):
            ...
```

Wrap only when `live_pricing.is_openrouter_id(string)` is true; everything else passes through untouched (D-07). Fresh wrapper instance per call — never cache (Pitfall 1: main + btw must not share one `_reported_costs` list).

**Error handling:** capture code must never raise into the stream — fail soft to the D-05 estimate path (see Shared Patterns).

---

### `strands_code_cli/cost_context.py` (TOUCH; utility, transform)

**Analog:** itself. Extend, do not restructure.

**Reported-spend extractor** (lines 182-187) — the main-turn analog starts here:

```python
def _reported_spend(event: dict[str, Any]) -> float | None:
    """Reported decision USD spend (None when absent or non-numeric)."""
    spend = event.get("decision_cost")
    if isinstance(spend, bool) or not isinstance(spend, (int, float)):
        return None
    return float(spend)
```

**Row loop** (lines 253-269) — where actual-wins lands (D-09) and the marker attaches (D-01):

```python
for row in session_turns:
    turn = row.get("turn", "?")
    in_tok = int(row.get("input_tokens", 0))
    out_tok = int(row.get("output_tokens", 0))
    row_model = row.get("model", model_id)
    total_in += in_tok
    total_out += out_tok
    cell = f"  turn {turn}: in {format_tokens(in_tok)}, out {format_tokens(out_tok)}"
    turn_cost = cost_for(in_tok, out_tok, row_model)
    if turn_cost is not None:
        any_priced = True
        total_cost += turn_cost
        cell += f", ${turn_cost:.4f}"
```

**Routing-line marker precedent** (lines 221-222) — D-04 adopts the same actual marker here:

```python
spend = _reported_spend(event)
return f"{head} ${spend if spend is not None else 0.0:.4f}"
```

**Phase 9 marker precedent** (lines 290-294) — computed-rate provenance rewrite inside the routing totals fold; the D-03/D-08 work follows this shape (conditional provenance/marker injection, then dedupe-append):

```python
if (
    event.get("engine") == "native"
    and provenance == "unknown"
):
    provenance = "native computed input rate"
```

**Totals + split** (lines 297-306): headline `Total:` line, then one provenance/footer line. The D-08 split goes beneath the blended total; hidden entirely when either lane is empty (D-11 + symmetric restraint per Ruling 2). Routing/decision spend counts in the actuals lane (D-10).

**Usage-line money rule** (lines 165-172): `usage_line` appends money only on hit — D-02 adds the same marker via an optional `reported_cost` kwarg; bare `$` stays estimate-only (D-03). New kwargs must be optional (backwards-compatible, per the `get_response_metrics` precedent cited in `tests/test_cost_context.py` docstring).

---

### `strands_code_cli/loop.py` (TOUCH; controller, request-response)

**Analog:** itself.

**Drain choke point** (`record_turn_metrics`, lines 278-307) — all four record sites (main, btw, revise, idle-drain) flow through this one function, so the drain lands here once:

```python
def record_turn_metrics(
    result: Any, current_model: str, session_turns: list
) -> str | None:
    """Append one per-turn token row; return the usage line when computable.

    Best-effort display only: doubles without metrics (tests, direct calls)
    yield None instead of raising.
    """
    from strands_code_agent.utils import get_response_metrics

    try:
        metrics = get_response_metrics(
            result, model_id=current_model, price_table=MODEL_PRICING
        )
    except Exception:
        return None
    ...
    session_turns.append(
        {
            "turn": len(session_turns) + 1,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "model": current_model,
        }
    )
    return usage_line(in_tok, out_tok, current_model)
```

Copy: function-local import, broad `try/except` returning the degraded value, row dict extended with one more key (`reported_cost`), pass-through to `usage_line`. New params must be optional (existing 3-arg call sites keep working). Drain from the model instance that SERVED the turn via duck-typed `getattr(model, "take_reported_costs", None)` (test doubles lack it → None → estimate path). Drain-and-sum ALL accumulated costs; all-None → None (Pitfall 2).

**Routed resolve site** (line 719) — one of the three wrap sites:

```python
routed = resolve_model(pick.model, pick.model, effort=pick.effort)
```

Wrap the result for openrouter-routed ids only; preserve `effort` (Pitfall 5: pre-built instances ignore `effort`/`caching`, so construct the wrapper with reasoning pre-configured or bypass-and-wrap).

**btw kwargs replay** (lines 787-800): the side agent replays `parent_kwargs` with the live model object verbatim (`kwargs["model"] = routed`, line 736; `build_btw_agent(kwargs, ...)` rebuilds via `create_harness(**kwargs)`). The btw path must get its OWN wrapper instance — never reuse the main agent's (Pitfall 1).

---

### `strands_code_cli/model_switch.py` (TOUCH; service, request-response)

**Analog:** itself (`apply_switch`, lines 626-657) — wrap site #2:

```python
from strands_harness.models import resolve_model

new_string = normalize_model_ref(new_string)
if effort is None:
    model = resolve_model(new_string, default or new_string)
else:
    model = resolve_model(new_string, default or new_string, effort=effort)
agent.model = model
return (model, model_id_of(model, new_string))
```

Copy: function-local `resolve_model` import; insert the wrap between resolve and `agent.model =` assignment. Two-arg behavior must stay byte-identical when the id is not openrouter-routed (effort-forwarding precedent in the docstring). Non-OpenRouter ids return the identical object (D-07; test pins identity, not equality).

---

### `strands_code_cli/main.py` (TOUCH; config, request-response)

**Analog:** itself (`model_for_config`, lines 83-103; excerpt under `reported_cost.py` above) — wrap site #3 (initial build path). Same lazy-import + `except ImportError: pass` shape; falls back to the plain string when the SDK is unavailable. Wrapping here must preserve the `OpenAIModel(... client_args={"base_url": ...})` custom-endpoint behavior — openrouter ids with a `base_url` still wrap only via the `is_openrouter_id` gate.

---

### `tests/test_reported_cost.py` (NEW; test, batch)

**Analog:** `tests/test_model_switch.py` `TestAggregatorIds` (lines 551-583) — pure-function aggregator-id tests, no network, function-local imports:

```python
class TestAggregatorIds:
    def test_true_vendor_and_family_parsing(self):
        from strands_code_cli.model_switch import _base_key, _vendor_of

        entry = "litellm/openrouter/qwen/qwen3-32b"
        assert _base_key(entry) == "qwen/qwen3-32b"
        ...
```

Copy: one class per behavior area, function-local imports of the unit under test, `litellm/openrouter/...` ids as fixtures. Hermetic `Usage` fakes via `types.SimpleNamespace(cost=...)` — never import litellm. Cases: capture per metadata chunk; chunks byte-identical to `super()`; drain sums multi-cycle; all-None → None; absent `.cost` → None, never raises (string/bool/object `.cost`); non-OpenRouter ids pass through identical; effort survives wrapping; int-`0` and `0.0` captured as present. Integration live test env-gated (`integration` marker, skips without key or litellm extra).

**Offline double precedent** (`tests/test_cost_context.py` lines 64-94, `_ReplayModel(Model)`): minimal `Model` subclass with canned `stream()` yielding Strands chunks including a `metadata.usage` dict. Copy this shape — not an import — if a stream-level double is needed (test doubles are copied per module, never imported across test modules, per the file docstring).

---

### `tests/test_cost_context.py` (EXTEND; test, batch)

**Analog:** itself. Existing classes to extend: `TestCostReport` (line 239), `TestRoutingEntries` (line 303), `TestLoopUsageWiring` (line 619).

**Row/event builder precedent** (line 279):

```python
def _routed_event(**overrides):
```

Copy: module-level `**overrides` factory for session-turn rows with `reported_cost` set/unset. Cases: marked actual when present (incl. int-0 and float-0.0); estimate on None (D-05); tokens-only on no-price (D-06); blended total + split; split hidden when either lane empty (D-11); routing spend in actuals lane + routed lines marked (D-04/D-10); usage line carries the marker (D-02); bare `$` stays estimate-only (D-03); Bedrock rows byte-identical to today (D-07).

**Autouse fixture** (lines 52-56): `_no_user_overrides` monkeypatches `model_capabilities.active_overrides` to `[]` — new tests inherit this; report assertions assume shipped tables.

---

### `tests/test_model_switch.py` (EXTEND; test, batch)

**Analog:** itself (`TestAggregatorIds`, lines 551-583; excerpt under `test_reported_cost.py` above). Add wrap-scope cases: openrouter ids wrapped (fresh instance each call), non-OpenRouter ids pass through identical (identity assert), effort preserved through wrapping. Same pure-function, no-network style.

## Shared Patterns

### Bool-safe numeric extraction

**Source:** `strands_code_cli/routing.py` lines 1108-1114 (`_cost`); mirrored in `strands_code_cli/cost_context.py` lines 182-187 (`_reported_spend`).
**Apply to:** `reported_cost.py` capture, `cost_report` actual-wins branch.

```python
if isinstance(value, bool):
    return None
if isinstance(value, (int, float)):
    return float(value)
return None
```

### Fail-soft read paths (never raise to callers)

**Source:** `strands_code_cli/loop.py` lines 288-293 (`record_turn_metrics`); `strands_code_cli/main.py` lines 101-102 (`except ImportError: pass`).
**Apply to:** capture (`format_chunk` override), drain, all display code.

Capture failures degrade to the D-05 estimate path; never log raw usage payloads (may carry provider metadata) and never log keys. No per-cycle log spam.

### Money-only-on-hit (D-06 preserved)

**Source:** `strands_code_cli/cost_context.py` lines 169-172 (`usage_line`), 261-265 (`cost_report` row loop).
**Apply to:** every new money cell — actual, estimate, and split lines alike render only when the value is present (`is not None`).

### Verbatim pre-built model pass-through

**Source:** `strands_code_cli/btw.py` lines 421-442 (`build_btw_agent` replays kwargs into `create_harness`); `strands_code_cli/loop.py` lines 787-790 (live model object stashed, never re-resolved).
**Apply to:** all three wrap sites — the wrapper is constructed with its final config (reasoning pre-configured) because the harness uses pre-built instances verbatim and ignores `effort`/`caching` on them.

### Test conventions

**Source:** `tests/test_cost_context.py` docstring + lines 52-56; `tests/test_model_switch.py` `TestAggregatorIds`.
**Apply to:** `tests/test_reported_cost.py`, extended test classes.

- Test files mirror modules: `tests/test_<module>.py`; one class per behavior area (PascalCase), not per method.
- Doubles copied per module, never imported across test modules; all hermetic tests offline.
- `integration` marker for live tests (deselected by default per `pyproject.toml`).
- Function-local imports of the unit under test inside test methods.
- Module `logger = logging.getLogger(__name__)` with `%s`-style args; absolute imports, one per line; `snake_case` modules/functions, `PascalCase` classes; why-comments only (1–2 lines); docstrings on public functions/classes.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| (none) | — | — | Every file has at least a role-match analog. Note: no existing SDK-`Model` subclass exists in tracked source, so the `format_chunk`-override mechanics come from 10-RESEARCH.md installed-SDK citations rather than a repo analog; repo construction/extractor precedents cover the rest. |

## Metadata

**Analog search scope:** `strands_code_cli/` (cost_context, loop, model_switch, main, routing, live_pricing, btw), `tests/` (test_cost_context, test_model_switch); SDK-subclass search across `strands_code_cli/` + `strands_code_agent/` (no matches).
**Files scanned:** 9
**Pattern extraction date:** 2026-10-12
