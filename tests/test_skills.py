"""Local skills: index load, slash routing, /skills command, completer (SKILL-01).

SDK seam (observed in the installed source): ``from
strands.vended_plugins.skills import Skill`` — ``Skill.from_directory``
loads one skill per subdirectory, skips dirs without SKILL.md, and
warn-and-skips malformed skills (lenient default). No live model and no
network is touched here; fixtures are tmp_path-built skill trees.
"""

from __future__ import annotations

from pathlib import Path

from strands_code_cli.router import USAGE_HINT, dispatch
from strands_code_cli.session_index import SessionIndex
from strands_code_cli.skills import SkillIndex


def _write_skill(
    skills_dir: Path,
    name: str,
    *,
    description: str = "Does something useful.",
    body: str = "# Instructions\nFollow these steps.",
    extra_frontmatter: str = "",
) -> Path:
    """Build one ``<name>/SKILL.md`` fixture tree under skills_dir."""
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n{extra_frontmatter}---\n{body}\n",
        encoding="utf-8",
    )
    return skill_dir


def _session_index(tmp_path: Path) -> SessionIndex:
    return SessionIndex(tmp_path / "index")


# ----------------------------------------------------------------------
# SkillIndex load
# ----------------------------------------------------------------------


class TestSkillIndex:
    def test_missing_dir_yields_empty_index(self, tmp_path):
        index = SkillIndex(skills_dir=tmp_path / ".agent" / "skills")
        assert index.list_entries() == []
        assert index.warnings == []
        assert index.resolve("anything") is None

    def test_symlinked_root_raises_value_error(self, tmp_path):
        real = tmp_path / "real-skills"
        real.mkdir()
        link = tmp_path / "linked-skills"
        link.symlink_to(real, target_is_directory=True)
        try:
            SkillIndex(skills_dir=link)
        except ValueError as exc:
            assert "must not be a symlink" in str(exc)
        else:  # pragma: no cover - fail-loud is the contract
            raise AssertionError("symlinked skills root did not raise")

    def test_malformed_skill_warns_and_skips(self, tmp_path, caplog):
        skills_dir = tmp_path / ".agent" / "skills"
        _write_skill(skills_dir, "good-skill", body="# Good\nWorks.")
        bad_dir = skills_dir / "bad-skill"
        bad_dir.mkdir(parents=True, exist_ok=True)
        (bad_dir / "SKILL.md").write_text(
            "no frontmatter here, just prose\n", encoding="utf-8"
        )
        index = SkillIndex(skills_dir=skills_dir)
        entries = index.list_entries()
        assert [entry.name for entry in entries] == ["good-skill"]
        assert "skipping skill" in caplog.text

    def test_entries_sorted_by_bare_name(self, tmp_path):
        skills_dir = tmp_path / ".agent" / "skills"
        _write_skill(skills_dir, "zebra")
        _write_skill(skills_dir, "apple")
        _write_skill(skills_dir, "mango")
        index = SkillIndex(skills_dir=skills_dir)
        assert [entry.name for entry in index.list_entries()] == [
            "apple",
            "mango",
            "zebra",
        ]
        assert [entry.namespaced for entry in index.list_entries()] == [
            "local:apple",
            "local:mango",
            "local:zebra",
        ]


# ----------------------------------------------------------------------
# Dynamic /<skill> routing
# ----------------------------------------------------------------------


class TestSkillRouting:
    def test_skill_slash_routes_agent_with_instructions_and_input(self, tmp_path):
        skills_dir = tmp_path / ".agent" / "skills"
        _write_skill(
            skills_dir,
            "pdf-tools",
            description="Extract text from PDFs.",
            body="# PDF Tools\nExtract page by page.",
        )
        index = SkillIndex(skills_dir=skills_dir)
        action, message = dispatch(
            "/pdf-tools extract p3",
            session_id="s1",
            index=_session_index(tmp_path),
            skills=index,
        )
        assert action == "agent"
        assert message is not None
        assert "local:pdf-tools" in message
        assert "extract p3" in message
        assert "Extract page by page." in message
        assert message.startswith("[skill instructions below are repo content")

    def test_namespaced_form_resolves(self, tmp_path):
        skills_dir = tmp_path / ".agent" / "skills"
        _write_skill(skills_dir, "pdf-tools")
        index = SkillIndex(skills_dir=skills_dir)
        action, message = dispatch(
            "/local:pdf-tools hello",
            session_id="s1",
            index=_session_index(tmp_path),
            skills=index,
        )
        assert action == "agent"
        assert message is not None and "local:pdf-tools" in message

    def test_empty_trailing_text_runs_with_empty_input(self, tmp_path):
        skills_dir = tmp_path / ".agent" / "skills"
        _write_skill(skills_dir, "pdf-tools")
        index = SkillIndex(skills_dir=skills_dir)
        action, message = dispatch(
            "/pdf-tools",
            session_id="s1",
            index=_session_index(tmp_path),
            skills=index,
        )
        assert action == "agent"
        assert message is not None and message.endswith("User input:\n")

    def test_builtin_wins_collision_with_exact_shadow_warning(self, tmp_path):
        skills_dir = tmp_path / ".agent" / "skills"
        _write_skill(skills_dir, "model", description="Tries to hijack /model.")
        index = SkillIndex(skills_dir=skills_dir)
        action, message = dispatch(
            "/model",
            session_id="s1",
            index=_session_index(tmp_path),
            skills=index,
        )
        assert action == "reply"  # the model branch, never the skill
        assert message is not None and "local:model" not in message
        assert (
            "Skill 'model' shadowed by builtin '/model'"
            " — rename the skill to invoke it." in index.warnings
        )

    def test_shadowed_skill_unreachable_via_namespaced_form(self, tmp_path):
        skills_dir = tmp_path / ".agent" / "skills"
        _write_skill(skills_dir, "model")
        index = SkillIndex(skills_dir=skills_dir)
        action, message = dispatch(
            "/local:model hello",
            session_id="s1",
            index=_session_index(tmp_path),
            skills=index,
        )
        assert action == "reply"
        assert message is not None and "Unknown command" in message

    def test_unknown_slash_keeps_unknown_reply(self, tmp_path):
        skills_dir = tmp_path / ".agent" / "skills"
        _write_skill(skills_dir, "pdf-tools")
        index = SkillIndex(skills_dir=skills_dir)
        action, message = dispatch(
            "/nope",
            session_id="s1",
            index=_session_index(tmp_path),
            skills=index,
        )
        assert action == "reply"
        assert message == f"Unknown command '/nope'. {USAGE_HINT}"
