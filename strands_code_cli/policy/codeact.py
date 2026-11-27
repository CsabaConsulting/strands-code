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
import os
import shlex
import stat
import subprocess
from pathlib import Path
from typing import Any

from strands_code_agent.python_environments.base import STDERR_LABEL, STDOUT_LABEL
from strands_code_cli.platform_io import (
    atomic_write_text,
    refuse_symlink_under_roots,
)
from strands_code_cli.policy.scope import confine, resolve
from strands_code_cli.sandbox.monty import MontyPythonInterpreter

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
            raise ValueError(
                f"unknown interface {interface!r}: expected tool|code|both"
            )
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


CODEACT_AUTHORIZED_IMPORTS = frozenset({"math", "json", "re"})
"""Pure-computation Monty VM stdlib note (D-04): host FS/OS stays behind callbacks."""

CODEACT_TIMEOUT_SECONDS = 60
"""Stint interpreter timeout (D-12 library default; no new setting)."""

CODEACT_SHELL_TIMEOUT_SECONDS = 60
"""Interior shell timeout, matching the interpreter bound (D-12)."""


def _load_codeact_policy(base: Path) -> tuple[Any | None, str | None]:
    """Load active home + repo policy fail-closed (returns error note on tamper)."""
    from strands_code_cli.policy.core import PolicyConfig

    try:
        return (PolicyConfig.load(repo_path=base / ".agent" / "policy.toml"), None)
    except ValueError as exc:
        return (None, f"Refused by policy: {exc}")


def _raw_walk_start(
    expanded: Path, base: Path, real_base: Path
) -> tuple[Path, tuple[str, ...]]:
    real_tmp = Path(os.path.realpath("/tmp"))
    if not expanded.is_absolute():
        return (real_base, expanded.parts)
    for root in (base, real_base):
        if expanded == root or root in expanded.parents:
            return (real_base, expanded.parts[len(root.parts) :])
    tmp_raw = Path("/tmp")
    for root in (tmp_raw, real_tmp):
        if expanded == root or root in expanded.parents:
            return (real_tmp, expanded.parts[len(root.parts) :])
    return (Path(expanded.anchor), expanded.parts[1:])


def _refuse_raw_symlink_traversal(
    raw_path: str, base: Path, real_base: Path, label: str
) -> Path:
    """Walk un-collapsed segments to catch ``symlink/../`` escapes while allowing symlinked ``cwd``."""
    expanded = Path(os.path.expanduser(raw_path))
    cur, parts = _raw_walk_start(expanded, base, real_base)
    resolved_input = (
        real_base / expanded
        if not expanded.is_absolute()
        else (cur / Path(*parts) if cur == real_base else expanded)
    )
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            cur = cur.parent
            continue
        cur = cur / part
        if cur.is_symlink():
            raise ValueError(f"Refusing symlink for {label}: {cur}")
    return resolved_input


def _prepare_codeact_path(
    cwd: str | Path, raw_path: str, op: str
) -> tuple[Path | None, str | None]:
    """Confine and check Phase 19.1 symlink, sensitive, protected, and [[deny]] rules."""
    from strands_code_cli.policy.core import (
        Deny,
        _is_protected_skills_or_config_path,
        _is_sensitive_read_path,
        decide,
    )

    base = Path(cwd)
    real_base = Path(os.path.realpath(base))
    policy, pol_err = _load_codeact_policy(real_base)
    if pol_err is not None or policy is None:
        return (None, pol_err or "Refused by policy")

    real_tmp = Path(os.path.realpath("/tmp"))
    roots = (real_base, real_tmp)
    try:
        rebased = _refuse_raw_symlink_traversal(
            raw_path, base, real_base, f"codeact {op} target"
        )
        target = confine(resolve(rebased, real_base), real_base)
        refuse_symlink_under_roots(target, roots, f"codeact {op} target")
    except ValueError as exc:
        return (None, str(exc))

    if op in ("read", "edit") and (
        _is_sensitive_read_path(raw_path, real_base)
        or _is_sensitive_read_path(str(target), real_base)
    ):
        return (None, f"Refused {op}: sensitive path {raw_path!r}")
    if op in ("write", "edit") and (
        _is_protected_skills_or_config_path(raw_path, real_base)
        or _is_protected_skills_or_config_path(str(target), real_base)
    ):
        return (None, f"Refused {op}: protected path {raw_path!r}")

    verdict = decide(op, {"path": str(target)}, policy, cwd=real_base)
    if isinstance(verdict, Deny):
        return (None, verdict.reason)
    return (target, None)


