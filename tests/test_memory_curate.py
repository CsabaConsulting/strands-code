"""SKILL-02 curation surface: curate queue, revise rounds, /init scan.

Hermetic by construction: canned turn text only, tmp fixtures only —
no live model, no network. Loop-hook wiring is asserted via the
consumer functions plus source assertions, never a live REPL.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from strands_code_cli.loop import review_memory_queue
from strands_code_cli.memory_modes import (
    MEMORY_EMPTY_QUEUE,
    CurateQueue,
    MemoryModeState,
    Proposal,
    silent_note,
)
from strands_code_cli.router import USAGE_HINT, _MEMORY_USAGE, dispatch
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
        assert "review_memory_queue(\n            curate_queue, memory_mode" in source
        assert "memory_mode=memory_mode," in source
        assert "curate=curate_queue," in source
