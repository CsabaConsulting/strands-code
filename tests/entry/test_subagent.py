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

from strands_code_cli.entry.subagent import build_cli_subagent
from strands_code_cli.memory.memory_file import load_memory
from strands_code_cli.policy.policy_gate import PolicyGateHandler


def _install_subagent_doubles(monkeypatch, sub_mod):
    captured: dict[str, Any] = {}
    reg_calls: list[Any] = []
    hook_calls: list[tuple[Any, ...]] = []

    def fake_create_harness(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(model=kwargs.get("model"))

    def record_reg(agent_obj, fn):
        reg_calls.append((agent_obj, fn))

    def record_hook(kind):
        def _cb(tid, _model, **extra):
            entry = (
                (kind, tid, extra["base_url"]) if "base_url" in extra else (kind, tid)
            )
            hook_calls.append(entry)

        return _cb

    monkeypatch.setattr(sub_mod, "create_harness", fake_create_harness)
    monkeypatch.setattr(sub_mod, "register_memory_plugin", record_reg)
    for attr, kind in (
        ("configure_streaming_for_model", "stream"),
        ("configure_gemini_for_model", "gemini"),
        ("configure_openai_for_model", "openai"),
        ("configure_base_url_for_model", "base_url"),
    ):
        monkeypatch.setattr(sub_mod, attr, record_hook(kind))
    return captured, reg_calls, hook_calls


def _assert_isolated_monty_repl(
    parent_interp, parent_repl, child_repl, sub_mod, child, monty_cls
):
    assert getattr(child_repl, "tool_name", None) == "python_repl"
    assert child_repl is not parent_repl
    assert isinstance(child_repl._interpreter, monty_cls)
    parent_repl(code="secret = 1")
    child_repl(code="secret = 2")
    assert parent_repl(code="print(secret)") == "STDOUT:\n1"
    assert child_repl(code="print(secret)") == "STDOUT:\n2"
    parent_interp.close()
    sub_mod.close_agent_repls(child)
    assert child_repl._interpreter._session is None


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
        from strands_code_cli.sandbox.monty import MontyPythonInterpreter

        initial_model = _ReplayModel("openai/gpt-5")
        switched_model = _ReplayModel("anthropic/claude-haiku-4-5")
        parent_interp = MontyPythonInterpreter()
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

        captured, reg_calls, hook_calls = _install_subagent_doubles(
            monkeypatch, sub_mod
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
        _assert_isolated_monty_repl(
            parent_interp,
            parent_repl,
            captured["tools"][0],
            sub_mod,
            child,
            MontyPythonInterpreter,
        )

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

    def test_wave5_subagent_meta_chat_and_cross_provider_signature_hook(
        self, monkeypatch
    ):
        import strands_code_cli.entry.subagent as sub_mod

        parent = SimpleNamespace(model=_ReplayModel("google/gemini-3.8-flash"))
        captured: dict[str, Any] = {}
        hooks: list[tuple[Any, Any]] = []

        class _FakeChild:
            def __init__(self, model):
                self.model = model
                self.messages = [
                    {
                        "role": "assistant",
                        "content": [
                            {
                                "toolUse": {
                                    "toolUseId": "t1",
                                    "name": "read",
                                    "input": {},
                                    "reasoningSignature": b"gem-sig",
                                }
                            }
                        ],
                    }
                ]

            def add_hook(self, cb, ev_cls):
                hooks.append((cb, ev_cls))

        monkeypatch.setenv("MODEL_API_KEY", "meta-test")
        monkeypatch.setattr(
            sub_mod,
            "create_harness",
            lambda **kw: captured.update(kw) or _FakeChild(kw.get("model")),
        )
        monkeypatch.setattr(sub_mod, "register_memory_plugin", lambda _a, _l: None)

        tool = build_cli_subagent(
            {"agent": parent},
            {
                "model": parent.model,
                "effort": "high",
                "tools": [],
                "builtin_tools": {"shell": True, "read": True, "web_search": True},
                "memory": False,
                "session": False,
                "callback_handler": None,
                "_base_url": "https://meta-custom.example/v1",
                "_base_url_provider": "meta",
            },
        )
        child = tool._builder(
            AgentSpec(task="analyze", model="meta/muse-spark-1.3-contributor")
        )
        assert (
            getattr(captured["model"], "_strands_model_ref", None)
            == "meta/muse-spark-1.3-contributor"
        )
        assert captured["caching"] is False
        assert "effort" not in captured
        assert captured["builtin_tools"]["web_search"] is False
        assert hooks
        hooks[-1][0](SimpleNamespace(agent=child))
        assert "reasoningSignature" not in child.messages[0]["content"][0]["toolUse"]

    def test_subagent_reconciles_stale_web_fetch_after_switch_and_string_spec_model(
        self, monkeypatch
    ):
        import strands_code_cli.entry.subagent as sub_mod

        stale_wf = _ReplayModel("meta/muse-spark-1.3-contributor")
        parent = SimpleNamespace(model=_ReplayModel("meta/muse-spark-1.3-contributor"))
        captured: dict[str, Any] = {}
        monkeypatch.setattr(
            sub_mod,
            "create_harness",
            lambda **kw: captured.update(kw) or SimpleNamespace(model=kw.get("model")),
        )
        monkeypatch.setattr(sub_mod, "register_memory_plugin", lambda _a, _l: None)
        monkeypatch.setattr(
            sub_mod, "configure_base_url_for_model", lambda *a, **k: None
        )
        monkeypatch.setenv("MODEL_API_KEY", "meta-test")
        monkeypatch.setenv("OPENAI_API_KEY", "oai-test")

        parent_builtin = {
            "shell": True,
            "read": True,
            "web_fetch": {"model": stale_wf},
            "web_search": True,
            "subagent": False,
        }
        tool = build_cli_subagent(
            {"agent": parent},
            {
                "model": parent.model,
                "tools": [],
                "builtin_tools": parent_builtin,
                "memory": False,
                "session": False,
                "callback_handler": None,
            },
        )
        # Parent switches from Meta to Anthropic -> stale web_fetch removed, web_search off.
        parent.model = _ReplayModel("anthropic/claude-haiku-4-5")
        tool._builder(AgentSpec(task="analyze"))
        assert captured["builtin_tools"]["web_fetch"] is True
        assert captured["builtin_tools"]["web_search"] is False
        assert parent_builtin["web_fetch"] == {"model": stale_wf}

        # String spec.model without native search turns web_search=True off.
        tool._builder(
            AgentSpec(
                task="analyze", model="litellm/openrouter/anthropic/claude-sonnet-4"
            )
        )
        assert captured["builtin_tools"]["web_search"] is False
        assert captured["builtin_tools"]["web_fetch"] is True

        # Excluded web_fetch via spec.tools stays False even on Meta target.
        tool._builder(
            AgentSpec(
                task="read only",
                tools=["read"],
                model="meta/muse-spark-1.3-contributor",
            )
        )
        assert captured["builtin_tools"]["web_fetch"] is False
        assert captured["builtin_tools"]["web_search"] is False

        # Exa opt-in stays preserved and custom OpenAI endpoint gets fresh web_fetch model.
        exa_parent = SimpleNamespace(
            model=parent.model,
            _base_url="https://oai-proxy.example/v1",
            _base_url_provider="openai",
            _api_mode="chat",
        )
        exa_tool = build_cli_subagent(
            {"agent": exa_parent},
            {
                "model": parent.model,
                "tools": [],
                "builtin_tools": {"shell": True, "read": True, "web_search": "exa"},
                "memory": False,
                "session": False,
                "callback_handler": None,
                "_base_url": "https://oai-proxy.example/v1",
                "_base_url_provider": "openai",
                "_api_mode": "chat",
            },
        )
        exa_tool._builder(AgentSpec(task="fetch", model="openai/gpt-5"))
        assert captured["builtin_tools"]["web_search"] == "exa"
        assert getattr(
            captured["builtin_tools"]["web_fetch"]["model"], "_strands_model_ref", None
        ) == ("openai/gpt-5")

    def test_nyquist_import_error_fallback_same_vendor_signatures_and_instructions(
        self, monkeypatch
    ):
        import strands_code_cli.entry.subagent as sub_mod

        parent = SimpleNamespace(model=_ReplayModel("anthropic/claude-opus-4-6"))
        captured: dict[str, Any] = {}
        hooks: list[tuple[Any, Any]] = []

        class _ChildWithSig:
            def __init__(self, model):
                self.model = model
                self.messages = [
                    {
                        "role": "assistant",
                        "content": [
                            {
                                "toolUse": {
                                    "toolUseId": "t1",
                                    "name": "read",
                                    "input": {},
                                    "reasoningSignature": b"anth-sig",
                                }
                            }
                        ],
                    }
                ]

            def add_hook(self, cb, ev_cls):
                hooks.append((cb, ev_cls))

        monkeypatch.setattr(
            sub_mod,
            "create_harness",
            lambda **kw: captured.update(kw) or _ChildWithSig(kw.get("model")),
        )
        monkeypatch.setattr(sub_mod, "register_memory_plugin", lambda _a, _l: None)
        monkeypatch.setattr(
            sub_mod, "configure_base_url_for_model", lambda *a, **k: None
        )

        tool = build_cli_subagent(
            {"agent": parent},
            {
                "model": parent.model,
                "tools": [],
                "builtin_tools": {"shell": True, "read": True, "subagent": False},
                "memory": False,
                "session": False,
                "callback_handler": None,
            },
        )
        # Same-provider + same-vendor reasoning keeps toolUse reasoningSignature intact.
        same_child = tool._builder(
            AgentSpec(
                task="inspect",
                model=_ReplayModel("anthropic/claude-sonnet-4-6"),
                instructions="custom child instructions",
            )
        )
        assert captured["instructions"] == "custom child instructions"
        hooks[-1][0](SimpleNamespace(agent=same_child))
        assert same_child.messages[0]["content"][0]["toolUse"][
            "reasoningSignature"
        ] == (b"anth-sig")

        # ImportError resolving meta/ falls back to string spec.model.
        monkeypatch.setattr(
            sub_mod,
            "resolve_harness_model",
            lambda *a, **k: (_ for _ in ()).throw(ImportError("no meta extra")),
        )
        tool._builder(
            AgentSpec(task="meta fallback", model="meta/muse-spark-1.3-contributor")
        )
        assert captured["model"] == "meta/muse-spark-1.3-contributor"

    def test_subagent_stream_cleanup_closes_completed_child_repls(self, monkeypatch):
        import asyncio

        import strands_code_cli.entry.subagent as sub_mod
        from strands_code_cli.sandbox.monty import MontyPythonInterpreter

        interp_pending = MontyPythonInterpreter()
        interp_done = MontyPythonInterpreter()
        interp_pending.execute_code("p = 1")
        interp_done.execute_code("d = 2")
        pending_child = SimpleNamespace(
            _delegate_repl_tools=[interp_pending.get_tool()]
        )
        done_child = SimpleNamespace(_delegate_repl_tools=[interp_done.get_tool()])

        async def _fake_stream(tool_use, invocation_state, **kwargs):
            yield {"ok": True}

        fake_tool = SimpleNamespace(
            _pending={"tu-1": pending_child}, stream=_fake_stream
        )
        children = [pending_child, done_child]
        sub_mod._wrap_subagent_cleanup(fake_tool, children)

        async def _drain():
            return [e async for e in fake_tool.stream({"toolUseId": "tu-1"}, {})]

        assert asyncio.run(_drain()) == [{"ok": True}]
        assert interp_pending._session is not None
        assert interp_done._session is None
        assert children == [pending_child]
        interp_pending.close()
