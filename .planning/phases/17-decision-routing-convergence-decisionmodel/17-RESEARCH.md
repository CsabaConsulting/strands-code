# Phase 17: Decision Routing Convergence (`DecisionModel`) — Research

**Researched:** 2026-11-24
**Phase:** `17-decision-routing-convergence-decisionmodel`
**Requirements:** `UPSTREAM-02`
**Sources Inspected Directly:**
- Installed SDK `strands-agents==1.66.0`: `.venv/lib/python3.12/site-packages/strands/decisions/{__init__,types,decision_model,_system_one_http_adapter,typesafe_decision_model,decisions_api_decision_model,llm_decision_model}.py`
- Live HTTP probes (2026-11-24) against `https://decisionapi.net/v1/systemone` (`JEV_API_KEY`) and `https://api.typesafe.ai/v1/systemone` (`TYPESAFE_API_KEY`)
- Codebase & complexity baseline (`radon cc -s -n C`): `strands_code_cli/routing/core.py`, `cost/cost_context.py`, `model/model_switch.py`, `dispatch/core.py`, `loop/core.py`, `tests/conftest.py`, `tests/routing/`, `tests/loop/test_loop_routing.py`, `tests/cost/test_cost_context.py`, `docs/ROUTING.md`, `scripts/route-probe.py`

---

## 1. Installed `strands.decisions` Inventory (`strands-agents==1.66.0`)

`strands.decisions` provides the official decision-model abstraction:

| Module / Export | Role & Wire Contract | Notable Constraints for `strands-code` |
| :--- | :--- | :--- |
| `__init__.py` | Eager exports `DecisionInput`, `DecisionMetadata`, `DecisionModel`, `DecisionResult`, `LLMDecisionModel`, `Question`, `Uncertain`, `UncertaintyOptions`; lazy `__getattr__` for `DecisionsAPIDecisionModel`, `SageMakerDecisionModel`, `TypeSafeDecisionModel` (avoids eager `httpx` import on `import strands`) | Keep `transports.py` importing upstream System One classes lazily inside builder/runner helpers or dedicated functions so CLI import time stays fast |
| `types.py` | `DecisionInput = str \| list[ContentBlock] \| Messages`; `Question(TypedDict)` (`question: str`, `choices: Literal["boolean"] \| list[str]`, `uncertainty: NotRequired[bool \| UncertaintyOptions]`); `Uncertain(reason: str \| None = None)` (frozen dataclass); `DecisionMetadata(latency_ms, provider_name, model_id, probabilities, confidence)`; `DecisionResult(answers, metadata, usage)` | `Uncertain` is **truthy** — every caller MUST narrow answers with `isinstance(value, Uncertain)` before string/bool indexing |
| `decision_model.py` | Abstract `DecisionModel.ask(state, questions, *, invocation_context=None, **kwargs)` opens an OpenTelemetry `"decision"` span (`SpanKind.INTERNAL`, attributes `gen_ai.operation.name`, `gen_ai.decision.questions`, `gen_ai.decision.latency_ms`, `gen_ai.decision.answers`, `gen_ai.usage.*`), validates `questions` via `_validate_questions()`, delegates to `await self._ask(state, questions, **kwargs)`, and closes/records errors on the span | `_validate_questions()` raises `ValueError` on empty `questions`, blank `question["question"]`, duplicate or empty strings in `choices`, or literal `"uncertain"` in `choices` (`"uncertain"` is reserved) |
| `_system_one_http_adapter.py` | Shared HTTP wire adapter (`POST /v1/systemone`) used by `TypeSafeDecisionModel` and `DecisionsAPIDecisionModel` | See §1.1 for critical wire/tolerance deltas vs CLI System One calls |
| `typesafe_decision_model.py` | `TypeSafeDecisionModel(api_key=None, model_id="jev-latest", default_min_confidence=0.5, http_client=None)` → `https://api.typesafe.ai/v1/systemone`, reads `TYPESAFE_API_KEY`; maps HTTP 400 `detail.error_type == "max_tokens_exceeded"` to `ContextWindowOverflowException` | Default `timeout=30.0` when `http_client=None`; supply per-call `httpx.AsyncClient(timeout=httpx.Timeout(timeout), ...)` inside `async with` to honor `DECISION_TIMEOUT_SECONDS = 10` without reusing closed-loop clients |
| `decisions_api_decision_model.py` | `DecisionsAPIDecisionModel(api_key=None, model_id="~typesafe/jev-latest", default_min_confidence=0.5, http_client=None)` → `https://decisionapi.net/v1/systemone`, reads `JEV_API_KEY`, `max_questions=8`, unwraps `{code, message, data: {result}}` envelope | Non-zero `code` raises `StructuredOutputException`; HTTP 200 envelope lacks `"model"` so adapter injects `self._provider_config.model_id` |
| `llm_decision_model.py` | `LLMDecisionModel(model=Model \| None = None, *, system_prompt=_DEFAULT_SYSTEM_PROMPT)` builds dynamic Pydantic `DecisionAnswers` with `Literal[..., "uncertain"]` when `uncertainty is not False`, appends prompt-injection mandatory rules, and invokes `ModelProxy(self._model).structured_output(...)` | Returns `DecisionMetadata(latency_ms=...)` with `probabilities=None` and `confidence=None`; wraps `ValidationError`/`ValueError` into `StructuredOutputException` |

