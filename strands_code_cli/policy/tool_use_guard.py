"""Fail-closed guard rejecting caller-supplied toolUse blocks (CVE-2026-18830 / CoreBreak)."""

from __future__ import annotations

from typing import Any

ALLOWLISTED_CONTENT_KEYS = frozenset({"text", "image", "document"})
"""Only these user ContentBlock keys may be constructed or sent in prompt lists."""

CALLER_TOOL_USE_ERROR = "Rejected caller-supplied toolUse block (CVE-2026-18830 guard)."


def contains_caller_tool_use(messages: Any) -> bool:
    """True when any incoming message or content block carries a ``toolUse`` entry."""
    if not isinstance(messages, (list, tuple)):
        return False
    for message in messages:
        if isinstance(message, dict) and "toolUse" in message:
            return True
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, (list, tuple)):
            continue
        for block in content:
            if isinstance(block, dict) and "toolUse" in block:
                return True
    return False


def validate_content_blocks(blocks: Any) -> list[dict[str, Any]]:
    """Validate that ``blocks`` contains strictly allowlisted ``text``/``image``/``document`` dicts.

    Raises:
        ValueError: When ``blocks`` is not a list/tuple, contains non-dicts,
            contains ``toolUse``, or uses any key outside ``ALLOWLISTED_CONTENT_KEYS``.
    """
    if not isinstance(blocks, (list, tuple)):
        raise ValueError("Content blocks must be a list of dicts.")
    validated: list[dict[str, Any]] = []
    for idx, block in enumerate(blocks):
        if not isinstance(block, dict):
            raise ValueError(f"Content block at index {idx} must be a dict.")
        keys = set(block.keys())
        if "toolUse" in keys:
            raise ValueError(CALLER_TOOL_USE_ERROR)
        if not keys or not keys.issubset(ALLOWLISTED_CONTENT_KEYS):
            bad = sorted(keys - ALLOWLISTED_CONTENT_KEYS)
            raise ValueError(
                f"Disallowed ContentBlock keys at index {idx}: {bad or ['<empty>']}"
            )
        validated.append(block)
    return validated


class RejectCallerToolUseHook:
    """Fail-closed ``BeforeInvocationEvent`` hook blocking caller-supplied ``toolUse`` blocks."""

    def on_before_invocation(self, event: Any) -> None:
        if contains_caller_tool_use(getattr(event, "messages", None)):
            event.cancel = CALLER_TOOL_USE_ERROR


def register_reject_caller_tool_use_hook(agent: Any) -> None:
    """Register the CVE-2026-18830 fail-closed guard on ``agent`` (idempotent)."""
    if agent is None or getattr(agent, "_reject_tool_use_hook_registered", False):
        return
    add_hook = getattr(agent, "add_hook", None)
    if not callable(add_hook):
        return
    from strands.hooks import HookOrder
    from strands.hooks.events import BeforeInvocationEvent

    hook = RejectCallerToolUseHook()
    try:
        add_hook(
            hook.on_before_invocation, BeforeInvocationEvent, order=HookOrder.SDK_FIRST
        )
    except TypeError:
        # Test doubles defining two-arg add_hook(cb, event_type) omit order=.
        add_hook(hook.on_before_invocation, BeforeInvocationEvent)
    try:
        agent._reject_tool_use_hook = hook
        agent._reject_tool_use_hook_registered = True
    except (AttributeError, TypeError):
        pass
