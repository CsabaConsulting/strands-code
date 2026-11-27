"""Custom CLI ``subagent`` tool wrapper with live-model inheritance and CLI hooks (D-01, D-08).

# Upstream: strands-agents/harness-sdk — build_default_subagent snapshots startup
# model and omits CLI post-init hooks / REPL isolation; retire wrapper if upstream
# adds live-model & post-build hook seams.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from strands.experimental.context_manager import ContextManager
from strands.hooks.events import BeforeModelCallEvent
from strands.models import Model
from strands.tools.mcp import MCPClient
from strands.types.tools import AgentTool
from strands_harness import create_harness, defaults
from strands_harness.memory import resolve_memory
from strands_harness.options import _normalize_builtin_tools
from strands_harness.tools.subagent import (
    _CONTEXT_MODES,
    GENERALIST,
    AgentSpec,
    Choice,
    _mcp_clients_by_name,
    make_subagent,
)

from strands_code_cli.cost.reported_cost import fresh_side_model
from strands_code_cli.loop.btw import fresh_tools_for_delegate
from strands_code_cli.memory.memory_file import load_memory, register_memory_plugin
from strands_code_cli.model.model_switch import (
    _provider_of,
    configure_base_url_for_model,
    configure_gemini_for_model,
    configure_openai_for_model,
    configure_streaming_for_model,
    model_id_of,
    normalize_model_ref,
    reconcile_delegate_builtin_tools,
    resolve_harness_model,
    same_provider,
    same_vendor,
    scoped_base_url,
    supports_reasoning,
)


def _select_child_tools(
    spec: AgentSpec,
    parent_builtin: Mapping[str, Any],
    consumer_by_name: Mapping[str, Any],
    mcp_clients_by_name: Mapping[str, MCPClient],
    child_config: dict[str, Any],
) -> None:
    """Populate clamped ``builtin_tools`` and isolated ``tools`` on ``child_config``."""
    if spec.tools is not None:
        child_config["builtin_tools"] = {
            name: False
            if name == "subagent"
            else (setting if name == "web_search" or name in spec.tools else False)
            for name, setting in parent_builtin.items()
        }
        selected_consumer = [
            consumer_by_name[name] for name in spec.tools if name in consumer_by_name
        ]
    else:
        child_config["builtin_tools"] = {**parent_builtin, "subagent": False}
        selected_consumer = list(consumer_by_name.values())

    non_mcp = [t for t in selected_consumer if not isinstance(t, MCPClient)]
    isolated_tools = fresh_tools_for_delegate(non_mcp)
    selected_names = (
        mcp_clients_by_name if spec.mcp_servers is None else spec.mcp_servers
    )
    selected_mcp = [
        mcp_clients_by_name[name]
        for name in dict.fromkeys(selected_names)
        if name in mcp_clients_by_name
    ]
    child_config["tools"] = [*isolated_tools, *selected_mcp]


def _resolve_child_memory(parent_memory: Any) -> Any:
    """Share parent memory stores read-only, or False when parent memory is off."""
    if parent_memory is None or parent_memory is False:
        return False
    if isinstance(parent_memory, Mapping):
        return resolve_memory(
            stores=parent_memory.get("stores"),
            memory_dir=parent_memory.get("dir") or defaults.DEFAULT_MEMORY_DIR,
            writable=False,
        )
    return resolve_memory(writable=False)


def _resolve_child_model(
    spec: AgentSpec,
    parent: Any,
    parent_config: Mapping[str, Any],
    child_config: dict[str, Any],
    *,
    base_url: str | None = None,
    base_url_provider: str | None = None,
    api_mode: str | None = None,
) -> None:
    """Resolve explicit spec model or live parent model onto ``child_config``."""
    live_model = (
        getattr(parent, "model", None)
        if parent is not None
        else parent_config.get("model")
    )
    if spec.model is not None:
        if isinstance(spec.model, str):
            scoped = scoped_base_url(base_url, base_url_provider, spec.model)
            eff_mode = api_mode if scoped is not None else None
            normalized_spec = normalize_model_ref(spec.model)
            if _provider_of(normalized_spec) == "meta" or (
                scoped
                and _provider_of(normalized_spec) == "openai"
                and eff_mode == "chat"
            ):
                try:
                    child_config["model"] = resolve_harness_model(
                        normalized_spec, base_url=scoped, api_mode=eff_mode
                    )
                except ImportError:
                    child_config["model"] = spec.model
            else:
                child_config["model"] = spec.model
        else:
            child_config["model"] = spec.model
    elif live_model is not None:
        child_config["model"] = fresh_side_model(live_model)
    chosen = child_config.get("model")
    if isinstance(chosen, Model) or isinstance(
        getattr(chosen, "_strands_model_ref", None), str
    ):
        child_config["caching"] = False
        child_config.pop("effort", None)


def _strip_foreign_signatures_hook(parent_id: str, target_id: str):
    """Strip parent toolUse thought signatures before cross-provider child model calls."""

    def _on_before_model(event: Any) -> None:
        if (
            parent_id
            and target_id
            and supports_reasoning(target_id)
            and same_vendor(parent_id, target_id)
            and same_provider(parent_id, target_id)
        ):
            return
        agent_obj = getattr(event, "agent", None)
        for msg in getattr(agent_obj, "messages", None) or ():
            for blk in msg.get("content", ()):
                tu = blk.get("toolUse")
                if isinstance(tu, dict):
                    tu.pop("reasoningSignature", None)

    return _on_before_model


def _configure_child_agent(
    child: Any,
    parent: Any,
    child_config: Mapping[str, Any],
    base_url: str | None,
    base_url_provider: str | None,
) -> None:
    """Attach CLI gate identity/read-only posture, provider config, and memory."""
    gate = next(
        (
            handler
            for handler in (child_config.get("interventions") or ())
            if callable(getattr(handler, "register_agent", None))
        ),
        getattr(parent, "_policy_gate", None),
    )
    if gate is not None and callable(getattr(gate, "register_agent", None)):
        gate.register_agent(child, "subagent")
        child._policy_gate = gate
        is_ro = getattr(gate, "is_read_only", None)
        enter_ro = getattr(gate, "enter_read_only", None)
        if (
            parent is not None
            and callable(is_ro)
            and callable(enter_ro)
            and is_ro(parent)
        ):
            enter_ro(child)

    resolved_model = getattr(child, "model", None)
    raw_model = child_config.get("model")
    target_id = (
        raw_model if isinstance(raw_model, str) else model_id_of(resolved_model, "")
    )
    parent_id = model_id_of(getattr(parent, "model", None), "")
    if callable(getattr(child, "add_hook", None)):
        child.add_hook(
            _strip_foreign_signatures_hook(parent_id, target_id), BeforeModelCallEvent
        )
    configure_streaming_for_model(target_id, resolved_model)
    configure_gemini_for_model(target_id, resolved_model)
    configure_openai_for_model(target_id, resolved_model)
    configure_base_url_for_model(
        target_id,
        resolved_model,
        base_url=scoped_base_url(base_url, base_url_provider, target_id),
    )
    register_memory_plugin(child, load_memory)


def build_cli_subagent(
    parent_holder: Mapping[str, Any],
    parent_config: Mapping[str, Any],
    *,
    max_depth: int = defaults.DEFAULT_SUBAGENT_MAX_DEPTH,
) -> AgentTool:
    """Build the CLI ``subagent`` tool backed by :func:`make_subagent`."""
    raw_tools = list(parent_config.get("tools") or [])
    consumer_by_name: dict[str, Any] = {
        t.tool_name: t for t in raw_tools if hasattr(t, "tool_name")
    }
    mcp_clients_by_name = _mcp_clients_by_name(raw_tools)
    parent_builtin = {
        **_normalize_builtin_tools(parent_config.get("builtin_tools")),
        "subagent": False,
    }

    def builder(spec: AgentSpec) -> Any:
        child_config = dict(parent_config)
        base_url = child_config.pop("_base_url", None)
        base_url_provider = child_config.pop("_base_url_provider", None)
        api_mode = child_config.pop("_api_mode", None)
        steering_hook = child_config.pop("steering_hook", None)
        if "hooks" in child_config:
            child_config["hooks"] = [
                h for h in (child_config["hooks"] or ()) if h is not steering_hook
            ]
        if isinstance(child_config.get("context_manager"), ContextManager):
            child_config["context_manager"] = defaults.DEFAULT_CONTEXT_MANAGER
        parent = parent_holder.get("agent")
        if parent is not None:
            if hasattr(parent, "_base_url"):
                base_url = getattr(parent, "_base_url", None)
            if hasattr(parent, "_base_url_provider"):
                base_url_provider = getattr(parent, "_base_url_provider", None)
            if hasattr(parent, "_api_mode"):
                api_mode = getattr(parent, "_api_mode", None)
        _resolve_child_model(
            spec,
            parent,
            parent_config,
            child_config,
            base_url=base_url,
            base_url_provider=base_url_provider,
            api_mode=api_mode,
        )
        if spec.instructions is not None:
            child_config["instructions"] = spec.instructions
        _select_child_tools(
            spec, parent_builtin, consumer_by_name, mcp_clients_by_name, child_config
        )
        child_config["builtin_tools"] = reconcile_delegate_builtin_tools(
            child_config.get("builtin_tools"),
            child_config.get("model"),
            base_url=base_url,
            base_url_provider=base_url_provider,
            api_mode=api_mode,
        )
        child_config["memory"] = _resolve_child_memory(parent_config.get("memory"))
        child_config["session"] = False
        child_config["callback_handler"] = None
        child = create_harness(**child_config)
        _configure_child_agent(child, parent, child_config, base_url, base_url_provider)
        return child

    builtin_names = [
        name
        for name, setting in parent_builtin.items()
        if setting is not False and name != "web_search"
    ]
    inherited_tools = list(
        dict.fromkeys([*builtin_names, *consumer_by_name, "subagent"])
    )
    tool = make_subagent(
        builder=builder,
        presets={"generalist": GENERALIST},
        inherited_tools=inherited_tools,
        inherited_mcp_servers=list(mcp_clients_by_name),
        max_depth=max_depth,
        context=Choice(list(_CONTEXT_MODES)),
    )
    consumer_by_name["subagent"] = tool
    return tool
