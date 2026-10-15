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

import functools
import subprocess
from pathlib import Path
from typing import Any

from strands_code_agent.python_environments.base import STDERR_LABEL, STDOUT_LABEL
from strands_code_agent.python_environments.local_sandboxed import (
    SandboxedPythonInterpreter,
)
from strands_code_cli.scope import confine, resolve

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
CODEACT_ROUTE_USAGE = "Usage: /code <ask> or /tool <ask>"


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
        self._one_shot: str | None = None

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

    def arm_one_shot(self, interface: str) -> None:
        """Arm a one-turn ``/code`` / ``/tool`` routing override (D-13).

        Raises:
            ValueError: For anything outside ``code|tool``.
        """
        if interface not in ("code", "tool"):
            raise ValueError(f"unknown one-shot {interface!r}: expected code|tool")
        self._one_shot = interface

    def resolve_turn(self) -> str:
        """Consume one armed override, else the sticky holder value.

        Returns:
            The armed ``code``/``tool`` exactly once (D-14 one interface
            per turn), clearing the arm; otherwise the sticky value.
        """
        if self._one_shot is not None:
            armed, self._one_shot = self._one_shot, None
            return armed
        return self._interface


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


CODEACT_AUTHORIZED_IMPORTS = frozenset({"math"})
"""Stint import allowlist (D-10): capabilities ride narrow functions, never imports."""

CODEACT_TIMEOUT_SECONDS = 60
"""Stint interpreter timeout (D-12 library default; no new setting)."""

CODEACT_SHELL_TIMEOUT_SECONDS = 60
"""Interior shell timeout, matching the interpreter bound (D-12)."""


def codeact_read(cwd: str | Path, path: str) -> str:
    """Read one in-scope file; missing files report, never raise.

    Args:
        cwd: The REPL working directory the stint was bound to.
        path: Caller-supplied path (relative resolves against ``cwd``).

    Returns:
        The file text, a not-found note, or the confine refusal —
        interior functions return error strings, never raise into
        the executor.
    """
    try:
        target = confine(resolve(path, cwd), cwd)
    except ValueError as exc:
        return str(exc)
    try:
        return target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"File not found: {path}"
    except (OSError, UnicodeDecodeError) as exc:
        return f"Could not read {path}: {exc}"


def codeact_write(cwd: str | Path, path: str, content: str) -> str:
    """Write one in-scope file, creating parents; reports, never raises.

    Args:
        cwd: The REPL working directory the stint was bound to.
        path: Caller-supplied path (relative resolves against ``cwd``).
        content: Full replacement text for the file.

    Returns:
        A confirmation naming the path, or the confine refusal.
    """
    try:
        target = confine(resolve(path, cwd), cwd)
    except ValueError as exc:
        return str(exc)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except (OSError, UnicodeEncodeError) as exc:
        return f"Could not write {path}: {exc}"
    return f"Wrote {target}"


def codeact_edit(cwd: str | Path, path: str, old: str, new: str) -> str:
    """Replace the first ``old`` with ``new`` in one in-scope file.

    Args:
        cwd: The REPL working directory the stint was bound to.
        path: Caller-supplied path (relative resolves against ``cwd``).
        old: The text to find (first occurrence only).
        new: The replacement text.

    Returns:
        A confirmation, an absent-match note, a not-found note, or
        the confine refusal — never raises into the executor.
    """
    try:
        target = confine(resolve(path, cwd), cwd)
    except ValueError as exc:
        return str(exc)
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"File not found: {path}"
    except (OSError, UnicodeDecodeError) as exc:
        return f"Could not read {path}: {exc}"
    if old not in text:
        return f"No match for {old!r} in {path}"
    try:
        target.write_text(text.replace(old, new, 1), encoding="utf-8")
    except (OSError, UnicodeEncodeError) as exc:
        return f"Could not write {path}: {exc}"
    return f"Edited {target}"


