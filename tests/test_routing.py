"""Decision-API transports, answer validation, gate, and chain tests (MODEL-03).

No live decision calls: the urllib seam serves canned Decision-API
payloads and the gate tests use stubbed almanac prices.
"""

from __future__ import annotations

import json
import urllib.error

import pytest

from strands_code_cli.routing import (
    OLLAMA_DEFAULT_HOST,
    OPENROUTER_DECISIONS_URL,
    EngineResult,
    RoutingCandidate,
    RoutingEngine,
    RoutingPick,
    RoutingState,
    RoutingStrategy,
    _ENGINE_REGISTRY,
    build_decision_state,
    build_effort_question,
    build_model_question,
    decide,
    decide_via_ollama,
    decide_via_openrouter,
    format_routed_line,
    gate_model,
    load_strategy,
    local_engine_ready,
    validate_choice_answer,
    validate_routed_effort,
)

HAIKU = "bedrock/anthropic.claude-haiku-4-5-20251001-v1:0"
NOVA_MICRO = "bedrock/amazon.nova-micro-v1:0"
SONNET = "bedrock/anthropic.claude-sonnet-4-6"


def _candidates() -> list[RoutingCandidate]:
    return [
        RoutingCandidate(
            id=HAIKU,
            tier="small",
            note="cheap",
            levels=["low", "high"],
            criteria="Cheap small model for trivial asks",
        ),
        RoutingCandidate(
            id=NOVA_MICRO,
            tier="tiny",
            levels=["low"],
            criteria="Tiny model for one-line lookups",
        ),
        RoutingCandidate(id=SONNET, tier="mid"),
    ]


def _strategy(**kwargs) -> RoutingStrategy:
    return RoutingStrategy(
        candidates=kwargs.pop("candidates", _candidates()[:2]),
        directives=kwargs.pop("directives", "trivial asks go cheap"),
        engine=kwargs.pop("engine", RoutingEngine(decision_model="cheap/decider")),
        **kwargs,
    )


def _answer(choice: str, probs: dict[str, float], confidence: float = 0.8) -> dict:
    return {
        "type": "choice",
        "choice": choice,
        "probabilities": dict(probs),
        "confidence": confidence,
    }


def _decision_payload(
    answer: dict,
    *,
    key: str = "pick_model",
    input_tokens: int = 384,
    output_tokens: int = 41,
    cost: float | None = 0.000016128,
    model: str = "typesafe/jev-1.13-20260917",
) -> dict:
    usage: dict = {"input_tokens": input_tokens, "output_tokens": output_tokens}
    if cost is not None:
        usage["cost"] = cost
    return {"model": model, "answers": {key: answer}, "usage": usage}


def _effort_payload(
    choice: str = "low",
    probs: dict[str, float] | None = None,
    **usage,
) -> dict:
    """Canned call-2 payload answering the picked levels only."""
    table = probs if probs is not None else {"low": 0.7, "high": 0.3}
    return _decision_payload(_answer(choice, table), key="pick_effort", **usage)


def _wants_effort(request) -> bool:
    """True when the stubbed POST asks the pick_effort question."""
    body = json.loads(request.data.decode("utf-8"))
    return "pick_effort" in body.get("questions", {})


