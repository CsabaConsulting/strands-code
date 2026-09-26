"""Approval broker: main-thread prompts, worker abort, deny re-prompt (GATE-02).

The SDK invokes ``ask`` in its event-loop worker thread, where blocking on
stdin parks the worker on Ctrl-C (double-Ctrl-C wedge) and ``asyncio.run``
cannot nest (dialog crash). The broker hands prompts to the pump thread;
these tests pin the handoff, the cancel abort, and the fail-closed
deny-never-covers rule.
"""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from typing import Any

import pytest
from strands.vended_interventions.hitl import HumanInTheLoop
from strands.interventions.actions import Confirm, Proceed

import strands_code_cli.policy_gate as pg
from strands_code_cli.loop import _invoke_agent
from strands_code_cli.policy import PolicyConfig
from strands_code_cli.policy_gate import ApprovalBroker, PolicyClassifier, TurnCancelled


def _event(name: str, tool_input: dict[str, Any], uid: str = "t1"):
    return SimpleNamespace(
        agent=SimpleNamespace(state={}),
        tool_use={"name": name, "input": tool_input, "toolUseId": uid},
    )


class TestBrokerHandoff:
    def test_request_inline_without_pump(self):
        broker = ApprovalBroker()
        assert broker.request(lambda: "y") == "y"

    def test_request_inline_on_pump_thread(self):
        # The pump thread itself must never queue (deadlock insurance).
        broker = ApprovalBroker()
        with broker.pump(threading.Event()):
            assert broker.request(lambda: "inline") == "inline"

    def test_pump_serves_worker_in_main_thread(self):
        broker = ApprovalBroker()
        cancel = threading.Event()
        box: dict[str, Any] = {}
        main_ident = threading.get_ident()

        def _main_only_prompt():
            box["prompt_ident"] = threading.get_ident()
            return "from-main"

        def worker():
            try:
                box["answer"] = broker.request(_main_only_prompt)
            except TurnCancelled:
                box["answer"] = "CANCELLED"

        thread = threading.Thread(target=worker)
        with broker.pump(cancel):
            thread.start()
            while thread.is_alive():
                req = broker.poll(timeout=0.5)
                if req is None:
                    continue
                req.run_prompt()
            thread.join(timeout=5)
        assert not thread.is_alive()
        assert box["answer"] == "from-main"
        assert box["prompt_ident"] == main_ident

    def test_worker_aborts_on_cancel(self):
        broker = ApprovalBroker()
        cancel = threading.Event()
        cancel.set()
        box: dict[str, Any] = {}
        with broker.pump(cancel):
            def worker():
                try:
                    broker.request(lambda: (_ for _ in ()).throw(AssertionError("unserved")))
                except TurnCancelled:
                    box["aborted"] = True

            thread = threading.Thread(target=worker)
            thread.start()
            thread.join(timeout=5)
        assert box.get("aborted") is True

    def test_pump_death_without_answer_is_cancel_not_assert(self):
        # Ctrl-C inside the dialog raises in the pump thread while
        # prompt_toolkit owns SIGINT, so the turn handler never sets
        # cancel — yet the worker must see cancellation, not a bare
        # assert (whose empty message surfaced as a blank "failed
        # closed" line followed by a spurious CONFIRMATION_FAILED).
        req = pg._ApprovalRequest(lambda: (_ for _ in ()).throw(KeyboardInterrupt()))
        with pytest.raises(KeyboardInterrupt):
            req.run_prompt()
        with pytest.raises(TurnCancelled):
            req.wait_answer(threading.Event())

    def test_ctrl_c_in_prompt_aborts_worker_cleanly(self):
        broker = ApprovalBroker()
        cancel = threading.Event()
        box: dict[str, Any] = {}

        def worker():
            try:
                broker.request(lambda: "never-served")
                box["outcome"] = "answered"
            except TurnCancelled:
                box["outcome"] = "cancelled"
            except BaseException as exc:  # noqa: BLE001 — must not be anything else
                box["outcome"] = f"wrong:{type(exc).__name__}"

        def dying_prompt():
            raise KeyboardInterrupt()  # dialog Ctrl-C: no answer, cancel unset

        thread = threading.Thread(target=worker)
        with broker.pump(cancel):
            thread.start()
            req = None
            while req is None:
                req = broker.poll(timeout=0.5)
            with pytest.raises(KeyboardInterrupt):
                req._prompt = dying_prompt
                req.run_prompt()
            thread.join(timeout=5)
        assert box.get("outcome") == "cancelled"


class TestInvokeAgentPump:
    def test_agent_turn_served_with_cancel_kwarg(self, monkeypatch):
        broker = ApprovalBroker()
        monkeypatch.setitem(pg._ACTIVE, "broker", broker)
        cancel = threading.Event()
        main_ident = threading.get_ident()
        seen: dict[str, Any] = {}

        class PumpAgent:
            cancel_signal = True

            def __call__(self, text, **kwargs):
                seen["kwargs"] = kwargs

                def prompt():
                    seen["prompt_ident"] = threading.get_ident()
                    return "y"

                seen["answer"] = broker.request(prompt)

        _invoke_agent(PumpAgent(), "do it", cancel)
        assert seen["answer"] == "y"
        assert seen["prompt_ident"] == main_ident
        assert seen["kwargs"] == {"cancel_signal": cancel}


class TestDenyFailClosed:
    def _handler(self, monkeypatch, answers):
        it = iter(answers)
        monkeypatch.setattr("builtins.input", lambda *args: next(it))
        classifier = PolicyClassifier(policy_loader=PolicyConfig.load)
        handler = HumanInTheLoop(
            allowed_tools=["read", "search"], classifier=classifier, ask=classifier.ask
        )
        return handler

    def test_deny_retry_reprompts(self, monkeypatch):
        handler = self._handler(monkeypatch, ["n", "n"])
        first = asyncio.run(
            handler.before_tool_call(_event("shell", {"command": "make test"}, uid="u1"))
        )
        assert isinstance(first, Confirm)
        assert first.evaluate("n") is False
        second = asyncio.run(
            handler.before_tool_call(_event("shell", {"command": "make test"}, uid="u2"))
        )
        assert isinstance(second, Confirm)  # not Proceed: denials never cover
        assert second.evaluate("n") is False

    def test_approve_retry_stays_silent(self, monkeypatch):
        handler = self._handler(monkeypatch, ["y"])
        first = asyncio.run(
            handler.before_tool_call(_event("shell", {"command": "make test"}, uid="u1"))
        )
        assert isinstance(first, Confirm)
        second = asyncio.run(
            handler.before_tool_call(_event("shell", {"command": "make test"}, uid="u2"))
        )
        assert isinstance(second, Proceed)

    def test_turn_cancelled_not_swallowed(self, monkeypatch):
        handler = self._handler(monkeypatch, [])

        class _CancellingBroker:
            def request(self, prompt):
                raise TurnCancelled()

        monkeypatch.setattr(pg, "_active_broker", lambda: _CancellingBroker())
        with pytest.raises(TurnCancelled):
            asyncio.run(
                handler.before_tool_call(
                    _event("shell", {"command": "make test"}, uid="u9")
                )
            )
