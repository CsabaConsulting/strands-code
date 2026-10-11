"""Pre-turn routing hook tests (MODEL-03 tracer).

Drives run_loop end to end with a mocked OpenRouter decision: the
urllib-adjacent seam patched is decide_via_openrouter (canned JSON),
while decide/parse/prompt and apply_model_action run for real.
"""

from __future__ import annotations

import json
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

import strands_code_cli.loop as loop_mod
import strands_code_cli.routing as routing_mod
from strands_code_cli.provider_config import ProviderConfig
from strands_code_cli.routing import (
    RoutingCandidate,
    RoutingEngine,
    RoutingStrategy,
)
from strands_code_cli.session_index import SessionIndex

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


def _pick_json(model: str, effort: str = "high") -> str:
    return json.dumps({"model": model, "effort": effort, "why": "cheap and fast"})


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
            routing_mod, "decide_via_openrouter", lambda **kw: _pick_json(HAIKU)
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
            routing_mod, "decide_via_openrouter", lambda **kw: _pick_json(NOVA_MICRO, "low")
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
        monkeypatch.setattr(routing_mod, "decide_via_openrouter", lambda **kw: None)
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
        monkeypatch.setattr(
            routing_mod, "decide_via_openrouter", lambda **kw: _pick_json(bad)
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
            routing_mod, "decide_via_openrouter", lambda **kw: _pick_json(HAIKU)
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
