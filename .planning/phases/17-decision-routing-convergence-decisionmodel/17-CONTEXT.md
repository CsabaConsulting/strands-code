# Phase 17: Decision Routing Convergence (`DecisionModel`) - Context

**Gathered:** 2026-11-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Converge custom HTTP routing transports in `strands_code_cli/routing/` onto `strands.decisions.DecisionModel` (`strands-agents == 1.66.0`, `UPSTREAM-02`) while keeping `strands-code`'s calibrated probability gating (`0.62` / `0.04`), two-call model + effort routing, `apply_model_action` + `convert_history()` + `RichHistory` stashes, hold-on-failure (`D-08`), `/route` UX, and `/cost` decision spend totals intact:
- Converge `native` (TypeSafe Jev) onto upstream `strands.decisions.typesafe_decision_model.TypeSafeDecisionModel`.
- Author CLI-owned `DecisionModel` subclasses `OpenRouterDecisionModel(DecisionModel)` and `OllamaDecisionModel(DecisionModel)` in `strands_code_cli/routing/transports.py` (preserving per-choice `criteria` dicts, 64 KiB body fit, OpenRouter inline USD `usage.cost`, and Ollama preflight + `keep_alive` + loopback key isolation).
- Wire upstream `strands.decisions.decisions_api_decision_model.DecisionsAPIDecisionModel` (`decisionapi.net`, `JEV_API_KEY`) as a config-only opt-in engine `"decisions_api"` in `routing.yaml`.
- Wire upstream `strands.decisions.LLMDecisionModel` (backed by any configured `provider/model` resolved via `model_switch.resolve_harness_model()`) as a config-only opt-in engine `"llm"` in `routing.yaml`, using `uncertainty=True` (`Uncertain` hold) and `cost_for()` estimation.
- Bridge `async def DecisionModel.ask(...)` cleanly into synchronous `decide()` on both main REPL threads and `/btw` background threads without breaking existing offline suites, `tests/rig/`, `xenon --max-absolute C`, `import-linter`, or pristine `strands_code_agent/`.

Out of scope: replacing `apply_model_action` / `convert_history()` / `RichHistory` with `strands.models.routing.ModelRouter` (explicit `v2.0` anchor decision), expanding `/route setup` interactive menus (`_setup_decision_entries` already sits at `xenon C (20)`), remote skills marketplaces (**Phase 18**, `SKILL-03`), Strands Box & Dogwood **Phase 19** (`SANDBOX-01`), `/help`/`@file`/`/review` (**Phase 20**), and `strands-agents-evals` (**Phase 21**).

</domain>

<decisions>
## Implementation Decisions

### Transport Convergence Architecture
- **D-01 (Hybrid `DecisionModel` Transports — Upstream TypeSafe + CLI `OpenRouterDecisionModel` / `OllamaDecisionModel`):**
  - Converge the `"native"` engine onto upstream `strands.decisions.typesafe_decision_model.TypeSafeDecisionModel` (`https://api.typesafe.ai/v1/systemone`, `TYPESAFE_API_KEY`, `uncertainty=False`), folding per-candidate / effort criteria prose cleanly into `Question["question"]` and passing structured routing context (`ask`, `directives`, `side`, 64 KiB fit) as `state: str` (`DecisionInput`).
  - Author thin CLI-owned `DecisionModel` subclasses `OpenRouterDecisionModel(DecisionModel)` and `OllamaDecisionModel(DecisionModel)` inside a dedicated module `strands_code_cli/routing/transports.py`:
    - Subclassing `strands.decisions.DecisionModel` yields uniform OTel `decision` spans, question validation, `DecisionResult`, `DecisionMetadata.probabilities`, `DecisionMetadata.confidence`, `usage`, and explicit `Uncertain` narrowing.
    - Both preserve System One per-choice `criteria` dicts (passed alongside `state` via `**kwargs` or normalized `Question`), 64 KiB payload fitting (`_fit_decision_payload` + `TRUNCATION_MARKER`), OpenRouter's inline USD `usage.cost` for `/cost`, and Ollama's `/api/version` + `/api/tags` preflight (`local_engine_ready`), `keep_alive: "5m"`, and loopback-only key suppression (`_ollama_headers`). — *Reversibility: moderate — all transport classes live behind `transports.py` + `register_engine`.*

