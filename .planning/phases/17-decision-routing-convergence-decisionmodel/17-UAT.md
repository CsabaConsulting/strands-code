---
status: complete
phase: 17-decision-routing-convergence-decisionmodel
source: [17-01-SUMMARY.md, 17-02-SUMMARY.md, 17-03-SUMMARY.md, 17-VERIFICATION.md]
started: 2026-11-24T23:13:00Z
updated: 2026-11-25T00:09:00Z
---

# Phase 17 User Acceptance Testing (`UPSTREAM-02`)

## Current Test

[testing complete]

## Tests

### 1. Unified `DecisionModel` Transports, OTel `"decision"` Spans, 64 KiB Body Fit, `Uncertain` Narrowing & Dual-Mode Async Bridge (`D-01`, `D-04`, `D-05`)
expected: `OpenRouterDecisionModel` and `OllamaDecisionModel` subclass `strands.decisions.DecisionModel` and emit OTel `"decision"` spans while preserving per-choice `criteria` dicts, 64 KiB body fit (`truncated=True`), OpenRouter inline `usage.cost`, Ollama `keep_alive="5m"` and loopback `Authorization` suppression (vs attached on non-loopback `https://`); `run_decision_sync()` works both outside and inside a running event loop (single retry on `ModelThrottledException`, zero retries on `ConnectError` / `HTTP 401`); `decision_result_to_engine_result()` explicitly narrows truthy `Uncertain` via `isinstance`; `_validate_choice_shape` accepts 4-decimal grid rounding (`0.3333*3`) and rejects `0.34+0.33+0.32`; and invalid runtime questions fail closed to `EngineResult(answers=None, error="invalid body")`.
result: pass
evidence:
- Executed via `run_uat17_test1.py` (`exit 0`, user accepted `pass` 2026-11-24T23:16Z):
  - `1a`: `OpenRouterDecisionModel` and `OllamaDecisionModel` subclass `DecisionModel`; recorded `3` OTel `"decision"` spans (`gen_ai.operation.name == "decision"`); OpenRouter capped 100k-char ask to `65520` bytes (`truncated: True`), preserved per-choice `criteria`, and captured inline `cost: 0.00042`; Ollama set `keep_alive="5m"`, suppressed `Authorization` on loopback (`auth: null`), and attached `Bearer` auth on `https://` proxy.
  - `1b`: `run_decision_sync()` passed in both bare (`"bare"`) and live-loop (`"nested"`) callers; retried once (`2` attempts) on `ModelThrottledException` and made `1` attempt on `ConnectError` and `HTTP 401`.
  - `1c`: Explicit `isinstance(..., Uncertain)` narrowed truthy `Uncertain` to held `EngineResult(uncertain=True)`; `_validate_choice_shape` accepted `{0.3333, 0.3333, 0.3333}` and rejected `{0.34, 0.33, 0.32}`; malformed runtime questions failed closed (`'invalid body'`).

### 2. Live `TypeSafeDecisionModel` (`TYPESAFE_API_KEY`) & `OpenRouterDecisionModel` (`OPENROUTER_API_KEY`) Routing + `/cost` Actuals (`D-01`, `D-05`, `D-07`)
expected: Live `TypeSafeDecisionModel` (`api.typesafe.ai`, `jev-1.13.0`, folded criteria prose + compact `state: str`) and `OpenRouterDecisionModel` return typed probability tables meeting `0.62`/`0.04` gating, fold two-call model+effort usage into `/cost` actuals (flat `$0.042/MTok` input spend on native, inline USD on OpenRouter), and preserve pre-turn `apply_model_action`, `convert_history()`, and `RichHistory`.
result: pass
evidence:
- Executed via `run_uat17_test2.py` (`exit 0`, `BypassSandbox: true`, user accepted `pass` 2026-11-24T23:44Z):
  - `2a`: Live `TypeSafeDecisionModel` (`jev-1.13.0`) routed to `bedrock/anthropic.claude-sonnet-4-6` (`high`, model `100%`, effort `97%`), `851` input tokens, `$0.00003574` computed USD (`Prices: native computed input rate.`).
  - `2b`: Live `OpenRouterDecisionModel` (`typesafe/jev-1.13`) routed to `bedrock/anthropic.claude-sonnet-4-6` (`high`, model `100%`, effort `99%`), inline USD `$0.00003604`; combined `/cost` rendered `via native $0.0000 actual`, `via openrouter $0.0000 actual`, `Total: in 1.71K, out 210, $0.0001`, `Prices: mixed (per-turn model).`; `apply_model_action(..., "google/gemini-3.8-flash")` converted thinking trace and stashed `RichHistory`.
  - `2c`: `native_engine_ready() and decisions_api_engine_ready()` returned `True` concurrently with zero key collision.

