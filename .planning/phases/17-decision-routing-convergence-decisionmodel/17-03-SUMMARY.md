---
phase: 17-decision-routing-convergence-decisionmodel
plan: "03"
subsystem: tests, docs
tags: [integration, live-probes, decisions-api, llm-decision-model, documentation, ci-gates]
requires:
  - phase: 17-decision-routing-convergence-decisionmodel
    provides: Converged DecisionModel transports and opt-in decisions_api & llm engines (17-01, 17-02)
provides:
  - "@pytest.mark.integration live probes for DecisionsAPIDecisionModel (JEV_API_KEY) and LLMDecisionModel in tests/routing/test_routing.py"
  - Updated docs/ROUTING.md and docs/QUICKSTART.md contrasting TYPESAFE_API_KEY vs JEV_API_KEY and documenting opt-in decisions_api & llm engines while keeping verbatim YAML validation green
  - Final Phase 17 CI gate & full-suite sign-off (all 6 CI gates, 44 rig contract tests, 1737+1 default tests, and 5/6 live integration probes passing)
affects: []
tech-stack:
  added: []
  patterns: ["@pytest.mark.integration key-gated live probes", "separate JEV_API_KEY vs TYPESAFE_API_KEY docs"]
key-files:
  created: []
  modified:
    - tests/routing/test_routing.py
    - docs/ROUTING.md
    - docs/QUICKSTART.md
key-decisions:
  - "Keep docs/ROUTING.md at exactly two 'candidates:' YAML blocks and show opt-in decisions_api/llm snippets as engine-only blocks so test_docs_routing_examples_validate_verbatim stays unmodified and green"
  - "Document respan/span-01-lite:free noul-only limitation on decisionapi.net alongside ~typesafe/jev-latest default and TYPESAFE_API_KEY vs JEV_API_KEY key separation"
requirements-completed: [UPSTREAM-02]
metrics:
  completed: "2026-11-24"
---

# Phase 17 Plan 03: Opportunistic Live Integration Probes, Routing & Key Documentation, and Full CI Gates Summary

**Added `@pytest.mark.integration` live probes for `DecisionsAPIDecisionModel` and `LLMDecisionModel` (verified live across OpenRouter, TypeSafe, decisionapi.net, and Gemini), updated `docs/ROUTING.md` & `docs/QUICKSTART.md`, and passed all 6 CI gates plus `tests/rig/` and the full test suite.**

## Changes Made
- **`tests/routing/test_routing.py` (`TestLiveEngines`):** Added `@pytest.mark.integration` tests `test_decisions_api_live_decision_returns_typed_table` (`JEV_API_KEY` + `~typesafe/jev-latest` + `cost is None`) and `test_llm_live_decision_routes_or_holds_uncertain` (env-selected direct provider via `decide_via_llm()` + `_pick_live_llm_model()`).
- **`docs/ROUTING.md`:** Documented `strands.decisions.DecisionModel` convergence across all 5 engines, added the `Opt-in decisions_api & llm engines` section (`~typesafe/jev-latest` default, `respan/span-01-lite:free` `noul`-only caveat, `JEV_API_KEY` vs `TYPESAFE_API_KEY` independence, `uncertainty=True` hold on `Uncertain`, bypassed `0.62`/`0.04` thresholds, and `/cost` estimated lane), updated `Manual edits` & `Keys`, and preserved the exact two `candidates:` example blocks required by `test_docs_routing_examples_validate_verbatim`.
- **`docs/QUICKSTART.md`:** Added `### Model routing & decision keys` cross-referencing `docs/ROUTING.md` and clearly separating `TYPESAFE_API_KEY` (`native` -> `api.typesafe.ai`) from `JEV_API_KEY` (`decisions_api` -> `decisionapi.net`).

## Opportunistic Live Integration Results (`BypassSandbox: true`, `.env` sourced silently)
`.venv/bin/pytest tests/routing/test_routing.py -m integration -v` -> **5 passed, 1 skipped, 190 deselected**:
- `test_openrouter_live_decision_returns_typed_table` -> **PASSED**
- `test_typesafe_live_decision_returns_typed_table_with_computed_spend` -> **PASSED** (`TYPESAFE_API_KEY`, `api.typesafe.ai`, `$0.042/MTok` input spend)
- `test_typesafe_live_usage_triple_folds_computed_spend` -> **PASSED**
- `test_decisions_api_live_decision_returns_typed_table` -> **PASSED** (`JEV_API_KEY`, `decisionapi.net`, `~typesafe/jev-latest`, `cost=None`)
- `test_llm_live_decision_routes_or_holds_uncertain` -> **PASSED** (`google/gemini-3.8-flash` via `LLMDecisionModel`)
- `test_ollama_live_daemon_decision_returns_typed_table` -> **SKIPPED** (no local Ollama daemon listening)

## CI Gates & Full Suite Verification (After Final Code & Docs Edits)
- `.venv/bin/ruff check strands_code_cli tests scripts` -> **All checks passed**
- `.venv/bin/ruff format --check strands_code_cli tests scripts` -> **121 files already formatted**
- `.venv/bin/xenon --max-absolute C strands_code_cli tests scripts` -> **passed** (`CC <= C 20`)
- `.venv/bin/lint-imports` -> **Contracts: 1 kept, 0 broken** (40 files, 89 dependencies)
- `/home/csaba/.local/bin/uv lock --check` -> **Resolved 156 packages** (`strands-agents==1.66.0`, `strands-harness==0.5.0`)
- `git diff ee42ea2 -- strands_code_agent/` -> **empty** (`D-24`)
- `.venv/bin/pytest tests/rig/ -q` -> **44 passed**
- `.venv/bin/pytest tests/ -k "not test_stub_server_systemone_decision_routes" -q` -> **1737 passed, 14 deselected**
- `.venv/bin/pytest tests/routing/test_routing.py -k test_stub_server_systemone_decision_routes -q` *(outside sandbox for loopback connect)* -> **1 passed, 195 deselected**