def codeact_shell(cwd: str | Path, argv: list[str]) -> str:
    """Run one argv command under ``cwd``; no shell, labeled output.

    Args:
        cwd: The REPL working directory the stint was bound to.
        argv: Argument vector (a bare string is refused — argv only).

    Returns:
        Labeled stdout/stderr text with the exit code when nonzero,
        or an error note — never raises into the executor.
    """
    if isinstance(argv, str) or not isinstance(argv, (list, tuple)):
        return "shell expects an argv list, e.g. shell(['ls'])"
    if not argv:
        return "shell expects a non-empty argv list"
    try:
        proc = subprocess.run(
            list(argv),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=CODEACT_SHELL_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        return f"Command not found: {argv[0]}"
    except subprocess.TimeoutExpired:
        return f"Command timed out after {CODEACT_SHELL_TIMEOUT_SECONDS}s"
    except OSError as exc:
        return f"shell failed: {exc}"
    parts = []
    if proc.stdout:
        parts.append(f"{STDOUT_LABEL}{proc.stdout.rstrip()}")
    if proc.stderr:
        parts.append(f"{STDERR_LABEL}{proc.stderr.rstrip()}")
    if proc.returncode != 0:
        parts.append(f"exit code: {proc.returncode}")
    return "\n".join(parts) if parts else "Command ran with no output."


class CodeactStint:
    """One CodeAct stint: a loop-owned sandboxed interpreter (D-10/D-11).

    Lazily builds a single :class:`SandboxedPythonInterpreter` whose
    ``additional_functions`` carry the sync scope-confined
    ``read``/``write``/``edit``/``shell`` callables (D-09). REPL state
    persists across code turns within the stint (D-11); the loop calls
    :meth:`reset` on every interface switch (D-17). The stint
    interpreter is separate from the always-on tool-turn REPL, so
    tool turns never observe stint state.

    Args:
        cwd: The REPL working directory interior functions confine to.
    """

    def __init__(self, cwd: str | Path) -> None:
        self._cwd = Path(cwd)
        self._interpreter: SandboxedPythonInterpreter | None = None
        self._tool: Any | None = None

    def _ensure(self) -> SandboxedPythonInterpreter:
        if self._interpreter is None:
            self._interpreter = SandboxedPythonInterpreter(
                "",
                authorized_imports=CODEACT_AUTHORIZED_IMPORTS,
                additional_functions={
                    "read": functools.partial(codeact_read, self._cwd),
                    "write": functools.partial(codeact_write, self._cwd),
                    "edit": functools.partial(codeact_edit, self._cwd),
                    "shell": functools.partial(codeact_shell, self._cwd),
                },
                timeout_seconds=CODEACT_TIMEOUT_SECONDS,
            )
        return self._interpreter

    def execute_code(self, code: str) -> tuple[str, str]:
        """Run one code block in the stint REPL (builds it on first use)."""
        return self._ensure().execute_code(code)

    def reset(self) -> None:
        """Clear stint REPL state; a never-built stint stays unbuilt."""
        if self._interpreter is not None:
            self._interpreter.clear_state()

    @property
    def tool(self) -> Any:
        """The stint ``python_repl`` tool, built once (for per-turn swap)."""
        if self._tool is None:
            self._tool = self._ensure().get_tool()
        return self._tool


def default_repl_handle(agent: Any) -> Any | None:
    """Read the always-on ``python_repl`` handle; None when absent.

    Reads the public ``agent.tool_registry.registry`` mapping once at
    loop startup. Doubles and registries without ``python_repl`` yield
    None (fail-soft): code turns then skip the swap and stay
    prefix-shaped.
    """
    registry = getattr(getattr(agent, "tool_registry", None), "registry", None)
    if not isinstance(registry, dict):
        return None
    return registry.get("python_repl")


def swap_for_code_turn(
    agent: Any, turn_interface: str, stint_tool: Any | None, default_tool: Any | None
) -> bool:
    """Swap the stint tool in for code turns via public ``replace``.

    Args:
        agent: The session agent owning the tool registry.
        turn_interface: The resolved ``"code"`` or ``"tool"`` turn.
        stint_tool: The stint ``python_repl`` (None skips the swap).
        default_tool: The startup ``python_repl`` (None skips the swap).

    Returns:
        True exactly when the swap happened (caller restores).
    """
    if turn_interface != "code":
        return False
    if stint_tool is None or default_tool is None:
        return False
    replace = getattr(getattr(agent, "tool_registry", None), "replace", None)
    if replace is None:
        return False
    replace(stint_tool)
    return True


def restore_after_turn(agent: Any, swapped: bool, default_tool: Any | None) -> None:
    """Restore the default tool when a code turn swapped it in.

    Args:
        agent: The session agent owning the tool registry.
        swapped: The flag :func:`swap_for_code_turn` returned.
        default_tool: The startup ``python_repl`` to restore.
    """
    if not swapped or default_tool is None:
        return
    replace = getattr(getattr(agent, "tool_registry", None), "replace", None)
    if replace is not None:
        replace(default_tool)


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