**No OpenRouter or Ollama `DecisionModel` exists upstream** (`sagemaker_decision_model.py` is the only other class in `strands/decisions/`). This directly motivates `D-01`: converging `"native"` onto `TypeSafeDecisionModel`, adding opt-in `"decisions_api"` (`DecisionsAPIDecisionModel`) & `"llm"` (`LLMDecisionModel`), and authoring CLI-owned `OpenRouterDecisionModel(DecisionModel)` and `OllamaDecisionModel(DecisionModel)` subclasses in `strands_code_cli/routing/transports.py`.

### 1.1 Wire Differences in `_system_one_http_adapter.py`

Inspecting `_system_one_http_adapter.py` directly surfaced four contract facts:
1. **`_to_wire_state(state)` (`L182–L205`)** accepts only `DecisionInput = str | list[ContentBlock] | Messages` (NOT `{ask, directives, side}` dicts — strings pass through verbatim, lists are walked for binary content).
2. **`_to_wire_questions(questions)` (`L216–L230`)** sends:
   ```python
   {"type": "choice", "instructions": question["question"], "criteria": {choice: None for choice in choices}}
   ```
   Per-choice prose is **not** carried in wire `criteria`; it must be folded cleanly into `Question["question"]` (`Options:\n- <choice>: <prose>`) for `TypeSafeDecisionModel` and `DecisionsAPIDecisionModel`, while keeping `state: str` compact JSON of `{ask, directives, side}` trimmed to fit the 64 KiB cap (`DECISION_BODY_MAX_BYTES`).
3. **4-decimal rounding tolerance (`L29–L32`, `L340–L348`):** `_parse_choice_answer()` applies `_PROBABILITY_TOLERANCE = 1e-6` plus `_PROBABILITY_ROUNDING_TOLERANCE = 5e-5` per choice when every value lies on the `1e-4` decimal grid (e.g. `0.3333 * 3 = 0.9999` returned by hosted System One / `decisionapi.net`). `_parse_choice_answer()` also **requires** `answer["confidence"]` in `[0.0, 1.0]` and checks `probabilities[selected] + 1e-6 >= max(probabilities.values())`.
4. **No `usage.cost` field (`L365–L374`):** `_parse_usage()` extracts only `Usage(inputTokens, outputTokens, totalTokens)`. TypeSafe spend (`in_tok * 0.042 / 1_000_000`) continues to be computed code-side from `result.usage["inputTokens"]`; `OpenRouterDecisionModel._ask()` parses OpenRouter's inline `usage.cost` directly.

---

## 2. Empirical Live Probe Results (2026-11-24)

Executed against `.env` keys (`JEV_API_KEY` on unfunded `decisionapi.net` account; `TYPESAFE_API_KEY` on `api.typesafe.ai`) prior to Phase 17 planning:

- **`DecisionsAPIDecisionModel(model_id="~typesafe/jev-latest")` (`decisionapi.net`, `JEV_API_KEY`):**
  - **HTTP 200 OK**, `1,170ms`: `answers={'pick_model': 'fast'}`, `probabilities={'pick_model': {'fast': 1, 'deep': 0}}`, `usage={'inputTokens': 319, 'outputTokens': 32, 'totalTokens': 351}`. Works on an unfunded account.
- **`DecisionsAPIDecisionModel(model_id="respan/span-01-lite:free")`:**
  - **HTTP 400:** `Model respan/span-01-lite:free only supports noul questions.` — boolean-only classifier, cannot serve multi-choice `pick_model` / `pick_effort`.
- **`DecisionsAPIDecisionModel(model_id="inception/mercury-decide:free")`:**
  - **HTTP 502:** `The decision provider rejected the request.`
