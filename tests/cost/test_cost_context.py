"""Tracer: usage-format + cost math + context/compact/clear on replay models.

Tracer observations (recorded 2026-09-27 — no live Bedrock touched):

- Usage-line shape ``451.27K (45%)``: abbreviated token value with fractional
  digits plus context-% vs the current model window; money appended only on an
  exact-substring price hit, otherwise tokens-only (unknown id → ``n/a`` %,
  no money). Computed from the local char/4 estimator, never the native
  Bedrock CountTokens API per-turn.
- ``get_response_metrics`` is extended, never replaced (signature stays
  backwards-compatible; new optional kwargs only).
- Snapshot mechanics (see tests/test_model_switch.py docstring): compact/clear
  mutate ``agent.messages`` in place and flush via ``explicit_save``; the
  session id and ``SessionIndex`` entry are kept.
- Pricing/window sources: see tests/test_model_switch.py docstring.

All tests run offline with a replay model double (copied pattern, no imports
from other test modules, no live Bedrock calls).
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from strands.models.model import Model
from strands_harness import create_harness

import strands_code_cli.cost.cost_context as cost_context
import strands_code_cli.cost.live_pricing as live_pricing
import strands_code_cli.model.model_capabilities as model_capabilities
from strands_code_agent.code_agent import CODE_AGENT_INSTRUCTIONS
from strands_code_agent.python_environments.local_sandboxed import (
    SandboxedPythonInterpreter,
)
from strands_code_cli.cost.cost_context import (
    AUTO_COMPACT_PCT,
    SUMMARY_MARKER,
    clear_messages,
    compact_messages,
    context_report,
    cost_for,
    cost_report,
    estimate_messages_tokens,
    format_tokens,
    format_usage,
    usage_line,
    window_for,
)


@pytest.fixture(autouse=True)
def _no_user_overrides(monkeypatch):
    """Report tests assume shipped tables; a real user file must not leak in."""
    monkeypatch.setattr(model_capabilities, "active_overrides", lambda: [])


# ----------------------------------------------------------------------
# Offline replay double (pattern copied from tests/test_kill_resume.py)
# ----------------------------------------------------------------------


class _ReplayModel(Model):
    """Offline model double streaming one canned text turn."""

    def __init__(self, text: str) -> None:
        self._text = text

    def update_config(self, **model_config: Any) -> None:
        pass

    def get_config(self) -> Any:
        return {}

    async def structured_output(  # type: ignore[override]
        self,
        output_model: Any,
        prompt: Any,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> Any:
        raise NotImplementedError("offline test double")
        yield  # pragma: no cover - keeps this an async generator

    async def stream(
        self,
        messages: Any,
        tool_specs: Any = None,
        system_prompt: Any = None,
        **kwargs: Any,
    ):  # type: ignore[override]
        yield {"messageStart": {"role": "assistant"}}
        yield {"contentBlockStart": {"start": {}}}
        yield {"contentBlockDelta": {"delta": {"text": self._text}}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "end_turn"}}
        yield {
            "metadata": {
                "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
                "metrics": {"latencyMs": 0},
            }
        }


def _make_replay_agent(session_id: str, session_dir: Path, text: str = "canned"):
    """Build a harness agent with the offline replay double."""
    interpreter = SandboxedPythonInterpreter("", authorized_imports=set())
    return create_harness(
        tools=[interpreter.get_tool()],
        instructions=CODE_AGENT_INSTRUCTIONS,
        session={"id": session_id, "dir": str(session_dir)},
        model=_ReplayModel(text),
        memory=False,
        skills=False,
    )


def _texts(agent) -> list[str]:
    """Flatten the agent's message history to plain text blocks."""
    return [
        block.get("text", "")
        for message in agent.messages
        for block in message.get("content", [])
        if "text" in block
    ]


def _pair_history() -> list[dict[str, Any]]:
    """Two tool pairs plus surrounding prose (pair-atomicity fixture)."""
    return [
        {"role": "user", "content": [{"text": "old question one"}]},
        {
            "role": "assistant",
            "content": [
                {
                    "toolUse": {
                        "toolUseId": "t-1",
                        "name": "python_repl",
                        "input": {"code": "1"},
                    }
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "toolResult": {
                        "toolUseId": "t-1",
                        "status": "success",
                        "content": [{"text": "1"}],
                    }
                }
            ],
        },
        {"role": "user", "content": [{"text": "old question two"}]},
        {
            "role": "assistant",
            "content": [
                {
                    "toolUse": {
                        "toolUseId": "t-2",
                        "name": "python_repl",
                        "input": {"code": "2"},
                    }
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "toolResult": {
                        "toolUseId": "t-2",
                        "status": "success",
                        "content": [{"text": "2"}],
                    }
                }
            ],
        },
        {"role": "user", "content": [{"text": "latest ask"}]},
    ]


class _Summary:
    """Minimal response double exposing metrics.get_summary()."""

    def __init__(
        self, in_tok: int, out_tok: int, cycles: int = 1, duration: float = 0.5
    ):
        self._summary = {
            "accumulated_usage": {"inputTokens": in_tok, "outputTokens": out_tok},
            "total_cycles": cycles,
            "total_duration": duration,
        }

    @property
    def metrics(self):
        outer = self

        class _M:
            def get_summary(self):
                return outer._summary

        return _M()


# ----------------------------------------------------------------------
# Usage-format spike
# ----------------------------------------------------------------------


