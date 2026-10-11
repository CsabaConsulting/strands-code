"""Pre-turn routing hook tests (MODEL-03 tracer).

Drives run_loop end to end with a mocked OpenRouter decision: the
urllib-adjacent seam patched is decide_via_openrouter (canned
EngineResult), while decide/parse/prompt and apply_model_action run
for real.
"""

from __future__ import annotations

import json
from contextlib import nullcontext
from types import SimpleNamespace

import sys

import pytest

import strands_code_cli.loop as loop_mod
import strands_code_cli.routing as routing_mod
from strands_code_cli.provider_config import ProviderConfig
from strands_code_cli.router import USAGE_HINT, dispatch
from strands_code_cli.routing import (
    MODEL_ROUTING_KEEP_REPLY,
    ROUTE_USAGE,
    ROUTING_MANUAL_OFF_NOTE,
    ROUTING_OFF_REPLY,
    EngineResult,
    RoutingCandidate,
    RoutingEngine,
    RoutingState,
    RoutingStrategy,
)
from strands_code_cli.session_index import SessionIndex
from strands_code_cli.skills import SkillIndex

HAIKU = "bedrock/anthropic.claude-haiku-4-5-20251001-v1:0"
NOVA_MICRO = "bedrock/amazon.nova-micro-v1:0"


def _strategy(candidates=None) -> RoutingStrategy:
    return RoutingStrategy(
        candidates=(
            candidates
            if candidates is not None
            else [
                RoutingCandidate(id=HAIKU, tier="small", levels=["low", "high"]),
                RoutingCandidate(id=NOVA_MICRO, tier="tiny", levels=["low"]),
            ]
        ),
        directives="trivial asks go cheap",
        engine=RoutingEngine(decision_model="cheap/decider"),
    )


def _pick_result(
    model: str, effort: str = "high", usage: tuple[int, int] = (0, 0)
) -> EngineResult:
    return EngineResult(
        text=json.dumps({"model": model, "effort": effort, "why": "cheap and fast"}),
        input_tokens=usage[0],
        output_tokens=usage[1],
    )


@pytest.fixture(autouse=True)
def _hermetic_fact_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(loop_mod, "MEMORY_FACT_DIR", tmp_path / "memory")


def _drive(monkeypatch, prompts, agent, index, model_id, invoke):
    """Drive run_loop with faked prompt/steering/output seams."""
    monkeypatch.setattr(loop_mod, "output_context", nullcontext)
    queue = iter(prompts)

    class _Session:
        def __init__(self, *args, **kwargs):
            pass

        def prompt(self, *args, **kwargs):
            try:
                return next(queue)
            except StopIteration:
                raise EOFError

    monkeypatch.setattr(loop_mod, "PromptSession", _Session)
    monkeypatch.setattr(loop_mod, "_invoke_agent", invoke)
    monkeypatch.setattr(
        loop_mod, "_steering_slot_for", lambda agent: SimpleNamespace(state=None)
    )
    monkeypatch.setattr(
        loop_mod,
        "start_steering_reader",
        lambda *args, **kwargs: SimpleNamespace(stop=lambda: None),
    )
    loop_mod.run_loop(
        agent, session_id=index.mint(), index=index, model_id=model_id
    )


def _serving_invoke(calls):
    """Fake turn: record (text, serving model id), append a Q/A pair."""

    def _invoke(agent, text, event, **kwargs):
        from strands_code_cli.model_switch import model_id_of

        calls.append((text, model_id_of(getattr(agent, "model", None), "?")))
        agent.messages.append({"role": "user", "content": [{"text": text}]})
        agent.messages.append({"role": "assistant", "content": [{"text": "hi"}]})
        return None

    return _invoke


def _quiet_invoke(calls):
    """Fake turn: record only, never touch history (isolates the hook)."""

    def _invoke(agent, text, event, **kwargs):
        calls.append(text)
        return None

    return _invoke


