"""Pump cancel path: ack-before-join ordering (G-7-2 F-3).

Cancelling with the dual pump up must acknowledge immediately: the
pool-exit join waits out the current step (a sync tool runs to
completion), and with no pre-join line a mid-tool cancel looks exactly
like the main task finishing naturally.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

import strands_code_cli.loop as loop_mod
import strands_code_cli.policy_gate as pg
from strands_code_cli.btw import BtwContext, BtwQueue
from strands_code_cli.loop import CANCEL_FIRST_PRESS, _invoke_agent
from strands_code_cli.policy_gate import ApprovalBroker


class _SlowMain:
    """Main double ignoring cancel: one slow sync step, then done."""

    def __init__(self, order: list[str]) -> None:
        self.order = order

    def __call__(self, text: str, **kwargs: Any) -> str:
        time.sleep(0.3)  # a sync tool step runs to completion
        self.order.append("worker-done")
        return "main-result"


class TestAckBeforeJoin:
    def test_pump_cancel_ack_prints_before_join(self, monkeypatch, capsys):
        broker = ApprovalBroker()
        monkeypatch.setitem(pg._ACTIVE, "broker", broker)
        order: list[str] = []
        real_print_plain = loop_mod.print_plain

        def spy_print(console, text, **kwargs):
            if text == CANCEL_FIRST_PRESS:
                order.append("ack")
            return real_print_plain(console, text, **kwargs)

        monkeypatch.setattr(loop_mod, "print_plain", spy_print)
        real_poll = broker.poll
        calls = {"n": 0}

        def raising_poll(timeout: float = 0.05):
            calls["n"] += 1
            if calls["n"] == 1:
                raise KeyboardInterrupt()  # Ctrl-C lands in the dialog
            return real_poll(timeout=timeout)

        monkeypatch.setattr(broker, "poll", raising_poll)
        btw = BtwContext(
            spawn_queue=BtwQueue(),
            build=lambda question: (None, []),
            cancel_event=threading.Event(),
            pending=[],
        )
        with pytest.raises(KeyboardInterrupt):
            _invoke_agent(_SlowMain(order), "do the thing", threading.Event(), btw=btw)
        assert order == ["ack", "worker-done"]
        assert CANCEL_FIRST_PRESS in capsys.readouterr().out
