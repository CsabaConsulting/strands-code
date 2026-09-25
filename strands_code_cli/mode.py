"""Plan/Act session modes (MODE-01, MODE-02, D-05..D-08).

Session-sticky, in-memory only: new sessions default to ``act`` (D-05),
``/mode plan|act`` switches mid-session with a transcript announcement
(D-06), and the choice persists for the session (D-07). Only ``plan``
and ``act`` exist — no general auto mode (D-08).

Copy uses mode vocabulary only: never policy-rule words, never
``/diff`` mode terms (``approve-each``/``on-demand``/``auto``).
"""

from __future__ import annotations

PLAN_PREFIX = """You are in Plan mode: read-only. Propose work, do not run it.
Survey with read-only tools and render a numbered step list shaped as:

Files to touch:
1. <verb> <target> — <one-line why>

Commands to run:
1. <verb> <target> — <one-line why>

Revise rounds are freeform: the user replies in plain words and you
re-plan. Close every plan with exactly:
Reply with revisions in plain words, or /approve to execute."""

MODE_PLAN_REPLY = "Mode: plan — read-only, proposes steps for /approve."
MODE_ACT_REPLY = "Mode: act — executing with approvals."
MODE_USAGE = "Usage: /mode [plan|act]"
APPROVE_OK = "Plan approved — switched to act."
APPROVE_EMPTY = "No pending plan — switch to Plan with /mode plan first."


class ModeState:
    """Session-sticky plan/act holder plus the pending-plan flag.

    ``mode`` is ``"plan"`` or ``"act"`` (anything else raises
    ``ValueError`` — there is no third mode). ``pending_plan`` is set
    when a Plan-mode turn proposes steps and cleared on ``/approve``
    or any ``/mode`` switch.
    """

    VALID = ("plan", "act")

    def __init__(self, initial: str = "act") -> None:
        if initial not in self.VALID:
            raise ValueError(f"unknown mode {initial!r}: expected plan|act")
        self._mode = initial
        self._pending_plan = False

    @property
    def mode(self) -> str:
        """Current mode (``"plan"`` or ``"act"``)."""
        return self._mode

    @property
    def pending_plan(self) -> bool:
        """True when a Plan turn proposed steps not yet approved."""
        return self._pending_plan

    def set(self, mode: str) -> str:
        """Switch mode; returns the transcript announcement.

        Raises:
            ValueError: For anything outside ``plan|act``.
        """
        if mode not in self.VALID:
            raise ValueError(f"unknown mode {mode!r}: expected plan|act")
        self._mode = mode
        self._pending_plan = False
        return MODE_PLAN_REPLY if mode == "plan" else MODE_ACT_REPLY

    def announce(self) -> str:
        """Current-mode report for bare ``/mode``."""
        return MODE_PLAN_REPLY if self._mode == "plan" else MODE_ACT_REPLY

    def note_plan_proposed(self) -> None:
        """Mark that a Plan-mode turn proposed steps (arms ``/approve``)."""
        self._pending_plan = True

    def approve(self) -> str:
        """Approve the pending plan: clear the flag, flip to act.

        Returns:
            The transcript reply (approval grant or guidance).
        """
        if not self._pending_plan:
            return APPROVE_EMPTY
        self._pending_plan = False
        self._mode = "act"
        return APPROVE_OK