def _no_persist(monkeypatch, saved):
    def _fake_save(self, model, path=None):
        saved.append(model)

    monkeypatch.setattr(ProviderConfig, "save_model_choice", _fake_save)


def _routed_lines(out: str) -> list[str]:
    return [line for line in out.splitlines() if line.startswith("Routed \u2192")]


class TestPreTurnHook:
    def test_unconfigured_iteration_never_calls_engine(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: None)

        def _boom(**kwargs):
            raise AssertionError("engine must not run unconfigured")

        monkeypatch.setattr(routing_mod, "decide_via_openrouter", _boom)
        agent = SimpleNamespace(messages=[], model="sentinel", _session_manager=None)
        index = SessionIndex(tmp_path / "index")
        calls: list = []
        _drive(monkeypatch, ["hello"], agent, index, NOVA_MICRO, _serving_invoke(calls))
        assert [text for text, _ in calls] == ["hello"]  # turn still served
        out = capsys.readouterr().out
        assert "Routed \u2192" not in out
        assert "Routing held" not in out

    def test_configured_pick_routes_through_apply_into_served_turn(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: _strategy())
        monkeypatch.setattr(
            routing_mod, "decide_via_openrouter", lambda **kw: _pick_result(HAIKU)
        )
        saved: list[str] = []
        _no_persist(monkeypatch, saved)
        agent = SimpleNamespace(messages=[], model="sentinel", _session_manager=None)
        index = SessionIndex(tmp_path / "index")
        calls: list = []
        _drive(
            monkeypatch, ["hello"], agent, index, NOVA_MICRO, _serving_invoke(calls)
        )
        assert saved == [HAIKU]  # routed switch persisted like /model
        assert len(calls) == 1 and calls[0][0] == "hello"
        assert "haiku" in calls[0][1]  # turn served on the picked model
        out = capsys.readouterr().out
        lines = _routed_lines(out)
        assert len(lines) == 1  # exactly one transcript line
        flat = " ".join(out.split())  # console width may wrap the line
        assert HAIKU in flat and "(high)" in flat
        assert "cheap and fast" in flat and "/ask vs" in flat

    def test_same_model_pick_skips_switch_but_prints_line(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: _strategy())
        monkeypatch.setattr(
            routing_mod, "decide_via_openrouter", lambda **kw: _pick_result(NOVA_MICRO, "low")
        )
        saved: list[str] = []
        _no_persist(monkeypatch, saved)
        agent = SimpleNamespace(messages=[], model="sentinel", _session_manager=None)
        index = SessionIndex(tmp_path / "index")
        calls: list = []
        _drive(
            monkeypatch, ["hello"], agent, index, NOVA_MICRO, _serving_invoke(calls)
        )
        assert saved == []  # no-op fast path: no switch, no persistence
        assert agent.model == "sentinel"
        assert len(_routed_lines(capsys.readouterr().out)) == 1

    def test_engine_failure_holds_current_byte_identical(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: _strategy())
        monkeypatch.setattr(
            routing_mod, "decide_via_openrouter", lambda **kw: EngineResult(text=None)
        )
        seed = [
            {"role": "user", "content": [{"text": "earlier"}]},
            {"role": "assistant", "content": [{"text": "answer"}]},
        ]
        agent = SimpleNamespace(
            messages=[dict(m) for m in seed], model="sentinel", _session_manager=None
        )
        index = SessionIndex(tmp_path / "index")
        calls: list = []
        _drive(monkeypatch, ["hello"], agent, index, NOVA_MICRO, _quiet_invoke(calls))
        assert calls  # the turn still runs, on the current model
        assert agent.messages == seed  # hook mutated nothing
        assert agent.model == "sentinel"
        out = capsys.readouterr().out
        flat = " ".join(out.split())  # console width may wrap the note
        assert (
            f"Routing held on {NOVA_MICRO} (openrouter failed; retrying next ask)"
            in flat
        )
        assert "Routed \u2192" not in out

    def test_unresolvable_pick_holds_current_with_history_untouched(
        self, tmp_path, monkeypatch, capsys
    ):
        bad = "frobnicate/xx"
        strategy = _strategy(
            candidates=[RoutingCandidate(id=bad), RoutingCandidate(id=NOVA_MICRO)]
        )
        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: strategy)
        # "off" passes effort validation so the pick reaches the resolve
        # guard, which must still hold with history untouched.
        monkeypatch.setattr(
            routing_mod, "decide_via_openrouter", lambda **kw: _pick_result(bad, "off")
        )
        seed = [{"role": "user", "content": [{"text": "earlier"}]}]
        agent = SimpleNamespace(
            messages=[dict(m) for m in seed], model="sentinel", _session_manager=None
        )
        index = SessionIndex(tmp_path / "index")
        calls: list = []
        _drive(monkeypatch, ["hello"], agent, index, NOVA_MICRO, _quiet_invoke(calls))
        assert agent.messages == seed  # switch-first: resolve raised pre-mutation
        out = capsys.readouterr().out
        flat = " ".join(out.split())  # console width may wrap the note
        assert (
            f"Routing held on {NOVA_MICRO} (resolve failed; retrying next ask)" in flat
        )

    def test_quiet_strategy_suppresses_routed_line(self, tmp_path, monkeypatch, capsys):
        strategy = _strategy()
        strategy.quiet = True
        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: strategy)
        monkeypatch.setattr(
            routing_mod, "decide_via_openrouter", lambda **kw: _pick_result(HAIKU)
        )
        saved: list[str] = []
        _no_persist(monkeypatch, saved)
        agent = SimpleNamespace(messages=[], model="sentinel", _session_manager=None)
        index = SessionIndex(tmp_path / "index")
        calls: list = []
        _drive(
            monkeypatch, ["hello"], agent, index, NOVA_MICRO, _serving_invoke(calls)
        )
        assert saved == [HAIKU]  # switch still applies
        assert "Routed \u2192" not in capsys.readouterr().out

    def test_rejected_effort_holds_current_byte_identical(
        self, tmp_path, monkeypatch, capsys
    ):
        # nova-micro advertises "low" but supports no thinking: the pick
        # parses yet the pre-mutation gate rejects it.
        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: _strategy())
        monkeypatch.setattr(
            routing_mod,
            "decide_via_openrouter",
            lambda **kw: _pick_result(NOVA_MICRO, "low"),
        )
        seed = [{"role": "user", "content": [{"text": "earlier"}]}]
        agent = SimpleNamespace(
            messages=[dict(m) for m in seed], model="sentinel", _session_manager=None
        )
        index = SessionIndex(tmp_path / "index")
        calls: list = []
        _drive(monkeypatch, ["hello"], agent, index, HAIKU, _quiet_invoke(calls))
        assert calls  # the turn still runs, on the current model
        assert agent.messages == seed
        assert agent.model == "sentinel"
        out = capsys.readouterr().out
        flat = " ".join(out.split())  # console width may wrap the note
        assert f"Routing held on {HAIKU} (openrouter failed; retrying next ask)" in flat
        assert "Routed \u2192" not in out

    def test_accepted_effort_reaches_resolved_model(
        self, tmp_path, monkeypatch, capsys
    ):
        import strands_harness.models as harness_models

        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: _strategy())
        monkeypatch.setattr(
            routing_mod, "decide_via_openrouter", lambda **kw: _pick_result(HAIKU)
        )
        real_resolve = harness_models.resolve_model
        efforts: list = []

        def _spy_resolve(*args, **kwargs):
            efforts.append(kwargs.get("effort"))
            return real_resolve(*args, **kwargs)

        monkeypatch.setattr(harness_models, "resolve_model", _spy_resolve)
        saved: list[str] = []
        _no_persist(monkeypatch, saved)
        agent = SimpleNamespace(messages=[], model="sentinel", _session_manager=None)
        index = SessionIndex(tmp_path / "index")
        calls: list = []
        _drive(
            monkeypatch, ["hello"], agent, index, NOVA_MICRO, _serving_invoke(calls)
        )
        assert saved == [HAIKU]
        assert efforts == ["high"]  # routed level reached the resolved model
        assert len(_routed_lines(capsys.readouterr().out)) == 1

    def test_empty_candidates_skip_silently(self, tmp_path, monkeypatch, capsys):
        strategy = _strategy(candidates=[])
        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: strategy)

        def _boom(**kwargs):
            raise AssertionError("no candidates: no decision call")

        monkeypatch.setattr(routing_mod, "decide_via_openrouter", _boom)
        agent = SimpleNamespace(messages=[], model="sentinel", _session_manager=None)
        index = SessionIndex(tmp_path / "index")
        calls: list = []
        _drive(monkeypatch, ["hello"], agent, index, NOVA_MICRO, _serving_invoke(calls))
        assert len(calls) == 1
        out = capsys.readouterr().out
        assert "Routed \u2192" not in out
        assert "Routing held" not in out


