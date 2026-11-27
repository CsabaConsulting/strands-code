"""Custom CLI subagent wrapper: live model, REPL isolation, hooks & gate (D-08)."""

from __future__ import annotations

import importlib
import uuid
from types import SimpleNamespace
from typing import Any

from strands.experimental.context_manager import ContextManager
from strands.models.model import Model
from strands.tools.tools import AgentTool
from strands_harness.tools.subagent import AgentSpec

from strands_code_agent.python_environments.local_sandboxed import (
    SandboxedPythonInterpreter,
)
from strands_code_cli.entry.subagent import build_cli_subagent
from strands_code_cli.memory.memory_file import load_memory
from strands_code_cli.policy.policy_gate import PolicyGateHandler


class _ReplayModel(Model):
    """Minimal offline Model double for real create_harness wiring checks."""

    def __init__(self, model_id: str) -> None:
        self._model_id = model_id

    def update_config(self, **model_config: Any) -> None:
        pass

    def get_config(self) -> Any:
        return {"model_id": self._model_id}

    async def structured_output(  # type: ignore[override]
        self,
        output_model: Any,
        prompt: Any,
        system_prompt: str | None = None,
        **kw: Any,
    ) -> Any:
        raise NotImplementedError("offline")
        yield

    async def stream(  # type: ignore[override]
        self,
        messages: Any,
        tool_specs: Any = None,
        system_prompt: Any = None,
        **kw: Any,
    ):
        yield {"messageStart": {"role": "assistant"}}
        yield {"contentBlockStart": {"start": {}}}
        yield {"contentBlockDelta": {"delta": {"text": "done"}}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "end_turn"}}
        yield {
            "metadata": {
                "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
                "metrics": {"latencyMs": 0},
            }
        }


