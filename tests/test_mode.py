"""Phase 4 tracer + Plan/Act mode tests (MODE-01, MODE-02; replay model only).

Tracer observations (04-PLAN.md task 1, all offline, no live Bedrock):

- Hook order (SDK inspection + live registry dispatch): the HITL
  intervention dispatcher registers its ``BeforeToolCallEvent`` handler
  at ``HookOrder.INTERVENTION_INPUT`` (90)
  (``strands/interventions/registry.py`` ``_register_hooks``); lower
  order values run first (``HookRegistry.get_callbacks_for``:
  priority order, registration order inside a priority). The steering
  hook registers at ``HookOrder.SDK_FIRST`` (-100), so it always sees
  the boundary first. PROVEN live below: with pending steering, the
  dispatched event carries the redirect ``cancel_tool`` and yields zero
  interrupts (no approval prompt), because the classifier consumes the
  hook-armed ``toolUseId`` as skip-prompt while the executor still
  cancels the call.
- Intervention-dispatcher gap (code read): ``_on_before_tool_call``
  does NOT check ``event.cancel_tool`` before running handlers, so
  order alone cannot skip the prompt — the arm/consume fallback (plan
  resolved item 12) is REQUIRED, not optional, and is what the test
  pins. Without the bound steering slot the same dispatch raises an
  approval interrupt.
- SIGINT surface: during the synchronous turn no prompt app runs
  (``loop.py`` ``agent(text)`` inside ``output_context``), so SIGINT
  surfaces as ``KeyboardInterrupt`` in the main thread at the turn
  site; the loop converts it via the two-press state machine (see
  ``test_plan_cancel.py``). Ctrl-C inside an open gate prompt never
  reaches the loop — the ask broad-except denies that tool (pinned by
  Phase 3 ``test_ask_error_returns_deny`` shape).
- Readline/input shape: the v1 reader does select+read on the stdin fd
  (temporarily nonblocking) instead of blocking ``readline`` so the
  turn-end join is prompt and no parked reader survives into the next
  idle prompt (T-04-12). Echo uses plain ``print`` rather than a nested
  ``output_context``: re-swapping the global ``sys.stdout`` proxy from
  a second thread would corrupt the turn's active proxy on restore;
  the turn holds ``output_context`` open while the reader runs, so the
  echo still lands in the transcript.

Invariants pinned here: exactly one HumanInTheLoop (no second
handler); all Plan reasons use mode vocabulary only.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from strands.interventions.actions import Confirm, Proceed
from strands.vended_interventions.hitl import HumanInTheLoop

from strands_code_cli.mode import (
    APPROVE_EMPTY,
    APPROVE_OK,
    MODE_ACT_REPLY,
    MODE_PLAN_REPLY,
    MODE_USAGE,
    PLAN_PREFIX,
    ModeState,
)
from strands_code_cli.policy import PolicyConfig, PolicyOptions
from strands_code_cli.policy_gate import PolicyClassifier
from strands_code_cli.router import USAGE_HINT, dispatch
from strands_code_cli.steering import SteeringState, make_steering_hook
from strands_code_cli.session_index import SessionIndex


BANNED_VOCAB = (
    "policy rule",
    "rule [",
    "approve-each",
    "on-demand",
    "auto",
    "/diff",
    "yolo",
)


class _FakeAgent:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {}


def _event(name: str, tool_input: dict[str, Any], agent: Any = None, uid: str = "t1"):
    return SimpleNamespace(
        agent=agent if agent is not None else _FakeAgent(),
        tool_use={"name": name, "input": tool_input, "toolUseId": uid},
    )


def _plan_classifier(**kwargs: Any) -> PolicyClassifier:
    classifier = PolicyClassifier(
        policy_loader=lambda: PolicyConfig(), **kwargs
    )
    classifier.set_mode("plan")
    return classifier


# ----------------------------------------------------------------------
# Tracer (a): classifier Plan-deny, above trust_delegated
# ----------------------------------------------------------------------


class TestTracerPlanDeny:
    @pytest.mark.parametrize("tool", ["write", "edit", "shell", "python_repl"])
    def test_plan_denies_mutations_with_mode_vocabulary(self, tool):
        classifier = _plan_classifier()
        result = classifier(_event(tool, {"path": "/x"} if tool in ("write", "edit") else {}))
        assert result.requires_human_in_the_loop is True
        assert "Plan mode is read-only" in result.reason
        for banned in BANNED_VOCAB:
            assert banned not in result.reason

    @pytest.mark.parametrize("tool", ["read", "search"])
    def test_plan_allows_reads(self, tool):
        classifier = _plan_classifier()
        result = classifier(_event(tool, {"path": "/x"} if tool == "read" else {}))
        assert result.requires_human_in_the_loop is False

    def test_plan_deny_above_trust_delegated(self):
        main_agent, child_agent = _FakeAgent(), _FakeAgent()
        classifier = PolicyClassifier(
            policy_loader=lambda: PolicyConfig(
                options=PolicyOptions(trust_delegated=True)
            )
        )
        classifier.bind_main_agent(main_agent)
        classifier.set_mode("plan")
        # Delegated + trusted would Proceed in Act — still denied in Plan.
        result = classifier(_event("shell", {"command": "make test"}, child_agent, "u1"))
        assert result.requires_human_in_the_loop is True
        assert "Plan mode is read-only" in result.reason

    def test_plan_deny_repeated_identical_call_still_denied(self):
        classifier = _plan_classifier()
        first = classifier(_event("write", {"path": "/x"}, uid="u1"))
        second = classifier(_event("write", {"path": "/x"}, uid="u2"))
        assert first.requires_human_in_the_loop is True
        assert second.requires_human_in_the_loop is True

    def test_act_mode_unaffected_by_flag(self, monkeypatch):
        classifier = PolicyClassifier(policy_loader=lambda: PolicyConfig())
        classifier.set_mode("act")
        _, handler = classifier, HumanInTheLoop(
            allowed_tools=["read", "search"], classifier=classifier, ask=classifier.ask
        )
        monkeypatch.setattr("builtins.input", lambda _: "n")
        result = asyncio.run(handler.before_tool_call(_event("shell", {"command": "x"})))
        assert isinstance(result, Confirm)

    def test_plan_ask_refusal_uses_mode_vocabulary(self, monkeypatch):
        classifier = _plan_classifier()
        classifier(_event("write", {"path": "/x"}))
        shown: list[str] = []
        monkeypatch.setattr("builtins.print", lambda *a, **k: shown.append(" ".join(map(str, a))))
        monkeypatch.setattr(
            "builtins.input",
            lambda _: (_ for _ in ()).throw(AssertionError("Plan deny must not prompt")),
        )
        assert classifier.ask("Approve?") == "n"
        text = "\n".join(shown)
        assert "Plan mode is read-only" in text
        for banned in BANNED_VOCAB:
            assert banned not in text

    def test_set_mode_rejects_third_mode(self):
        classifier = PolicyClassifier(policy_loader=lambda: PolicyConfig())
        with pytest.raises(ValueError):
            classifier.set_mode("yolo")


# ----------------------------------------------------------------------
# Tracer (b)+(c): hook order + steering redirect on a live registry
# ----------------------------------------------------------------------


class TestTracerHookOrder:
    def _wired_agent(self, model_text: str = "ok"):
        from strands_code_cli.main import build_agent
        from strands_code_cli.policy_gate import _active_classifier
        from tests.test_kill_resume import _ReplayModel

        import tempfile, uuid
        from pathlib import Path

        session_dir = Path(tempfile.mkdtemp())
        agent = build_agent(str(uuid.uuid4()), session_dir, model=_ReplayModel(model_text))
        return agent, _active_classifier()

    def test_steering_hook_before_prompt_with_redirect(self):
        from strands.hooks.events import BeforeToolCallEvent

        agent, classifier = self._wired_agent()
        assert classifier is not None
        slot = getattr(agent, "_steering_slot", None)
        assert slot is not None and slot.state is None  # fresh until a turn binds
        state = SteeringState()
        state.bind_turn("turn-1")
        slot.state = state
        state.note("use poetry instead")
        event = BeforeToolCallEvent(
            agent=agent,
            selected_tool=None,
            tool_use={"name": "shell", "input": {"command": "pip install x"}, "toolUseId": "ord-1"},
            invocation_state={},
        )
        _, interrupts = asyncio.run(agent.hooks.invoke_callbacks_async(event))
        # Redirect armed by the hook AND no approval interrupt raised:
        # the steering-cancelled call skips the HITL prompt.
        assert "Steering redirected by user: use poetry instead" in str(event.cancel_tool)
        assert "the skipped call was not executed" in str(event.cancel_tool)
        assert interrupts == []
        assert not state.has_pending()  # one-shot consumption

    def test_no_steering_no_cancel_no_interrupt_for_allowlisted(self):
        from strands.hooks.events import BeforeToolCallEvent

        agent, _ = self._wired_agent()
        slot = getattr(agent, "_steering_slot", None)
        state = SteeringState()
        state.bind_turn("turn-1")
        slot.state = state
        event = BeforeToolCallEvent(
            agent=agent,
            selected_tool=None,
            tool_use={"name": "read", "input": {"path": "/x"}, "toolUseId": "ord-2"},
            invocation_state={},
        )
        _, interrupts = asyncio.run(agent.hooks.invoke_callbacks_async(event))
        assert not event.cancel_tool
        assert interrupts == []

    def test_hook_unit_redirect_and_clear(self):
        state = SteeringState()
        state.note("skip this step")
        hook = make_steering_hook(state)
        event = SimpleNamespace(
            tool_use={"name": "write", "input": {}, "toolUseId": "u9"}, cancel_tool=False
        )
        hook(event)
        assert "skip this step" in event.cancel_tool
        assert not state.has_pending()

    def test_hook_unit_noop_when_empty_and_never_invokes_agent(self):
        state = SteeringState()
        hook = make_steering_hook(state)
        seen: list[str] = []

        class _Agent:
            def __call__(self, text: str) -> None:
                seen.append(text)

        event = SimpleNamespace(
            agent=_Agent(), tool_use={"name": "read", "input": {}, "toolUseId": "u1"},
            cancel_tool=False,
        )
        hook(event)
        assert event.cancel_tool is False
        assert seen == []


# ----------------------------------------------------------------------
# Mode state + router
# ----------------------------------------------------------------------


class TestModeState:
    def test_default_act(self):
        assert ModeState().mode == "act"

    def test_rejects_third_mode(self):
        with pytest.raises(ValueError):
            ModeState("yolo")
        with pytest.raises(ValueError):
            ModeState().set("auto")

    def test_switch_announces_and_sticks(self):
        mode = ModeState()
        assert mode.set("plan") == MODE_PLAN_REPLY
        assert mode.mode == "plan"
        assert mode.announce() == MODE_PLAN_REPLY
        assert mode.set("act") == MODE_ACT_REPLY
        assert mode.mode == "act"

    def test_approve_without_plan_guides(self):
        assert ModeState().approve() == APPROVE_EMPTY

    def test_approve_with_plan_flips_to_act(self):
        mode = ModeState()
        mode.set("plan")
        mode.note_plan_proposed()
        assert mode.approve() == APPROVE_OK
        assert mode.mode == "act"
        assert not mode.pending_plan

    def test_mode_switch_clears_pending(self):
        mode = ModeState()
        mode.set("plan")
        mode.note_plan_proposed()
        mode.set("act")
        assert mode.approve() == APPROVE_EMPTY


class TestRouterMode:
    def _dispatch(self, text: str, tmp_path, mode=None):  # type: ignore[no-untyped-def]
        index = SessionIndex(tmp_path / "index")
        return dispatch(text, session_id="s", index=index, mode=mode)

    def test_mode_bare_reports_current(self, tmp_path):
        mode = ModeState()
        assert self._dispatch("/mode", tmp_path, mode) == ("reply", MODE_ACT_REPLY)
        mode.set("plan")
        assert self._dispatch("/mode", tmp_path, mode) == ("reply", MODE_PLAN_REPLY)

    def test_mode_switch_reply_only_and_sticky(self, tmp_path):
        mode = ModeState()
        assert self._dispatch("/mode plan", tmp_path, mode) == ("reply", MODE_PLAN_REPLY)
        assert mode.mode == "plan"
        assert self._dispatch("/mode act", tmp_path, mode) == ("reply", MODE_ACT_REPLY)
        assert mode.mode == "act"

    def test_mode_bogus_usage_never_agent_turn(self, tmp_path):
        mode = ModeState()
        action, message = self._dispatch("/mode turbo", tmp_path, mode)
        assert action == "reply"
        assert message == MODE_USAGE
        assert mode.mode == "act"

    def test_approve_without_plan_guidance(self, tmp_path):
        mode = ModeState()
        mode.set("plan")
        assert self._dispatch("/approve", tmp_path, mode) == ("reply", APPROVE_EMPTY)
        assert mode.mode == "plan"

    def test_approve_with_plan_hands_off(self, tmp_path):
        from strands_code_cli.mode import APPROVE_EXECUTE

        mode = ModeState()
        mode.set("plan")
        mode.note_plan_proposed()
        action, message = self._dispatch("/approve", tmp_path, mode)
        assert action == "agent"
        assert APPROVE_OK in message
        assert APPROVE_EXECUTE in message
        assert mode.mode == "act"

    def test_approve_without_holder_guides(self, tmp_path):
        assert self._dispatch("/approve", tmp_path, None) == ("reply", APPROVE_EMPTY)

    def test_plain_text_still_agent_turn_revise_replans(self, tmp_path):
        mode = ModeState()
        mode.set("plan")
        mode.note_plan_proposed()
        assert self._dispatch("actually use sqlite", tmp_path, mode) == ("agent", None)

    def test_usage_hint_lists_mode_commands(self):
        assert "/mode [plan|act]" in USAGE_HINT
        assert "/approve" in USAGE_HINT


class TestPlanPrefix:
    def test_step_list_shape(self):
        assert "Files to touch:" in PLAN_PREFIX
        assert "Commands to run:" in PLAN_PREFIX
        assert "Reply with revisions in plain words, or /approve to execute." in PLAN_PREFIX

    def test_prefix_vocabulary_lock(self):
        from strands_code_cli.mode import APPROVE_EXECUTE

        for copy in (PLAN_PREFIX, APPROVE_EXECUTE):
            lowered = copy.lower()
            for banned in ("policy", "approve-each", "on-demand", "auto", "yolo"):
                assert banned not in lowered


# ----------------------------------------------------------------------
# Wiring: single HITL + steering hook + classifier setter (task 6)
# ----------------------------------------------------------------------


class TestWiring:
    def test_build_agent_single_hitl_hook_and_mode(self, tmp_path, monkeypatch):
        import uuid

        import importlib

        main_module = importlib.import_module("strands_code_cli.main")
        from strands_code_cli.policy_gate import _active_classifier
        from tests.test_kill_resume import _ReplayModel

        captured: dict[str, Any] = {}
        real_factory = main_module.create_harness

        def _spy(**kwargs: Any):
            captured.update(kwargs)
            return real_factory(**kwargs)

        monkeypatch.setattr(main_module, "create_harness", _spy)
        agent = main_module.build_agent(str(uuid.uuid4()), tmp_path, model=_ReplayModel("hi"))
        assert len(captured["interventions"]) == 1
        assert captured["builtin_tools"]["programmatic_tool_caller"] is False
        assert agent.hooks.has_callbacks()
        assert getattr(agent, "_steering_slot", None) is not None
        classifier = _active_classifier()
        assert classifier is not None
        classifier.set_mode("plan")  # setter reachable through the built gate
        classifier.set_mode("act")