def _write_skill(skills_dir, name: str):
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: A route skill.\n---\n# Route\nGo.\n",
        encoding="utf-8",
    )
    return skill_dir


class TestRoutingToggle:
    def test_routing_state_rejects_unknown_values(self):
        with pytest.raises(ValueError, match="on\\|off"):
            RoutingState(initial="bogus")
        holder = RoutingState(initial="on")
        with pytest.raises(ValueError, match="on\\|off"):
            holder.set("bogus")
        assert holder.is_on() is True

    def test_route_off_skips_engine_seam(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: _strategy())

        def _boom(**kwargs):
            raise AssertionError("toggled off: engine must not run")

        monkeypatch.setattr(routing_mod, "decide_via_openrouter", _boom)
        agent = SimpleNamespace(messages=[], model="sentinel", _session_manager=None)
        index = SessionIndex(tmp_path / "index")
        calls: list = []
        _drive(
            monkeypatch,
            ["/route off", "hello"],
            agent,
            index,
            NOVA_MICRO,
            _serving_invoke(calls),
        )
        assert [text for text, _ in calls] == ["hello"]
        out = capsys.readouterr().out
        assert ROUTING_OFF_REPLY in out
        assert "Routed \u2192" not in out
        assert "Routing held" not in out

    def test_route_on_re_enables_hook(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: _strategy())
        monkeypatch.setattr(
            routing_mod, "decide_via_openrouter", lambda **kw: _pick_result(HAIKU)
        )
        saved: list[str] = []
        _no_persist(monkeypatch, saved)
        agent = SimpleNamespace(messages=[], model="sentinel", _session_manager=None)
        index = SessionIndex(tmp_path / "index")
        calls: list = []
        _drive(
            monkeypatch,
            ["/route off", "/route on", "hello"],
            agent,
            index,
            NOVA_MICRO,
            _serving_invoke(calls),
        )
        assert saved == [HAIKU]
        assert len(_routed_lines(capsys.readouterr().out)) == 1

    def test_route_status_names_source_engine_and_count(self, tmp_path, monkeypatch):
        source = tmp_path / "routing.yaml"
        strategy = _strategy()
        strategy.source = source
        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: strategy)
        action, message = dispatch(
            "/route status",
            session_id="s",
            index=SessionIndex(tmp_path / "index"),
            routing=RoutingState(initial="on"),
        )
        assert action == "reply"
        assert message is not None
        assert "Routing: on" in message
        assert str(source) in message
        assert "openrouter" in message and "cheap/decider" in message
        assert "2 candidates" in message

    def test_bare_route_reports_status(self, tmp_path, monkeypatch):
        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: _strategy())
        action, message = dispatch(
            "/route",
            session_id="s",
            index=SessionIndex(tmp_path / "index"),
            routing=RoutingState(initial="off"),
        )
        assert action == "reply"
        assert message is not None and "Routing: off" in message

    def test_route_unknown_subcommand_returns_usage(self, tmp_path):
        action, message = dispatch(
            "/route frobnicate",
            session_id="s",
            index=SessionIndex(tmp_path / "index"),
            routing=RoutingState(initial="on"),
        )
        assert (action, message) == ("reply", ROUTE_USAGE)

    def test_usage_hint_advertises_route(self):
        assert "/route [on|off|status]" in USAGE_HINT

    def _configured(self, monkeypatch):
        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: _strategy())

    def test_model_with_routing_on_radio_cancel_keeps_routing(
        self, tmp_path, monkeypatch
    ):
        import strands_code_cli.choice as choice_mod

        self._configured(monkeypatch)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr(choice_mod, "radio_choice", lambda *a, **k: "cancel")
        holder = RoutingState(initial="on")
        action, message = dispatch(
            f"/model {HAIKU}",
            session_id="s",
            index=SessionIndex(tmp_path / "index"),
            current_model=NOVA_MICRO,
            routing=holder,
        )
        assert (action, message) == ("reply", MODEL_ROUTING_KEEP_REPLY)
        assert holder.is_on() is True

    def test_model_with_routing_on_radio_proceed_disables_after_apply(
        self, tmp_path, monkeypatch, capsys
    ):
        import strands_code_cli.choice as choice_mod

        self._configured(monkeypatch)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr(choice_mod, "radio_choice", lambda *a, **k: "proceed")

        def _boom(**kwargs):
            raise AssertionError("routing off after apply: engine must not run")

        monkeypatch.setattr(routing_mod, "decide_via_openrouter", _boom)
        saved: list[str] = []
        _no_persist(monkeypatch, saved)
        agent = SimpleNamespace(messages=[], model="sentinel", _session_manager=None)
        index = SessionIndex(tmp_path / "index")
        calls: list = []
        _drive(
            monkeypatch,
            [f"/model {HAIKU}", "hello"],
            agent,
            index,
            NOVA_MICRO,
            _serving_invoke(calls),
        )
        assert saved == [HAIKU]  # manual switch applied
        assert [text for text, _ in calls] == ["hello"]  # served, unrouted
        out = capsys.readouterr().out
        assert ROUTING_MANUAL_OFF_NOTE in " ".join(out.split())
        assert "Routed \u2192" not in out

    def test_model_off_tty_empty_input_keeps_routing(self, tmp_path, monkeypatch):
        self._configured(monkeypatch)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        monkeypatch.setattr("builtins.input", lambda *a: "")
        holder = RoutingState(initial="on")
        action, message = dispatch(
            f"/model {HAIKU}",
            session_id="s",
            index=SessionIndex(tmp_path / "index"),
            current_model=NOVA_MICRO,
            routing=holder,
        )
        assert (action, message) == ("reply", MODEL_ROUTING_KEEP_REPLY)
        assert holder.is_on() is True

    def test_model_off_tty_typed_confirm_disables_after_apply(
        self, tmp_path, monkeypatch, capsys
    ):
        self._configured(monkeypatch)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        monkeypatch.setattr("builtins.input", lambda *a: "yes")

        def _boom(**kwargs):
            raise AssertionError("routing off after apply: engine must not run")

        monkeypatch.setattr(routing_mod, "decide_via_openrouter", _boom)
        saved: list[str] = []
        _no_persist(monkeypatch, saved)
        agent = SimpleNamespace(messages=[], model="sentinel", _session_manager=None)
        index = SessionIndex(tmp_path / "index")
        calls: list = []
        _drive(
            monkeypatch,
            [f"/model {HAIKU}", "hello"],
            agent,
            index,
            NOVA_MICRO,
            _serving_invoke(calls),
        )
        assert saved == [HAIKU]
        assert [text for text, _ in calls] == ["hello"]
        assert ROUTING_MANUAL_OFF_NOTE in " ".join(capsys.readouterr().out.split())

    def test_model_with_routing_off_skips_warn_entirely(self, tmp_path, monkeypatch):
        import strands_code_cli.choice as choice_mod

        monkeypatch.setattr(
            choice_mod,
            "radio_choice",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("no radio")),
        )
        monkeypatch.setattr(
            "builtins.input", lambda *a: (_ for _ in ()).throw(AssertionError("no input"))
        )
        holder = RoutingState(initial="off")
        action, message = dispatch(
            f"/model {HAIKU}",
            session_id="s",
            index=SessionIndex(tmp_path / "index"),
            current_model=NOVA_MICRO,
            routing=holder,
        )
        assert (action, message) == ("model", HAIKU)

    def test_model_unconfigured_skips_warn_entirely(self, tmp_path, monkeypatch):
        import strands_code_cli.choice as choice_mod

        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: None)
        monkeypatch.setattr(
            choice_mod,
            "radio_choice",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("no radio")),
        )
        monkeypatch.setattr(
            "builtins.input", lambda *a: (_ for _ in ()).throw(AssertionError("no input"))
        )
        holder = RoutingState(initial="on")
        action, message = dispatch(
            f"/model {HAIKU}",
            session_id="s",
            index=SessionIndex(tmp_path / "index"),
            current_model=NOVA_MICRO,
            routing=holder,
        )
        assert (action, message) == ("model", HAIKU)

    def test_route_skill_shadowed_while_builtin_wins(self, tmp_path, monkeypatch):
        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: _strategy())
        skills_dir = tmp_path / ".agent" / "skills"
        _write_skill(skills_dir, "route")
        skills = SkillIndex(skills_dir=skills_dir)
        action, message = dispatch(
            "/route status",
            session_id="s",
            index=SessionIndex(tmp_path / "index"),
            routing=RoutingState(initial="on"),
            skills=skills,
        )
        assert action == "reply"
        assert message is not None and "Routing: on" in message
        assert any(
            "shadowed by builtin '/route'" in warning for warning in skills.warnings
        )


