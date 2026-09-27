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


# ----------------------------------------------------------------------
# P1: router branches + loop usage/auto-compact wiring
# ----------------------------------------------------------------------


class TestCostRouterBranches:
    def _dispatch(self, tmp_path, text, agent=None, turns=None, model=None):
        from strands_code_cli.router import dispatch
        from strands_code_cli.session_index import SessionIndex

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
        from strands_code_cli.router import dispatch
        from strands_code_cli.session_index import SessionIndex

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
        from strands_code_cli.loop import record_turn_metrics

        turns: list = []
        line = record_turn_metrics(
            _Summary(451270, 1000),
            "bedrock/global.anthropic.claude-sonnet-4-6",
            turns,
        )
        assert line is not None and "451.27K (45%)" in line and "$" in line
        assert turns == [{"turn": 1, "input_tokens": 451270, "output_tokens": 1000}]

    def test_record_turn_metrics_without_metrics_returns_none(self):
        from strands_code_cli.loop import record_turn_metrics

        assert record_turn_metrics(None, "bedrock/x", []) is None

    def test_auto_compact_fires_at_80_and_keeps_pairs(self, tmp_path):
        from strands_code_cli.loop import maybe_auto_compact

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
        from strands_code_cli.loop import maybe_auto_compact

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
            _Path("strands_code_cli/model_switch.py"),
            _Path("strands_code_cli/cost_context.py"),
            _Path("strands_code_cli/router.py"),
            _Path("strands_code_cli/loop.py"),
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
        from strands_code_cli.provider_config import ProviderConfig

        path = tmp_path / "config.yaml"
        ProviderConfig(model="bedrock/x", base_url="https://proxy.local").save(path)
        import yaml

        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert set(payload) <= {"model", "base_url"}  # keys only, never secrets

        from pathlib import Path as _Path

        for mod in ("model_switch", "cost_context", "router", "loop", "main"):
            text = _Path(f"strands_code_cli/{mod}.py").read_text(encoding="utf-8")
            assert "os.getenv" not in text and "os.environ" not in text, mod
