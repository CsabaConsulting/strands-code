"""Pre-turn routing hook tests (MODEL-03 tracer).

Drives run_loop end to end with a mocked OpenRouter decision: the
urllib-adjacent seam patched is decide_via_openrouter (canned
EngineResult), while decide/validate/gate and apply_model_action run
for real.
"""

from __future__ import annotations

import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

import strands_code_cli.loop.core as loop_mod
import strands_code_cli.routing.core as routing_mod
from strands_code_cli.dispatch.core import USAGE_HINT, dispatch
from strands_code_cli.entry.provider_config import ProviderConfig
from strands_code_cli.memory.skills import SkillIndex
from strands_code_cli.routing.core import (
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
from strands_code_cli.session.session_index import SessionIndex

HAIKU = "bedrock/anthropic.claude-haiku-4-5-20251001-v1:0"
NOVA_MICRO = "bedrock/amazon.nova-micro-v1:0"
SONNET = "bedrock/anthropic.claude-sonnet-4-6"


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


def _table_result(
    choice: str = HAIKU,
    probs: dict | None = None,
    usage: tuple = (0, 0, None),
    confidence: float = 0.85,
    effort: str = "low",
    effort_probs: dict | None = None,
    effort_confidence: float = 0.7,
) -> EngineResult:
    table = probs if probs is not None else {HAIKU: 0.85, NOVA_MICRO: 0.15}
    effort_table = (
        effort_probs if effort_probs is not None else {"low": 0.7, "high": 0.3}
    )
    return EngineResult(
        answers={
            "pick_model": {
                "type": "choice",
                "choice": choice,
                "probabilities": dict(table),
                "confidence": confidence,
            },
            "pick_effort": {
                "type": "choice",
                "choice": effort,
                "probabilities": dict(effort_table),
                "confidence": effort_confidence,
            },
        },
        input_tokens=usage[0],
        output_tokens=usage[1],
        cost=usage[2],
        model="typesafe/jev-1.13-20260917",
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
    loop_mod.run_loop(agent, session_id=index.mint(), index=index, model_id=model_id)


def _serving_invoke(calls):
    """Fake turn: record (text, serving model id), append a Q/A pair."""

    def _invoke(agent, text, event, **kwargs):
        from strands_code_cli.model.model_switch import model_id_of

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
            routing_mod, "decide_via_openrouter", lambda **kw: _table_result(HAIKU)
        )
        saved: list[str] = []
        _no_persist(monkeypatch, saved)
        agent = SimpleNamespace(messages=[], model="sentinel", _session_manager=None)
        index = SessionIndex(tmp_path / "index")
        calls: list = []
        _drive(monkeypatch, ["hello"], agent, index, NOVA_MICRO, _serving_invoke(calls))
        assert saved == []  # FENCE: routed switch applies in memory only
        assert len(calls) == 1 and calls[0][0] == "hello"
        assert "haiku" in calls[0][1]  # turn served on the picked model
        out = capsys.readouterr().out
        lines = _routed_lines(out)
        assert len(lines) == 1  # exactly one transcript line
        flat = " ".join(out.split())  # console width may wrap the line
        assert HAIKU in flat and "(low)" in flat  # first advertised level
        assert "85%" in flat and "~$" in flat and "/ask vs" in flat

    def test_same_model_pick_skips_switch_but_prints_line(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: _strategy())
        monkeypatch.setattr(
            routing_mod,
            "decide_via_openrouter",
            lambda **kw: _table_result(
                NOVA_MICRO, probs={HAIKU: 0.15, NOVA_MICRO: 0.85}
            ),
        )
        saved: list[str] = []
        _no_persist(monkeypatch, saved)
        agent = SimpleNamespace(messages=[], model="sentinel", _session_manager=None)
        index = SessionIndex(tmp_path / "index")
        calls: list = []
        _drive(monkeypatch, ["hello"], agent, index, NOVA_MICRO, _serving_invoke(calls))
        assert saved == []  # no-op fast path: no switch, no persistence
        assert agent.model == "sentinel"
        assert len(_routed_lines(capsys.readouterr().out)) == 1

    def test_engine_failure_holds_current_byte_identical(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: _strategy())
        monkeypatch.setattr(
            routing_mod,
            "decide_via_openrouter",
            lambda **kw: EngineResult(answers=None),
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
            candidates=[
                RoutingCandidate(id=bad, levels=["off"]),
                RoutingCandidate(id=NOVA_MICRO, levels=["low"]),
            ]
        )
        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: strategy)
        # "off" passes effort validation so the pick reaches the resolve
        # guard, which must still hold with history untouched.
        monkeypatch.setattr(
            routing_mod,
            "decide_via_openrouter",
            lambda **kw: _table_result(bad, probs={bad: 0.9, NOVA_MICRO: 0.1}),
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
            routing_mod, "decide_via_openrouter", lambda **kw: _table_result(HAIKU)
        )
        saved: list[str] = []
        _no_persist(monkeypatch, saved)
        agent = SimpleNamespace(messages=[], model="sentinel", _session_manager=None)
        index = SessionIndex(tmp_path / "index")
        calls: list = []
        _drive(monkeypatch, ["hello"], agent, index, NOVA_MICRO, _serving_invoke(calls))
        assert saved == []  # FENCE: switch applies in memory, never persists
        assert "Routed \u2192" not in capsys.readouterr().out

    def test_all_refused_ask_pauses_and_serves_current(
        self, tmp_path, monkeypatch, capsys
    ):
        events: list = []
        routing = RoutingState(initial="on")
        served, _ = _hook_with_routing(
            tmp_path,
            monkeypatch,
            _strategy(),
            EngineResult(answers=None, error="refused"),
            events,
            routing,
        )
        assert served == NOVA_MICRO  # the current model serves the ask
        assert routing.is_paused() is True  # same-turn decisions skip
        out = capsys.readouterr().out
        flat = " ".join(out.split())  # console width may wrap the note
        assert (
            f"Routing held on {NOVA_MICRO} "
            "(paused: all engines unreachable (openrouter); retrying next ask)" in flat
        )
        assert "Routed \u2192" not in out
        assert events[0]["held"] is True
        assert events[0]["engine"] == "openrouter"

    def test_transport_hold_prints_engine_and_code_note(
        self, tmp_path, monkeypatch, capsys
    ):
        events: list = []
        served, _ = _hook(
            tmp_path,
            monkeypatch,
            _strategy(),
            EngineResult(answers=None, error="HTTP 503"),
            events,
        )
        assert served == NOVA_MICRO
        out = capsys.readouterr().out
        flat = " ".join(out.split())  # console width may wrap the note
        assert (
            f"Routing held on {NOVA_MICRO} (openrouter 503; retrying next ask)" in flat
        )

    def test_quiet_keeps_pause_note(self, tmp_path, monkeypatch, capsys):
        strategy = _strategy()
        strategy.quiet = True
        events: list = []
        served, _ = _hook(
            tmp_path,
            monkeypatch,
            strategy,
            EngineResult(answers=None, error="refused"),
            events,
        )
        assert served == NOVA_MICRO
        out = capsys.readouterr().out
        assert "Routed \u2192" not in out
        flat = " ".join(out.split())  # console width may wrap the note
        assert "paused: all engines unreachable (openrouter)" in flat

    def test_quiet_keeps_failure_note_on_decide_error(
        self, tmp_path, monkeypatch, capsys
    ):
        from strands_code_cli.loop.core import _route_pre_turn

        strategy = _strategy()
        strategy.quiet = True
        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: strategy)

        def _boom(*args, **kwargs):
            raise RuntimeError("almanac down")

        monkeypatch.setattr(routing_mod, "decide", _boom)
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
            routing_events=[],
        )
        assert served == NOVA_MICRO
        out = capsys.readouterr().out
        flat = " ".join(out.split())  # console width may wrap the note
        assert (
            f"Routing held on {NOVA_MICRO} (decide failed; retrying next ask)" in flat
        )

    def test_pause_resumes_on_next_ask(self, tmp_path, monkeypatch, capsys):
        events: list = []
        routing = RoutingState(initial="on")
        routing.pause()
        served, saved = _hook_with_routing(
            tmp_path,
            monkeypatch,
            _strategy(),
            _table_result(HAIKU),
            events,
            routing,
        )
        assert served == HAIKU  # the new ask attempts fresh and routes
        assert saved == []  # FENCE: routed resume never persists
        assert routing.is_paused() is False
        assert len(_routed_lines(capsys.readouterr().out)) == 1

    def test_routed_line_carries_truncation_marker(self, tmp_path, monkeypatch, capsys):
        import dataclasses

        events: list = []
        shrunk = dataclasses.replace(_table_result(HAIKU), truncated=True)
        served, _ = _hook(tmp_path, monkeypatch, _strategy(), shrunk, events)
        assert served == HAIKU
        out = capsys.readouterr().out
        flat = " ".join(out.split())  # console width may wrap the line
        assert len(_routed_lines(out)) == 1
        assert routing_mod.TRUNCATION_MARKER in flat

    def test_hold_line_carries_truncation_marker(self, tmp_path, monkeypatch, capsys):
        events: list = []
        served, _ = _hook(
            tmp_path,
            monkeypatch,
            _strategy(),
            EngineResult(answers=None, error="HTTP 400", truncated=True),
            events,
        )
        assert served == NOVA_MICRO
        out = capsys.readouterr().out
        flat = " ".join(out.split())  # console width may wrap the note
        assert "openrouter 400" in flat
        assert routing_mod.TRUNCATION_MARKER in flat

    def test_normal_routed_line_has_no_marker(self, tmp_path, monkeypatch, capsys):
        events: list = []
        served, _ = _hook(
            tmp_path, monkeypatch, _strategy(), _table_result(HAIKU), events
        )
        assert served == HAIKU
        out = capsys.readouterr().out
        assert len(_routed_lines(out)) == 1
        assert "truncated" not in out

    def test_rejected_effort_holds_current_byte_identical(
        self, tmp_path, monkeypatch, capsys
    ):
        # nova-micro advertises "low" but supports no thinking: the pick
        # gates yet the passthrough effort fails validation.
        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: _strategy())
        monkeypatch.setattr(
            routing_mod,
            "decide_via_openrouter",
            lambda **kw: _table_result(NOVA_MICRO, probs={HAIKU: 0.1, NOVA_MICRO: 0.9}),
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
        assert (
            f"Routing held on {HAIKU} "
            f"(effort 'low' unsupported by {NOVA_MICRO}; retrying next ask)"
        ) in flat
        assert "Routed \u2192" not in out

    def test_accepted_effort_reaches_resolved_model(
        self, tmp_path, monkeypatch, capsys
    ):
        import strands_harness.models as harness_models

        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: _strategy())
        monkeypatch.setattr(
            routing_mod, "decide_via_openrouter", lambda **kw: _table_result(HAIKU)
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
        _drive(monkeypatch, ["hello"], agent, index, NOVA_MICRO, _serving_invoke(calls))
        assert saved == []  # FENCE: routed switch never persists
        assert efforts == ["low"]  # first advertised level reached the model
        assert len(_routed_lines(capsys.readouterr().out)) == 1

    def test_threshold_hold_prints_confidence_note(self, tmp_path, monkeypatch, capsys):
        strategy = _strategy(
            candidates=[
                RoutingCandidate(id=HAIKU, levels=["low", "high"]),
                RoutingCandidate(id=NOVA_MICRO, levels=["low"]),
                RoutingCandidate(id=SONNET, levels=["low", "high"]),
            ]
        )
        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: strategy)
        monkeypatch.setattr(
            routing_mod,
            "decide_via_openrouter",
            lambda **kw: _table_result(
                HAIKU, probs={HAIKU: 0.41, NOVA_MICRO: 0.30, SONNET: 0.29}
            ),
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
        out = capsys.readouterr().out
        flat = " ".join(out.split())  # console width may wrap the note
        assert (
            f"Routing held on {HAIKU} (confidence 41% < 62%; retrying next ask)" in flat
        )
        assert "Routed \u2192" not in out

    def test_near_tie_routes_cheaper_with_marker(self, tmp_path, monkeypatch, capsys):
        strategy = _strategy(
            candidates=[
                RoutingCandidate(id=HAIKU, levels=["low", "high"]),
                RoutingCandidate(id=SONNET, levels=["low", "high"]),
            ]
        )
        strategy.confidence_threshold = 0.4
        strategy.tie_margin = 0.05
        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: strategy)
        prices = {HAIKU: (3.0, 15.0), SONNET: (0.5, 2.0)}
        monkeypatch.setattr(routing_mod, "price_for", lambda mid: prices.get(mid))
        monkeypatch.setattr(
            routing_mod,
            "decide_via_openrouter",
            lambda **kw: _table_result(HAIKU, probs={HAIKU: 0.52, SONNET: 0.48}),
        )
        saved: list[str] = []
        _no_persist(monkeypatch, saved)
        agent = SimpleNamespace(messages=[], model="sentinel", _session_manager=None)
        index = SessionIndex(tmp_path / "index")
        calls: list = []
        _drive(monkeypatch, ["hello"], agent, index, NOVA_MICRO, _serving_invoke(calls))
        assert saved == []  # FENCE: tie-break switch never persists
        out = capsys.readouterr().out
        flat = " ".join(out.split())  # console width may wrap the line
        assert SONNET in flat and "tie-break" in flat

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


