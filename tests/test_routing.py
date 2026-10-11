"""Routing prompt, strict parse, and engine chain tests (MODEL-03 tracer).

No live decision calls: the urllib seam serves canned JSON and the
prompt tests use canned or static-table prices only.
"""

from __future__ import annotations

import json
import urllib.error

import pytest

from strands_code_cli.routing import (
    OLLAMA_DEFAULT_HOST,
    EngineResult,
    RoutingCandidate,
    RoutingEngine,
    RoutingPick,
    RoutingStrategy,
    _ENGINE_REGISTRY,
    build_routing_prompt,
    decide,
    decide_via_ollama,
    decide_via_openrouter,
    load_strategy,
    parse_pick,
    validate_routed_effort,
)

HAIKU = "bedrock/anthropic.claude-haiku-4-5-20251001-v1:0"
NOVA_MICRO = "bedrock/amazon.nova-micro-v1:0"
SONNET = "bedrock/anthropic.claude-sonnet-4-6"


def _candidates() -> list[RoutingCandidate]:
    return [
        RoutingCandidate(id=HAIKU, tier="small", note="cheap", levels=["low", "high"]),
        RoutingCandidate(id=NOVA_MICRO, tier="tiny", levels=["low"]),
        RoutingCandidate(id=SONNET, tier="mid"),
    ]


def _strategy(**kwargs) -> RoutingStrategy:
    return RoutingStrategy(
        candidates=kwargs.pop("candidates", _candidates()[:2]),
        directives=kwargs.pop("directives", "trivial asks go cheap"),
        engine=kwargs.pop("engine", RoutingEngine(decision_model="cheap/decider")),
        **kwargs,
    )


class TestRoutingPrompt:
    def test_prompt_carries_directives_table_current_side_and_ask(self, monkeypatch):
        import strands_code_cli.routing as routing_mod

        monkeypatch.setattr(routing_mod, "price_for", lambda model: (3.0, 15.0))
        monkeypatch.setattr(routing_mod, "window_for", lambda model: 200000)
        system, user = build_routing_prompt(
            directives="trivial asks go cheap",
            candidates=_candidates()[:2],
            current_model=HAIKU,
            side=False,
            ask="fix the typo",
        )
        assert "JSON only" in system
        assert "verbatim" in system
        assert "trivial asks go cheap" in user  # directives verbatim
        assert HAIKU in user and NOVA_MICRO in user  # one line per candidate
        assert "$3/$15 per 1M" in user  # live price values
        assert "200000" in user  # live window values
        assert "low,high" in user  # advertised levels
        assert f"Current model: {HAIKU}" in user
        assert "Side ask: false" in user
        assert "fix the typo" in user

    def test_prompt_marks_side_asks(self):
        _, user = build_routing_prompt(
            directives="",
            candidates=_candidates()[:1],
            current_model=HAIKU,
            side=True,
            ask="quick question",
        )
        assert "Side ask: true" in user

    def test_prompt_truncates_long_asks(self):
        long_ask = "x" * 5000
        _, user = build_routing_prompt(
            directives="d",
            candidates=_candidates()[:1],
            current_model=HAIKU,
            side=False,
            ask=long_ask,
        )
        tail = user.rsplit("\n", 1)[-1]
        assert tail == "x" * 2000
        assert long_ask not in user

    def test_prompt_uses_static_prices_without_monkeypatch(self):
        # Static table hit: nova-micro is priced at 0.035/0.14 per 1M.
        _, user = build_routing_prompt(
            directives="d",
            candidates=[RoutingCandidate(id=NOVA_MICRO)],
            current_model=HAIKU,
            side=False,
            ask="hi",
        )
        assert "$0.035/$0.14 per 1M" in user

    def test_prompt_never_carries_history_or_tool_text(self):
        _, user = build_routing_prompt(
            directives="d",
            candidates=_candidates()[:1],
            current_model=HAIKU,
            side=False,
            ask="plain ask",
        )
        assert "toolUse" not in user
        assert "toolResult" not in user
        assert "reasoningContent" not in user


