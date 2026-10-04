"""Session-sticky memory modes: curate vs silent (SKILL-02, D-07).

Session-sticky, in-memory only: new sessions default to ``curate``
(every proposal prompts approve/deny — the deny-first posture),
``/memory mode silent`` opts into auto-apply with one transcript line
per applied write. Mirrors :class:`ModeState` exactly; no disk
persistence.

The curate surface rides :class:`CurateQueue`: promotion sweeps of
the harness fact store queue :class:`Proposal` records, ``/memory``
approve/deny verbs act on them immediately, and the loop's
turn-boundary review prompts per proposal in curate mode or
auto-applies with :func:`silent_note` lines in silent mode. Denied
ids are remembered for the session and never re-queued unprompted.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

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
        return MEMORY_MODE_CURATE_REPLY if mode == "curate" else MEMORY_MODE_SILENT_REPLY

    def announce(self) -> str:
        """Current-mode report for bare ``/memory mode``."""
        return MEMORY_MODE_CURATE_REPLY if self._mode == "curate" else MEMORY_MODE_SILENT_REPLY


def silent_note(section: str, source: str) -> str:
    """One transcript line per silent-mode applied write."""
    return f"Memory updated (silent): {section} ← {source}"


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


class CurateQueue:
    """Pending memory proposals with session-sticky deny memory.

    Ids auto-generate as ``p1``, ``p2``, ... unless the caller passes
    an explicit ``proposal_id``. Denied ids are refused on re-propose
    (the no-nag prohibition); pending and approved ids refuse
    duplicates so the queue can never hold two entries under one id.
    """

    def __init__(self) -> None:
        self._pending: dict[str, Proposal] = {}
        self._approved: set[str] = set()
        self._denied: set[str] = set()
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
        """Queue a proposal; None when the id is already known.

        A denied id is refused outright — a denied proposal is never
        re-queued unprompted in the same session.
        """
        if proposal_id is None:
            self._counter += 1
            proposal_id = f"p{self._counter}"
        if (
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
        """Apply one proposal through the file write; marks it approved."""
        proposal = self._pending.pop(proposal_id, None)
        if proposal is None:
            return unknown_proposal(proposal_id)
        apply_fn(proposal)
        self._approved.add(proposal_id)
        return f"Approved {proposal_id} → {proposal.section}."

    def deny(self, proposal_id: str) -> str:
        """Skip one proposal; records the id so it never re-queues.

        Records only — no covering, no file write (the D-02 deny
        shape: deny-skips-and-continues).
        """
        proposal = self._pending.pop(proposal_id, None)
        if proposal is None:
            return unknown_proposal(proposal_id)
        self._denied.add(proposal_id)
        return f"Denied {proposal_id} — skipped, will not re-ask this session."

    def sweep_promotions(
        self,
        memory_dir: str | Path,
        seen: set[str],
        limit: int = PROMOTION_SWEEP_LIMIT,
    ) -> list[Proposal]:
        """Queue promoted proposals for new fact files, capped per sweep.

        Diffs the ``.md`` filename set under ``memory_dir`` against
        ``seen``, which is mutated in place with exactly the files
        queued — the remainder surface on later sweeps. Fact files are
        read, never deleted; a missing dir, symlinks, and unreadable
        files yield nothing.
        """
        try:
            names = sorted(
                p.name
                for p in Path(memory_dir).glob("*.md")
                if p.is_file() and not p.is_symlink()
            )
        except OSError:
            return []
        queued: list[Proposal] = []
        for name in names:
            if len(queued) >= limit:
                break
            if name in seen:
                continue
            try:
                body = (Path(memory_dir) / name).read_text(encoding="utf-8")
            except OSError:
                continue
            proposal = self.propose(
                section=Path(name).stem, source="promoted", body=body
            )
            if proposal is None:  # pragma: no cover - counter ids never collide
                continue
            seen.add(name)
            queued.append(proposal)
        return queued