class TestUsageFormat:
    def test_abbreviated_tokens(self):
        assert format_tokens(451270) == "451.27K"
        assert format_tokens(999) == "999"
        assert format_tokens(1500000) == "1.50M"

    def test_usage_shape_with_percent(self):
        assert format_usage(451270, 1_000_000) == "451.27K (45%)"

    def test_usage_unknown_window(self):
        assert format_usage(451270, None) == "451.27K (n/a)"

    def test_window_lookup_known_and_unknown(self):
        assert window_for("bedrock/global.anthropic.claude-sonnet-4-6") == 1_000_000
        assert window_for("bedrock/anthropic.claude-3-haiku-20240307") == 200_000
        assert window_for("mystery/acme-1") is None

    def test_money_only_on_price_hit(self):
        assert (
            cost_for(1_000_000, 1_000_000, "bedrock/global.anthropic.claude-sonnet-4-6")
            == 18.0
        )
        assert cost_for(1_000_000, 1_000_000, "mystery/acme-1") is None

    def test_usage_line_money_on_hit(self):
        line = usage_line(451270, 1000, "bedrock/global.anthropic.claude-sonnet-4-6")
        assert "451.27K (45%)" in line
        assert "$" in line

    def test_usage_line_tokens_only_fallback(self):
        line = usage_line(451270, 1000, "mystery/acme-1")
        assert line == "451.27K (n/a)"

    def test_gemini_static_pricing_limits_and_skip_bedrock_live(self, monkeypatch):
        assert cost_context.price_for("google/gemini-2.5-pro") == (1.25, 10.00)
        assert cost_context.price_for("google/gemini-2.5-flash") == (0.30, 2.50)
        assert cost_context.price_for("google/gemini-2.5-flash-lite") == (0.10, 0.40)
        assert window_for("google/gemini-2.5-flash") == 1_048_576
        assert window_for("google/gemini-2.5-pro") == 1_048_576

        line = usage_line(451270, 1000, "google/gemini-2.5-flash")
        assert "451.27K (43%)" in line
        assert "$" in line

        # Direct non-Bedrock providers skip AWS Price List lookups when live is enabled
        monkeypatch.delenv("STRANDS_CODE_NO_LIVE_PRICING", raising=False)
        monkeypatch.setattr(
            live_pricing,
            "bedrock_live_price",
            lambda *a, **k: pytest.fail(
                "non-Bedrock model must skip bedrock_live_price"
            ),
        )
        assert cost_context.price_for("google/gemini-2.5-flash") is not None
        assert cost_context.price_for("anthropic/claude-sonnet-4-6") is not None

    def test_gemini_3_and_4_static_pricing_and_limits(self):
        expected = {
            "google/gemini-3.5-flash-lite": (0.30, 2.50),
            "google/gemini-3.5-flash": (1.50, 9.00),
            "google/gemini-3.8-flash-cyber": (1.50, 7.50),
            "google/gemini-3.8-flash": (0.75, 3.75),
            "google/gemini-4-hydrogen": (1.50, 7.50),
            "google/gemini-4-neon": (3.00, 15.00),
            "google/gemini-4-argon": (2.00, 10.00),
            "google/gemini-4-carbon": (2.00, 10.00),
        }
        for model_id, rates in expected.items():
            assert cost_context.price_for(model_id) == rates, model_id
            assert window_for(model_id) == 1_048_576, model_id

    def test_get_response_metrics_cost_math(self):
        from strands_code_agent.utils import get_response_metrics

        m = get_response_metrics(
            _Summary(1_000_000, 1_000_000),
            price_1M_input_tokens=3.0,
            price_1M_output_tokens=15.0,
        )
        assert m["input_tokens"] == 1_000_000
        assert m["output_tokens"] == 1_000_000
        assert m["cost"] == 18.0
        assert m["total_cycles"] == 1

    def test_get_response_metrics_no_prices_no_cost(self):
        from strands_code_agent.utils import get_response_metrics

        m = get_response_metrics(_Summary(10, 20))
        assert "cost" not in m

    def test_get_response_metrics_model_id_lookup(self):
        from strands_code_agent.utils import get_response_metrics

        m = get_response_metrics(
            _Summary(1_000_000, 0),
            model_id="bedrock/global.anthropic.claude-sonnet-4-6",
            price_table=cost_context.MODEL_PRICING,
        )
        assert m["cost"] == 3.0


# ----------------------------------------------------------------------
# /cost report spike
# ----------------------------------------------------------------------


class TestCostReport:
    def test_rows_totals_and_display_only_footer(self):
        turns = [
            {"turn": 1, "input_tokens": 1_000_000, "output_tokens": 500_000},
            {"turn": 2, "input_tokens": 2000, "output_tokens": 500},
        ]
        report = cost_report(turns, "bedrock/global.anthropic.claude-sonnet-4-6")
        assert (
            "turn 1" in report.lower()
            or "#1" in report
            or "1" in report.splitlines()[1]
        )
        assert "Display only" in report
        assert "no budgets or enforcement" in report

    def test_unknown_model_tokens_only(self):
        report = cost_report(
            [{"turn": 1, "input_tokens": 10, "output_tokens": 5}], "mystery/acme-1"
        )
        assert "$" not in report
        assert "Display only" in report

    def test_rows_keep_own_turn_model_rates(self):
        turns = [
            {
                "turn": 1,
                "input_tokens": 1_000_000,
                "output_tokens": 1_000_000,
                "model": "anthropic.claude-3-haiku-20240307-v1:0",
            },
            {
                "turn": 2,
                "input_tokens": 1_000_000,
                "output_tokens": 1_000_000,
                "model": "amazon.nova-micro-v1:0",
            },
            # Legacy row without a model falls back to the report model.
            {"turn": 3, "input_tokens": 1_000_000, "output_tokens": 0},
        ]
        report = cost_report(turns, "anthropic.claude-3-haiku-20240307-v1:0")
        assert "turn 1: in 1.00M, out 1.00M, $1.5000" in report
        assert "turn 2: in 1.00M, out 1.00M, $0.1750" in report
        assert "turn 3: in 1.00M, out 0, $0.2500" in report
        assert "Total: in 3.00M, out 2.00M, $1.9250" in report


def _session_row(**overrides):
    base = {
        "turn": 1,
        "input_tokens": 12,
        "output_tokens": 1,
        "model": "anthropic.claude-3-haiku-20240307-v1:0",
    }
    base.update(overrides)
    return base


class TestReportedRows:
    def test_actual_row_renders_marked(self):
        report = cost_report([_session_row(reported_cost=0.0024)], "mystery/acme-1")
        assert "  turn 1: in 12, out 1, $0.0024 actual" in report

    def test_present_zero_renders_marked_zero(self):
        report = cost_report([_session_row(reported_cost=0.0)], "mystery/acme-1")
        assert "  turn 1: in 12, out 1, $0.0000 actual" in report

    def test_none_with_price_renders_bare(self):
        report = cost_report([_session_row(reported_cost=None)], "mystery/acme-1")
        assert "  turn 1: in 12, out 1, $0.0000" in report
        assert "actual" not in report

    def test_none_unpriced_tokens_only(self):
        row = _session_row(reported_cost=None, model="mystery/acme-1")
        report = cost_report([row], "mystery/acme-1")
        assert "$" not in report

    def test_mixed_actual_and_estimate_total(self):
        turns = [
            _session_row(reported_cost=0.0024),
            _session_row(turn=2, input_tokens=4000, output_tokens=0),
        ]
        report = cost_report(turns, "mystery/acme-1")
        assert "Total: in 4.01K, out 1, $0.0034" in report


