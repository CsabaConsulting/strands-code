"""DecisionModel transport layer for strands-code routing (UPSTREAM-02).

Converges OpenRouter, Ollama System One, TypeSafe native Jev, decisionapi.net,
and LLM structured-output routing behind ``strands.decisions.DecisionModel``
while preserving 64 KiB body fitting, per-call httpx timeouts, explicit
``Uncertain`` narrowing, and async-to-sync bridging across REPL & ``/btw`` threads.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import errno
import ipaddress
import json
import logging
import math
import os
import socket
import time
import urllib.error
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar
from urllib.parse import urlsplit

import httpx
from strands.decisions import (
    DecisionInput,
    DecisionModel,
    DecisionResult,
    Question,
    Uncertain,
)
from strands.decisions.types import DecisionMetadata
from strands.types.event_loop import Usage
from strands.types.exceptions import (
    ContextWindowOverflowException,
    ModelThrottledException,
    StructuredOutputException,
)

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

ASK_TRUNCATE_CHARS = 2000
DECISION_TIMEOUT_SECONDS = 10
OPENROUTER_DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
TYPESAFE_DECISIONS_URL = "https://api.typesafe.ai/v1/systemone"
DECISIONS_API_URL = "https://decisionapi.net/v1/systemone"
DECISIONS_API_DEFAULT_MODEL = "~typesafe/jev-latest"
TYPESAFE_INPUT_USD_PER_MTOK = 0.042
OLLAMA_DEFAULT_HOST = "http://127.0.0.1:11434"
OLLAMA_TIMEOUT_SECONDS = 30
OLLAMA_KEEP_ALIVE = "5m"
OLLAMA_PREFLIGHT_TIMEOUT_SECONDS = 5
DECISION_BODY_MAX_BYTES = 64 * 1024
TRUNCATION_MARKER = "ask truncated to fit the decision cap"

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 524, 529})
_THROTTLE_STATUS = frozenset({429, 503, 529})
_OLLAMA_LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")
_PROBABILITY_TOLERANCE = 1e-6
_PROBABILITY_ROUNDING_TOLERANCE = 5e-5


@dataclass(frozen=True)
class EngineResult:
    """One engine try: typed answers plus usage triple plus snapshot."""

    answers: dict[str, Any] | None
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float | None = None
    model: str | None = None
    error: str | None = None
    truncated: bool = False
    uncertain: bool = False


def _has_unsafe_chars(value: str) -> bool:
    return any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value)


def valid_model_id(value: object) -> bool:
    """True when a model id is a non-empty string without whitespace/controls."""
    return isinstance(value, str) and bool(value) and not _has_unsafe_chars(value)


def read_env_api_key(name: str) -> str | None:
    """Read an env API key cleanly, rejecting empty or control-containing values."""
    raw = os.environ.get(name)
    if not raw:
        return None
    cleaned = raw.strip()
    if not cleaned or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in cleaned):
        return None
    return cleaned


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"invalid JSON constant: {value}")


def _sanitize_uncertain_reason(reason: str | None) -> str:
    """Strip control characters and bound length on untrusted Uncertain.reason."""
    if not isinstance(reason, str):
        return "uncertain"
    cleaned = "".join(ch for ch in reason if ord(ch) >= 0x20 and ord(ch) != 0x7F)
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        return "uncertain"
    return cleaned[:200]


def valid_base_url(value: str) -> bool:
    """True for http(s) URLs with host and no credentials, query, or fragment."""
    if not isinstance(value, str) or not value or _has_unsafe_chars(value):
        return False
    try:
        parts = urlsplit(value)
        _ = parts.port
    except ValueError:
        return False
    return (
        parts.scheme.lower() in ("http", "https")
        and bool(parts.hostname)
        and parts.username is None
        and parts.password is None
        and not parts.query
        and not parts.fragment
    )


def make_async_client(
    timeout: float, headers: dict[str, str] | None = None
) -> httpx.AsyncClient:
    """Create a per-call AsyncClient so closed event loops never leak across asks."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout),
        headers=headers or {},
        follow_redirects=False,
    )


def make_sync_client(timeout: float) -> httpx.Client:
    """Create a short-lived sync httpx Client for Ollama preflight GETs."""
    return httpx.Client(timeout=httpx.Timeout(timeout), follow_redirects=False)


