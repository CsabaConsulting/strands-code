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
    build_model_question,
    decide,
    decide_via_ollama,
    decide_via_openrouter,
    gate_model,
    load_strategy,
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
    input_tokens: int = 384,
    output_tokens: int = 41,
    cost: float | None = 0.000016128,
    model: str = "typesafe/jev-1.13-20260917",
) -> dict:
    usage: dict = {"input_tokens": input_tokens, "output_tokens": output_tokens}
    if cost is not None:
        usage["cost"] = cost
    return {"model": model, "answers": {"pick_model": answer}, "usage": usage}


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
            return _FakeResponse(_route_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, engine, usage, detail = decide(
            _strategy(), current_model=SONNET, side=False, ask="hi"
        )
        assert len(calls) == 1
        assert pick == RoutingPick(
            model=HAIKU,
            effort="low",  # first advertised level passthrough
            model_confidence=0.85,
            effort_confidence=None,
            tie_break=False,
        )
        assert engine == "openrouter"
        assert usage == (384, 41, 0.000016128)  # reported triple, cost verbatim
        assert detail == ""

    def test_openrouter_posts_decision_contract(self, monkeypatch):
        import urllib.request

        seen: dict = {}

        def _fake_urlopen(request, timeout=None):
            seen["url"] = request.full_url
            seen["body"] = json.loads(request.data.decode("utf-8"))
            seen["auth"] = request.get_header("Authorization")
            seen["timeout"] = timeout
            return _FakeResponse(_route_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        decide(_strategy(), current_model=SONNET, side=False, ask="hi")
        assert seen["url"] == OPENROUTER_DECISIONS_URL
        assert seen["url"] == "https://openrouter.ai/api/alpha/decisions"
        body = seen["body"]
        assert body["model"] == "cheap/decider"
        assert body["state"] == {
            "ask": "hi",
            "directives": "trivial asks go cheap",
            "side": False,
        }
        assert body["questions"]["pick_model"]["type"] == "choice"
        assert set(body["questions"]["pick_model"]["criteria"]) == {
            HAIKU,
            NOVA_MICRO,
        }
        assert "response_format" not in body  # no legacy JSON mode
        assert "messages" not in body and "max_tokens" not in body
        assert seen["auth"] == "Bearer " + "test-key"  # header-only, not in URL
        assert seen["timeout"] == 10

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
            step = script.pop(0) if script else None
            if isinstance(step, Exception):
                raise step
            return _FakeResponse(_route_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, engine, _, _ = decide(
            _strategy(), current_model=SONNET, side=False, ask="hi"
        )
        assert len(calls) == 2  # at most one retry
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
            step = script.pop(0) if script else None
            if isinstance(step, Exception):
                raise step
            return _FakeResponse(_route_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, _, _, _ = decide(
            _strategy(), current_model=SONNET, side=False, ask="hi"
        )
        assert len(calls) == 2
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
            step = script.pop(0) if script else None
            if isinstance(step, Exception):
                raise step
            return _FakeResponse(_route_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, _, _, _ = decide(
            _strategy(), current_model=SONNET, side=False, ask="hi"
        )
        assert len(calls) == 2
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
            if "openrouter" in request.full_url:
                bad = _answer(HAIKU, {HAIKU: 0.5, NOVA_MICRO: 0.5, SONNET: 0.5})
                return _FakeResponse(_decision_payload(bad))
            return _FakeResponse(_route_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
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

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
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
        # The picked candidate's first advertised level rides through
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
            return _FakeResponse(_route_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, engine, _, _ = decide(
            self._dual(), current_model=SONNET, side=False, ask="hi"
        )
        assert urls == [OPENROUTER_DECISIONS_URL]
        assert pick == RoutingPick(
            model=HAIKU,
            effort="low",
            model_confidence=0.85,
            effort_confidence=None,
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
            return _FakeResponse(self._local_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, engine, usage, _ = decide(
            self._dual(), current_model=SONNET, side=False, ask="hi"
        )
        assert len(urls) == 2  # one attempt per engine, no in-ask retry
        assert urls[1].startswith(OLLAMA_DEFAULT_HOST)
        assert urls[1] == f"{OLLAMA_DEFAULT_HOST}/v1/systemone"
        assert pick is not None and pick.model == HAIKU
        assert engine == "local"
        assert usage == (384, 41, None)  # local spend records as None

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
        assert detail == "local failed"

    def test_primary_local_skips_the_api(self, monkeypatch):
        import urllib.request

        urls: list[str] = []

        def _fake_urlopen(request, timeout=None):
            urls.append(request.full_url)
            assert "openrouter" not in request.full_url
            return _FakeResponse(self._local_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        strategy = self._dual(primary="local")
        pick, engine, _, _ = decide(
            strategy, current_model=SONNET, side=False, ask="hi"
        )
        assert len(urls) == 1
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
            return _FakeResponse(self._local_payload())

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
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
            return _FakeResponse(
                _decision_payload(
                    _answer(HAIKU, {HAIKU: 0.85, NOVA_MICRO: 0.15}),
                    input_tokens=90,
                    output_tokens=12,
                    cost=None,
                )
            )

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        result = decide_via_ollama(
            local_model="nimble", state={}, questions={}
        )
        assert (result.input_tokens, result.output_tokens) == (90, 12)
        assert result.cost is None
        _, _, usage, _ = decide(
            self._dual(primary="local"), current_model=SONNET, side=False, ask="hi"
        )
        assert usage == (90, 12, None)

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

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
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


class TestRoutedEffort:
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


class TestSingleCandidateFastPath:
    def test_single_candidate_passes_first_advertised_level(self, monkeypatch):
        # Interim 08-01 shape: nothing to choose, so the first
        # advertised level rides through with zero engine calls; the
        # effort decision call lands in plan 08-02.
        import urllib.request

        def _boom(request, timeout=None):
            raise AssertionError("fast path must not call any engine")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        strategy = _strategy(
            candidates=[RoutingCandidate(id=HAIKU, levels=["low", "high"])],
            engine=RoutingEngine(
                decision_model="cheap/decider", local_model="nimble"
            ),
        )
        pick, engine, usage, detail = decide(
            strategy, current_model=SONNET, side=False, ask="hi"
        )
        assert pick == RoutingPick(
            model=HAIKU,
            effort="low",
            model_confidence=None,
            effort_confidence=None,
            tie_break=False,
        )
        assert engine == "none"
        assert usage == (0, 0, None)
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
        import urllib.request

        def _boom(request, timeout=None):
            raise AssertionError("fast path must not call any engine")

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

    def test_hook_prints_routed_line_with_zero_token_event(
        self, monkeypatch, capsys
    ):
        import urllib.request
        from types import SimpleNamespace

        import strands_code_cli.loop as loop_mod
        import strands_code_cli.routing as routing_mod

        def _boom(request, timeout=None):
            raise AssertionError("fast path must not call any engine")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
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
                "effort_confidence": None,
                "tie_break": False,
                "engine": "none",
                "input_tokens": 0,
                "output_tokens": 0,
                "decision_cost": None,
                "held": False,
                "decision_model": None,
            }
        ]
        shown = " ".join(capsys.readouterr().out.split())
        assert f"Routed → {HAIKU} (low): model n/a, effort n/a" in shown


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

        class _Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                seen["path"] = self.path
                seen["body"] = json.loads(self.rfile.read(length).decode("utf-8"))
                body = json.dumps(canned).encode("utf-8")
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
            effort_confidence=None,
            tie_break=False,
        )
        assert engine == "local"
        assert usage == (90, 12, None)
        assert seen["path"] == "/v1/systemone"
        body = seen["body"]
        assert body["model"] == "stub-model"
        assert body["keep_alive"] == "5m"
        assert set(body["state"]) == {"ask", "directives", "side"}
        assert body["questions"]["pick_model"]["type"] == "choice"

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
