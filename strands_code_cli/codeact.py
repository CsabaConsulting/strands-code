"""Session action-interface selection (TOOL-07, D-01..D-04, D-13..D-20).

Session-sticky, in-memory only: new sessions default to ``tool`` (D-03),
``/codeact tool|code|both`` switches mid-session with a transcript
announcement (D-01), and the choice persists for the session. Switches
apply at the next ask only (D-19): the turn interface is resolved once
when the ask is sent (D-14, :func:`resolve_turn_interface`), one
interface per turn. History is never touched on a switch (D-20); cost
rows keep their shape (D-16) — interface records ride a loop-owned
parallel list.

Copy uses interface vocabulary only: never mode words (plan/act),
never policy-rule words, never ``/diff`` mode terms.
"""

from __future__ import annotations

CODEACT_PREFIX = """You are in CodeAct mode: solve this turn by generating Python first.

Do the work with Python code executed through the python_repl tool.
Inside generated code, call read, write, edit, and shell as plain
functions for file and command work — one interface per turn, so do
not also emit tool calls for work the code block covers. Use
absolute paths; file access stays inside the working directory plus
subdirectories and /tmp."""

CODEACT_TOOL_REPLY = "Interface: tool — gated tool-calling."
CODEACT_CODE_REPLY = "Interface: code — code-first actions through python_repl."
CODEACT_BOTH_REPLY = "Interface: both — route each ask at send time."
CODEACT_USAGE = "Usage: /codeact [tool|code|both]"


class CodeactState:
    """Session-sticky tool/code/both holder (ModeState mirror, D-01/D-03).

    ``interface`` is ``"tool"``, ``"code"``, or ``"both"`` (anything
    else raises ``ValueError`` — new sessions default to ``"tool"``).
    """

    VALID = ("tool", "code", "both")

    def __init__(self, initial: str = "tool") -> None:
        if initial not in self.VALID:
            raise ValueError(f"unknown interface {initial!r}: expected tool|code|both")
        self._interface = initial

    @property
    def interface(self) -> str:
        """Current interface (``"tool"``, ``"code"``, or ``"both"``)."""
        return self._interface

    def set(self, interface: str) -> str:
        """Switch interface; returns the transcript announcement.

        Raises:
            ValueError: For anything outside ``tool|code|both``.
        """
        if interface not in self.VALID:
            raise ValueError(f"unknown interface {interface!r}: expected tool|code|both")
        self._interface = interface
        if interface == "code":
            return CODEACT_CODE_REPLY
        if interface == "both":
            return CODEACT_BOTH_REPLY
        return CODEACT_TOOL_REPLY

    def announce(self) -> str:
        """Current-interface report for bare ``/codeact``."""
        if self._interface == "code":
            return CODEACT_CODE_REPLY
        if self._interface == "both":
            return CODEACT_BOTH_REPLY
        return CODEACT_TOOL_REPLY


def resolve_turn_interface(value: str) -> str:
    """Fix the turn's interface at send time (D-14 fix-at-send).

    Args:
        value: The holder's current interface.

    Returns:
        ``"code"`` for code-holder turns, ``"tool"`` otherwise —
        ``both`` runs tool-shaped until per-ask routing lands (11-02).

    Raises:
        ValueError: For anything outside ``tool|code|both``.
    """
    if value not in CodeactState.VALID:
        raise ValueError(f"unknown interface {value!r}: expected tool|code|both")
    return "code" if value == "code" else "tool"


def shape_turn_text(turn_interface: str, agent_text: str) -> str:
    """Prepend the code-first prefix on code turns; tool turns unchanged."""
    if turn_interface == "code":
        return f"{CODEACT_PREFIX}\n\n{agent_text}"
    return agent_text


def codeact_label(turn_interface: str) -> str:
    """Exact per-turn transcript label for the resolved interface (D-15)."""
    if turn_interface == "code":
        return "interface: codeact"
    return "interface: tool"


def resolve_initial_interface(
    flag: str | None, saved: str | None, remember: bool
) -> str:
    """Resolve the session-start interface by D-03 precedence.

    Args:
        flag: The ``--codeact`` value (None when the flag is absent).
        saved: The persisted last choice (None when never saved).
        remember: The remember-last-choice option (D-03).

    Returns:
        The flag first, then the saved choice when remembered,
        else ``"tool"`` (tool-calling stays the default).

    Raises:
        ValueError: For a flag or saved value outside ``tool|code|both``.
    """
    for value in (flag, saved):
        if value is not None and value not in CodeactState.VALID:
            raise ValueError(f"unknown interface {value!r}: expected tool|code|both")
    if flag is not None:
        return flag
    if remember and saved is not None:
        return saved
    return "tool"