def preflight_get(url: str, headers: dict[str, str]) -> dict[str, Any] | None:
    """One daemon preflight GET: parsed mapping or None on any failure."""
    if not valid_base_url(url):
        return None
    try:
        with make_sync_client(OLLAMA_PREFLIGHT_TIMEOUT_SECONDS) as client:
            response = client.get(url, headers=headers)
        if not response.is_success:
            return None
        data = json.loads(response.text, parse_constant=_reject_json_constant)
    except Exception:  # noqa: BLE001 — every preflight failure reads unready
        return None
    return data if isinstance(data, dict) else None


def ollama_base(local_base_url: str | None) -> str:
    """Daemon root: strategy URL, else the harness host, else loopback."""
    return local_base_url or os.environ.get("OLLAMA_HOST") or OLLAMA_DEFAULT_HOST


def _is_ip_loopback_or_unspecified(folded: str) -> bool:
    try:
        addr = ipaddress.ip_address(folded)
        if addr.is_loopback or addr.is_unspecified:
            return True
        mapped = getattr(addr, "ipv4_mapped", None)
        return bool(
            mapped is not None and (mapped.is_loopback or mapped.is_unspecified)
        )
    except ValueError:
        try:
            packed = socket.inet_aton(folded)
        except OSError:
            return False
        ipv4 = ipaddress.IPv4Address(packed)
        return bool(ipv4.is_loopback or ipv4.is_unspecified)


def _is_loopback_host(base: str) -> bool:
    """True when URL resolves to loopback/unspecified (fail-closed on malformed URL)."""
    try:
        host = urlsplit(base).hostname
    except ValueError:
        return True
    if not host:
        return True
    folded = host.rstrip(".").lower()
    if folded == "localhost" or folded.endswith(".localhost"):
        return True
    return _is_ip_loopback_or_unspecified(folded)


def ollama_headers(base: str) -> dict[str, str]:
    """Local daemon headers; bearer key attaches on HTTPS non-loopback proxies only."""
    headers = {"Content-Type": "application/json", "User-Agent": "strands-code"}
    if not valid_base_url(base):
        return headers
    if urlsplit(base).scheme.lower() != "https":
        return headers
    api_key = read_env_api_key("OLLAMA_API_KEY")
    if api_key and not _is_loopback_host(base):
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _count(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _cost(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if (
        isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value) >= 0.0
    ):
        return float(value)
    return None


def _is_refused(exc: BaseException) -> bool:
    seen: list[BaseException | None] = [exc, exc.__cause__, exc.__context__]
    for err in seen:
        if err is None:
            continue
        if isinstance(err, ConnectionRefusedError):
            return True
        if isinstance(err, OSError) and err.errno == errno.ECONNREFUSED:
            return True
        if "connection refused" in str(err).lower():
            return True
    return False


def is_retryable_decision_error(exc: BaseException) -> bool:
    """True for the single-retry class (429/5xx throttling and timeouts only)."""
    if isinstance(exc, ModelThrottledException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return True
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in _RETRYABLE_STATUS
    if isinstance(exc, urllib.error.URLError):
        return isinstance(exc.reason, TimeoutError)
    return False


def _structured_error_class(exc: StructuredOutputException) -> str:
    msg = str(exc).lower()
    body_tokens = (
        "invalid body",
        "non-json",
        "response must be",
        "model must be",
        "answers must be",
        "error code",
    )
    if any(token in msg for token in body_tokens):
        return "invalid body"
    return "invalid table"


def failure_reason(exc: BaseException) -> str:
    """Short failure class for one transport exception (never leaks secrets)."""
    if isinstance(exc, (ModelThrottledException, ContextWindowOverflowException)):
        cause = exc.__cause__
        if isinstance(cause, httpx.HTTPStatusError):
            return f"HTTP {cause.response.status_code}"
        if isinstance(exc, ContextWindowOverflowException):
            return "HTTP 413"
        return "HTTP 429"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return "timeout"
    if isinstance(exc, httpx.ConnectError):
        return "refused" if _is_refused(exc) else "unreachable"
    if isinstance(exc, urllib.error.URLError):
        if isinstance(exc.reason, TimeoutError):
            return "timeout"
        return "refused" if _is_refused(exc) else "unreachable"
    if isinstance(exc, (ConnectionError, OSError)):
        return "refused" if _is_refused(exc) else "unreachable"
    if isinstance(exc, StructuredOutputException):
        return _structured_error_class(exc)
    if isinstance(exc, ValueError):
        return "invalid body"
    return "error"


def _run_coro_sync(coro_factory: Callable[[], Awaitable[_T]]) -> _T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro_factory())).result()


