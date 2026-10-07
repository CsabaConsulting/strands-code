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
import time
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

    def test_cancelled_waiter_discards_orphaned_request(self):
        # A waiter aborted before the pump polled must not leave its
        # request queued: the next turn's pump would serve the dead
        # worker's request as a phantom prompt.
        broker = ApprovalBroker()
        cancel = threading.Event()
        cancel.set()
        box: dict[str, Any] = {}
        with broker.pump(cancel):
            def worker():
                try:
                    broker.request(lambda: "unserved")
                except TurnCancelled:
                    box["aborted"] = True

            thread = threading.Thread(target=worker)
            thread.start()
            thread.join(timeout=5)
        assert box.get("aborted") is True
        assert broker.has_pending is False
        assert broker.poll(timeout=0.01) is None

    def test_discard_of_polled_request_is_noop(self):
        # Discard races the pump poll: an already-polled request has
        # nothing orphaned, and discarding a foreign request never raises.
        broker = ApprovalBroker()
        foreign = pg._ApprovalRequest(lambda: "x")
        broker.discard(foreign)  # never queued: no-op, no raise
        req = pg._ApprovalRequest(lambda: "y")
        broker._queue.put(req)
        assert broker.poll(timeout=0.5) is req
        broker.discard(req)  # already polled: no-op, no raise
        assert broker.has_pending is False

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
            def cancel_for(self, tag):
                return None

            def request(self, prompt, cancel=None):
                raise TurnCancelled()

        monkeypatch.setattr(pg, "_active_broker", lambda: _CancellingBroker())
        with pytest.raises(TurnCancelled):
            asyncio.run(
                handler.before_tool_call(
                    _event("shell", {"command": "make test"}, uid="u9")
                )
            )


# ---------------------------------------------------------------------------
# 07-02 task 2: per-request cancel domains + shared diff-store audit
# ---------------------------------------------------------------------------


class TestPerRequestCancel:
    def test_only_named_tag_aborts(self):
        # Distinct main/btw events; only the btw waiter aborts while the
        # main waiter still receives its served answer (T-07-06). The btw
        # event is pre-set so the outcome holds however the pump serves.
        broker = ApprovalBroker()
        pump_cancel = threading.Event()
        main_cancel = threading.Event()
        btw_cancel = threading.Event()
        btw_cancel.set()
        broker.register_cancel("main", main_cancel)
        broker.register_cancel("btw", btw_cancel)
        box: dict[str, str] = {}

        def main_worker():
            box["main"] = broker.request(lambda: "main-answer", broker.cancel_for("main"))

        def btw_worker():
            try:
                broker.request(lambda: "never", broker.cancel_for("btw"))
                box["btw"] = "answered?!"
            except TurnCancelled:
                box["btw"] = "cancelled"

        with broker.pump(pump_cancel):
            main_thread = threading.Thread(target=main_worker)
            btw_thread = threading.Thread(target=btw_worker)
            main_thread.start()
            btw_thread.start()
            while main_thread.is_alive() or btw_thread.is_alive():
                req = broker.poll(timeout=0.5)
                if req is not None:
                    req.run_prompt()
            main_thread.join(timeout=5)
            btw_thread.join(timeout=5)
        assert not main_thread.is_alive()
        assert not btw_thread.is_alive()
        assert box == {"main": "main-answer", "btw": "cancelled"}
        assert not main_cancel.is_set()
        assert not pump_cancel.is_set()

    def test_single_arg_request_uses_pump_cancel(self):
        # No registered tag, no cancel arg: the legacy pump path answers.
        broker = ApprovalBroker()
        cancel = threading.Event()
        box: dict[str, str] = {}

        def worker():
            box["answer"] = broker.request(lambda: "served")

        with broker.pump(cancel):
            thread = threading.Thread(target=worker)
            thread.start()
            while thread.is_alive():
                req = broker.poll(timeout=0.5)
                if req is not None:
                    req.run_prompt()
            thread.join(timeout=5)
        assert box["answer"] == "served"

    def test_cancel_registry_defaults_and_unregister(self):
        broker = ApprovalBroker()
        assert broker.cancel_for("main") is None
        event = threading.Event()
        broker.register_cancel("main", event)
        assert broker.cancel_for("main") is event
        broker.unregister_cancel("main")
        assert broker.cancel_for("main") is None
        broker.unregister_cancel("main")  # idempotent

    def test_ask_passes_tag_cancel_to_broker(self, monkeypatch):
        # The ask wires its own tag's event into the request.
        main_agent = SimpleNamespace(state={})
        classifier = PolicyClassifier(policy_loader=PolicyConfig.load)
        classifier.bind_main_agent(main_agent)
        broker = ApprovalBroker()
        main_cancel, btw_cancel = threading.Event(), threading.Event()
        broker.register_cancel("main", main_cancel)
        broker.register_cancel("btw", btw_cancel)
        seen: dict[str, Any] = {}
        real_request = broker.request

        def spy(prompt, cancel=None):
            seen["cancel"] = cancel
            return real_request(prompt, cancel=cancel)

        monkeypatch.setattr(broker, "request", spy)
        monkeypatch.setattr(pg, "_active_broker", lambda: broker)
        monkeypatch.setattr("builtins.input", lambda *args: "y")
        classifier(_event("shell", {"command": "make test"}, uid="b1"))
        assert classifier.ask("Approve?") == "y"
        assert seen["cancel"] is btw_cancel


