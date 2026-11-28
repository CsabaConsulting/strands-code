"""Tests for declarative /help command registry, BUILTIN_SLASH_HEADS, and USAGE_HINT (LOOP-06)."""

from __future__ import annotations

from strands_code_cli.dispatch.core import USAGE_HINT, dispatch
from strands_code_cli.dispatch.help import (
    COMMANDS,
    build_usage_hint,
    help_message,
)
from strands_code_cli.memory.skills import BUILTIN_SLASH_HEADS, SkillIndex
from strands_code_cli.session.session_index import SessionIndex


def _write_skill(
    root,
    name: str,
    description: str = "Helpful skill",
    body: str = "Follow skill steps carefully.",
) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )


class TestHelpCommandRegistry:
    def test_builtin_slash_heads_matches_commands_one_to_one(self):
        declared = {spec.head for spec in COMMANDS}
        assert declared == BUILTIN_SLASH_HEADS
        assert {"help", "file", "review"} <= BUILTIN_SLASH_HEADS
        assert USAGE_HINT == build_usage_hint()

    def test_bare_help_lists_grouped_builtins_skills_and_sanitized_warnings(
        self, tmp_path
    ):
        skills_dir = tmp_path / ".agent" / "skills"
        _write_skill(skills_dir, "audit-deps", description="Check deps \u202efast")
        _write_skill(
            skills_dir, "review", description="Custom conflicting review skill"
        )
        skills = SkillIndex(skills_dir=skills_dir)
        skills.list_entries()
        skills._drift_warnings.append("Tampered \x1b[31mdrift\x1b[0m lockfile")

        action, msg = dispatch(
            "/help",
            session_id="s1",
            index=SessionIndex(tmp_path / "sessions"),
            skills=skills,
        )
        assert action == "reply"
        assert msg is not None
        assert "Built-in commands:" in msg
        assert "Files, Search & Review:" in msg
        assert "/help [command|skill]" in msg
        assert "/file [filter]" in msg
        assert "/review [--staged|<base-ref>] [focus...]" in msg
        assert "/local:audit-deps" in msg
        assert "/local:review [shadowed by built-in]" in msg
        assert "Warnings:" in msg
        assert "Skill 'review' shadowed by builtin '/review'" in msg
        assert "Tampered drift lockfile" in msg
        assert "\x1b" not in msg
        assert "\u202e" not in msg

    def test_help_lookup_handles_builtin_commands_with_or_without_slash(self, tmp_path):
        index = SessionIndex(tmp_path / "sessions")
        action1, msg1 = dispatch("/help model", session_id="s1", index=index)
        action2, msg2 = dispatch("/help /MODEL", session_id="s1", index=index)
        assert action1 == "reply" and action2 == "reply"
        assert msg1 == msg2
        assert msg1 is not None
        assert "/model (Models & Cost)" in msg1
        assert "/model [provider/name|id|ARN]" in msg1

    def test_help_lookup_resolves_skills_and_reports_shadow_or_unknown(self, tmp_path):
        skills_dir = tmp_path / ".agent" / "skills"
        _write_skill(skills_dir, "deploy-check", description="Pre-flight deploy check")
        skills = SkillIndex(skills_dir=skills_dir)
        index = SessionIndex(tmp_path / "sessions")

        action, msg = dispatch(
            "/help deploy-check", session_id="s1", index=index, skills=skills
        )
        assert action == "reply"
        assert msg is not None
        assert "/local:deploy-check" in msg
        assert "Pre-flight deploy check" in msg

        _, ns_msg = dispatch(
            "/help /local:deploy-check", session_id="s1", index=index, skills=skills
        )
        assert ns_msg == msg

        _, unknown = dispatch(
            "/help nope\x1b[31mx\x1b[0m", session_id="s1", index=index, skills=skills
        )
        assert unknown is not None
        assert "Unknown command or skill" in unknown
        assert "\x1b" not in unknown

    def test_builtin_help_wins_even_if_skill_named_help_exists(self, tmp_path):
        skills_dir = tmp_path / ".agent" / "skills"
        _write_skill(skills_dir, "help", description="Shadowed help skill")
        skills = SkillIndex(skills_dir=skills_dir)
        action, msg = dispatch(
            "/help",
            session_id="s1",
            index=SessionIndex(tmp_path / "sessions"),
            skills=skills,
        )
        assert action == "reply"
        assert msg is not None
        assert "Built-in commands:" in msg
        assert "/local:help [shadowed by built-in]" in msg

        detail = help_message("local:help", skills)
        assert "shadowed by built-in" in detail
        assert "Shadowed help skill" in detail
        assert "rename the skill to invoke it" in detail
        assert "invoke with /local:help" not in detail

        ns_act, ns_msg = dispatch(
            "/local:help extra",
            session_id="s1",
            index=SessionIndex(tmp_path / "sessions"),
            skills=skills,
        )
        assert ns_act == "reply"
        assert ns_msg is not None and "Unknown command" in ns_msg