class TestParsePick:
    def test_well_formed_pick_returns_model_effort_why(self):
        pick = parse_pick(
            json.dumps({"model": HAIKU, "effort": "high", "why": "cheap and fast"}),
            _candidates(),
        )
        assert pick == RoutingPick(model=HAIKU, effort="high", why="cheap and fast")

    def test_unknown_model_id_holds_with_no_fuzzy_match(self):
        near_miss = HAIKU + "x"  # one char off: must NOT fuzzy-match
        assert parse_pick(
            json.dumps({"model": near_miss, "effort": "high", "why": "close"}),
            _candidates(),
        ) is None

    def test_non_listed_effort_holds(self):
        assert parse_pick(
            json.dumps({"model": HAIKU, "effort": "max", "why": "too much"}),
            _candidates(),
        ) is None

    def test_malformed_json_holds(self):
        assert parse_pick("{not json", _candidates()) is None
        assert parse_pick('["model"]', _candidates()) is None
        assert parse_pick("", _candidates()) is None
        assert parse_pick(None, _candidates()) is None

    def test_missing_model_key_holds(self):
        assert parse_pick(
            json.dumps({"effort": "high", "why": "no model"}), _candidates()
        ) is None

    def test_why_truncates_to_one_line(self):
        pick = parse_pick(
            json.dumps(
                {"model": HAIKU, "effort": "low", "why": "first line\nsecond line"}
            ),
            _candidates(),
        )
        assert pick is not None
        assert pick.why == "first line"

    def test_effort_without_advertised_levels_accepts_any_string(self):
        pick = parse_pick(
            json.dumps({"model": SONNET, "effort": "medium", "why": "mid work"}),
            _candidates(),
        )
        assert pick == RoutingPick(model=SONNET, effort="medium", why="mid work")


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


def _chat_payload(content: str | None) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def _pick_json(model: str = HAIKU, effort: str = "high") -> str:
    return json.dumps({"model": model, "effort": effort, "why": "cheap and fast"})