class TestCliSubagentWiring:
    def test_build_agent_wires_custom_subagent_and_keeps_background_registration(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        main_module = importlib.import_module("strands_code_cli.entry.main")
        agent = main_module.build_agent(
            str(uuid.uuid4()),
            tmp_path / "sessions",
            model=_ReplayModel("anthropic/claude-sonnet-4-5"),
        )
        assert agent._harness_kwargs["builtin_tools"]["subagent"] is False
        tools = agent._harness_kwargs["tools"]
        subagent_tool = next(
            t for t in tools if getattr(t, "tool_name", None) == "subagent"
        )
        assert isinstance(subagent_tool, AgentTool)
        # Background task manager stays attached and registers subagent under always.
        bg = getattr(agent, "_background_tasks", None)
        assert bg is not None
        always = bg._config.get("always", [])
        assert any(
            entry is subagent_tool or getattr(entry, "tool_name", entry) == "subagent"
            for entry in always
        )

    def test_child_inherits_live_model_isolated_repl_hooks_and_read_only(
        self, monkeypatch
    ):
        import strands_code_cli.entry.subagent as sub_mod

        initial_model = _ReplayModel("openai/gpt-5")
        switched_model = _ReplayModel("anthropic/claude-haiku-4-5")
        parent_interp = SandboxedPythonInterpreter("", authorized_imports=set())
        parent_repl = parent_interp.get_tool()
        search_tool = SimpleNamespace(tool_name="search")
        gate = PolicyGateHandler()
        parent = SimpleNamespace(
            model=initial_model,
            _base_url="https://oai-proxy.example/v1",
            _base_url_provider="openai",
            _policy_gate=gate,
        )
        gate.register_agent(parent, "main")
        gate.enter_read_only(parent)

        steering_hook = object()
        other_hook = object()
        parent_cfg = {
            "model": initial_model,
            "tools": [parent_repl, search_tool],
            "builtin_tools": {"shell": True, "read": True, "subagent": False},
            "interventions": [gate],
            "hooks": [steering_hook, other_hook],
            "steering_hook": steering_hook,
            "context_manager": ContextManager(),
            "memory": {"dir": "/tmp/mem"},
            "session": {"id": "sess-1"},
            "callback_handler": object(),
        }
        tool = build_cli_subagent({"agent": parent}, parent_cfg)

        # Simulate /model switch on parent after startup.
        parent.model = switched_model
        parent._base_url = None
        parent._base_url_provider = None

        captured: dict[str, Any] = {}
        reg_calls: list[Any] = []
        hook_calls: list[tuple[str, Any]] = []

        def fake_create_harness(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(model=kwargs.get("model"))

        monkeypatch.setattr(sub_mod, "create_harness", fake_create_harness)
        monkeypatch.setattr(
            sub_mod, "register_memory_plugin", lambda a, fn: reg_calls.append((a, fn))
        )
        monkeypatch.setattr(
            sub_mod,
            "configure_streaming_for_model",
            lambda tid, m: hook_calls.append(("stream", tid)),
        )
        monkeypatch.setattr(
            sub_mod,
            "configure_gemini_for_model",
            lambda tid, m: hook_calls.append(("gemini", tid)),
        )
        monkeypatch.setattr(
            sub_mod,
            "configure_openai_for_model",
            lambda tid, m: hook_calls.append(("openai", tid)),
        )
        monkeypatch.setattr(
            sub_mod,
            "configure_base_url_for_model",
            lambda tid, m, base_url=None: hook_calls.append(
                ("base_url", tid, base_url)
            ),
        )

        child = tool._builder(AgentSpec(task="inspect code"))
        assert captured["model"] is switched_model
        assert captured["caching"] is False
        assert captured["session"] is False
        assert captured["callback_handler"] is None
        assert captured["hooks"] == [other_hook]
        assert "_base_url" not in captured
        assert not isinstance(captured["context_manager"], ContextManager)
        assert captured["builtin_tools"]["subagent"] is False

        # Isolated REPL check.
        child_repl = next(
            t
            for t in captured["tools"]
            if getattr(t, "tool_name", None) == "python_repl"
        )
        assert child_repl is not parent_repl
        parent_repl(code="secret = 1")
        child_repl(code="secret = 2")
        assert parent_repl(code="print(secret)") == "STDOUT:\n1"
        assert child_repl(code="print(secret)") == "STDOUT:\n2"

        # CLI hooks and gate posture.
        assert gate.tag_for(child) == "subagent"
        assert gate.is_read_only(child) is True
        assert getattr(child, "_policy_gate", None) is gate
        assert reg_calls == [(child, load_memory)]
        assert ("stream", "anthropic/claude-haiku-4-5") in hook_calls
        assert ("base_url", "anthropic/claude-haiku-4-5", None) in hook_calls

    def test_child_explicit_spec_tools_and_cross_provider_base_url_scoping(
        self, monkeypatch
    ):
        import strands_code_cli.entry.subagent as sub_mod

        parent = SimpleNamespace(
            model=_ReplayModel("openai/gpt-5"),
            _base_url="https://oai-proxy.example/v1",
            _base_url_provider="openai",
        )
        captured: dict[str, Any] = {}
        base_urls: list[Any] = []

        monkeypatch.setattr(
            sub_mod,
            "create_harness",
            lambda **kw: captured.update(kw) or SimpleNamespace(model=kw.get("model")),
        )
        monkeypatch.setattr(sub_mod, "register_memory_plugin", lambda a, fn: None)
        monkeypatch.setattr(
            sub_mod,
            "configure_base_url_for_model",
            lambda tid, m, base_url=None: base_urls.append((tid, base_url)),
        )

        search_tool = SimpleNamespace(tool_name="search")
        tool = build_cli_subagent(
            {"agent": parent},
            {
                "model": parent.model,
                "tools": [search_tool],
                "builtin_tools": {"shell": True, "read": True, "subagent": False},
                "memory": False,
                "session": False,
                "callback_handler": None,
            },
        )
        # Child selects only `read` and switches to Anthropic -> OpenAI base_url scrubbed.
        tool._builder(
            AgentSpec(
                task="read",
                tools=["read"],
                model=_ReplayModel("anthropic/claude-sonnet-4-5"),
            )
        )
        assert captured["builtin_tools"]["shell"] is False
        assert captured["builtin_tools"]["read"] is True
        assert captured["builtin_tools"]["subagent"] is False
        assert captured["tools"] == []
        assert captured["memory"] is False
        assert base_urls[-1] == ("anthropic/claude-sonnet-4-5", None)

    def test_read_only_btw_spawning_subagent_inherits_read_only_posture(
        self, tmp_path, monkeypatch
    ):
        from strands_code_cli.loop.btw import build_btw_agent

        monkeypatch.chdir(tmp_path)
        main_module = importlib.import_module("strands_code_cli.entry.main")
        main_agent = main_module.build_agent(
            str(uuid.uuid4()),
            tmp_path / "sessions",
            model=_ReplayModel("anthropic/claude-sonnet-4-5"),
        )
        gate = main_agent._policy_gate
        side_agent, _prompt = build_btw_agent(
            {**main_agent._harness_kwargs, "_parent_agent": main_agent},
            [],
            "check",
        )
        gate.enter_read_only(side_agent)
        sub_tool = next(
            t
            for t in side_agent.tool_registry.registry.values()
            if t.tool_name == "subagent"
        )
        child = sub_tool._builder(AgentSpec(task="inspect"))
        assert gate.is_read_only(main_agent) is False
        assert gate.is_read_only(side_agent) is True
        assert gate.is_read_only(child) is True