### 3. Live Opt-In `decisions_api` (`decisionapi.net`, `JEV_API_KEY`, `~typesafe/jev-latest`), Zero-Network `/route validate`, Keyless Skip Note & `save_strategy` Secret Stripping (`D-02`, `D-05`, `D-07`)
expected: Live `DecisionsAPIDecisionModel` unwraps `decisionapi.net`'s `{code, message, data: {result}}` envelope using `JEV_API_KEY` and default `~typesafe/jev-latest`, routes via `0.62`/`0.04` gating, renders `$0.0000` in `/cost`, stays config-only in `routing.yaml`, validates with zero network calls in `/route validate`, emits a one-time skip note when `JEV_API_KEY` is missing, and drops `JEV_API_KEY`-shaped secrets on `save_strategy`.
result: pass
evidence:
- Executed via `run_uat17_test3.py` (`exit 0`, `BypassSandbox: true`, user accepted `pass` 2026-11-24T23:52Z):
  - `3a`: Live `DecisionsAPIDecisionModel` (`~typesafe/jev-latest` via `JEV_API_KEY`) routed to `bedrock/anthropic.claude-sonnet-4-6` (`high`, model `100%`, effort `99%`, `851` in / `105` out, `cost: None`); `route_status_text()` reported `decisions_api (~typesafe/jev-latest)`; `cost_report()` rendered `via decisions_api $0.0000` and `Total: in 851, out 105`.
  - `3b`: Default `_effective_order(RoutingEngine()) == ["openrouter", "local"]`; zero-network `validate_strategy()` passed (`decisions_api model ~typesafe/jev-latest — ok`); keyless `chain_skip_notes()` emitted `decisions_api engine skipped: JEV_API_KEY not set`.
  - `3c`: `save_strategy()` stripped both top-level `JEV_API_KEY` and nested `engine.jev_api_key` from disk.

### 4. Live Opt-In `llm` Engine (`LLMDecisionModel`, `effort="off"`, `web_search=False`, `caching=False`), `Uncertain` Hold, `/btw` Parity & `/cost` Estimated Lane (`D-03`, `D-04`, `D-05`)
expected: Opt-in `engine.order: [llm]` resolves `engine.llm_model` via `resolve_harness_model(..., effort="off", web_search=False, caching=False)`, routes live via `LLMDecisionModel` or halts immediately on `Uncertain` without falling back to `candidates[0]`, renders `model n/a, effort n/a`, preserves `/btw` & history immutability on hold, and accounts spend via `cost_for()` in the `/cost` estimated lane (omitting `"actual"`).
result: pass
evidence:
- Executed via `run_uat17_test4.py` (`exit 0`, `BypassSandbox: true`, user accepted `pass` 2026-11-25T00:01Z):
  - `4a`: `resolve_harness_model` received `{'ref': 'google/gemini-3.8-flash', 'effort': 'off', 'web_search': False, 'caching': False}`. Live `google/gemini-3.8-flash` routed `"What is 2 + 2?"` → `bedrock/anthropic.claude-haiku-4-5-20251001-v1:0` (`low`, `conf=[None, None]`, line `Routed → bedrock/anthropic.claude-haiku-4-5-20251001-v1:0 (low): model n/a, effort n/a`); upstream `GeminiModel.structured_output` omits usage (`[0, 0, None]`), while live `anthropic/claude-haiku-4-5` (`AnthropicModel.structured_output`) emitted `[2224 in, 114 out, $0.002794]`.
  - `4b`: `cost_report()` rendered `via llm $0.0028` (`" actual"` absent) and mixed `(actual $0.1200 + estimated $0.0028)`.
  - `4c`: `Uncertain("ambiguous")` halted immediately (`detail == "llm uncertain"`) with zero fallback to OpenRouter; `/btw` kept `agent.messages` byte-identical with `held=True`.

