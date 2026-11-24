---
phase: "17"
slug: "decision-routing-convergence-decisionmodel"
status: draft
nyquist_compliant: true
wave_0_complete: false
created: "2026-11-24"
---

# Phase 17 — Validation Strategy

> Per-phase Nyquist validation contract for feedback sampling during Phase 17 execution (`UPSTREAM-02`).

---

## Test Infrastructure

| Property | Value |
| :--- | :--- |
| **Framework** | `pytest` (installed in `.venv`) via `/home/csaba/.local/bin/uv run pytest` or `.venv/bin/pytest` |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, `addopts = "-m 'not integration'"`) |
| **Quick run command** | `.venv/bin/pytest tests/routing/ tests/loop/test_loop_routing.py tests/cost/test_cost_context.py -k "not test_stub_server_systemone_decision_routes" -q` |
| **Full suite command** | `.venv/bin/pytest tests/ -k "not test_stub_server_systemone_decision_routes" -q` + standalone `test_stub_server_systemone_decision_routes` |
| **Static / complexity gates** | `ruff check`, `ruff format --check`, `xenon --max-absolute C`, `lint-imports`, `uv lock --check` |

---

## Sampling Rate

- **After every task commit:** Run the task's targeted verification command (`< 25s`).
- **After every plan wave:** Run `.venv/bin/pytest tests/routing/ tests/loop/test_loop_routing.py tests/cost/test_cost_context.py -k "not test_stub_server_systemone_decision_routes" -q` + `ruff check` + `ruff format --check` + `xenon --max-absolute C` + `lint-imports`.
- **Before `/gsd-verify-work 17`:** All 6 CI workflow checks must pass cleanly (`strands_code_agent/` diff empty).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Decision / Anchor | Secure / Correct Behavior | Test Type | Automated Command | File Exists | Status |
| :--- | :---: | :---: | :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| `17-01-T1` | 01 | 1 | `UPSTREAM-02` | `D-01`, `D-04`, `T-17-02`..`T-17-05` | `strands_code_cli/routing/transports.py`: `OpenRouterDecisionModel(DecisionModel)`, `OllamaDecisionModel(DecisionModel)`, `TypeSafeDecisionModel` bridge, folded `state: str` + criteria prose, OTel `"decision"` spans, `isinstance(val, Uncertain)` narrowing, per-call `httpx.AsyncClient(timeout=10s)`, active-loop thread bridge, retry matrix (zero retry on 4xx / `ConnectError`) | unit (TDD RED→GREEN, Wave 0 file) | `.venv/bin/pytest tests/routing/test_routing_transports.py -q && .venv/bin/ruff check strands_code_cli/routing/transports.py tests/routing/test_routing_transports.py && .venv/bin/xenon --max-absolute C strands_code_cli/routing/transports.py tests/routing/test_routing_transports.py` | ❌ (`Wave 0`) | ⬜ pending |
| `17-01-T2` | 01 | 1 | `UPSTREAM-02` | `D-05`, `D-06`, `D-07`, `T-17-01` | Rewire `routing/core.py` onto `transports.py` (`decide_via_openrouter`, `decide_via_typesafe`, `decide_via_ollama`, `_preflight_get`), align `_validate_choice_shape` 4-decimal grid tolerance + `math.isfinite`, decompose `_run_chain`/`_decide_effort`, scrub `TYPESAFE_API_KEY` + `JEV_API_KEY` in `tests/conftest.py` (with `@pytest.mark.integration` exemption), migrate `test_routing.py` onto `httpx.MockTransport`, pass loopback stub server | unit + loopback integration | `.venv/bin/pytest tests/routing/ tests/loop/test_loop_routing.py tests/cost/test_cost_context.py -k "not test_stub_server_systemone_decision_routes" -q && .venv/bin/ruff check strands_code_cli/routing tests/routing && .venv/bin/xenon --max-absolute C strands_code_cli/routing tests/routing && .venv/bin/lint-imports` | ✅ | ⬜ pending |
| `17-02-T1` | 02 | 2 | `UPSTREAM-02` | `D-02`, `D-03`, `D-04`, `D-06` | Add `web_search`/`caching` flags on `resolve_harness_model`, implement `run_decisions_api_decision` (`DecisionsAPIDecisionModel`, `JEV_API_KEY`, `{code, message, data: {result}}`, `~typesafe/jev-latest`) and `run_llm_decision` (`LLMDecisionModel`, `uncertainty=True` → `Uncertain` hold, `cost_for()`, `asyncio.wait_for` timeout), wire config-only YAML schema & `_ENGINE_REGISTRY` keeping `CC <= 20` | unit (TDD RED→GREEN) | `.venv/bin/pytest tests/routing/test_routing_transports.py tests/routing/test_routing_strategy.py -q && .venv/bin/ruff check strands_code_cli/routing strands_code_cli/model/model_switch.py && .venv/bin/xenon --max-absolute C strands_code_cli/routing strands_code_cli/model/model_switch.py` | ✅ | ⬜ pending |
| `17-02-T2` | 02 | 2 | `UPSTREAM-02` | `D-03`, `D-05`, `D-07` | Update `cost_context._routing_line`, `_fold_routing_events`, and `cost_report` to route `engine == "llm"` spend into the estimated lane (no `"actual"` suffix, `price_table` untouched at `CC 20`), plus end-to-end `run_loop` / `/btw` (`apply_model_action`, `convert_history`, `RichHistory`) and `test_no_credential_persistence_sinks` tests | unit + integration (loop/cost) | `.venv/bin/pytest tests/routing/ tests/loop/test_loop_routing.py tests/cost/test_cost_context.py tests/entry/ -k "not test_stub_server_systemone_decision_routes" -q && .venv/bin/ruff check strands_code_cli tests && .venv/bin/xenon --max-absolute C strands_code_cli tests && .venv/bin/lint-imports` | ✅ | ⬜ pending |
| `17-03-T1` | 03 | 3 | `UPSTREAM-02` | `D-07` | Add `@pytest.mark.integration` live probes for `decisions_api` (`JEV_API_KEY`) & `llm` (direct `.env` provider key) in `tests/routing/test_routing.py`, execute opportunistic live probes without exposing `.env` secrets, verify `tests/rig/` & `test_routing_calibration.py` | integration + rig contract | `.venv/bin/pytest tests/rig/ tests/routing/test_routing_calibration.py -q && .venv/bin/ruff check tests/routing/test_routing.py && .venv/bin/xenon --max-absolute C tests/routing/test_routing.py` | ✅ | ⬜ pending |
| `17-03-T2` | 03 | 3 | `UPSTREAM-02` | `D-01`–`D-06` + Gates | Document `DecisionModel` convergence, `decisions_api` (`JEV_API_KEY` vs `TYPESAFE_API_KEY`, `noul`-only `respan/span-01-lite:free` caveat), and `llm` in `docs/ROUTING.md` + `docs/QUICKSTART.md` (`test_docs_routing_examples_validate_verbatim` green) and verify all 6 CI gates + full suite + standalone loopback test | docs + full CI gates | `.venv/bin/ruff check strands_code_cli tests scripts && .venv/bin/ruff format --check strands_code_cli tests scripts && .venv/bin/xenon --max-absolute C strands_code_cli tests scripts && .venv/bin/lint-imports && /home/csaba/.local/bin/uv lock --check && .venv/bin/pytest tests/rig/ -q && .venv/bin/pytest tests/ -k "not test_stub_server_systemone_decision_routes" -q && git diff ee42ea2 -- strands_code_agent/` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- `tests/routing/test_routing_transports.py` — created TDD-first in Plan `17-01` Task 1 (`17-01-T1`) covering direct `DecisionModel.ask()` OTel spans, `OpenRouterDecisionModel`, `OllamaDecisionModel`, `TypeSafeDecisionModel`, `Uncertain` narrowing, active-loop sync bridge, and retry matrix (extended in `17-02-T1` for `DecisionsAPIDecisionModel` and `LLMDecisionModel`).