- **`TypeSafeDecisionModel(model_id="jev-1.13.0")` (`api.typesafe.ai`, `TYPESAFE_API_KEY`):**
  - **HTTP 200 OK**, `184ms`: `answers={'pick_model': 'fast'}`, `probabilities={'pick_model': {'fast': 1.0, 'deep': 0.0}}`, `usage={'inputTokens': 319, 'outputTokens': 32, 'totalTokens': 351}`. Zero env-var collision between `TYPESAFE_API_KEY` and `JEV_API_KEY`.

**Doc & default consequence:** Default `engine.decisions_api_model` to `"~typesafe/jev-latest"`, and in `docs/ROUTING.md` + `docs/QUICKSTART.md` explicitly distinguish `TYPESAFE_API_KEY` (`native` → `api.typesafe.ai`) from `JEV_API_KEY` (`decisions_api` → `decisionapi.net`).

---

## 3. Codebase Complexity Baseline & Technical Watchpoints

### 3.1 `radon cc -s -n C` Baseline

| Module | Functions at Rank C (`11 <= CC <= 20`) | Headroom Note |
| :--- | :--- | :--- |
| `strands_code_cli/routing/core.py` | `save_strategy` `C (20)`, `_candidate_skip_reason` `C (18)`, `_run_chain` `C (18)`, `_parse_engine` `C (17)`, `_validate_engine_order_chain` `C (16)`, `local_engine_ready` `C (16)`, `validate_strategy` `C (14)`, `_decide_effort` `C (14)`, `_validate_choice_shape` `C (12)` | `save_strategy` is at the ceiling (`20`) and requires zero edits (`_is_secret_shaped_key` already catches `JEV_API_KEY`). Extract transport logic to `routing/transports.py` and decompose `_run_chain`, `_decide_effort`, `_parse_engine`, and `_validate_engine_order_chain` via clean helpers (`CC <= 14`) |
| `strands_code_cli/dispatch/core.py` | `_setup_decision_entries` `C (20)`, `_route_validate_message` `C (12)` | Do NOT touch `_setup_decision_entries` (`D-02`/`D-03` config-only) |
| `strands_code_cli/loop/core.py` | `run_loop` `C (18)`, `_route_side_spawn` `C (17)`, `_invoke_agent` `C (15)`, `apply_model_action` `C (13)` | Zero edits needed in `loop/core.py` if `routing/core.py` preserves `(pick, engine, usage, detail)` & `RoutingPick`! |
| `strands_code_cli/cost/cost_context.py` | `price_table` `C (20)`, `compact_messages` `C (17)`, `cost_report` `C (12)`, `_fold_routing_events` `B (9)`, `_routing_line` `B (8)` | Keep `price_table` untouched; minor update to `_routing_line` / `_fold_routing_events` / `cost_report` for `engine == "llm"` estimated lane stays well under `C (15)` |

### 3.2 Nine Specific Pitfalls & Design Solutions

1. **Zero-retry on refused/unreachable connections (`T-08-24`, `D-09`):**
   - `httpx.ConnectError` (connection refused `errno.ECONNREFUSED` or DNS/unreachable) MUST NOT trigger retry (`test_url_error_holds_without_retry`, `test_all_links_refused_pauses_with_both_links_named`, `test_single_link_refused_pauses`).
   - Only `ModelThrottledException`, retryable `httpx.HTTPStatusError` (`code in {429, 500, 502, 503, 524, 529}`), `httpx.TimeoutException`, and `TimeoutError` retry once inside `run_decision_sync()`.
   - When diagnosing `httpx.ConnectError`, inspect `exc.__cause__` / `errno` (`errno.ECONNREFUSED` or `"connection refused"` → `"refused"`, else `"unreachable"`), matching existing `_CONNECTION_ERRORS` pause semantics.

2. **Out-of-levels effort diagnostic preservation (`test_effort_outside_levels_holds_via_validation`):**
   - When the wire response returns a well-formed `pick_effort` probability table whose `choice` is outside the candidate's advertised `levels` (e.g. `"max"` when candidate advertises `["low", "high"]`), existing behavior emits `detail == f"effort 'max' unsupported by {model}"` via `validate_routed_effort()`.
   - Therefore `OpenRouterDecisionModel` and `OllamaDecisionModel` validate valid probability distribution (`0..1`, sum `1`, `choice in probs`) with an internal `allow_unlisted_choices=True` option on `pick_effort` so `validate_routed_effort()` handles membership and emits the exact diagnostic string.

3. **Optional vendor `"confidence"` field (`T-08-21`, `test_missing_confidence_still_validates`):**
   - OpenRouter/Ollama tests allow `"confidence"` to be omitted in JSON answers. CLI `OpenRouterDecisionModel` / `OllamaDecisionModel` treat `"confidence"` as optional (defaulting `DecisionMetadata.confidence[q_id]` to `probs[selected]` when absent), while downstream `gate_model()` and `_run_chain()` still read `probabilities` exclusively (`D-05`).

