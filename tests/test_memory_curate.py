"""SKILL-02 curation surface: curate queue, revise rounds, /init scan.

Hermetic by construction: canned turn text only, tmp fixtures only —
no live model, no network. Loop-hook wiring is asserted via the
consumer functions plus source assertions, never a live REPL.
"""

from __future__ import annotations

import sys
import threading
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from strands_code_cli.loop import (
    _drain_revise_rounds,
    _result_text,
    consume_init_turn,
    consume_revise_turn,
    review_memory_queue,
)
from strands_code_cli.memory_file import (
    MAX_SCAN_BYTES,
    MAX_SCAN_FILES,
    apply_init_proposal,
    diff_sections,
    dump_memory_file,
    load_memory,
    memory_section_names,
    parse_memory_file,
    scan_repo,
)
from strands_code_cli.memory_modes import (
    MEMORY_EMPTY_QUEUE,
    CurateQueue,
    InitState,
    MemoryModeState,
    Proposal,
    ReviseState,
    format_init_prompt,
    seed_promotion_seen,
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

    def test_approve_failed_write_stays_pending_for_retry(self):
        queue = CurateQueue()
        queue.propose("Build", "promoted", "Run uv build.\n", proposal_id="p1")

        def _failing(proposal):
            raise OSError("disk full")

        with pytest.raises(OSError, match="disk full"):
            queue.approve("p1", _failing)
        assert [p.id for p in queue.list_pending()] == ["p1"]
        calls: list = []
        assert queue.approve("p1", calls.append) == "Approved p1 → Build."
        assert [p.id for p in calls] == ["p1"]
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
        monkeypatch.setattr(router_mod, "apply_approved_proposal", calls.append)
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

        monkeypatch.setattr(router_mod, "apply_approved_proposal", _must_not_write)
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

    def test_review_eof_at_prompt_keeps_proposal_pending(self, monkeypatch):
        queue = CurateQueue()
        queue.propose("Build", "promoted", "Run uv build.\n", proposal_id="p1")

        def _eof(*args):
            raise EOFError

        monkeypatch.setattr("builtins.input", _eof)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        assert review_memory_queue(queue, MemoryModeState(), lambda p: None) == []
        assert [p.id for p in queue.list_pending()] == ["p1"]

    def test_review_eof_at_revise_instruction_keeps_proposal_pending(
        self, monkeypatch
    ):
        queue = CurateQueue()
        queue.propose("Build", "promoted", "Run uv build.\n", proposal_id="p1")
        prompted: list = []

        def _scripted(*args):
            if not prompted:
                prompted.append(True)
                return "revise"
            raise EOFError

        monkeypatch.setattr("builtins.input", _scripted)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

        def _must_not_arm(proposal, instruction):
            raise AssertionError("EOF must not arm a revise round")

        lines = review_memory_queue(
            queue, MemoryModeState(), lambda p: None, on_revise=_must_not_arm
        )
        assert lines == []
        assert [p.id for p in queue.list_pending()] == ["p1"]

    def test_review_silent_mode_propagates_write_failure_to_caller(self):
        queue = CurateQueue()
        queue.propose("Build", "promoted", "Run uv build.\n", proposal_id="p1")

        def _failing(proposal):
            raise OSError("disk full")

        with pytest.raises(OSError, match="disk full"):
            review_memory_queue(queue, MemoryModeState("silent"), _failing)

    def test_memory_approve_reports_write_failure_as_reply(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        agent_dir = tmp_path / ".agent"
        agent_dir.mkdir(parents=True, exist_ok=True)
        outside = tmp_path / "real.md"
        outside.write_text("---\nscope: repo\n---\n## Build\n", encoding="utf-8")
        (agent_dir / "MEMORY.md").symlink_to(outside)
        queue = CurateQueue()
        queue.propose("Build", "promoted", "Run uv build.\n", proposal_id="p1")
        action, message = _dispatch("/memory approve p1", tmp_path, curate=queue)
        assert action == "reply"
        assert message is not None
        assert message.startswith("Memory write failed — proposal p1 kept pending:")
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

    def test_apply_memory_proposal_stamps_freshness_marker(
        self, tmp_path, monkeypatch
    ):
        from strands_code_cli.router import apply_memory_proposal

        monkeypatch.chdir(tmp_path)
        apply_memory_proposal(Proposal("p1", "Build", "promoted", "Run uv build.\n"))
        _frontmatter, body = parse_memory_file(tmp_path / ".agent" / "MEMORY.md")
        marker = f"<!-- updated: {date.today().isoformat()} -->"
        assert f"{marker}\n## Build\nRun uv build.\n" in body

    def test_apply_memory_proposal_marks_existing_section_only(
        self, tmp_path, monkeypatch
    ):
        from strands_code_cli.router import apply_memory_proposal

        monkeypatch.chdir(tmp_path)
        _write_memory(tmp_path, "## Build\nRun make.\n\n## Test\nRun pytest.\n")
        apply_memory_proposal(Proposal("p1", "Build", "promoted", "Use uv run.\n"))
        _frontmatter, body = parse_memory_file(tmp_path / ".agent" / "MEMORY.md")
        marker = f"<!-- updated: {date.today().isoformat()} -->"
        assert f"{marker}\n## Build\n" in body
        assert "Use uv run." in body
        assert body.count(marker) == 1
        assert "## Test\nRun pytest.\n" in body

    def test_apply_memory_proposal_refreshes_stale_marker(
        self, tmp_path, monkeypatch
    ):
        from strands_code_cli.router import apply_memory_proposal

        monkeypatch.chdir(tmp_path)
        old = (date.today() - timedelta(days=91)).isoformat()
        _write_memory(tmp_path, f"<!-- updated: {old} -->\n## Build\nRun make.\n")
        apply_memory_proposal(Proposal("p1", "Build", "promoted", "Use uv run.\n"))
        _frontmatter, body = parse_memory_file(tmp_path / ".agent" / "MEMORY.md")
        fresh = f"<!-- updated: {date.today().isoformat()} -->"
        assert old not in body
        assert body.count(fresh) == 1
        assert f"{fresh}\n## Build\n" in body

    def test_approved_section_reads_fresh_to_diff(self, tmp_path, monkeypatch):
        from strands_code_cli.router import apply_memory_proposal

        monkeypatch.chdir(tmp_path)
        apply_memory_proposal(Proposal("p1", "Build", "promoted", "Run uv build.\n"))
        snapshot = load_memory()
        assert "Build" not in diff_sections(snapshot)

    def test_loop_boundary_wires_sweep_and_review(self):
        source = _loop_source()
        assert "curate_queue.sweep_promotions(" in source
        assert "MEMORY_FACT_DIR," in source
        assert "skip_sections=memory_section_names(memory_snapshot.agent_text)" in source
        assert "promotion_seen: set[str] = seed_promotion_seen(MEMORY_FACT_DIR)" in source
        assert "review_memory_queue(\n                curate_queue,\n                memory_mode" in source
        assert "apply_approved_proposal," in source
        assert "except (OSError, ValueError) as exc:" in source
        assert "Memory review skipped — write failed:" in source
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

    def test_consume_eof_disarms_with_revert_note(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        path = _write_memory(tmp_path, "## Build\nRun make.\n")
        before = path.read_bytes()

        def _eof(*args):
            raise EOFError

        monkeypatch.setattr("builtins.input", _eof)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        state = _arm()
        reply = consume_revise_turn(
            "Here:\n```\nRun uv build.\n```\nSwitched to uv.",
            state,
            apply_memory_section,
        )
        assert reply == "Reverted — 'Build' unchanged."
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


def _write_repo(root: Path) -> None:
    """Tmp fixture repo: README, manifest, docs, policy, sources, sessions."""
    (root / "README.md").write_text("# Demo\nA demo repo.\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["requests>=2", "click"]\n'
        "[tool.pytest.ini_options]\naddopts = '-q'\n",
        encoding="utf-8",
    )
    (root / "docs").mkdir()
    (root / "docs" / "guide.md").write_text("Guide body here.\n", encoding="utf-8")
    (root / ".agent").mkdir()
    (root / ".agent" / "policy.toml").write_text(
        "[allow]\ntools = ['read']\n", encoding="utf-8"
    )
    (root / ".agent" / "sessions").mkdir()
    (root / ".agent" / "sessions" / "s1.md").write_text(
        "SESSION-SECRET-STUFF\n", encoding="utf-8"
    )
    (root / "pkg").mkdir()
    (root / "pkg" / "core.py").write_text(
        '"""Core module."""\nimport os\n\ndef run():\n    """Run it."""\n    return 42\n',
        encoding="utf-8",
    )
    (root / "api_keys.py").write_text("KEY = 'SECRET-KEY-STUFF'\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_x.py").write_text(
        "def test_x():\n    assert True\n", encoding="utf-8"
    )


def _arm_init(depth: str = "shallow", stale: list | None = None) -> InitState:
    state = InitState()
    state.arm(depth, SimpleNamespace(depth=depth, outline="outline"), stale or [])
    return state


# ----------------------------------------------------------------------
# Init scan: repo scan plus draft-through-curate plus merge-never-clobber
# ----------------------------------------------------------------------


class TestInitScan:
    def test_scan_shallow_reads_only_listed_sources(self, tmp_path):
        _write_repo(tmp_path)
        report = scan_repo(tmp_path, "shallow")
        assert report.depth == "shallow"
        assert set(report.sources_read) == {
            "README.md",
            "pyproject.toml",
            ".agent/policy.toml",
        }
        total = sum(
            (tmp_path / name).stat().st_size for name in report.sources_read
        )
        assert len(report.sources_read) <= MAX_SCAN_FILES
        assert total <= MAX_SCAN_BYTES
        assert "SESSION-SECRET-STUFF" not in report.outline
        assert ".agent/sessions/ (contents skipped)" in report.outline
        assert "A demo repo." in report.outline  # README content
        assert "guide.md" in report.outline  # docs filenames…
        assert "Guide body here." not in report.outline  # …only
        assert "tools = ['read']" in report.outline  # policy posture

    def test_scan_deep_adds_sources_deps_tests(self, tmp_path):
        _write_repo(tmp_path)
        report = scan_repo(tmp_path, "deep")
        assert "pkg/core.py" in report.sources_read
        assert "tests/test_x.py" in report.sources_read
        assert "api_keys.py" not in report.sources_read  # key-shaped: never read
        assert "SECRET-KEY-STUFF" not in report.outline
        assert "import os" in report.outline
        assert "def run: Run it." in report.outline
        assert "return 42" not in report.outline  # bodies excluded
        assert "requests" in report.outline and "click" in report.outline
        assert "tests/test_x.py" in report.outline
        assert "addopts" in report.outline  # runner config

    def test_scan_samples_at_most_ten_sources(self, tmp_path):
        for pos in range(12):
            (tmp_path / f"mod_{pos:02d}.py").write_text(
                f"VALUE = {pos}\n", encoding="utf-8"
            )
        report = scan_repo(tmp_path, "deep")
        assert report.outline.count("Source (mod_") == 10

    def test_scan_respects_file_and_byte_caps(self, tmp_path):
        for pos in range(30):
            (tmp_path / f"README.{pos}").write_text("x\n", encoding="utf-8")
        report = scan_repo(tmp_path, "shallow")
        assert len(report.sources_read) == MAX_SCAN_FILES == 25
        assert "(scan capped at 25 files / 50000 bytes" in report.outline

    def test_scan_single_file_over_byte_cap_is_skipped(self, tmp_path):
        (tmp_path / "README.md").write_text("y" * (MAX_SCAN_BYTES + 1), encoding="utf-8")
        report = scan_repo(tmp_path, "shallow")
        assert report.sources_read == []
        assert "(scan capped at 25 files / 50000 bytes" in report.outline

    def test_scan_rejects_unknown_depth(self, tmp_path):
        with pytest.raises(ValueError):
            scan_repo(tmp_path, "sideways")

    def test_diff_sections_flags_missing_unmarked_and_stale(self):
        from strands_code_cli.memory_file import MemorySnapshot

        old = (date.today() - timedelta(days=91)).isoformat()
        fresh = date.today().isoformat()
        body = (
            "## Build\nUnmarked body.\n"
            f"<!-- updated: {old} -->\n## Test\nOld body.\n"
            f"<!-- updated: {fresh} -->\n## Conventions\nFresh body.\n"
        )
        snapshot = MemorySnapshot(root_text="", agent_text=body)
        assert diff_sections(snapshot) == ["Build", "Test", "Layout", "Gotchas"]

    def test_consume_init_turn_queues_stale_labeled_blocks(self):
        queue = CurateQueue()
        state = _arm_init("shallow", ["Build", "Test"])
        reply = consume_init_turn(
            "Intro.\n"
            "```proposed: Build\nRun uv build.\n```\n"
            "```proposed: Test\nRun pytest.\n```\n"
            "```proposed: Layout\nShould not queue.\n```\n"
            "```\nUnlabeled fence.\n```\n",
            state,
            queue,
        )
        assert reply == "Drafted 2 sections from shallow scan — review with /memory."
        assert not state.armed
        pending = queue.list_pending()
        assert [(p.section, p.source) for p in pending] == [
            ("Build", "init-shallow"),
            ("Test", "init-shallow"),
        ]
        assert [p.body for p in pending] == ["Run uv build.", "Run pytest."]

    def test_consume_init_turn_ignores_repeats_and_empty(self):
        queue = CurateQueue()
        state = _arm_init("deep", ["Build"])
        reply = consume_init_turn(
            "```proposed: Build\nFirst.\n```\n```proposed: Build\nSecond.\n```\n",
            state,
            queue,
        )
        assert reply == "Drafted 1 sections from deep scan — review with /memory."
        assert [p.body for p in queue.list_pending()] == ["First."]
        assert consume_init_turn("no blocks", _arm_init("deep", ["Build"]), queue) == (
            "Drafted 0 sections from deep scan — review with /memory."
        )

    def test_apply_init_proposal_merges_without_clobbering(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        fresh = date.today().isoformat()
        approved_span = f"<!-- updated: {fresh} -->\n## Build\nApproved line.\n"
        _write_memory(tmp_path, approved_span)
        snapshot = load_memory(tmp_path / "STRANDS.md", tmp_path / ".agent" / "MEMORY.md")
        apply_init_proposal(
            Proposal("p1", "Test", "init-shallow", "Run pytest.\nSecond line here.\n"),
            snapshot,
        )
        _frontmatter, body = parse_memory_file(tmp_path / ".agent" / "MEMORY.md")
        assert approved_span in body  # pre-approved span byte-identical
        assert "## Test\nRun pytest.\nSecond line here.\n" in body
        _root_frontmatter, root_body = parse_memory_file(tmp_path / "STRANDS.md")
        assert "Details live in .agent/MEMORY.md" in root_body
        assert "- Test: Run pytest." in root_body
        assert "Second line here." not in root_body  # thin lines only

    def test_apply_init_proposal_upserts_root_pointer(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        snapshot = load_memory(tmp_path / "STRANDS.md", tmp_path / ".agent" / "MEMORY.md")
        apply_init_proposal(Proposal("p1", "Build", "init-shallow", "Run uv.\n"), snapshot)
        snapshot = load_memory(tmp_path / "STRANDS.md", tmp_path / ".agent" / "MEMORY.md")
        apply_init_proposal(Proposal("p2", "Test", "init-shallow", "Run pytest.\n"), snapshot)
        snapshot = load_memory(tmp_path / "STRANDS.md", tmp_path / ".agent" / "MEMORY.md")
        apply_init_proposal(Proposal("p3", "Build", "init-deep", "Run uv run.\n"), snapshot)
        _frontmatter, root_body = parse_memory_file(tmp_path / "STRANDS.md")
        assert root_body.count("## Memory") == 1
        assert root_body.count("- Build:") == 1
        assert "- Build: Run uv run." in root_body  # latest wins
        assert "- Test: Run pytest." in root_body
        first = root_body.split("## Memory")[1].strip().splitlines()[0]
        assert first == "Details live in .agent/MEMORY.md — see that file for full conventions."

    def test_init_dispatch_arms_and_names_only_stale(self, tmp_path):
        _write_repo(tmp_path)
        fresh = date.today().isoformat()
        _write_memory(tmp_path, f"<!-- updated: {fresh} -->\n## Conventions\nFresh.\n")
        holder = InitState()
        action, message = _dispatch("/init", tmp_path, init=holder, cwd=tmp_path)
        assert action == "agent"
        assert message is not None
        assert (
            "Draft ONLY these memory sections: Build, Test, Layout, Gotchas."
            in message
        )
        assert "Conventions" not in message.split("Draft ONLY")[1]
        assert holder.armed and holder.depth == "shallow"
        assert holder.stale_sections == ["Build", "Test", "Layout", "Gotchas"]
        assert not (tmp_path / "STRANDS.md").exists()  # nothing written pre-approval

    def test_init_deeper_selects_deep_scan(self, tmp_path):
        _write_repo(tmp_path)
        holder = InitState()
        action, message = _dispatch("/init deeper", tmp_path, init=holder, cwd=tmp_path)
        assert action == "agent"
        assert message is not None and "Repo scan (deep)" in message
        assert holder.depth == "deep"

    def test_init_unknown_arg_returns_usage(self, tmp_path):
        _write_repo(tmp_path)
        action, message = _dispatch("/init sideways", tmp_path, cwd=tmp_path)
        assert action == "reply"
        assert message == "Usage: /init [deeper]"

    def test_init_all_fresh_replies(self, tmp_path):
        _write_repo(tmp_path)
        fresh = date.today().isoformat()
        sections = "".join(
            f"<!-- updated: {fresh} -->\n## {name}\nBody.\n"
            for name in ("Build", "Test", "Conventions", "Layout", "Gotchas")
        )
        _write_memory(tmp_path, sections)
        holder = InitState()
        action, message = _dispatch("/init", tmp_path, init=holder, cwd=tmp_path)
        assert action == "reply"
        assert message == "Memory is fresh — no sections to draft."
        assert not holder.armed

    def test_approve_routes_init_proposal_to_init_writer(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        queue = CurateQueue()
        queue.propose("Build", "init-shallow", "Run uv build.\n", proposal_id="p1")
        queue.propose("Test", "promoted", "Run pytest.\n", proposal_id="p2")
        action, message = _dispatch("/memory approve p1", tmp_path, curate=queue)
        assert action == "reply" and message == "Approved p1 → Build."
        _frontmatter, body = parse_memory_file(tmp_path / ".agent" / "MEMORY.md")
        assert "## Build\nRun uv build.\n" in body
        _root_frontmatter, root_body = parse_memory_file(tmp_path / "STRANDS.md")
        assert "Details live in .agent/MEMORY.md" in root_body
        action, message = _dispatch("/memory approve p2", tmp_path, curate=queue)
        assert message == "Approved p2 → Test."
        _root_frontmatter, root_body = parse_memory_file(tmp_path / "STRANDS.md")
        assert "pytest" not in root_body  # promoted path leaves root alone

    def test_usage_hint_contains_init(self):
        assert "/init [deeper]" in USAGE_HINT

    def test_loop_wires_init_consumer(self):
        source = _loop_source()
        assert "init_state = InitState()" in source
        assert "init=init_state," in source
        assert "consume_init_turn(" in source
        assert "_result_text(agent, result), init_state, curate_queue" in source


# ----------------------------------------------------------------------
# UAT gap round: promotion quieting, batch verbs, init guard
# ----------------------------------------------------------------------


class TestMemoryGapRound:
    def test_seed_collects_preexisting_facts(self, tmp_path):
        fact_dir = tmp_path / ".agent" / "memory"
        fact_dir.mkdir(parents=True)
        (fact_dir / "old.md").write_text("Old fact.\n", encoding="utf-8")
        (fact_dir / "notes.txt").write_text("Not a fact.\n", encoding="utf-8")
        assert seed_promotion_seen(fact_dir) == {"old.md"}
        assert seed_promotion_seen(tmp_path / ".agent" / "absent") == set()

    def test_seeded_sweep_surfaces_only_new_facts(self, tmp_path):
        fact_dir = tmp_path / ".agent" / "memory"
        fact_dir.mkdir(parents=True)
        (fact_dir / "old.md").write_text("Old fact.\n", encoding="utf-8")
        queue, seen = CurateQueue(), seed_promotion_seen(fact_dir)
        assert queue.sweep_promotions(fact_dir, seen) == []
        (fact_dir / "new.md").write_text("New fact.\n", encoding="utf-8")
        queued = queue.sweep_promotions(fact_dir, seen)
        assert [p.section for p in queued] == ["new"]

    def test_sweep_skips_memorialized_sections(self, tmp_path):
        fact_dir = tmp_path / ".agent" / "memory"
        fact_dir.mkdir(parents=True)
        (fact_dir / "Build.md").write_text("Run uv build.\n", encoding="utf-8")
        (fact_dir / "Fresh.md").write_text("Fresh fact.\n", encoding="utf-8")
        skip = memory_section_names("<!-- updated: 2026-01-01 -->\n## Build\nRun uv build.\n")
        queue, seen = CurateQueue(), set()
        queued = queue.sweep_promotions(fact_dir, seen, skip_sections=skip)
        assert [p.section for p in queued] == ["Fresh"]
        assert seen == {"Build.md", "Fresh.md"}
        assert queue.sweep_promotions(fact_dir, seen, skip_sections=skip) == []

    def test_approve_all_applies_each_pending(self, tmp_path, monkeypatch):
        import strands_code_cli.router as router_mod

        queue = CurateQueue()
        queue.propose("Build", "promoted", "Run uv build.\n", proposal_id="p1")
        queue.propose("Test", "promoted", "Run pytest.\n", proposal_id="p2")
        calls: list = []
        monkeypatch.setattr(router_mod, "apply_approved_proposal", calls.append)
        action, message = _dispatch("/memory approve-all", tmp_path, curate=queue)
        assert action == "reply"
        assert message == "Approved 2 proposals."
        assert [p.id for p in calls] == ["p1", "p2"]
        assert queue.list_pending() == []

    def test_deny_all_skips_each_without_writing(self, tmp_path, monkeypatch):
        import strands_code_cli.router as router_mod

        queue = CurateQueue()
        queue.propose("Build", "promoted", "Run uv build.\n", proposal_id="p1")
        queue.propose("Test", "promoted", "Run pytest.\n", proposal_id="p2")

        def _must_not_write(proposal):
            raise AssertionError("deny-all must never write")

        monkeypatch.setattr(router_mod, "apply_approved_proposal", _must_not_write)
        action, message = _dispatch("/memory deny-all", tmp_path, curate=queue)
        assert action == "reply"
        assert message == "Denied 2 proposals — will not re-ask this session."
        assert queue.list_pending() == []
        assert queue.denied_ids == {"p1", "p2"}

    def test_batch_verbs_empty_queue_replies(self, tmp_path):
        queue = CurateQueue()
        for text in ("/memory approve-all", "/memory deny-all"):
            action, message = _dispatch(text, tmp_path, curate=queue)
            assert action == "reply"
            assert message == MEMORY_EMPTY_QUEUE

    def test_init_prompt_guards_agent_internals(self):
        report = SimpleNamespace(depth="shallow", outline="Layout:\n  .agent/\n")
        prompt = format_init_prompt(report, ["Build"])
        assert ".agent/sessions" in prompt
        assert "session index" in prompt
        assert "Draft ONLY these memory sections: Build." in prompt
