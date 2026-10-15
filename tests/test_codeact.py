"""Phase 11 tracer + /codeact interface-toggle tests (TOOL-07; offline only).

Tracer observations (11-01-PLAN.md task 1, all offline, no live model):

- The toggle-to-turn pipeline is three pure seams: ``dispatch``
  flips the loop-owned holder, ``resolve_turn_interface`` fixes the
  turn's interface at send (D-14/D-19), and ``shape_turn_text`` plus
  ``codeact_label`` shape the turn and its transcript line (D-15).
- ``both`` runs tool-shaped until per-ask routing lands (11-02):
  the holder accepts it, turn setup resolves it to ``tool``.
- Interface records ride a loop-owned parallel list, never the
  ``session_turns`` rows (D-16) — cost rows stay byte-identical.

Invariants pinned here: tool-calling default with CodeAct never
mandatory; one interface per turn fixed at send; every turn labeled;
zero history mutation on switch; zero cost-row change.
"""

from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace

from strands_code_cli.codeact import (
    CODEACT_BOTH_REPLY,
    CODEACT_CODE_REPLY,
    CODEACT_PREFIX,
    CODEACT_TOOL_REPLY,
    CODEACT_USAGE,
    CodeactState,
    codeact_label,
    resolve_turn_interface,
    shape_turn_text,
)
from strands_code_cli.router import USAGE_HINT, dispatch
from strands_code_cli.session_index import SessionIndex
from strands_code_cli.skills import BUILTIN_SLASH_HEADS, SkillIndex


CODEACT_BANNED_VOCAB = (
    "Mode:",
    "plan mode",
    "act mode",
    "policy rule",
    "rule [",
    "approve-each",
    "on-demand",
    "/diff",
    "yolo",
)


class _Summary:
    """Minimal response double exposing metrics.get_summary()."""

    def __init__(self, in_tok: int, out_tok: int):
        self._summary = {
            "accumulated_usage": {"inputTokens": in_tok, "outputTokens": out_tok},
            "total_cycles": 1,
            "total_duration": 0.5,
        }

    @property
    def metrics(self):
        outer = self

        class _Metrics:
            def get_summary(self):
                return dict(outer._summary)

        return _Metrics()


def _write_skill(skills_dir: Path, name: str) -> Path:
    """Build one ``<name>/SKILL.md`` fixture tree under skills_dir."""
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Does something useful.\n---\n# Instructions\n",
        encoding="utf-8",
    )
    return skill_dir


# ----------------------------------------------------------------------
# Holder
# ----------------------------------------------------------------------


class TestCodeactState:
    def test_fresh_holder_defaults_to_tool(self):
        assert CodeactState().interface == "tool"

    def test_valid_values(self):
        assert CodeactState.VALID == ("tool", "code", "both")

    def test_init_each_value(self):
        for value in CodeactState.VALID:
            assert CodeactState(initial=value).interface == value

    def test_init_unknown_raises(self):
        try:
            CodeactState(initial="turbo")
        except ValueError as exc:
            assert "tool|code|both" in str(exc)
        else:
            raise AssertionError("expected ValueError")

    def test_set_each_value_announces_and_flips(self):
        holder = CodeactState()
        assert holder.set("code") == CODEACT_CODE_REPLY
        assert holder.interface == "code"
        assert holder.set("both") == CODEACT_BOTH_REPLY
        assert holder.interface == "both"
        assert holder.set("tool") == CODEACT_TOOL_REPLY
        assert holder.interface == "tool"

    def test_set_unknown_raises_and_keeps_value(self):
        holder = CodeactState(initial="code")
        try:
            holder.set("turbo")
        except ValueError as exc:
            assert "tool|code|both" in str(exc)
        else:
            raise AssertionError("expected ValueError")
        assert holder.interface == "code"

    def test_announce_reports_current(self):
        assert CodeactState(initial="tool").announce() == CODEACT_TOOL_REPLY
        assert CodeactState(initial="code").announce() == CODEACT_CODE_REPLY
        assert CodeactState(initial="both").announce() == CODEACT_BOTH_REPLY

    def test_replies_use_interface_vocabulary_only(self):
        for copy in (CODEACT_TOOL_REPLY, CODEACT_CODE_REPLY, CODEACT_BOTH_REPLY):
            for banned in CODEACT_BANNED_VOCAB:
                assert banned not in copy