4. **Upstream 4-decimal rounding tolerance vs `_validate_choice_shape` (`_system_one_http_adapter.py:L340-L348`):**
   - Existing `_validate_choice_shape` checked `abs(sum(probs) - 1.0) > 1e-6`. Updating `_validate_choice_shape` to check `math.isfinite(prob)` + mirror upstream's exact 4-decimal grid check (`tolerance = 1e-6 + (len(probs) * 5e-5 if rounded else 0.0)`) ensures `0.3333*3 = 0.9999` from `decisionapi.net`/`TypeSafe` passes cleanly while `{0.34, 0.33, 0.32}` (2 decimals, sum `0.99`) and `{0.5, 0.5, 0.5}` still fail!

5. **Native `web_search` conflict in `LLMDecisionModel` (`resolve_harness_model`):**
   - `model_switch.resolve_harness_model(model_ref, default, effort=...)` enables `web_search=True` and `caching=True` by default. Adding optional keyword parameters `web_search: bool = True, caching: bool = True` (preserving all existing callers) lets `run_llm_decision` call `resolve_harness_model(llm_model, llm_model, effort="off", web_search=False, caching=False)` — disabling extra server/native tools that could interfere with `ModelProxy.structured_output` forced tool use — and wraps `LLMDecisionModel.ask(...)` with `asyncio.wait_for(..., timeout=timeout)`.

6. **Distinguishing `"llm"` estimated spend vs actuals in `/cost` (`cost_context.py`):**
   - `decide_via_llm` estimates USD via `cost_for(input_tokens, output_tokens, llm_model)`. Labeling estimated LLM router spend as `"actual"` in `/cost` would conflate provider-billed actuals (OpenRouter / TypeSafe) with catalog estimates. Passing `engine == "llm"` to `_fold_routing_events()` adds `"llm"` spend to the **estimated** lane (`has_estimated=True, total_estimated += spend`) and omits `" actual"` on `_routing_line()` for `engine == "llm"`, keeping `test_totals_fold_reported_spend` and `openrouter`/`native`/`local` byte-identical.

7. **`tests/conftest.py` hermeticity vs `@pytest.mark.integration`:**
   - Currently `_PROVIDER_ENV_VARS` lacks `"TYPESAFE_API_KEY"` and `"JEV_API_KEY"`. Adding both protects offline tests against host key leakage (`T-17-01`), AND skipping `_hermetic_provider_env` deletion when `request.node.get_closest_marker("integration") is not None` allows `pytest -m integration` to use `.env` keys directly.

8. **Legacy mock & contract seams (`test_routing.py`, `test_loop_routing.py`, `route-probe.py`, `docs/ROUTING.md`):**
   - `tests/routing/test_routing.py` patches `urllib.request.urlopen` at ~80 sites while `tests/routing/test_routing_strategy.py` patches it at 2 sites. In Wave 1, replace HTTP network calls with `httpx.AsyncClient`/`httpx.Client` created via `transports.make_async_client()` / `make_sync_client()` so tests patch cleanly with `httpx.MockTransport`, keeping `test_stub_server_systemone_decision_routes` passing unmodified against real `HTTPServer`.
   - Keep `decide_via_openrouter`, `decide_via_typesafe`, `decide_via_ollama`, `_preflight_get`, and `local_engine_ready` exported/patchable on `strands_code_cli.routing.core` so `tests/loop/test_loop_routing.py`, `tests/routing/test_routing_calibration.py`, `dispatch/core.py:_route_validate_message()`, and `scripts/route-probe.py` work seamlessly.
   - Keep `docs/ROUTING.md` YAML examples limited to the exact strategy examples checked by `test_docs_routing_examples_validate_verbatim` (or update that test deliberately if an opt-in YAML example is added — keeping `len(examples)` and catalog seeding in sync).

9. **Async-to-sync bridge across main thread & active event loop (`D-04`):**
   - `run_decision_sync()` inspects `asyncio.get_running_loop()`. If `RuntimeError` (no running loop — standard CLI pre-turn & `/btw` pump thread), runs `asyncio.run(coro)`. If a loop is already running on the calling thread, spawns a short-lived `concurrent.futures.ThreadPoolExecutor(max_workers=1)` running `asyncio.run(coro)` and re-raises any exception cleanly.

---

*Researched: 2026-11-24 for Phase 17 (`UPSTREAM-02`)*