class _FakeResponse:
    """Minimal urlopen context manager serving a canned JSON payload."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(OPENROUTER_DECISIONS_URL, code, "boom", {}, None)


def _with_preflight(fake, *, version: str = "0.40.3", tags=("nimble",)):
    """Serve daemon preflight GETs, delegating decision POSTs to fake."""

    def _wrapped(request, timeout=None):
        url = request.full_url
        if url.endswith("/api/version"):
            return _FakeResponse({"version": version})
        if url.endswith("/api/tags"):
            return _FakeResponse({"models": [{"name": name} for name in tags]})
        return fake(request, timeout=timeout)

    return _wrapped


class TestDecisionBuilders:
    def test_state_carries_ask_directives_and_side(self):
        state = build_decision_state(
            ask="fix the typo", directives="trivial asks go cheap", side=False
        )
        assert state == {
            "ask": "fix the typo",
            "directives": "trivial asks go cheap",
            "side": False,
        }

    def test_state_marks_side_asks(self):
        state = build_decision_state(ask="quick question", directives="", side=True)
        assert state["side"] is True
        assert state["ask"] == "quick question"

    def test_state_truncates_long_ask_and_directives(self):
        # T-08-23: unbounded repo text must not reach the paid call.
        state = build_decision_state(
            ask="x" * 5000, directives="d" * 5000, side=False
        )
        assert state["ask"] == "x" * 2000
        assert state["directives"] == "d" * 2000

    def test_state_never_carries_history_or_tool_text(self):
        state = build_decision_state(ask="plain ask", directives="d", side=False)
        assert set(state) == {"ask", "directives", "side"}
        blob = json.dumps(state)
        assert "toolUse" not in blob
        assert "toolResult" not in blob
        assert "reasoningContent" not in blob

    def test_question_maps_candidate_ids_to_criteria(self):
        question = build_model_question(
            candidates=_candidates(),
            directives="trivial asks go cheap",
        )
        assert question["type"] == "choice"
        assert question["criteria"] == {
            HAIKU: "Cheap small model for trivial asks",
            NOVA_MICRO: "Tiny model for one-line lookups",
            SONNET: "mid",  # no criteria: tier fallback
        }

    def test_question_appends_directives_to_instructions(self):
        question = build_model_question(
            candidates=_candidates()[:1], directives="trivial asks go cheap"
        )
        assert question["instructions"].startswith("Which candidate model")
        assert question["instructions"].endswith("trivial asks go cheap")
        bare = build_model_question(candidates=_candidates()[:1], directives="")
        assert bare["instructions"] == (
            "Which candidate model should serve the ask in `ask`? "
            "Judge the ask, not its length. "
        )

    def test_question_truncates_long_directives(self):
        question = build_model_question(
            candidates=_candidates()[:1], directives="d" * 5000
        )
        assert "d" * 2000 in question["instructions"]
        assert "d" * 5000 not in question["instructions"]

    def test_question_falls_back_for_missing_criteria(self):
        noted = RoutingCandidate(id="a/noted", note="note prose")
        bare = RoutingCandidate(id="a/bare")
        question = build_model_question(candidates=[noted, bare], directives="")
        assert question["criteria"] == {"a/noted": "note prose", "a/bare": "a/bare"}

    def test_question_never_touches_prices_or_stats(self, monkeypatch):
        # D-02: quantities stay code-side; building the question must
        # not consult the almanac at all.
        import strands_code_cli.routing as routing_mod

        def _boom(model_id):
            raise AssertionError("question building must not price candidates")

        monkeypatch.setattr(routing_mod, "price_for", _boom)
        question = build_model_question(
            candidates=_candidates(), directives="trivial asks go cheap"
        )
        assert set(question["criteria"]) == {HAIKU, NOVA_MICRO, SONNET}

    def test_effort_question_scopes_criteria_to_picked_levels(self):
        candidate = RoutingCandidate(id=HAIKU, levels=["low", "high"])
        question = build_effort_question(
            candidate=candidate, directives="trivial asks go cheap"
        )
        assert question["type"] == "choice"
        assert set(question["criteria"]) == {"low", "high"}
        assert HAIKU not in question["criteria"]  # levels only, never models

    def test_effort_question_uses_known_level_prose(self):
        from strands_code_cli.routing import _EFFORT_CRITERIA

        candidate = RoutingCandidate(id=HAIKU, levels=["low", "high"])
        question = build_effort_question(candidate=candidate, directives="")
        assert question["criteria"]["low"] == _EFFORT_CRITERIA["low"]
        assert question["criteria"]["low"] != "low"  # fixed prose, not the name

    def test_effort_question_falls_back_to_bare_level_name(self):
        candidate = RoutingCandidate(id=HAIKU, levels=["low", "turbo"])
        question = build_effort_question(candidate=candidate, directives="")
        assert question["criteria"]["turbo"] == "turbo"  # unknown: bare name

    def test_effort_question_shapes_instructions_with_directives(self):
        candidate = RoutingCandidate(id=HAIKU, levels=["low", "high"])
        question = build_effort_question(
            candidate=candidate, directives="trivial asks go cheap"
        )
        assert "trivial asks go cheap" in question["instructions"]
        assert HAIKU in question["instructions"]  # names the picked model
        assert "`ask`" in question["instructions"]


class TestValidateChoiceAnswer:
    def test_valid_table_returns_the_answer(self):
        answer = _answer(HAIKU, {HAIKU: 0.85, NOVA_MICRO: 0.15})
        assert validate_choice_answer(answer, _candidates()) is answer

    def test_wrong_type_holds(self):
        base = {HAIKU: 0.85, NOVA_MICRO: 0.15}
        for bad in (
            _answer(HAIKU, base) | {"type": "score"},
            _answer(HAIKU, base) | {"type": "bool"},
            {"choice": HAIKU, "probabilities": base},  # missing type
        ):
            assert validate_choice_answer(bad, _candidates()) is None

    def test_missing_or_empty_probabilities_holds(self):
        for bad in (
            {"type": "choice", "choice": HAIKU},  # missing key
            _answer(HAIKU, {}),  # empty table
            _answer(HAIKU, {HAIKU: 0.85, NOVA_MICRO: 0.15})
            | {"probabilities": [0.85, 0.15]},  # not a mapping
        ):
            assert validate_choice_answer(bad, _candidates()) is None

    def test_out_of_range_or_non_numeric_values_hold(self):
        for probs in (
            {HAIKU: 1.5, NOVA_MICRO: -0.5},  # out of range, sums to 1
            {HAIKU: 0.85, NOVA_MICRO: "0.15"},  # non-numeric
            {HAIKU: 0.85, NOVA_MICRO: True},  # bool is not a probability
        ):
            assert (
                validate_choice_answer(_answer(HAIKU, probs), _candidates()) is None
            )

    def test_bad_probability_sum_holds(self):
        assert (
            validate_choice_answer(
                _answer(HAIKU, {HAIKU: 0.5, NOVA_MICRO: 0.5, SONNET: 0.5}),
                _candidates(),
            )
            is None
        )
        assert (
            validate_choice_answer(
                _answer(HAIKU, {HAIKU: 0.34, NOVA_MICRO: 0.33, SONNET: 0.32}),
                _candidates(),
            )
            is None
        )

    def test_near_sum_within_tolerance_passes(self):
        third = 1 / 3  # float thirds sum to 1 within 1e-6
        answer = _answer(
            HAIKU, {HAIKU: third, NOVA_MICRO: third, SONNET: third}
        )
        assert validate_choice_answer(answer, _candidates()) is answer

    def test_choice_outside_table_holds(self):
        table = {HAIKU: 0.5, NOVA_MICRO: 0.5}
        assert (
            validate_choice_answer(_answer(SONNET, table), _candidates()) is None
        )
        answer = _answer(HAIKU, table)
        del answer["choice"]
        assert validate_choice_answer(answer, _candidates()) is None

    def test_stale_choice_holds_with_no_fuzzy_match(self):
        near_miss = HAIKU + "x"  # one char off: must NOT fuzzy-match
        table = {HAIKU: 0.5, near_miss: 0.5}
        assert (
            validate_choice_answer(_answer(near_miss, table), _candidates()) is None
        )
        ghost = {HAIKU: 0.5, "ghost/model": 0.5}
        assert (
            validate_choice_answer(_answer("ghost/model", ghost), _candidates())
            is None
        )

    def test_non_dict_answer_holds(self):
        for bad in (None, "", "choice", ["choice"], 42):
            assert validate_choice_answer(bad, _candidates()) is None

    def test_missing_confidence_still_validates(self):
        # The vendor confidence field is optional: logged, never gated.
        answer = _answer(HAIKU, {HAIKU: 0.85, NOVA_MICRO: 0.15})
        del answer["confidence"]
        assert validate_choice_answer(answer, _candidates()) is answer


class TestGateModel:
    def _priced(self, monkeypatch):
        import strands_code_cli.routing as routing_mod

        prices = {HAIKU: (3.0, 15.0), NOVA_MICRO: (0.035, 0.14)}
        monkeypatch.setattr(routing_mod, "price_for", lambda mid: prices.get(mid))

    def test_clear_winner_routes_top_with_empty_detail(self):
        model, tie_break, detail = gate_model(
            _answer(HAIKU, {HAIKU: 0.85, NOVA_MICRO: 0.15}), _strategy()
        )
        assert (model, tie_break, detail) == (HAIKU, False, "")

    def test_below_threshold_holds_naming_both_percents(self):
        model, tie_break, detail = gate_model(
            _answer(
                HAIKU, {HAIKU: 0.41, NOVA_MICRO: 0.30, SONNET: 0.29}
            ),
            _strategy(candidates=_candidates()),
        )
        assert model is None
        assert tie_break is False
        assert detail == "confidence 41% < 70%"

    def test_threshold_boundary_routes(self):
        model, _, _ = gate_model(
            _answer(HAIKU, {HAIKU: 0.70, NOVA_MICRO: 0.30}), _strategy()
        )
        assert model == HAIKU  # exactly at the threshold still routes

    def test_near_tie_substitutes_cheaper_with_note(self, monkeypatch):
        self._priced(monkeypatch)
        model, tie_break, detail = gate_model(
            _answer(HAIKU, {HAIKU: 0.52, NOVA_MICRO: 0.48}),
            _strategy(confidence_threshold=0.4),
        )
        assert model == NOVA_MICRO
        assert tie_break is True
        assert detail == f"tie 52% vs 48% → {NOVA_MICRO} (cheaper)"

    def test_exact_tie_routes_cheaper(self, monkeypatch):
        import strands_code_cli.routing as routing_mod

        # Exact ties break alphabetically (NOVA_MICRO sorts first), so
        # price it dearer to force the substitution the other way.
        prices = {HAIKU: (0.035, 0.14), NOVA_MICRO: (3.0, 15.0)}
        monkeypatch.setattr(routing_mod, "price_for", lambda mid: prices.get(mid))
        model, tie_break, detail = gate_model(
            _answer(HAIKU, {HAIKU: 0.5, NOVA_MICRO: 0.5}),
            _strategy(confidence_threshold=0.4),
        )
        assert model == HAIKU
        assert tie_break is True
        assert detail == f"tie 50% vs 50% → {HAIKU} (cheaper)"

    def test_outside_margin_keeps_top_without_lookup(self, monkeypatch):
        import strands_code_cli.routing as routing_mod

        def _boom(model_id):
            raise AssertionError("clear winners must not price candidates")

        monkeypatch.setattr(routing_mod, "price_for", _boom)
        model, tie_break, detail = gate_model(
            _answer(HAIKU, {HAIKU: 0.85, NOVA_MICRO: 0.15}), _strategy()
        )
        assert (model, tie_break, detail) == (HAIKU, False, "")

    def test_equal_prices_keep_top_without_marker(self, monkeypatch):
        import strands_code_cli.routing as routing_mod

        monkeypatch.setattr(routing_mod, "price_for", lambda mid: (1.0, 1.0))
        model, tie_break, detail = gate_model(
            _answer(HAIKU, {HAIKU: 0.52, NOVA_MICRO: 0.48}),
            _strategy(confidence_threshold=0.4),
        )
        assert (model, tie_break, detail) == (HAIKU, False, "")

    def test_missing_or_raising_prices_keep_top(self, monkeypatch):
        import strands_code_cli.routing as routing_mod

        monkeypatch.setattr(routing_mod, "price_for", lambda mid: None)
        table = _answer(HAIKU, {HAIKU: 0.52, NOVA_MICRO: 0.48})
        low = _strategy(confidence_threshold=0.4)
        assert gate_model(table, low) == (HAIKU, False, "")

        def _boom(model_id):
            raise RuntimeError("almanac down")

        monkeypatch.setattr(routing_mod, "price_for", _boom)
        assert gate_model(table, low) == (HAIKU, False, "")

    def test_single_entry_table_routes_top(self):
        model, tie_break, detail = gate_model(
            _answer(HAIKU, {HAIKU: 1.0}), _strategy()
        )
        assert (model, tie_break, detail) == (HAIKU, False, "")

    def test_vendor_confidence_never_gates(self):
        # Pitfall 1: the gate reads the table, never .confidence.
        strategy = _strategy()
        confident_hold = _answer(
            HAIKU, {HAIKU: 0.5, NOVA_MICRO: 0.5}, confidence=0.99
        )
        assert gate_model(confident_hold, strategy)[0] is None
        timid_route = _answer(
            HAIKU, {HAIKU: 0.9, NOVA_MICRO: 0.1}, confidence=0.01
        )
        assert gate_model(timid_route, strategy) == (HAIKU, False, "")

    def test_gate_reads_argmax_not_choice_field(self):
        answer = _answer(NOVA_MICRO, {HAIKU: 0.9, NOVA_MICRO: 0.1})
        assert validate_choice_answer(answer, _candidates()) is answer
        assert gate_model(answer, _strategy()) == (HAIKU, False, "")


def _route_payload(choice=HAIKU, probs=None, **usage) -> dict:
    table = probs if probs is not None else {HAIKU: 0.85, NOVA_MICRO: 0.15}
    return _decision_payload(_answer(choice, table), **usage)


class TestEngineChain:
    @pytest.fixture(autouse=True)
    def _key(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    def test_openrouter_success_routes_with_usage_triple(self, monkeypatch):
        import urllib.request

        calls: list = []

        def _fake_urlopen(request, timeout=None):
            calls.append(request)
            if _wants_effort(request):
                return _FakeResponse(
                    _effort_payload(input_tokens=100, output_tokens=5, cost=0.000004)
                )
            return _FakeResponse(_route_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, engine, usage, detail = decide(
            _strategy(), current_model=SONNET, side=False, ask="hi"
        )
        assert len(calls) == 2  # model call, then the effort call
        assert pick == RoutingPick(
            model=HAIKU,
            effort="low",  # decided level, top of the effort table
            model_confidence=0.85,
            effort_confidence=0.7,
            tie_break=False,
        )
        assert engine == "openrouter"
        # summed reported triples, both costs verbatim
        assert usage == (484, 46, 0.000016128 + 0.000004)
        assert detail == ""

    def test_openrouter_posts_decision_contract(self, monkeypatch):
        import urllib.request

        seen: list = []

        def _fake_urlopen(request, timeout=None):
            seen.append(
                {
                    "url": request.full_url,
                    "body": json.loads(request.data.decode("utf-8")),
                    "auth": request.get_header("Authorization"),
                    "timeout": timeout,
                }
            )
            if _wants_effort(request):
                return _FakeResponse(_effort_payload())
            return _FakeResponse(_route_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        decide(_strategy(), current_model=SONNET, side=False, ask="hi")
        assert len(seen) == 2  # model call first, effort call second
        for call in seen:
            assert call["url"] == OPENROUTER_DECISIONS_URL
            assert call["url"] == "https://openrouter.ai/api/alpha/decisions"
            assert call["body"]["model"] == "cheap/decider"
            assert call["body"]["state"] == {
                "ask": "hi",
                "directives": "trivial asks go cheap",
                "side": False,
            }
            assert "response_format" not in call["body"]  # no legacy JSON mode
            assert "messages" not in call["body"] and "max_tokens" not in call["body"]
            assert call["auth"] == "Bearer " + "test-key"  # header-only
            assert call["timeout"] == 10
        first, second = seen[0]["body"], seen[1]["body"]
        assert set(first["questions"]) == {"pick_model"}  # sequential, never merged
        assert first["questions"]["pick_model"]["type"] == "choice"
        assert set(first["questions"]["pick_model"]["criteria"]) == {
            HAIKU,
            NOVA_MICRO,
        }
        assert set(second["questions"]) == {"pick_effort"}
        assert second["questions"]["pick_effort"]["type"] == "choice"
        assert set(second["questions"]["pick_effort"]["criteria"]) == {
            "low",
            "high",
        }

    def test_openrouter_reports_snapshot_and_cost(self, monkeypatch):
        import urllib.request

        def _fake_urlopen(request, timeout=None):
            return _FakeResponse(_route_payload(cost=0.00002))

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        result = decide_via_openrouter(
            decision_model="m", state={"ask": "hi"}, questions={"pick_model": {}}
        )
        assert result.answers is not None
        assert result.answers["pick_model"]["choice"] == HAIKU
        assert (result.input_tokens, result.output_tokens) == (384, 41)
        assert result.cost == 0.00002
        assert result.model == "typesafe/jev-1.13-20260917"

    def test_missing_key_yields_hold_without_network(self, monkeypatch):
        import urllib.request

        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        def _boom(request, timeout=None):
            raise AssertionError("must not call the network without a key")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        pick, engine, usage, detail = decide(
            _strategy(), current_model=SONNET, side=False, ask="hi"
        )
        assert pick is None
        assert engine == "openrouter"
        assert usage == (0, 0, None)
        assert detail == "openrouter failed"

    def test_missing_decision_model_skips_openrouter(self, monkeypatch):
        import urllib.request

        def _boom(request, timeout=None):
            raise AssertionError("no decision model: no call")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        strategy = _strategy(engine=RoutingEngine())
        pick, engine, usage, detail = decide(
            strategy, current_model=SONNET, side=False, ask="hi"
        )
        assert pick is None
        assert engine == "openrouter"
        assert usage == (0, 0, None)
        assert detail == "openrouter failed"

    @pytest.mark.parametrize("code", [429, 500, 502, 503, 524, 529])
    def test_retryable_status_retries_once_then_routes(self, monkeypatch, code):
        import urllib.request

        calls: list = []
        script: list = [_http_error(code)]

        def _fake_urlopen(request, timeout=None):
            calls.append(request)
            if _wants_effort(request):
                return _FakeResponse(_effort_payload())
            step = script.pop(0) if script else None
            if isinstance(step, Exception):
                raise step
            return _FakeResponse(_route_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, engine, _, _ = decide(
            _strategy(), current_model=SONNET, side=False, ask="hi"
        )
        assert len(calls) == 3  # one retry on call 1, then call 2
        assert pick is not None and pick.model == HAIKU
        assert engine == "openrouter"

    def test_retry_exhaustion_holds(self, monkeypatch):
        import urllib.request

        calls: list = []

        def _fake_urlopen(request, timeout=None):
            calls.append(request)
            raise _http_error(503)

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, engine, usage, detail = decide(
            _strategy(), current_model=SONNET, side=False, ask="hi"
        )
        assert len(calls) == 2
        assert pick is None
        assert engine == "openrouter"
        assert usage == (0, 0, None)
        assert detail == "openrouter failed"

    @pytest.mark.parametrize("code", [400, 401, 402, 403, 404, 413])
    def test_4xx_never_retries(self, monkeypatch, code):
        import urllib.request

        calls: list = []

        def _fake_urlopen(request, timeout=None):
            calls.append(request)
            raise _http_error(code)

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, _, _, _ = decide(
            _strategy(), current_model=SONNET, side=False, ask="hi"
        )
        assert len(calls) == 1  # the request itself is wrong: hold
        assert pick is None

    def test_timeout_retries_once_then_routes(self, monkeypatch):
        import urllib.request

        calls: list = []
        script: list = [TimeoutError("slow engine")]

        def _fake_urlopen(request, timeout=None):
            calls.append(request)
            if _wants_effort(request):
                return _FakeResponse(_effort_payload())
            step = script.pop(0) if script else None
            if isinstance(step, Exception):
                raise step
            return _FakeResponse(_route_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, _, _, _ = decide(
            _strategy(), current_model=SONNET, side=False, ask="hi"
        )
        assert len(calls) == 3  # one retry on call 1, then call 2
        assert pick is not None and pick.model == HAIKU

    def test_timeout_exhaustion_holds(self, monkeypatch):
        import urllib.request

        calls: list = []

        def _slow(request, timeout=None):
            calls.append(request)
            raise TimeoutError("slow engine")

        monkeypatch.setattr(urllib.request, "urlopen", _slow)
        assert (
            decide_via_openrouter(
                decision_model="m", state={}, questions={}
            ).answers
            is None
        )
        pick, _, _, _ = decide(
            _strategy(), current_model=SONNET, side=False, ask="hi"
        )
        assert len(calls) == 4  # one retry per call site, then hold
        assert pick is None

    def test_url_error_holds_without_retry(self, monkeypatch):
        import urllib.request

        calls: list = []

        def _boom(request, timeout=None):
            calls.append(request)
            raise urllib.error.URLError("offline")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        assert (
            decide_via_openrouter(
                decision_model="m", state={}, questions={}
            ).answers
            is None
        )
        pick, _, _, _ = decide(
            _strategy(), current_model=SONNET, side=False, ask="hi"
        )
        assert len(calls) == 2  # refused connections never retry
        assert pick is None

    def test_wrapped_timeout_error_retries_once(self, monkeypatch):
        import urllib.request

        calls: list = []
        script: list = [urllib.error.URLError(TimeoutError("timed out"))]

        def _fake_urlopen(request, timeout=None):
            calls.append(request)
            if _wants_effort(request):
                return _FakeResponse(_effort_payload())
            step = script.pop(0) if script else None
            if isinstance(step, Exception):
                raise step
            return _FakeResponse(_route_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, _, _, _ = decide(
            _strategy(), current_model=SONNET, side=False, ask="hi"
        )
        assert len(calls) == 3  # one retry on call 1, then call 2
        assert pick is not None

    def test_schema_failures_hold_without_retry(self, monkeypatch):
        import urllib.request

        for payload in (
            {"model": "m", "usage": {}},  # answers key missing
            {"model": "m", "answers": [], "usage": {}},  # answers not a dict
            {"model": "m", "answers": {"other": {}}, "usage": {}},  # key missing
            ["not", "a", "mapping"],  # body not a mapping
        ):
            calls: list = []

            def _fake_urlopen(request, timeout=None):
                calls.append(request)
                return _FakeResponse(payload)

            monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
            pick, engine, _, _ = decide(
                _strategy(), current_model=SONNET, side=False, ask="hi"
            )
            assert pick is None
            assert engine == "openrouter"
            assert len(calls) == 1  # schema misses never re-ask

    def test_malformed_table_falls_through_to_next_engine(self, monkeypatch):
        import urllib.request

        def _fake_urlopen(request, timeout=None):
            if _wants_effort(request):
                return _FakeResponse(_effort_payload(cost=None))
            if "openrouter" in request.full_url:
                bad = _answer(HAIKU, {HAIKU: 0.5, NOVA_MICRO: 0.5, SONNET: 0.5})
                return _FakeResponse(_decision_payload(bad))
            return _FakeResponse(_route_payload())

        monkeypatch.setattr(
            urllib.request, "urlopen", _with_preflight(_fake_urlopen)
        )
        strategy = _strategy(
            engine=RoutingEngine(
                decision_model="cheap/decider", local_model="nimble"
            )
        )
        pick, engine, _, _ = decide(
            strategy, current_model=SONNET, side=False, ask="hi"
        )
        assert pick is not None and pick.model == HAIKU
        assert engine == "local"  # schema-invalid openrouter yields to local

    def test_stale_choice_holds(self, monkeypatch):
        import urllib.request

        def _fake_urlopen(request, timeout=None):
            ghost = {HAIKU: 0.5, "ghost/model": 0.5}
            return _FakeResponse(_decision_payload(_answer("ghost/model", ghost)))

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, engine, _, detail = decide(
            _strategy(), current_model=SONNET, side=False, ask="hi"
        )
        assert pick is None
        assert engine == "openrouter"
        assert detail == "openrouter failed"

    def test_threshold_hold_short_circuits_chain(self, monkeypatch):
        import urllib.request

        urls: list[str] = []
        weak = _answer(
            HAIKU, {HAIKU: 0.41, NOVA_MICRO: 0.30, SONNET: 0.29}
        )

        def _fake_urlopen(request, timeout=None):
            urls.append(request.full_url)
            return _FakeResponse(_decision_payload(weak))

        monkeypatch.setattr(
            urllib.request, "urlopen", _with_preflight(_fake_urlopen)
        )
        strategy = _strategy(
            candidates=_candidates(),
            engine=RoutingEngine(
                decision_model="cheap/decider", local_model="nimble"
            ),
        )
        pick, engine, usage, detail = decide(
            strategy, current_model=SONNET, side=False, ask="hi"
        )
        assert pick is None  # ambiguous ask: hold, retry next ask
        assert engine == "openrouter"
        assert usage == (0, 0, None)
        assert detail == "confidence 41% < 70%"
        assert urls == [OPENROUTER_DECISIONS_URL]  # local never tried

    def test_first_advertised_level_rejection_holds(self, monkeypatch):
        # The picked candidate's lone level rides through
        # validate_routed_effort: nova-micro advertises "low" but
        # supports no thinking, so the route holds.
        import urllib.request

        def _fake_urlopen(request, timeout=None):
            return _FakeResponse(
                _route_payload(
                    choice=NOVA_MICRO, probs={HAIKU: 0.1, NOVA_MICRO: 0.9}
                )
            )

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, engine, _, detail = decide(
            _strategy(), current_model=SONNET, side=False, ask="hi"
        )
        assert pick is None
        assert engine == "openrouter"
        assert detail == f"effort 'low' unsupported by {NOVA_MICRO}"

    def test_picked_candidate_without_levels_holds(self, monkeypatch):
        import urllib.request

        def _fake_urlopen(request, timeout=None):
            return _FakeResponse(_route_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        strategy = _strategy(
            candidates=[
                RoutingCandidate(id=HAIKU),
                RoutingCandidate(id=NOVA_MICRO),
            ]
        )
        pick, engine, _, detail = decide(
            strategy, current_model=SONNET, side=False, ask="hi"
        )
        assert pick is None
        assert engine == "openrouter"
        assert detail == f"picked candidate {HAIKU} advertises no levels"

    def test_same_model_pick_skips_effort_validation(self, monkeypatch):
        # No-op fast path: the hook applies no switch and no effort,
        # so an unsupported passthrough level still yields a pick.
        import urllib.request

        def _fake_urlopen(request, timeout=None):
            return _FakeResponse(
                _route_payload(
                    choice=NOVA_MICRO, probs={HAIKU: 0.1, NOVA_MICRO: 0.9}
                )
            )

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, engine, _, detail = decide(
            _strategy(), current_model=NOVA_MICRO, side=False, ask="hi"
        )
        assert pick is not None and pick.model == NOVA_MICRO
        assert pick.effort == "low"
        assert engine == "openrouter"
        assert detail == ""

    def test_registry_orders_openrouter_first(self):
        assert _ENGINE_REGISTRY and _ENGINE_REGISTRY[0][0] == "openrouter"

    def test_decide_defaults_to_main_side(self, monkeypatch):
        import urllib.request

        def _fake_urlopen(request, timeout=None):
            body = json.loads(request.data.decode("utf-8"))
            assert body["state"]["side"] is False
            if _wants_effort(request):
                return _FakeResponse(_effort_payload())
            return _FakeResponse(_route_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, _, _, _ = decide(_strategy(), current_model=SONNET, ask="hi")
        assert pick is not None


class TestLocalEngine:
    @pytest.fixture(autouse=True)
    def _keys(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)

    def _dual(self, **engine_kwargs) -> RoutingStrategy:
        engine = RoutingEngine(decision_model="cheap/decider", local_model="nimble")
        for key, value in engine_kwargs.items():
            setattr(engine, key, value)
        return _strategy(engine=engine)

    def _local_payload(self, **usage) -> dict:
        usage.setdefault("cost", None)  # local shape carries no cost
        return _route_payload(**usage)

    def test_openrouter_success_short_circuits_with_no_local_call(self, monkeypatch):
        import urllib.request

        urls: list[str] = []

        def _fake_urlopen(request, timeout=None):
            urls.append(request.full_url)
            if _wants_effort(request):
                return _FakeResponse(_effort_payload())
            return _FakeResponse(_route_payload())

        monkeypatch.setattr(
            urllib.request, "urlopen", _with_preflight(_fake_urlopen)
        )
        pick, engine, _, _ = decide(
            self._dual(), current_model=SONNET, side=False, ask="hi"
        )
        assert urls == [OPENROUTER_DECISIONS_URL] * 2  # both calls, no local
        assert pick == RoutingPick(
            model=HAIKU,
            effort="low",
            model_confidence=0.85,
            effort_confidence=0.7,
            tie_break=False,
        )
        assert engine == "openrouter"

    def test_openrouter_failure_falls_back_to_local_pick(self, monkeypatch):
        import urllib.request

        urls: list[str] = []

        def _fake_urlopen(request, timeout=None):
            urls.append(request.full_url)
            if "openrouter" in request.full_url:
                raise urllib.error.URLError("api down")
            if _wants_effort(request):
                return _FakeResponse(
                    _effort_payload(cost=None, input_tokens=50, output_tokens=6)
                )
            return _FakeResponse(self._local_payload())

        monkeypatch.setattr(
            urllib.request, "urlopen", _with_preflight(_fake_urlopen)
        )
        pick, engine, usage, _ = decide(
            self._dual(), current_model=SONNET, side=False, ask="hi"
        )
        # call 1 falls through, then call 2 retries the chain (api still
        # down) before landing local: one attempt per engine per call
        assert len(urls) == 4
        assert urls[1] == f"{OLLAMA_DEFAULT_HOST}/v1/systemone"
        assert urls[2] == OPENROUTER_DECISIONS_URL
        assert urls[3] == f"{OLLAMA_DEFAULT_HOST}/v1/systemone"
        assert pick is not None and pick.model == HAIKU
        assert pick.effort_confidence == 0.7
        assert engine == "local"
        assert usage == (434, 47, None)  # local spend records as None

    def test_both_failing_holds_current(self, monkeypatch):
        import urllib.request

        def _boom(request, timeout=None):
            raise urllib.error.URLError("offline")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        pick, engine, usage, detail = decide(
            self._dual(), current_model=SONNET, side=False, ask="hi"
        )
        assert pick is None
        assert engine == "local"  # last attempted engine
        assert usage == (0, 0, None)
        # The refused preflight skips the local link with the distinct
        # unready detail instead of a transport failure.
        assert detail == "local unready (daemon version or tag not ready)"

    def test_primary_local_skips_the_api(self, monkeypatch):
        import urllib.request

        urls: list[str] = []

        def _fake_urlopen(request, timeout=None):
            urls.append(request.full_url)
            assert "openrouter" not in request.full_url
            if _wants_effort(request):
                return _FakeResponse(_effort_payload(cost=None))
            return _FakeResponse(self._local_payload())

        monkeypatch.setattr(
            urllib.request, "urlopen", _with_preflight(_fake_urlopen)
        )
        strategy = self._dual(primary="local")
        pick, engine, _, _ = decide(
            strategy, current_model=SONNET, side=False, ask="hi"
        )
        assert len(urls) == 2  # both calls stay local
        assert pick is not None and engine == "local"

    def test_primary_local_failure_holds_without_api_call(self, monkeypatch):
        import urllib.request

        def _boom(request, timeout=None):
            raise urllib.error.URLError("daemon down")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        strategy = self._dual(primary="local")
        pick, engine, _, _ = decide(
            strategy, current_model=SONNET, side=False, ask="hi"
        )
        assert pick is None
        assert engine == "local"

    def test_primary_off_load_yields_none_with_zero_calls(
        self, tmp_path, monkeypatch, capsys
    ):
        import urllib.request

        global_path = tmp_path / "routing.yaml"
        global_path.write_text(
            "candidates:\n"
            f"  - id: {HAIKU}\n"
            "engine: {primary: off, decision_model: cheap/decider}\n",
            encoding="utf-8",
        )

        def _boom(request, timeout=None):
            raise AssertionError("routing off: no engine call")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        assert (
            load_strategy(global_path=global_path, repo_path=tmp_path / "missing.yaml")
            is None
        )
        assert capsys.readouterr().out == ""  # specifically no hold note

    def test_quoted_off_disables_routing(self, tmp_path):
        path = tmp_path / "routing.yaml"
        path.write_text(
            "candidates:\n"
            f"  - id: {HAIKU}\n"
            "engine: {primary: 'off', decision_model: cheap/decider}\n",
            encoding="utf-8",
        )
        assert (
            load_strategy(global_path=path, repo_path=tmp_path / "missing.yaml") is None
        )

    def test_repo_off_shadows_global_on(self, tmp_path):
        repo_path = tmp_path / "repo.yaml"
        repo_path.write_text(
            "candidates:\n"
            f"  - id: {HAIKU}\n"
            "engine: {primary: off}\n",
            encoding="utf-8",
        )
        global_path = tmp_path / "global.yaml"
        global_path.write_text(
            "candidates:\n"
            f"  - id: {HAIKU}\n"
            "engine: {primary: openrouter, decision_model: cheap/decider}\n",
            encoding="utf-8",
        )
        # Repo wins whole-file, then off yields None: no fallthrough.
        assert load_strategy(global_path=global_path, repo_path=repo_path) is None

    def test_missing_local_model_skips_local_layer(self, monkeypatch):
        import urllib.request

        urls: list[str] = []

        def _fake_urlopen(request, timeout=None):
            urls.append(request.full_url)
            raise urllib.error.URLError("api down")

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        strategy = _strategy(engine=RoutingEngine(decision_model="cheap/decider"))
        pick, engine, _, _ = decide(
            strategy, current_model=SONNET, side=False, ask="hi"
        )
        assert pick is None
        assert engine == "openrouter"  # local skipped, not failed
        assert urls == [OPENROUTER_DECISIONS_URL]

    def test_no_engine_configured_makes_zero_calls(self, monkeypatch):
        import urllib.request

        def _boom(request, timeout=None):
            raise AssertionError("no usable engine: no network attempt")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        strategy = _strategy(engine=RoutingEngine())
        pick, engine, usage, detail = decide(
            strategy, current_model=SONNET, side=False, ask="hi"
        )
        assert (pick, engine, usage, detail) == (
            None,
            "openrouter",
            (0, 0, None),
            "openrouter failed",
        )

    def test_non_http_base_url_warns_and_uses_default_host(
        self, tmp_path, monkeypatch, caplog
    ):
        path = tmp_path / "routing.yaml"
        path.write_text(
            "candidates:\n"
            f"  - id: {HAIKU}\n"
            "engine: {primary: local, local_model: nimble, "
            "local_base_url: 'ftp://files.local/ollama'}\n",
            encoding="utf-8",
        )
        with caplog.at_level("WARNING", logger="strands_code_cli.routing"):
            strategy = load_strategy(global_path=path, repo_path=tmp_path / "missing.yaml")
        assert strategy is not None
        assert strategy.engine.local_base_url == OLLAMA_DEFAULT_HOST
        assert "http/https only" in caplog.text

    def test_default_host_serves_local_calls(self, monkeypatch):
        import urllib.request

        seen: dict = {}

        def _fake_urlopen(request, timeout=None):
            seen["url"] = request.full_url
            seen["timeout"] = timeout
            if _wants_effort(request):
                return _FakeResponse(_effort_payload(cost=None))
            return _FakeResponse(self._local_payload())

        monkeypatch.setattr(
            urllib.request, "urlopen", _with_preflight(_fake_urlopen)
        )
        strategy = self._dual(primary="local")
        pick, _, _, _ = decide(strategy, current_model=SONNET, side=False, ask="hi")
        assert pick is not None
        assert seen["url"] == f"{OLLAMA_DEFAULT_HOST}/v1/systemone"
        assert seen["timeout"] == 30

    def test_ollama_posts_systemone_contract(self, monkeypatch):
        import urllib.request

        seen: dict = {}

        def _fake_urlopen(request, timeout=None):
            seen["url"] = request.full_url
            seen["body"] = json.loads(request.data.decode("utf-8"))
            seen["auth"] = request.get_header("Authorization")
            return _FakeResponse(self._local_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        result = decide_via_ollama(
            local_model="nimble", state={"ask": "hi"}, questions={"pick_model": {}}
        )
        assert result.answers is not None
        assert result.answers["pick_model"]["choice"] == HAIKU
        assert seen["url"] == f"{OLLAMA_DEFAULT_HOST}/v1/systemone"
        body = seen["body"]
        assert body["model"] == "nimble"
        assert body["keep_alive"] == "5m"
        assert set(body) == {"model", "state", "questions", "keep_alive"}
        assert seen["auth"] is None  # localhost never carries key material

    def test_ollama_usage_comes_from_token_counts(self, monkeypatch):
        import urllib.request

        def _fake_urlopen(request, timeout=None):
            if _wants_effort(request):
                return _FakeResponse(
                    _effort_payload(cost=None, input_tokens=30, output_tokens=4)
                )
            return _FakeResponse(
                _decision_payload(
                    _answer(HAIKU, {HAIKU: 0.85, NOVA_MICRO: 0.15}),
                    input_tokens=90,
                    output_tokens=12,
                    cost=None,
                )
            )

        monkeypatch.setattr(
            urllib.request, "urlopen", _with_preflight(_fake_urlopen)
        )
        result = decide_via_ollama(
            local_model="nimble", state={}, questions={}
        )
        assert (result.input_tokens, result.output_tokens) == (90, 12)
        assert result.cost is None
        _, _, usage, _ = decide(
            self._dual(primary="local"), current_model=SONNET, side=False, ask="hi"
        )
        assert usage == (120, 16, None)  # both local calls summed, still costless

    def test_proxied_host_carries_bearer_key(self, monkeypatch):
        import urllib.request

        monkeypatch.setenv("OLLAMA_API_KEY", "proxy-secret")
        seen: dict = {}

        def _fake_urlopen(request, timeout=None):
            seen["url"] = request.full_url
            seen["auth"] = request.get_header("Authorization")
            return _FakeResponse(self._local_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        result = decide_via_ollama(
            local_model="nimble",
            local_base_url="http://gpu-box.example:11434",
            state={},
            questions={},
        )
        assert result.answers is not None
        assert seen["url"] == "http://gpu-box.example:11434/v1/systemone"
        assert seen["auth"] == "Bearer " + "proxy-secret"

    def test_invalid_base_url_at_call_time_fails_soft(self, monkeypatch):
        import urllib.request

        def _boom(request, timeout=None):
            raise AssertionError("invalid base URL: no call")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        strategy = self._dual(
            primary="local", local_base_url="gopher://daemon.local/"
        )
        pick, engine, _, _ = decide(
            strategy, current_model=SONNET, side=False, ask="hi"
        )
        assert pick is None
        assert engine == "local"

    def test_local_stale_choice_holds(self, monkeypatch):
        import urllib.request

        near_miss = HAIKU + "x"  # one char off: must NOT fuzzy-match

        def _fake_urlopen(request, timeout=None):
            table = {HAIKU: 0.2, near_miss: 0.8}
            return _FakeResponse(_decision_payload(_answer(near_miss, table)))

        monkeypatch.setattr(
            urllib.request, "urlopen", _with_preflight(_fake_urlopen)
        )
        pick, engine, _, _ = decide(
            self._dual(primary="local"), current_model=SONNET, side=False, ask="hi"
        )
        assert pick is None
        assert engine == "local"

    def test_registry_orders_local_second(self):
        assert [name for name, _ in _ENGINE_REGISTRY] == ["openrouter", "local"]

    def test_engine_result_defaults_to_zero_usage(self):
        assert EngineResult(answers=None) == EngineResult(
            answers=None, input_tokens=0, output_tokens=0, cost=None, model=None
        )

    def test_ready_daemon_attempts_local_link(self, monkeypatch):
        import urllib.request

        gets: list[str] = []
        posts: list[str] = []

        def _fake_urlopen(request, timeout=None):
            posts.append(request.full_url)
            if _wants_effort(request):
                return _FakeResponse(_effort_payload(cost=None))
            return _FakeResponse(self._local_payload())

        def _recording(request, timeout=None):
            if request.full_url.endswith(
                ("/api/version", "/api/tags")
            ):
                gets.append(request.full_url)
            return _with_preflight(_fake_urlopen)(request, timeout=timeout)

        monkeypatch.setattr(urllib.request, "urlopen", _recording)
        pick, engine, _, detail = decide(
            self._dual(primary="local"), current_model=SONNET, side=False, ask="hi"
        )
        assert pick is not None and pick.model == HAIKU
        assert engine == "local"
        assert detail == ""
        assert len(gets) == 2  # version plus tags, once per ask
        assert posts == [f"{OLLAMA_DEFAULT_HOST}/v1/systemone"] * 2

    def test_old_daemon_skips_local_link_with_zero_posts(self, monkeypatch):
        import urllib.request

        gets: list[str] = []

        def _boom(request, timeout=None):
            raise AssertionError("unready daemon: no decision POST")

        def _recording(request, timeout=None):
            gets.append(request.full_url)
            return _with_preflight(_boom, version="0.34.0")(
                request, timeout=timeout
            )

        monkeypatch.setattr(urllib.request, "urlopen", _recording)
        pick, engine, usage, detail = decide(
            self._dual(primary="local"), current_model=SONNET, side=False, ask="hi"
        )
        assert pick is None
        assert engine == "local"
        assert usage == (0, 0, None)
        assert detail == "local unready (daemon version or tag not ready)"
        assert gets == [f"{OLLAMA_DEFAULT_HOST}/api/version"]  # tags never asked

    def test_missing_tag_skips_local_link_with_zero_posts(self, monkeypatch):
        import urllib.request

        def _boom(request, timeout=None):
            raise AssertionError("tag missing: no decision POST")

        monkeypatch.setattr(
            urllib.request,
            "urlopen",
            _with_preflight(_boom, tags=("other-model:1b",)),
        )
        pick, engine, usage, detail = decide(
            self._dual(primary="local"), current_model=SONNET, side=False, ask="hi"
        )
        assert pick is None
        assert engine == "local"
        assert usage == (0, 0, None)
        assert detail == "local unready (daemon version or tag not ready)"

    def test_clef_tag_needs_point_release(self, monkeypatch):
        import urllib.request

        def _boom(request, timeout=None):
            raise AssertionError("preflight only: no decision POST")

        monkeypatch.setattr(
            urllib.request,
            "urlopen",
            _with_preflight(_boom, version="0.35.0", tags=("clef", "nimble")),
        )
        base = OLLAMA_DEFAULT_HOST
        assert local_engine_ready(base, "clef") is False  # 0.35.0 < 0.35.1
        assert local_engine_ready(base, "nimble") is True  # floor is 0.35
        monkeypatch.setattr(
            urllib.request,
            "urlopen",
            _with_preflight(
                _boom, version="0.35.1", tags=("clef", "clef-flash")
            ),
        )
        assert local_engine_ready(base, "clef") is True
        assert local_engine_ready(base, "clef-flash") is True

    @pytest.mark.parametrize(
        "version,ready",
        [
            ("0.35", True),  # exactly the floor
            ("0.35.0", True),
            ("0.40.3", True),
            ("1.2.3", True),
            ("0.34.9", False),  # just below the floor
            ("0.34", False),
            ("", False),
            ("abc", False),  # unparseable fails closed
            ("0.x.1", False),
        ],
    )
    def test_version_floor_boundaries(self, monkeypatch, version, ready):
        import urllib.request

        def _boom(request, timeout=None):
            raise AssertionError("preflight only: no decision POST")

        monkeypatch.setattr(
            urllib.request, "urlopen", _with_preflight(_boom, version=version)
        )
        assert local_engine_ready(OLLAMA_DEFAULT_HOST, "nimble") is ready

    @pytest.mark.parametrize(
        "payload",
        [
            {"version": "0.40.3", "models": "nimble"},  # models not a list
            {"version": "0.40.3", "models": [{"digest": "abc"}]},  # no names
            {"version": "0.40.3", "models": [{"name": 42}]},  # name not a str
        ],
    )
    def test_malformed_tags_shape_is_unready(self, monkeypatch, payload):
        import urllib.request

        def _fake_urlopen(request, timeout=None):
            if request.full_url.endswith("/api/version"):
                return _FakeResponse({"version": "0.40.3"})
            if request.full_url.endswith("/api/tags"):
                return _FakeResponse(payload)
            raise AssertionError("preflight only: no decision POST")

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        assert local_engine_ready(OLLAMA_DEFAULT_HOST, "nimble") is False

    def test_missing_version_key_is_unready(self, monkeypatch):
        import urllib.request

        def _fake_urlopen(request, timeout=None):
            return _FakeResponse({"models": []})  # no version anywhere

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        assert local_engine_ready(OLLAMA_DEFAULT_HOST, "nimble") is False

    def test_latest_suffixed_daemon_name_matches(self, monkeypatch):
        import urllib.request

        def _boom(request, timeout=None):
            raise AssertionError("preflight only: no decision POST")

        monkeypatch.setattr(
            urllib.request,
            "urlopen",
            _with_preflight(_boom, tags=("nimble:latest",)),
        )
        base = OLLAMA_DEFAULT_HOST
        assert local_engine_ready(base, "nimble") is True
        assert local_engine_ready(base, "nimble:latest") is True  # exact too
        assert local_engine_ready(base, "nimble:9b") is False  # no fuzzy tag

    def test_refused_preflight_returns_false_and_never_raises(self, monkeypatch):
        import urllib.request

        calls: list = []

        def _refused(request, timeout=None):
            calls.append(request)
            raise urllib.error.URLError(
                ConnectionRefusedError(111, "Connection refused")
            )

        monkeypatch.setattr(urllib.request, "urlopen", _refused)
        assert local_engine_ready(OLLAMA_DEFAULT_HOST, "nimble") is False
        pick, engine, _, detail = decide(
            self._dual(primary="local"), current_model=SONNET, side=False, ask="hi"
        )
        assert pick is None  # the hook holds; nothing raised to it
        assert engine == "local"
        assert detail == "local unready (daemon version or tag not ready)"
        assert all(
            call.full_url.endswith("/api/version") for call in calls
        )  # zero POSTs

    def test_empty_base_or_tag_is_unready_without_network(self, monkeypatch):
        import urllib.request

        def _boom(request, timeout=None):
            raise AssertionError("empty input: no preflight attempt")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        assert local_engine_ready("", "nimble") is False
        assert local_engine_ready(OLLAMA_DEFAULT_HOST, "") is False


class TestRoutedEffort:
    @pytest.fixture(autouse=True)
    def _key(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    def test_apply_switch_forwards_effort_to_resolve(self, monkeypatch):
        import strands_harness.models as harness_models
        from types import SimpleNamespace

        from strands_code_cli.model_switch import apply_switch

        calls: list = []

        def _fake_resolve(*args, **kwargs):
            calls.append((args, kwargs))
            return SimpleNamespace()

        monkeypatch.setattr(harness_models, "resolve_model", _fake_resolve)
        agent = SimpleNamespace()
        _model, resolved = apply_switch(agent, HAIKU, effort="high")
        assert resolved == HAIKU
        assert calls == [((HAIKU, HAIKU), {"effort": "high"})]

    def test_apply_switch_without_effort_calls_two_args(self, monkeypatch):
        import strands_harness.models as harness_models
        from types import SimpleNamespace

        from strands_code_cli.model_switch import apply_switch

        calls: list = []

        def _fake_resolve(*args, **kwargs):
            calls.append((args, kwargs))
            return SimpleNamespace()

        monkeypatch.setattr(harness_models, "resolve_model", _fake_resolve)
        apply_switch(SimpleNamespace(), HAIKU)
        assert calls == [((HAIKU, HAIKU), {})]  # byte-identical two-arg call

    def test_validate_accepts_listed_level_on_reasoning_candidate(self):
        pick = RoutingPick(model=HAIKU, effort="high")
        assert validate_routed_effort(pick, _candidates()) is True

    def test_validate_rejects_unlisted_level(self):
        pick = RoutingPick(model=HAIKU, effort="max")
        assert validate_routed_effort(pick, _candidates()) is False

    def test_validate_rejects_listed_level_on_incapable_candidate(self):
        # nova-micro advertises "low" but supports no thinking: mismatch
        # holds current, never coerces the level.
        pick = RoutingPick(model=NOVA_MICRO, effort="low")
        assert validate_routed_effort(pick, _candidates()) is False

    def test_validate_accepts_auto_and_off_without_advertised_levels(self):
        # SONNET advertises no levels, so any string effort passes the
        # levels gate; auto/off need no thinking support either.
        for effort in ("auto", "off"):
            pick = RoutingPick(model=SONNET, effort=effort)
            assert validate_routed_effort(pick, _candidates()) is True

    def test_validate_rejects_unknown_model(self):
        pick = RoutingPick(model="ghost/1", effort="low")
        assert validate_routed_effort(pick, _candidates()) is False

    def test_apply_model_action_without_effort_resolves_as_before(self, monkeypatch):
        import strands_harness.models as harness_models
        from types import SimpleNamespace

        import strands_code_cli.loop as loop_mod

        real_resolve = harness_models.resolve_model
        calls: list = []

        def _spy_resolve(*args, **kwargs):
            calls.append((args, kwargs))
            return real_resolve(*args, **kwargs)

        monkeypatch.setattr(harness_models, "resolve_model", _spy_resolve)
        agent = SimpleNamespace(messages=[])
        resolved_id, _reply = loop_mod.apply_model_action(
            agent, HAIKU, turn_running=False, current_model=NOVA_MICRO
        )
        assert resolved_id is not None
        assert calls and all("effort" not in kwargs for _, kwargs in calls)

    def test_sequential_calls_run_model_then_effort(self, monkeypatch):
        import urllib.request

        bodies: list = []

        def _fake_urlopen(request, timeout=None):
            bodies.append(json.loads(request.data.decode("utf-8")))
            if _wants_effort(request):
                return _FakeResponse(_effort_payload())
            return _FakeResponse(_route_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, _, usage, _ = decide(
            _strategy(), current_model=SONNET, side=False, ask="hi"
        )
        assert len(bodies) == 2  # exactly two sequential POSTs
        first, second = bodies
        assert set(first["questions"]) == {"pick_model"}
        assert set(second["questions"]) == {"pick_effort"}
        assert second["state"] == first["state"]  # same state reused
        assert set(second["questions"]["pick_effort"]["criteria"]) == {
            "low",
            "high",
        }
        assert pick is not None and pick.effort == "low"
        assert pick.effort_confidence == 0.7
        assert usage[0] == 384 + 384 and usage[1] == 41 + 41

    def test_effort_scoped_to_picked_model_levels_only(self, monkeypatch):
        import urllib.request

        other = "other/model"
        bodies: list = []

        def _fake_urlopen(request, timeout=None):
            bodies.append(json.loads(request.data.decode("utf-8")))
            if _wants_effort(request):
                return _FakeResponse(_effort_payload())
            return _FakeResponse(
                _route_payload(choice=HAIKU, probs={HAIKU: 0.9, other: 0.1})
            )

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        strategy = _strategy(
            candidates=[
                RoutingCandidate(id=HAIKU, levels=["low", "high"]),
                RoutingCandidate(id=other, levels=["medium", "max"]),
            ]
        )
        pick, _, _, _ = decide(
            strategy, current_model=SONNET, side=False, ask="hi"
        )
        assert pick is not None and pick.model == HAIKU
        assert set(bodies[1]["questions"]["pick_effort"]["criteria"]) == {
            "low",
            "high",  # the picked levels only, never the runner-up's
        }

    def test_weak_effort_read_still_routes(self, monkeypatch):
        # Only the model confidence gates (D-16): a 51% effort top-1
        # routes with the top level named on the line.
        import urllib.request

        def _fake_urlopen(request, timeout=None):
            if _wants_effort(request):
                return _FakeResponse(
                    _effort_payload("low", {"low": 0.51, "high": 0.49})
                )
            return _FakeResponse(_route_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, _, _, _ = decide(
            _strategy(), current_model=SONNET, side=False, ask="hi"
        )
        assert pick is not None
        assert (pick.effort, pick.effort_confidence) == ("low", 0.51)
        line = format_routed_line(
            model=pick.model,
            effort=pick.effort,
            model_confidence=pick.model_confidence,
            effort_confidence=pick.effort_confidence,
            tie_break=pick.tie_break,
            prev_model=SONNET,
            ask="hi",
        )
        assert "(low)" in line and "85%" in line and "51%" in line
        assert "~$" in line and "/ask vs" in line

    def test_effort_outside_levels_holds_via_validation(self, monkeypatch):
        # The effort top choice sits outside the advertised set: the
        # shape validates, then validate_routed_effort holds current.
        import urllib.request

        def _fake_urlopen(request, timeout=None):
            if _wants_effort(request):
                return _FakeResponse(
                    _effort_payload("max", {"low": 0.15, "max": 0.85})
                )
            return _FakeResponse(_route_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, engine, usage, detail = decide(
            _strategy(), current_model=SONNET, side=False, ask="hi"
        )
        assert pick is None
        assert engine == "openrouter"
        assert usage == (0, 0, None)
        assert detail == f"effort 'max' unsupported by {HAIKU}"

    def test_single_level_pick_skips_effort_call(self, monkeypatch):
        import urllib.request

        calls: list = []

        def _fake_urlopen(request, timeout=None):
            calls.append(request)
            return _FakeResponse(_route_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        strategy = _strategy(
            candidates=[
                RoutingCandidate(id=HAIKU, levels=["high"]),
                RoutingCandidate(id=NOVA_MICRO, levels=["low"]),
            ]
        )
        pick, _, usage, _ = decide(
            strategy, current_model=SONNET, side=False, ask="hi"
        )
        assert len(calls) == 1  # degenerate choice: no effort question
        assert pick is not None
        assert (pick.effort, pick.effort_confidence) == ("high", None)
        assert usage == (384, 41, 0.000016128)  # call-1 totals only

    def test_failed_effort_call_holds(self, monkeypatch):
        import urllib.request

        def _fake_urlopen(request, timeout=None):
            if _wants_effort(request):
                return _FakeResponse(_route_payload())  # no pick_effort key
            return _FakeResponse(_route_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, engine, usage, detail = decide(
            _strategy(), current_model=SONNET, side=False, ask="hi"
        )
        assert pick is None  # no level to route: hold, never guess
        assert engine == "openrouter"
        assert usage == (0, 0, None)
        assert detail == "openrouter failed"

    def test_cost_absent_effort_keeps_call_1_spend(self, monkeypatch):
        import urllib.request

        def _fake_urlopen(request, timeout=None):
            if _wants_effort(request):
                return _FakeResponse(_effort_payload(cost=None))
            return _FakeResponse(_route_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, _, usage, _ = decide(
            _strategy(), current_model=SONNET, side=False, ask="hi"
        )
        assert pick is not None
        assert usage == (768, 82, 0.000016128)  # None side adds $0, never None


class TestSingleCandidateFastPath:
    def test_single_candidate_asks_effort_only(self, monkeypatch):
        import urllib.request

        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        bodies: list = []

        def _fake_urlopen(request, timeout=None):
            bodies.append(json.loads(request.data.decode("utf-8")))
            return _FakeResponse(_effort_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        strategy = _strategy(
            candidates=[RoutingCandidate(id=HAIKU, levels=["low", "high"])],
            engine=RoutingEngine(
                decision_model="cheap/decider", local_model="nimble"
            ),
        )
        pick, engine, usage, detail = decide(
            strategy, current_model=SONNET, side=False, ask="hi"
        )
        assert len(bodies) == 1  # the effort question only, never a model call
        assert set(bodies[0]["questions"]) == {"pick_effort"}
        assert set(bodies[0]["questions"]["pick_effort"]["criteria"]) == {
            "low",
            "high",
        }
        assert pick == RoutingPick(
            model=HAIKU,
            effort="low",
            model_confidence=None,
            effort_confidence=0.7,
            tie_break=False,
        )
        assert engine == "openrouter"
        assert usage == (384, 41, 0.000016128)  # call-2-only, never zero
        assert usage != (0, 0, None)
        assert detail == ""

    def test_single_candidate_without_levels_holds_with_no_call(self, monkeypatch):
        import urllib.request

        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

        def _boom(request, timeout=None):
            raise AssertionError("no levels to pass: no engine call")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        strategy = _strategy(
            candidates=[RoutingCandidate(id=HAIKU)],
            engine=RoutingEngine(decision_model="cheap/decider"),
        )
        pick, engine, usage, detail = decide(
            strategy, current_model=SONNET, side=False, ask="hi"
        )
        assert pick is None  # a one-option choice is invalid: hold
        assert engine == "none"
        assert usage == (0, 0, None)
        assert detail == "only candidate advertises no levels"

    def test_single_candidate_with_empty_levels_holds_with_no_call(
        self, monkeypatch
    ):
        import urllib.request

        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

        def _boom(request, timeout=None):
            raise AssertionError("no levels to pass: no engine call")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        strategy = _strategy(
            candidates=[RoutingCandidate(id=HAIKU, levels=[])],
            engine=RoutingEngine(decision_model="cheap/decider"),
        )
        pick, engine, _, detail = decide(
            strategy, current_model=SONNET, side=False, ask="hi"
        )
        assert pick is None
        assert engine == "none"
        assert detail == "only candidate advertises no levels"

    def test_single_candidate_with_rejected_first_level_holds(
        self, monkeypatch
    ):
        # Fully degenerate: the lone level rides through with no
        # decision call, then validation holds it.
        import urllib.request

        def _boom(request, timeout=None):
            raise AssertionError("degenerate path must not call any engine")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        strategy = _strategy(
            candidates=[RoutingCandidate(id=NOVA_MICRO, levels=["low"])],
            engine=RoutingEngine(decision_model="cheap/decider"),
        )
        pick, engine, _, detail = decide(
            strategy, current_model=SONNET, side=False, ask="hi"
        )
        assert pick is None
        assert engine == "none"
        assert detail == f"effort 'low' unsupported by {NOVA_MICRO}"

    def test_lone_single_level_routes_with_no_call(self, monkeypatch):
        # Fully degenerate exception to the one-POST rule: a lone
        # single-level candidate has no choice at either stage, and a
        # one-option question violates the 2-26 floor — so the lone
        # level rides through with no decision call.
        import urllib.request

        def _boom(request, timeout=None):
            raise AssertionError("degenerate path must not call any engine")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        strategy = _strategy(
            candidates=[RoutingCandidate(id=HAIKU, levels=["high"])],
            engine=RoutingEngine(decision_model="cheap/decider"),
        )
        pick, engine, usage, detail = decide(
            strategy, current_model=SONNET, side=False, ask="hi"
        )
        assert pick == RoutingPick(
            model=HAIKU,
            effort="high",
            model_confidence=None,
            effort_confidence=None,
            tie_break=False,
        )
        assert engine == "none"
        assert usage == (0, 0, None)
        assert detail == ""

    def test_single_candidate_with_rejected_decided_level_holds(
        self, monkeypatch
    ):
        import urllib.request

        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        calls: list = []

        def _fake_urlopen(request, timeout=None):
            calls.append(request)
            return _FakeResponse(
                _effort_payload("max", {"low": 0.15, "max": 0.85})
            )

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        strategy = _strategy(
            candidates=[RoutingCandidate(id=HAIKU, levels=["low", "high"])],
            engine=RoutingEngine(decision_model="cheap/decider"),
        )
        pick, engine, _, detail = decide(
            strategy, current_model=SONNET, side=False, ask="hi"
        )
        assert len(calls) == 1
        assert pick is None
        assert engine == "openrouter"
        assert detail == f"effort 'max' unsupported by {HAIKU}"

    def test_hook_prints_routed_line_with_effort_usage(
        self, monkeypatch, capsys
    ):
        import urllib.request
        from types import SimpleNamespace

        import strands_code_cli.loop as loop_mod
        import strands_code_cli.routing as routing_mod

        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

        def _fake_urlopen(request, timeout=None):
            return _FakeResponse(_effort_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        strategy = _strategy(
            candidates=[RoutingCandidate(id=HAIKU, levels=["low", "high"])],
        )
        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: strategy)
        events: list = []
        model = loop_mod._route_pre_turn(
            SimpleNamespace(),
            current_model=HAIKU,  # same-model no-op: no switch, still a line
            ask_text="fix the typo",
            rich=None,
            index=None,
            session_id="s",
            stash_path=None,
            routing=RoutingState(initial="on"),
            routing_events=events,
        )
        assert model == HAIKU
        assert events == [
            {
                "ask": 1,
                "side": False,
                "model": HAIKU,
                "effort": "low",
                "model_confidence": None,
                "effort_confidence": 0.7,
                "tie_break": False,
                "engine": "openrouter",
                "input_tokens": 384,
                "output_tokens": 41,
                "decision_cost": 0.000016128,
                "held": False,
                "decision_model": "cheap/decider",
            }
        ]
        shown = " ".join(capsys.readouterr().out.split())
        assert f"Routed → {HAIKU} (low): model n/a, effort 70%" in shown


class TestLiveEngines:
    def test_stub_server_systemone_decision_routes(self):
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        seen: dict = {}
        canned = _decision_payload(
            _answer(HAIKU, {HAIKU: 0.85, NOVA_MICRO: 0.15}),
            input_tokens=90,
            output_tokens=12,
            cost=None,
            model="nimble",
        )
        canned_effort = _effort_payload(
            input_tokens=30, output_tokens=4, cost=None, model="nimble"
        )

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.setdefault("gets", []).append(self.path)
                if self.path == "/api/version":
                    payload: dict = {"version": "0.40.3"}
                elif self.path == "/api/tags":
                    payload = {"models": [{"name": "stub-model"}]}
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                seen["path"] = self.path
                seen.setdefault("bodies", []).append(
                    json.loads(self.rfile.read(length).decode("utf-8"))
                )
                payload = canned_effort if (
                    "pick_effort" in seen["bodies"][-1].get("questions", {})
                ) else canned
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            strategy = _strategy(
                candidates=_candidates()[:2],
                engine=RoutingEngine(
                    primary="local",
                    local_model="stub-model",
                    local_base_url=f"http://127.0.0.1:{port}",
                ),
            )
            pick, engine, usage, _ = decide(
                strategy, current_model=SONNET, side=False, ask="hi"
            )
        finally:
            server.shutdown()
            thread.join(timeout=10)
            server.server_close()
        assert pick == RoutingPick(
            model=HAIKU,
            effort="low",
            model_confidence=0.85,
            effort_confidence=0.7,
            tie_break=False,
        )
        assert engine == "local"
        assert usage == (120, 16, None)
        assert seen["path"] == "/v1/systemone"
        assert seen["gets"] == ["/api/version", "/api/tags"]  # preflight first
        assert len(seen["bodies"]) == 2  # model call, then the effort call
        for body in seen["bodies"]:
            assert body["model"] == "stub-model"
            assert body["keep_alive"] == "5m"
            assert set(body["state"]) == {"ask", "directives", "side"}
        assert seen["bodies"][0]["questions"]["pick_model"]["type"] == "choice"
        assert set(seen["bodies"][1]["questions"]) == {"pick_effort"}

    @pytest.mark.integration
    def test_openrouter_live_decision_returns_answers(self):
        import os

        if not os.environ.get("OPENROUTER_API_KEY"):
            pytest.skip("OPENROUTER_API_KEY not set")
        # Pinned id re-verified against the live decisions catalog at
        # implementation time (2026-10-12: 19 entries, jev ctx 64000).
        decision_model = "typesafe/jev-1.13"
        from strands_code_cli.routing import (
            build_decision_state,
            build_model_question,
        )

        candidates = [RoutingCandidate(id="live/a"), RoutingCandidate(id="live/b")]
        state = build_decision_state(
            ask="live probe", directives="live probe", side=False
        )
        questions = {
            "pick_model": build_model_question(
                candidates=candidates, directives="live probe"
            )
        }
        result = decide_via_openrouter(
            decision_model=decision_model, state=state, questions=questions
        )
        assert result.answers is not None, (
            "live decision call failed — check key, quota, and network"
        )
        assert result.input_tokens >= 0 and result.output_tokens >= 0

    @pytest.mark.integration
    def test_ollama_live_daemon_decision_returns_answers(self):
        import os
        import urllib.request

        if not os.environ.get("OLLAMA_LIVE"):
            pytest.skip("OLLAMA_LIVE not set")
        base = os.environ.get("OLLAMA_HOST") or OLLAMA_DEFAULT_HOST
        try:
            with urllib.request.urlopen(
                urllib.request.Request(
                    f"{base.rstrip('/')}/api/tags",
                    headers={"User-Agent": "strands-code"},
                ),
                timeout=10,
            ) as response:
                tags = json.loads(response.read().decode("utf-8"))
        except Exception:
            pytest.skip(f"Ollama daemon unreachable at {base}")
        names = [
            model.get("name")
            for model in tags.get("models", [])
            if isinstance(model, dict) and model.get("name")
        ]
        wanted = os.environ.get("OLLAMA_TEST_MODEL")
        if wanted:
            if wanted not in names:
                pytest.skip(f"OLLAMA_TEST_MODEL {wanted} not pulled")
            model = wanted
        elif "tev1:0.8b" in names:
            model = "tev1:0.8b"
        else:
            pytest.skip("no decision model pulled in the daemon")
        state = build_decision_state(
            ask="live probe", directives="live probe", side=False
        )
        questions = {
            "pick_model": build_model_question(
                candidates=[
                    RoutingCandidate(id="live/a"),
                    RoutingCandidate(id="live/b"),
                ],
                directives="live probe",
            )
        }
        result = decide_via_ollama(
            local_model=model, state=state, questions=questions, timeout=120
        )
        assert result.answers is not None, f"live Ollama decision failed on {model}"
