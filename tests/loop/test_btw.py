"""Mid-turn /btw side channel: fork, fence, carve-out, parallel turn, rebuild (LOOP-03).

Hermetic: doubles stand in for both agents (no live model, no
network). Concurrency is real threads over the real pump, lock, and
reader; timing assertions carry 2x headroom.
"""

from __future__ import annotations

import os
import queue
import threading
import time
from concurrent.futures import Future
from types import SimpleNamespace

import pytest
from strands.models import Model
from strands.types.exceptions import EventLoopException

from strands_code_cli.loop.btw import (
    BTW_FORK_PREAMBLE,
    BTW_FRAMING,
    BTW_IDLE_APPROVAL,
    BTW_INFLIGHT_MARKER,
    BtwContext,
    BtwQueue,
    FencedBtwHandler,
    LockedHandler,
    append_btw_turn,
    build_btw_agent,
    fork_btw_history,
    render_btw_error,
)
from strands_code_cli.loop.core import (
    _drain_idle_btw,
    _finish_btw_turn,
    _invoke_agent,
    _note_dropped_side,
)
from strands_code_cli.loop.steering import (
    StdinGuard,
    SteeringState,
    is_btw_line,
    start_steering_reader,
)
from strands_code_cli.policy.policy_gate import ApprovalBroker, TurnCancelled


def _history_trailing_assistant() -> list:
    """Parent history ending in an assistant turn (new-message fork case)."""
    return [
        {"role": "user", "content": [{"text": "implement retry"}]},
        {
            "role": "assistant",
            "content": [
                {"text": "on it"},
                {"reasoningContent": {"reasoningText": {"text": "hmm"}}},
                {
                    "toolUse": {
                        "toolUseId": "t1",
                        "name": "shell",
                        "input": {"command": "ls"},
                    }
                },
                {
                    "toolUse": {
                        "toolUseId": "t2",
                        "name": "shell",
                        "input": {"command": "sleep 99"},
                    }
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "toolResult": {
                        "toolUseId": "t1",
                        "status": "success",
                        "content": [{"text": "ok"}],
                    }
                }
            ],
        },
        {"role": "assistant", "content": [{"text": "done-ish"}]},
    ]


def _history_trailing_user() -> list:
    """Parent history ending in a user turn (absorb fork case)."""
    return [
        {"role": "user", "content": [{"text": "implement retry"}]},
        {
            "role": "assistant",
            "content": [
                {"text": "running"},
                {
                    "toolUse": {
                        "toolUseId": "t1",
                        "name": "shell",
                        "input": {"command": "ls"},
                    }
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "toolResult": {
                        "toolUseId": "t1",
                        "status": "success",
                        "content": [{"text": "ok"}],
                    }
                }
            ],
        },
    ]


class TestForkBtwHistory:
    def test_drops_reasoning_and_unanswered_tooluse(self):
        forked = fork_btw_history(_history_trailing_assistant(), "why slow?")
        for message in forked:
            for block in message["content"]:
                assert "reasoningContent" not in block
        answered = {
            block["toolResult"]["toolUseId"]
            for message in forked
            for block in message["content"]
            if "toolResult" in block
        }
        used = {
            block["toolUse"]["toolUseId"]
            for message in forked
            for block in message["content"]
            if "toolUse" in block
        }
        assert used == {"t1"} <= answered

    def test_mutating_fork_leaves_parent_untouched(self):
        parent = _history_trailing_assistant()
        forked = fork_btw_history(parent, "why slow?")
        forked[0]["content"][0]["text"] = "MUTATED"
        forked[-1]["content"][-1]["text"] = "MUTATED"
        assert parent[0]["content"][0]["text"] == "implement retry"
        assert parent[-1] == {"role": "assistant", "content": [{"text": "done-ish"}]}

    def test_trailing_message_carries_question_and_roles_alternate(self):
        forked = fork_btw_history(_history_trailing_assistant(), "why slow?")
        roles = [message["role"] for message in forked]
        assert roles == ["user", "assistant", "user", "assistant", "user"]
        assert forked[-1]["content"][-1]["text"].endswith("why slow?")

    def test_absorb_case_appends_into_trailing_user_message(self):
        forked = fork_btw_history(_history_trailing_user(), "why slow?")
        assert len(forked) == 3  # no new message added
        trailing = forked[-1]
        assert trailing["role"] == "user"
        assert len(trailing["content"]) == 2
        assert trailing["content"][-1]["text"].endswith("why slow?")
        roles = [message["role"] for message in forked]
        assert roles == ["user", "assistant", "user"]

    def test_empty_history_yields_single_question_turn(self):
        forked = fork_btw_history([], "why slow?")
        assert len(forked) == 1
        assert forked[0]["role"] == "user"
        assert forked[0]["content"][0]["text"].endswith("why slow?")

    def test_drops_injected_blocks_and_empty_injected_messages(self):
        parent = [
            {"role": "user", "content": [{"injected": {"text": "only-ctx"}}]},
            {"role": "assistant", "content": [{"text": "ack"}]},
            {
                "role": "user",
                "content": [
                    {"text": "implement retry"},
                    {
                        "injected": {
                            "text": "<ctx>memory</ctx>",
                            "source": "strands-code:memory",
                        }
                    },
                ],
            },
            {"role": "assistant", "content": [{"text": "done"}]},
        ]
        forked = fork_btw_history(parent, "why slow?")
        assert all(
            "injected" not in block
            for message in forked
            for block in message["content"]
        )
        assert [m["role"] for m in forked] == ["assistant", "user", "assistant", "user"]

    def test_converts_anthropic_summary_blocks_to_text(self):
        from strands_code_cli.model.model_switch import SUMMARY_LABEL

        parent = [
            {
                "role": "assistant",
                "content": [
                    {
                        "summary": {
                            "provider": "anthropic",
                            "signature": "S",
                            "text": "Compacted prior exchange",
                        }
                    },
                    {"summary": {"provider": "anthropic", "text": "   "}},
                ],
            },
            {"role": "user", "content": [{"text": "continue"}]},
        ]
        forked = fork_btw_history(parent, "why slow?")
        assert forked[0]["content"] == [
            {"text": f"{SUMMARY_LABEL}\nCompacted prior exchange"}
        ]
        assert all("summary" not in block for msg in forked for block in msg["content"])


class TestForkScope:
    """G-7-1b A+B: the forked side prompt bounds scope structurally (D-04/D-09)."""

    def test_trailing_unanswered_user_text_turn_gets_context_marker(self):
        # Mid-turn spawn: the trailing raw-text user turn is the
        # in-flight main directive — marked context-only in place.
        parent = [
            {"role": "user", "content": [{"text": "write an essay"}]},
        ]
        forked = fork_btw_history(parent, "list /tmp")
        assert len(forked) == 1  # absorbed, no split
        trailing = forked[-1]
        assert trailing["role"] == "user"
        assert len(trailing["content"]) == 2
        assert trailing["content"][0]["text"].startswith(BTW_INFLIGHT_MARKER)
        assert "write an essay" in trailing["content"][0]["text"]
        assert trailing["content"][-1]["text"].endswith("list /tmp")

    def test_trailing_toolresult_turn_gets_no_marker(self):
        forked = fork_btw_history(_history_trailing_user(), "why slow?")
        texts = [
            block.get("text", "") for block in forked[-1]["content"] if "text" in block
        ]
        assert all(BTW_INFLIGHT_MARKER not in text for text in texts)

    def test_trailing_assistant_turn_gets_no_marker(self):
        forked = fork_btw_history(_history_trailing_assistant(), "why slow?")
        texts = [
            block.get("text", "")
            for message in forked
            for block in message["content"]
            if "text" in block
        ]
        assert all(BTW_INFLIGHT_MARKER not in text for text in texts)

    def test_marked_fork_roles_alternate_and_parent_unmutated(self):
        parent = [
            {"role": "user", "content": [{"text": "write an essay"}]},
            {"role": "assistant", "content": [{"text": "on it"}]},
            {"role": "user", "content": [{"text": "make it long"}]},
        ]
        forked = fork_btw_history(parent, "list /tmp")
        roles = [message["role"] for message in forked]
        assert roles == ["user", "assistant", "user"]
        forked[-1]["content"][0]["text"] = "MUTATED"
        assert parent[-1] == {"role": "user", "content": [{"text": "make it long"}]}

    def test_framing_constants_carry_scope_boundary(self):
        for constant in (BTW_FRAMING, BTW_FORK_PREAMBLE):
            assert "ONLY" in constant
            assert "do not perform" in constant
            assert "read-only context" in constant


