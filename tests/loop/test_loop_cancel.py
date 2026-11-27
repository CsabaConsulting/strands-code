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

import strands_code_cli.loop.pump as pump_mod
from strands_code_cli.loop.btw import BtwContext, BtwQueue
from strands_code_cli.loop.core import CANCEL_FIRST_PRESS, _invoke_agent
from strands_code_cli.policy.policy_gate import ApprovalBroker


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
        order: list[str] = []
        real_print_plain = pump_mod.print_plain

        def spy_print(console, text, **kwargs):
            if text == CANCEL_FIRST_PRESS:
                order.append("ack")
            return real_print_plain(console, text, **kwargs)

        monkeypatch.setattr(pump_mod, "print_plain", spy_print)
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
            main_agent = _SlowMain(order)
            main_agent._approval_broker = broker
            _invoke_agent(main_agent, "do the thing", threading.Event(), btw=btw)
        assert order == ["ack", "worker-done"]
        assert CANCEL_FIRST_PRESS in capsys.readouterr().out


class TestBackgroundCancelAndShutdown:
    """D-08: Ctrl-C and session exit cancel background tasks and shut down agent."""

    def test_handle_turn_cancel_cancels_background_only_for_main_target(self, tmp_path):
        from strands_code_cli.loop.core import _handle_turn_cancel
        from strands_code_cli.session.session_index import SessionIndex

        calls: list[bool] = []

        class _Agent:
            messages: list = []

            def cancel(self, *, cancel_background_tasks: bool = False) -> None:
                calls.append(cancel_background_tasks)

        agent = _Agent()
        index = SessionIndex(tmp_path / "index")
        sid = index.mint()
        _handle_turn_cancel(agent, sid, index, threading.Event(), None, target="btw")
        assert calls == []
        _handle_turn_cancel(agent, sid, index, threading.Event(), None, target="main")
        assert calls == [True]

    def test_pump_interrupt_cancels_background_tasks(self, monkeypatch):
        from strands_code_cli.policy.policy_gate import ApprovalBroker

        broker = ApprovalBroker()
        real_poll = broker.poll
        calls_poll = {"n": 0}
        cancel_calls: list[bool] = []

        class _Agent:
            def __call__(self, text: str, **kwargs: Any) -> str:
                time.sleep(0.2)
                return "ok"

            def cancel(self, *, cancel_background_tasks: bool = False) -> None:
                cancel_calls.append(cancel_background_tasks)

        def raising_poll(timeout: float = 0.05):
            calls_poll["n"] += 1
            if calls_poll["n"] == 1:
                raise KeyboardInterrupt()
            return real_poll(timeout=timeout)

        monkeypatch.setattr(broker, "poll", raising_poll)
        agent = _Agent()
        agent._approval_broker = broker
        btw = BtwContext(
            spawn_queue=BtwQueue(),
            build=lambda question: (None, []),
            cancel_event=threading.Event(),
            pending=[],
        )
        with pytest.raises(KeyboardInterrupt):
            _invoke_agent(agent, "task", threading.Event(), btw=btw)
        assert cancel_calls == [True]

    def test_close_loop_session_cancels_background_flushes_and_shuts_down(
        self, tmp_path, monkeypatch
    ):
        from concurrent.futures import ThreadPoolExecutor

        import strands_code_cli.loop.core as loop_mod
        from strands_code_cli.session.session_index import SessionIndex

        events: list[Any] = []

        class _Agent:
            messages: list = []

            def cancel(self, *, cancel_background_tasks: bool = False) -> None:
                events.append(("cancel", cancel_background_tasks))

            def shutdown(self) -> None:
                events.append("shutdown")

        monkeypatch.setattr(
            loop_mod, "explicit_save", lambda a: events.append("explicit_save")
        )
        monkeypatch.setattr(
            loop_mod, "flush_memory", lambda a: events.append("flush_memory")
        )
        index = SessionIndex(tmp_path / "index")
        sid = index.mint()
        btw = BtwContext(
            spawn_queue=BtwQueue(),
            build=lambda q: (None, []),
            cancel_event=threading.Event(),
            pending=[],
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            loop_mod._close_loop_session(
                _Agent(), btw, None, "test-model", [], pool, None, index, sid
            )
        assert events == [("cancel", True), "explicit_save", "flush_memory", "shutdown"]
        # Agents without cancel/shutdown or raising cleanup stay harmless.
        with ThreadPoolExecutor(max_workers=1) as pool:
            loop_mod._close_loop_session(
                object(), btw, None, "test-model", [], pool, None, index, sid
            )

    def test_wave5_multihop_away_tail_unary_note_and_bedrock_cache_usage(self):
        import warnings
        from types import SimpleNamespace

        import strands_code_cli.loop.core as loop_mod
        from strands_code_cli.model import model_switch as ms

        # 1. Multi-hop restore G1 -> O -> B -> G2 converts B's away tail cleanly.
        g_prefix = [
            {"role": "user", "content": [{"text": "u1"}]},
            {
                "role": "assistant",
                "content": [
                    {
                        "reasoningContent": {
                            "reasoningText": {"text": "gem", "signature": "gsig"}
                        }
                    },
                    {"text": "g-ans"},
                ],
            },
        ]
        b_tail = [
            {"role": "user", "content": [{"text": "u2"}]},
            {
                "role": "assistant",
                "content": [
                    {
                        "reasoningContent": {
                            "reasoningText": {"text": "bdr-away", "signature": "bsig"}
                        }
                    },
                    {"text": "b-ans"},
                ],
            },
        ]
        rich = loop_mod.RichHistory()
        rich.messages = g_prefix
        rich.model_id = "google/gemini-2.5-pro"
        rich.length = len(g_prefix)
        rich.prefix_hash = ms.canonical_prefix_hash(g_prefix)
        away_converted = ms.convert_history(
            g_prefix, "google/gemini-2.5-pro", "openai/gpt-5"
        )
        agent = SimpleNamespace(
            messages=away_converted + b_tail,
            model=SimpleNamespace(
                config={"model_id": "us.anthropic.claude-sonnet-4-6"}
            ),
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _id, reply = loop_mod.apply_model_action(
                agent,
                "google/gemini-3.8-flash",
                turn_running=False,
                current_model="bedrock/us.anthropic.claude-sonnet-4-6",
                rich=rich,
            )
        assert "thinking restored" in reply
        assert (
            agent.messages[1]["content"][0]["reasoningContent"]["reasoningText"][
                "signature"
            ]
            == "gsig"
        )
        assert "reasoningContent" not in agent.messages[3]["content"][0]
        assert agent.messages[3]["content"][0]["text"].startswith(ms.TRACE_LABEL)

        # 2. Bedrock Converse exclusive inputTokens with equal raw_in+raw_out == totalTokens adds cache.
        bdr_res = SimpleNamespace(
            metrics=SimpleNamespace(
                get_summary=lambda: {
                    "accumulated_usage": {
                        "inputTokens": 100,
                        "outputTokens": 50,
                        "totalTokens": 150,
                        "cacheReadInputTokens": 20000,
                        "cacheWriteInputTokens": 500,
                    }
                }
            )
        )
        assert loop_mod._extract_prompt_usage(
            bdr_res, "bedrock/us.anthropic.claude-sonnet-4-6", 100, 50
        ) == (20600, 20000, 500)
        # Non-Bedrock inclusive usage stays raw_in.
        assert loop_mod._extract_prompt_usage(
            bdr_res, "google/gemini-2.5-flash", 100, 50
        ) == (100, 20000, 500)