def _keyless_native_strategy(**overrides) -> RoutingStrategy:
    """Two-candidate strategy with a keyless native link first (D-03)."""
    strategy = RoutingStrategy(
        candidates=[
            RoutingCandidate(id=HAIKU, tier="small", levels=["low", "high"]),
            RoutingCandidate(id=NOVA_MICRO, tier="tiny", levels=["low"]),
        ],
        directives="trivial asks go cheap",
        engine=RoutingEngine(
            order=["native", "openrouter"],
            decision_model="cheap/decider",
            native_model="jev-1.13.0",
        ),
    )
    for key, value in overrides.items():
        if key in ("skip_notes",):
            setattr(strategy.engine, key, value)
        else:
            setattr(strategy, key, value)
    return strategy


class TestChainSkipNotes:
    @pytest.fixture(autouse=True)
    def _fresh_notes(self, monkeypatch):
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        loop_mod._emitted_chain_skip_notes.clear()
        yield
        loop_mod._emitted_chain_skip_notes.clear()

    def _drive_two_asks(self, tmp_path, monkeypatch, strategy):
        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: strategy)
        monkeypatch.setattr(
            routing_mod, "decide_via_openrouter", lambda **kw: _table_result(HAIKU)
        )
        saved: list[str] = []
        _no_persist(monkeypatch, saved)
        agent = SimpleNamespace(messages=[], model="sentinel", _session_manager=None)
        index = SessionIndex(tmp_path / "index")
        calls: list = []
        _drive(
            monkeypatch,
            ["hello", "again"],
            agent,
            index,
            NOVA_MICRO,
            _serving_invoke(calls),
        )
        assert len(calls) == 2  # both asks served through the hook
        return saved

    def test_two_routed_asks_emit_one_skip_line(self, tmp_path, monkeypatch, capsys):
        self._drive_two_asks(tmp_path, monkeypatch, _keyless_native_strategy())
        out = capsys.readouterr().out
        assert len(_routed_lines(out)) == 2  # the hook ran for both asks
        assert out.count("native engine skipped: TYPESAFE_API_KEY not set") == 1

    def test_skip_notes_false_emits_zero(self, tmp_path, monkeypatch, capsys):
        self._drive_two_asks(
            tmp_path, monkeypatch, _keyless_native_strategy(skip_notes=False)
        )
        out = capsys.readouterr().out
        assert len(_routed_lines(out)) == 2
        assert "native engine skipped" not in out

    def test_quiet_true_still_emits_note(self, tmp_path, monkeypatch, capsys):
        self._drive_two_asks(
            tmp_path, monkeypatch, _keyless_native_strategy(quiet=True)
        )
        out = capsys.readouterr().out
        assert _routed_lines(out) == []  # quiet suppresses the routine line
        assert out.count("native engine skipped: TYPESAFE_API_KEY not set") == 1


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

    def test_pause_resume_round_trip(self):
        routing = RoutingState(initial="on")
        assert routing.is_paused() is False
        routing.pause()
        assert routing.is_paused() is True
        assert routing.is_on() is True  # pause never flips the toggle
        routing.resume()
        assert routing.is_paused() is False

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
            routing_mod, "decide_via_openrouter", lambda **kw: _table_result(HAIKU)
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
        assert saved == []  # FENCE: re-enabled hook never persists
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
        assert "/route [on|off|status|setup" in USAGE_HINT

    def _configured(self, monkeypatch):
        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: _strategy())

    def test_model_with_routing_on_radio_cancel_keeps_routing(
        self, tmp_path, monkeypatch
    ):
        import strands_code_cli.ui.choice as choice_mod

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
        import strands_code_cli.ui.choice as choice_mod

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
        import strands_code_cli.ui.choice as choice_mod

        monkeypatch.setattr(
            choice_mod,
            "radio_choice",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("no radio")),
        )
        monkeypatch.setattr(
            "builtins.input",
            lambda *a: (_ for _ in ()).throw(AssertionError("no input")),
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
        import strands_code_cli.ui.choice as choice_mod

        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: None)
        monkeypatch.setattr(
            choice_mod,
            "radio_choice",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("no radio")),
        )
        monkeypatch.setattr(
            "builtins.input",
            lambda *a: (_ for _ in ()).throw(AssertionError("no input")),
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
        "model_confidence": 0.85,
        "effort_confidence": None,
        "tie_break": False,
        "engine": "openrouter",
        "input_tokens": 2000,
        "output_tokens": 100,
        "decision_cost": 0.000625,  # == cost_for(2000, 100, DECIDER)
        "held": False,
        "decision_model": DECIDER,
    }
    base.update(overrides)
    return base


