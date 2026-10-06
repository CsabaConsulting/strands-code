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
from types import SimpleNamespace

import pytest

import strands_code_cli.policy_gate as pg
from strands_code_cli.btw import (
    BTW_FRAMING,
    BtwContext,
    BtwQueue,
    FencedBtwHandler,
    LockedHandler,
    append_btw_turn,
    build_btw_agent,
    fork_btw_history,
    render_btw_error,
)
from strands_code_cli.loop import _invoke_agent
from strands_code_cli.policy_gate import ApprovalBroker
from strands_code_cli.steering import (
    SteeringState,
    is_btw_line,
    start_steering_reader,
)


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
        from strands_code_cli.model_switch import MODEL_REFUSAL

        state = SteeringState()
        gate = threading.Event()
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
                lambda: len(spawned) == 1
                and len(refused) == 1
                and state.has_pending()
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
        gate = threading.Event()
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
                fenced(
                    message={"role": "assistant", "content": [{"text": SENTINEL}]}
                )
                return SENTINEL

        return _BtwDouble(), [{"role": "user", "content": [{"text": question}]}]

    return build


class TestParallelTurn:
    def test_btw_answers_in_parallel_while_main_continues(
        self, monkeypatch, capsys
    ):
        broker = ApprovalBroker()
        monkeypatch.setitem(pg._ACTIVE, "broker", broker)
        main = _MainDouble(delay=0.4)
        spawn: queue.Queue = queue.Queue()
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
        assert "--- btw: " in capsys.readouterr().out
        assert main.messages == [
            {"role": "user", "content": [{"text": "/btw why is this slow?"}]},
            {"role": "assistant", "content": [{"text": SENTINEL}]},
        ]
        assert btw.done is True
        # Sequential would cost 0.4 + 0.4 = 0.8s; parallel overlaps them.
        assert elapsed < 0.8

    def test_btw_failure_renders_fenced_and_main_continues(self, monkeypatch, capsys):
        broker = ApprovalBroker()
        monkeypatch.setitem(pg._ACTIVE, "broker", broker)
        main = _MainDouble()
        spawn: queue.Queue = queue.Queue()
        spawn.put("why is this slow?")
        btw = BtwContext(
            spawn_queue=spawn,
            build=_fenced_build(fail=True),
            cancel_event=threading.Event(),
            pending=[],
        )
        result = _invoke_agent(main, "do the thing", threading.Event(), btw=btw)
        assert result == "main-result"
        out = capsys.readouterr().out
        assert "btw failed (ValueError)" in out
        assert "--- end btw ---" in out
        assert main.messages == []
        assert btw.done is False


class TestBuildBtwAgent:
    def _patch_factory(self, monkeypatch):
        import strands_code_cli.btw as btw_mod

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
        from strands_code_cli.memory_file import load_memory

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
        import strands_code_cli.btw as btw_mod

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
        monkeypatch.setitem(pg._ACTIVE, "broker", broker)
        main = _MainDouble(delay=0.4)
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
        # Main finished first (0.4s) but the boundary held until the
        # queue drained (3 x 0.15s sequential sides): drain-before-exit.
        assert elapsed >= 0.4
        # ...while still overlapping main (sequential would cost 0.85s).
        assert elapsed < 0.85


class TestSteeringDuringBacklog:
    def test_plain_text_still_steers_main_while_btw_runs(self):
        state = SteeringState()
        gate = threading.Event()
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
        gate = threading.Event()
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
        gate = threading.Event()
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