# ----------------------------------------------------------------------
# Router: /codeact branch
# ----------------------------------------------------------------------


class TestRouterCodeact:
    def _dispatch(self, text: str, tmp_path, interface=None):  # type: ignore[no-untyped-def]
        index = SessionIndex(tmp_path / "index")
        return dispatch(text, session_id="s", index=index, interface=interface)

    def test_codeact_bare_reports_current(self, tmp_path):
        holder = CodeactState()
        assert self._dispatch("/codeact", tmp_path, holder) == ("reply", CODEACT_TOOL_REPLY)
        holder.set("code")
        assert self._dispatch("/codeact", tmp_path, holder) == ("reply", CODEACT_CODE_REPLY)
        holder.set("both")
        assert self._dispatch("/codeact", tmp_path, holder) == ("reply", CODEACT_BOTH_REPLY)

    def test_codeact_switch_names_code_and_sticks(self, tmp_path):
        holder = CodeactState()
        action, message = self._dispatch("/codeact code", tmp_path, holder)
        assert action == "reply"
        assert "code" in message
        assert holder.interface == "code"

    def test_codeact_switch_each_value(self, tmp_path):
        holder = CodeactState()
        for verb, reply in (
            ("tool", CODEACT_TOOL_REPLY),
            ("code", CODEACT_CODE_REPLY),
            ("both", CODEACT_BOTH_REPLY),
        ):
            assert self._dispatch(f"/codeact {verb}", tmp_path, holder) == ("reply", reply)
            assert holder.interface == verb

    def test_codeact_bogus_usage_never_agent_turn(self, tmp_path):
        holder = CodeactState(initial="code")
        action, message = self._dispatch("/codeact turbo", tmp_path, holder)
        assert action == "reply"
        assert message == CODEACT_USAGE
        assert holder.interface == "code"

    def test_codeact_without_holder_replies_tool_default(self, tmp_path):
        assert self._dispatch("/codeact", tmp_path, None) == ("reply", CODEACT_TOOL_REPLY)
        action, message = self._dispatch("/codeact bogus", tmp_path, None)
        assert action == "reply"
        assert message == CODEACT_USAGE

    def test_codeact_never_starts_agent_turn(self, tmp_path):
        holder = CodeactState()
        for text in ("/codeact", "/codeact tool", "/codeact code", "/codeact both", "/codeact nope"):
            action, _ = self._dispatch(text, tmp_path, holder)
            assert action == "reply"

    def test_usage_hint_lists_codeact(self):
        assert "/codeact [tool|code|both]" in USAGE_HINT

    def test_codeact_is_builtin_head(self):
        assert "codeact" in BUILTIN_SLASH_HEADS

    def test_codeact_beats_shadowed_skill(self, tmp_path):
        skills_dir = tmp_path / "skills"
        _write_skill(skills_dir, "codeact")
        skills = SkillIndex(skills_dir)
        assert skills.warnings  # shadow warning automatic (T-11-03)
        holder = CodeactState()
        index = SessionIndex(tmp_path / "index")
        action, message = dispatch(
            "/codeact code", session_id="s", index=index, skills=skills, interface=holder
        )
        assert action == "reply"
        assert message == CODEACT_CODE_REPLY
        assert holder.interface == "code"


# ----------------------------------------------------------------------
# Turn setup: fix-at-send + prefix shaping
# ----------------------------------------------------------------------


class TestTurnSetup:
    def test_resolve_each_holder_value(self):
        assert resolve_turn_interface("tool") == "tool"
        assert resolve_turn_interface("code") == "code"
        # Both runs tool-shaped until per-ask routing lands (11-02).
        assert resolve_turn_interface("both") == "tool"

    def test_resolve_unknown_raises(self):
        try:
            resolve_turn_interface("turbo")
        except ValueError as exc:
            assert "tool|code|both" in str(exc)
        else:
            raise AssertionError("expected ValueError")

    def test_code_turn_prepends_prefix(self):
        shaped = shape_turn_text("code", "list the files")
        assert shaped == f"{CODEACT_PREFIX}\n\nlist the files"

    def test_tool_turn_byte_identical(self):
        text = "list the files"
        shaped = shape_turn_text("tool", text)
        assert shaped == text
        assert shaped is text
        assert CODEACT_PREFIX not in shaped

    def test_fix_at_send_snapshot(self):
        holder = CodeactState(initial="code")
        resolved = resolve_turn_interface(holder.interface)
        holder.set("tool")  # a later flip must not move the fixed turn
        assert resolved == "code"
        assert shape_turn_text(resolved, "go").startswith(CODEACT_PREFIX)