def _hook(tmp_path, monkeypatch, strategy, engine_result, events):
    """Drive the pre-turn hook directly with a canned engine result."""
    from strands_code_cli.loop.core import _route_pre_turn

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


def _hook_with_routing(tmp_path, monkeypatch, strategy, engine_result, events, routing):
    """Drive the pre-turn hook directly with a caller-owned toggle."""
    from strands_code_cli.loop.core import _route_pre_turn

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
        routing=routing,
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
            _table_result(HAIKU, usage=(120, 25, 0.0002)),
            events,
        )
        assert served == HAIKU
        assert saved == []  # FENCE: routed pick never persists
        assert events == [
            {
                "ask": 1,
                "side": False,
                "model": HAIKU,
                "effort": "low",
                "model_confidence": 0.85,
                "effort_confidence": 0.7,
                "tie_break": False,
                "engine": "openrouter",
                "input_tokens": 240,  # both decision calls merged
                "output_tokens": 50,
                "decision_cost": 0.0002 + 0.0002,
                "held": False,
                "decision_model": "cheap/decider",
            }
        ]

    def test_cost_report_renders_routing_and_folds_spend(self):
        from strands_code_cli.cost.cost_context import cost_for, cost_report

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
        assert HAIKU in report and "85%" in report
        assert "openrouter" in report
        expected = cost_for(1000, 500, NOVA_MICRO) + 0.000625  # reported spend
        assert expected is not None
        total = next(line for line in report.splitlines() if line.startswith("Total:"))
        assert total == (f"Total: in 3.00K, out 600, ${expected:.4f}")
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
        assert HAIKU in message and "85%" in message

    def test_cost_report_without_routing_is_byte_identical(self):
        from strands_code_cli.cost.cost_context import cost_report

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
            cost_report([], "mystery/model-x") == "Cost — mystery/model-x\n"
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
            tmp_path, monkeypatch, strategy, EngineResult(answers=None), events
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
            tmp_path, monkeypatch, _strategy(), EngineResult(answers=None), events
        )
        assert served == NOVA_MICRO
        assert events == [
            {
                "ask": 1,
                "side": False,
                "model": NOVA_MICRO,
                "effort": "",
                "model_confidence": None,
                "effort_confidence": None,
                "tie_break": False,
                "engine": "openrouter",
                "input_tokens": 0,
                "output_tokens": 0,
                "decision_cost": None,
                "held": True,
                "decision_model": "cheap/decider",
            }
        ]

    def test_skipped_ask_appends_no_event(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: None)
        events: list = []
        agent = SimpleNamespace(messages=[], model="sentinel", _session_manager=None)
        from strands_code_cli.loop.core import _route_pre_turn

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


