"""Integration tests for /review turn-scoped read-only Plan gate and tool_interface isolation (REVIEW-01)."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace

from strands.interventions import Deny as InterventionDeny

from strands_code_cli.dispatch.core import dispatch
from strands_code_cli.loop.core import run_loop
from strands_code_cli.policy.codeact import CodeactState
from strands_code_cli.policy.core import Deny
from strands_code_cli.policy.mode import ModeState
from strands_code_cli.policy.policy_gate import build_interventions
from strands_code_cli.session.session_index import SessionIndex


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo_with_dirty_change(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "src.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "secret.txt").write_text("TOP_SECRET_VALUE\n", encoding="utf-8")
    _git(repo, "add", "src.py", "secret.txt")
    _git(repo, "commit", "-q", "-m", "init")
    (repo / "src.py").write_text("x = 2\n# look at @secret.txt\n", encoding="utf-8")
    return repo


class TestReviewLoopIsolation:
    def test_review_uses_turn_scoped_read_only_gate_tool_interface_and_preserves_sticky_modes(
        self, tmp_path, monkeypatch
    ):
        repo = _init_repo_with_dirty_change(tmp_path)
        monkeypatch.chdir(repo)
        index = SessionIndex(tmp_path / "sessions")

        # Built-in /review wins even if a skill named 'review' exists.
        (repo / ".agent" / "skills" / "review").mkdir(parents=True)
        (repo / ".agent" / "skills" / "review" / "SKILL.md").write_text(
            "---\nname: review\ndescription: Custom\n---\nBody\n", encoding="utf-8"
        )
        act_action, act_payload = dispatch(
            "/review -- focus on diff", session_id="s1", index=index, cwd=repo
        )
        assert act_action == "review" and act_payload is not None

        gate = build_interventions()[0]
        observed_read_only: list[bool] = []
        observed_write_verdict: list[bool] = []
        prompts: list = []

        class _FakeAgent:
            def __init__(self) -> None:
                self.messages: list[dict] = []
                self._policy_gate = gate
                self.tools = {}

            def add_hook(self, *_a, **_k) -> None:
                pass

            def __call__(self, prompt, **_kw):
                prompts.append(prompt)
                observed_read_only.append(gate.is_read_only(self))
                ev = SimpleNamespace(
                    agent=self,
                    tool_use={
                        "name": "write",
                        "input": {"path": "x.py", "content": "1"},
                    },
                    cancel_tool=None,
                )
                outcome = asyncio.run(gate.before_tool_call(ev))
                observed_write_verdict.append(isinstance(outcome, InterventionDeny))
                self.messages.append(
                    {"role": "assistant", "content": [{"text": "looks good"}]}
                )
                return SimpleNamespace(
                    stop_reason="end_turn",
                    metrics=SimpleNamespace(accumulated_usage={}),
                    message=self.messages[-1],
                )

        agent = _FakeAgent()
        gate.bind_main_agent(agent)

        lines = iter(["/codeact code", "/review -- check bug risk", "/exit"])

        class _Sess:
            def __init__(self, **_kw):
                pass

            def prompt(self, _p: str, **_kw):
                return next(lines)

        monkeypatch.setattr("strands_code_cli.loop.core.PromptSession", _Sess)
        routing_asks: list[str] = []
        monkeypatch.setattr(
            "strands_code_cli.loop.core._route_pre_turn",
            lambda _a, *, current_model, ask_text, **_kw: (
                routing_asks.append(ask_text) or current_model
            ),
        )
        printed: list[str] = []
        monkeypatch.setattr(
            "strands_code_cli.loop.core.print_plain",
            lambda _c, text, **_kw: printed.append(str(text)),
        )

        run_loop(
            agent, session_id="s1", index=index, model_id="anthropic/claude-sonnet-5-5"
        )

        # Turn ran under read-only gate blocking write, then restored to act.
        assert observed_read_only == [True]
        assert observed_write_verdict == [True]
        assert gate.is_read_only(agent) is False
        # Sticky CodeactState stayed untouched & review ran on tool interface.
        assert "interface: tool" in printed
        assert "interface: codeact" not in printed
        # Diff body & @secret.txt never triggered attachment read or leaked to routing_ask.
        assert routing_asks == ["/review HEAD check bug risk"]
        assert "TOP_SECRET_VALUE" not in prompts[0]
        assert "You are in Plan mode:" not in prompts[0]
        assert isinstance(Deny("x"), Deny)
        assert ModeState().mode == "act"
        assert CodeactState().interface == "tool"

    def test_review_restores_gate_on_keyboard_interrupt(self, tmp_path, monkeypatch):
        repo = _init_repo_with_dirty_change(tmp_path)
        monkeypatch.chdir(repo)
        index = SessionIndex(tmp_path / "sessions")
        gate = build_interventions()[0]

        class _InterruptAgent:
            def __init__(self) -> None:
                self.messages: list[dict] = []
                self._policy_gate = gate

            def add_hook(self, *_a, **_k) -> None:
                pass

            def __call__(self, *_a, **_kw):
                assert gate.is_read_only(self) is True
                raise KeyboardInterrupt

        agent = _InterruptAgent()
        gate.bind_main_agent(agent)
        lines = iter(["/review", "/exit"])

        class _Sess:
            def __init__(self, **_kw):
                pass

            def prompt(self, _p: str, **_kw):
                return next(lines)

        monkeypatch.setattr("strands_code_cli.loop.core.PromptSession", _Sess)
        run_loop(
            agent, session_id="s1", index=index, model_id="anthropic/claude-sonnet-5-5"
        )
        assert gate.is_read_only(agent) is False

    def test_review_in_sticky_plan_mode_keeps_read_only_without_arming_pending_plan(
        self, tmp_path, monkeypatch
    ):
        repo = _init_repo_with_dirty_change(tmp_path)
        monkeypatch.chdir(repo)
        index = SessionIndex(tmp_path / "sessions")
        gate = build_interventions()[0]

        class _PlanAgent:
            def __init__(self) -> None:
                self.messages: list[dict] = []
                self._policy_gate = gate

            def add_hook(self, *_a, **_k) -> None:
                pass

            def __call__(self, *_a, **_kw):
                assert gate.is_read_only(self) is True
                self.messages.append(
                    {"role": "assistant", "content": [{"text": "reviewed"}]}
                )
                return SimpleNamespace(
                    stop_reason="end_turn",
                    metrics=SimpleNamespace(accumulated_usage={}),
                    message=self.messages[-1],
                )

        agent = _PlanAgent()
        gate.bind_main_agent(agent)
        lines = iter(["/mode plan", "/review", "/approve", "/exit"])

        class _Sess:
            def __init__(self, **_kw):
                pass

            def prompt(self, _p: str, **_kw):
                return next(lines)

        monkeypatch.setattr("strands_code_cli.loop.core.PromptSession", _Sess)
        printed: list[str] = []
        monkeypatch.setattr(
            "strands_code_cli.loop.core.print_plain",
            lambda _c, text, **_kw: printed.append(str(text)),
        )
        run_loop(
            agent, session_id="s1", index=index, model_id="anthropic/claude-sonnet-5-5"
        )
        # /approve must report no pending plan because /review did not arm it.
        assert any("No pending plan" in line for line in printed)
        assert gate.is_read_only(agent) is True
