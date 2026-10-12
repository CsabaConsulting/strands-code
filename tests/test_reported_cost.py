"""Tracer: provider-reported turn spend from capture to marked display.

Hermetic: the LiteLLMModel base is stubbed in sys.modules with a fake class
(copied-double pattern, no litellm import, no network, no credentials).
Covers capture, delegate-verbatim, drain, wrap gate, promotion, the
reported_cost usage-line kwarg, and the end-to-end tracer.
"""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from typing import Any

import pytest


@pytest.fixture
def _litellm_stub(monkeypatch):
    """Stub strands.models.litellm with a fake base class (hermetic)."""

    class FakeLiteLLMModel:
        """Minimal format_chunk base standing in for LiteLLMModel."""

        def format_chunk(self, event: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
            return {"chunk": dict(event), "kwargs": dict(kwargs)}

    module = types.ModuleType("strands.models.litellm")
    module.LiteLLMModel = FakeLiteLLMModel
    monkeypatch.setitem(sys.modules, "strands.models.litellm", module)
    return FakeLiteLLMModel


def _wrapped(model_id: str, fake_base: type, **config: Any):
    """Promote a fake resolved instance through the wrap gate."""
    from strands_code_cli.reported_cost import wrap_for_openrouter

    resolved = fake_base()
    for key, value in config.items():
        setattr(resolved, key, value)
    return wrap_for_openrouter(model_id, resolved)


def _metadata(cost: Any) -> dict[str, Any]:
    """One metadata chunk carrying a Usage-shaped fake (or a bare object)."""
    return {"chunk_type": "metadata", "data": SimpleNamespace(cost=cost)}


class _Summary:
    """Minimal response double exposing metrics.get_summary()."""

    def __init__(self, in_tok: int, out_tok: int) -> None:
        self._summary = {
            "accumulated_usage": {"inputTokens": in_tok, "outputTokens": out_tok},
            "total_cycles": 1,
            "total_duration": 0.5,
        }

    @property
    def metrics(self):
        outer = self

        class _M:
            def get_summary(self):
                return outer._summary

        return _M()


class TestCapture:
    def test_metadata_chunk_with_cost_records_cost(self, _litellm_stub):
        model = _wrapped("litellm/openrouter/qwen/qwen3-32b", _litellm_stub)
        model.format_chunk(_metadata(0.0024))
        assert model.take_reported_costs() == [0.0024]

    def test_metadata_chunk_without_cost_records_absent(self, _litellm_stub):
        from strands_code_cli.reported_cost import sum_reported_costs

        model = _wrapped("litellm/openrouter/qwen/qwen3-32b", _litellm_stub)
        model.format_chunk({"chunk_type": "metadata", "data": SimpleNamespace()})
        model.format_chunk({"chunk_type": "metadata", "data": None})
        assert model.take_reported_costs() == [None, None]
        assert sum_reported_costs(model.take_reported_costs()) is None

    def test_non_metadata_chunks_ignored(self, _litellm_stub):
        model = _wrapped("litellm/openrouter/qwen/qwen3-32b", _litellm_stub)
        model.format_chunk({"chunk_type": "text", "data": SimpleNamespace(cost=9.99)})
        assert model.take_reported_costs() == []

    def test_malformed_costs_never_raise_and_drain_to_none(self, _litellm_stub):
        from strands_code_cli.reported_cost import sum_reported_costs

        model = _wrapped("litellm/openrouter/qwen/qwen3-32b", _litellm_stub)
        model.format_chunk(_metadata("0.0024"))
        model.format_chunk(_metadata(True))
        model.format_chunk(_metadata(object()))
        model.format_chunk({"chunk_type": "metadata", "data": SimpleNamespace()})
        assert sum_reported_costs(model.take_reported_costs()) is None


class TestDelegateChunks:
    def test_override_returns_super_output_exactly(self, _litellm_stub):
        model = _wrapped("litellm/openrouter/qwen/qwen3-32b", _litellm_stub)
        event = _metadata(0.0024)
        assert model.format_chunk(event) == _litellm_stub().format_chunk(event)


class TestDrain:
    def test_take_returns_accumulated_and_resets(self, _litellm_stub):
        model = _wrapped("litellm/openrouter/qwen/qwen3-32b", _litellm_stub)
        model.format_chunk(_metadata(0.001))
        model.format_chunk(_metadata(0.002))
        assert model.take_reported_costs() == [0.001, 0.002]
        assert model.take_reported_costs() == []

    def test_multi_cycle_sums_present_only(self, _litellm_stub):
        from strands_code_cli.reported_cost import sum_reported_costs

        model = _wrapped("litellm/openrouter/qwen/qwen3-32b", _litellm_stub)
        model.format_chunk(_metadata(0.001))
        model.format_chunk({"chunk_type": "metadata", "data": SimpleNamespace()})
        model.format_chunk(_metadata(0.002))
        assert sum_reported_costs(model.take_reported_costs()) == pytest.approx(0.003)

    def test_present_zero_drains_as_present_zero(self, _litellm_stub):
        from strands_code_cli.reported_cost import sum_reported_costs

        model = _wrapped("litellm/openrouter/qwen/qwen3-32b", _litellm_stub)
        model.format_chunk(_metadata(0.0))
        assert sum_reported_costs(model.take_reported_costs()) == 0.0
        model.format_chunk(_metadata(0))
        drained = sum_reported_costs(model.take_reported_costs())
        assert drained == 0.0 and drained is not None


class TestWrapGate:
    def test_non_openrouter_ids_pass_through_identical(self, _litellm_stub):
        from strands_code_cli.reported_cost import wrap_for_openrouter

        bedrock = _litellm_stub()
        assert wrap_for_openrouter("bedrock/anthropic.claude-x", bedrock) is bedrock
        plain = _litellm_stub()
        assert wrap_for_openrouter("openai/gpt-4o", plain) is plain
        assert not hasattr(bedrock, "take_reported_costs")

    def test_openrouter_prefix_forms_wrap(self, _litellm_stub):
        first = _wrapped("litellm/openrouter/qwen/qwen3-32b", _litellm_stub)
        second = _wrapped("openrouter/qwen/qwen3-32b", _litellm_stub)
        assert callable(getattr(first, "take_reported_costs", None))
        assert callable(getattr(second, "take_reported_costs", None))

    def test_missing_extra_returns_resolved_unchanged(self, monkeypatch):
        from strands_code_cli.reported_cost import wrap_for_openrouter

        monkeypatch.setitem(sys.modules, "strands.models.litellm", None)
        resolved = SimpleNamespace(model_id="litellm/openrouter/qwen/qwen3-32b")
        assert (
            wrap_for_openrouter("litellm/openrouter/qwen/qwen3-32b", resolved) is resolved
        )


class TestPromotion:
    def test_promoted_instance_keeps_config(self, _litellm_stub):
        model = _wrapped(
            "litellm/openrouter/qwen/qwen3-32b",
            _litellm_stub,
            client_args={"base_url": "https://openrouter.ai/api/v1"},
            effort="high",
        )
        assert isinstance(model, _litellm_stub)
        assert type(model) is not _litellm_stub
        assert model.client_args == {"base_url": "https://openrouter.ai/api/v1"}
        assert model.effort == "high"


class TestUsageLineActual:
    def test_reported_cost_marks_actual(self):
        from strands_code_cli.cost_context import usage_line

        line = usage_line(12, 1, "bedrock/any", reported_cost=0.0024)
        assert "$0.00 actual" in line

    def test_actual_wins_over_estimate(self):
        from strands_code_cli.cost_context import usage_line

        line = usage_line(
            1_000_000,
            1_000_000,
            "bedrock/global.anthropic.claude-sonnet-4-6",
            reported_cost=0.0024,
        )
        assert line == "1.00M (100%) $0.00 actual"

    def test_without_reported_cost_byte_identical(self):
        from strands_code_cli.cost_context import usage_line

        assert (
            usage_line(451270, 1000, "bedrock/global.anthropic.claude-sonnet-4-6")
            == "451.27K (45%) $1.37"
        )
        assert usage_line(451270, 1000, "mystery/acme-1") == "451.27K (n/a)"


class TestTracerEndToEnd:
    def test_fake_cost_flows_to_row_and_usage_line(self, _litellm_stub):
        from strands_code_cli.loop import record_turn_metrics

        model = _wrapped("litellm/openrouter/qwen/qwen3-32b", _litellm_stub)
        model.format_chunk(_metadata(0.0024))
        turns: list = []
        line = record_turn_metrics(
            _Summary(12, 1), "litellm/openrouter/qwen/qwen3-32b", turns, model=model
        )
        assert turns[-1]["reported_cost"] == 0.0024
        assert line is not None and "$0.00 actual" in line

    def test_failed_turn_drains_without_bleed(self, _litellm_stub):
        from strands_code_cli.loop import record_turn_metrics

        model = _wrapped("litellm/openrouter/qwen/qwen3-32b", _litellm_stub)
        model.format_chunk(_metadata(0.0024))
        assert (
            record_turn_metrics(None, "litellm/openrouter/qwen/qwen3-32b", [], model=model)
            is None
        )
        assert model.take_reported_costs() == []


class TestFreshSideModel:
    def test_side_builds_from_one_parent_stay_independent(self, _litellm_stub):
        from strands_code_cli.reported_cost import fresh_side_model

        parent = _wrapped("litellm/openrouter/qwen/qwen3-32b", _litellm_stub)
        parent.format_chunk(_metadata(0.005))
        first = fresh_side_model(parent)
        second = fresh_side_model(parent)
        assert first is not parent
        assert second is not parent
        assert first is not second
        first.format_chunk(_metadata(0.001))
        assert first.take_reported_costs() == [0.001]
        assert second.take_reported_costs() == []
        assert parent.take_reported_costs() == [0.005]

    def test_plain_model_passes_through_identical(self):
        from strands_code_cli.reported_cost import fresh_side_model

        plain = SimpleNamespace()
        assert fresh_side_model(plain) is plain


class TestSideDrainCarrier:
    def test_finished_side_turns_carry_cost_to_rows(self, _litellm_stub):
        from concurrent.futures import Future

        from strands_code_cli.loop import _finish_btw_turn, record_turn_metrics

        def _side_agent(cost):
            model = _wrapped("litellm/openrouter/qwen/qwen3-32b", _litellm_stub)
            model.format_chunk(_metadata(cost))
            return SimpleNamespace(model=model, messages=[])

        btw = SimpleNamespace(pending=[], done=False)
        for question, cost in (("q1", 0.001), ("q2", 0.002)):
            future: Future = Future()
            future.set_result(_Summary(10, 1))
            _finish_btw_turn(btw, _side_agent(cost), future, question)
        assert [len(entry) for entry in btw.pending] == [4, 4]
        turns: list = []
        for _question, _body, result, reported in btw.pending:
            record_turn_metrics(
                result,
                "litellm/openrouter/qwen/qwen3-32b",
                turns,
                reported_cost=reported,
            )
        assert [turn["reported_cost"] for turn in turns] == [0.001, 0.002]


class TestExplicitReportedWins:
    def test_explicit_none_wins_over_model_costs(self, _litellm_stub):
        from strands_code_cli.loop import record_turn_metrics

        model = _wrapped("litellm/openrouter/qwen/qwen3-32b", _litellm_stub)
        model.format_chunk(_metadata(0.0024))
        turns: list = []
        record_turn_metrics(
            _Summary(12, 1),
            "litellm/openrouter/qwen/qwen3-32b",
            turns,
            model=model,
            reported_cost=None,
        )
        assert turns[-1].get("reported_cost") is None
        assert model.take_reported_costs() == [0.0024]

    def test_explicit_value_wins_without_consulting_model(self, _litellm_stub):
        from strands_code_cli.loop import record_turn_metrics

        model = _wrapped("litellm/openrouter/qwen/qwen3-32b", _litellm_stub)
        model.format_chunk(_metadata(0.0099))
        turns: list = []
        record_turn_metrics(
            _Summary(12, 1),
            "litellm/openrouter/qwen/qwen3-32b",
            turns,
            model=model,
            reported_cost=0.001,
        )
        assert turns[-1]["reported_cost"] == 0.001
        assert model.take_reported_costs() == [0.0099]


def _build_agent_with_resolved(monkeypatch, tmp_path, model_string, resolved):
    """Run build_agent with a stubbed create_harness resolving to `resolved`."""
    import importlib
    import uuid

    from strands.models.model import Model

    main_module = importlib.import_module("strands_code_cli.main")

    class _Placeholder(Model):
        def update_config(self, **model_config: Any) -> None:
            pass

        def get_config(self) -> Any:
            return {}

        async def structured_output(  # type: ignore[override]
            self, output_model: Any, prompt: Any, system_prompt: Any = None, **kwargs: Any
        ) -> Any:
            raise NotImplementedError("offline test double")
            yield  # pragma: no cover - keeps this an async generator

        async def stream(  # type: ignore[override]
            self, messages: Any, tool_specs: Any = None, system_prompt: Any = None, **kwargs: Any
        ):
            yield {"messageStop": {"stopReason": "end_turn"}}

    real_create = main_module.create_harness

    def _fake_create(**kwargs):
        agent = real_create(**{**kwargs, "model": _Placeholder()})
        agent.model = resolved
        return agent

    monkeypatch.setattr(main_module, "create_harness", _fake_create)
    return main_module.build_agent(str(uuid.uuid4()), tmp_path, model=model_string)


class TestInitialBuildWrap:
    def test_openrouter_initial_build_promotes_in_place(
        self, _litellm_stub, monkeypatch, tmp_path
    ):
        resolved = _litellm_stub()
        resolved.effort = "high"
        agent = _build_agent_with_resolved(
            monkeypatch, tmp_path, "litellm/openrouter/qwen/qwen3-32b", resolved
        )
        assert agent.model is resolved
        assert callable(getattr(agent.model, "take_reported_costs", None))
        assert agent.model.effort == "high"
        assert (
            agent._harness_kwargs["model"] == "litellm/openrouter/qwen/qwen3-32b"
        )

    def test_bedrock_initial_build_leaves_model_identical(
        self, _litellm_stub, monkeypatch, tmp_path
    ):
        resolved = _litellm_stub()
        agent = _build_agent_with_resolved(
            monkeypatch, tmp_path, "bedrock/anthropic.claude-x", resolved
        )
        assert agent.model is resolved
        assert not hasattr(agent.model, "take_reported_costs")


class TestWrapScope:
    def test_two_wraps_on_same_id_have_independent_costs(self, _litellm_stub):
        first = _wrapped("litellm/openrouter/qwen/qwen3-32b", _litellm_stub)
        second = _wrapped("litellm/openrouter/qwen/qwen3-32b", _litellm_stub)
        first.format_chunk(_metadata(0.001))
        assert first.take_reported_costs() == [0.001]
        assert second.take_reported_costs() == []

    def test_promotion_preserves_every_config_attribute(self, _litellm_stub):
        from strands_code_cli.reported_cost import wrap_for_openrouter

        resolved = _litellm_stub()
        resolved.model_id = "litellm/openrouter/qwen/qwen3-32b"
        resolved.effort = "high"
        resolved.thinking = {"type": "enabled", "budget_tokens": 4000}
        resolved.client_args = {"base_url": "https://openrouter.ai/api/v1"}
        resolved.temperature = 0.7
        before = dict(vars(resolved))
        promoted = wrap_for_openrouter(
            "litellm/openrouter/qwen/qwen3-32b", resolved
        )
        assert promoted is resolved
        after = {
            key: value
            for key, value in vars(promoted).items()
            if key != "_reported_costs"
        }
        assert after == before
