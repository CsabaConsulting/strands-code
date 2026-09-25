"""Single-HITL gate tests + tracer spine evidence (TOOL-03, D-01..D-04, D-11, D-12).

Tracer observations (03-PLAN.md task 1):

- Single-HITL construction: ``HumanInTheLoop(allowed_tools=["read"],
  classifier=<stub>, ask=<stub>)`` constructs fine and passes through
  ``create_harness`` as ``interventions=[...]`` (kwargs assertion below,
  same mock-Agent pattern as ``test_tool_surface.py``). A second instance
  through ``resolve_interventions`` raises ``ValueError`` (handler-name
  collision ``strands:human-in-the-loop``) — proven by
  ``test_two_hitl_instances_collide``. Hence exactly one gate instance.
- Deny-continuation probe: NO live model turn was runnable in this
  environment (Bedrock credentials absent; ``preflight_credentials``
  stops before construction). Unit-level evidence instead: a deny
  verdict drives the real ``HumanInTheLoop.before_tool_call`` to a
  ``Confirm`` whose evaluate rejects (tool cancelled with a message the
  agent explains mid-turn and continues — D-02), while the user-visible
  refusal names the rule. Guide-action/steering fallback: NOT built; if
  a live turn ever shows identical-retry looping, add prompt steering
  per task 8(d).
- Liveness probes: ``web_fetch``/``web_search``/``programmatic_tool_caller``/
  ``subagent`` are all in the harness DEFAULT set
  (``strands_harness/agent.py`` docstring: shell/read/write/edit,
  web_fetch, web_search, programmatic_tool_caller, subagent) and every
  tool call fires ``before_tool_call``, so the gate sees them.
  ``web_fetch`` default transport is ``"curl"`` (sandboxed). The
  ``programmatic_tool_caller`` inner-call path (whether Monty-sandboxed
  inner tool calls re-fire ``before_tool_call``) is UNVERIFIABLE without
  a live model here → fail-closed decision: ``programmatic_tool_caller``
  is pinned ``False`` in the ``builtin_tools`` mapping (risk 9), with
  this docstring as the record. ``web_fetch``/``web_search`` stay live
  under built-in fetch-class allows (any host, D-16); ``subagent``
  inherits the gate and prompts per D-12.
- ``python_repl`` approval is all-or-nothing per execution: the prompt
  shows the code string (D-11), but approval does NOT imply
  file/network confinement inside the snippet (risk 5).

No ``code_agent.py`` prompt change: tracer saw no looping (no live turn
ran), so per task 8(d) that file is untouched.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import importlib

import pytest
from strands.interventions.actions import Confirm, Proceed
from strands.vended_interventions.hitl import HumanInTheLoop
from strands_harness.interventions import resolve_interventions

from strands_code_cli.policy import PolicyConfig, PolicyOptions, Rule
from strands_code_cli.policy_gate import (
    BatchState,
    PolicyClassifier,
    bind_main_agent,
    bind_turn,
    build_interventions,
    last_covered,
)

main_module = importlib.import_module("strands_code_cli.main")


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeAgent:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {}


def _event(name: str, tool_input: dict[str, Any], agent: Any = None, uid: str = "t1"):
    return SimpleNamespace(
        agent=agent if agent is not None else _FakeAgent(),
        tool_use={"name": name, "input": tool_input, "toolUseId": uid},
    )


def _gate(
    loader=None, answers: list[str] | None = None, monkeypatch=None, **kwargs
):
    classifier = PolicyClassifier(policy_loader=loader or PolicyConfig.load, **kwargs)
    handler = HumanInTheLoop(
        allowed_tools=["read", "search"], classifier=classifier, ask=classifier.ask
    )
    if answers is not None and monkeypatch is not None:
        it = iter(answers)
        monkeypatch.setattr("builtins.input", lambda _: next(it))
    return classifier, handler


def _run(handler, event):
    return asyncio.run(handler.before_tool_call(event))


# ---------------------------------------------------------------------------
# Tracer: single-HITL spine
# ---------------------------------------------------------------------------


class TestSingleHitlSpine:
    def test_single_hitl_constructs(self):
        gate = HumanInTheLoop(
            allowed_tools=["read"], classifier=lambda e: None, ask=lambda p: "y"
        )
        assert gate.name == "strands:human-in-the-loop"

    def test_two_hitl_instances_collide(self):
        one = HumanInTheLoop(allowed_tools=["read"])
        two = HumanInTheLoop(allowed_tools=["read"])
        with pytest.raises(ValueError):
            resolve_interventions([one, two])

    def test_interventions_reach_create_harness_as_single_hitl(self, tmp_path):
        with patch.object(main_module, "create_harness", return_value=MagicMock()) as factory:
            main_module.build_agent("test-session", tmp_path)
            kwargs = factory.call_args[1]
        interventions = kwargs["interventions"]
        assert isinstance(interventions, list) and len(interventions) == 1
        assert isinstance(interventions[0], HumanInTheLoop)

    def test_programmatic_tool_caller_pinned_off(self, tmp_path):
        with patch.object(main_module, "create_harness", return_value=MagicMock()) as factory:
            main_module.build_agent("test-session", tmp_path)
            mapping = factory.call_args[1]["builtin_tools"]
        # Risk 9: inner-call gating unverifiable without a live model → off.
        assert mapping["programmatic_tool_caller"] is False


# ---------------------------------------------------------------------------
# Gate layer: classifier + ask + batching + remember-me
# ---------------------------------------------------------------------------


class TestGateLayer:
    def test_allow_silent_no_prompt(self, monkeypatch):
        _, handler = _gate(monkeypatch=monkeypatch, answers=[])
        monkeypatch.setattr(
            "builtins.input", lambda _: (_ for _ in ()).throw(AssertionError("must not prompt"))
        )
        result = _run(handler, _event("read", {"path": "/x"}))
        assert isinstance(result, Proceed)

    def test_prompt_once_per_rule_per_turn(self, monkeypatch):
        _, handler = _gate(monkeypatch=monkeypatch, answers=["y"])
        first = _run(handler, _event("shell", {"command": "make test"}, uid="u1"))
        assert isinstance(first, Confirm)
        assert first.evaluate("y") is True
        second = _run(handler, _event("shell", {"command": "make test"}, uid="u2"))
        assert isinstance(second, Proceed)

    def test_batch_resets_next_turn(self, monkeypatch):
        classifier, handler = _gate(monkeypatch=monkeypatch, answers=["y", "y"])
        assert isinstance(_run(handler, _event("shell", {"command": "make test"}, uid="u1")), Confirm)
        classifier.batch.bind_turn("turn-2")
        assert isinstance(_run(handler, _event("shell", {"command": "make test"}, uid="u3")), Confirm)

    def test_deny_short_circuits_naming_rule(self, monkeypatch):
        def loader():
            return PolicyConfig(deny=[Rule(tool="shell", command="curl")])

        shown: list[str] = []
        monkeypatch.setattr("builtins.print", lambda *a, **k: shown.append(" ".join(map(str, a))))
        _, handler = _gate(loader=loader, monkeypatch=monkeypatch, answers=[])
        monkeypatch.setattr(
            "builtins.input", lambda _: (_ for _ in ()).throw(AssertionError("deny must not prompt"))
        )
        result = _run(handler, _event("shell", {"command": "curl http://x"}, uid="u9"))
        assert isinstance(result, Confirm)
        assert result.evaluate("n") is False
        # Deny reason reaches the model-side prompt AND the user-visible refusal.
        assert "curl" in result.prompt
        assert any("Denied by policy rule" in line and "curl" in line for line in shown)

    def test_always_appends_narrow_rule(self, tmp_path, monkeypatch):
        repo = tmp_path / "policy.toml"
        missing = tmp_path / "missing.toml"

        def loader():
            return PolicyConfig.load(home_path=missing, repo_path=repo)

        classifier = PolicyClassifier(policy_loader=loader, append_path=repo)
        handler = HumanInTheLoop(
            allowed_tools=["read", "search"], classifier=classifier, ask=classifier.ask
        )
        monkeypatch.setattr("builtins.input", lambda _: "always")
        result = _run(handler, _event("shell", {"command": "git status"}, uid="u1"))
        assert isinstance(result, Confirm)
        reloaded = PolicyConfig.load(home_path=missing, repo_path=repo)
        assert len(reloaded.allow) == 1
        assert reloaded.allow[0].tool == "shell"
        assert reloaded.allow[0].command == "git status"
        # Next identical action proceeds silently (fresh loader sees the rule).
        monkeypatch.setattr(
            "builtins.input", lambda _: (_ for _ in ()).throw(AssertionError("must not prompt"))
        )
        second = _run(handler, _event("shell", {"command": "git status --short"}, uid="u2"))
        assert isinstance(second, Proceed)

    def test_never_appends_deny_rule(self, tmp_path, monkeypatch):
        repo = tmp_path / "policy.toml"
        missing = tmp_path / "missing.toml"
        classifier = PolicyClassifier(
            policy_loader=lambda: PolicyConfig.load(home_path=missing, repo_path=repo),
            append_path=repo,
        )
        handler = HumanInTheLoop(
            allowed_tools=["read", "search"], classifier=classifier, ask=classifier.ask
        )
        monkeypatch.setattr("builtins.input", lambda _: "never")
        result = _run(handler, _event("shell", {"command": "make test"}, uid="u1"))
        assert isinstance(result, Confirm)
        assert result.evaluate("n") is False
        reloaded = PolicyConfig.load(home_path=missing, repo_path=repo)
        assert len(reloaded.deny) == 1

    def test_trust_delegated_skips_only_non_main_agent(self):
        main_agent, child_agent = _FakeAgent(), _FakeAgent()
        classifier = PolicyClassifier(
            policy_loader=lambda: PolicyConfig(
                options=PolicyOptions(trust_delegated=True)
            )
        )
        classifier.bind_main_agent(main_agent)
        handler = HumanInTheLoop(
            allowed_tools=["read", "search"], classifier=classifier, ask=classifier.ask
        )
        assert isinstance(
            _run(handler, _event("shell", {"command": "make test"}, child_agent, "u1")), Proceed
        )
        assert isinstance(
            _run(handler, _event("shell", {"command": "make test"}, main_agent, "u2")), Confirm
        )

    def test_delegate_prompts_by_default(self, monkeypatch):
        _, handler = _gate(monkeypatch=monkeypatch, answers=["y"])
        result = _run(handler, _event("shell", {"command": "make test"}, _FakeAgent(), "u1"))
        assert isinstance(result, Confirm)

    def test_unbound_agent_prompts_fail_closed(self, monkeypatch):
        classifier = PolicyClassifier(
            policy_loader=lambda: PolicyConfig(
                options=PolicyOptions(trust_delegated=True)
            )
        )
        handler = HumanInTheLoop(
            allowed_tools=["read", "search"], classifier=classifier, ask=classifier.ask
        )
        monkeypatch.setattr("builtins.input", lambda _: "n")
        result = _run(handler, _event("shell", {"command": "make test"}, _FakeAgent(), "u1"))
        assert isinstance(result, Confirm)

    def test_ask_error_returns_deny(self, monkeypatch):
        classifier, _ = _gate(monkeypatch=monkeypatch, answers=[])
        classifier(
            _event("shell", {"command": "make test"})
        )  # stash last-decision context
        monkeypatch.setattr(
            "builtins.input", lambda _: (_ for _ in ()).throw(RuntimeError("tty gone"))
        )
        assert classifier.ask("Approve?") == "n"


# ---------------------------------------------------------------------------
# Task 8: python_repl gating + delegated e2e + deny messaging
# ---------------------------------------------------------------------------


class TestReplAndDelegation:
    def test_repl_prompted_with_code(self, monkeypatch):
        _, handler = _gate(monkeypatch=monkeypatch, answers=["n"])
        result = _run(
            handler, _event("python_repl", {"code": "import socket\nprint(1)"}, uid="r1")
        )
        assert isinstance(result, Confirm)
        assert result.evaluate("n") is False

    def test_subagent_call_prompts(self, monkeypatch):
        _, handler = _gate(monkeypatch=monkeypatch, answers=["n"])
        result = _run(handler, _event("subagent", {"task": "do it"}, uid="s1"))
        assert isinstance(result, Confirm)

    def test_deny_reason_propagates(self, monkeypatch):
        def loader():
            return PolicyConfig(deny=[Rule(tool="shell", command="curl")])

        _, handler = _gate(loader=loader, monkeypatch=monkeypatch, answers=[])
        monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(AssertionError()))
        result = _run(handler, _event("shell", {"command": "curl http://x"}, uid="d1"))
        assert isinstance(result, Confirm)
        assert "DENY" in result.prompt and "curl" in result.prompt


# ---------------------------------------------------------------------------
# Module-level bind helpers
# ---------------------------------------------------------------------------


class TestBindHelpers:
    def test_bind_turn_and_last_covered(self, monkeypatch):
        build_interventions()
        bind_turn("t-1")
        import strands_code_cli.policy_gate as gate_module

        classifier = gate_module._ACTIVE["classifier"]
        assert isinstance(classifier, PolicyClassifier)
        monkeypatch.setattr("builtins.input", lambda _: "y")
        classifier(_event("shell", {"command": "make test"}))
        classifier.ask("Approve?")
        assert last_covered() != []
        bind_turn("t-2")
        assert classifier.batch.is_covered(("prompt", "shell", "Shell command: make test")) is False

    def test_bind_main_agent_noop_without_crash(self):
        bind_main_agent(object())
