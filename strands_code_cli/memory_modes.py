"""Session-sticky memory modes: curate vs silent (SKILL-02, D-07).

Session-sticky, in-memory only: new sessions default to ``curate``
(every proposal prompts approve/deny — the deny-first posture),
``/memory mode silent`` opts into auto-apply with one transcript line
per applied write. Mirrors :class:`ModeState` exactly; no disk
persistence.
"""

from __future__ import annotations

MEMORY_MODE_CURATE_REPLY = "Memory mode: curate — every proposal prompts approve/deny."
MEMORY_MODE_SILENT_REPLY = "Memory mode: silent — proposals auto-apply, writes logged."
MEMORY_MODE_USAGE = "Usage: /memory mode [curate|silent]"


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
