---
phase: 17-decision-routing-convergence-decisionmodel
plan: "02"
subsystem: routing, model, cost, loop
tags: [decisions-api, llm-decision-model, jev, cost-lane, uncertainty, apply-model-action]
requires:
  - phase: 17-decision-routing-convergence-decisionmodel
    provides: DecisionModel transport module, run_decision_sync, Explicit Uncertain narrowing (17-01)
provides:
  - resolve_harness_model(..., web_search=True, caching=True) tool and caching suppression switches
  - Opt-in "decisions_api" engine (DecisionsAPIDecisionModel, JEV_API_KEY, default ~typesafe/jev-latest, 0.62/0.04 gating, $0.0000 spend)
  - Opt-in "llm" engine (LLMDecisionModel, engine.llm_model, uncertainty=True immediate hold, bypassed 0.62/0.04, estimated /cost lane)
  - Simplified _parse_engine and shared _validate_single_order_engine with complexity well below xenon C (20)
affects: [17-03]
tech-stack:
  added: []
  patterns: [shared _run_folded_system_one bridge, _select_model_from_result / _evaluate_effort_answer "llm_choice" narrow path, 6-tuple _fold_routing_events estimated USD lane]
key-files:
  created: []
  modified:
    - strands_code_cli/model/model_switch.py
    - strands_code_cli/routing/transports.py
    - strands_code_cli/routing/core.py
    - strands_code_cli/cost/cost_context.py
    - tests/model/test_model_switch.py
    - tests/routing/test_routing_transports.py
    - tests/routing/test_routing_strategy.py
    - tests/routing/test_routing.py
    - tests/cost/test_cost_context.py
    - tests/loop/test_loop_routing.py
key-decisions:
  - "Keep both 'decisions_api' and 'llm' config-only opt-in in routing.yaml, appended after 'native' in _ENGINE_REGISTRY so default chains and /route setup stay untouched"
  - "Resolve engine.llm_model with effort='off', web_search=False, caching=False and run LLMDecisionModel with uncertainty=True under asyncio.wait_for(timeout), holding current immediately on Uncertain without fallback"
  - "Route engine=='llm' spend computed via cost_for(in_tok, out_tok, llm_model) into cost_context's estimated lane (no 'actual' tag) while preserving System One actuals and decisions_api $0.0000"
requirements-completed: [UPSTREAM-02]
metrics:
  completed: "2026-11-24"
---

# Phase 17 Plan 02: Opt-In `decisions_api` (`DecisionsAPIDecisionModel`) & `llm` (`LLMDecisionModel`) Engines + `/cost` & Loop Integration Summary

**Added opt-in `decisions_api` (`DecisionsAPIDecisionModel`, `JEV_API_KEY`) and `llm` (`LLMDecisionModel`, `uncertainty=True`) routing engines with `web_search=False, caching=False` suppression on `resolve_harness_model()`, `/cost` estimated-lane accounting, and full loop + `/btw` integration.**

## Changes Made
- **`strands_code_cli/model/model_switch.py`:** Extended `resolve_harness_model()` with backward-compatible `web_search: bool = True, caching: bool = True` kwargs (forwarding both on `meta/`, setting `caching_explicit=not caching`, and omitting `web_search` when `web_search=False`).
- **`strands_code_cli/routing/transports.py`:** Shared `_run_folded_system_one()` across `run_typesafe_decision()` and new `run_decisions_api_decision()` (`DecisionsAPIDecisionModel`, `JEV_API_KEY`, `~typesafe/jev-latest`, `{code, message, data: {result}}` envelope, `uncertainty=False`, `cost=None`); implemented `_estimate_llm_cost()` and `run_llm_decision()` (`resolve_harness_model(..., effort="off", web_search=False, caching=False)`, `LLMDecisionModel` under `asyncio.wait_for(..., timeout=timeout)`, explicit `isinstance(..., Uncertain)` hold, `{"type": "llm_choice", "choice": ...}`, estimated USD via `cost_for(in_tok, out_tok, llm_model)`).
- **`strands_code_cli/routing/core.py`:** Added `decisions_api_model` and `llm_model` schema fields, extended `_VALID_ORDER_ENGINES`/`_VALID_PRIMARY_ENGINES`/`_LEGACY_PRIMARY_ORDER`, simplified `_parse_engine()` (`CC 16`), extracted `_validate_single_order_engine()` (`CC 12`), registered `"decisions_api"` and `"llm"` after `"native"` in `_ENGINE_REGISTRY`, added `decisions_api_engine_ready()`, `decide_via_decisions_api`, `decide_via_llm`, `JEV_API_KEY` skip notes, `_select_model_from_result()`/`_evaluate_effort_answer()` `"llm_choice"` support (strictly restricted to `name == "llm"`, keeping `0.62`/`0.04` for System One), and updated `decision_model_for()` and `route_status_text()`. Left `save_strategy` (`CC 20`) and `dispatch/_setup_decision_entries` (`CC 20`) untouched.
- **`strands_code_cli/cost/cost_context.py`:** Updated `_routing_line()`, `_fold_routing_events()` (6-tuple splitting actual vs estimated routing USD), and `cost_report()` so `engine == "llm"` spend lands in the estimated lane without `" actual"`, `decisions_api` shows `$0.0000`, and `price_table` (`CC 20`) remains untouched.
- **`tests/`:** Added TDD coverage across `tests/model/test_model_switch.py`, `tests/routing/test_routing_transports.py`, `tests/routing/test_routing_strategy.py` (`JEV_API_KEY` stripping on `save_strategy`, zero-network `validate_strategy`), `tests/routing/test_routing.py` (registry order + `decisions_api` gating + `llm` bypass/`Uncertain` hold), `tests/cost/test_cost_context.py`, and `tests/loop/test_loop_routing.py` (main + `/btw` with `apply_model_action` + `RichHistory`).

## Complexity Check (`radon cc`)
- `strands_code_cli/routing/core.py`: `save_strategy` `C (20)` untouched, `_parse_engine` `C (16)`, `_validate_single_order_engine` `C (12)`, `_run_chain` `C (13)`, `_decide_effort` `C (15)`.
- `strands_code_cli/routing/transports.py`: highest `failure_reason` `C (16)`.
- `strands_code_cli/cost/cost_context.py`: `price_table` `C (20)` untouched, `cost_report` `C (13)`.
- `strands_code_cli/model/model_switch.py`: highest `configure_base_url_for_model` `C (16)`.

## Verification
- `.venv/bin/pytest tests/routing/ tests/loop/test_loop_routing.py tests/cost/test_cost_context.py tests/model/ tests/dispatch/test_router_setup.py tests/entry/ -k "not test_stub_server_systemone_decision_routes" -q` -> **719 passed, 5 deselected**
- `.venv/bin/ruff check strands_code_cli tests scripts` -> **All checks passed**
- `.venv/bin/ruff format --check strands_code_cli tests scripts` -> **121 files already formatted**
- `.venv/bin/xenon --max-absolute C strands_code_cli tests` -> **passed**
- `.venv/bin/lint-imports` -> **Contracts: 1 kept, 0 broken** (40 files, 89 dependencies)
- `git diff ee42ea2 -- strands_code_agent/` -> **empty** (`D-24`)
