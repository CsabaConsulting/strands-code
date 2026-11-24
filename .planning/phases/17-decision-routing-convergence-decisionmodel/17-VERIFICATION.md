---
phase: 17-decision-routing-convergence-decisionmodel
status: passed
score: 7/7
verified: "2026-11-24"
requirements:
  - UPSTREAM-02
commits:
  - f6d8651
  - a8e9993
  - b474041
---

# Phase 17 Verification: Decision Routing Convergence (`DecisionModel`, `UPSTREAM-02`)

**Status:** Passed (`7/7` must-have truths verified + live integration probes `5 passed, 1 skipped` + all 6 CI gates + `44/44` rig contract tests + `1737 + 1` full suite green)  
**Verified:** 2026-11-24 on branch `main`

## Truth-by-Truth Verification Matrix

| # | Decision / Truth | Evidence (Code & Tests) | Observed Status |
|---|---|---|---|
| 1 | `D-01`, `D-04`: `strands_code_cli/routing/transports.py` converges `native` (`TypeSafeDecisionModel`), `openrouter` (`OpenRouterDecisionModel(DecisionModel)`), and `local` (`OllamaDecisionModel(DecisionModel)`) onto unified `DecisionModel` interfaces preserving 64 KiB body fit, criteria prose, OpenRouter inline `usage.cost`, Ollama `keep_alive="5m"` + preflight + loopback `Authorization` suppression, and OTel `"decision"` spans | `strands_code_cli/routing/transports.py`, `tests/routing/test_routing_transports.py::TestDecisionModelOtelAndSubclasses` & `TestFoldedStateAndTypeSafeBridge`, `f6d8651` | ✅ Verified |
| 2 | `D-04`, `D-05`: `run_decision_sync()` safely bridges async `DecisionModel.ask()` into synchronous pre-turn & `/btw` callers (both bare threads and active-loop `ThreadPoolExecutor(max_workers=1)`) using per-call `httpx.AsyncClient(timeout=10s)` and retrying once only on retryable faults (zero retry on `ConnectError` / 4xx / `StructuredOutputException` / `ContextWindowOverflowException`) | `strands_code_cli/routing/transports.py::run_decision_sync` & `make_async_client`, `tests/routing/test_routing_transports.py::TestUncertainNarrowingAndAsyncBridge`, `tests/routing/test_routing.py`, `f6d8651` | ✅ Verified |
| 3 | `D-01`, `D-05`: Every `DecisionModel` response explicitly narrows `isinstance(val, Uncertain)` before indexing; `TypeSafeDecisionModel` & System One transports run with `uncertainty=False`, align `_validate_choice_shape` to 4-decimal grid rounding tolerance + `math.isfinite`, reproduce `0.62`/`0.04` gating and two-call model + effort routing without `candidates[0]` fallback regressions | `strands_code_cli/routing/transports.py::decision_result_to_engine_result`, `strands_code_cli/routing/core.py::_validate_choice_shape`, `gate_model`, `_run_chain`, `tests/routing/test_routing.py`, `f6d8651` | ✅ Verified |
| 4 | `D-02`, `D-05`: Config-only opt-in `"decisions_api"` engine wraps upstream `DecisionsAPIDecisionModel` (`https://decisionapi.net/v1/systemone`, `JEV_API_KEY`, default `~typesafe/jev-latest`, `{code, message, data: {result}}` envelope, `uncertainty=False`), participates in `0.62`/`0.04` gating, renders `$0.0000` in `/cost`, and emits a one-time skip note when listed without `JEV_API_KEY` | `strands_code_cli/routing/transports.py::run_decisions_api_decision`, `strands_code_cli/routing/core.py::decide_via_decisions_api` & `decisions_api_engine_ready`, `tests/routing/test_routing_transports.py`, `tests/routing/test_routing_strategy.py`, `tests/routing/test_routing.py`, `a8e9993` | ✅ Verified |
| 5 | `D-03`, `D-04`, `D-05`: Config-only opt-in `"llm"` engine resolves `engine.llm_model` via `resolve_harness_model(..., effort="off", web_search=False, caching=False)`, wraps upstream `LLMDecisionModel` (`uncertainty=True`, `asyncio.wait_for` timeout), halts immediately on `Uncertain` without fallback, bypasses numeric `0.62`/`0.04` (`model_confidence=None`/`effort_confidence=None`), and places `cost_for()` spend in `/cost`'s estimated lane (no `"actual"` tag) | `strands_code_cli/model/model_switch.py`, `strands_code_cli/routing/transports.py::run_llm_decision`, `strands_code_cli/routing/core.py::_select_model_from_result` & `_evaluate_effort_answer`, `strands_code_cli/cost/cost_context.py`, `tests/model/test_model_switch.py`, `tests/cost/test_cost_context.py`, `tests/loop/test_loop_routing.py`, `a8e9993` | ✅ Verified |
| 6 | `D-05`, `D-07`: Pre-turn `apply_model_action`, `convert_history()`, `RichHistory` stashes, `/route`, `/btw`, and credential isolation (`tests/conftest.py` scrubbing + `save_strategy` stripping `JEV_API_KEY` + `test_no_credential_persistence_sinks` + `httpx.MockTransport` + loopback `HTTPServer` stub) work end-to-end across all 5 engines | `tests/conftest.py`, `tests/loop/test_loop_routing.py::TestOptInEngineLoopAndBtw`, `tests/routing/test_routing.py::test_stub_server_systemone_decision_routes`, `tests/cost/test_cost_context.py::TestLoopUsageWiring::test_no_credential_persistence_sinks`, `f6d8651`, `a8e9993`, `b474041` | ✅ Verified |
| 7 | `D-06`, `D-07`, `D-24`: Opportunistic live `-m integration` probes verify OpenRouter, TypeSafe, `decisionapi.net`, and `LLMDecisionModel`; `docs/ROUTING.md` and `docs/QUICKSTART.md` document `DecisionModel` convergence and `TYPESAFE_API_KEY` vs `JEV_API_KEY`; `save_strategy` (`CC 20`), `_setup_decision_entries` (`CC 20`), `price_table` (`CC 20`), and `strands_code_agent/` stay untouched; all 6 CI gates pass | `docs/ROUTING.md`, `docs/QUICKSTART.md`, `tests/routing/test_routing.py::TestLiveEngines`, `tests/rig/`, `b474041`, `git diff ee42ea2 -- strands_code_agent/` empty | ✅ Verified |

