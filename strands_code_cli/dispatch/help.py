"""Declarative slash command registry, /help renderer, and single-source USAGE_HINT (LOOP-06)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from strands_code_cli.ui.console import sanitize_display

if TYPE_CHECKING:
    from strands_code_cli.memory.skills import SkillIndex


@dataclass(frozen=True)
class CommandSpec:
    """Metadata describing one built-in slash command."""

    head: str
    usage: str
    category: str
    summary: str
    details: str = ""


CATEGORIES: tuple[str, ...] = (
    "Session",
    "Files, Search & Review",
    "Modes & Execution",
    "Models & Cost",
    "Context & Memory",
    "Skills & Help",
)

COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(
        head="resume",
        usage="/resume",
        category="Session",
        summary="Pick and resume a saved session (or switch by prefix).",
        details="Accepts an optional session id or unique prefix: /resume <id-or-prefix>.",
    ),
    CommandSpec(
        head="rename",
        usage="/rename <title>",
        category="Session",
        summary="Rename the current session in the local index.",
    ),
    CommandSpec(
        head="forget",
        usage="/forget <id>",
        category="Session",
        summary="Delete a saved session and its thinking stash (refuses active session).",
    ),
    CommandSpec(
        head="diff",
        usage="/diff [on-demand|auto|show [path]|apply [path]|discard [path]]",
        category="Files, Search & Review",
        summary="Inspect, apply, or discard pending edits and toggle diff review mode.",
    ),
    CommandSpec(
        head="search",
        usage="/search <pattern>",
        category="Files, Search & Review",
        summary="Search workspace files using ripgrep/glob filters.",
        details="Supports /search <pattern> [--glob <glob>] [--limit <n>].",
    ),
    CommandSpec(
        head="file",
        usage="/file [filter]",
        category="Files, Search & Review",
        summary="Open a workspace file picker and pre-fill @<path> into the next prompt.",
        details="Use @<path> inline in any prompt (text, images png/jpeg/gif/webp, or docs pdf/docx/xlsx).",
    ),
    CommandSpec(
        head="review",
        usage="/review [--staged|<base-ref>] [focus...]",
        category="Files, Search & Review",
        summary="Run a read-only diff review against HEAD, staged changes, or a base ref.",
        details="Supports optional focus text after target or `--`, keeping sticky /mode & /codeact unchanged.",
    ),
    CommandSpec(
        head="policy",
        usage="/policy [show|last]",
        category="Modes & Execution",
        summary="Inspect active allow/deny rules, Strands Box status, and last gate decision.",
    ),
    CommandSpec(
        head="mode",
        usage="/mode [plan|act]",
        category="Modes & Execution",
        summary="Show or switch session Plan (read-only) vs Act execution mode.",
    ),
    CommandSpec(
        head="approve",
        usage="/approve",
        category="Modes & Execution",
        summary="Approve the pending Plan-mode proposal and switch to Act mode.",
    ),
    CommandSpec(
        head="codeact",
        usage="/codeact [tool|code|both]",
        category="Modes & Execution",
        summary="Show or switch action interface between tool-calling, CodeAct, or explicit per-ask.",
    ),
    CommandSpec(
        head="code",
        usage="/code <ask>",
        category="Modes & Execution",
        summary="Run this turn using the CodeAct Python REPL interface.",
    ),
    CommandSpec(
        head="tool",
        usage="/tool <ask>",
        category="Modes & Execution",
        summary="Run this turn using direct tool-calling interface.",
    ),
    CommandSpec(
        head="model",
        usage="/model [provider/name|id|ARN]",
        category="Models & Cost",
        summary="Pick, search, or switch the active model mid-session.",
    ),
    CommandSpec(
        head="cost",
        usage="/cost [refresh|table [filter]]",
        category="Models & Cost",
        summary="Display session token/cost usage, refresh live pricing, or browse model rates.",
    ),
    CommandSpec(
        head="route",
        usage="/route [on|off|status|setup|validate]",
        category="Models & Cost",
        summary="Configure, validate, or toggle pre-turn automatic model routing.",
    ),
    CommandSpec(
        head="compact",
        usage="/compact",
        category="Context & Memory",
        summary="Summarize earlier conversation turns to reclaim context window space.",
    ),
    CommandSpec(
        head="clear",
        usage="/clear",
        category="Context & Memory",
        summary="Clear conversation history for the active session.",
    ),
    CommandSpec(
        head="context",
        usage="/context",
        category="Context & Memory",
        summary="Show estimated context usage, message counts, and capability overrides.",
    ),
    CommandSpec(
        head="btw",
        usage="/btw <side question>",
        category="Context & Memory",
        summary="Ask a parallel side question without disturbing the main task stream.",
    ),
    CommandSpec(
        head="memory",
        usage="/memory [mode [curate|silent]|list|approve <id>|deny <id>|approve-all|deny-all|revise <section> <instruction>]",
        category="Context & Memory",
        summary="Inspect, toggle curate/silent mode, approve, deny, or revise project memory.",
    ),
    CommandSpec(
        head="init",
        usage="/init [deeper]",
        category="Context & Memory",
        summary="Scan the repository and draft STRANDS.md / .agent/MEMORY.md conventions.",
    ),
    CommandSpec(
        head="skills",
        usage="/skills [marketplace|browse|install|update|sync|show|remove|reload]",
        category="Skills & Help",
        summary="Manage local and marketplace agent skills and lockfile verification.",
    ),
    CommandSpec(
        head="help",
        usage="/help [command|skill]",
        category="Skills & Help",
        summary="List grouped built-in commands + loaded skills or inspect one command/skill.",
    ),
    CommandSpec(
        head="exit",
        usage="/exit",
        category="Session",
        summary="Save session state, clean up workers, and exit strands-code.",
    ),
)

_BY_HEAD: dict[str, CommandSpec] = {spec.head: spec for spec in COMMANDS}


def build_usage_hint() -> str:
    """Build the single-line USAGE_HINT derived directly from COMMANDS (D-01)."""
    return "Available commands: " + ", ".join(spec.usage for spec in COMMANDS)


def lookup_command(name: str) -> CommandSpec | None:
    """Look up a built-in command by bare or /-prefixed head (case-insensitive)."""
    key = name.strip().lstrip("/").lower()
    return _BY_HEAD.get(key)


def _format_command_detail(spec: CommandSpec) -> str:
    lines = [
        f"/{spec.head} ({spec.category})",
        f"  Usage: {spec.usage}",
        f"  Summary: {spec.summary}",
    ]
    if spec.details:
        lines.append(f"  Details: {spec.details}")
    return "\n".join(lines)


def _format_skill_detail(entry) -> str:
    shadow_note = " [shadowed by built-in]" if entry.shadowed else ""
    lines = [
        f"/{sanitize_display(entry.namespaced)}{shadow_note}",
        f"  Skill: {sanitize_display(entry.name)} (source: {sanitize_display(entry.source)})",
        f"  Description: {sanitize_display(entry.description or '(no description)')}",
    ]
    if entry.path is not None:
        lines.append(f"  Path: {sanitize_display(entry.path)}")
    if entry.shadowed:
        lines.append(
            f"  Note: Built-in '/{sanitize_display(entry.name.lower())}' takes precedence"
            " — rename the skill to invoke it."
        )
    return "\n".join(lines)


def _format_overview(skills: SkillIndex | None) -> str:
    lines = ["Built-in commands:"]
    by_cat: dict[str, list[CommandSpec]] = {cat: [] for cat in CATEGORIES}
    for spec in COMMANDS:
        by_cat.setdefault(spec.category, []).append(spec)
    for cat in CATEGORIES:
        items = by_cat.get(cat, [])
        if not items:
            continue
        lines.append(f"  {cat}:")
        for spec in items:
            lines.append(f"    {spec.usage} — {spec.summary}")

    if skills is not None:
        entries = skills.list_entries()
        lines.append("")
        lines.append(f"Loaded skills ({len(entries)}):")
        if not entries:
            lines.append("  (none)")
        else:
            for entry in entries:
                flag = " [shadowed by built-in]" if entry.shadowed else ""
                desc = sanitize_display(entry.description or "")
                suffix = f" — {desc}" if desc else ""
                lines.append(f"  /{sanitize_display(entry.namespaced)}{flag}{suffix}")
        warnings = skills.warnings
        if warnings:
            lines.append("")
            lines.append("Warnings:")
            for warning in warnings:
                lines.append(f"  ! {sanitize_display(warning)}")

    lines.append("")
    lines.append(
        "Tip: Run /help <command|skill> for details, or @<file> / /file to attach files."
    )
    return "\n".join(lines)


def help_message(rest: str = "", skills: SkillIndex | None = None) -> str:
    """Render grouped /help overview or single-target command/skill help (D-02)."""
    query = rest.strip()
    if not query:
        return _format_overview(skills)
    target = query.split()[0]
    spec = lookup_command(target)
    if spec is not None:
        return _format_command_detail(spec)

    if skills is not None:
        stripped = target.lstrip("/")
        entry = skills.resolve(stripped)
        if entry is not None:
            return _format_skill_detail(entry)
        ambiguous = skills.ambiguous_matches(stripped)
        if ambiguous:
            options = ", ".join(
                f"/{sanitize_display(item.namespaced)}" for item in ambiguous
            )
            return (
                f"Ambiguous skill {sanitize_display(stripped)!r}; use one of: {options}"
            )

    safe_target = sanitize_display(target)
    return f"Unknown command or skill {safe_target!r}. Run /help to list available commands."