def _read_regular_file_utf8(
    target: Path, raw_path: str, op: str = "read"
) -> tuple[str | None, str | None]:
    """Read UTF-8 text from ``target`` with ``O_NOFOLLOW | O_NONBLOCK``."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(target, flags)
    except FileNotFoundError:
        return (None, f"File not found: {raw_path}")
    except OSError as exc:
        return (None, f"Could not read {raw_path}: {exc}")
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return (None, f"Refused {op}: {raw_path!r} is not a regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        return (b"".join(chunks).decode("utf-8", errors="strict"), None)
    except (OSError, UnicodeDecodeError) as exc:
        return (None, f"Could not read {raw_path}: {exc}")
    finally:
        os.close(fd)


def codeact_read(cwd: str | Path, path: str) -> str:
    """Read one in-scope regular file enforcing policy and symlink guards."""
    target, err = _prepare_codeact_path(cwd, path, "read")
    if err is not None or target is None:
        return err or "Refused read"
    text, read_err = _read_regular_file_utf8(target, path, "read")
    if read_err is not None or text is None:
        return read_err or f"Could not read {path}"
    return text


def codeact_write(cwd: str | Path, path: str, content: str) -> str:
    """Atomically write one in-scope file enforcing policy and symlink guards."""
    target, err = _prepare_codeact_path(cwd, path, "write")
    if err is not None or target is None:
        return err or "Refused write"
    try:
        atomic_write_text(
            target,
            content,
            mode=None,
            dir_mode=None,
            refuse_ancestors=1,
            label="codeact write target",
        )
    except (ValueError, OSError, UnicodeEncodeError) as exc:
        return f"Could not write {path}: {exc}"
    return f"Wrote {target}"


def codeact_edit(cwd: str | Path, path: str, old: str, new: str) -> str:
    """Replace the first ``old`` with ``new`` in one in-scope regular file."""
    target, err = _prepare_codeact_path(cwd, path, "edit")
    if err is not None or target is None:
        return err or "Refused edit"
    text, read_err = _read_regular_file_utf8(target, path, "edit")
    if read_err is not None or text is None:
        return read_err or f"Could not read {path}"
    if old not in text:
        return f"No match for {old!r} in {path}"
    try:
        atomic_write_text(
            target,
            text.replace(old, new, 1),
            mode=None,
            dir_mode=None,
            refuse_ancestors=1,
            label="codeact edit target",
        )
    except (ValueError, OSError, UnicodeEncodeError) as exc:
        return f"Could not write {path}: {exc}"
    return f"Edited {target}"


def _codeact_shell_cmd(argv: list[str] | tuple[str, ...]) -> list[str]:
    """Build subprocess argv, wrapping via ``sh -c`` inside Strands Box for Dogwood."""
    from strands_code_cli.sandbox.box import is_in_strands_box

    cmd = [str(part) for part in argv]
    if is_in_strands_box():
        return ["sh", "-c", shlex.join(cmd)]
    return cmd


def _codeact_shell_deny_candidates(cmd_parts: list[str]) -> list[str]:
    cands: list[str] = [shlex.join(cmd_parts)]
    head_base = os.path.basename(cmd_parts[0])
    if head_base and head_base != cmd_parts[0]:
        cands.append(shlex.join([head_base, *cmd_parts[1:]]))
    if head_base == "env":
        idx = 1
        while idx < len(cmd_parts) and (
            cmd_parts[idx].startswith("-") or "=" in cmd_parts[idx]
        ):
            idx += 1
        if idx < len(cmd_parts):
            rest = cmd_parts[idx:]
            cands.append(shlex.join(rest))
            rest_base = os.path.basename(rest[0])
            if rest_base and rest_base != rest[0]:
                cands.append(shlex.join([rest_base, *rest[1:]]))
    return cands


def codeact_shell(cwd: str | Path, argv: list[str]) -> str:
    """Run one argv command under ``cwd`` after evaluating ``[[deny]]`` rules."""
    if isinstance(argv, str) or not isinstance(argv, (list, tuple)):
        return "shell expects an argv list, e.g. shell(['ls'])"
    if not argv:
        return "shell expects a non-empty argv list"
    from strands_code_cli.policy.core import Deny, decide

    real_base = Path(os.path.realpath(Path(cwd)))
    policy, pol_err = _load_codeact_policy(real_base)
    if pol_err is not None or policy is None:
        return pol_err or "Refused shell"
    cmd_parts = [str(part) for part in argv]
    for cand in _codeact_shell_deny_candidates(cmd_parts):
        verdict = decide("shell", {"command": cand}, policy, cwd=real_base)
        if isinstance(verdict, Deny):
            return verdict.reason
    try:
        proc = subprocess.run(
            _codeact_shell_cmd(argv),
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
    """One CodeAct stint: a loop-owned Monty VM interpreter (D-10/D-11).

    Lazily builds a single :class:`MontyPythonInterpreter` whose
    ``additional_functions`` carry the hardened sync host
    ``read``/``write``/``edit``/``shell`` callables. REPL state persists
    across code turns within the stint; the loop calls :meth:`reset` on
    every interface switch and :meth:`close` on loop exit.
    """

    def __init__(self, cwd: str | Path) -> None:
        self._cwd = Path(cwd)
        self._interpreter: MontyPythonInterpreter | None = None
        self._tool: Any | None = None

    def _ensure(self) -> MontyPythonInterpreter:
        if self._interpreter is None:
            self._interpreter = MontyPythonInterpreter(
                "",
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

    def close(self) -> None:
        """Release the stint's Monty VM worker session cleanly."""
        if self._interpreter is not None:
            self._interpreter.close()

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


def resolve_initial_interface(flag: str | None, saved: str | None = None) -> str:
    """Resolve the session-start interface from CLI flag or config.yaml default.

    Args:
        flag: The ``--codeact`` value (None when the flag is absent).
        saved: Optional startup default from ``config.yaml`` (``codeact``).

    Returns:
        The CLI flag first, then the config.yaml default, else ``"tool"``.

    Raises:
        ValueError: For a flag or saved value outside ``tool|code|both``.
    """
    for value in (flag, saved):
        if value is not None and value not in CodeactState.VALID:
            raise ValueError(f"unknown interface {value!r}: expected tool|code|both")
    if flag is not None:
        return flag
    if saved is not None:
        return saved
    return "tool"
