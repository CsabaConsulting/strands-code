"""Hermetic unit tests for DecisionModel routing transports (UPSTREAM-02)."""

from __future__ import annotations

import asyncio
import errno
import json
from typing import Any

import httpx
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from strands.decisions import DecisionResult, Question, Uncertain
from strands.decisions.types import DecisionMetadata
from strands.types.exceptions import (
    ContextWindowOverflowException,
    ModelThrottledException,
    StructuredOutputException,
)

import strands_code_cli.routing.transports as transports
from strands_code_cli.routing.transports import (
    DECISION_BODY_MAX_BYTES,
    OLLAMA_KEEP_ALIVE,
    OPENROUTER_DECISIONS_URL,
    TYPESAFE_DECISIONS_URL,
    TYPESAFE_INPUT_USD_PER_MTOK,
    OllamaDecisionModel,
    OpenRouterDecisionModel,
    build_folded_state_and_questions,
    build_sdk_questions_and_criteria,
    decision_result_to_engine_result,
    failure_reason,
    is_retryable_decision_error,
    run_decision_sync,
    run_ollama_decision,
    run_openrouter_decision,
    run_typesafe_decision,
)


def _patch_httpx(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        transports,
        "make_async_client",
        lambda timeout, headers=None: httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(timeout),
            headers=headers or {},
        ),
    )
    monkeypatch.setattr(
        transports,
        "make_sync_client",
        lambda timeout: httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(timeout),
        ),
    )


def _choice_payload(
    *,
    key: str = "pick_model",
    choice: str = "a/1",
    probs: dict[str, float] | None = None,
    confidence: float | None = 0.85,
    cost: float | None = 0.0001,
    model: str | None = "snapshot-1",
) -> dict[str, Any]:
    answer: dict[str, Any] = {
        "type": "choice",
        "choice": choice,
        "probabilities": probs or {"a/1": 0.85, "b/2": 0.15},
    }
    if confidence is not None:
        answer["confidence"] = confidence
    usage: dict[str, Any] = {"input_tokens": 120, "output_tokens": 18}
    if cost is not None:
        usage["cost"] = cost
    body: dict[str, Any] = {"answers": {key: answer}, "usage": usage}
    if model is not None:
        body["model"] = model
    return body


def _model_raw_questions() -> dict[str, Any]:
    return {
        "pick_model": {
            "type": "choice",
            "instructions": "Which candidate model should serve the ask?",
            "criteria": {
                "a/1": "Cheap model for trivial asks",
                "b/2": "Deep model for complex work",
            },
        }
    }


def _effort_raw_questions() -> dict[str, Any]:
    return {
        "pick_effort": {
            "type": "choice",
            "instructions": "How much thinking budget?",
            "criteria": {
                "low": "Light thinking",
                "high": "Deep thinking",
            },
        }
    }