### 5. Real Loopback Ollama Stub (`test_stub_server_systemone_decision_routes`) & Documentation Review (`docs/ROUTING.md` & `docs/QUICKSTART.md`) (`D-01`–`D-03`, `D-05`)
expected: Real loopback `HTTPServer` stub serves `/api/version`, `/api/tags`, and `/v1/systemone` end-to-end; `docs/ROUTING.md` and `docs/QUICKSTART.md` clearly contrast `TYPESAFE_API_KEY` vs `JEV_API_KEY`, document `DecisionModel` convergence and opt-in `decisions_api` (`~typesafe/jev-latest` + `respan/span-01-lite:free` `noul`-only caveat) & `llm`, and pass verbatim YAML doc checks (`test_docs_routing_examples_are_valid_yaml` / `test_docs_routing_examples_validate_verbatim`).
result: pass
evidence:
- Verified cleanly on `HEAD` (`c05f89e`, user accepted `pass` 2026-11-25T00:06Z):
  - `5a`: `test_stub_server_systemone_decision_routes` (`BypassSandbox: true`, real loopback `HTTPServer`) → `1 passed, 195 deselected` in `2.32s`.
  - `5b`: `test_docs_routing_examples_are_valid_yaml` & `test_docs_routing_examples_validate_verbatim` → `2 passed, 92 deselected` in `2.37s`.
  - `5c`: Reviewed `docs/ROUTING.md` (`L21-L34`, `L98-L136`, `L210-L236`) and `docs/QUICKSTART.md` (`L245-L266`).

### 6. Full Hermetic Suite, Rig Contracts, Complexity Ceilings & All 6 CI Gates on Current `HEAD` (`D-06`, `D-24`)
expected: `pytest tests/ -q` (`+` standalone loopback stub), `pytest tests/rig/ -q`, `ruff check`, `ruff format --check`, `xenon --max-absolute C`, `lint-imports`, `uv lock --check`, and empty `git diff ee42ea2 -- strands_code_agent/` all pass cleanly with `save_strategy` (`CC 20`), `_setup_decision_entries` (`CC 20`), and `price_table` (`CC 20`) untouched.
result: pass
evidence:
- Verified against `HEAD` (`c05f89e`, user accepted `pass` 2026-11-25T00:09Z):
  - `.venv/bin/pytest tests/ -k "not test_stub_server_systemone_decision_routes" -q` → `1737 passed, 14 deselected` in `67.36s`, plus `1 passed` (`195 deselected`, `2.46s`) standalone unsandboxed for `test_stub_server_systemone_decision_routes` (`1738/1738` non-integration suite green).
  - `.venv/bin/pytest tests/rig/ -q` → `44 passed` in `0.10s`.
  - Static & CI gates: `ruff check strands_code_cli tests scripts` (`All checks passed!`), `ruff format --check strands_code_cli tests scripts` (`121 files already formatted`), `xenon --max-absolute C strands_code_cli tests scripts` (`exit 0`), `radon cc` confirming `save_strategy` (`20`), `_setup_decision_entries` (`20`), and `price_table` (`20`) untouched, `lint-imports` (`Contracts: 1 kept, 0 broken`, `40` files / `89` deps), `uv lock --check` (`Resolved 156 packages`), and `git diff ee42ea2 -- strands_code_agent/` (empty).

## Summary

total: 6
passed: 6
issues: 0
pending: 0
skipped: 0

## Gaps

[none yet]