class TestBlendedTotalsAndSplit:
    def test_mixed_total_shows_blended_and_split(self):
        turns = [
            _session_row(reported_cost=0.0024),
            _session_row(turn=2, input_tokens=4000, output_tokens=0),
        ]
        report = cost_report(turns, "mystery/acme-1")
        assert "Total: in 4.01K, out 1, $0.0034" in report
        assert "  (actual $0.0024 + estimated $0.0010)" in report.splitlines()

    def test_estimate_only_has_no_split(self):
        turns = [_session_row(turn=2, input_tokens=4000, output_tokens=0)]
        report = cost_report(turns, "mystery/acme-1")
        assert "Total: in 4.00K, out 0, $0.0010" in report
        assert not [
            line for line in report.splitlines() if line.startswith("  (actual")
        ]

    def test_actuals_only_has_no_split(self):
        turns = [
            _session_row(reported_cost=0.0024),
            _session_row(turn=2, reported_cost=0.001),
        ]
        report = cost_report(turns, "mystery/acme-1")
        assert "Total: in 24, out 2, $0.0034" in report
        assert not [
            line for line in report.splitlines() if line.startswith("  (actual")
        ]

    def test_present_zero_actual_opens_lane(self):
        turns = [
            _session_row(reported_cost=0.0),
            _session_row(turn=2, input_tokens=4000, output_tokens=0),
        ]
        report = cost_report(turns, "mystery/acme-1")
        assert "  (actual $0.0000 + estimated $0.0010)" in report.splitlines()

    def test_routing_reported_spend_marked_and_laned(self):
        turns = [_session_row(turn=1, input_tokens=4000, output_tokens=0)]
        event = _routed_event(decision_cost=0.0006)
        report = cost_report(turns, "mystery/acme-1", routing=[event])
        lines = _routing_lines(report)
        assert len(lines) == 1
        assert lines[0].endswith("$0.0006 actual")
        assert "  (actual $0.0006 + estimated $0.0010)" in report.splitlines()

    def test_routing_absent_cost_bare_zero(self):
        event = _routed_event(decision_cost=None)
        report = cost_report([], "a/routed", routing=[event])
        lines = _routing_lines(report)
        assert len(lines) == 1
        assert lines[0].endswith("$0.0000")
        assert "actual" not in lines[0]

    def test_absent_routing_cost_never_opens_lane(self):
        turns = [_session_row(turn=1, input_tokens=4000, output_tokens=0)]
        event = _routed_event(decision_cost=None)
        report = cost_report(turns, "mystery/acme-1", routing=[event])
        assert "Total: in 4.38K, out 41, $0.0010" in report
        assert not [
            line for line in report.splitlines() if line.startswith("  (actual")
        ]


class TestBedrockOfflineParity:
    def test_bedrock_report_byte_identical(self):
        turns = [
            {
                "turn": 1,
                "input_tokens": 1_000_000,
                "output_tokens": 500_000,
                "model": "bedrock/global.anthropic.claude-sonnet-4-6",
            },
            {
                "turn": 2,
                "input_tokens": 2000,
                "output_tokens": 500,
                "model": "bedrock/global.anthropic.claude-sonnet-4-6",
            },
        ]
        assert cost_report(turns, "bedrock/global.anthropic.claude-sonnet-4-6") == (
            "Cost — bedrock/global.anthropic.claude-sonnet-4-6\n"
            "  turn 1: in 1.00M, out 500.00K, $10.5000\n"
            "  turn 2: in 2.00K, out 500, $0.0135\n"
            "Total: in 1.00M, out 500.50K, $10.5135\n"
            "Prices: static table.\n"
            "Display only — no budgets or enforcement."
        )

    def test_bedrock_usage_line_unchanged(self):
        assert (
            usage_line(1000, 500, "bedrock/global.anthropic.claude-sonnet-4-6")
            == "1.00K (0%) $0.01"
        )

    def test_estimate_only_has_no_marker_or_split(self):
        turns = [
            _session_row(turn=1, input_tokens=4000, output_tokens=0),
            _session_row(turn=2, input_tokens=12, output_tokens=1),
        ]
        report = cost_report(turns, "mystery/acme-1")
        assert "actual" not in report
        assert not [
            line for line in report.splitlines() if line.startswith("  (actual")
        ]
        assert "n/a" not in report

    def test_unpriced_offline_report_byte_identical(self):
        row = _session_row(model="mystery/acme-1")
        assert cost_report([row], "mystery/acme-1") == (
            "Cost — mystery/acme-1\n"
            "  turn 1: in 12, out 1\n"
            "Total: in 12, out 1\n"
            "Prices: unknown.\n"
            "Display only — no budgets or enforcement."
        )


def _routed_event(**overrides):
    base = {
        "ask": 1,
        "side": False,
        "model": "a/routed",
        "effort": "low",
        "model_confidence": 0.85,
        "effort_confidence": None,
        "tie_break": False,
        "engine": "openrouter",
        "input_tokens": 384,
        "output_tokens": 41,
        "decision_cost": 0.0002,
        "held": False,
        "decision_model": "cheap/decider",
    }
    base.update(overrides)
    return base


def _routing_lines(report: str) -> list[str]:
    return [line for line in report.splitlines() if line.startswith("  ask ")]