def run_decision_sync(
    coro_factory: Callable[[], Awaitable[_T]], *, retry: bool = True
) -> _T:
    """Run an async DecisionModel call synchronously, retrying once if retryable."""
    attempts = 2 if retry else 1
    for attempt_no in range(attempts):
        try:
            return _run_coro_sync(coro_factory)
        except Exception as exc:
            if attempt_no + 1 < attempts and is_retryable_decision_error(exc):
                continue
            raise
    raise AssertionError("unreachable")


def _truncate_ask_binary(
    ask: str, measure_bytes: Callable[[str], int], max_bytes: int
) -> str:
    """Binary-search longest Unicode prefix of ``ask`` fitting within ``max_bytes``."""
    if measure_bytes("") > max_bytes:
        return ""
    lo = 0
    hi = len(ask)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if measure_bytes(ask[:mid]) <= max_bytes:
            lo = mid
        else:
            hi = mid - 1
    return ask[:lo]


def fit_decision_payload(
    payload: dict[str, Any], *, strict: bool = False
) -> tuple[dict[str, Any], bool]:
    """Shrink state.ask until serialized bytes fit DECISION_BODY_MAX_BYTES."""
    body = json.dumps(payload).encode("utf-8")
    if len(body) <= DECISION_BODY_MAX_BYTES:
        return payload, False
    state = payload.get("state")
    ask = state.get("ask") if isinstance(state, dict) else None
    if not isinstance(state, dict) or not isinstance(ask, str) or not ask:
        if strict:
            raise ValueError("Decision payload exceeds size limit")
        return payload, False

    def _measure(cand: str) -> int:
        trial = {**payload, "state": {**state, "ask": cand}}
        return len(json.dumps(trial).encode("utf-8"))

    fitted_ask = _truncate_ask_binary(ask, _measure, DECISION_BODY_MAX_BYTES)
    if strict and _measure(fitted_ask) > DECISION_BODY_MAX_BYTES:
        raise ValueError("Decision payload exceeds size limit")
    shrunk = dict(payload)
    shrunk["state"] = {**state, "ask": fitted_ask}
    return shrunk, True


def _raw_question_choices_and_text(
    q_id: str, raw_q: Any
) -> tuple[str, list[str], dict[str, str]]:
    if not isinstance(raw_q, dict):
        return q_id, [], {}
    instructions = raw_q.get("instructions") or raw_q.get("question") or q_id
    raw_criteria = raw_q.get("criteria")
    criteria: dict[str, str] = {}
    if isinstance(raw_criteria, dict):
        for choice, prose in raw_criteria.items():
            criteria[str(choice)] = (
                prose if isinstance(prose, str) and prose.strip() else str(choice)
            )
    return str(instructions), list(criteria), criteria


def build_sdk_questions_and_criteria(
    raw_questions: dict[str, Any], *, uncertainty: bool = False
) -> tuple[dict[str, Question], dict[str, dict[str, str]]]:
    """Translate System One question maps to SDK ``Question`` objects + criteria."""
    sdk_questions: dict[str, Question] = {}
    criteria_by_q: dict[str, dict[str, str]] = {}
    for q_id, raw_q in raw_questions.items():
        text, choices, criteria = _raw_question_choices_and_text(q_id, raw_q)
        if not choices:
            raise ValueError(
                f"question id=<{q_id}> requires non-empty criteria choices"
            )
        sdk_questions[q_id] = Question(
            question=text, choices=choices, uncertainty=uncertainty
        )
        criteria_by_q[q_id] = criteria
    return sdk_questions, criteria_by_q