class TestDecisionModelOtelAndSubclasses:
    def test_openrouter_decision_model_records_otel_span_and_criteria(
        self, monkeypatch
    ):
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))

        class _FakeTracer:
            def __init__(self, inner) -> None:
                self.tracer = inner

        import strands.decisions.decision_model as dm_mod

        monkeypatch.setattr(
            dm_mod, "get_tracer", lambda: _FakeTracer(provider.get_tracer(__name__))
        )

        seen: list[dict[str, Any]] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            seen.append(
                {
                    "url": str(request.url),
                    "body": json.loads(request.content.decode("utf-8")),
                    "auth": request.headers.get("authorization"),
                }
            )
            return httpx.Response(
                200, json=_choice_payload(confidence=None, cost=0.002)
            )

        _patch_httpx(monkeypatch, _handler)
        dm = OpenRouterDecisionModel(api_key="or-secret", model_id="cheap/decider")
        raw_q = _model_raw_questions()
        sdk_q, _ = build_sdk_questions_and_criteria(raw_q, uncertainty=False)
        raw_state = {"ask": "hello", "directives": "cheap", "side": False}

        result = asyncio.run(
            dm.ask(
                json.dumps(raw_state),
                sdk_q,
                raw_state=raw_state,
                raw_questions=raw_q,
            )
        )

        assert result.answers == {"pick_model": "a/1"}
        assert result.metadata.probabilities == {
            "pick_model": {"a/1": 0.85, "b/2": 0.15}
        }
        assert result.metadata.confidence == {"pick_model": 0.85}
        assert result.usage == {
            "inputTokens": 120,
            "outputTokens": 18,
            "totalTokens": 138,
        }
        assert dm.last_cost == 0.002
        assert dm.last_truncated is False
        assert seen[0]["url"] == OPENROUTER_DECISIONS_URL
        assert seen[0]["auth"] == "Bearer " + "or-secret"
        assert seen[0]["body"]["questions"]["pick_model"]["criteria"] == {
            "a/1": "Cheap model for trivial asks",
            "b/2": "Deep model for complex work",
        }

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "decision"
        assert spans[0].attributes["gen_ai.operation.name"] == "decision"
        assert list(spans[0].attributes["gen_ai.decision.questions"]) == ["pick_model"]
        assert json.loads(spans[0].attributes["gen_ai.decision.answers"]) == {
            "pick_model": "a/1"
        }

    def test_openrouter_decision_model_direct_sdk_invocation_and_unlisted_effort(
        self, monkeypatch
    ):
        seen: list[dict[str, Any]] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            seen.append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(
                200,
                json=_choice_payload(
                    key="pick_effort",
                    choice="max",
                    probs={"low": 0.15, "max": 0.85},
                    confidence=0.85,
                    cost=False,  # type: ignore[arg-type]
                ),
            )

        _patch_httpx(monkeypatch, _handler)
        dm = OpenRouterDecisionModel(api_key="or-secret", model_id="cheap/decider")
        q: dict[str, Question] = {
            "pick_effort": {
                "question": "Effort level?",
                "choices": ["low", "high"],
                "uncertainty": False,
            }
        }
        result = asyncio.run(dm.ask("fix bug", q, allow_unlisted_choices=True))
        assert result.answers["pick_effort"] == "max"
        assert dm.last_cost is None  # bool cost ignored safely
        assert seen[0]["state"] == "fix bug"
        assert seen[0]["questions"]["pick_effort"]["criteria"] == {
            "low": "low",
            "high": "high",
        }

    def test_ollama_decision_model_loopback_and_proxied_auth(self, monkeypatch):
        calls: list[dict[str, Any]] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            calls.append(
                {
                    "url": str(request.url),
                    "auth": request.headers.get("authorization"),
                    "body": json.loads(request.content.decode("utf-8")),
                }
            )
            return httpx.Response(200, json=_choice_payload(cost=None))

        _patch_httpx(monkeypatch, _handler)
        monkeypatch.setenv("OLLAMA_API_KEY", "ollama-secret")

        local_res = run_ollama_decision(
            local_model="nimble",
            local_base_url="http://127.0.0.1:11434",
            state={"ask": "hi", "directives": "d", "side": False},
            questions=_model_raw_questions(),
        )
        assert local_res.answers is not None
        assert local_res.cost is None
        assert calls[0]["url"] == "http://127.0.0.1:11434/v1/systemone"
        assert calls[0]["auth"] is None
        assert calls[0]["body"]["keep_alive"] == OLLAMA_KEEP_ALIVE

        proxied_res = run_ollama_decision(
            local_model="nimble",
            local_base_url="https://ollama.internal:11434/",
            state={"ask": "hi", "directives": "d", "side": False},
            questions=_model_raw_questions(),
        )
        assert proxied_res.answers is not None
        assert calls[1]["url"] == "https://ollama.internal:11434/v1/systemone"
        assert calls[1]["auth"] == "Bearer " + "ollama-secret"

        bad = run_ollama_decision(
            local_model="nimble",
            local_base_url="ftp://bad.invalid",
            state={"ask": "hi"},
            questions=_model_raw_questions(),
        )
        assert bad.answers is None

        dm = OllamaDecisionModel(model_id="nimble", base_url="http://127.0.0.1:11434")
        sdk_q, _ = build_sdk_questions_and_criteria(_model_raw_questions())
        direct = asyncio.run(dm.ask("hello", sdk_q))
        assert direct.answers["pick_model"] == "a/1"
        assert direct.metadata.provider_name == "ollama"


