"""Session memory modes: curate vs silent (SKILL-02, D-07, PARITY-01 D-01).

New sessions open in ``curate`` (or the ``memory_mode`` startup default in
``~/.config/strands-code/config.yaml``): curate prompts approve/deny per
proposal — the deny-first posture — while ``/memory mode silent`` opts
into in-memory session-sticky auto-apply for promoted facts with one
transcript line per applied write (slash switches never persist to disk).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from strands_code_cli.platform_io import refuse_symlink
from strands_code_cli.ui.console import sanitize_display

logger = logging.getLogger(__name__)

MEMORY_MODE_CURATE_REPLY = "Memory mode: curate — every proposal prompts approve/deny."
MEMORY_MODE_SILENT_REPLY = "Memory mode: silent — proposals auto-apply, writes logged."
MEMORY_MODE_USAGE = "Usage: /memory mode [curate|silent]"

PROMOTION_SWEEP_LIMIT = 3
"""Max promotion proposals queued per turn-boundary sweep (Open Q2)."""

MEMORY_FACT_DIR = Path(".agent/memory")
"""Harness fact-store dir watched for promotion candidates."""

MEMORY_EMPTY_QUEUE = "No pending memory proposals."

PROPOSAL_SOURCES = ("init-shallow", "init-deep", "promoted", "manual", "revise")
"""Allowed :attr:`Proposal.source` values (resolved item 2)."""


class MemoryModeState:
    """Session-sticky curate/silent holder.

    ``mode`` is ``"curate"`` or ``"silent"`` (anything else raises
    ``ValueError`` — there is no third mode).
    """

    VALID = ("curate", "silent")

    def __init__(self, initial: str = "curate") -> None:
        if initial not in self.VALID:
            raise ValueError(f"unknown memory mode {initial!r}: expected curate|silent")
        self._mode = initial

    @property
    def mode(self) -> str:
        """Current mode (``"curate"`` or ``"silent"``)."""
        return self._mode

    def set(self, mode: str) -> str:
        """Switch mode; returns the transcript announcement.

        Raises:
            ValueError: For anything outside ``curate|silent``.
        """
        if mode not in self.VALID:
            raise ValueError(f"unknown memory mode {mode!r}: expected curate|silent")
        self._mode = mode
        return (
            MEMORY_MODE_CURATE_REPLY if mode == "curate" else MEMORY_MODE_SILENT_REPLY
        )

    def announce(self) -> str:
        """Current-mode report for bare ``/memory mode``."""
        return (
            MEMORY_MODE_CURATE_REPLY
            if self._mode == "curate"
            else MEMORY_MODE_SILENT_REPLY
        )


def silent_note(section: str, source: str) -> str:
    """One transcript line per silent-mode applied write."""
    return (
        f"Memory updated (silent): {sanitize_display(section)}"
        f" ← {sanitize_display(source)}"
    )


def seed_promotion_seen(memory_dir: str | Path) -> set[str]:
    """Fact filenames already in the store at launch — never surface as new.

    The loop seeds its sweep set with this once at startup so only
    facts extracted *during* the session queue as proposals; stale
    files from past sessions stay quiet instead of flooding curate
    on every launch. Missing dirs and symlinks yield nothing.
    """
    try:
        fact_dir = Path(memory_dir)
        refuse_symlink(fact_dir, "memory fact dir", max_ancestors=1)
        return {
            p.name for p in fact_dir.glob("*.md") if p.is_file() and not p.is_symlink()
        }
    except (OSError, ValueError):
        return set()


@dataclass
class Proposal:
    """One curate-queue entry awaiting approve/deny.

    ``source`` is one of :data:`PROPOSAL_SOURCES`; ``created_turn``
    names the turn that queued it (empty when queued outside a turn).
    """

    id: str
    section: str
    source: str
    body: str
    created_turn: str = ""


def unknown_proposal(proposal_id: str) -> str:
    """Reply for approve/deny naming an id with no pending proposal."""
    return f"Unknown proposal {proposal_id!r}."


class ReviseState:
    """Session-sticky revise-round holder (D-08).

    Armed by ``/memory revise`` (or the boundary review's revise
    choice); the loop consumes the armed round after the agent turn.
    In-memory like :class:`MemoryModeState` — a round never survives
    the session.
    """

    def __init__(self) -> None:
        self.armed = False
        self.section = ""
        self.previous_text = ""
        self.instruction = ""

    def arm(self, section: str, previous_text: str, instruction: str) -> None:
        """Arm a round for one section plus its NL instruction."""
        self.armed = True
        self.section = section
        self.previous_text = previous_text
        self.instruction = instruction

    def disarm(self) -> None:
        """Clear the round (accept, revert, abort, or missing fence)."""
        self.armed = False
        self.section = ""
        self.previous_text = ""
        self.instruction = ""


def format_revise_prompt(section: str, current: str, instruction: str) -> str:
    """Revise-turn prompt: quoted section plus instruction (resolved item 6)."""
    return (
        f"Current '{section}' section (quoted):\n{current}\n\n"
        f"Instruction:\n{instruction}\n\n"
        "Revise the quoted memory section per the instruction. "
        "Reply with the FULL revised section in one fenced block, "
        "then a one-line summary of what changed."
    )


class InitState:
    """Session-sticky /init draft holder (D-09).

    Armed by ``/init`` with the scan report plus the stale section
    list; the loop consumes the armed draft after the agent turn.
    In-memory like :class:`MemoryModeState`. ``report`` is
    ScanReport-shaped (kept untyped: memory_file owns that type and
    importing it here would cycle).
    """

    def __init__(self) -> None:
        self.armed = False
        self.depth = "shallow"
        self.report: Any = None
        self.stale_sections: list[str] = []

    def arm(self, depth: str, report: Any, stale_sections: list[str]) -> None:
        """Arm a draft round for one scan depth plus its stale sections."""
        self.armed = True
        self.depth = depth
        self.report = report
        self.stale_sections = list(stale_sections)

    def disarm(self) -> None:
        """Clear the draft round (consumed, fresh, or aborted)."""
        self.armed = False
        self.depth = "shallow"
        self.report = None
        self.stale_sections = []


def format_init_prompt(report: Any, stale_sections: list[str]) -> str:
    """Init-draft prompt: scan outline plus the stale-only section list.

    Names ONLY the stale sections and requires one labeled fenced
    block per section; drafts stay labeled proposed until approved.
    """
    names = ", ".join(stale_sections)
    return (
        f"Repo scan ({report.depth}):\n{report.outline}\n\n"
        f"Draft ONLY these memory sections: {names}.\n"
        "Do not read .agent/sessions, session snapshots, or the session "
        "index — draft from the scan outline above, no tool exploration "
        "of agent internals.\n"
        "Reply with one fenced block per section. Each block MUST open with "
        "```proposed: <Section> on its own line, hold the FULL section body, "
        "and close with ```. Keep every draft labeled proposed — never "
        "present unapproved drafts as established repo fact."
    )


def _proposal_fingerprint(section: str, body: str) -> tuple[str, str]:
    """Canonical (section, normalized_body) key for deny deduplication."""
    return (section.strip().lower(), " ".join(body.split()))


class CurateQueue:
    """Pending memory proposals with session-sticky deny memory.

    Ids auto-generate as ``p1``, ``p2``, ... unless the caller passes
    an explicit ``proposal_id``. Denied ids and denied content
    fingerprints are refused on re-propose (the no-nag prohibition);
    pending and approved ids refuse duplicates so the queue can never
    hold two entries under one id.
    """

    def __init__(self) -> None:
        self._pending: dict[str, Proposal] = {}
        self._approved: set[str] = set()
        self._denied: set[str] = set()
        self._denied_fingerprints: set[tuple[str, str]] = set()
        self._counter = 0

    @property
    def denied_ids(self) -> set[str]:
        """Ids denied this session — never re-queued unprompted."""
        return set(self._denied)

    def propose(
        self,
        section: str,
        source: str,
        body: str,
        created_turn: str = "",
        proposal_id: str | None = None,
    ) -> Proposal | None:
        """Queue a proposal; None when the id or content was already denied.

        A denied id or previously denied ``(section, normalized_body)``
        is refused before advancing the counter — a denied proposal is
        never re-queued unprompted in the same session.
        """
        fingerprint = _proposal_fingerprint(section, body)
        if fingerprint in self._denied_fingerprints:
            return None
        if proposal_id is None:
            while True:
                self._counter += 1
                candidate = f"p{self._counter}"
                if (
                    candidate not in self._pending
                    and candidate not in self._approved
                    and candidate not in self._denied
                ):
                    proposal_id = candidate
                    break
        elif (
            proposal_id in self._pending
            or proposal_id in self._approved
            or proposal_id in self._denied
        ):
            return None
        proposal = Proposal(
            id=proposal_id,
            section=section,
            source=source,
            body=body,
            created_turn=created_turn,
        )
        self._pending[proposal_id] = proposal
        return proposal

    def list_pending(self) -> list[Proposal]:
        """Pending proposals in queue order."""
        return list(self._pending.values())

    def approve(self, proposal_id: str, apply_fn: Callable[[Proposal], None]) -> str:
        """Apply one proposal through the file write; marks it approved.

        The write runs before any queue mutation: a raising write
        leaves the entry pending for retry or the next turn.
        """
        proposal = self._pending.get(proposal_id)
        if proposal is None:
            return unknown_proposal(proposal_id)
        apply_fn(proposal)
        del self._pending[proposal_id]
        self._approved.add(proposal_id)
        return (
            f"Approved {sanitize_display(proposal_id)}"
            f" → {sanitize_display(proposal.section)}."
        )

    def deny(self, proposal_id: str) -> str:
        """Skip one proposal; records id and content so it never re-queues.

        Records only — no covering, no file write (the D-02 deny
        shape: deny-skips-and-continues).
        """
        proposal = self._pending.pop(proposal_id, None)
        if proposal is None:
            return unknown_proposal(proposal_id)
        self._denied.add(proposal_id)
        self._denied_fingerprints.add(
            _proposal_fingerprint(proposal.section, proposal.body)
        )
        return (
            f"Denied {sanitize_display(proposal_id)}"
            " — skipped, will not re-ask this session."
        )

    def sweep_promotions(
        self,
        memory_dir: str | Path,
        seen: set[str],
        limit: int = PROMOTION_SWEEP_LIMIT,
        skip_sections: set[str] | None = None,
    ) -> list[Proposal]:
        """Queue promoted proposals for new fact files, capped per sweep.

        Diffs the ``.md`` filename set under ``memory_dir`` against
        ``seen``, which is mutated in place with exactly the files
        queued — the remainder surface on later sweeps. Files whose
        stem already lives in ``skip_sections`` (sections memorialized
        in ``.agent/MEMORY.md``) are marked seen but never queued.
        Fact files are read, never deleted; a missing dir, symlinks,
        and unreadable files yield nothing.
        """
        try:
            fact_dir = Path(memory_dir)
            refuse_symlink(fact_dir, "memory fact dir", max_ancestors=1)
            names = sorted(
                p.name
                for p in fact_dir.glob("*.md")
                if p.is_file() and not p.is_symlink()
            )
        except (OSError, ValueError):
            return []
        skip = skip_sections or set()
        queued: list[Proposal] = []
        for name in names:
            if len(queued) >= limit:
                break
            if name in seen:
                continue
            if Path(name).stem in skip:
                seen.add(name)
                continue
            try:
                body = (Path(memory_dir) / name).read_text(encoding="utf-8")
            except OSError:
                continue
            proposal = self.propose(
                section=Path(name).stem, source="promoted", body=body
            )
            seen.add(name)
            if proposal is None:
                continue
            queued.append(proposal)
        return queued