DECIDER = "decider-claude-3-haiku"
"""Decision model id hitting the static price table (0.25/1.25 per 1M)."""


def _event(**overrides):
    base = {
        "ask": 1,
        "side": False,
        "model": HAIKU,
        "effort": "high",
        "why": "cheap and fast",
        "engine": "openrouter",
        "input_tokens": 2000,
        "output_tokens": 100,
        "held": False,
        "decision_model": DECIDER,
    }
    base.update(overrides)
    return base


def _hook(tmp_path, monkeypatch, strategy, engine_result, events):
    """Drive the pre-turn hook directly with a canned engine result."""
    from strands_code_cli.loop import _route_pre_turn

    monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: strategy)
    monkeypatch.setattr(
        routing_mod, "decide_via_openrouter", lambda **kw: engine_result
    )
    saved: list[str] = []
    _no_persist(monkeypatch, saved)
    agent = SimpleNamespace(messages=[], model="sentinel", _session_manager=None)
    served = _route_pre_turn(
        agent,
        current_model=NOVA_MICRO,
        ask_text="hello",
        rich=None,
        index=SessionIndex(tmp_path / "index"),
        session_id="s",
        stash_path=None,
        routing=RoutingState(initial="on"),
        routing_events=events,
    )
    return served, saved


class TestCostRouting:
    def test_hook_appends_routing_event_with_usage(self, tmp_path, monkeypatch):
        events: list = []
        served, saved = _hook(
            tmp_path,
            monkeypatch,
            _strategy(),
            _pick_result(HAIKU, usage=(120, 25)),
            events,
        )
        assert served == HAIKU
        assert saved == [HAIKU]
        assert events == [
            {
                "ask": 1,
                "side": False,
                "model": HAIKU,
                "effort": "high",
                "why": "cheap and fast",
                "engine": "openrouter",
                "input_tokens": 120,
                "output_tokens": 25,
                "held": False,
                "decision_model": "cheap/decider",
            }
        ]

    def test_cost_report_renders_routing_and_folds_spend(self):
        from strands_code_cli.cost_context import cost_for, cost_report

        turns = [
            {
                "turn": 1,
                "input_tokens": 1000,
                "output_tokens": 500,
                "model": NOVA_MICRO,
            }
        ]
        report = cost_report(turns, NOVA_MICRO, routing=[_event()])
        assert "Routing:" in report
        assert HAIKU in report and "cheap and fast" in report
        assert "openrouter" in report
        expected = cost_for(1000, 500, NOVA_MICRO) + cost_for(2000, 100, DECIDER)
        assert expected is not None
        total = next(line for line in report.splitlines() if line.startswith("Total:"))
        assert total == (
            f"Total: in 3.00K, out 600, ${expected:.4f}"
        )
        assert "Prices: static table." in report

    def test_dispatch_cost_forwards_routing_events(self, tmp_path):
        turns = [
            {
                "turn": 1,
                "input_tokens": 1000,
                "output_tokens": 500,
                "model": NOVA_MICRO,
            }
        ]
        action, message = dispatch(
            "/cost",
            session_id="s",
            index=SessionIndex(tmp_path / "index"),
            current_model=NOVA_MICRO,
            session_turns=turns,
            routing_events=[_event()],
        )
        assert action == "reply"
        assert message is not None
        assert "Routing:" in message
        assert HAIKU in message and "cheap and fast" in message

    def test_cost_report_without_routing_is_byte_identical(self):
        from strands_code_cli.cost_context import cost_report

        turns = [
            {
                "turn": 1,
                "input_tokens": 1000,
                "output_tokens": 500,
                "model": NOVA_MICRO,
            }
        ]
        golden = (
            "Cost — bedrock/amazon.nova-micro-v1:0\n"
            "  turn 1: in 1.00K, out 500, $0.0001\n"
            "Total: in 1.00K, out 500, $0.0001\n"
            "Prices: static table.\n"
            "Display only — no budgets or enforcement."
        )
        assert cost_report(turns, NOVA_MICRO) == golden
        assert cost_report(turns, NOVA_MICRO, routing=None) == golden
        assert cost_report(turns, NOVA_MICRO, routing=[]) == golden
        assert (
            cost_report([], "mystery/model-x")
            == "Cost — mystery/model-x\n"
            "Total: in 0, out 0\n"
            "Prices: unknown.\n"
            "Display only — no budgets or enforcement."
        )

    def test_quiet_strategy_prints_hold_note_on_failure(
        self, tmp_path, monkeypatch, capsys
    ):
        strategy = _strategy()
        strategy.quiet = True
        events: list = []
        served, _ = _hook(
            tmp_path, monkeypatch, strategy, EngineResult(text=None), events
        )
        assert served == NOVA_MICRO  # held current
        out = capsys.readouterr().out
        assert "Routed →" not in out
        flat = " ".join(out.split())  # console width may wrap the note
        assert (
            f"Routing held on {NOVA_MICRO} (openrouter failed; retrying next ask)"
            in flat
        )

    def test_held_ask_appends_held_event(self, tmp_path, monkeypatch):
        events: list = []
        served, _ = _hook(
            tmp_path, monkeypatch, _strategy(), EngineResult(text=None), events
        )
        assert served == NOVA_MICRO
        assert events == [
            {
                "ask": 1,
                "side": False,
                "model": NOVA_MICRO,
                "effort": "",
                "why": "",
                "engine": "openrouter",
                "input_tokens": 0,
                "output_tokens": 0,
                "held": True,
                "decision_model": "cheap/decider",
            }
        ]

    def test_skipped_ask_appends_no_event(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: None)
        events: list = []
        agent = SimpleNamespace(messages=[], model="sentinel", _session_manager=None)
        from strands_code_cli.loop import _route_pre_turn

        served = _route_pre_turn(
            agent,
            current_model=NOVA_MICRO,
            ask_text="hello",
            rich=None,
            index=SessionIndex(tmp_path / "index"),
            session_id="s",
            stash_path=None,
            routing=RoutingState(initial="on"),
            routing_events=events,
        )
        assert served == NOVA_MICRO
        assert events == []
        assert capsys.readouterr().out == ""