class TestPendingStoreThreads:
    def test_ten_thread_hammer_loses_no_writes(self, tmp_path):
        from strands_code_cli.diff_gate import PendingStore

        store = PendingStore(tmp_path / "pending")
        errors: list[BaseException] = []

        def writer(n: int):
            try:
                for i in range(25):
                    store.stash(f"/tmp/f{n}-{i}.py", None, f"new-{n}-{i}", "write")
                    store.list()
            except BaseException as exc:  # noqa: BLE001 — collected, asserted below
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        assert not any(thread.is_alive() for thread in threads)
        assert errors == []
        assert len(store.list()) == 250


# ---------------------------------------------------------------------------
# 07-04 task 1: nesting-safe pump (G-7-1a)
# ---------------------------------------------------------------------------


class TestPumpNesting:
    def test_nested_turn_pump_exit_preserves_session_pump(self):
        # Turn pumps nest inside the session pump: exiting the turn
        # must not wipe the still-entered session pump — an idle side
        # approval then enqueues for the next turn instead of running
        # inline on the worker thread (where prompt_toolkit fails).
        broker = ApprovalBroker()
        session_cancel, turn_cancel = threading.Event(), threading.Event()
        with broker.pump(session_cancel):
            with broker.pump(turn_cancel):
                pass  # turn ends inside the session
            assert broker._pumping.is_set()  # entered state survives
            assert broker._cancel is session_cancel  # outer cancel restored
            box: dict[str, str] = {}

            def worker():
                box["answer"] = broker.request(lambda: "allow")

            thread = threading.Thread(target=worker)
            thread.start()

            def _waiting() -> bool:
                if not broker.has_pending:
                    return False
                served = broker.poll(timeout=2.0)
                assert served is not None
                served.run_prompt()
                return True

            deadline = time.monotonic() + 5.0
            while thread.is_alive() and time.monotonic() < deadline:
                if _waiting():
                    break
            thread.join(timeout=5)
            assert not thread.is_alive()
            assert box == {"answer": "allow"}
        assert not broker._pumping.is_set()  # full exit still clears

    def test_exception_inside_turn_pump_preserves_session_pump(self):
        # The finally path must preserve the session pump too: an
        # exception unwinding through the turn pump leaves the session
        # entered, the session cancel restored, and the depth sane.
        broker = ApprovalBroker()
        session_cancel, turn_cancel = threading.Event(), threading.Event()
        with broker.pump(session_cancel):
            with pytest.raises(RuntimeError, match="boom"):
                with broker.pump(turn_cancel):
                    raise RuntimeError("boom")
            assert broker._pumping.is_set()
            assert broker._cancel is session_cancel
            assert broker._depth == 1
            box: dict[str, str] = {}

            def worker():
                box["answer"] = broker.request(lambda: "allow")

            thread = threading.Thread(target=worker)
            thread.start()
            served = broker.poll(timeout=2.0)
            assert served is not None  # still enqueues, never inline
            served.run_prompt()
            thread.join(timeout=5)
            assert not thread.is_alive()
            assert box == {"answer": "allow"}
        assert not broker._pumping.is_set()
        assert broker._depth == 0

    def test_depth_counts_two_deep_and_clears_on_full_exit(self):
        # Depth bookkeeping: two-deep entry, one exit leaves depth 1
        # with the pump entered; the outer exit clears everything.
        broker = ApprovalBroker()
        assert broker._depth == 0
        session_pump = broker.pump(threading.Event())
        turn_pump = broker.pump(threading.Event())
        session_pump.__enter__()
        assert broker._depth == 1
        turn_pump.__enter__()
        assert broker._depth == 2
        turn_pump.__exit__(None, None, None)
        assert broker._depth == 1
        assert broker._pumping.is_set()
        session_pump.__exit__(None, None, None)
        assert broker._depth == 0
        assert not broker._pumping.is_set()
