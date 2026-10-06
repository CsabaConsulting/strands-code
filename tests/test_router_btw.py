"""Idle /btw dispatch: normal inline turn plus builtin-head protection (LOOP-03, D-01)."""

from __future__ import annotations

from pathlib import Path

from strands_code_cli.router import USAGE_HINT, dispatch
from strands_code_cli.session_index import SessionIndex
from strands_code_cli.skills import SkillIndex


def _session_index(tmp_path: Path) -> SessionIndex:
    return SessionIndex(tmp_path / "index")


def _write_skill(skills_dir: Path, name: str, body: str = "# Btw\nSide me.") -> Path:
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: A btw skill.\n---\n{body}\n",
        encoding="utf-8",
    )
    return skill_dir


class TestBtwIdleDispatch:
    def test_btw_with_question_routes_agent_verbatim(self, tmp_path):
        action, message = dispatch(
            "/btw why is this slow?",
            session_id="s",
            index=_session_index(tmp_path),
        )
        assert (action, message) == ("agent", "why is this slow?")

    def test_bare_btw_returns_usage(self, tmp_path):
        action, message = dispatch(
            "/btw", session_id="s", index=_session_index(tmp_path)
        )
        assert (action, message) == ("reply", "Usage: /btw <side question>")

    def test_btw_skill_stays_shadowed_while_branch_wins(self, tmp_path):
        skills_dir = tmp_path / ".agent" / "skills"
        _write_skill(skills_dir, "btw")
        index = SkillIndex(skills_dir=skills_dir)
        action, message = dispatch(
            "/btw q",
            session_id="s",
            index=_session_index(tmp_path),
            skills=index,
        )
        assert action == "agent"
        assert message == "q"
        assert any(
            "shadowed by builtin '/btw'" in warning for warning in index.warnings
        )

    def test_usage_hint_advertises_btw(self):
        assert "/btw <side question>" in USAGE_HINT