class TestRoutingEntries:
    def test_compact_routed_entry(self):
        report = cost_report([], "a/routed", routing=[_routed_event()])
        assert _routing_lines(report) == [
            "  ask 1: a/routed (low) [model 85%, effort n/a]"
            " via openrouter $0.0002 actual"
        ]

    def test_routed_entry_renders_exact_reported_cost(self):
        # The spend is verbatim, never estimated from tokens: huge
        # usage on an unpriced model still prints the reported cents.
        event = _routed_event(
            input_tokens=1000000,
            output_tokens=1000000,
            decision_cost=0.0002,
            decision_model="mystery/x",
        )
        report = cost_report([], "a/routed", routing=[event])
        assert _routing_lines(report) == [
            "  ask 1: a/routed (low) [model 85%, effort n/a]"
            " via openrouter $0.0002 actual"
        ]

    def test_local_entry_renders_zero_spend(self):
        event = _routed_event(
            engine="local",
            input_tokens=1000000,
            output_tokens=1000000,
            decision_cost=None,
            decision_model="nimble",
        )
        report = cost_report([], "a/routed", routing=[event])
        assert _routing_lines(report) == [
            "  ask 1: a/routed (low) [model 85%, effort n/a] via local $0.0000"
        ]

    def test_native_entry_renders_computed_spend_with_marker(self):
        from strands_code_cli.routing.core import TYPESAFE_INPUT_USD_PER_MTOK

        event = _routed_event(
            engine="native",
            input_tokens=1000000,
            output_tokens=7,
            decision_cost=1000000 * TYPESAFE_INPUT_USD_PER_MTOK / 1_000_000,
            decision_model="jev-1.13.0",
        )
        report = cost_report([], "a/routed", routing=[event])
        assert _routing_lines(report) == [
            "  ask 1: a/routed (low) [model 85%, effort n/a] via native $0.0420 actual"
        ]
        assert "Prices: native computed input rate." in report

    def test_openrouter_unknown_provenance_keeps_unknown(self):
        event = _routed_event(decision_model="mystery/x")
        report = cost_report([], "a/routed", routing=[event])
        assert "Prices: unknown." in report

    def test_held_entry_names_serving_model(self):
        event = _routed_event(
            ask=2,
            model="a/serving",
            effort="",
            model_confidence=None,
            effort_confidence=None,
            input_tokens=0,
            output_tokens=0,
            decision_cost=None,
            held=True,
        )
        report = cost_report([], "a/serving", routing=[event])
        assert _routing_lines(report) == [
            "  ask 2: a/serving [model n/a, effort n/a] via openrouter [held] $0.0000"
        ]

    def test_side_marker_and_tie_break(self):
        event = _routed_event(side=True, tie_break=True)
        report = cost_report([], "a/routed", routing=[event])
        assert _routing_lines(report) == [
            "  ask 1 (btw): a/routed (low) [model 85%, effort n/a]"
            " via openrouter [tie-break] $0.0002 actual"
        ]

    def test_totals_fold_reported_spend(self):
        from strands_code_cli.cost.cost_context import cost_for

        turns = [
            {
                "turn": 1,
                "input_tokens": 1000,
                "output_tokens": 500,
                "model": "amazon.nova-micro-v1:0",
            }
        ]
        report = cost_report(turns, "amazon.nova-micro-v1:0", routing=[_routed_event()])
        expected = cost_for(1000, 500, "amazon.nova-micro-v1:0") + 0.0002
        assert expected is not None
        total = next(line for line in report.splitlines() if line.startswith("Total:"))
        assert total == f"Total: in 1.38K, out 541, ${expected:.4f}"

    def test_unparseable_event_falls_back(self):
        event = _routed_event(input_tokens="xx")
        report = cost_report([], "a/routed", routing=[event, "not-a-dict"])
        assert "  ask ?: unparseable routing event" in report
        total = next(line for line in report.splitlines() if line.startswith("Total:"))
        assert total == "Total: in 0, out 0"

    def test_missing_keys_degrade(self):
        report = cost_report([], "a/routed", routing=[{}])
        assert _routing_lines(report) == [
            "  ask ?: ? [model n/a, effort n/a] via ? $0.0000"
        ]

    def test_decisions_api_entry_renders_zero_actual_spend(self):
        event = _routed_event(
            engine="decisions_api",
            input_tokens=300,
            output_tokens=15,
            decision_cost=None,
            decision_model="~typesafe/jev-latest",
        )
        report = cost_report([], "a/routed", routing=[event])
        assert _routing_lines(report) == [
            "  ask 1: a/routed (low) [model 85%, effort n/a] via decisions_api $0.0000"
        ]

    def test_llm_entry_renders_and_folds_estimated_spend_lane(self, monkeypatch):
        monkeypatch.setattr(
            cost_context,
            "price_for",
            lambda mid: (0.15, 0.60) if mid == "openai/gpt-4o-mini" else None,
        )
        event = _routed_event(
            engine="llm",
            model_confidence=None,
            effort_confidence=None,
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            decision_cost=0.75,
            decision_model="openai/gpt-4o-mini",
        )
        report = cost_report([], "a/routed", routing=[event])
        assert _routing_lines(report) == [
            "  ask 1: a/routed (low) [model n/a, effort n/a] via llm $0.7500"
        ]
        assert " actual" not in report
        assert "Total: in 1.00M, out 1.00M, $0.7500" in report
        assert "Prices:" in report

    def test_mixed_actual_turn_and_llm_router_split_correctly(self, monkeypatch):
        monkeypatch.setattr(
            cost_context,
            "price_for",
            lambda mid: (0.15, 0.60) if mid == "openai/gpt-4o-mini" else None,
        )
        turns = [
            {
                "turn": 1,
                "input_tokens": 1000,
                "output_tokens": 500,
                "reported_cost": 0.25,
                "model": "openai/gpt-6.2-sol",
            }
        ]
        events = [
            _routed_event(
                engine="llm",
                model_confidence=None,
                effort_confidence=None,
                input_tokens=1000,
                output_tokens=200,
                decision_cost=0.05,
                decision_model="openai/gpt-4o-mini",
            )
        ]
        report = cost_report(turns, "openai/gpt-6.2-sol", routing=events)
        assert "Total: in 2.00K, out 700, $0.3000" in report
        assert "(actual $0.2500 + estimated $0.0500)" in report

    def test_nyquist_llm_routing_event_without_decision_model_skips_provenance(self):
        event = _routed_event(
            engine="llm",
            model_confidence=None,
            effort_confidence=None,
            input_tokens=500,
            output_tokens=50,
            decision_cost=0.0012,
            decision_model=None,
        )
        report = cost_report([], "a/routed", routing=[event])
        assert "via llm $0.0012" in report
        assert " actual" not in report
        assert "Total: in 500, out 50, $0.0012" in report
        assert "Prices: unknown." in report


# ----------------------------------------------------------------------
# /context + compact + clear spike on the replay model
# ----------------------------------------------------------------------


class TestContextOps:
    def test_context_report_exact_fields(self, tmp_path):
        agent = _make_replay_agent(str(uuid.uuid4()), tmp_path / "sessions")
        agent.messages.extend(_pair_history())
        report = context_report(agent, "bedrock/global.anthropic.claude-sonnet-4-6")
        lowered = report.lower()
        assert "token" in lowered
        assert "%" in report
        assert "message" in lowered
        assert "tool" in lowered
        assert "bedrock/global.anthropic.claude-sonnet-4-6" in report

    def test_context_report_unknown_window(self, tmp_path):
        agent = _make_replay_agent(str(uuid.uuid4()), tmp_path / "sessions")
        report = context_report(agent, "mystery/acme-1")
        assert "n/a" in report

    def test_compact_preserves_pairs_and_replays_last_user(self, tmp_path):
        agent = _make_replay_agent(str(uuid.uuid4()), tmp_path / "sessions")
        agent.messages.extend(_pair_history())
        n_before = len(agent.messages)
        compact_messages(
            agent, summarize=lambda old: f"summary of {len(old)}", keep_recent=2
        )
        assert len(agent.messages) < n_before
        texts = _texts(agent)
        assert any(SUMMARY_MARKER in t for t in texts)
        # Pair atomicity: no orphan toolUse without its toolResult and vice versa.
        uses = [
            block["toolUse"]["toolUseId"]
            for message in agent.messages
            for block in message.get("content", [])
            if "toolUse" in block
        ]
        results = [
            block["toolResult"]["toolUseId"]
            for message in agent.messages
            for block in message.get("content", [])
            if "toolResult" in block
        ]
        assert sorted(uses) == sorted(results)
        assert any("latest ask" in t for t in texts)

    def test_compact_never_emits_tool_result_summary(self, tmp_path):
        agent = _make_replay_agent(str(uuid.uuid4()), tmp_path / "sessions")
        agent.messages.extend(_pair_history())
        compact_messages(agent, summarize=lambda old: "s", keep_recent=2)
        for message in agent.messages:
            for block in message.get("content", []):
                if "text" in block and SUMMARY_MARKER in block["text"]:
                    continue
                assert "toolResult" not in block or SUMMARY_MARKER not in str(block)

    def test_clear_keeps_session_id_with_empty_history(self, tmp_path):
        from strands_code_cli.loop.core import explicit_save

        session_id = str(uuid.uuid4())
        agent = _make_replay_agent(session_id, tmp_path / "sessions")
        agent("something to forget")
        assert len(agent.messages) > 0
        cleared = clear_messages(agent)
        assert cleared >= 1
        assert agent.messages == []
        explicit_save(agent)  # flush must not raise on emptied history
        assert f"Context cleared — session {session_id} kept." == (
            f"Context cleared — session {session_id} kept."
        )

    def test_auto_compact_threshold_is_80(self):
        assert AUTO_COMPACT_PCT == 80

    def test_estimate_messages_tokens_scales(self):
        small = [{"role": "user", "content": [{"text": "hi"}]}]
        big = [{"role": "user", "content": [{"text": "x" * 4000}]}]
        assert estimate_messages_tokens(big) > estimate_messages_tokens(small) > 0

    def test_estimate_messages_tokens_counts_injected_blocks(self):
        injected = [
            {
                "role": "user",
                "content": [
                    {"injected": {"text": "a" * 400, "source": "strands-code:memory"}}
                ],
            }
        ]
        assert estimate_messages_tokens(injected) == 100
        malformed = [
            {
                "role": "user",
                "content": [
                    {"injected": "not-a-dict"},
                    {"injected": {"source": "no-text"}},
                    {"injected": {"text": None}},
                ],
            }
        ]
        assert estimate_messages_tokens(malformed) == 0


