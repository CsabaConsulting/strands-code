"""SKILL-02 curation surface: curate queue, revise rounds, /init scan.

Hermetic by construction: canned turn text only, tmp fixtures only —
no live model, no network. Loop-hook wiring is asserted via the
consumer functions plus source assertions, never a live REPL.
"""

from __future__ import annotations

import sys
import threading
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from strands_code_cli.loop import (
    _drain_revise_rounds,
    _result_text,
    consume_revise_turn,
    review_memory_queue,
)
from strands_code_cli.memory_file import dump_memory_file
from strands_code_cli.memory_modes import (
    MEMORY_EMPTY_QUEUE,
    CurateQueue,
    MemoryModeState,
    Proposal,
    ReviseState,
    silent_note,
)
from strands_code_cli.mode import ModeState
from strands_code_cli.router import (
    USAGE_HINT,
    _MEMORY_USAGE,
    apply_memory_section,
    dispatch,
    read_memory_section,
)
from strands_code_cli.session_index import SessionIndex


def _dispatch(text, tmp_path, **kwargs):
    """Dispatch one slash line against a tmp scratch index."""
    return dispatch(
        text, session_id="s1", index=SessionIndex(tmp_path / "index"), **kwargs
    )


def _loop_source() -> str:
    return (
        Path(__file__).resolve().parent.parent / "strands_code_cli" / "loop.py"
    ).read_text(encoding="utf-8")


# ----------------------------------------------------------------------
# Curate loop: promotion sweep, /memory verbs, boundary review
# ----------------------------------------------------------------------