### Opt-In Upstream Engines (`decisions_api` & `llm`)
- **D-02 (Opt-In `DecisionsAPIDecisionModel` — `"decisions_api"` Engine in `routing.yaml`):**
  - Wire upstream `strands.decisions.decisions_api_decision_model.DecisionsAPIDecisionModel` (`https://decisionapi.net/v1/systemone`, `JEV_API_KEY`, `{code, message, data: {result}}` envelope, `max_questions=8`, default model `"~typesafe/jev-latest"`) as an opt-in engine `"decisions_api"` in `routing.yaml` (`engine.order: [..., decisions_api]` or `engine.primary: decisions_api`, plus optional `engine.decisions_api_model`).
  - Uses the same folded-instructions `state: str` + `Question` builder as `TypeSafeDecisionModel`, runs with `uncertainty=False` over `result.metadata.probabilities`, participates cleanly in the `0.62` / `0.04` gate and two-call effort flow, and records `cost=None` (display-only unless a rate is supplied).
  - Config-only (never auto-inserted into default fallback chains or interactive `/route setup`), with `JEV_API_KEY` scrubbed in `tests/conftest.py` and presence-only key checks. — *Reversibility: easy — registered engine entry and YAML schema key.*

- **D-03 (Opt-In `LLMDecisionModel` — `"llm"` Engine in `routing.yaml`):**
  - Wire upstream `strands.decisions.LLMDecisionModel` as an opt-in engine `"llm"` in `routing.yaml` (`engine.order: [..., llm]` or `engine.primary: llm`, configured via `engine.llm_model: "<provider/model>"` resolved through `model_switch.resolve_harness_model()` with thinking off / small-budget framing).
  - Because `LLMDecisionModel` returns `metadata.probabilities=None` and `metadata.confidence=None`, run it with `uncertainty=True` (default): narrow every answer with `isinstance(val, Uncertain)` and **hold current** cleanly on `Uncertain` (no candidate commitment when unsure).
  - When `LLMDecisionModel` commits to a candidate/level, bypass the numeric `0.62` / `0.04` probability gate, set `model_confidence=None` / `effort_confidence=None` on `RoutingPick` (formatted distinctly as `-` or `n/a` in `/route`), and compute estimated decision spend via `cost_context.cost_for(input_tokens, output_tokens, llm_model)` so `/cost` still accounts for LLM decision calls.
  - Config-only in `routing.yaml` (keep interactive `/route setup` focused and protect `_setup_decision_entries`'s `xenon C (20)` ceiling). — *Reversibility: easy — registered engine entry and YAML schema key.*

### Async Bridge, Timeout, Retry & Failure Semantics
- **D-04 (Async-to-Sync Bridge, Per-Call `httpx.AsyncClient` Timeout & Retry/Hold Parity):**
  - Bridge `async def DecisionModel.ask(...)` safely into synchronous `decide()` (called on both main REPL threads and `/btw` background threads) via `run_decision_sync()` in `routing/transports.py`: uses `asyncio.run()` when no event loop is running on the calling thread, or isolates execution on a dedicated short-lived worker thread if a loop is active.
  - Supply per-call `httpx.AsyncClient(timeout=httpx.Timeout(timeout), headers={"User-Agent": "strands-code"})` closed cleanly inside `async with` to `TypeSafeDecisionModel` and `DecisionsAPIDecisionModel` (honoring `DECISION_TIMEOUT_SECONDS = 10` instead of the SDK's 30s default and preventing closed-loop client reuse across calls).
  - Preserve at most 1 retry on retryable failures (`ModelThrottledException`, HTTP 429/500/502/503/524/529, `httpx.TimeoutException`, `httpx.ConnectError`), zero retries on 4xx / `StructuredOutputException` / `ContextWindowOverflowException`, explicit `isinstance(answer, Uncertain)` checks on all returned answers, and strict hold-on-failure (`D-08` — never fall back to `candidates[0]`). — *Reversibility: easy — self-contained bridge and retry wrapper in `transports.py`.*

### Preserved Invariants, Complexity & Package Isolation
- **D-05 (Preserved Calibration, `apply_model_action`, `/cost` & Public Facade):**
  - Keep `0.62` confidence threshold and `0.04` tie-margin gate read from `result.metadata.probabilities` (never vendor `confidence` field) across all 4 System One engines (`native`, `decisions_api`, `openrouter`, `local`).
  - Keep two-call model + effort routing (including single-candidate effort-only shortcut and multi-question `validate_routed_effort`), `apply_model_action` + `convert_history()` + `RichHistory`, `/cost` actuals (OpenRouter inline `usage.cost`, TypeSafe flat `\$0.042/MTok` input rate, Ollama `cost=None`, DecisionsAPI `cost=None`, LLM estimated `cost_for()`), and public `routing/core.py` facade exports (`decide`, `decide_via_openrouter`, `decide_via_typesafe`, `decide_via_ollama`, `EngineResult`, `register_engine`, `gate_model`, `RoutingPick`). — *Reversibility: hard contract — existing tests and rig contracts depend on these.*

- **D-06 (Modular Extraction Under `xenon <= C (20)` & Import-Linter Contract):**
  - Isolate `DecisionModel` subclasses, folded-instruction state helpers, async bridge, and retry/error classification inside `strands_code_cli/routing/transports.py`, leaving `strands_code_cli/routing/core.py` clean and keeping `save_strategy` (`C 20`), `_run_chain` (`C 18`), `_setup_decision_entries` (`C 20`), and `run_loop` (`C 18`) within `xenon --max-absolute C`.
  - Feature modules under `routing/` must never import `strands_code_cli.entry` (`lint-imports`), read secrets anywhere outside permitted engine/first_run scopes (`test_no_credential_persistence_sinks`), or touch `strands_code_agent/` (`D-24`). — *Reversibility: easy — internal module boundary.*

### Verification Scope
- **D-07 (Hermetic Transport Suite + Opportunistic Live Probes):**
  - Pin all 5 `DecisionModel` transports offline: mocked `httpx` / `MockTransport` / structured-output fakes, `Uncertain` narrowing, `0.62`/`0.04` probability gate parity, 64 KiB body fit & `TRUNCATION_MARKER`, OpenRouter inline USD `cost`, DecisionsAPI `{code, message, data: {result}}` envelope unwrapping, `LLMDecisionModel` estimation + `Uncertain` hold, async-to-sync bridge under both no-loop and active-loop threads, loopback stub server (`test_stub_server_systemone_decision_routes`), and `tests/rig/`.
  - During planning and/or verification, run opportunistic live probes against whichever routing/LLM keys are present in `.env` (never reading, printing, or logging `.env` or secret values). — *Reversibility: easy — purely additive verification.*

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `.planning/REQUIREMENTS.md` — `UPSTREAM-02`
- `.planning/ROADMAP.md` — Phase 17 goal & 3 success criteria
- `strands_code_cli/routing/core.py` — Strategy parser/validator (`L132–1035`), state/question builders (`L1041–1130`), current HTTP transports (`L1239–1572`), probability gates (`L1574–1695`), engine registry & chain (`L1696–2210`, `_run_chain` `C 18`), `decide` & `validate_routed_effort` (`L2211–2295`), `/route` formatters (`L2298–2470`)
- `strands_code_cli/loop/core.py` — Pre-turn `routing_mod.decide(...)` call sites, `/btw` `_route_side_spawn` (`C 17`), `apply_model_action` (`C 13`), `run_loop` (`C 18`), `/cost` decision spend recording
- `strands_code_cli/dispatch/core.py` — `/route` validation & status dispatch (`L1452–1575`), `_setup_decision_entries` (`C 20` — do not inflate!)
- `strands_code_cli/model/model_switch.py` — `resolve_harness_model()` (target resolver for `LLMDecisionModel`) & `supports_reasoning()`
- `strands_code_cli/cost/cost_context.py` — `cost_for()` & `price_for()`
- `strands.decisions` (`.venv` installed `strands-agents==1.66.0`):
  - `strands.decisions.types` (`DecisionInput`, `Question`, `Uncertain`, `DecisionMetadata`, `DecisionResult`, `UncertaintyOptions`)
  - `strands.decisions.decision_model` (`DecisionModel` ABC, OTel `decision` span, `_validate_questions`)
  - `strands.decisions.typesafe_decision_model` (`TypeSafeDecisionModel` — `https://api.typesafe.ai/v1/systemone`, `TYPESAFE_API_KEY`)
  - `strands.decisions.decisions_api_decision_model` (`DecisionsAPIDecisionModel` — `https://decisionapi.net/v1/systemone`, `JEV_API_KEY`, `{code, message, data: {result}}` envelope, `max_questions=8`)
  - `strands.decisions._system_one_http_adapter` (`_ask_system_one`, `_http_transport`, `httpx.AsyncClient`)
  - `strands.decisions.llm_decision_model` (`LLMDecisionModel` — `ModelProxy.structured_output`, `Uncertain` enum option)
- `tests/routing/test_routing.py`, `tests/loop/test_loop_routing.py`, `tests/conftest.py`, `tests/rig/`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_fit_decision_payload()`, `_version_tuple()`, `local_engine_ready()`, `native_engine_ready()`, `validate_choice_answer()`, `_validate_effort_answer()`, and `gate_model()` in `strands_code_cli/routing/core.py` already isolate payload sizing, daemon readiness checks, and probability gating from the raw HTTP calls.
- `model_switch.resolve_harness_model(model_ref, effort="off")` already builds direct SDK `Model` instances across `bedrock/`, `google/`, `openai/`, `anthropic/`, `meta/`, and `litellm/` — reusable directly by the `llm` engine (`LLMDecisionModel(model=...)`).
- `cost_context.cost_for(input_tokens, output_tokens, model_id)` already computes display-only USD estimates for any resolved LLM model ID.

### Constraints & Watchpoints
- **Wire shape difference in SDK `TypeSafeDecisionModel` / `DecisionsAPIDecisionModel`:** `strands.decisions._system_one_http_adapter._to_wire_questions()` sends `{"type": "choice", "instructions": question["question"], "criteria": {c: None for c in choices}}` (prose lives in `Question["question"]`, NOT in per-choice `criteria` dict) and expects `state` as `str | list[ContentBlock] | Messages` (NOT a `dict` matching System One's raw `{ask, directives, side}` object unless serialized to a compact string). Any folded-instructions builder must pack `{ask, directives, side}` + per-candidate/effort criteria cleanly into `(state_str, Question)` without losing gating semantics or bloating past 64 KiB.
- **System One SDK 4-decimal rounding tolerance vs CLI `1e-6`:** Upstream `_system_one_http_adapter._parse_choice_answer` widens sum tolerance for 4-decimal rounded probabilities (`_PROBABILITY_ROUNDING_TOLERANCE = 5e-5`), whereas CLI `validate_choice_answer` historically checked `1e-6` — verify calibration & tolerance compatibility when bridging `DecisionResult.metadata.probabilities` back into `gate_model()`.
- **HTTP client lifecycle & event loops:** `httpx.AsyncClient` cannot be reused across distinct `asyncio.run()` calls/loops; per-call `async with httpx.AsyncClient(timeout=httpx.Timeout(timeout), ...)` created inside the async boundary avoids closed-loop errors cleanly while overriding the SDK's 30s default timeout.
- **Complexity ceiling (`xenon --max-absolute C`):** `save_strategy` (`C 20`), `_setup_decision_entries` (`C 20`), `_run_chain` (`C 18`), and `run_loop` (`C 18`) leave zero headroom for inline transport code — extract cleanly into `strands_code_cli/routing/transports.py`.
- **`test_no_credential_persistence_sinks` (`tests/cost/test_cost_context.py:988`):** `routing/core.py` and `routing/transports.py` remain permitted engine-layer env readers when credentials stay in-memory and never leak to logs or `routing.yaml`; keep `JEV_API_KEY`, `TYPESAFE_API_KEY`, `OPENROUTER_API_KEY`, `OLLAMA_API_KEY` out of `entry/`, `model/`, `dispatch/`, and `cost/`.
- **Pristine `strands_code_agent/` (`D-24`) & pure Python (`import-linter`):** Zero modifications to `strands_code_agent/` and zero imports from `entry/` in `routing/`.

</code_context>

<specifics>
## Specific Ideas

- Structure `strands_code_cli/routing/transports.py` around cohesive `DecisionModel` builders/subclasses:
  - `OpenRouterDecisionModel(DecisionModel)` and `OllamaDecisionModel(DecisionModel)` accepting optional structured `criteria` / `directives` metadata cleanly alongside standard `DecisionInput` and `Question`, populating `DecisionMetadata(latency_ms, provider_name, model_id, probabilities, confidence)` and `DecisionResult.usage` (extending `Usage` or returning `(DecisionResult, reported_cost)` via internal engine metadata/attribute so `DecisionModel.ask()` contract stays strict).
  - Shared `build_folded_state_and_questions(...)` helper for `TypeSafeDecisionModel` and `DecisionsAPIDecisionModel` that serializes `{ask, directives, side}` within 64 KiB and appends formatted option criteria cleanly to `Question["question"]` with `uncertainty=False`.
  - Shared `run_decision_sync(model, state, questions, *, retry=True)` helper unifying event-loop safe sync execution (`asyncio.run` vs worker thread) + single retry on retryable errors (`ModelThrottledException`, HTTP 429/5xx, `httpx.TimeoutException`, `httpx.ConnectError`).
- Inspect how existing `169` transport mock sites in `tests/routing/test_routing.py` stub `urllib.request.urlopen`, `_post_decision`, or `decide_via_*` so the test migration preserves facade compatibility (`decide_via_openrouter`, `decide_via_typesafe`, `decide_via_ollama`) while genuinely exercising `DecisionModel.ask()`, OTel spans, `Uncertain`, and real `httpx` / `MockTransport` paths.

</specifics>

<deferred>
## Deferred Ideas

- Interactive `/route setup` picker entries for `decisions_api` and `llm` (left YAML/config-only in Phase 17 unless refactored out of `_setup_decision_entries` in a future UX pass).
- Remote skills marketplaces and lockfile installer — **Phase 18 (`SKILL-03`)**.
- Strands Box Linux sandbox floor & Dogwood policy — **Phase 19 (`SANDBOX-01`)**.
- `/help`, `@file` / `/file`, `/review` — **Phase 20 (`LOOP-06`, `TOOL-05`, `REVIEW-01`)**.
- `strands-agents-evals` & red-team suite — **Phase 21 (`EVAL-01`)**.

</deferred>

*Phase: 17-decision-routing-convergence-decisionmodel*
*Context gathered: 2026-11-24*