---

## Manual / Opportunistic Live Verifications

| Behavior | Requirement | Why Live Creds / Network Required | Test Instructions | Status |
| :--- | :--- | :--- | :--- | :--- |
| Live `DecisionsAPIDecisionModel` (`~typesafe/jev-latest` on `https://decisionapi.net/v1/systemone`) | `UPSTREAM-02` | Requires `JEV_API_KEY` + outbound HTTPS | `.venv/bin/pytest tests/routing/test_routing.py -m integration -k test_decisions_api_live_decision` | ⬜ pre-probe passed (`HTTP 200`, `1,170ms`); re-verify via `decide_via_decisions_api` in `17-03` |
| Live `TypeSafeDecisionModel` (`jev-1.13.0` on `https://api.typesafe.ai/v1/systemone`) | `UPSTREAM-02` | Requires `TYPESAFE_API_KEY` + outbound HTTPS | `.venv/bin/pytest tests/routing/test_routing.py -m integration -k test_typesafe_live` | ⬜ pre-probe passed (`HTTP 200`, `184ms`); re-verify via `17-03` |
| Live `LLMDecisionModel` routing decision | `UPSTREAM-02` | Requires configured LLM provider key in `.env` | `.venv/bin/pytest tests/routing/test_routing.py -m integration -k test_llm_live_decision` | ⬜ pending (`17-03-T1`) |
| Real loopback `HTTPServer` Ollama `/api/version` + `/api/tags` + `/v1/systemone` routing (`test_stub_server_systemone_decision_routes`) | `UPSTREAM-02` | Requires local TCP bind (outside network-restricted sandbox) | `.venv/bin/pytest tests/routing/test_routing.py -k test_stub_server_systemone_decision_routes -q` | ⬜ pending (`17-01-T2`, `17-03-T2`) |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands
- [x] Sampling continuity: every task commits with TDD / automated verification
- [x] Wave 0 gaps identified (`tests/routing/test_routing_transports.py` in `17-01-T1`)
- [x] No watch-mode flags
- [x] Fast feedback latency (`< 25s` per targeted verification run)
- [ ] `nyquist_compliant: true` audited post-execution

**Plan Status:** ready for `/gsd-execute-phase 17`.