class TestCurateLoop:
    def test_sweep_caps_at_three_and_keeps_fact_files(self, tmp_path):
        fact_dir = tmp_path / ".agent" / "memory"
        fact_dir.mkdir(parents=True)
        for name in ("a.md", "b.md", "c.md", "d.md", "e.md"):
            (fact_dir / name).write_text(f"# {name}\nFact body.\n", encoding="utf-8")
        queue, seen = CurateQueue(), set()
        queued = queue.sweep_promotions(fact_dir, seen)
        assert len(queued) == 3
        assert all(p.source == "promoted" for p in queued)
        assert len(seen) == 3  # only queued files marked — rest surface later
        assert len(list(fact_dir.glob("*.md"))) == 5  # never auto-deleted
        rest = queue.sweep_promotions(fact_dir, seen)
        assert len(rest) == 2
        assert queue.sweep_promotions(fact_dir, seen) == []

    def test_sweep_ignores_missing_dir_and_seen_files(self, tmp_path):
        queue = CurateQueue()
        assert queue.sweep_promotions(tmp_path / "nope", set()) == []
        fact_dir = tmp_path / ".agent" / "memory"
        fact_dir.mkdir(parents=True)
        (fact_dir / "old.md").write_text("Old fact.\n", encoding="utf-8")
        assert queue.sweep_promotions(fact_dir, {"old.md"}) == []
        assert queue.list_pending() == []

    def test_approve_applies_via_spy_and_replies(self):
        queue = CurateQueue()
        proposal = queue.propose(
            "Build", "promoted", "Run uv build.\n", proposal_id="p1"
        )
        calls: list = []
        assert queue.approve("p1", calls.append) == "Approved p1 → Build."
        assert calls == [proposal]
        assert queue.list_pending() == []

    def test_deny_records_without_writing(self):
        queue = CurateQueue()
        queue.propose("Test", "promoted", "Run pytest.\n", proposal_id="p2")

        def _must_not_write(proposal):
            raise AssertionError("deny must never write")

        assert (
            queue.deny("p2")
            == "Denied p2 — skipped, will not re-ask this session."
        )
        assert "p2" in queue.denied_ids
        assert queue.list_pending() == []

    def test_reproposing_denied_id_is_refused(self):
        queue = CurateQueue()
        queue.propose("Test", "promoted", "Run pytest.\n", proposal_id="p2")
        queue.deny("p2")
        assert (
            queue.propose("Test", "promoted", "Run pytest.\n", proposal_id="p2")
            is None
        )
        assert queue.list_pending() == []

    def test_unknown_id_replies(self):
        queue = CurateQueue()
        assert queue.approve("p9", lambda p: None) == "Unknown proposal 'p9'."
        assert queue.deny("p9") == "Unknown proposal 'p9'."

    def test_bare_memory_with_empty_queue_replies(self, tmp_path):
        for text in ("/memory", "/memory list"):
            action, message = _dispatch(text, tmp_path, curate=CurateQueue())
            assert action == "reply"
            assert message == MEMORY_EMPTY_QUEUE
            assert message == "No pending memory proposals."

    def test_memory_list_formats_pending_lines(self, tmp_path):
        queue = CurateQueue()
        queue.propose("Build", "promoted", "Run uv build.\nMore.\n", proposal_id="p1")
        queue.propose("Test", "manual", "Run pytest.\n", proposal_id="p2")
        action, message = _dispatch("/memory list", tmp_path, curate=queue)
        assert action == "reply"
        assert message == (
            "p1 [promoted] Build — Run uv build.\n"
            "p2 [manual] Test — Run pytest."
        )

    def test_memory_approve_verb_acts_immediately(self, tmp_path, monkeypatch):
        import strands_code_cli.router as router_mod

        queue = CurateQueue()
        queue.propose("Build", "promoted", "Run uv build.\n", proposal_id="p1")
        calls: list = []
        monkeypatch.setattr(router_mod, "apply_memory_proposal", calls.append)
        action, message = _dispatch("/memory approve p1", tmp_path, curate=queue)
        assert action == "reply"
        assert message == "Approved p1 → Build."
        assert [p.id for p in calls] == ["p1"]

    def test_memory_deny_verb_never_writes(self, tmp_path, monkeypatch):
        import strands_code_cli.router as router_mod

        queue = CurateQueue()
        queue.propose("Test", "promoted", "Run pytest.\n", proposal_id="p1")

        def _must_not_write(proposal):
            raise AssertionError("deny must never write")

        monkeypatch.setattr(router_mod, "apply_memory_proposal", _must_not_write)
        action, message = _dispatch("/memory deny p1", tmp_path, curate=queue)
        assert action == "reply"
        assert message == "Denied p1 — skipped, will not re-ask this session."
        assert "p1" in queue.denied_ids

    def test_memory_approve_deny_need_an_id(self, tmp_path):
        queue = CurateQueue()
        for text in ("/memory approve", "/memory deny"):
            action, message = _dispatch(text, tmp_path, curate=queue)
            assert action == "reply"
            assert message == _MEMORY_USAGE
        action, message = _dispatch("/memory approve p9", tmp_path, curate=queue)
        assert message == "Unknown proposal 'p9'."

    def test_review_silent_mode_emits_line_per_proposal(self):
        queue = CurateQueue()
        queue.propose("Build", "promoted", "Run uv build.\n", proposal_id="p1")
        queue.propose("Test", "promoted", "Run pytest.\n", proposal_id="p2")
        calls: list = []
        lines = review_memory_queue(queue, MemoryModeState("silent"), calls.append)
        assert lines == [
            silent_note("Build", "promoted"),
            silent_note("Test", "promoted"),
        ]
        assert [p.id for p in calls] == ["p1", "p2"]
        assert queue.list_pending() == []

    def test_review_curate_prompts_per_proposal(self, monkeypatch):
        queue = CurateQueue()
        queue.propose("Build", "promoted", "Run uv build.\n", proposal_id="p1")
        queue.propose("Test", "promoted", "Run pytest.\n", proposal_id="p2")
        answers = iter(["approve", "deny"])
        monkeypatch.setattr("builtins.input", lambda *args: next(answers))
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        calls: list = []
        lines = review_memory_queue(queue, MemoryModeState(), calls.append)
        assert lines == [
            "Approved p1 → Build.",
            "Denied p2 — skipped, will not re-ask this session.",
        ]
        assert [p.id for p in calls] == ["p1"]
        assert "p2" in queue.denied_ids

    def test_review_ctrl_c_keeps_rest_pending(self, monkeypatch):
        queue = CurateQueue()
        queue.propose("Build", "promoted", "Run uv build.\n", proposal_id="p1")

        def _cancel(*args):
            raise KeyboardInterrupt

        monkeypatch.setattr("builtins.input", _cancel)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        assert review_memory_queue(queue, MemoryModeState(), lambda p: None) == []
        assert [p.id for p in queue.list_pending()] == ["p1"]

    def test_review_revise_choice_hands_instruction_to_callback(self, monkeypatch):
        queue = CurateQueue()
        queue.propose("Build", "promoted", "Run uv build.\n", proposal_id="p1")
        answers = iter(["revise", "mention uv run"])
        monkeypatch.setattr("builtins.input", lambda *args: next(answers))
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        handed: list = []
        lines = review_memory_queue(
            queue,
            MemoryModeState(),
            lambda p: None,
            on_revise=lambda proposal, instruction: handed.append(
                (proposal.id, instruction)
            ),
        )
        assert handed == [("p1", "mention uv run")]
        assert lines == []  # callback returned nothing; proposal stays pending
        assert [p.id for p in queue.list_pending()] == ["p1"]

    def test_usage_hint_contains_curate_verbs(self):
        assert "approve <id>|deny <id>" in USAGE_HINT

    def test_apply_memory_proposal_writes_through_dump(self, tmp_path, monkeypatch):
        from strands_code_cli.memory_file import parse_memory_file
        from strands_code_cli.router import apply_memory_proposal

        monkeypatch.chdir(tmp_path)
        apply_memory_proposal(Proposal("p1", "Build", "promoted", "Run uv build.\n"))
        _frontmatter, body = parse_memory_file(tmp_path / ".agent" / "MEMORY.md")
        assert "## Build\nRun uv build.\n" in body
        apply_memory_proposal(Proposal("p2", "Build", "promoted", "Use uv run.\n"))
        _frontmatter, body = parse_memory_file(tmp_path / ".agent" / "MEMORY.md")
        assert body.count("## Build") == 1
        assert "Use uv run." in body

    def test_loop_boundary_wires_sweep_and_review(self):
        source = _loop_source()
        assert "curate_queue.sweep_promotions(MEMORY_FACT_DIR, promotion_seen)" in source
        assert "review_memory_queue(\n            curate_queue,\n            memory_mode" in source
        assert "memory_mode=memory_mode," in source
        assert "curate=curate_queue," in source