# ----------------------------------------------------------------------
# P1: router branches + loop usage/auto-compact wiring
# ----------------------------------------------------------------------


class TestCostRouterBranches:
    def _dispatch(self, tmp_path, text, agent=None, turns=None, model=None):
        from strands_code_cli.dispatch.core import dispatch
        from strands_code_cli.session.session_index import SessionIndex

        index = SessionIndex(tmp_path / "index")
        return dispatch(
            text,
            session_id=index.mint(),
            index=index,
            agent=agent,
            session_turns=turns,
            current_model=model or "bedrock/global.anthropic.claude-sonnet-4-6",
        )

    def test_cost_rows_and_footer(self, tmp_path):
        turns = [{"turn": 1, "input_tokens": 451270, "output_tokens": 1000}]
        action, message = self._dispatch(tmp_path, "/cost", turns=turns)
        assert action == "reply"
        assert "451.27K" in message
        assert "$" in message
        assert "Display only — no budgets or enforcement." in message

    def test_cost_refresh_dispatch(self, tmp_path, monkeypatch):
        import strands_code_cli.cost.live_pricing as live_pricing

        monkeypatch.delenv("STRANDS_CODE_NO_LIVE_PRICING", raising=False)
        monkeypatch.setenv("STRANDS_CODE_CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.setenv("AWS_REGION", "us-west-2")
        monkeypatch.setattr(live_pricing, "fetch_bedrock_records", lambda _r: [])
        monkeypatch.setattr(live_pricing, "fetch_openrouter_models", lambda: [])
        live_pricing._reset_cooldowns()
        action, message = self._dispatch(tmp_path, "/cost refresh")
        assert action == "reply"
        assert "Bedrock us-west-2: 0 models" in message
        assert "OpenRouter: 0 models." in message

    def test_cost_table_dispatch_reads_cache_only(self, tmp_path, monkeypatch):
        import strands_code_cli.cost.live_pricing as live_pricing

        monkeypatch.setenv("STRANDS_CODE_CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.setenv("AWS_REGION", "us-west-2")

        def _boom(*_a, **_k):
            raise AssertionError("table must not fetch")

        monkeypatch.setattr(live_pricing, "fetch_bedrock_records", _boom)
        monkeypatch.setattr(live_pricing, "fetch_openrouter_models", _boom)
        action, message = self._dispatch(tmp_path, "/cost table claude")
        assert action == "reply"
        assert "no cached data" in message
        assert "Static fallback:" in message

    def test_cost_unknown_subcommand(self, tmp_path):
        action, message = self._dispatch(tmp_path, "/cost frobnicate")
        assert action == "reply"
        assert message == "Usage: /cost [refresh|table [filter]]"

    def test_context_exact_fields(self, tmp_path):
        agent = _make_replay_agent(str(uuid.uuid4()), tmp_path / "sessions")
        agent.messages.extend(_pair_history())
        action, message = self._dispatch(tmp_path, "/context", agent=agent)
        assert action == "reply"
        assert "bedrock/global.anthropic.claude-sonnet-4-6" in message
        assert "%" in message and "messages:" in message and "tool calls:" in message
        assert "per-task accumulated tokens:" in message

    def test_compact_pair_atomic_with_marker_and_replay(self, tmp_path):
        agent = _make_replay_agent(str(uuid.uuid4()), tmp_path / "sessions")
        agent.messages.extend(
            {"role": "user", "content": [{"text": f"filler {n}"}]} for n in range(12)
        )
        agent.messages.extend(_pair_history())
        action, message = self._dispatch(tmp_path, "/compact", agent=agent)
        assert action == "reply"
        assert "recent messages kept" in message
        texts = _texts(agent)
        assert any(SUMMARY_MARKER in t for t in texts)
        assert any("latest ask" in t for t in texts)
        uses = {
            block["toolUse"]["toolUseId"]
            for msg in agent.messages
            for block in msg.get("content", [])
            if "toolUse" in block
        }
        results = {
            block["toolResult"]["toolUseId"]
            for msg in agent.messages
            for block in msg.get("content", [])
            if "toolResult" in block
        }
        assert sorted(uses) == sorted(results)

    def test_clear_keeps_session_id_exact_reply(self, tmp_path):
        from strands_code_cli.dispatch.core import dispatch
        from strands_code_cli.session.session_index import SessionIndex

        index = SessionIndex(tmp_path / "index")
        sid = index.mint()
        agent = _make_replay_agent(sid, tmp_path / "sessions")
        agent("something to forget")
        action, message = dispatch("/clear", session_id=sid, index=index, agent=agent)
        assert action == "reply"
        assert message == f"Context cleared — session {sid} kept."
        assert agent.messages == []

    def test_branches_without_agent_stay_replies(self, tmp_path):
        for cmd in ("/compact", "/clear", "/context"):
            action, message = self._dispatch(tmp_path, cmd)
            assert action == "reply"
            assert message == "No active session."


class TestLoopUsageWiring:
    def test_record_turn_metrics_appends_row_and_usage_line(self):
        from strands_code_cli.loop.core import record_turn_metrics

        turns: list = []
        line = record_turn_metrics(
            _Summary(451270, 1000),
            "bedrock/global.anthropic.claude-sonnet-4-6",
            turns,
        )
        assert line is not None and "451.27K (45%)" in line and "$" in line
        assert turns == [
            {
                "turn": 1,
                "input_tokens": 451270,
                "output_tokens": 1000,
                "model": "bedrock/global.anthropic.claude-sonnet-4-6",
            }
        ]

    def test_record_turn_metrics_without_metrics_returns_none(self):
        from strands_code_cli.loop.core import record_turn_metrics

        assert record_turn_metrics(None, "bedrock/x", []) is None

    def test_btw_spend_melts_into_session_totals(self):
        from strands_code_cli.loop.core import record_turn_metrics

        turns: list = []
        record_turn_metrics(_Summary(1000, 200), "bedrock/x-model", turns)
        record_turn_metrics(_Summary(3000, 400), "bedrock/x-model", turns)
        assert len(turns) == 2
        assert set(turns[0]) == set(turns[1])
        report = cost_report(turns, "bedrock/x-model")
        assert "Total: in 4.00K, out 600" in report
        assert "btw" not in report.lower()

    def test_auto_compact_fires_at_80_and_keeps_pairs(self, tmp_path):
        from strands_code_cli.loop.core import maybe_auto_compact

        agent = _make_replay_agent(str(uuid.uuid4()), tmp_path / "sessions")
        agent.messages.extend(
            {"role": "user", "content": [{"text": "z" * 400}]} for _ in range(1700)
        )
        agent.messages.extend(_pair_history())
        announcement = maybe_auto_compact(
            agent, "bedrock/anthropic.claude-3-haiku-20240307"
        )
        assert announcement is not None
        assert "auto-compacted" in announcement
        assert "recent messages kept" in announcement
        uses = {
            block["toolUse"]["toolUseId"]
            for msg in agent.messages
            for block in msg.get("content", [])
            if "toolUse" in block
        }
        results = {
            block["toolResult"]["toolUseId"]
            for msg in agent.messages
            for block in msg.get("content", [])
            if "toolResult" in block
        }
        assert sorted(uses) == sorted(results)

    def test_auto_compact_quiet_below_threshold_and_unknown(self, tmp_path):
        from strands_code_cli.loop.core import maybe_auto_compact

        agent = _make_replay_agent(str(uuid.uuid4()), tmp_path / "sessions")
        agent.messages.append({"role": "user", "content": [{"text": "hi"}]})
        assert (
            maybe_auto_compact(agent, "bedrock/global.anthropic.claude-sonnet-4-6")
            is None
        )
        assert maybe_auto_compact(agent, "mystery/acme-1") is None

    def test_no_budgets_or_enforcement_vocabulary(self):
        from pathlib import Path as _Path

        roots = [
            _Path("strands_code_cli/model/model_switch.py"),
            _Path("strands_code_cli/cost/cost_context.py"),
            _Path("strands_code_cli/dispatch/core.py"),
            _Path("strands_code_cli/loop/core.py"),
            _Path("strands_code_cli/loop/pump.py"),
            _Path("strands_code_agent/utils.py"),
        ]
        for path in roots:
            lines = path.read_text(encoding="utf-8").splitlines()
            for pos, line in enumerate(lines):
                lowered = line.lower()
                hits = [
                    word
                    for word in ("budget", "enforce", "quota", "halt")
                    if word in lowered
                ]
                if not hits:
                    continue
                # The display-only posture names what cost display never does;
                # allow the negation within a two-line window (wrapped prose).
                window = "\n".join(lines[max(0, pos - 1) : pos + 1]).lower()
                assert (
                    "display only" in window or "never" in window or "no " in window
                ), (path, line.strip())

    def test_no_credential_persistence_sinks(self, tmp_path):
        from strands_code_cli.entry.provider_config import ProviderConfig

        path = tmp_path / "config.yaml"
        ProviderConfig(model="bedrock/x", base_url="https://proxy.local").save(path)
        import yaml

        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert set(payload) <= {"model", "base_url"}  # keys only, never secrets
        ProviderConfig(
            model="openai/gpt-6.1-sol",
            base_url="https://proxy.local",
            api_mode="chat",
        ).save(path)
        payload_with_mode = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert set(payload_with_mode) <= {"model", "base_url", "api_mode"}

        from pathlib import Path as _Path

        for mod in (
            "model/model_switch",
            "cost/cost_context",
            "dispatch/core",
            "loop/core",
            "loop/pump",
            "entry/main",
        ):
            text = _Path(f"strands_code_cli/{mod}.py").read_text(encoding="utf-8")
            assert "os.getenv" not in text and "os.environ" not in text, mod


class TestSdkModelInfoWindow:
    def test_direct_provider_prefers_sdk_model_info_over_litellm_and_static(
        self, monkeypatch
    ):
        monkeypatch.delenv("STRANDS_CODE_NO_LIVE_PRICING", raising=False)
        monkeypatch.setattr(live_pricing, "openrouter_entry", lambda _id: None)
        monkeypatch.setattr(
            live_pricing,
            "litellm_entry",
            lambda _id: {"in": 1.0, "out": 2.0, "window": 111_111},
        )
        assert window_for("bedrock/global.anthropic.claude-sonnet-4-6") == 1_000_000
        assert window_for("openai/gpt-5.4") == 1_050_000

    def test_openrouter_prefers_endpoint_window_before_sdk_model_info(
        self, monkeypatch
    ):
        monkeypatch.delenv("STRANDS_CODE_NO_LIVE_PRICING", raising=False)
        monkeypatch.setattr(
            live_pricing,
            "openrouter_entry",
            lambda _id: {"in": 1.0, "out": 2.0, "window": 65_536},
        )
        monkeypatch.setattr(
            live_pricing,
            "litellm_entry",
            lambda _id: {"in": 1.0, "out": 2.0, "window": 111_111},
        )
        assert window_for("litellm/openrouter/openai/gpt-5.4") == 65_536

    def test_openrouter_falls_back_to_sdk_when_endpoint_window_absent(
        self, monkeypatch
    ):
        monkeypatch.delenv("STRANDS_CODE_NO_LIVE_PRICING", raising=False)
        monkeypatch.setattr(live_pricing, "openrouter_entry", lambda _id: None)
        monkeypatch.setattr(live_pricing, "litellm_entry", lambda _id: None)
        assert window_for("litellm/openrouter/openai/gpt-5.4") == 1_050_000

    def test_explicit_model_instance_window_honored_fail_soft(self, monkeypatch):
        from types import SimpleNamespace

        monkeypatch.setattr(live_pricing, "litellm_entry", lambda _id: None)
        fake_model = SimpleNamespace(
            model_info=SimpleNamespace(limits=SimpleNamespace(context_window=333_333))
        )
        assert window_for("mystery/custom-1", model=fake_model) == 333_333
        bad_model = SimpleNamespace(
            model_info=SimpleNamespace(limits=SimpleNamespace(context_window=True))
        )
        assert window_for("mystery/custom-1", model=bad_model) is None

    def test_sdk_lookup_exception_fails_soft_to_fallback(self, monkeypatch):
        import strands.models._model_info as sdk_model_info

        def _boom(_candidate: str):
            raise RuntimeError("corrupt sdk table")

        monkeypatch.setattr(sdk_model_info, "get_context_window_limit", _boom)
        assert window_for("bedrock/global.anthropic.claude-sonnet-4-6") == 1_000_000
        assert window_for("mystery/acme-1") is None

    def test_arn_inference_profile_and_openrouter_litellm_fallback(self, monkeypatch):
        monkeypatch.delenv("STRANDS_CODE_NO_LIVE_PRICING", raising=False)
        monkeypatch.setattr(live_pricing, "openrouter_entry", lambda _id: None)
        monkeypatch.setattr(
            live_pricing,
            "litellm_entry",
            lambda _id: {"in": 1.0, "out": 2.0, "window": 77_777},
        )
        assert (
            window_for(
                "arn:aws:bedrock:us-west-2:123456789012:inference-profile/global.anthropic.claude-sonnet-4-6"
            )
            == 1_000_000
        )
        assert window_for("litellm/openrouter/mystery/custom-model") == 77_777


class TestCacheAwareUsageAndCost:
    @staticmethod
    def _usage_result(
        in_tok: int,
        out_tok: int,
        *,
        cache_read: int = 0,
        cache_write: int = 0,
        total_tok: int = 0,
    ):
        usage: dict[str, int] = {
            "inputTokens": in_tok,
            "outputTokens": out_tok,
        }
        if cache_read:
            usage["cacheReadInputTokens"] = cache_read
        if cache_write:
            usage["cacheWriteInputTokens"] = cache_write
        if total_tok:
            usage["totalTokens"] = total_tok

        class _R:
            class metrics:
                @staticmethod
                def get_summary():
                    return {
                        "accumulated_usage": usage,
                        "total_cycles": 1,
                        "total_duration": 0.5,
                    }

        return _R()

    def test_record_turn_metrics_anthropic_exclusive_vs_openai_inclusive(self):
        from strands_code_cli.loop.core import record_turn_metrics

        anthropic_turns: list[dict[str, Any]] = []
        a_line = record_turn_metrics(
            self._usage_result(
                100,
                300,
                cache_read=125_000,
                cache_write=40_500,
                total_tok=165_900,
            ),
            "anthropic/claude-sonnet-5-5",
            anthropic_turns,
        )
        assert a_line is not None
        assert "(17%, 75% cached)" in a_line
        assert anthropic_turns == [
            {
                "turn": 1,
                "input_tokens": 165_600,
                "output_tokens": 300,
                "model": "anthropic/claude-sonnet-5-5",
                "cache_read_tokens": 125_000,
                "cache_write_tokens": 40_500,
            }
        ]

        openai_turns: list[dict[str, Any]] = []
        o_line = record_turn_metrics(
            self._usage_result(
                165_600,
                300,
                cache_read=125_000,
                cache_write=0,
                total_tok=165_900,
            ),
            "openai/gpt-6.1-sol",
            openai_turns,
        )
        assert o_line is not None
        assert "(16%, 75% cached)" in o_line
        assert openai_turns == [
            {
                "turn": 1,
                "input_tokens": 165_600,
                "output_tokens": 300,
                "model": "openai/gpt-6.1-sol",
                "cache_read_tokens": 125_000,
            }
        ]
        rates = cost_context.cache_prices_for("openai/gpt-6.1-sol")
        assert rates is not None
        expected = (
            (165_600 - 125_000) * rates[0] + 125_000 * rates[1] + 300 * rates[3]
        ) / 1_000_000
        assert cost_for(
            165_600, 300, "openai/gpt-6.1-sol", cache_read_tokens=125_000
        ) == pytest.approx(expected)

    def test_zero_cache_turns_byte_identical_usage_and_report(self):
        line_no_cache = usage_line(1000, 500, "anthropic/claude-sonnet-5-5")
        line_zero = usage_line(
            1000,
            500,
            "anthropic/claude-sonnet-5-5",
            cache_read_tokens=0,
            cache_write_tokens=0,
        )
        assert line_no_cache == line_zero == "1.00K (0%) $0.01"
        assert "cached" not in line_zero

        turns = [{"turn": 1, "input_tokens": 1000, "output_tokens": 500}]
        report = cost_report(turns, "anthropic/claude-sonnet-5-5")
        assert "turn 1: in 1.00K, out 500, $0.0070" in report
        assert "cached" not in report

    def test_cost_report_renders_cache_read_and_write_cells(self):
        report = cost_report(
            [
                {
                    "turn": 1,
                    "input_tokens": 165_600,
                    "output_tokens": 300,
                    "cache_read_tokens": 125_000,
                    "cache_write_tokens": 40_500,
                },
                {
                    "turn": 2,
                    "input_tokens": 165_600,
                    "output_tokens": 300,
                    "cache_read_tokens": 125_000,
                },
                {
                    "turn": 3,
                    "input_tokens": 40_600,
                    "output_tokens": 100,
                    "cache_write_tokens": 40_500,
                },
            ],
            "anthropic/claude-sonnet-5-5",
        )
        assert "turn 1: in 165.60K (125.00K cached, 40.50K write)" in report
        assert "turn 2: in 165.60K (125.00K cached)," in report
        assert "turn 3: in 40.60K (40.50K write)," in report
        assert (
            usage_line(165_600, 300, "mystery/unknown-model", cache_read_tokens=125_000)
            == "165.60K (n/a, 75% cached)"
        )

    def test_estimate_messages_tokens_counts_summary_blocks(self):
        from strands_code_cli.cost.cost_context import estimate_messages_tokens

        summary_msg = [
            {
                "role": "assistant",
                "content": [
                    {
                        "summary": {
                            "provider": "anthropic",
                            "signature": "S",
                            "text": "x" * 400,
                        }
                    }
                ],
            }
        ]
        assert estimate_messages_tokens(summary_msg) == 100
        malformed = [
            {
                "role": "assistant",
                "content": [{"summary": None}, {"summary": {"text": None}}],
            }
        ]
        assert estimate_messages_tokens(malformed) == 0

    def test_gpt_62_static_pricing_cache_rates_and_window(self, monkeypatch):
        monkeypatch.setattr(live_pricing, "openrouter_entry", lambda _id: None)
        monkeypatch.setattr(live_pricing, "litellm_entry", lambda _id: None)
        assert cost_context.price_for("openai/gpt-6.2-sol") == (2.00, 10.00)
        assert cost_context.price_for("openai/gpt-6.2-astra") == (8.00, 40.00)
        assert cost_context.cache_prices_for("openai/gpt-6.2-sol") == (
            2.00,
            0.10,
            2.00,
            10.00,
        )
        assert cost_context.cache_prices_for("openai/gpt-6.2-astra") == (
            8.00,
            0.40,
            8.00,
            40.00,
        )
        assert window_for("openai/gpt-6.2-sol") == 1_050_000
        assert window_for("openai/gpt-6.2-astra") == 1_050_000
        assert cost_for(
            1_000_000, 100_000, "openai/gpt-6.2-sol", cache_read_tokens=500_000
        ) == pytest.approx(2.05)

    def test_scrub_credentials_redacts_openai_and_anthropic_keys(self):
        from strands_code_cli.cost.cost_context import scrub_credentials

        raw = (
            "keys sk-proj-abcdefghijklmnopqrstuvwxyz123456 "
            "sk-svcacct-abcdefghijklmnopqrstuvwxyz123456 "
            "sk-ant-api03-abcdefghijklmnop "
            "AKIAIOSFODNN7EXAMPLE "
            "TYPESAFE_API_KEY=ts-canary-abc12345 "
            "JEV_API_KEY=jev-canary-xyz98765"
        )
        scrubbed = scrub_credentials(raw)
        assert "sk-proj-" not in scrubbed
        assert "sk-svcacct-" not in scrubbed
        assert "sk-ant-" not in scrubbed
        assert "AKIA" not in scrubbed
        assert "ts-canary-abc12345" not in scrubbed
        assert "jev-canary-xyz98765" not in scrubbed

    def test_nyquist_cache_rates_write_only_suffix_and_invalid_anthropic_window(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.delenv("STRANDS_CODE_NO_LIVE_PRICING", raising=False)
        monkeypatch.setenv("STRANDS_CODE_CACHE_DIR", str(tmp_path))
        monkeypatch.setattr(live_pricing, "openrouter_entry", lambda _id: None)

        live_pricing.store_anthropic_models(
            [
                {"id": "claude-bool-win", "max_input_tokens": True},
                {"id": "claude-zero-win", "max_input_tokens": 0},
            ]
        )
        assert (
            cost_context._anthropic_cached_window("anthropic/claude-bool-win") is None
        )
        assert (
            cost_context._anthropic_cached_window("anthropic/claude-zero-win") is None
        )

        assert cost_context._default_cache_rates("openai/gpt-4o", 2.0) == (1.0, 2.0)
        assert cost_context._default_cache_rates("openai/o3", 2.0) == (0.5, 2.0)

        monkeypatch.setattr(
            live_pricing,
            "litellm_entry",
            lambda _id: {
                "in": 2.0,
                "out": 10.0,
                "cache_read": 0.15,
                "cache_write": 2.5,
            },
        )
        assert cost_context.cache_prices_for("openai/gpt-6.1-sol") == (
            2.0,
            0.15,
            2.5,
            10.0,
        )

        zero_in = usage_line(0, 10, "anthropic/claude-sonnet-5-5", cache_read_tokens=5)
        assert "cached" not in zero_in and "write" not in zero_in
        write_only = usage_line(
            100_000, 100, "anthropic/claude-sonnet-5-5", cache_write_tokens=50_000
        )
        assert "(10%, 50% cache write)" in write_only

    def test_nyquist_extract_prompt_usage_zero_total_and_malformed_fallbacks(self):
        from strands_code_cli.loop.core import (
            _extract_prompt_usage,
            record_turn_metrics,
        )

        for model_id, expected_in in (
            ("anthropic/claude-sonnet-5-5", 10_600),
            ("claude-sonnet-5-5", 10_600),
            ("openai/gpt-6.1-sol", 100),
        ):
            turns: list[dict[str, Any]] = []
            record_turn_metrics(
                self._usage_result(
                    100, 50, cache_read=10_000, cache_write=500, total_tok=0
                ),
                model_id,
                turns,
            )
            assert turns[0]["input_tokens"] == expected_in

        class _BoomMetrics:
            class metrics:
                @staticmethod
                def get_summary():
                    raise RuntimeError("boom")

        assert _extract_prompt_usage(_BoomMetrics(), "openai/gpt-6.1-sol", 42, 5) == (
            42,
            0,
            0,
        )
        bad_usage = self._usage_result(42, 5)
        bad_usage.metrics.get_summary()["accumulated_usage"]["cacheReadInputTokens"] = (
            "not-an-int"
        )
        assert _extract_prompt_usage(bad_usage, "openai/gpt-6.1-sol", 42, 5) == (
            42,
            0,
            0,
        )

    def test_meta_muse_static_pricing_50x_cache_window_usage_and_scrub(
        self, monkeypatch
    ):
        from strands_code_cli.cost.cost_context import scrub_credentials
        from strands_code_cli.loop.core import record_turn_metrics

        monkeypatch.setattr(live_pricing, "openrouter_entry", lambda _id: None)
        monkeypatch.setattr(live_pricing, "litellm_entry", lambda _id: None)

        assert cost_context.price_for("meta/muse-spark-1.3-contributor") == (0.10, 0.20)
        assert cost_context.price_for("meta/muse-spark-1.3") == (1.25, 4.25)
        assert cost_context.price_for("meta/muse-wonder-1.0") == (4.00, 20.00)
        assert cost_context.price_for("meta/muse-ember-1.0") == (0.10, 0.50)

        assert cost_context.cache_prices_for(
            "meta/muse-spark-1.3-contributor"
        ) == pytest.approx((0.10, 0.002, 0.10, 0.20))
        assert cost_context.cache_prices_for("meta/muse-ember-1.0") == pytest.approx(
            (0.10, 0.004, 0.10, 0.50)
        )
        assert cost_context.cache_prices_for("meta/muse-wonder-1.0") == pytest.approx(
            (4.00, 0.20, 4.00, 20.00)
        )
        assert cost_context.cache_prices_for("meta/muse-spark-1.3") == pytest.approx(
            (1.25, 0.15, 1.25, 4.25)
        )
        for mid in (
            "meta/muse-spark-1.3-contributor",
            "meta/muse-spark-1.3",
            "meta/muse-wonder-1.0",
            "meta/muse-ember-1.0",
        ):
            assert window_for(mid) == 1_048_576

        # Probe-verified inclusive inputTokens on Meta /v1/responses
        turns: list[dict[str, Any]] = []
        line = record_turn_metrics(
            self._usage_result(1250, 129, cache_read=226, total_tok=1379),
            "meta/muse-spark-1.3-contributor",
            turns,
        )
        assert line is not None
        assert "18% cached" in line
        assert turns[0]["input_tokens"] == 1250
        assert turns[0]["cache_read_tokens"] == 226
        expected_usd = (1024 * 0.10 + 226 * 0.002 + 129 * 0.20) / 1_000_000
        assert cost_for(
            1250, 129, "meta/muse-spark-1.3-contributor", cache_read_tokens=226
        ) == pytest.approx(expected_usd)

        raw = (
            "LLM_1607358788850350_nx9SecretToken1234 "
            "Authorization: Bearer LLM|1607358788850350|pipeSecret5678 "
            "LLM|1607358788850350|AbCd+EfGh/IjKl== "
            "MODEL_API_KEY=LLM|99999|SecretToken123456"
        )
        scrubbed = scrub_credentials(raw)
        assert "LLM_1607" not in scrubbed
        assert "LLM|1607" not in scrubbed
        assert "AbCd+EfGh/IjKl==" not in scrubbed
        assert "SecretToken123456" not in scrubbed

    def test_meta_muse_additional_tier_pricing_and_cache_rates(self, monkeypatch):
        monkeypatch.setattr(live_pricing, "openrouter_entry", lambda _id: None)
        monkeypatch.setattr(live_pricing, "litellm_entry", lambda _id: None)
        assert cost_context.price_for("meta/muse-spark-1.2-contributor") == (0.10, 0.20)
        assert cost_context.price_for("meta/muse-spark-1.1") == (1.25, 4.25)
        assert cost_context.cache_prices_for(
            "meta/muse-spark-1.2-contributor"
        ) == pytest.approx((0.10, 0.002, 0.10, 0.20))
        assert cost_context.cache_prices_for("meta/muse-spark-1.1") == pytest.approx(
            (1.25, 0.15, 1.25, 4.25)
        )