class TestAppendBtwTurn:
    def test_appends_verbatim_pair(self):
        messages: list = [{"role": "assistant", "content": [{"text": "main work"}]}]
        append_btw_turn(messages, "why slow?", "because reasons")
        assert messages[-2:] == [
            {"role": "user", "content": [{"text": "/btw why slow?"}]},
            {"role": "assistant", "content": [{"text": "because reasons"}]},
        ]


class _Body:
    """Inner-handler double printing one identifiable body line per message."""

    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.count = 0

    def __call__(self, **kwargs) -> None:
        self.count += 1
        print(f"{self.tag}-body-{self.count}")


class TestFencedRender:
    def test_fenced_blocks_stay_contiguous_under_concurrency(self, capsys):
        main = LockedHandler(_Body("main"))
        fenced = FencedBtwHandler(_Body("side"), "what does retry do?")

        def run_main() -> None:
            for _ in range(10):
                main(message={"role": "assistant", "content": [{"text": "m"}]})

        def run_side() -> None:
            for _ in range(10):
                fenced(message={"role": "assistant", "content": [{"text": "s"}]})

        threads = [
            threading.Thread(target=run_main),
            threading.Thread(target=run_side),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        assert not any(thread.is_alive() for thread in threads)
        lines = capsys.readouterr().out.splitlines()
        assert sum(line.startswith("main-body-") for line in lines) == 10
        headers = [i for i, line in enumerate(lines) if line.startswith("--- btw: ")]
        assert len(headers) == 10
        for head in headers:
            # Atomic block: header, then exactly its body, then its footer —
            # no torn interleave from the other thread.
            assert lines[head + 1].startswith("side-body-")
            assert lines[head + 2] == "--- end btw ---"

    def test_production_nesting_reenters_without_deadlock(self, capsys):
        # Production wiring wraps the shared LockedHandler, so __call__
        # re-enters RENDER_LOCK on the same thread — a plain Lock wedges
        # here on the first side content message. Timeout-guarded so a
        # regression fails instead of hanging the suite.
        body = _Body("side")
        fenced = FencedBtwHandler(LockedHandler(body), "why slow?")
        box: dict = {}

        def run() -> None:
            box["result"] = fenced(
                message={"role": "assistant", "content": [{"text": "s"}]}
            )

        thread = threading.Thread(target=run)
        thread.start()
        thread.join(timeout=10)
        assert not thread.is_alive()
        assert box["result"] is None
        assert body.count == 1
        out = capsys.readouterr().out
        assert "--- btw: why slow? ---" in out
        assert "--- end btw ---" in out

    def test_contentless_message_prints_no_fence(self, capsys):
        fenced = FencedBtwHandler(_Body("side"), "why slow?")
        assert fenced() is None
        assert fenced(message={"role": "assistant", "content": []}) is None
        assert capsys.readouterr().out == ""

    def test_render_btw_error_uses_fence_shape(self, capsys):
        render_btw_error("why slow?", ValueError("boom"))
        out = capsys.readouterr().out
        assert "--- btw: why slow? ---" in out
        assert "btw failed (ValueError): boom" in out
        assert "--- end btw ---" in out

    def test_locked_handler_delegates_and_exposes_inner(self):
        def inner(**kwargs):
            return ("ok", kwargs)

        locked = LockedHandler(inner)
        assert locked.inner is inner
        assert locked(message={"x": 1}) == ("ok", {"message": {"x": 1}})


class _PipeStdin:
    """Minimal stdin double exposing a real fd for the select+read loop."""

    def __init__(self, fd: int) -> None:
        self._fd = fd

    def fileno(self) -> int:
        return self._fd


def _wait_for(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


class TestIsBtwLine:
    def test_head_match_is_case_insensitive(self):
        assert is_btw_line("/btw what does retry do?")
        assert is_btw_line("/BTW what does retry do?")
        assert is_btw_line("  /Btw x  ")
        assert is_btw_line("/btw")

    def test_other_lines_are_not_btw(self):
        assert not is_btw_line("/btwx oops")
        assert not is_btw_line("/model")
        assert not is_btw_line("plain steer text")
        assert not is_btw_line("")


class TestMidTurnCarveOut:
    def test_btw_carves_out_while_other_slash_refuses_and_text_steers(self):
        from strands_code_cli.model.model_switch import MODEL_REFUSAL

        state = SteeringState()
        gate = StdinGuard()
        spawned: list[str] = []
        refused: list[tuple] = []
        read_fd, write_fd = os.pipe()
        try:
            reader = start_steering_reader(
                state,
                gate,
                stdin=_PipeStdin(read_fd),
                on_btw=spawned.append,
                on_refusal=lambda line, reply: refused.append((line, reply)),
            )
            os.write(write_fd, b"/btw what does retry do?\n/model\nsteer text\n")
            assert _wait_for(
                lambda: len(spawned) == 1 and len(refused) == 1 and state.has_pending()
            )
            assert spawned == ["what does retry do?"]
            assert refused == [("/model", MODEL_REFUSAL)]
            assert state.take() == "steer text"
            reader.stop()
            assert not reader.alive
        finally:
            os.close(write_fd)
            os.close(read_fd)

    def test_bare_btw_mid_turn_yields_usage_not_spawn(self):
        state = SteeringState()
        gate = StdinGuard()
        spawned: list[str] = []
        refused: list[tuple] = []
        read_fd, write_fd = os.pipe()
        try:
            reader = start_steering_reader(
                state,
                gate,
                stdin=_PipeStdin(read_fd),
                on_btw=spawned.append,
                on_refusal=lambda line, reply: refused.append((line, reply)),
            )
            os.write(write_fd, b"/btw\n")
            assert _wait_for(lambda: len(refused) == 1)
            assert spawned == []
            assert refused == [("/btw", "Usage: /btw <side question>")]
            assert not state.has_pending()
            reader.stop()
        finally:
            os.close(write_fd)
            os.close(read_fd)


class _MainDouble:
    """Main agent double: sleeps, returns, never touches history itself."""

    def __init__(self, delay: float = 0.0) -> None:
        self.messages: list = []
        self.calls: list = []
        self._delay = delay

    def __call__(self, text, **kwargs):
        self.calls.append(text)
        if self._delay:
            time.sleep(self._delay)
        return "main-result"


SENTINEL = "side-answer-sentinel"


def _settle_live_btw(btw: BtwContext, timeout: float = 5.0):
    """Block until the attached side run completes (None when nothing live).

    Worker failures return None here — they surface via the drain's
    fenced render, never via this wait.
    """
    from concurrent.futures import TimeoutError as FuturesTimeoutError

    future = btw.live_future
    if future is None:
        return None
    try:
        return future.result(timeout=timeout)
    except FuturesTimeoutError:
        raise
    except Exception:
        return None


class _MeteredResult:
    """Side-result double: answer text plus a metrics summary (spend row)."""

    def __init__(self, text: str, in_tok: int = 10, out_tok: int = 20) -> None:
        self.text = text
        summary = {
            "accumulated_usage": {"inputTokens": in_tok, "outputTokens": out_tok},
            "total_cycles": 1,
            "total_duration": 0.5,
        }

        class _Metrics:
            def get_summary(self):
                return summary

        self.metrics = _Metrics()


def _metered_build(answer: str = "metered-side-answer", delay: float = 0.0):
    """Build double: streams one fenced block, then a metered result."""

    def build(question: str):
        fenced = FencedBtwHandler(_Body("side"), question)

        class _BtwDouble:
            def __call__(self, prompt, **kwargs):
                if delay:
                    time.sleep(delay)
                fenced(message={"role": "assistant", "content": [{"text": SENTINEL}]})
                return _MeteredResult(answer)

        return _BtwDouble(), [{"role": "user", "content": [{"text": question}]}]

    return build


def _fenced_build(inner_tag: str = "side", delay: float = 0.0, fail: bool = False):
    """Build callable double: streams one fenced block, then answers (or fails)."""

    def build(question: str):
        inner = _Body(inner_tag)
        fenced = FencedBtwHandler(inner, question)

        class _BtwDouble:
            def __call__(self, prompt, **kwargs):
                if delay:
                    time.sleep(delay)
                if fail:
                    raise ValueError("side boom")
                fenced(message={"role": "assistant", "content": [{"text": SENTINEL}]})
                return SENTINEL

        return _BtwDouble(), [{"role": "user", "content": [{"text": question}]}]

    return build


class TestParallelTurn:
    def test_btw_answers_in_parallel_then_outlives_main(self, monkeypatch, capsys):
        broker = ApprovalBroker()
        main = _MainDouble(delay=0.1)
        main._approval_broker = broker
        spawn = BtwQueue()
        spawn.put("why is this slow?")
        btw = BtwContext(
            spawn_queue=spawn,
            build=_fenced_build(delay=0.4),
            cancel_event=threading.Event(),
            pending=[],
        )
        start = time.monotonic()
        result = _invoke_agent(main, "do the thing", threading.Event(), btw=btw)
        elapsed = time.monotonic() - start
        assert result == "main-result"
        assert main.calls == ["do the thing"]
        # No join: the turn returns on main completion, not side completion.
        assert elapsed < 0.4
        assert btw.has_live
        assert not btw.live_future.done()
        assert not btw.cancel_event.is_set()  # not cut, not cancelled
        assert main.messages == []  # nothing reaped yet
        _settle_live_btw(btw)
        _drain_idle_btw(main, btw, broker, "test-model", [])
        out = capsys.readouterr().out
        assert "--- btw: " in out
        assert "side-body-1" in out
        assert main.messages == [
            {"role": "user", "content": [{"text": "/btw why is this slow?"}]},
            {"role": "assistant", "content": [{"text": SENTINEL}]},
        ]
        assert btw.done is True
        assert not btw.has_live

    def test_btw_failure_renders_fenced_and_main_continues(self, monkeypatch, capsys):
        broker = ApprovalBroker()
        main = _MainDouble()
        main._approval_broker = broker
        spawn = BtwQueue()
        spawn.put("why is this slow?")
        btw = BtwContext(
            spawn_queue=spawn,
            build=_fenced_build(fail=True),
            cancel_event=threading.Event(),
            pending=[],
        )
        result = _invoke_agent(main, "do the thing", threading.Event(), btw=btw)
        assert result == "main-result"
        _settle_live_btw(btw)
        _drain_idle_btw(main, btw, broker, "test-model", [])
        out = capsys.readouterr().out
        assert "btw failed (ValueError)" in out
        assert "--- end btw ---" in out
        assert main.messages == []
        assert btw.done is False


class TestBuildBtwAgent:
    def _patch_factory(self, monkeypatch):
        import strands_code_cli.loop.btw as btw_mod

        created: dict = {}
        sentinel_agent = SimpleNamespace()
        mem_calls: dict = {}
        sentinel_mem = object()
        reg_calls: list = []

        def fake_create_harness(**kwargs):
            created.update(kwargs)
            return sentinel_agent

        def fake_resolve_memory(**kwargs):
            mem_calls.update(kwargs)
            return sentinel_mem

        def fake_register(agent, injector):
            reg_calls.append((agent, injector))

        monkeypatch.setattr(btw_mod, "create_harness", fake_create_harness)
        monkeypatch.setattr(btw_mod, "resolve_memory", fake_resolve_memory)
        monkeypatch.setattr(btw_mod, "register_memory_plugin", fake_register)
        return created, mem_calls, reg_calls, sentinel_agent, sentinel_mem

    def test_rebuild_replays_parent_with_delegate_overrides(self, monkeypatch):
        from strands_code_agent.code_agent import CODE_AGENT_INSTRUCTIONS
        from strands_code_cli.memory.memory_file import load_memory

        created, mem_calls, reg_calls, sentinel_agent, sentinel_mem = (
            self._patch_factory(monkeypatch)
        )
        model, tools, interventions = object(), [object()], [object()]
        hook_steer, hook_other = object(), object()
        handler = object()
        parent = {
            "model": model,
            "tools": tools,
            "interventions": interventions,
            "hooks": [hook_steer, hook_other],
            "steering_hook": hook_steer,
            "memory": True,
            "session": {"id": "s"},
            "callback_handler": handler,
            "instructions": "parent",
            "skills": object(),
        }
        history = [{"role": "user", "content": [{"text": "do x"}]}]
        agent, prompt = build_btw_agent(parent, history, "why slow?")
        assert agent is sentinel_agent
        assert created["model"] is model
        assert created["tools"] is tools
        assert created["interventions"] is interventions
        assert created["session"] is False
        assert created["memory"] is sentinel_mem
        assert mem_calls.get("writable") is False
        assert len(created["hooks"]) == 1 and created["hooks"][0] is hook_other
        assert "steering_hook" not in created
        fenced = created["callback_handler"]
        assert isinstance(fenced, FencedBtwHandler) and fenced.inner is handler
        assert created["instructions"] == f"{CODE_AGENT_INSTRUCTIONS}\n{BTW_FRAMING}"
        assert reg_calls == [(sentinel_agent, load_memory)]
        assert prompt[-1]["role"] == "user"
        assert "why slow?" in prompt[-1]["content"][-1]["text"]
        assert parent["hooks"] == [hook_steer, hook_other]

    def test_build_btw_agent_registers_side_agent_tag(self, monkeypatch):
        from strands_code_cli.policy.policy_gate import PolicyGateHandler

        _, _, _, sentinel_agent, _ = self._patch_factory(monkeypatch)
        gate = PolicyGateHandler()
        parent = {
            "model": object(),
            "tools": [],
            "interventions": [gate],
            "memory": False,
            "session": {"id": "s"},
            "callback_handler": object(),
        }
        agent, _ = build_btw_agent(parent, [], "side question")
        assert agent is sentinel_agent
        assert gate.tag_for(agent) == "btw"
        assert getattr(agent, "_policy_gate", None) is gate

    def test_mapping_memory_forwards_stores_readonly(self, monkeypatch):
        created, mem_calls, _, _, _ = self._patch_factory(monkeypatch)
        stores = object()
        parent = {
            "memory": {"stores": stores, "dir": "/tmp/mem"},
            "session": {"id": "s"},
            "callback_handler": object(),
        }
        build_btw_agent(parent, [], "why slow?")
        assert mem_calls == {
            "stores": stores,
            "memory_dir": "/tmp/mem",
            "writable": False,
        }
        assert "steering_hook" not in created

    def test_memory_off_parent_builds_memoryless_child(self, monkeypatch):
        import strands_code_cli.loop.btw as btw_mod

        created: dict = {}

        def fake_create_harness(**kwargs):
            created.update(kwargs)
            return SimpleNamespace()

        def boom_resolve(**kwargs):
            raise AssertionError("resolve_memory must not run for memory=False")

        monkeypatch.setattr(btw_mod, "create_harness", fake_create_harness)
        monkeypatch.setattr(btw_mod, "resolve_memory", boom_resolve)
        monkeypatch.setattr(btw_mod, "register_memory_plugin", lambda a, i: None)
        build_btw_agent(
            {"memory": False, "session": {"id": "s"}, "callback_handler": object()},
            [],
            "why slow?",
        )
        assert created["memory"] is False

    def test_build_btw_agent_disables_streaming_on_llama(self, monkeypatch):
        import strands_code_cli.loop.btw as btw_mod

        update_calls = []

        class _LlamaModel:
            def get_config(self):
                return {"model_id": "us.meta.llama4-scout-17b-instruct-v1:0"}

            def update_config(self, **kwargs):
                update_calls.append(kwargs)

        def fake_create_harness(**kwargs):
            return SimpleNamespace(model=_LlamaModel())

        monkeypatch.setattr(btw_mod, "create_harness", fake_create_harness)
        monkeypatch.setattr(btw_mod, "register_memory_plugin", lambda a, i: None)
        build_btw_agent(
            {
                "model": "us.meta.llama4-scout-17b-instruct-v1:0",
                "memory": False,
                "session": {"id": "s"},
                "callback_handler": object(),
            },
            [],
            "why slow?",
        )
        assert update_calls == [{"streaming": False}]

    def test_build_btw_agent_normalizes_gemini_25_thinking(self, monkeypatch):
        import strands_code_cli.loop.btw as btw_mod

        class _GeminiModel:
            def __init__(self):
                self.config = {
                    "model_id": "gemini-2.5-pro",
                    "params": {"thinking_config": {"thinking_level": "high"}},
                }

            def get_config(self):
                return self.config

            def update_config(self, **kwargs):
                self.config.update(kwargs)

        gemini_model = _GeminiModel()
        monkeypatch.setattr(
            btw_mod,
            "create_harness",
            lambda **kwargs: SimpleNamespace(model=gemini_model),
        )
        monkeypatch.setattr(btw_mod, "register_memory_plugin", lambda a, i: None)
        build_btw_agent(
            {
                "model": "google/gemini-2.5-pro",
                "memory": False,
                "session": {"id": "s"},
                "callback_handler": object(),
            },
            [],
            "why slow?",
        )
        assert gemini_model.config["params"]["thinking_config"] == {
            "thinking_budget": -1
        }

    def test_build_btw_agent_applies_base_url_without_leaking_kwarg(self, monkeypatch):
        import strands_code_cli.loop.btw as btw_mod

        created: dict = {}
        oai_model = SimpleNamespace(client_args={}, _bedrock_mantle_config=None)

        def fake_create_harness(**kwargs):
            created.update(kwargs)
            return SimpleNamespace(model=oai_model)

        monkeypatch.setattr(btw_mod, "create_harness", fake_create_harness)
        monkeypatch.setattr(btw_mod, "register_memory_plugin", lambda a, i: None)
        build_btw_agent(
            {
                "model": "openai/gpt-6.1-sol",
                "memory": False,
                "session": {"id": "s"},
                "callback_handler": object(),
                "_base_url": "https://proxy.local/v1",
                "_base_url_provider": "openai",
            },
            [],
            "why slow?",
        )
        assert "_base_url" not in created
        assert "_base_url_provider" not in created
        assert oai_model.client_args["base_url"] == "https://proxy.local/v1"

        cross_model = SimpleNamespace(client_args={}, _bedrock_mantle_config=None)
        monkeypatch.setattr(
            btw_mod,
            "create_harness",
            lambda **kwargs: SimpleNamespace(model=cross_model),
        )
        build_btw_agent(
            {
                "model": "openai/gpt-6.1-sol",
                "memory": False,
                "session": {"id": "s"},
                "callback_handler": object(),
                "_base_url": "https://anthropic-proxy.local/v1",
                "_base_url_provider": "anthropic",
            },
            [],
            "cross check",
        )
        assert "base_url" not in cross_model.client_args

    def test_build_btw_agent_calls_configure_openai_for_model(self, monkeypatch):
        import strands_code_cli.loop.btw as btw_mod

        class _OaiModel:
            def __init__(self):
                self.config = {"params": {"reasoning": {"effort": "high"}}}
                self._bedrock_mantle_config = None

            def get_config(self):
                return self.config

            def update_config(self, **kw):
                self.config.update(kw)

        oai_model = _OaiModel()
        monkeypatch.setattr(
            btw_mod,
            "create_harness",
            lambda **kwargs: SimpleNamespace(model=oai_model),
        )
        monkeypatch.setattr(btw_mod, "register_memory_plugin", lambda a, i: None)
        build_btw_agent(
            {
                "model": "openai/gpt-4o",
                "memory": False,
                "session": {"id": "s"},
                "callback_handler": object(),
            },
            [],
            "why slow?",
        )
        assert "reasoning" not in oai_model.config["params"]

    def test_build_btw_agent_preserves_meta_model_ref_and_base_url_scope(
        self, monkeypatch
    ):
        import strands_code_cli.loop.btw as btw_mod
        from strands_code_cli.model.model_switch import build_meta_model, model_id_of

        monkeypatch.setenv("MODEL_API_KEY", "test-meta-token")
        meta_model = build_meta_model("meta/muse-spark-1.3-contributor")
        captured: dict = {}

        def fake_create_harness(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(model=meta_model)

        monkeypatch.setattr(btw_mod, "create_harness", fake_create_harness)
        monkeypatch.setattr(btw_mod, "register_memory_plugin", lambda a, i: None)
        build_btw_agent(
            {
                "model": meta_model,
                "memory": False,
                "session": {"id": "s"},
                "callback_handler": object(),
                "_base_url": "https://meta-proxy.local/v1",
                "_base_url_provider": "meta",
            },
            [],
            "meta side?",
        )
        assert captured["caching"] is False
        assert model_id_of(meta_model, "?") == "meta/muse-spark-1.3-contributor"
        assert meta_model.client_args["base_url"] == "https://meta-proxy.local/v1"

        fresh_meta = build_meta_model("meta/muse-ember-1.0")
        monkeypatch.setattr(
            btw_mod, "create_harness", lambda **_kw: SimpleNamespace(model=fresh_meta)
        )
        build_btw_agent(
            {
                "model": fresh_meta,
                "memory": False,
                "session": {"id": "s"},
                "callback_handler": object(),
                "_base_url": "https://openai-proxy.local/v1",
                "_base_url_provider": "openai",
            },
            [],
            "foreign base_url ignored?",
        )
        assert fresh_meta.client_args["base_url"] == "https://api.meta.ai/v1"


def _idle_btw(**overrides):
    """BtwContext double with a real BtwQueue (submit/echo tests)."""
    fields = {
        "spawn_queue": BtwQueue(),
        "build": _fenced_build(),
        "cancel_event": threading.Event(),
    }
    fields.update(overrides)
    return BtwContext(**fields)


class TestBtwQueue:
    def test_put_returns_depth_and_holds_fifo_order(self):
        pending = BtwQueue()
        assert pending.empty()
        assert pending.put("q1") == 1
        assert pending.put("  q2  ") == 2
        assert pending.put("q3") == 3
        assert not pending.empty()
        assert pending.qsize() == 3
        assert pending.depth == 3
        assert pending.get_nowait() == "q1"
        assert pending.get_nowait() == "q2"  # stripped on the way in
        assert pending.get_nowait() == "q3"
        assert pending.empty()
        with pytest.raises(queue.Empty):
            pending.get_nowait()

    def test_put_rejects_blank_questions(self):
        pending = BtwQueue()
        with pytest.raises(ValueError):
            pending.put("   ")
        assert pending.empty()

    def test_submit_echoes_noted_when_side_idle(self, capsys):
        btw = _idle_btw()
        assert btw.submit("why slow?") == 1
        out = capsys.readouterr().out
        assert "> /btw why slow?" in out
        assert "Side question noted — answering in parallel." in out
        assert "queued" not in out
        assert btw.spawn_queue.get_nowait() == "why slow?"

    def test_submit_echoes_queued_depth_when_side_runs(self, capsys):
        btw = _idle_btw()
        btw.running.set()  # a side double runs
        assert btw.submit("q1") == 1
        assert btw.submit("q2") == 2
        assert btw.submit("q3") == 3
        out = capsys.readouterr().out
        assert "> /btw q2" in out
        assert "Side question queued (#1 in line)" in out
        assert "Side question queued (#2 in line)" in out
        assert "Side question queued (#3 in line)" in out
        assert "noted" not in out

    def test_submit_rejects_blank_with_no_echo(self, capsys):
        btw = _idle_btw()
        with pytest.raises(ValueError):
            btw.submit("  ")
        assert capsys.readouterr().out == ""
        assert btw.spawn_queue.empty()


class _CountingSideBuild:
    """Build double recording start order and max concurrent live runs."""

    def __init__(self, delay: float = 0.15) -> None:
        self.starts: list[str] = []
        self.live_max = 0
        self._live = 0
        self._lock = threading.Lock()
        self._delay = delay

    def __call__(self, question: str):
        parent = self

        class _Side:
            def __call__(self, prompt, **kwargs):
                with parent._lock:
                    parent._live += 1
                    parent.live_max = max(parent.live_max, parent._live)
                    parent.starts.append(question)
                try:
                    time.sleep(parent._delay)
                finally:
                    with parent._lock:
                        parent._live -= 1
                return f"answer-{question}"

        return _Side(), [{"role": "user", "content": [{"text": question}]}]


class TestBtwFifoDrain:
    def test_queued_questions_run_in_order_one_at_a_time(self, monkeypatch, capsys):
        broker = ApprovalBroker()
        main = _MainDouble(delay=0.4)
        main._approval_broker = broker
        spawn = BtwQueue()
        assert spawn.put("q1") == 1
        assert spawn.put("q2") == 2
        assert spawn.put("q3") == 3
        sides = _CountingSideBuild(delay=0.15)
        btw = BtwContext(
            spawn_queue=spawn,
            build=sides,
            cancel_event=threading.Event(),
            pending=[],
        )
        start = time.monotonic()
        result = _invoke_agent(main, "do the thing", threading.Event(), btw=btw)
        elapsed = time.monotonic() - start
        assert result == "main-result"
        # Main finished first (0.4s); whether q3 was still running
        # or just completed at the boundary is scheduling luck — either
        # way nothing joins (sequential would cost 0.85s) and the idle
        # drain lands whatever the pump did not reap.
        assert elapsed < 0.85
        _settle_live_btw(btw)
        _drain_idle_btw(main, btw, broker, "test-model", [])
        assert sides.starts == ["q1", "q2", "q3"]
        assert sides.live_max == 1
        assert btw.done is True
        assert main.messages == [
            {"role": "user", "content": [{"text": "/btw q1"}]},
            {"role": "assistant", "content": [{"text": "answer-q1"}]},
            {"role": "user", "content": [{"text": "/btw q2"}]},
            {"role": "assistant", "content": [{"text": "answer-q2"}]},
            {"role": "user", "content": [{"text": "/btw q3"}]},
            {"role": "assistant", "content": [{"text": "answer-q3"}]},
        ]
        assert not btw.has_live


class TestSteeringDuringBacklog:
    def test_plain_text_still_steers_main_while_btw_runs(self):
        state = SteeringState()
        gate = StdinGuard()
        btw = _idle_btw()
        btw.running.set()  # backlog: a side answer runs
        read_fd, write_fd = os.pipe()
        try:
            reader = start_steering_reader(
                state, gate, stdin=_PipeStdin(read_fd), on_btw=btw.submit
            )
            os.write(write_fd, b"steer text\n")
            assert _wait_for(state.has_pending)
            assert state.take() == "steer text"
            assert btw.spawn_queue.empty()  # steering never enqueues
            reader.stop()
        finally:
            os.close(write_fd)
            os.close(read_fd)

    def test_btw_submit_through_reader_echoes_receipt_and_status(self, capsys):
        state = SteeringState()
        gate = StdinGuard()
        btw = _idle_btw()
        btw.running.set()  # backlog: a side answer runs
        read_fd, write_fd = os.pipe()
        try:
            reader = start_steering_reader(
                state, gate, stdin=_PipeStdin(read_fd), on_btw=btw.submit
            )
            os.write(write_fd, b"/btw queued question\n")
            assert _wait_for(lambda: btw.spawn_queue.qsize() == 1)
            out = capsys.readouterr().out
            assert "> /btw queued question" in out
            assert "Side question queued (#1 in line)" in out
            assert not state.has_pending()
            reader.stop()
        finally:
            os.close(write_fd)
            os.close(read_fd)


class TestGateOpenBtw:
    def test_btw_typed_during_open_prompt_waits_for_close(self):
        state = SteeringState()
        gate = StdinGuard()
        gate.set()  # approval prompt open: the reader must not consume
        spawned: list[str] = []
        read_fd, write_fd = os.pipe()
        try:
            reader = start_steering_reader(
                state, gate, stdin=_PipeStdin(read_fd), on_btw=spawned.append
            )
            os.write(write_fd, b"/btw q\n")
            time.sleep(0.2)
            assert spawned == []
            gate.clear()
            assert _wait_for(lambda: spawned == ["q"])
            reader.stop()
        finally:
            os.close(write_fd)
            os.close(read_fd)


def _done_future():
    """Future double already completed."""
    from concurrent.futures import Future

    future: Future = Future()
    future.set_result("side-result")
    return future


def _pending_future():
    """Future double that never completes on its own."""
    from concurrent.futures import Future

    return Future()


class TestLiveHandle:
    def test_attach_detach_round_trip(self):
        btw = _idle_btw()
        assert not btw.has_live
        assert btw.detach_live() is None
        future = _pending_future()
        agent = object()
        btw.attach_live(agent, future, "q1")
        assert btw.has_live
        assert btw.detach_live() == (agent, future, "q1")
        assert not btw.has_live
        assert btw.detach_live() is None

    def test_take_done_live_reaps_only_completed(self):
        btw = _idle_btw()
        assert btw.take_done_live() is None
        running_future = _pending_future()
        btw.attach_live(object(), running_future, "q1")
        assert btw.take_done_live() is None  # still running: stays attached
        assert btw.has_live
        done_future = _done_future()
        btw.attach_live(object(), done_future, "q2")
        taken = btw.take_done_live()
        assert taken is not None
        assert taken[1] is done_future
        assert taken[2] == "q2"
        assert not btw.has_live

    def test_take_done_live_clears_running_only_when_queue_empty(self):
        btw = _idle_btw()
        btw.running.set()
        btw.attach_live(object(), _done_future(), "q1")
        assert btw.take_done_live() is not None
        assert not btw.running.is_set()  # drained fully: idle-side again
        btw.running.set()
        btw.spawn_queue.put("q2")  # backlog waits for the next pump
        btw.attach_live(object(), _done_future(), "q1")
        assert btw.take_done_live() is not None
        assert btw.running.is_set()  # backlog: submits still read queued


class TestOutlivingMain:
    def test_side_lands_fenced_with_history_and_metrics_at_idle(
        self, monkeypatch, capsys
    ):
        broker = ApprovalBroker()
        main = _MainDouble()
        main._approval_broker = broker
        spawn = BtwQueue()
        spawn.put("why is this slow?")
        btw = BtwContext(
            spawn_queue=spawn,
            build=_metered_build(delay=0.3),
            cancel_event=threading.Event(),
            pending=[],
        )
        start = time.monotonic()
        result = _invoke_agent(main, "do the thing", threading.Event(), btw=btw)
        elapsed = time.monotonic() - start
        assert result == "main-result"
        assert elapsed < 0.3  # the side (0.3s) outlived the instant main
        assert btw.has_live
        assert not btw.cancel_event.is_set()
        _settle_live_btw(btw)
        session_turns: list = []
        _drain_idle_btw(main, btw, broker, "test-model", session_turns)
        out = capsys.readouterr().out
        assert "--- btw: " in out
        assert main.messages == [
            {"role": "user", "content": [{"text": "/btw why is this slow?"}]},
            {"role": "assistant", "content": [{"text": "metered-side-answer"}]},
        ]
        assert len(session_turns) == 1
        assert session_turns[0]["input_tokens"] == 10
        assert session_turns[0]["output_tokens"] == 20
        assert btw.done is True
        assert not btw.has_live
        assert btw.pending == []  # delivered, never double-recorded

    def test_new_turn_adopts_live_side_without_respawn(self, monkeypatch, capsys):
        broker = ApprovalBroker()
        spawn = BtwQueue()
        spawn.put("why is this slow?")
        sides = _CountingSideBuild(delay=0.4)
        btw = BtwContext(
            spawn_queue=spawn,
            build=sides,
            cancel_event=threading.Event(),
            pending=[],
        )
        first = _MainDouble()
        first._approval_broker = broker
        assert _invoke_agent(first, "turn one", threading.Event(), btw=btw)
        assert btw.has_live  # the side outlived turn one
        assert sides.starts == ["why is this slow?"]
        second = _MainDouble(delay=0.6)
        second._approval_broker = broker
        both_running = threading.Event()
        result = _invoke_agent(
            second, "turn two", threading.Event(), btw=btw, both_running=both_running
        )
        assert result == "main-result"
        # Turn two re-entered the pump with the live side adopted: the
        # side completed mid-turn and flushed there — no rebuild, no
        # restart, no second spawn.
        assert sides.starts == ["why is this slow?"]
        assert sides.live_max == 1
        assert second.messages == [
            {"role": "user", "content": [{"text": "/btw why is this slow?"}]},
            {
                "role": "assistant",
                "content": [{"text": "answer-why is this slow?"}],
            },
        ]
        assert btw.done is True
        assert not btw.has_live
        capsys.readouterr()  # counting sides print nothing; drain the capture

    def test_idle_approval_announced_once_then_served_next_turn(
        self, monkeypatch, capsys
    ):
        broker = ApprovalBroker()
        main = _MainDouble()
        main._approval_broker = broker
        btw = _idle_btw()
        # A side run lives past its turn while the session pump stays
        # entered (the run_loop idle shape, minus the terminal).
        session_cancel = threading.Event()
        with broker.pump(session_cancel):
            # The exact G-7-1a shape: a turn pump enters and exits
            # inside the session pump before the idle request — the
            # session pump must stay entered so the approval enqueues.
            with broker.pump(threading.Event()):
                pass
            assert broker._pumping.is_set()
            assert broker._cancel is session_cancel
            btw.attach_live(object(), _pending_future(), "needs approval")
            btw.running.set()
            answers: list = []

            def worker() -> None:
                answers.append(broker.request(lambda: "allow", btw.cancel_event))

            thread = threading.Thread(target=worker)
            thread.start()
            assert _wait_for(lambda: broker.has_pending)
            session_turns: list = []
            _drain_idle_btw(main, btw, broker, "test-model", session_turns)
            first = capsys.readouterr().out
            assert BTW_IDLE_APPROVAL in first
            # Still waiting at the next boundary: announced once, never
            # re-announced, and the drain never serves it.
            _drain_idle_btw(main, btw, broker, "test-model", session_turns)
            assert BTW_IDLE_APPROVAL not in capsys.readouterr().out
            assert answers == []  # the worker still waits
            # The next turn's pump serves the queued approval.
            served = broker.poll(timeout=2.0)
            assert served is not None
            served.run_prompt()
            thread.join(timeout=5.0)
            assert not thread.is_alive()
            assert answers == ["allow"]
            assert not broker.has_pending
            # Queue clear: the notice arms again for the next episode.
            _drain_idle_btw(main, btw, broker, "test-model", session_turns)
            assert btw.approval_announced is False
            assert capsys.readouterr().out == ""


class TestExitDropNote:
    """Exit names a live side run with its state; never promises a turn."""

    def _exit_sequence(self, main, btw, broker, session_turns):
        # The exact run_loop exit order: drain, name, cancel.
        _drain_idle_btw(main, btw, broker, "test-model", session_turns, from_exit=True)
        _note_dropped_side(btw, broker)
        if btw.has_live:
            btw.cancel_event.set()

    def test_live_parked_side_named_waiting_no_next_turn(self, monkeypatch, capsys):
        broker = ApprovalBroker()
        main = _MainDouble()
        main._approval_broker = broker
        btw = _idle_btw()
        session_cancel = threading.Event()
        with broker.pump(session_cancel):
            btw.attach_live(object(), _pending_future(), "needs approval")
            btw.running.set()
            answers: list = []

            def worker() -> None:
                try:
                    answers.append(broker.request(lambda: "allow", btw.cancel_event))
                except TurnCancelled:
                    answers.append("cancelled")

            thread = threading.Thread(target=worker)
            thread.start()
            assert _wait_for(lambda: broker.has_pending)
            self._exit_sequence(main, btw, broker, [])
            out = capsys.readouterr().out
            assert "needs approval" in out
            assert "waiting on approval" in out
            assert "--- btw: needs approval ---" in out
            assert BTW_IDLE_APPROVAL not in out
            assert "next turn" not in out
            thread.join(timeout=5.0)
            assert not thread.is_alive()
            assert answers == ["cancelled"]  # exit cancel unblocks the waiter

    def test_live_running_side_named_still_running(self, monkeypatch, capsys):
        broker = ApprovalBroker()
        main = _MainDouble()
        main._approval_broker = broker
        btw = _idle_btw()
        with broker.pump(threading.Event()):
            btw.attach_live(object(), _pending_future(), "long analysis")
            btw.running.set()
            self._exit_sequence(main, btw, broker, [])
            out = capsys.readouterr().out
            assert "long analysis" in out
            assert "still running" in out
            assert "next turn" not in out

    def test_done_unreaped_side_lands_without_drop_note(self, monkeypatch, capsys):
        broker = ApprovalBroker()
        main = _MainDouble()
        main._approval_broker = broker
        btw = _idle_btw()
        with broker.pump(threading.Event()):
            btw.attach_live(object(), _done_future(), "q1")
            btw.running.set()
            self._exit_sequence(main, btw, broker, [])
            assert not btw.has_live  # reaped by the exit drain
            assert btw.pending == []  # flushed to history, nothing held
            out = capsys.readouterr().out
            assert "dropped on exit" not in out
            assert "next turn" not in out


class TestFinishBtwTurnCancel:
    def test_cancel_renders_fenced_note_never_failed(self, capsys):
        # G-7-2 F-2: a side future dying on cancel (raw or SDK-wrapped)
        # lands as a fenced cancel note — never "btw failed" text.
        for exc in (TurnCancelled(), EventLoopException(TurnCancelled())):
            btw = _idle_btw()
            future: Future = Future()
            future.set_exception(exc)
            _finish_btw_turn(btw, object(), future, "needs approval")
            out = capsys.readouterr().out
            assert "--- btw: " in out
            assert "--- end btw ---" in out
            assert "Cancelled by user" in out
            assert "failed (" not in out
            assert "EventLoopException" not in out
            assert btw.pending == []
            assert btw.done is False


@pytest.mark.integration
class TestLiveIdleScenario:
    """Live D-11 bounded-wait scenario (manual-terminal checklist).

    Hermetic doubles prove the mechanism (outlive, idle land, announce,
    next-turn serve); only a live terminal proves the rendering:
    start a long main task, fire ``/btw`` needing approval, let main
    finish first, and confirm the ``btw approval needed`` notice lands
    once, the tagged ``[btw]`` prompt serves on the next turn, and the
    fenced block lands without scrambling the ``> `` line.
    """

    def test_live_outlive_announce_and_land(self, monkeypatch, capsys):
        if not os.environ.get("STRANDS_CODE_LIVE_MODEL"):
            pytest.skip("needs a live model + terminal; see the class docstring")
        broker = ApprovalBroker()
        main = _MainDouble()
        main._approval_broker = broker
        spawn = BtwQueue()
        spawn.put("why is this slow?")
        btw = BtwContext(
            spawn_queue=spawn,
            build=_metered_build(delay=0.2),
            cancel_event=threading.Event(),
            pending=[],
        )
        assert _invoke_agent(main, "do the thing", threading.Event(), btw=btw)
        assert btw.has_live
        _settle_live_btw(btw)
        session_turns: list = []
        _drain_idle_btw(main, btw, broker, "test-model", session_turns)
        assert "--- btw: " in capsys.readouterr().out
        assert len(main.messages) == 2
        assert len(session_turns) == 1


class TestBtwLiveModelBillingAndReplIsolation:
    """D-08: live model sync, routed /cost attribution, REPL isolation, read-only."""

    def test_btw_context_picks_up_switched_live_model_and_endpoint(self, monkeypatch):
        import strands_code_cli.loop.core as loop_mod

        old_model = SimpleNamespace(
            config=SimpleNamespace(model_id="anthropic/claude-opus-4-6")
        )
        new_model = SimpleNamespace(config=SimpleNamespace(model_id="openai/gpt-5"))
        builds: list = []

        def fake_build(kwargs, history, question):
            builds.append((dict(kwargs), question))
            return SimpleNamespace(model=kwargs["model"]), []

        monkeypatch.setattr(loop_mod, "build_btw_agent", fake_build)
        agent = SimpleNamespace(
            model=old_model,
            messages=[],
            _base_url="https://old.example/v1",
            _base_url_provider="anthropic",
            _api_mode="responses",
            _harness_kwargs={
                "model": old_model,
                "tools": [],
                "interventions": [],
                "memory": False,
                "callback_handler": object(),
                "_base_url": "https://old.example/v1",
                "_base_url_provider": "anthropic",
                "_api_mode": "responses",
            },
        )
        ctx = loop_mod._btw_context_for(agent)
        # Switch main agent model and clear endpoint after /btw context creation.
        agent.model = new_model
        agent._base_url = None
        agent._base_url_provider = None
        agent._api_mode = None

        ctx.build("first check")
        ctx.attach_live(object(), _pending_future(), "first check")
        ctx.build("second while live")

        assert len(builds) == 2
        for kw, _q in builds:
            assert kw["model"] is new_model
            assert "_base_url" not in kw
            assert "_base_url_provider" not in kw
            assert "_api_mode" not in kw

    def test_routed_btw_bills_under_side_model_rates(self, monkeypatch):
        import strands_code_cli.loop.core as loop_mod
        from strands_code_cli.cost.cost_context import cost_for, cost_report

        opus_id = "us.anthropic.claude-opus-4-6-v1"
        haiku_id = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
        side_model = SimpleNamespace(config=SimpleNamespace(model_id=haiku_id))

        btw = _idle_btw()
        future: Future = Future()
        future.set_result(_MeteredResult("ok", in_tok=100_000, out_tok=50_000))
        _finish_btw_turn(
            btw, SimpleNamespace(model=side_model, messages=[]), future, "q1"
        )
        assert len(btw.pending) == 1
        assert btw.pending[0][4] == haiku_id

        session_turns: list = []
        loop_mod._announce_turn_usage(
            btw,
            _MeteredResult("main", in_tok=1_000, out_tok=500),
            opus_id,
            session_turns,
            SimpleNamespace(
                model=SimpleNamespace(config=SimpleNamespace(model_id=opus_id))
            ),
            "tool",
            [],
        )
        assert len(session_turns) == 2
        assert session_turns[0]["model"] == haiku_id
        assert session_turns[1]["model"] == opus_id
        haiku_cost = cost_for(100_000, 50_000, haiku_id)
        opus_cost = cost_for(100_000, 50_000, opus_id)
        assert (
            haiku_cost is not None and opus_cost is not None and haiku_cost < opus_cost
        )
        report = cost_report(session_turns, opus_id)
        assert f"${haiku_cost:.4f}" in report

        # Idle drain also attributes using side_model_id instead of parent opus_id.
        btw2 = _idle_btw()
        done_future: Future = Future()
        done_future.set_result(_MeteredResult("ok", in_tok=100_000, out_tok=50_000))
        btw2.attach_live(
            SimpleNamespace(model=side_model, messages=[]), done_future, "q2"
        )
        idle_turns: list = []
        _drain_idle_btw(SimpleNamespace(messages=[]), btw2, None, opus_id, idle_turns)
        assert len(idle_turns) == 1
        assert idle_turns[0]["model"] == haiku_id

    def test_fresh_tools_for_delegate_and_build_btw_agent_isolate_python_repl(
        self, monkeypatch
    ):
        from strands_code_agent.python_environments.local_sandboxed import (
            SandboxedPythonInterpreter,
        )
        from strands_code_cli.loop.btw import fresh_tools_for_delegate
        from strands_code_cli.policy.policy_gate import PolicyGateHandler

        non_repl = [object()]
        assert fresh_tools_for_delegate(non_repl) is non_repl

        parent_interp = SandboxedPythonInterpreter("", authorized_imports=set())
        parent_repl = parent_interp.get_tool()
        other_tool = SimpleNamespace(tool_name="search")
        parent_gate = PolicyGateHandler()
        parent_agent = SimpleNamespace()
        parent_gate.register_agent(parent_agent, "main")
        parent_gate.enter_read_only(parent_agent)

        import strands_code_cli.loop.btw as btw_mod

        captured: dict = {}

        def fake_create_harness(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace()

        monkeypatch.setattr(btw_mod, "create_harness", fake_create_harness)
        monkeypatch.setattr(btw_mod, "register_memory_plugin", lambda a, i: None)

        side_agent, _ = build_btw_agent(
            {
                "model": object(),
                "tools": [parent_repl, other_tool],
                "interventions": [parent_gate],
                "memory": False,
                "session": {"id": "s"},
                "callback_handler": object(),
                "_parent_agent": parent_agent,
            },
            [],
            "compute",
        )
        child_tools = captured["tools"]
        assert child_tools[1] is other_tool
        child_repl = child_tools[0]
        assert child_repl is not parent_repl
        parent_repl(code="x = 10")
        child_repl(code="x = 999")
        assert parent_repl(code="print(x)") == "STDOUT:\n10"
        assert child_repl(code="print(x)") == "STDOUT:\n999"
        assert parent_gate.tag_for(side_agent) == "btw"
        assert parent_gate.is_read_only(side_agent) is True

    def test_wave5_btw_strips_tool_use_signature_and_model_instance_guards(
        self, monkeypatch
    ):
        from strands.models import Model

        import strands_code_cli.loop.btw as btw_mod

        history = [
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "c1",
                            "name": "read",
                            "input": {"path": "a"},
                            "reasoningSignature": b"gem-sig",
                        }
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {"toolResult": {"toolUseId": "c1", "content": [{"text": "ok"}]}}
                ],
            },
        ]
        forked = btw_mod.fork_btw_history(history, "explain")
        tu = forked[0]["content"][0]["toolUse"]
        assert "reasoningSignature" not in tu
        assert "reasoningSignature" in history[0]["content"][0]["toolUse"]

        class _FakeModel(Model):
            def update_config(self, **model_config):
                pass

            def get_config(self):
                return {"model_id": "fake"}

            async def stream(self, *args, **kwargs):
                yield {}

            def structured_output(self, *args, **kwargs):
                return None

        captured: dict = {}
        monkeypatch.setattr(
            btw_mod,
            "create_harness",
            lambda **kw: captured.update(kw) or SimpleNamespace(),
        )
        monkeypatch.setattr(btw_mod, "register_memory_plugin", lambda _a, _l: None)
        btw_mod.build_btw_agent(
            {
                "model": _FakeModel(),
                "effort": "low",
                "memory": False,
                "session": False,
                "callback_handler": object(),
            },
            [],
            "q",
        )
        assert captured["caching"] is False
        assert "effort" not in captured


class _BtwProbeModel(Model):
    """Minimal Model subclass for real create_harness /btw wiring tests."""

    def __init__(self, model_id: str = "fake") -> None:
        self._model_id = model_id

    def update_config(self, **model_config):
        pass

    def get_config(self):
        return {"model_id": self._model_id}

    async def stream(self, *args, **kwargs):
        yield {}

    def structured_output(self, *args, **kwargs):
        return None


class TestBtwTest5Hardening:
    """Test 5 gaps: web_search on Model, stale web_fetch, subagent clean instructions, teardown."""

    def test_btw_web_search_true_on_prebuilt_model_uses_real_create_harness(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        parent_builtin = {
            "shell": True,
            "read": True,
            "web_search": True,
            "subagent": False,
        }
        parent_kwargs = {
            "model": _BtwProbeModel("anthropic/claude-sonnet-4-5"),
            "builtin_tools": parent_builtin,
            "tools": [],
            "memory": False,
            "session": False,
            "callback_handler": LockedHandler(_Body("parent")),
        }
        side_agent, _prompt = build_btw_agent(parent_kwargs, [], "check real harness")
        assert parent_builtin["web_search"] is True
        assert "web_search" not in side_agent.tool_registry.registry

    def test_btw_reconciles_stale_web_fetch_and_preserves_exa_and_meta(
        self, monkeypatch
    ):
        import strands_code_cli.loop.btw as btw_mod

        captured: dict = {}
        monkeypatch.setattr(
            btw_mod,
            "create_harness",
            lambda **kw: captured.update(kw) or SimpleNamespace(model=kw.get("model")),
        )
        monkeypatch.setattr(btw_mod, "register_memory_plugin", lambda _a, _l: None)
        monkeypatch.setenv("MODEL_API_KEY", "meta-test")

        stale_wf = object()
        parent_builtin = {
            "shell": True,
            "read": True,
            "web_search": True,
            "web_fetch": {"model": stale_wf},
        }
        btw_mod.build_btw_agent(
            {
                "model": _BtwProbeModel("anthropic/claude-sonnet-4-6"),
                "builtin_tools": parent_builtin,
                "memory": False,
                "session": False,
                "callback_handler": object(),
            },
            [],
            "check stale",
        )
        assert captured["builtin_tools"]["web_search"] is False
        assert captured["builtin_tools"]["web_fetch"] is True
        assert parent_builtin["web_fetch"] == {"model": stale_wf}

        # Preserve web_search="exa" and web_fetch=False.
        btw_mod.build_btw_agent(
            {
                "model": _BtwProbeModel("openai/gpt-5"),
                "builtin_tools": {"web_search": "exa", "web_fetch": False},
                "memory": False,
                "session": False,
                "callback_handler": object(),
            },
            [],
            "preserve exa",
        )
        assert captured["builtin_tools"]["web_search"] == "exa"
        assert captured["builtin_tools"]["web_fetch"] is False

        # Meta target rebuilds a fresh web_fetch summarizer rather than keeping None/stale.
        btw_mod.build_btw_agent(
            {
                "model": "meta/muse-spark-1.3-contributor",
                "builtin_tools": {"web_fetch": {"model": stale_wf}, "web_search": True},
                "memory": False,
                "session": False,
                "callback_handler": object(),
            },
            [],
            "meta target",
        )
        new_wf = captured["builtin_tools"]["web_fetch"]["model"]
        assert new_wf is not stale_wf
        assert getattr(new_wf, "_strands_model_ref", None) == (
            "meta/muse-spark-1.3-contributor"
        )

    def test_btw_stamps_endpoint_and_keeps_rebound_subagent_instructions_clean(
        self, monkeypatch
    ):
        from strands_harness.tools.subagent import AgentSpec

        import strands_code_cli.entry.subagent as sub_mod
        import strands_code_cli.loop.btw as btw_mod

        sub_captured: dict = {}
        monkeypatch.setattr(
            btw_mod,
            "create_harness",
            lambda **kw: SimpleNamespace(
                model=kw.get("model"), _tools=kw.get("tools", [])
            ),
        )
        monkeypatch.setattr(btw_mod, "register_memory_plugin", lambda _a, _l: None)
        monkeypatch.setattr(
            btw_mod, "configure_base_url_for_model", lambda *a, **k: None
        )
        monkeypatch.setattr(
            sub_mod,
            "create_harness",
            lambda **kw: (
                sub_captured.update(kw) or SimpleNamespace(model=kw.get("model"))
            ),
        )
        monkeypatch.setattr(sub_mod, "register_memory_plugin", lambda _a, _l: None)
        monkeypatch.setattr(
            sub_mod, "configure_base_url_for_model", lambda *a, **k: None
        )
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        rebound_parent = SimpleNamespace(tool_name="subagent")
        side_agent, _prompt = build_btw_agent(
            {
                "model": _BtwProbeModel("openai/gpt-5"),
                "tools": [rebound_parent],
                "instructions": "BASE_ONLY",
                "builtin_tools": {"shell": True, "read": True, "subagent": False},
                "memory": False,
                "session": False,
                "callback_handler": object(),
                "_base_url": "https://oai-proxy.example/v1",
                "_base_url_provider": "openai",
                "_api_mode": "chat",
            },
            [],
            "spawn child",
        )
        assert side_agent._base_url == "https://oai-proxy.example/v1"
        assert side_agent._base_url_provider == "openai"
        assert side_agent._api_mode == "chat"

        sub_tool = next(t for t in side_agent._tools if t.tool_name == "subagent")
        assert sub_tool is not rebound_parent
        sub_tool._builder(AgentSpec(task="inspect", model="openai/gpt-4o"))
        assert BTW_FRAMING not in sub_captured.get("instructions", "")
        assert sub_captured["instructions"] == "BASE_ONLY"
        wf_model = sub_captured["builtin_tools"]["web_fetch"]["model"]
        assert getattr(wf_model, "_strands_model_ref", None) == "openai/gpt-4o"

    def test_finish_btw_turn_tears_down_side_agent_on_success_and_cancel(self):
        from strands_code_cli.policy.policy_gate import PolicyGateHandler

        def _make_side(gate):
            events: list = []

            class _Side:
                model = SimpleNamespace(
                    config=SimpleNamespace(model_id="anthropic/claude-haiku-4-5")
                )
                messages = []

                def cancel(self, *, cancel_background_tasks: bool = False) -> None:
                    events.append(("cancel", cancel_background_tasks))

                def shutdown(self) -> None:
                    events.append("shutdown")

            side = _Side()
            gate.register_agent(side, "btw")
            side._policy_gate = gate
            gate.enter_read_only(side)
            return side, events

        gate = PolicyGateHandler()
        main_agent = SimpleNamespace()
        gate.bind_main_agent(main_agent)

        btw = _idle_btw()
        side_ok, events_ok = _make_side(gate)
        fut_ok: Future = Future()
        fut_ok.set_result(_MeteredResult("answer ok", in_tok=10, out_tok=5))
        _finish_btw_turn(btw, side_ok, fut_ok, "q ok")
        assert btw.pending[0][1] == "answer ok"
        assert events_ok == [("cancel", True), "shutdown"]
        assert id(side_ok) not in gate._agent_tags
        assert id(side_ok) not in gate._read_only_agents

        side_cancel, events_cancel = _make_side(gate)
        fut_cancel: Future = Future()
        fut_cancel.set_exception(TurnCancelled())
        _finish_btw_turn(btw, side_cancel, fut_cancel, "q cancel")
        assert events_cancel == [("cancel", True), "shutdown"]
        assert id(side_cancel) not in gate._agent_tags
        assert id(side_cancel) not in gate._read_only_agents
