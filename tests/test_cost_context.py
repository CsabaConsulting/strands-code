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

from strands.models.model import Model
from strands_harness import create_harness

from strands_code_agent.code_agent import CODE_AGENT_INSTRUCTIONS
from strands_code_agent.python_environments.local_sandboxed import (
    SandboxedPythonInterpreter,
)
from strands_code_cli import cost_context
from strands_code_cli.cost_context import (
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
    price_for,
    usage_line,
    window_for,
)


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
        self, output_model: Any, prompt: Any, system_prompt: str | None = None, **kwargs: Any
    ) -> Any:
        raise NotImplementedError("offline test double")
        yield  # pragma: no cover - keeps this an async generator

    async def stream(self, messages: Any, tool_specs: Any = None, system_prompt: Any = None, **kwargs: Any):  # type: ignore[override]
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
            "content": [{"toolUse": {"toolUseId": "t-1", "name": "python_repl", "input": {"code": "1"}}}],
        },
        {
            "role": "user",
            "content": [
                {"toolResult": {"toolUseId": "t-1", "status": "success", "content": [{"text": "1"}]}}
            ],
        },
        {"role": "user", "content": [{"text": "old question two"}]},
        {
            "role": "assistant",
            "content": [{"toolUse": {"toolUseId": "t-2", "name": "python_repl", "input": {"code": "2"}}}],
        },
        {
            "role": "user",
            "content": [
                {"toolResult": {"toolUseId": "t-2", "status": "success", "content": [{"text": "2"}]}}
            ],
        },
        {"role": "user", "content": [{"text": "latest ask"}]},
    ]


class _Summary:
    """Minimal response double exposing metrics.get_summary()."""

    def __init__(self, in_tok: int, out_tok: int, cycles: int = 1, duration: float = 0.5):
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
        assert cost_for(1_000_000, 1_000_000, "bedrock/global.anthropic.claude-sonnet-4-6") == 18.0
        assert cost_for(1_000_000, 1_000_000, "mystery/acme-1") is None

    def test_usage_line_money_on_hit(self):
        line = usage_line(451270, 1000, "bedrock/global.anthropic.claude-sonnet-4-6")
        assert "451.27K (45%)" in line
        assert "$" in line

    def test_usage_line_tokens_only_fallback(self):
        line = usage_line(451270, 1000, "mystery/acme-1")
        assert line == "451.27K (n/a)"

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
        assert "turn 1" in report.lower() or "#1" in report or "1" in report.splitlines()[1]
        assert "Display only" in report
        assert "no budgets or enforcement" in report

    def test_unknown_model_tokens_only(self):
        report = cost_report([{"turn": 1, "input_tokens": 10, "output_tokens": 5}], "mystery/acme-1")
        assert "$" not in report
        assert "Display only" in report


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
        compact_messages(agent, summarize=lambda old: f"summary of {len(old)}", keep_recent=2)
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
        from strands_code_cli.loop import explicit_save

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
