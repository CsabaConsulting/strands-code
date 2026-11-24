# Phase 17 Codebase Patterns & Extension Seams

**Created:** 2026-11-24
**Purpose:** Concrete module boundaries, transport interfaces, complexity decomposition, and CI/security guardrails across Plans `17-01`, `17-02`, and `17-03`.

---

## 1. Unified Decision Transports (`strands_code_cli/routing/transports.py`)

New self-contained transport module under `strands_code_cli/routing/` (zero imports from `strands_code_cli.entry` so `lint-imports` stays `1 kept, 0 broken`; keeps every function `CC <= 14`).

- **Public constants & types (`D-01`–`D-05`):**
  - `DECISION_TIMEOUT_SECONDS = 10`
  - `OPENROUTER_DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"`
  - `TYPESAFE_DECISIONS_URL = "https://api.typesafe.ai/v1/systemone"`
  - `DECISIONS_API_URL = "https://decisionapi.net/v1/systemone"`
  - `DECISIONS_API_DEFAULT_MODEL = "~typesafe/jev-latest"`
  - `TYPESAFE_INPUT_USD_PER_MTOK = 0.042`
  - `OLLAMA_DEFAULT_HOST = "http://127.0.0.1:11434"`
  - `OLLAMA_TIMEOUT_SECONDS = 30`, `OLLAMA_KEEP_ALIVE = "5m"`, `OLLAMA_PREFLIGHT_TIMEOUT_SECONDS = 5`
  - `DECISION_BODY_MAX_BYTES = 64 * 1024`, `TRUNCATION_MARKER = "ask truncated to fit the decision cap"`
  - `_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 524, 529})`
  - `_OLLAMA_LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")`
  - `EngineResult(answers, input_tokens=0, output_tokens=0, cost=None, model=None, error=None, truncated=False, uncertain=False)`

- **HTTP client seams & async-to-sync bridge (`D-04`):**
  - `make_async_client(timeout: float, headers: dict[str, str] | None = None) -> httpx.AsyncClient`: creates a fresh per-call async client inside `async with` (prevents reusing a client across closed `asyncio.run()` loops and lets `httpx.MockTransport` tests patch one clean factory).
  - `make_sync_client(timeout: float) -> httpx.Client`: sync client factory used by `preflight_get(url, headers)` (returns `dict | None`, catches `Exception`, fail-closed `None`).
  - `is_retryable_decision_error(exc: BaseException) -> bool`:
    - `True` ONLY for `ModelThrottledException`, `httpx.HTTPStatusError` (`response.status_code in _RETRYABLE_STATUS`), `httpx.TimeoutException`, `TimeoutError`, and `urllib.error` timeouts (`HTTPError` in `_RETRYABLE_STATUS`, `TimeoutError`, `URLError(TimeoutError)`).
    - `False` for `httpx.ConnectError` (refused/unreachable — T-08-24), 4xx `HTTPStatusError`, `StructuredOutputException`, `ContextWindowOverflowException`, and `ValueError`.
  - `failure_reason(exc: BaseException) -> str`: maps to `"HTTP <code>"`, `"timeout"`, `"refused"` (errno `ECONNREFUSED` / `"connection refused"`), `"unreachable"`, `"invalid body"` (`StructuredOutputException` / JSON `ValueError`), `"HTTP 413"` / `"context overflow"` (`ContextWindowOverflowException`), or `"error"` (never echoing headers/keys).
  - `run_decision_sync(coro_factory: Callable[[], Awaitable[T]], *, retry: bool = True) -> T`:
    - Executes `asyncio.run(coro_factory())` when no loop is running on the calling thread, or delegates to a single-worker `ThreadPoolExecutor` executing `asyncio.run(coro_factory())` when an event loop is already active.
    - Retries at most once (`attempt_no == 0 and is_retryable_decision_error(exc)`).