class TestEngineChain:
    @pytest.fixture(autouse=True)
    def _key(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    def test_openrouter_success_short_circuits_with_one_call(self, monkeypatch):
        import urllib.request

        calls: list = []

        def _fake_urlopen(request, timeout=None):
            calls.append(request)
            return _FakeResponse(_chat_payload(_pick_json()))

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, engine, usage = decide(
            _strategy(), current_model=SONNET, side=False, ask="hi"
        )
        assert len(calls) == 1
        assert pick == RoutingPick(model=HAIKU, effort="high", why="cheap and fast")
        assert engine == "openrouter"
        assert usage == (0, 0)  # no usage fields: zeros, not absence

    def test_openrouter_posts_json_contract(self, monkeypatch):
        import urllib.request

        seen: dict = {}

        def _fake_urlopen(request, timeout=None):
            seen["url"] = request.full_url
            seen["body"] = json.loads(request.data.decode("utf-8"))
            seen["auth"] = request.get_header("Authorization")
            return _FakeResponse(_chat_payload(_pick_json()))

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        decide(_strategy(), current_model=SONNET, side=False, ask="hi")
        assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
        assert seen["body"]["response_format"] == {"type": "json_object"}
        assert seen["body"]["max_tokens"] == 300
        assert seen["body"]["temperature"] == 0
        assert seen["body"]["model"] == "cheap/decider"
        assert seen["auth"] == "Bearer test-key"  # header-only, never in the URL

    def test_openrouter_failure_yields_hold_current(self, monkeypatch):
        import urllib.request

        def _fake_urlopen(request, timeout=None):
            return _FakeResponse({"choices": []})  # empty choices: no content

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, engine, usage = decide(
            _strategy(), current_model=SONNET, side=False, ask="hi"
        )
        assert pick is None
        assert engine == "openrouter"
        assert usage == (0, 0)

    def test_url_error_yields_hold_current(self, monkeypatch):
        import urllib.request

        def _boom(request, timeout=None):
            raise urllib.error.URLError("offline")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        assert (
            decide_via_openrouter(decision_model="m", system="s", user="u").text is None
        )
        pick, _, _ = decide(_strategy(), current_model=SONNET, side=False, ask="hi")
        assert pick is None

    def test_timeout_yields_hold_current(self, monkeypatch):
        import urllib.request

        def _slow(request, timeout=None):
            raise TimeoutError("slow engine")

        monkeypatch.setattr(urllib.request, "urlopen", _slow)
        assert (
            decide_via_openrouter(decision_model="m", system="s", user="u").text is None
        )
        pick, _, _ = decide(_strategy(), current_model=SONNET, side=False, ask="hi")
        assert pick is None

    def test_missing_key_yields_hold_without_network(self, monkeypatch):
        import urllib.request

        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        def _boom(request, timeout=None):
            raise AssertionError("must not call the network without a key")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        pick, engine, _ = decide(
            _strategy(), current_model=SONNET, side=False, ask="hi"
        )
        assert pick is None
        assert engine == "openrouter"

    def test_unparseable_engine_output_yields_hold(self, monkeypatch):
        import urllib.request

        def _fake_urlopen(request, timeout=None):
            return _FakeResponse(_chat_payload("definitely not json"))

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, _, _ = decide(_strategy(), current_model=SONNET, side=False, ask="hi")
        assert pick is None

    def test_missing_decision_model_skips_openrouter(self, monkeypatch):
        import urllib.request

        def _boom(request, timeout=None):
            raise AssertionError("no decision model: no call")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        strategy = _strategy(engine=RoutingEngine())
        pick, engine, _ = decide(strategy, current_model=SONNET, side=False, ask="hi")
        assert pick is None
        assert engine == "openrouter"

    def test_openrouter_usage_fields_feed_the_usage_pair(self, monkeypatch):
        import urllib.request

        payload = _chat_payload(_pick_json())
        payload["usage"] = {"prompt_tokens": 120, "completion_tokens": 25}

        def _fake_urlopen(request, timeout=None):
            return _FakeResponse(payload)

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        result = decide_via_openrouter(decision_model="m", system="s", user="u")
        assert (result.input_tokens, result.output_tokens) == (120, 25)
        _, _, usage = decide(_strategy(), current_model=SONNET, side=False, ask="hi")
        assert usage == (120, 25)

    def test_registry_orders_openrouter_first(self):
        assert _ENGINE_REGISTRY and _ENGINE_REGISTRY[0][0] == "openrouter"


def _ollama_payload(content: str | None, prompt_eval: int = 0, eval_count: int = 0) -> dict:
    return {
        "message": {"content": content},
        "prompt_eval_count": prompt_eval,
        "eval_count": eval_count,
        "done": True,
    }


class TestLocalEngine:
    @pytest.fixture(autouse=True)
    def _keys(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)

    def _dual(self, **engine_kwargs) -> RoutingStrategy:
        engine = RoutingEngine(decision_model="cheap/decider", local_model="qwen3:8b")
        for key, value in engine_kwargs.items():
            setattr(engine, key, value)
        return _strategy(engine=engine)

    def test_openrouter_success_short_circuits_with_no_local_call(self, monkeypatch):
        import urllib.request

        urls: list[str] = []

        def _fake_urlopen(request, timeout=None):
            urls.append(request.full_url)
            return _FakeResponse(_chat_payload(_pick_json()))

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, engine, _ = decide(self._dual(), current_model=SONNET, side=False, ask="hi")
        assert urls == ["https://openrouter.ai/api/v1/chat/completions"]
        assert pick == RoutingPick(model=HAIKU, effort="high", why="cheap and fast")
        assert engine == "openrouter"

    def test_openrouter_failure_falls_back_to_local_pick(self, monkeypatch):
        import urllib.request

        urls: list[str] = []

        def _fake_urlopen(request, timeout=None):
            urls.append(request.full_url)
            if "openrouter" in request.full_url:
                raise urllib.error.URLError("api down")
            return _FakeResponse(_ollama_payload(_pick_json(NOVA_MICRO, "low")))

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, engine, _ = decide(self._dual(), current_model=SONNET, side=False, ask="hi")
        assert len(urls) == 2  # one attempt per engine, no in-ask retry
        assert urls[1].startswith(OLLAMA_DEFAULT_HOST)
        assert pick == RoutingPick(model=NOVA_MICRO, effort="low", why="cheap and fast")
        assert engine == "local"

    def test_both_failing_holds_current(self, monkeypatch):
        import urllib.request

        def _boom(request, timeout=None):
            raise urllib.error.URLError("offline")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        pick, engine, usage = decide(
            self._dual(), current_model=SONNET, side=False, ask="hi"
        )
        assert pick is None
        assert engine == "local"  # last attempted engine
        assert usage == (0, 0)

    def test_primary_local_skips_the_api(self, monkeypatch):
        import urllib.request

        urls: list[str] = []

        def _fake_urlopen(request, timeout=None):
            urls.append(request.full_url)
            assert "openrouter" not in request.full_url
            return _FakeResponse(_ollama_payload(_pick_json()))

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        strategy = self._dual(primary="local")
        pick, engine, _ = decide(strategy, current_model=SONNET, side=False, ask="hi")
        assert len(urls) == 1
        assert pick is not None and engine == "local"

    def test_primary_local_failure_holds_without_api_call(self, monkeypatch):
        import urllib.request

        def _boom(request, timeout=None):
            raise TimeoutError("cold daemon")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        strategy = self._dual(primary="local")
        pick, engine, _ = decide(strategy, current_model=SONNET, side=False, ask="hi")
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
        pick, engine, _ = decide(strategy, current_model=SONNET, side=False, ask="hi")
        assert pick is None
        assert engine == "openrouter"  # local skipped, not failed
        assert urls == ["https://openrouter.ai/api/v1/chat/completions"]

    def test_no_engine_configured_makes_zero_calls(self, monkeypatch):
        import urllib.request

        def _boom(request, timeout=None):
            raise AssertionError("no usable engine: no network attempt")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        strategy = _strategy(engine=RoutingEngine())
        pick, engine, usage = decide(strategy, current_model=SONNET, side=False, ask="hi")
        assert (pick, engine, usage) == (None, "openrouter", (0, 0))

    def test_non_http_base_url_warns_and_uses_default_host(
        self, tmp_path, monkeypatch, caplog
    ):
        path = tmp_path / "routing.yaml"
        path.write_text(
            "candidates:\n"
            f"  - id: {HAIKU}\n"
            "engine: {primary: local, local_model: qwen3:8b, "
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
            return _FakeResponse(_ollama_payload(_pick_json()))

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        strategy = self._dual(primary="local")
        pick, _, _ = decide(strategy, current_model=SONNET, side=False, ask="hi")
        assert pick is not None
        assert seen["url"] == f"{OLLAMA_DEFAULT_HOST}/api/chat"
        assert seen["timeout"] == 30

    def test_ollama_posts_chat_contract(self, monkeypatch):
        import urllib.request

        seen: dict = {}

        def _fake_urlopen(request, timeout=None):
            seen["body"] = json.loads(request.data.decode("utf-8"))
            seen["auth"] = request.get_header("Authorization")
            return _FakeResponse(_ollama_payload(_pick_json()))

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        result = decide_via_ollama(local_model="qwen3:8b", system="s", user="u")
        assert result.text == _pick_json()
        body = seen["body"]
        assert body["model"] == "qwen3:8b"
        assert body["stream"] is False
        assert body["keep_alive"] == "5m"
        assert [m["role"] for m in body["messages"]] == ["system", "user"]
        fmt = body["format"]
        assert fmt["type"] == "object"
        assert set(fmt["properties"]) == {"model", "effort", "why"}
        assert seen["auth"] is None  # localhost never carries key material

    def test_ollama_usage_comes_from_eval_counts(self, monkeypatch):
        import urllib.request

        def _fake_urlopen(request, timeout=None):
            return _FakeResponse(_ollama_payload(_pick_json(), 90, 12))

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        result = decide_via_ollama(local_model="qwen3:8b", system="s", user="u")
        assert (result.input_tokens, result.output_tokens) == (90, 12)
        _, _, usage = decide(
            self._dual(primary="local"), current_model=SONNET, side=False, ask="hi"
        )
        assert usage == (90, 12)

    def test_proxied_host_carries_bearer_key(self, monkeypatch):
        import urllib.request

        monkeypatch.setenv("OLLAMA_API_KEY", "proxy-secret")
        seen: dict = {}

        def _fake_urlopen(request, timeout=None):
            seen["url"] = request.full_url
            seen["auth"] = request.get_header("Authorization")
            return _FakeResponse(_ollama_payload(_pick_json()))

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        result = decide_via_ollama(
            local_model="qwen3:8b",
            local_base_url="http://gpu-box.example:11434",
            system="s",
            user="u",
        )
        assert result.text == _pick_json()
        assert seen["url"] == "http://gpu-box.example:11434/api/chat"
        assert seen["auth"] == "Bearer " + "proxy-secret"

    def test_invalid_base_url_at_call_time_fails_soft(self, monkeypatch):
        import urllib.request

        def _boom(request, timeout=None):
            raise AssertionError("invalid base URL: no call")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        strategy = self._dual(
            primary="local", local_base_url="gopher://daemon.local/"
        )
        pick, engine, _ = decide(strategy, current_model=SONNET, side=False, ask="hi")
        assert pick is None
        assert engine == "local"

    def test_local_non_candidate_pick_holds_without_fuzzy_match(self, monkeypatch):
        import urllib.request

        near_miss = HAIKU + "x"  # one char off: must NOT fuzzy-match

        def _fake_urlopen(request, timeout=None):
            return _FakeResponse(_ollama_payload(_pick_json(near_miss)))

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        pick, engine, _ = decide(
            self._dual(primary="local"), current_model=SONNET, side=False, ask="hi"
        )
        assert pick is None
        assert engine == "local"

    def test_registry_orders_local_second(self):
        assert [name for name, _ in _ENGINE_REGISTRY] == ["openrouter", "local"]

    def test_engine_result_defaults_to_zero_usage(self):
        assert EngineResult(text=None) == EngineResult(
            text=None, input_tokens=0, output_tokens=0
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
        pick = RoutingPick(model=HAIKU, effort="high", why="deep work")
        assert validate_routed_effort(pick, _candidates()) is True

    def test_validate_rejects_unlisted_level(self):
        pick = RoutingPick(model=HAIKU, effort="max", why="too much")
        assert validate_routed_effort(pick, _candidates()) is False

    def test_validate_rejects_listed_level_on_incapable_candidate(self):
        # nova-micro advertises "low" but supports no thinking: mismatch
        # holds current, never coerces the level.
        pick = RoutingPick(model=NOVA_MICRO, effort="low", why="cheap")
        assert validate_routed_effort(pick, _candidates()) is False

    def test_validate_accepts_auto_and_off_without_advertised_levels(self):
        # SONNET advertises no levels, so any string effort passes the
        # levels gate; auto/off need no thinking support either.
        for effort in ("auto", "off"):
            pick = RoutingPick(model=SONNET, effort=effort, why="default")
            assert validate_routed_effort(pick, _candidates()) is True

    def test_validate_rejects_unknown_model(self):
        pick = RoutingPick(model="ghost/1", effort="low", why="ghost")
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