# ----------------------------------------------------------------------
# Prefix content + vocabulary
# ----------------------------------------------------------------------


class TestCodeactPrefix:
    def test_prefix_names_execution_surface(self):
        for name in ("python_repl", "read", "write", "edit", "shell"):
            assert name in CODEACT_PREFIX

    def test_prefix_states_paths_and_scope(self):
        assert "absolute paths" in CODEACT_PREFIX
        assert "working directory" in CODEACT_PREFIX
        assert "/tmp" in CODEACT_PREFIX

    def test_prefix_states_one_interface_per_turn(self):
        assert "one interface per turn" in CODEACT_PREFIX.lower()

    def test_prefix_vocabulary_lock(self):
        lowered = CODEACT_PREFIX.lower()
        for banned in ("policy", "approve-each", "on-demand", "auto", "yolo", "plan mode"):
            assert banned not in lowered


# ----------------------------------------------------------------------
# Labels
# ----------------------------------------------------------------------


class TestCodeactLabel:
    def test_exact_label_lines(self):
        assert codeact_label("code") == "interface: codeact"
        assert codeact_label("tool") == "interface: tool"


# ----------------------------------------------------------------------
# History + cost rows untouched
# ----------------------------------------------------------------------


class TestCodeactHistory:
    def test_switch_leaves_history_byte_identical(self, tmp_path):
        holder = CodeactState()
        agent = SimpleNamespace(
            messages=[
                {"role": "user", "content": [{"text": "q"}]},
                {"role": "assistant", "content": [{"text": "a"}]},
            ]
        )
        before = copy.deepcopy(agent.messages)
        index = SessionIndex(tmp_path / "index")
        for verb in ("code", "both", "tool"):
            dispatch("/codeact " + verb, session_id="s", index=index, agent=agent, interface=holder)
        assert agent.messages == before


class TestCodeactCostRows:
    def test_session_turn_row_keys_unchanged(self):
        from strands_code_cli.loop import record_turn_metrics

        turns: list = []
        record_turn_metrics(_Summary(1000, 200), "bedrock/x-model", turns)
        assert len(turns) == 1
        assert set(turns[0]) == {"turn", "input_tokens", "output_tokens", "model"}
        assert "interface" not in turns[0]


# ----------------------------------------------------------------------
# Tracer: toggle -> shaped turn -> label, end to end
# ----------------------------------------------------------------------


class TestTracer:
    def test_codeact_code_to_shaped_turn_to_label(self, tmp_path):
        holder = CodeactState()
        index = SessionIndex(tmp_path / "index")
        action, message = dispatch(
            "/codeact code", session_id="s", index=index, interface=holder
        )
        assert action == "reply"
        assert holder.interface == "code"
        turn = resolve_turn_interface(holder.interface)
        shaped = shape_turn_text(turn, "list the files")
        label = codeact_label(turn)
        assert shaped.startswith(CODEACT_PREFIX)
        transcript = f"{message}\n{label}"
        assert transcript.count("interface: codeact") == 1
        assert "interface: tool" not in transcript

    def test_default_tool_turn_unshaped_with_tool_label(self, tmp_path):
        holder = CodeactState()
        index = SessionIndex(tmp_path / "index")
        action, message = dispatch("/codeact", session_id="s", index=index, interface=holder)
        assert action == "reply"
        assert holder.interface == "tool"
        turn = resolve_turn_interface(holder.interface)
        ask = "list the files"
        assert shape_turn_text(turn, ask) == ask
        transcript = f"{message}\n{codeact_label(turn)}"
        assert transcript.count("interface: tool") == 1
        assert "interface: codeact" not in transcript