def _side_agent():
    """Parent double with a live model object resolving to NOVA_MICRO."""
    live = SimpleNamespace(config=SimpleNamespace(model_id=NOVA_MICRO))
    return SimpleNamespace(
        messages=[],
        model=live,
        _harness_kwargs={"model": live, "session": True},
        _session_manager=None,
    )


def _capture_build(calls):
    def _fake(parent_kwargs, history, question):
        calls.append((dict(parent_kwargs), list(history), question))
        return (SimpleNamespace(), [])

    return _fake


def _side_ctx(monkeypatch, agent, engine, events, strategy=None):
    monkeypatch.setattr(
        routing_mod,
        "load_strategy",
        lambda **kw: _strategy() if strategy is None else strategy,
    )
    monkeypatch.setattr(routing_mod, "decide_via_openrouter", engine)
    builds: list = []
    monkeypatch.setattr(loop_mod, "build_btw_agent", _capture_build(builds))
    ctx = loop_mod._btw_context_for(
        agent, routing=RoutingState(initial="on"), routing_events=events
    )
    return ctx, builds


class TestSideRouting:
    def test_spawn_runs_two_calls_both_side_flagged(self, monkeypatch):
        seen: list = []

        def _engine(**kwargs):
            seen.append(kwargs)
            return _table_result(HAIKU, usage=(40, 8, 0.0001))

        events: list = []
        ctx, builds = _side_ctx(monkeypatch, _side_agent(), _engine, events)
        ctx.build("why is the sky blue?")
        assert len(seen) == 2  # model call plus effort call per spawn
        assert [set(call["questions"]) for call in seen] == [
            {"pick_model"},
            {"pick_effort"},
        ]
        assert seen[1]["state"] == seen[0]["state"]  # same state reused
        assert all(call["state"]["side"] is True for call in seen)
        assert seen[0]["state"]["ask"] == "why is the sky blue?"
        assert set(seen[1]["questions"]["pick_effort"]["criteria"]) == {
            "low",
            "high",
        }
        assert len(builds) == 1
        assert events[0]["side"] is True
        assert events[0]["held"] is False
        assert events[0]["model_confidence"] == 0.85
        assert events[0]["effort_confidence"] == 0.7
        assert (events[0]["input_tokens"], events[0]["output_tokens"]) == (80, 16)
        assert events[0]["decision_cost"] == 0.0001 + 0.0001

    def test_pick_reaches_build_with_resolved_model_and_effort(
        self, monkeypatch, capsys
    ):
        import strands_harness.models as harness_models

        from strands_code_cli.model.model_switch import model_id_of

        real_resolve = harness_models.resolve_model
        seen: list = []

        def _spy_resolve(*args, **kwargs):
            seen.append((args, kwargs))
            return real_resolve(*args, **kwargs)

        monkeypatch.setattr(harness_models, "resolve_model", _spy_resolve)
        events: list = []
        agent = _side_agent()
        ctx, builds = _side_ctx(
            monkeypatch, agent, lambda **kw: _table_result(HAIKU), events
        )
        ctx.build("deep refactor?")
        assert len(builds) == 1
        kwargs, _, question = builds[0]
        assert question == "deep refactor?"
        assert kwargs["model"] is not agent.model
        assert model_id_of(kwargs["model"], "?").endswith(
            "anthropic.claude-haiku-4-5-20251001-v1:0"
        )
        assert kwargs["effort"] == "low"  # decided level
        assert seen == [((HAIKU, HAIKU), {"effort": "low"})]
        out = capsys.readouterr().out
        flat = " ".join(out.split())  # console width may wrap the line
        assert "Routed (btw)" in out  # side head, never the main head
        assert HAIKU in flat  # picked model named
        assert "85%" in flat and "70%" in flat  # both confidences inline
        assert "~$" in flat and "/ask vs" in flat

    def test_engine_failure_spawns_on_parent_model_silently(self, monkeypatch, capsys):
        events: list = []
        agent = _side_agent()
        ctx, builds = _side_ctx(
            monkeypatch, agent, lambda **kw: EngineResult(answers=None), events
        )
        ctx.build("quick question")
        assert len(builds) == 1
        assert builds[0][0]["model"] is agent.model
        assert "effort" not in builds[0][0]  # replay untouched
        out = capsys.readouterr().out
        assert "Routed" not in out
        assert "Routing held" not in out
        assert "Routing disabled" not in out
        assert events[0]["held"] is True
        assert events[0]["side"] is True

    def test_routing_off_spawns_with_zero_decisions(self, monkeypatch):
        def _boom(**kwargs):
            raise AssertionError("routing off: no decision call")

        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: _strategy())
        monkeypatch.setattr(routing_mod, "decide_via_openrouter", _boom)
        builds: list = []
        monkeypatch.setattr(loop_mod, "build_btw_agent", _capture_build(builds))
        events: list = []
        agent = _side_agent()
        ctx = loop_mod._btw_context_for(
            agent, routing=RoutingState(initial="off"), routing_events=events
        )
        ctx.build("quick question")
        assert len(builds) == 1
        assert builds[0][0]["model"] is agent.model
        assert events == []

    def test_unconfigured_spawns_with_zero_decisions(self, monkeypatch):
        def _boom(**kwargs):
            raise AssertionError("unconfigured: no decision call")

        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: None)
        monkeypatch.setattr(routing_mod, "decide_via_openrouter", _boom)
        builds: list = []
        monkeypatch.setattr(loop_mod, "build_btw_agent", _capture_build(builds))
        events: list = []
        ctx = loop_mod._btw_context_for(
            _side_agent(), routing=RoutingState(initial="on"), routing_events=events
        )
        ctx.build("quick question")
        assert len(builds) == 1
        assert events == []

    def test_paused_turn_spawns_with_zero_decisions(self, monkeypatch, capsys):
        def _boom(**kwargs):
            raise AssertionError("paused turn: no decision call")

        monkeypatch.setattr(routing_mod, "load_strategy", lambda **kw: _strategy())
        monkeypatch.setattr(routing_mod, "decide_via_openrouter", _boom)
        builds: list = []
        monkeypatch.setattr(loop_mod, "build_btw_agent", _capture_build(builds))
        events: list = []
        agent = _side_agent()
        routing = RoutingState(initial="on")
        routing.pause()
        ctx = loop_mod._btw_context_for(agent, routing=routing, routing_events=events)
        ctx.build("quick question")
        assert len(builds) == 1
        assert builds[0][0]["model"] is agent.model
        assert "effort" not in builds[0][0]  # replay untouched
        out = capsys.readouterr().out
        assert "Routed" not in out
        assert "Routing held" not in out
        assert events[0]["held"] is True
        assert events[0]["side"] is True
        assert events[0]["engine"] == "paused"
        assert events[0]["decision_model"] is None  # zero spend on skip

    def test_side_pause_skips_second_build(self, monkeypatch):
        calls: list = []

        def _engine(**kwargs):
            calls.append(kwargs)
            return EngineResult(answers=None, error="refused")

        events: list = []
        agent = _side_agent()
        ctx, builds = _side_ctx(monkeypatch, agent, _engine, events)
        ctx.build("first question")
        assert len(calls) == 1  # call 1 pauses; call 2 never runs
        assert builds[0][0]["model"] is agent.model
        ctx.build("second question")
        assert len(calls) == 1  # paused turn: zero new decisions
        assert builds[1][0]["model"] is agent.model
        assert events[0]["held"] is True and events[0]["engine"] == "openrouter"
        assert events[1]["held"] is True and events[1]["engine"] == "paused"

    def test_second_build_while_live_makes_no_new_decision(self, monkeypatch):
        calls: list = []

        def _engine(**kwargs):
            calls.append(kwargs)
            return _table_result(HAIKU)

        events: list = []
        agent = _side_agent()
        ctx, builds = _side_ctx(monkeypatch, agent, _engine, events)
        ctx.build("first question")
        assert len(calls) == 2  # model call plus effort call
        ctx.attach_live(SimpleNamespace(), SimpleNamespace(), "first question")
        assert ctx.has_live is True
        ctx.build("second question")
        assert len(calls) == 2  # no re-decision while live
        assert builds[1][0]["model"] is agent.model
        assert len(events) == 1

    def test_quiet_strategy_suppresses_btw_line(self, monkeypatch, capsys):
        strategy = _strategy()
        strategy.quiet = True
        events: list = []
        agent = _side_agent()
        ctx, builds = _side_ctx(
            monkeypatch, agent, lambda **kw: _table_result(HAIKU), events, strategy
        )
        ctx.build("deep refactor?")
        assert builds[0][0]["model"] is not agent.model  # pick still applies
        assert "Routed (btw)" not in capsys.readouterr().out

    def test_resolve_failure_holds_to_parent_silently(self, monkeypatch, capsys):
        import strands_harness.models as harness_models

        def _boom(*args, **kwargs):
            raise ValueError("unknown provider 'frobnicate'")

        monkeypatch.setattr(harness_models, "resolve_model", _boom)
        events: list = []
        agent = _side_agent()
        ctx, builds = _side_ctx(
            monkeypatch, agent, lambda **kw: _table_result(HAIKU), events
        )
        ctx.build("deep refactor?")
        assert builds[0][0]["model"] is agent.model
        assert "effort" not in builds[0][0]
        out = capsys.readouterr().out
        assert "Routed" not in out
        assert events[0]["held"] is True
        assert events[0]["engine"] == "resolve"

    def test_same_model_pick_skips_resolve_and_still_routes(self, monkeypatch, capsys):
        # Same-model stay picks never resolve: the hook applies no
        # switch and no effort, so there is nothing to judge.
        import strands_harness.models as harness_models

        def _boom(*args, **kwargs):
            raise AssertionError("same-model pick must not resolve")

        monkeypatch.setattr(harness_models, "resolve_model", _boom)
        strategy = _strategy(
            candidates=[
                RoutingCandidate(id=HAIKU, tier="small", levels=["low", "high"]),
                RoutingCandidate(id=NOVA_MICRO, tier="tiny", levels=["low"]),
            ]
        )
        events: list = []
        agent = _side_agent()  # live model resolves to NOVA_MICRO
        ctx, builds = _side_ctx(
            monkeypatch,
            agent,
            lambda **kw: _table_result(
                NOVA_MICRO, probs={HAIKU: 0.15, NOVA_MICRO: 0.85}
            ),
            events,
            strategy,
        )
        ctx.build("quick question")
        assert builds[0][0]["model"] is agent.model
        assert "effort" not in builds[0][0]
        assert events[0]["held"] is False
        assert events[0]["side"] is True
        assert "Routed (btw)" in capsys.readouterr().out

    def test_unreasoned_effort_holds_to_parent_silently(self, monkeypatch, capsys):
        # Thinking effort on a non-reasoning candidate passes the
        # effort call but the switch-path effort check must still hold.
        strategy = _strategy(
            candidates=[
                RoutingCandidate(id="openrouter/some-chat", levels=["low", "high"]),
            ]
        )
        events: list = []
        agent = _side_agent()
        ctx, builds = _side_ctx(
            monkeypatch,
            agent,
            lambda **kw: _table_result(
                "openrouter/some-chat",
                effort="low",
                effort_probs={"low": 0.8, "high": 0.2},
            ),
            events,
            strategy,
        )
        ctx.build("deep refactor?")
        assert builds[0][0]["model"] is agent.model
        out = capsys.readouterr().out
        assert "Routed" not in out
        assert events[0]["held"] is True
        assert events[0]["side"] is True
        assert events[0]["engine"] == "openrouter"

    def test_effort_reject_holds_to_parent_silently(self, monkeypatch, capsys):
        # Call-2-driven hold: the effort top choice sits outside the
        # picked levels, so the side spawn holds with no note.
        events: list = []
        agent = _side_agent()
        ctx, builds = _side_ctx(
            monkeypatch,
            agent,
            lambda **kw: _table_result(
                HAIKU,
                effort="max",
                effort_probs={"low": 0.15, "max": 0.85},
            ),
            events,
        )
        ctx.build("deep refactor?")
        assert builds[0][0]["model"] is agent.model
        assert "effort" not in builds[0][0]
        out = capsys.readouterr().out
        assert "Routed" not in out
        assert "Routing held" not in out
        assert events[0]["held"] is True
        assert events[0]["side"] is True

    def test_threshold_hold_stays_silent_with_event(self, monkeypatch, capsys):
        events: list = []
        agent = _side_agent()
        ctx, builds = _side_ctx(
            monkeypatch,
            agent,
            lambda **kw: _table_result(HAIKU, probs={HAIKU: 0.41, NOVA_MICRO: 0.59}),
            events,
        )
        ctx.build("ambiguous ask?")
        assert builds[0][0]["model"] is agent.model
        out = capsys.readouterr().out
        assert "Routed" not in out
        assert "Routing held" not in out
        assert events[0]["held"] is True
        assert events[0]["side"] is True
        assert events[0]["engine"] == "openrouter"

    def test_single_candidate_side_route_carries_effort_only_usage(
        self, monkeypatch, capsys
    ):
        # Fast-path parity: a lone candidate routes the side spawn
        # through the effort call only, with no model confidence.
        strategy = _strategy(
            candidates=[RoutingCandidate(id=HAIKU, levels=["low", "high"])]
        )
        events: list = []
        agent = _side_agent()
        ctx, builds = _side_ctx(
            monkeypatch,
            agent,
            lambda **kw: _table_result(HAIKU, usage=(40, 8, 0.0001)),
            events,
            strategy,
        )
        ctx.build("deep refactor?")
        kwargs = builds[0][0]
        assert kwargs["model"] is not agent.model
        assert kwargs["effort"] == "low"
        assert events[0]["held"] is False
        assert events[0]["side"] is True
        assert events[0]["model_confidence"] is None
        assert events[0]["effort_confidence"] == 0.7
        assert (events[0]["input_tokens"], events[0]["output_tokens"]) == (40, 8)
        assert events[0]["decision_cost"] == 0.0001  # call-2-only spend
        out = capsys.readouterr().out
        flat = " ".join(out.split())  # console width may wrap the line
        assert "Routed (btw)" in out
        assert "model n/a, effort 70%" in flat


class TestRoutedPickNoPersist:
    """FENCE (G-08-1): routed picks apply in memory and never touch
    the global default; only explicit /model choices persist."""

    def test_routed_pick_records_zero_saves(self, tmp_path, monkeypatch, capsys):
        events: list = []
        served, saved = _hook(
            tmp_path, monkeypatch, _strategy(), _table_result(HAIKU), events
        )
        assert served == HAIKU  # in-memory switch still applies
        assert saved == []  # but the global default is untouched
        assert len(_routed_lines(capsys.readouterr().out)) == 1  # note intact

    def test_explicit_model_branch_is_sole_persist_call_site(self):
        src = Path(loop_mod.__file__).read_text()
        assert src.count("save_model_choice") == 1

    def test_sole_persist_call_site_is_inside_model_branch(self):
        lines = Path(loop_mod.__file__).read_text().splitlines()
        hits = [i for i, ln in enumerate(lines) if "save_model_choice" in ln]
        assert len(hits) == 1
        window = "\n".join(lines[max(0, hits[0] - 20) : hits[0]])
        assert 'action == "model"' in window