def _write_memory(root: Path, body: str) -> Path:
    """Write a tmp .agent/MEMORY.md through the atomic dump path."""
    path = root / ".agent" / "MEMORY.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_memory_file(path, {"scope": "repo", "version": 1}, body)
    return path


def _arm(section: str = "Build", previous: str = "Run make.\n") -> ReviseState:
    state = ReviseState()
    state.arm(section, previous, "use uv")
    return state


def _non_tty(monkeypatch, *answers):
    """Fake the typed prompt path: non-tty stdin plus scripted input."""
    replies = iter(answers)
    monkeypatch.setattr("builtins.input", lambda *args: next(replies))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)


# ----------------------------------------------------------------------
# Revise rounds: quoted review plus accept/revert/iterate
# ----------------------------------------------------------------------


class TestReviseRounds:
    def test_revise_dispatch_returns_agent_turn(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_memory(tmp_path, "## Build\nRun make.\n")
        holder = ReviseState()
        action, message = _dispatch(
            "/memory revise Build use uv", tmp_path, revise=holder
        )
        assert action == "agent"
        assert message is not None
        assert "Reply with the FULL revised section in one fenced block" in message
        assert "Run make." in message  # quoted current section
        assert holder.armed
        assert (holder.section, holder.instruction) == ("Build", "use uv")

    def test_revise_unknown_section_replies(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_memory(tmp_path, "## Build\nRun make.\n")
        holder = ReviseState()
        action, message = _dispatch(
            "/memory revise Nope use uv", tmp_path, revise=holder
        )
        assert action == "reply"
        assert message == "Unknown memory section 'Nope'."
        assert not holder.armed

    def test_revise_needs_section_and_instruction(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_memory(tmp_path, "## Build\nRun make.\n")
        for text in ("/memory revise", "/memory revise Build"):
            action, message = _dispatch(text, tmp_path, revise=ReviseState())
            assert action == "reply"
            assert message == _MEMORY_USAGE

    def test_consume_accept_applies_block_verbatim(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        path = _write_memory(tmp_path, "## Build\nRun make.\n")
        _non_tty(monkeypatch, "accept")
        printed: list = []
        monkeypatch.setattr(
            "builtins.print",
            lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)),
        )
        state = _arm()
        reply = consume_revise_turn(
            "Here:\n```\nRun uv build.\n```\nSwitched to uv.",
            state,
            apply_memory_section,
        )
        assert reply == "Memory section 'Build' updated."
        assert not state.armed
        assert read_memory_section("Build") == "Run uv build.\n"
        body = path.read_text(encoding="utf-8")
        assert f"<!-- updated: {date.today().isoformat()} -->" in body
        assert "> Run uv build." in printed  # quoted for review
        assert "Summary: Switched to uv." in printed  # one-line summary

    def test_consume_revert_leaves_file_byte_identical(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        path = _write_memory(tmp_path, "## Build\nRun make.\n")
        before = path.read_bytes()
        _non_tty(monkeypatch, "revert")
        state = _arm()
        reply = consume_revise_turn(
            "Here:\n```\nRun uv build.\n```\nSwitched to uv.",
            state,
            apply_memory_section,
        )
        assert reply == "Reverted — 'Build' unchanged."
        assert not state.armed
        assert path.read_bytes() == before

    def test_consume_no_fence_disarms_without_prompting(self, monkeypatch):
        def _must_not_prompt(*args):
            raise AssertionError("no-fence path must not prompt")

        monkeypatch.setattr("builtins.input", _must_not_prompt)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        state = _arm()
        reply = consume_revise_turn("no fenced block here", state, apply_memory_section)
        assert reply == "No fenced block found — revision discarded, 'Build' unchanged."
        assert not state.armed

    def test_consume_ctrl_c_disarms_and_reraises(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        path = _write_memory(tmp_path, "## Build\nRun make.\n")
        before = path.read_bytes()

        def _cancel(*args):
            raise KeyboardInterrupt

        monkeypatch.setattr("builtins.input", _cancel)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        state = _arm()
        with pytest.raises(KeyboardInterrupt):
            consume_revise_turn(
                "Here:\n```\nRun uv build.\n```\nSwitched to uv.",
                state,
                apply_memory_section,
            )
        assert not state.armed
        assert path.read_bytes() == before

    def test_consume_iterate_rearms_with_new_instruction(self, monkeypatch):
        _non_tty(monkeypatch, "iterate", "mention uv run")
        state = _arm()
        calls: list = []
        reply = consume_revise_turn(
            "Here:\n```\nRun uv build.\n```\nSwitched to uv.",
            state,
            lambda section, text: calls.append((section, text)),
        )
        assert reply is None  # still armed: the loop re-invokes
        assert state.armed
        assert state.instruction == "mention uv run"
        assert state.previous_text == "Run make.\n"
        assert calls == []  # nothing applied yet

    def test_consume_empty_iterate_instruction_fails_closed(self, monkeypatch):
        _non_tty(monkeypatch, "iterate", "   ")
        state = _arm()
        reply = consume_revise_turn(
            "Here:\n```\nRun uv build.\n```\nSwitched to uv.",
            state,
            apply_memory_section,
        )
        assert reply == "Reverted — 'Build' unchanged."
        assert not state.armed

    def test_drain_iterates_with_offline_double(self, monkeypatch):
        # No live model: a recording lambda drives the follow-up turn.
        seen: list = []
        canned = iter(["Again:\n```\nRun uv run build.\n```\nUses uv run."])

        def _fake_agent(text):
            seen.append(text)
            return next(canned)

        _non_tty(monkeypatch, "iterate", "use uv run", "accept")
        state = _arm()
        calls: list = []
        _drain_revise_rounds(
            _fake_agent,
            "Here:\n```\nRun uv build.\n```\nSwitched to uv.",
            state,
            threading.Event(),
            [],
            "test-model",
            ModeState(),
            apply_fn=lambda section, text: calls.append((section, text)),
        )
        assert len(seen) == 1
        assert "use uv run" in seen[0]  # follow-up carries the new instruction
        assert calls == [("Build", "Run uv run build.")]
        assert not state.armed

    def test_result_text_prefers_result_then_history(self):
        assert _result_text(SimpleNamespace(), "plain") == "plain"
        assert _result_text(SimpleNamespace(), SimpleNamespace(text="t")) == "t"
        message = {"role": "assistant", "content": [{"text": "m"}]}
        assert _result_text(SimpleNamespace(), SimpleNamespace(message=message)) == "m"
        history = [
            {"role": "user", "content": [{"text": "q"}]},
            {"role": "assistant", "content": [{"text": "h"}]},
        ]
        assert _result_text(SimpleNamespace(messages=history), object()) == "h"
        assert _result_text(SimpleNamespace(), object()) == ""

    def test_apply_memory_section_replaces_and_refreshes_marker(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        _write_memory(
            tmp_path,
            "<!-- updated: 2020-01-01 -->\n## Build\nRun make.\n\n## Test\nRun pytest.\n",
        )
        apply_memory_section("Build", "Run uv build.\n")
        assert read_memory_section("Build") == "Run uv build.\n"
        assert read_memory_section("Test") == "Run pytest.\n"
        body = (tmp_path / ".agent" / "MEMORY.md").read_text(encoding="utf-8")
        assert "2020-01-01" not in body
        assert f"<!-- updated: {date.today().isoformat()} -->" in body

    def test_apply_memory_section_appends_missing_section(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        _write_memory(tmp_path, "## Build\nRun make.\n")
        apply_memory_section("Test", "Run pytest.\n")
        assert read_memory_section("Test") == "Run pytest.\n"
        assert read_memory_section("Build") == "Run make.\n"

    def test_read_memory_section_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert read_memory_section("Build") is None
        _write_memory(tmp_path, "## Build\nRun make.\n")
        assert read_memory_section("Nope") is None

    def test_section_span_keeps_marker_glued_to_next_heading(
        self, tmp_path, monkeypatch
    ):
        from strands_code_cli.router import apply_memory_proposal

        monkeypatch.chdir(tmp_path)
        path = _write_memory(
            tmp_path,
            "## Build\nRun make.\n\n<!-- updated: 2020-05-05 -->\n## Test\nRun pytest.\n",
        )
        assert read_memory_section("Build") == "Run make.\n"
        apply_memory_proposal(Proposal("p1", "Build", "promoted", "Use uv run.\n"))
        body = path.read_text(encoding="utf-8")
        assert "<!-- updated: 2020-05-05 -->\n## Test" in body  # still glued
        assert read_memory_section("Build") == "Run make.\n\nUse uv run.\n"

    def test_loop_wires_revise_consumer(self):
        source = _loop_source()
        assert "revise_state = ReviseState()" in source
        assert "revise=revise_state," in source
        assert "on_revise=_arm_revise_from_review," in source
        assert "_drain_revise_rounds(" in source
        assert "consume_revise_turn(text, revise_state, writer)" in source