## Opportunistic Live Integration Probes (`BypassSandbox: true`, `.env` sourced silently)

`.venv/bin/pytest tests/routing/test_routing.py -m integration -v` -> **5 passed, 1 skipped, 190 deselected**:
- `test_openrouter_live_decision_returns_typed_table` -> **PASSED**
- `test_typesafe_live_decision_returns_typed_table_with_computed_spend` -> **PASSED** (`TypeSafeDecisionModel` on `api.typesafe.ai`, `jev-1.13.0`, computed `$0.042/MTok` input spend)
- `test_typesafe_live_usage_triple_folds_computed_spend` -> **PASSED**
- `test_decisions_api_live_decision_returns_typed_table` -> **PASSED** (`DecisionsAPIDecisionModel` on `decisionapi.net`, `~typesafe/jev-latest`, `JEV_API_KEY`, `cost=None`)
- `test_llm_live_decision_routes_or_holds_uncertain` -> **PASSED** (`LLMDecisionModel` via `google/gemini-3.8-flash`)
- `test_ollama_live_daemon_decision_returns_typed_table` -> **SKIPPED** (no local Ollama daemon reachable)

## Final CI Gates & Test Suites (Verified After Wave 3 Edits `b474041`)

- `.venv/bin/ruff check strands_code_cli tests scripts` -> **All checks passed**
- `.venv/bin/ruff format --check strands_code_cli tests scripts` -> **121 files already formatted**
- `.venv/bin/xenon --max-absolute C strands_code_cli tests scripts` -> **passed** (`CC <= C 20`; `save_strategy`, `_setup_decision_entries`, `price_table` untouched at `20`)
- `.venv/bin/lint-imports` -> **Contracts: 1 kept, 0 broken** (40 files, 89 dependencies)
- `/home/csaba/.local/bin/uv lock --check` -> **Resolved 156 packages**
- `git diff ee42ea2 -- strands_code_agent/` -> **empty** (`D-24`)
- `.venv/bin/pytest tests/rig/ -q` -> **44 passed**
- `.venv/bin/pytest tests/ -k "not test_stub_server_systemone_decision_routes" -q` -> **1737 passed, 14 deselected** (`6` integration + `1` loopback test + default `-m 'not integration'` marker selection)
- `.venv/bin/pytest tests/routing/test_routing.py -k test_stub_server_systemone_decision_routes -q` *(with loopback socket access via `BypassSandbox: true`)* -> **1 passed, 195 deselected**