def build_folded_state_and_questions(
    state: dict[str, Any],
    raw_questions: dict[str, Any],
    *,
    model_id: str | None = None,
    uncertainty: bool = False,
    max_bytes: int = DECISION_BODY_MAX_BYTES,
    strict: bool = False,
) -> tuple[str, dict[str, Question], bool]:
    """Fold ``{ask, directives, side}`` + criteria into SDK ``(state_str, questions)``."""
    questions: dict[str, Question] = {}
    wire_questions: dict[str, Any] = {}
    for q_id, raw_q in raw_questions.items():
        text, choices, criteria = _raw_question_choices_and_text(q_id, raw_q)
        if not choices:
            raise ValueError(
                f"question id=<{q_id}> requires non-empty criteria choices"
            )
        option_lines = [f"- {choice}: {criteria[choice]}" for choice in choices]
        folded = f"{text}\nOptions:\n" + "\n".join(option_lines)
        questions[q_id] = Question(
            question=folded, choices=choices, uncertainty=uncertainty
        )
        wire_questions[q_id] = {
            "type": "choice",
            "instructions": folded,
            "criteria": {choice: None for choice in choices},
        }

    compact_state = dict(state)
    state_str = json.dumps(compact_state, ensure_ascii=False, separators=(",", ":"))
    envelope: dict[str, Any] = {"state": state_str, "questions": wire_questions}
    if model_id is not None:
        envelope["model"] = model_id

    def _envelope_size(cand_envelope: dict[str, Any]) -> int:
        compact = json.dumps(
            cand_envelope, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        default = json.dumps(cand_envelope).encode("utf-8")
        return max(len(compact), len(default))

    if _envelope_size(envelope) <= max_bytes:
        return state_str, questions, False

    ask = compact_state.get("ask")
    if not isinstance(ask, str) or not ask:
        if strict:
            raise ValueError("Decision payload exceeds size limit")
        return state_str, questions, False

    def _measure(cand: str) -> int:
        cand_state = json.dumps(
            {**compact_state, "ask": cand}, ensure_ascii=False, separators=(",", ":")
        )
        return _envelope_size({**envelope, "state": cand_state})

    fitted_ask = _truncate_ask_binary(ask, _measure, max_bytes)
    compact_state = {**compact_state, "ask": fitted_ask}
    state_str = json.dumps(compact_state, ensure_ascii=False, separators=(",", ":"))
    if strict and _measure(fitted_ask) > max_bytes:
        raise ValueError("Decision payload exceeds size limit")
    return state_str, questions, True


def _sdk_to_wire_questions(questions: dict[str, Question]) -> dict[str, dict[str, Any]]:
    wire: dict[str, dict[str, Any]] = {}
    for q_id, q in questions.items():
        choices = q["choices"]
        if choices == "boolean":
            wire[q_id] = {"type": "noul", "instructions": q["question"]}
            continue
        wire[q_id] = {
            "type": "choice",
            "instructions": q["question"],
            "criteria": {choice: choice for choice in choices},
        }
    return wire


def _is_unit_probability(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    fval = float(value)
    return math.isfinite(fval) and 0.0 <= fval <= 1.0


def _parse_probabilities_table(raw_probs: Any, q_id: str) -> dict[str, float]:
    if not isinstance(raw_probs, dict) or not raw_probs:
        raise StructuredOutputException(
            f"invalid table: probabilities for question id=<{q_id}> missing"
        )
    probs: dict[str, float] = {}
    for label, prob in raw_probs.items():
        if not _is_unit_probability(prob):
            raise StructuredOutputException(
                f"invalid table: invalid probability in id=<{q_id}>"
            )
        probs[str(label)] = float(prob)
    vals = probs.values()
    rounded = all(abs(p * 1e4 - round(p * 1e4)) < 1e-6 for p in vals)
    tol = min(
        0.01,
        _PROBABILITY_TOLERANCE
        + (len(probs) * _PROBABILITY_ROUNDING_TOLERANCE if rounded else 0.0),
    )
    if abs(sum(vals) - 1.0) > tol:
        raise StructuredOutputException(
            f"invalid table: probabilities for question id=<{q_id}> must sum to 1"
        )
    return probs


def _parse_custom_choice_answer(
    raw_answer: Any,
    choices: list[str] | str,
    q_id: str,
    *,
    allow_unlisted_choices: bool,
) -> tuple[str, dict[str, float], float]:
    if not isinstance(raw_answer, dict) or raw_answer.get("type") != "choice":
        raise StructuredOutputException(
            f"invalid table: answer for question id=<{q_id}> must have type 'choice'"
        )
    probs = _parse_probabilities_table(raw_answer.get("probabilities"), q_id)
    choice = raw_answer.get("choice")
    if not isinstance(choice, str) or choice not in probs:
        raise StructuredOutputException(
            f"invalid table: choice for question id=<{q_id}> missing from table"
        )
    if (
        not allow_unlisted_choices
        and isinstance(choices, list)
        and (choice not in choices or any(k not in choices for k in probs))
    ):
        raise StructuredOutputException(
            f"invalid table: choice {choice!r} outside allowed set for id=<{q_id}>"
        )
    conf = raw_answer.get("confidence")
    conf_val = float(conf) if _is_unit_probability(conf) else probs[choice]
    return choice, probs, conf_val


def _parse_system_one_payload(
    response: httpx.Response,
    questions: dict[str, Question],
    *,
    allow_unlisted_choices: bool,
    provider_name: str,
) -> tuple[
    dict[str, bool | str | Uncertain],
    dict[str, dict[str, float]],
    dict[str, float],
    Usage | None,
    float | None,
    str | None,
]:
    if not response.is_success:
        status = response.status_code
        http_err = httpx.HTTPStatusError(
            f"{provider_name} decision request failed with HTTP {status}",
            request=response.request,
            response=response,
        )
        if status == 413:
            raise ContextWindowOverflowException(str(http_err)) from http_err
        if status in _THROTTLE_STATUS:
            raise ModelThrottledException(str(http_err)) from http_err
        raise http_err
    try:
        payload = json.loads(response.text, parse_constant=_reject_json_constant)
    except ValueError as exc:
        raise StructuredOutputException("invalid body: non-JSON response") from exc
    if not isinstance(payload, dict):
        raise StructuredOutputException("invalid body: response must be an object")
    raw_answers = payload.get("answers")
    if not isinstance(raw_answers, dict):
        raise StructuredOutputException("invalid body: answers must be an object")

    answers: dict[str, bool | str | Uncertain] = {}
    probabilities: dict[str, dict[str, float]] = {}
    confidence: dict[str, float] = {}
    for q_id, question in questions.items():
        if q_id not in raw_answers:
            raise StructuredOutputException(
                f"invalid table: omitted answer for question id=<{q_id}>"
            )
        choice, probs, conf = _parse_custom_choice_answer(
            raw_answers[q_id],
            question["choices"],
            q_id,
            allow_unlisted_choices=allow_unlisted_choices,
        )
        answers[q_id] = choice
        probabilities[q_id] = probs
        confidence[q_id] = conf

    raw_usage = payload.get("usage")
    usage_obj: Usage | None = None
    reported_cost: float | None = None
    if isinstance(raw_usage, dict):
        in_tok = _count(raw_usage.get("input_tokens"))
        out_tok = _count(raw_usage.get("output_tokens"))
        usage_obj = Usage(
            inputTokens=in_tok, outputTokens=out_tok, totalTokens=in_tok + out_tok
        )
        reported_cost = _cost(raw_usage.get("cost"))
    raw_model = payload.get("model")
    reported_model = raw_model if isinstance(raw_model, str) else None
    return answers, probabilities, confidence, usage_obj, reported_cost, reported_model


class _SystemOneCustomDecisionModel(DecisionModel):
    """Base DecisionModel for OpenRouter and Ollama System One endpoints."""

    def __init__(
        self,
        *,
        provider_name: str,
        endpoint: str,
        model_id: str,
        headers: dict[str, str],
        timeout: float,
        extra_payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self._provider_name = provider_name
        self._endpoint = endpoint
        self._model_id = model_id
        self._headers = headers
        self._timeout = timeout
        self._extra_payload = extra_payload or {}
        self.last_truncated = False
        self.last_cost: float | None = None
        self.last_reported_model: str | None = None

    async def _ask(
        self, state: DecisionInput, questions: dict[str, Question], **kwargs: Any
    ) -> DecisionResult:
        self.last_truncated = False
        self.last_cost = None
        self.last_reported_model = None
        wire_state = kwargs.get("raw_state", state)
        raw_questions = kwargs.get("raw_questions")
        wire_questions = (
            raw_questions
            if isinstance(raw_questions, dict)
            else _sdk_to_wire_questions(questions)
        )
        payload: dict[str, Any] = {
            "model": self._model_id,
            "state": wire_state,
            "questions": wire_questions,
            **self._extra_payload,
        }
        fitted, truncated = fit_decision_payload(payload, strict=True)
        self.last_truncated = truncated
        body = json.dumps(fitted).encode("utf-8")

        started_at = time.perf_counter()
        async with make_async_client(self._timeout) as client:
            response = await client.post(
                self._endpoint, headers=self._headers, content=body
            )
        (
            answers,
            probabilities,
            confidence,
            usage,
            reported_cost,
            reported_model,
        ) = _parse_system_one_payload(
            response,
            questions,
            allow_unlisted_choices=bool(kwargs.get("allow_unlisted_choices", False)),
            provider_name=self._provider_name,
        )
        self.last_cost = reported_cost
        self.last_reported_model = reported_model
        latency_ms = round((time.perf_counter() - started_at) * 1000)
        return DecisionResult(
            answers=answers,
            usage=usage,
            metadata=DecisionMetadata(
                latency_ms=latency_ms,
                provider_name=self._provider_name,
                model_id=reported_model or self._model_id,
                probabilities=probabilities,
                confidence=confidence,
            ),
        )


class OpenRouterDecisionModel(_SystemOneCustomDecisionModel):
    """DecisionModel backed by OpenRouter's System One Decisions endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        model_id: str,
        timeout: float = DECISION_TIMEOUT_SECONDS,
        endpoint: str = OPENROUTER_DECISIONS_URL,
    ) -> None:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "strands-code",
        }
        super().__init__(
            provider_name="openrouter",
            endpoint=endpoint,
            model_id=model_id,
            headers=headers,
            timeout=timeout,
        )


class OllamaDecisionModel(_SystemOneCustomDecisionModel):
    """DecisionModel backed by a local or proxied Ollama ``/v1/systemone`` daemon."""

    def __init__(
        self,
        *,
        model_id: str,
        base_url: str,
        timeout: float = OLLAMA_TIMEOUT_SECONDS,
        keep_alive: str = OLLAMA_KEEP_ALIVE,
    ) -> None:
        endpoint = f"{base_url.rstrip('/')}/v1/systemone"
        super().__init__(
            provider_name="ollama",
            endpoint=endpoint,
            model_id=model_id,
            headers=ollama_headers(base_url),
            timeout=timeout,
            extra_payload={"keep_alive": keep_alive},
        )


def decision_result_to_engine_result(
    result: DecisionResult,
    *,
    raw_questions: dict[str, Any],
    cost: float | None,
    truncated: bool,
    llm_mode: bool = False,
    reported_model: str | None = None,
) -> EngineResult:
    """Convert an SDK ``DecisionResult`` into CLI ``EngineResult`` safely."""
    usage = result.usage or {}
    in_tok = _count(usage.get("inputTokens"))
    out_tok = _count(usage.get("outputTokens"))
    model_name = (
        reported_model
        if reported_model is not None or llm_mode
        else result.metadata.model_id
    )
    for q_id, answer in result.answers.items():
        if isinstance(answer, Uncertain):
            return EngineResult(
                answers=None,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cost=cost,
                model=model_name,
                error=_sanitize_uncertain_reason(answer.reason),
                truncated=truncated,
                uncertain=True,
            )

    probs_map = result.metadata.probabilities or {}
    conf_map = result.metadata.confidence or {}
    answers: dict[str, Any] = {}
    for q_id in raw_questions:
        if q_id not in result.answers:
            return EngineResult(answers=None, error="invalid body", truncated=truncated)
        val = result.answers[q_id]
        if llm_mode:
            answers[q_id] = {"type": "llm_choice", "choice": val}
        else:
            q_probs = probs_map.get(q_id) or {}
            q_conf = conf_map.get(q_id)
            entry: dict[str, Any] = {
                "type": "choice",
                "choice": val,
                "probabilities": dict(q_probs),
            }
            if q_conf is not None:
                entry["confidence"] = q_conf
            answers[q_id] = entry
    return EngineResult(
        answers=answers,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost=cost,
        model=model_name,
        truncated=truncated,
    )


def _ask_custom_system_one_sync(
    dm: _SystemOneCustomDecisionModel,
    *,
    state: dict[str, Any],
    questions: dict[str, Any],
    cost_override: float | None = None,
    use_last_cost: bool = False,
) -> EngineResult:
    try:
        sdk_questions, _ = build_sdk_questions_and_criteria(
            questions, uncertainty=False
        )
    except ValueError:
        return EngineResult(answers=None, error="invalid body")
    state_str = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    allow_unlisted = set(questions.keys()) == {"pick_effort"}

    async def _invoke() -> DecisionResult:
        return await dm.ask(
            state_str,
            sdk_questions,
            raw_state=state,
            raw_questions=questions,
            allow_unlisted_choices=allow_unlisted,
        )

    try:
        result = run_decision_sync(_invoke, retry=True)
    except Exception as exc:
        return EngineResult(
            answers=None,
            error=failure_reason(exc),
            truncated=dm.last_truncated,
        )
    cost = dm.last_cost if use_last_cost else cost_override
    return decision_result_to_engine_result(
        result,
        raw_questions=questions,
        cost=cost,
        truncated=dm.last_truncated,
        reported_model=dm.last_reported_model,
    )


def run_openrouter_decision(
    *,
    decision_model: str,
    state: dict[str, Any],
    questions: dict[str, Any],
    timeout: float = DECISION_TIMEOUT_SECONDS,
) -> EngineResult:
    """Execute one OpenRouter routing decision via ``OpenRouterDecisionModel``."""
    api_key = read_env_api_key("OPENROUTER_API_KEY")
    if not api_key or not isinstance(decision_model, str) or not decision_model.strip():
        return EngineResult(answers=None)
    if not valid_model_id(decision_model):
        return EngineResult(answers=None, error="invalid body")
    dm = OpenRouterDecisionModel(
        api_key=api_key, model_id=decision_model, timeout=timeout
    )
    return _ask_custom_system_one_sync(
        dm, state=state, questions=questions, use_last_cost=True
    )


def run_ollama_decision(
    *,
    local_model: str,
    local_base_url: str | None = None,
    state: dict[str, Any],
    questions: dict[str, Any],
    timeout: float = OLLAMA_TIMEOUT_SECONDS,
) -> EngineResult:
    """Execute one local Ollama routing decision via ``OllamaDecisionModel``."""
    if not isinstance(local_model, str) or not local_model.strip():
        return EngineResult(answers=None)
    if not valid_model_id(local_model):
        return EngineResult(answers=None, error="invalid body")
    base = ollama_base(local_base_url)
    if not valid_base_url(base):
        return EngineResult(answers=None)
    dm = OllamaDecisionModel(model_id=local_model, base_url=base, timeout=timeout)
    return _ask_custom_system_one_sync(
        dm, state=state, questions=questions, cost_override=None, use_last_cost=False
    )


def _run_folded_system_one(
    *,
    dm_cls: type[DecisionModel],
    api_key: str,
    model_id: str,
    state: dict[str, Any],
    questions: dict[str, Any],
    timeout: float,
    compute_cost: Callable[[DecisionResult], float | None],
) -> EngineResult:
    try:
        state_str, sdk_questions, truncated = build_folded_state_and_questions(
            state, questions, model_id=model_id, uncertainty=False, strict=True
        )
    except ValueError:
        return EngineResult(answers=None, error="invalid body")

    async def _invoke() -> DecisionResult:
        async with make_async_client(
            timeout, headers={"User-Agent": "strands-code"}
        ) as client:
            dm = dm_cls(
                api_key=api_key,
                model_id=model_id,
                default_min_confidence=0.0,
                http_client=client,
            )  # type: ignore[call-arg]
            return await dm.ask(state_str, sdk_questions)

    try:
        result = run_decision_sync(_invoke, retry=True)
    except Exception as exc:
        return EngineResult(
            answers=None, error=failure_reason(exc), truncated=truncated
        )
    return decision_result_to_engine_result(
        result, raw_questions=questions, cost=compute_cost(result), truncated=truncated
    )


def run_typesafe_decision(
    *,
    native_model: str,
    state: dict[str, Any],
    questions: dict[str, Any],
    timeout: float = DECISION_TIMEOUT_SECONDS,
) -> EngineResult:
    """Execute one native TypeSafe decision via upstream ``TypeSafeDecisionModel``."""
    from strands.decisions import TypeSafeDecisionModel

    api_key = read_env_api_key("TYPESAFE_API_KEY")
    if not api_key or not isinstance(native_model, str) or not native_model.strip():
        return EngineResult(answers=None)
    if not valid_model_id(native_model):
        return EngineResult(answers=None, error="invalid body")
    return _run_folded_system_one(
        dm_cls=TypeSafeDecisionModel,
        api_key=api_key,
        model_id=native_model,
        state=state,
        questions=questions,
        timeout=timeout,
        compute_cost=lambda res: (
            _count((res.usage or {}).get("inputTokens"))
            * TYPESAFE_INPUT_USD_PER_MTOK
            / 1_000_000
        ),
    )


def run_decisions_api_decision(
    *,
    model_id: str | None = None,
    state: dict[str, Any],
    questions: dict[str, Any],
    timeout: float = DECISION_TIMEOUT_SECONDS,
) -> EngineResult:
    """Execute one decisionapi.net request via ``DecisionsAPIDecisionModel``."""
    from strands.decisions import DecisionsAPIDecisionModel

    api_key = read_env_api_key("JEV_API_KEY")
    if not api_key:
        return EngineResult(answers=None)
    if isinstance(model_id, str) and model_id.strip():
        if not valid_model_id(model_id):
            return EngineResult(answers=None, error="invalid body")
        resolved_model = model_id
    else:
        resolved_model = DECISIONS_API_DEFAULT_MODEL
    return _run_folded_system_one(
        dm_cls=DecisionsAPIDecisionModel,
        api_key=api_key,
        model_id=resolved_model,
        state=state,
        questions=questions,
        timeout=timeout,
        compute_cost=lambda _res: None,
    )


def _estimate_llm_cost(llm_model: str, in_tok: int, out_tok: int) -> float | None:
    if in_tok <= 0 and out_tok <= 0:
        return None
    from strands_code_cli.cost.cost_context import cost_for

    try:
        return cost_for(in_tok, out_tok, llm_model)
    except Exception:
        return None


def _llm_scoped_endpoint(target_model: str) -> tuple[str | None, str | None]:
    """Return scoped ``(base_url, api_mode)`` from ProviderConfig for ``target_model``."""
    from strands_code_cli.entry.provider_config import ProviderConfig
    from strands_code_cli.model.model_switch import (
        normalize_model_ref,
        scoped_base_url,
    )
    from strands_code_cli.model.provider_id import provider_of

    try:
        cfg = ProviderConfig.load()
    except ValueError:
        return None, None
    owner = (
        provider_of(normalize_model_ref(cfg.model), unwrap_litellm=True)
        if cfg.model
        else None
    )
    scoped_url = scoped_base_url(cfg.base_url, owner, target_model)
    if scoped_url is None:
        return None, None
    return scoped_url, cfg.api_mode


def run_llm_decision(
    *,
    llm_model: str,
    state: dict[str, Any],
    questions: dict[str, Any],
    timeout: float = DECISION_TIMEOUT_SECONDS,
) -> EngineResult:
    """Execute one closed decision via upstream ``LLMDecisionModel``."""
    from strands.decisions import LLMDecisionModel

    import strands_code_cli.model.model_switch as switch_mod

    if not isinstance(llm_model, str) or not llm_model.strip():
        return EngineResult(answers=None)
    if not valid_model_id(llm_model):
        return EngineResult(answers=None, error="invalid body")
    target_model = llm_model
    scoped_url, scoped_mode = _llm_scoped_endpoint(target_model)
    llm_kwargs: dict[str, Any] = {
        "effort": "off",
        "web_search": False,
        "caching": False,
    }
    if scoped_url is not None:
        llm_kwargs["base_url"] = scoped_url
        if scoped_mode is not None:
            llm_kwargs["api_mode"] = scoped_mode
    try:
        state_str, sdk_questions, truncated = build_folded_state_and_questions(
            state, questions, model_id=target_model, uncertainty=True, strict=True
        )
    except ValueError:
        return EngineResult(answers=None, error="invalid body")

    async def _invoke() -> DecisionResult:
        # Resolve per attempt so retry on a fresh event loop never reuses a closed HTTP pool.
        resolved_model = switch_mod.resolve_harness_model(
            target_model, target_model, **llm_kwargs
        )
        dm = LLMDecisionModel(model=resolved_model)
        return await asyncio.wait_for(dm.ask(state_str, sdk_questions), timeout=timeout)

    try:
        result = run_decision_sync(_invoke, retry=True)
    except Exception as exc:
        return EngineResult(
            answers=None, error=failure_reason(exc), truncated=truncated
        )
    usage = result.usage or {}
    est_cost = _estimate_llm_cost(
        target_model,
        _count(usage.get("inputTokens")),
        _count(usage.get("outputTokens")),
    )
    return decision_result_to_engine_result(
        result,
        raw_questions=questions,
        cost=est_cost,
        truncated=truncated,
        llm_mode=True,
        reported_model=target_model,
    )