- **State & Question builders (`D-01`–`D-03`):**
  - `valid_base_url(value: str) -> bool`: http(s) URL with non-empty hostname (`urlsplit`).
  - `fit_decision_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]`: shrinks `state["ask"]` (exact bytes <= `DECISION_BODY_MAX_BYTES`) without altering directives or criteria; supports both nested dict `state` and JSON-serialized `state` string if passed inside SDK payloads.
  - `build_sdk_questions_and_criteria(questions: dict[str, Any], *, uncertainty: bool = False) -> tuple[dict[str, Question], dict[str, dict[str, str]]]`: translates internal System One dicts (`{"type": "choice", "instructions": ..., "criteria": {k: prose}}`) into canonical SDK `dict[str, Question]` (`choices=list(criteria.keys())`) plus preserved criteria maps.
  - `build_folded_state_and_questions(state: dict[str, Any], questions: dict[str, Any], *, model_id: str | None = None, uncertainty: bool = False, max_bytes: int = DECISION_BODY_MAX_BYTES) -> tuple[str, dict[str, Question], bool]`:
    - Formats `Options:\n- <choice>: <prose>` into each SDK `Question["question"]` (`uncertainty=False`), serializes `{ask, directives, side}` compactly into `state_str`, and if the upstream JSON body `{"state": state_str, "model": ..., "questions": wire_q}` exceeds `max_bytes`, trims `state["ask"]` iteratively to fit (`truncated=True`).

- **CLI `DecisionModel` subclasses (`D-01`):**
  - `_SystemOneCustomDecisionModel(DecisionModel)` shared base for HTTP System One transports that preserve per-choice `criteria` dicts and optional `confidence`:
    - Reads raw System One `questions` + optional per-call flags via `ask(..., raw_questions=..., allow_unlisted_choices=...)`.
    - Stores `self.last_truncated: bool` and `self.last_cost: float | None` per call (kept off `DecisionResult` so upstream `DecisionResult` dataclass contract stays strict).
    - Validates response shape cleanly (`type == "choice"`, `0 <= prob <= 1`, `math.isfinite`, 4-decimal grid sum tolerance `1e-6 + 5e-5 * N`, optional `"confidence"` falling back to `probs[selected]`), enforces `choice in choices` unless `allow_unlisted_choices=True` (preserves `test_effort_outside_levels_holds_via_validation`), raises `ContextWindowOverflowException` (413) / `ModelThrottledException` (429/503/529) / `httpx.HTTPStatusError` / `StructuredOutputException`, and returns complete `DecisionResult(answers, metadata=DecisionMetadata(latency_ms, provider_name, model_id, probabilities, confidence), usage=Usage(...))` inside the base `DecisionModel.ask()` OTel span!
  - `OpenRouterDecisionModel(_SystemOneCustomDecisionModel)`: `endpoint=OPENROUTER_DECISIONS_URL`, reads `OPENROUTER_API_KEY` header-only (`User-Agent: strands-code`), extracts inline `usage.cost` (float/int only, bool-safe).
  - `OllamaDecisionModel(_SystemOneCustomDecisionModel)`: `endpoint=f"{base.rstrip('/')}/v1/systemone"`, suppresses `Authorization` header for loopback hosts (`localhost`, `127.0.0.1`, `::1`), sets `"keep_alive": OLLAMA_KEEP_ALIVE` in payload, `last_cost=None`.

