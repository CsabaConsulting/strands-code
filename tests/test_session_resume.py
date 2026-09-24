"""Cross-process session resume: same id restores transcript plus agent state.

Covers SES-01 / D-07 / D-08 via ``create_harness`` with a session dict
carrying only ``id`` and ``dir`` keys. The model is an offline replay
double, so this runs with no AWS credentials.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from strands.models.model import Model
from strands_harness import create_harness

from strands_code_agent.code_agent import CODE_AGENT_INSTRUCTIONS
from strands_code_agent.python_environments.local_sandboxed import (
    SandboxedPythonInterpreter,
)


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


def _make_session_agent(session_id: str, session_dir: Path, text: str):
    """Build a harness agent for a session id (default agent id, always)."""
    interpreter = SandboxedPythonInterpreter("", authorized_imports=set())
    return create_harness(
        tools=[interpreter.get_tool()],
        instructions=CODE_AGENT_INSTRUCTIONS,
        session={"id": session_id, "dir": str(session_dir)},
        model=_ReplayModel(text),
        memory=False,
        skills=False,
    )


def _transcript_text(agent) -> str:
    """Flatten the agent's message history to plain text."""
    parts = []
    for message in agent.messages:
        for block in message.get("content", []):
            if "text" in block:
                parts.append(block["text"])
    return "\n".join(parts)


# ----------------------------------------------------------------------
# Resume round-trip
# ----------------------------------------------------------------------


class TestSessionResume:
    def test_same_id_reconstruction_restores_transcript_and_state(self, tmp_path):
        session_id = str(uuid.uuid4())
        session_dir = tmp_path / "sessions"

        first = _make_session_agent(session_id, session_dir, "first answer")
        first("remember the number 42")
        first.state.set("working_plan", ["step-1", "step-2"])
        first("continue the plan")

        second = _make_session_agent(session_id, session_dir, "second answer")
        transcript = _transcript_text(second)
        assert "remember the number 42" in transcript
        assert "continue the plan" in transcript
        assert "first answer" in transcript
        assert second.state.get("working_plan") == ["step-1", "step-2"]
        assert second.session_id == session_id
        assert second.agent_id == "default"

        follow_up = second("a follow-up question")
        assert "second answer" in follow_up.message["content"][0]["text"]
        assert "a follow-up question" in _transcript_text(second)

    def test_different_id_starts_empty(self, tmp_path):
        session_dir = tmp_path / "sessions"

        first = _make_session_agent(str(uuid.uuid4()), session_dir, "first answer")
        first("session A secret marker")

        other = _make_session_agent(str(uuid.uuid4()), session_dir, "other answer")
        assert "session A secret marker" not in _transcript_text(other)
        assert other.state.get("working_plan") is None


# ----------------------------------------------------------------------
# CLI construction contract (no bare Agent / CodeAgent in CLI code)
# ----------------------------------------------------------------------


class TestCliConstructionContract:
    def test_no_bare_agent_construction_in_cli(self):
        cli_dir = Path(__file__).resolve().parent.parent / "strands_code_cli"
        sources = sorted(cli_dir.glob("*.py"))
        assert sources, "strands_code_cli package must contain modules"
        offenders = []
        for path in sources:
            if path.name.startswith("test_"):
                continue
            text = path.read_text(encoding="utf-8")
            if re.search(r"(?<![\w.])Agent\s*\(", text):
                offenders.append(f"{path.name}: bare Agent(")
            if "CodeAgent(" in text:
                offenders.append(f"{path.name}: bare CodeAgent(")
        assert not offenders, f"CLI must construct via create_harness only: {offenders}"

    def test_session_dict_routes_to_given_id(self, tmp_path):
        session_id = str(uuid.uuid4())
        agent = _make_session_agent(session_id, tmp_path / "sessions", "probe")
        assert agent.session_id == session_id
        assert agent.agent_id == "default"
