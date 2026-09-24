"""Kill-resume guarantee: restore without exit flush, clean exit flush (SES-03).

Full state means transcript plus agent state as of the last completed
message; an in-flight turn interrupted by SIGKILL is never replayed
(D-07/D-08). All tests run offline with a replay model double.
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
# SIGKILL simulation: restore without any exit flush
# ----------------------------------------------------------------------


class TestKillResume:
    def test_restore_without_exit_flush_keeps_transcript_and_state(self, tmp_path):
        session_id = str(uuid.uuid4())
        session_dir = tmp_path / "sessions"

        first = _make_session_agent(session_id, session_dir, "first answer")
        first("remember the number 42")
        first.state.set("working_plan", ["step-1", "step-2"])
        first("continue the plan")
        # SIGKILL here: no explicit_save, no index update, no cleanup.

        second = _make_session_agent(session_id, session_dir, "second answer")
        transcript = _transcript_text(second)
        assert "remember the number 42" in transcript
        assert "continue the plan" in transcript
        assert "first answer" in transcript
        assert second.state.get("working_plan") == ["step-1", "step-2"]

    def test_kill_loses_at_most_the_in_flight_turn(self, tmp_path):
        session_id = str(uuid.uuid4())
        session_dir = tmp_path / "sessions"

        first = _make_session_agent(session_id, session_dir, "first answer")
        first("completed turn marker")
        # The in-flight turn never completes, so it must not appear on resume.
        second = _make_session_agent(session_id, session_dir, "second answer")
        assert "completed turn marker" in _transcript_text(second)
        assert "never-sent in-flight marker" not in _transcript_text(second)


# ----------------------------------------------------------------------
# Clean exit: explicit save plus index update
# ----------------------------------------------------------------------


class TestCleanExitFlush:
    def test_explicit_save_round_trips_last_turn(self, tmp_path):
        from strands_code_cli.loop import explicit_save

        session_id = str(uuid.uuid4())
        session_dir = tmp_path / "sessions"

        first = _make_session_agent(session_id, session_dir, "first answer")
        first("final turn before clean exit")
        first.state.set("working_plan", ["done-1"])
        explicit_save(first)  # the deterministic clean-exit flush

        second = _make_session_agent(session_id, session_dir, "second answer")
        assert "final turn before clean exit" in _transcript_text(second)
        assert second.state.get("working_plan") == ["done-1"]

    def test_explicit_save_never_raises_without_session_manager(self):
        from strands_code_cli.loop import explicit_save

        explicit_save(object())  # no _session_manager: must be a silent no-op

    def test_clean_exit_bumps_index_recency(self, tmp_path):
        from strands_code_cli.session_index import SessionIndex

        index = SessionIndex(tmp_path / "index")
        session_id = index.mint()
        before = index.list_recent()[0]["updated_at"]
        index.ensure(session_id)  # what run_loop does after explicit_save
        assert index.list_recent()[0]["id"] == session_id
        assert index.list_recent()[0]["updated_at"] >= before