class TestFoldedStateAndTypeSafeBridge:
    def test_build_folded_state_and_questions_shrinks_ask_within_64k(self):
        long_ask = "a" * 100_000
        state_str, questions, truncated = build_folded_state_and_questions(
            {"ask": long_ask, "directives": "be brief", "side": False},
            _model_raw_questions(),
            model_id="jev-1.13.0",
        )
        assert truncated is True
        decoded = json.loads(state_str)
        assert decoded["directives"] == "be brief"
        assert len(decoded["ask"]) < len(long_ask)
        assert "Cheap model for trivial asks" in questions["pick_model"]["question"]
        assert questions["pick_model"]["uncertainty"] is False
        wire_payload = {
            "state": state_str,
            "model": "jev-1.13.0",
            "questions": {
                "pick_model": {
                    "type": "choice",
                    "instructions": questions["pick_model"]["question"],
                    "criteria": {"a/1": None, "b/2": None},
                }
            },
        }
        assert len(json.dumps(wire_payload).encode("utf-8")) <= DECISION_BODY_MAX_BYTES

    def test_run_typesafe_decision_uses_per_call_client_4dec_tolerance_and_flat_cost(
        self, monkeypatch
    ):
        monkeypatch.setenv("TYPESAFE_API_KEY", "ts-secret")
        captured: list[dict[str, Any]] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            captured.append(
                {
                    "url": str(request.url),
                    "auth": request.headers.get("authorization"),
                    "body": json.loads(request.content.decode("utf-8")),
                }
            )
            return httpx.Response(
                200,
                json={
                    "model": "jev-1.13.0",
                    "answers": {
                        "pick_model": {
                            "type": "choice",
                            "choice": "a/1",
                            # 4-decimal grid summing to 0.9999
                            "probabilities": {
                                "a/1": 0.3333,
                                "b/2": 0.3333,
                                "c/3": 0.3333,
                            },
                            "confidence": 0.3333,
                        }
                    },
                    "usage": {"input_tokens": 500, "output_tokens": 20},
                },
            )

        _patch_httpx(monkeypatch, _handler)
        raw_q = {
            "pick_model": {
                "type": "choice",
                "instructions": "Pick one",
                "criteria": {"a/1": "first", "b/2": "second", "c/3": "third"},
            }
        }
        result = run_typesafe_decision(
            native_model="jev-1.13.0",
            state={"ask": "hi", "directives": "d", "side": False},
            questions=raw_q,
        )
        assert result.answers is not None
        assert result.answers["pick_model"]["choice"] == "a/1"
        assert result.input_tokens == 500
        assert result.output_tokens == 20
        assert result.cost == pytest.approx(
            500 * TYPESAFE_INPUT_USD_PER_MTOK / 1_000_000
        )
        assert captured[0]["url"] == TYPESAFE_DECISIONS_URL
        assert captured[0]["auth"] == "Bearer " + "ts-secret"
        assert isinstance(captured[0]["body"]["state"], str)
        assert captured[0]["body"]["questions"]["pick_model"]["criteria"] == {
            "a/1": None,
            "b/2": None,
            "c/3": None,
        }
        assert "first" in captured[0]["body"]["questions"]["pick_model"]["instructions"]

    def test_run_openrouter_decision_caps_body_to_64k(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-secret")
        bodies: list[bytes] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            bodies.append(request.content)
            return httpx.Response(200, json=_choice_payload())

        _patch_httpx(monkeypatch, _handler)
        res = run_openrouter_decision(
            decision_model="cheap/decider",
            state={"ask": "z" * 120_000, "directives": "d", "side": False},
            questions=_model_raw_questions(),
        )
        assert res.truncated is True
        assert len(bodies[0]) <= DECISION_BODY_MAX_BYTES


class TestUncertainNarrowingAndAsyncBridge:
    def test_decision_result_to_engine_result_narrows_uncertain_explicitly(self):
        unc = Uncertain("too close to call")
        assert bool(unc) is True  # truthy sentinel: must use isinstance!
        dr = DecisionResult(
            answers={"pick_model": unc},
            metadata=DecisionMetadata(latency_ms=12, model_id="m"),
            usage={"inputTokens": 40, "outputTokens": 5, "totalTokens": 45},
        )
        er = decision_result_to_engine_result(
            dr, raw_questions=_model_raw_questions(), cost=None, truncated=False
        )
        assert er.answers is None
        assert er.uncertain is True
        assert er.error == "too close to call"
        assert er.input_tokens == 40

    def test_run_decision_sync_works_inside_active_event_loop(self):
        async def _inner() -> str:
            await asyncio.sleep(0)
            return "ok"

        async def _outer() -> str:
            return run_decision_sync(_inner, retry=False)

        assert asyncio.run(_outer()) == "ok"

    def test_retry_and_failure_classification_contracts(self):
        req = httpx.Request("POST", OPENROUTER_DECISIONS_URL)
        r429 = httpx.Response(429, request=req)
        r500 = httpx.Response(500, request=req)
        r401 = httpx.Response(401, request=req)
        r413 = httpx.Response(413, request=req)

        throttled = ModelThrottledException("rate limited")
        throttled.__cause__ = httpx.HTTPStatusError("429", request=req, response=r429)
        assert is_retryable_decision_error(throttled) is True
        assert failure_reason(throttled) == "HTTP 429"

        assert (
            is_retryable_decision_error(
                httpx.HTTPStatusError("500", request=req, response=r500)
            )
            is True
        )
        assert (
            is_retryable_decision_error(
                httpx.HTTPStatusError("401", request=req, response=r401)
            )
            is False
        )
        assert (
            failure_reason(httpx.HTTPStatusError("401", request=req, response=r401))
            == "HTTP 401"
        )

        assert (
            is_retryable_decision_error(httpx.ReadTimeout("slow", request=req)) is True
        )
        assert failure_reason(httpx.ReadTimeout("slow", request=req)) == "timeout"

        refused_exc = httpx.ConnectError("Connection refused", request=req)
        refused_exc.__cause__ = ConnectionRefusedError(
            errno.ECONNREFUSED, "Connection refused"
        )
        assert is_retryable_decision_error(refused_exc) is False
        assert failure_reason(refused_exc) == "refused"

        unreach_exc = httpx.ConnectError("Name or service not known", request=req)
        assert is_retryable_decision_error(unreach_exc) is False
        assert failure_reason(unreach_exc) == "unreachable"

        overflow = ContextWindowOverflowException("too big")
        overflow.__cause__ = httpx.HTTPStatusError("413", request=req, response=r413)
        assert is_retryable_decision_error(overflow) is False
        assert failure_reason(overflow) == "HTTP 413"

        body_err = StructuredOutputException(
            "decision provider response must be an object"
        )
        table_err = StructuredOutputException(
            "decision provider omitted answer for question id=<pick_model>"
        )
        assert is_retryable_decision_error(body_err) is False
        assert failure_reason(body_err) == "invalid body"
        assert failure_reason(table_err) == "invalid table"

    def test_run_decision_sync_retries_once_on_throttle_not_on_connect_error(self):
        attempts: list[int] = []
        req = httpx.Request("POST", OPENROUTER_DECISIONS_URL)

        async def _flaky() -> str:
            attempts.append(1)
            if len(attempts) == 1:
                raise ModelThrottledException("retry me")
            return "recovered"

        assert run_decision_sync(_flaky, retry=True) == "recovered"
        assert len(attempts) == 2

        conn_attempts: list[int] = []

        async def _refused() -> str:
            conn_attempts.append(1)
            raise httpx.ConnectError("Connection refused", request=req)

        with pytest.raises(httpx.ConnectError):
            run_decision_sync(_refused, retry=True)
        assert len(conn_attempts) == 1

    def test_invalid_questions_fail_closed_across_transports(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-secret")
        monkeypatch.setenv("TYPESAFE_API_KEY", "ts-secret")

        def _boom(request: httpx.Request) -> httpx.Response:
            raise AssertionError("invalid questions must fail before HTTP send")

        _patch_httpx(monkeypatch, _boom)
        bad_uncertain = {
            "pick_model": {
                "type": "choice",
                "instructions": "Pick one",
                "criteria": {"a/1": "first", "uncertain": "ambiguous"},
            }
        }
        for bad_questions in ({}, bad_uncertain):
            or_res = run_openrouter_decision(
                decision_model="cheap/decider",
                state={"ask": "hi"},
                questions=bad_questions,
            )
            ol_res = run_ollama_decision(
                local_model="nimble",
                local_base_url="http://127.0.0.1:11434",
                state={"ask": "hi"},
                questions=bad_questions,
            )
            ts_res = run_typesafe_decision(
                native_model="jev-1.13.0",
                state={"ask": "hi"},
                questions=bad_questions,
            )
            for res in (or_res, ol_res, ts_res):
                assert res.answers is None
                assert res.error == "invalid body"
