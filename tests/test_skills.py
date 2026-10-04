"""Local skills: index load, slash routing, /skills command, completer (SKILL-01).

SDK seam (observed in the installed source): ``from
strands.vended_plugins.skills import Skill`` — ``Skill.from_directory``
loads one skill per subdirectory, skips dirs without SKILL.md, and
warn-and-skips malformed skills (lenient default). No live model and no
network is touched here; fixtures are tmp_path-built skill trees.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from prompt_toolkit.completion import CompleteEvent, DynamicCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.history import InMemoryHistory

import strands_code_cli.loop as loop_module
from strands_code_cli.completer import SlashCompleter, build_completer
from strands_code_cli.router import USAGE_HINT, dispatch
from strands_code_cli.session_index import SessionIndex
from strands_code_cli.skills import BUILTIN_SLASH_HEADS, SkillIndex, remove_skill


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

    def test_memory_skill_shadowed_by_memory_builtin(self, tmp_path):
        skills_dir = tmp_path / ".agent" / "skills"
        _write_skill(skills_dir, "memory", description="Tries to hijack /memory.")
        index = SkillIndex(skills_dir=skills_dir)
        action, message = dispatch(
            "/memory",
            session_id="s1",
            index=_session_index(tmp_path),
            skills=index,
        )
        assert action == "reply"  # the memory branch, never the skill
        assert message is not None and "local:memory" not in message
        assert (
            "Skill 'memory' shadowed by builtin '/memory'"
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


# ----------------------------------------------------------------------
# /skills list/show/remove
# ----------------------------------------------------------------------


class TestSkillsCommand:
    def test_bare_list_sorted_with_shadowed_tag(self, tmp_path):
        skills_dir = tmp_path / ".agent" / "skills"
        _write_skill(skills_dir, "b-tools", description="Bee tools.")
        _write_skill(skills_dir, "a-tools", description="Ay tools.")
        _write_skill(skills_dir, "model", description="Hijack attempt.")
        index = SkillIndex(skills_dir=skills_dir)
        action, message = dispatch(
            "/skills", session_id="s1", index=_session_index(tmp_path), skills=index
        )
        assert action == "reply"
        assert message is not None
        assert "local:a-tools — Ay tools." in message
        assert "local:b-tools — Bee tools." in message
        assert message.index("local:a-tools") < message.index("local:b-tools")
        assert "local:model — shadowed by builtin '/model'" in message

    def test_bare_list_empty_or_missing_reports_no_skills(self, tmp_path):
        missing = SkillIndex(skills_dir=tmp_path / ".agent" / "skills")
        action, message = dispatch(
            "/skills", session_id="s1", index=_session_index(tmp_path), skills=missing
        )
        assert (action, message) == (
            "reply",
            "No skills loaded (./.agent/skills missing or empty).",
        )
        action, message = dispatch(
            "/skills", session_id="s1", index=_session_index(tmp_path), skills=None
        )
        assert (action, message) == (
            "reply",
            "No skills loaded (./.agent/skills missing or empty).",
        )

    def test_show_returns_full_record_with_allowed_tools_verbatim(self, tmp_path):
        skills_dir = tmp_path / ".agent" / "skills"
        _write_skill(
            skills_dir,
            "pdf-tools",
            description="Extract text from PDFs.",
            extra_frontmatter="allowed-tools: Read Bash\n",
        )
        index = SkillIndex(skills_dir=skills_dir)
        action, message = dispatch(
            "/skills show pdf-tools",
            session_id="s1",
            index=_session_index(tmp_path),
            skills=index,
        )
        assert action == "reply"
        assert message is not None
        assert "pdf-tools (local:pdf-tools)" in message
        assert "Extract text from PDFs." in message
        assert "Allowed tools: Read Bash" in message
        assert "SKILL.md" not in message  # path points at the skill dir
        assert str(skills_dir / "pdf-tools") in message

    def test_show_unknown_skill(self, tmp_path):
        index = SkillIndex(skills_dir=tmp_path / ".agent" / "skills")
        action, message = dispatch(
            "/skills show nope",
            session_id="s1",
            index=_session_index(tmp_path),
            skills=index,
        )
        assert (action, message) == ("reply", "Unknown skill 'nope'.")

    def test_remove_deletes_skill_dir(self, tmp_path):
        skills_dir = tmp_path / ".agent" / "skills"
        target = _write_skill(skills_dir, "gone")
        _write_skill(skills_dir, "stays")
        index = SkillIndex(skills_dir=skills_dir)
        action, message = dispatch(
            "/skills remove gone",
            session_id="s1",
            index=_session_index(tmp_path),
            skills=index,
        )
        assert (action, message) == ("reply", "Removed skill 'local:gone'.")
        assert not target.exists()
        assert (skills_dir / "stays").is_dir()
        assert index.resolve("gone") is None  # evicted, not just deleted

    def test_remove_traversal_name_leaves_tree_intact(self, tmp_path):
        skills_dir = tmp_path / ".agent" / "skills"
        _write_skill(skills_dir, "stays")
        index = SkillIndex(skills_dir=skills_dir)
        action, message = dispatch(
            "/skills remove ../x",
            session_id="s1",
            index=_session_index(tmp_path),
            skills=index,
        )
        assert (action, message) == ("reply", "Unknown skill '../x'.")
        assert (skills_dir / "stays" / "SKILL.md").is_file()

    def test_remove_skill_helper_refuses_traversal_directly(self, tmp_path):
        skills_dir = tmp_path / ".agent" / "skills"
        _write_skill(skills_dir, "stays")
        assert remove_skill(skills_dir, "../x") is False
        assert remove_skill(skills_dir, "missing") is False
        assert (skills_dir / "stays" / "SKILL.md").is_file()

    def test_remove_symlinked_skill_dir_refused(self, tmp_path):
        skills_dir = tmp_path / ".agent" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        outside = tmp_path / "outside"
        _write_skill(outside, "linky")
        (skills_dir / "linky").symlink_to(outside / "linky", target_is_directory=True)
        index = SkillIndex(skills_dir=skills_dir)
        assert index.resolve("linky") is not None  # symlinked skill still loads
        action, message = dispatch(
            "/skills remove linky",
            session_id="s1",
            index=_session_index(tmp_path),
            skills=index,
        )
        assert action == "reply"
        assert message is not None and "Refused to remove skill 'local:linky'" in message
        assert (outside / "linky" / "SKILL.md").is_file()

    def test_unknown_verb_returns_usage(self, tmp_path):
        index = SkillIndex(skills_dir=tmp_path / ".agent" / "skills")
        action, message = dispatch(
            "/skills frobnicate x",
            session_id="s1",
            index=_session_index(tmp_path),
            skills=index,
        )
        assert action == "reply"
        assert message is not None
        assert "Unknown /skills verb 'frobnicate'." in message
        assert "Usage: /skills [show <name>|remove <name>]" in message

    def test_usage_hint_advertises_skills(self):
        assert "/skills [show <name>|remove <name>]" in USAGE_HINT


def _loop_style_words(index: SkillIndex) -> list[tuple[str, str]]:
    """Word callable mirroring the loop: builtins plus unshadowed skills."""
    words = [(head, f"/{head}") for head in sorted(BUILTIN_SLASH_HEADS)]
    words.extend(
        (entry.name, entry.namespaced)
        for entry in index.list_entries()
        if not entry.shadowed
    )
    return words


# ----------------------------------------------------------------------
# Skill completer + loop wiring
# ----------------------------------------------------------------------


class TestSkillCompleter:
    def test_skill_bare_prefix_completes_namespaced_form(self, tmp_path):
        skills_dir = tmp_path / ".agent" / "skills"
        _write_skill(skills_dir, "pdf-tools")
        index = SkillIndex(skills_dir=skills_dir)
        completer = SlashCompleter(lambda: _loop_style_words(index))
        completions = list(
            completer.get_completions(Document("/pd"), CompleteEvent())
        )
        assert any(c.text == "local:pdf-tools" for c in completions)

    def test_shadowed_skill_never_completes_builtin_head_intact(self, tmp_path):
        skills_dir = tmp_path / ".agent" / "skills"
        _write_skill(skills_dir, "model")
        _write_skill(skills_dir, "pdf-tools")
        index = SkillIndex(skills_dir=skills_dir)
        completer = SlashCompleter(lambda: _loop_style_words(index))
        completions = list(
            completer.get_completions(Document("/model"), CompleteEvent())
        )
        assert any(c.text == "/model" for c in completions)
        assert all(not c.text.startswith("local:") for c in completions)

    def test_removed_skill_stops_completing(self, tmp_path):
        skills_dir = tmp_path / ".agent" / "skills"
        _write_skill(skills_dir, "pdf-tools")
        index = SkillIndex(skills_dir=skills_dir)
        completer = SlashCompleter(lambda: _loop_style_words(index))
        assert any(
            c.text == "local:pdf-tools"
            for c in completer.get_completions(Document("/pd"), CompleteEvent())
        )
        assert index.remove("pdf-tools") is True
        assert (
            list(completer.get_completions(Document("/pd"), CompleteEvent())) == []
        )

    def test_trailing_space_yields_no_completions(self, tmp_path):
        skills_dir = tmp_path / ".agent" / "skills"
        _write_skill(skills_dir, "pdf-tools")
        index = SkillIndex(skills_dir=skills_dir)
        completer = SlashCompleter(lambda: _loop_style_words(index))
        assert (
            list(
                completer.get_completions(Document("/pdf-tools "), CompleteEvent())
            )
            == []
        )

    def test_fuzzy_wrapped_completer_keeps_skill_match(self, tmp_path):
        skills_dir = tmp_path / ".agent" / "skills"
        _write_skill(skills_dir, "pdf-tools")
        index = SkillIndex(skills_dir=skills_dir)
        completer = build_completer(lambda: _loop_style_words(index))
        assert isinstance(completer, DynamicCompleter)
        completions = list(
            completer.get_completions(Document("/pd"), CompleteEvent())
        )
        match = [c for c in completions if c.text == "local:pdf-tools"]
        assert len(match) == 1
        assert match[0].start_position == -len("/pd")

    def test_loop_wires_completer_exactly_once(self):
        loop_source = (
            Path(__file__).resolve().parent.parent
            / "strands_code_cli"
            / "loop.py"
        ).read_text(encoding="utf-8")
        assert loop_source.count("completer=build_completer") == 1

    def test_run_loop_startup_prints_shadow_warnings_once(
        self, tmp_path, monkeypatch, capsys
    ):
        skills_dir = tmp_path / ".agent" / "skills"
        _write_skill(skills_dir, "model")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(loop_module, "_history", lambda: InMemoryHistory())

        seen: dict = {}

        class _FakeSession:
            def __init__(self, history=None, completer=None):
                seen["history"] = history
                seen["completer"] = completer

            def prompt(self, *args, **kwargs):
                raise EOFError

        monkeypatch.setattr(loop_module, "PromptSession", _FakeSession)
        agent = SimpleNamespace(messages=[], add_hook=lambda *a, **k: None)
        loop_module.run_loop(
            agent,
            session_id="startup-warn",
            index=SessionIndex(tmp_path / "index"),
            model_id="test-model",
        )
        out = capsys.readouterr().out
        assert out.count("Skill 'model' shadowed by builtin '/model'") == 1
        assert isinstance(seen["completer"], DynamicCompleter)