- **Result translation & 5 engine runners (`D-01`–`D-05`):**
  - `decision_result_to_engine_result(result: DecisionResult, *, raw_questions: dict[str, Any], cost: float | None, truncated: bool, llm_mode: bool = False) -> EngineResult`:
    - Checks **every** answer with `isinstance(val, Uncertain)` FIRST! If any answer is `Uncertain`, returns `EngineResult(answers=None, input_tokens=..., output_tokens=..., cost=..., error=val.reason or "uncertain", truncated=truncated, uncertain=True)` — holds immediately!
    - For System One engines, builds `answers[q_id] = {"type": "choice", "choice": val, "probabilities": probs[q_id], "confidence": conf[q_id]}`.
    - For LLM engine (`llm_mode=True`), builds `answers[q_id] = {"type": "llm_choice", "choice": val}`.
  - Public transport runners called by `routing/core.py`:
    - `run_openrouter_decision(*, decision_model, state, questions, timeout=DECISION_TIMEOUT_SECONDS) -> EngineResult`
    - `run_typesafe_decision(*, native_model, state, questions, timeout=DECISION_TIMEOUT_SECONDS) -> EngineResult` — constructs upstream `TypeSafeDecisionModel(api_key=api_key, model_id=native_model, default_min_confidence=0.0, http_client=client)` inside per-call `async with make_async_client(timeout)`, computes `in_tok * TYPESAFE_INPUT_USD_PER_MTOK / 1_000_000`.
    - `run_ollama_decision(*, local_model, local_base_url, state, questions, timeout=OLLAMA_TIMEOUT_SECONDS) -> EngineResult`
    - `run_decisions_api_decision(*, model_id, state, questions, timeout=DECISION_TIMEOUT_SECONDS) -> EngineResult` — constructs upstream `DecisionsAPIDecisionModel(api_key=api_key, model_id=model_id, default_min_confidence=0.0, http_client=client)` inside per-call `async with make_async_client(timeout)`, `cost=None`.
    - `run_llm_decision(*, llm_model, state, questions, timeout=DECISION_TIMEOUT_SECONDS) -> EngineResult` — resolves `resolve_harness_model(llm_model, llm_model, effort="off", web_search=False, caching=False)`, builds `LLMDecisionModel(model=resolved)`, wraps `ask(..., uncertainty=True)` in `asyncio.wait_for(..., timeout=timeout)` (`retry=False` on `StructuredOutputException`/`ValueError`, single retry on `ModelThrottledException`/timeout), estimates USD spend via `cost_context.cost_for(in_tok, out_tok, llm_model)`.

---

## 2. Routing Facade, Schema & Complexity Extraction (`strands_code_cli/routing/core.py`)

- **Schema & engine expansion (`D-02`, `D-03`):**
  - `_ENGINE_KEYS |= {"decisions_api_model", "llm_model"}`
  - `RoutingEngine`: add `decisions_api_model: str | None = None` and `llm_model: str | None = None`.
  - `_VALID_ORDER_ENGINES = ("native", "decisions_api", "openrouter", "local", "llm")`
  - `_VALID_PRIMARY_ENGINES = ("openrouter", "local", "decisions_api", "llm", "off")`
  - `_LEGACY_PRIMARY_ORDER`: add `"decisions_api": ["decisions_api"]`, `"llm": ["llm"]`.
  - `_parse_engine()` (`CC 17 -> <= 13`): read optional string fields via loop over `("primary", "decision_model", "local_model", "local_base_url", "native_model", "decisions_api_model", "llm_model")`.
  - `_validate_single_order_engine()` + `_validate_engine_legacy_primary()` (`CC <= 10`):
    - `decisions_api`: optional `decisions_api_model` (defaults cleanly to `DECISIONS_API_DEFAULT_MODEL = "~typesafe/jev-latest"` when omitted, or checks non-empty string if set) → reports `engine: decisions_api model <id> — ok`.
    - `llm`: **requires** non-empty `engine.llm_model` (`order lists llm with no llm_model` + `fix: set engine.llm_model to a provider/model id (for example, google/gemini-3.8-flash)`). Notice `/route validate` performs ZERO network/live pings for `decisions_api` or `llm` (preserving `test_validate_makes_zero_network_calls`!).
  - Engine registry (`_ENGINE_REGISTRY`) preserves indices 0 and 1:
    1. `"openrouter"` → `_openrouter_attempt`
    2. `"local"` → `_ollama_attempt`
    3. `"native"` → `_typesafe_attempt`
    4. `"decisions_api"` → `_decisions_api_attempt` (`decisions_api_engine_ready()`: `bool(os.environ.get("JEV_API_KEY"))`, skips when keyless + emits one-time skip note in `chain_skip_notes`: `"decisions_api engine skipped: JEV_API_KEY not set"`)
    5. `"llm"` → `_llm_attempt` (uses configured `strategy.engine.llm_model`; skips if empty).

