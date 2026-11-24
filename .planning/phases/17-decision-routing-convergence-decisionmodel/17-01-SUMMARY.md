---
phase: 17-decision-routing-convergence-decisionmodel
plan: "01"
subsystem: routing, tests
tags: [decision-model, strands-decisions, httpx, otel, typesafe, openrouter, ollama]
requires:
  - phase: 16-first-class-meta-model-api-muse
    provides: strands-agents==1.66.0 with strands.decisions DecisionModel/TypeSafeDecisionModel
provides:
  - DecisionModel transport module strands_code_cli/routing/transports.py with OpenRouterDecisionModel, OllamaDecisionModel, TypeSafeDecisionModel folded bridge, run_decision_sync, and explicit isinstance(val, Uncertain) narrowing
  - Converged strands_code_cli/routing/core.py facade delegations, 4-decimal probability grid tolerance, math.isfinite guard, and decomposed _evaluate_model_answer / _evaluate_effort_answer helpers
  - Hermetic test scrubbing of TYPESAFE_API_KEY & JEV_API_KEY (honoring @pytest.mark.integration) and httpx.MockTransport test suite
affects: [17-02, 17-03]
tech-stack:
  added: []
  patterns: [DecisionModel subclasses for System One custom criteria/telemetry, folded Question prose bridge for TypeSafeDecisionModel, ThreadPoolExecutor fallback in run_decision_sync, per-call httpx.AsyncClient lifecycle]
key-files:
  created:
    - strands_code_cli/routing/transports.py
    - tests/routing/test_routing_transports.py
  modified:
    - strands_code_cli/routing/core.py
    - tests/conftest.py
    - tests/routing/test_routing.py
    - tests/routing/test_routing_strategy.py
key-decisions:
  - "Keep OpenRouterDecisionModel and OllamaDecisionModel as thin DecisionModel subclasses so OpenRouter inline usage.cost, per-choice criteria dicts, allow_unlisted_choices, and Ollama keep_alive='5m'/loopback header rules stay intact while emitting OTel 'decision' spans (D-01, D-04)"
  - "Wrap upstream TypeSafeDecisionModel with default_min_confidence=0.0 inside per-call make_async_client(DECISION_TIMEOUT_SECONDS=10), folding criteria prose into Question['question'] and failing closed to EngineResult(error='invalid body') on ValueError"
  - "Narrow every DecisionModel answer with isinstance(val, Uncertain) before indexing and halt immediately on Uncertain in _run_chain/_decide_effort without fallback to candidates[0]"
requirements-completed: [UPSTREAM-02]
metrics:
  completed: "2026-11-24"
---

# Phase 17 Plan 01: Tracer — `routing/transports.py` `DecisionModel` Convergence & `routing/core.py` Facade Wiring Summary

**Extracted the routing transport layer into `strands_code_cli/routing/transports.py` on `strands.decisions.DecisionModel` (`OpenRouterDecisionModel`, `OllamaDecisionModel`, and upstream `TypeSafeDecisionModel` bridge), converged `strands_code_cli/routing/core.py`, hardened `tests/conftest.py`, and migrated HTTP stubs onto `httpx.MockTransport`.**

## Changes Made
- **`strands_code_cli/routing/transports.py`:** Implemented `EngineResult` (with `uncertain: bool = False`), transport constants, `valid_base_url`, per-call `make_async_client`/`make_sync_client`, `preflight_get`, `ollama_base`/`ollama_headers` (loopback `Authorization` suppression), `is_retryable_decision_error`/`failure_reason`, dual-mode `run_decision_sync` (`asyncio.run` vs `ThreadPoolExecutor(max_workers=1)` inside an active loop, single retry on retryable faults only), `fit_decision_payload` (64 KiB cap), `build_sdk_questions_and_criteria`, `build_folded_state_and_questions` (folding criteria prose into `Question["question"]`), `_SystemOneCustomDecisionModel(DecisionModel)`, `OpenRouterDecisionModel`, `OllamaDecisionModel`, `decision_result_to_engine_result` (explicit `isinstance(answer, Uncertain)` check), `run_openrouter_decision`, `run_ollama_decision`, and `run_typesafe_decision` (`try/except ValueError` fail-closed guard on invalid questions).
- **`strands_code_cli/routing/core.py`:** Re-exported transport constants and `EngineResult`, replaced legacy `urllib.request` transport code with facade delegations (`decide_via_openrouter`, `decide_via_typesafe`, `decide_via_ollama`, `_preflight_get`), updated `_validate_choice_shape` with `math.isfinite` and 4-decimal grid tolerance (`1e-6 + len(probs) * 5e-5`), and extracted `_evaluate_model_answer` / `_evaluate_effort_answer` (dropping `_run_chain` complexity from `C (18)` to `C (13)` while keeping `save_strategy` untouched at `C (20)`).
- **`tests/`:** Added `TYPESAFE_API_KEY` and `JEV_API_KEY` to `tests/conftest.py:_PROVIDER_ENV_VARS` while preserving integration marker bypass, added `tests/routing/test_routing_transports.py` (OTel spans, `Uncertain` narrowing, active-loop bridge, fail-closed `ValueError`, retry/ConnectError contracts, 4-decimal grid tolerance), guarded `transports.make_*_client` in `tests/routing/test_routing_strategy.py`, and migrated `tests/routing/test_routing.py` from `urllib.request.urlopen` stubs to `httpx.MockTransport` while keeping `test_stub_server_systemone_decision_routes` unmodified against real `HTTPServer`.

## Verification
- `.venv/bin/pytest tests/routing/ tests/loop/test_loop_routing.py tests/cost/test_cost_context.py tests/dispatch/test_router_setup.py -k "not test_stub_server_systemone_decision_routes" -q` -> **489 passed, 5 deselected**
- `.venv/bin/pytest tests/routing/test_routing.py -k test_stub_server_systemone_decision_routes -q` *(with loopback socket access outside sandbox)* -> **1 passed, 191 deselected**
- `.venv/bin/ruff check strands_code_cli tests scripts` -> **All checks passed**
- `.venv/bin/ruff format --check strands_code_cli tests scripts` -> **121 files already formatted**
- `.venv/bin/xenon --max-absolute C strands_code_cli/routing tests/routing` -> **passed** (`CC <= 20`)
- `.venv/bin/lint-imports` -> **Contracts: 1 kept, 0 broken** (40 files, 87 dependencies)
- `git diff ee42ea2 -- strands_code_agent/` -> **empty** (`D-24`)