- **Preserved mockable seams & calibration (`D-05`, `D-06`):**
  - Re-export constants & `EngineResult` from `transports.py`; delegate `_post_decision`, `_retryable_error`, `_failure_reason`, `_preflight_get`, `decide_via_openrouter`, `decide_via_typesafe`, `decide_via_ollama`, `decide_via_decisions_api`, `decide_via_llm` cleanly so all `core.*` public signatures stay intact.
  - `_validate_choice_shape()`: add `math.isfinite(prob)` + 4-decimal grid tolerance (`1e-6 + 5e-5 * len(probs)` when on `1e-4` grid).
  - Decompose `_run_chain()` (`C 18` -> `B ~11`) and `_decide_effort()` (`C 14` -> `B ~9`) using `_evaluate_model_answer()` and `_evaluate_effort_answer()`:
    - When `result.answers is None`: if `result.uncertain` → short-circuit hold (`None, name, (0, 0, None), f"{name} uncertain"` — zero fallback to next engine or `candidates[0]`, matching below-threshold hold!).
    - When `ans.get("type") == "llm_choice"`: verify `choice in {c.id for c in candidates}` cleanly (invalid → `"invalid table"`), return `(choice, None, False, "")` bypassing `0.62`/`0.04` gate with `model_confidence=None` / `effort_confidence=None`.
  - `decision_model_for()` returns `decisions_api_model or DECISIONS_API_DEFAULT_MODEL` for `"decisions_api"` and `llm_model` for `"llm"`.

---

## 3. Model Switcher & Cost Reporting (`strands_code_cli/model/model_switch.py`, `cost/cost_context.py`)

- **`model_switch.resolve_harness_model(..., *, effort=None, base_url=None, web_search=True, caching=True)`:**
  - When `web_search=False`: omit `kwargs["web_search"]`. Wait — check what `create_harness`/`resolve_model` does when `web_search` is omitted vs `False`: let's verify in code if `resolve_model` defaults `web_search=False`! Only set `kwargs["web_search"] = True` when `web_search and has_search and ...`; only pass `caching=True` when `caching` is True else `caching=False, caching_explicit=True` (and forward `caching=caching` to `build_meta_model`).
- **`cost_context.py` (`price_table` untouched at `CC 20`):**
  - `_routing_line(event)`: omit `" actual"` when `event.get("engine") == "llm"` (`f"{head} ${spend:.4f}"` instead of `f"{head} ${spend:.4f} actual"`).
  - `_fold_routing_events(routing, lines, provenances)`: return `(total_in, total_out, total_actual, has_actual, total_estimated, has_estimated)` — `llm` routing spend increments `total_estimated` & `has_estimated`, and records `price_provenance(decision_model)` in `provenances` cleanly; all other engines increment `total_actual` & `has_actual` unchanged!

---

## 4. Tests, Rigs & Documentation (`tests/`, `docs/`)

- `tests/conftest.py`: add `"TYPESAFE_API_KEY"`, `"JEV_API_KEY"` to `_PROVIDER_ENV_VARS`; skip deletion only when `request.node.get_closest_marker("integration") is not None`.
- `tests/routing/test_routing_transports.py`: direct `DecisionModel.ask()` + OTel span tests + all 5 engines + async active-loop worker bridge + retry matrix + `Uncertain` narrowing + 4-decimal tolerance + `MockTransport`.
- `tests/routing/test_routing.py`: migrate legacy `urlopen` fakes to a single `_mock_httpx(monkeypatch, handler)` helper patching `transports.make_async_client` & `transports.make_sync_client`; keep `test_stub_server_systemone_decision_routes` passing unmodified; add `@pytest.mark.integration` probes for `decisions_api` and `llm`.
- `docs/ROUTING.md` & `docs/QUICKSTART.md`: document `DecisionModel` convergence, `decisions_api` (`JEV_API_KEY` vs `TYPESAFE_API_KEY` distinction, `~typesafe/jev-latest` vs `noul`-only `respan/span-01-lite:free`), and `llm` (`LLMDecisionModel`, `uncertainty=True`, estimated `/cost`), keeping `test_docs_routing_examples_validate_verbatim` green.

---
*Phase: 17-decision-routing-convergence-decisionmodel*
