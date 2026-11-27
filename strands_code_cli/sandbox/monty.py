"""Crash-isolated Rust Python VM backend via ``pydantic-monty`` (SANDBOX-02)."""

from __future__ import annotations

import ast
import atexit
import os
import threading
import weakref
from collections.abc import Callable
from typing import Any

from strands_code_agent.python_environments.base import (
    STDERR_LABEL,
    STDOUT_LABEL,
    PythonInterpreter,
)

MONTY_MAX_MEMORY_BYTES = 256 * 1024 * 1024
"""Default Monty VM heap limit (256 MiB, D-05)."""

MONTY_DEFAULT_TIMEOUT_SECONDS = 60.0
"""Default Monty VM per-feed CPU timeout (60s, D-05)."""

MONTY_MAX_RECURSION_DEPTH = 200
"""Default Monty VM call stack depth limit (200, D-05)."""

MONTY_MAX_STDOUT_BYTES = 4 * 1024 * 1024
"""Default Monty stdout capture cap (4 MiB, D-05)."""

MONTY_DENIED_IMPORTS: frozenset[str] = frozenset({"os", "pathlib", "subprocess"})
"""Host-OS modules explicitly denied inside Monty (D-04)."""

_DEFAULT_REQUEST_TIMEOUT_GRACE = 5.0
_MISSING_BUILTINS: dict[str, Any] = {"ascii": ascii}

_POOL_LOCK = threading.Lock()
_SHARED_POOL: Any = None
_SHARED_POOL_BIN: str | None = None
_ATEXIT_REGISTERED = False
_ACTIVE_INTERPRETERS: weakref.WeakSet[MontyPythonInterpreter] = weakref.WeakSet()


class _StdoutCollector:
    """Bounded ``print_callback`` accumulator preserving partial output on crash."""

    def __init__(self, max_bytes: int = MONTY_MAX_STDOUT_BYTES) -> None:
        self._max_bytes = max_bytes
        self._parts: list[str] = []
        self._total = 0
        self.truncated = False

    def __call__(self, _stream: str, chunk: str) -> None:
        if not chunk or self.truncated:
            return
        raw = chunk.encode("utf-8", errors="replace")
        remaining = self._max_bytes - self._total
        if remaining <= 0:
            self.truncated = True
            return
        if len(raw) <= remaining:
            self._parts.append(chunk)
            self._total += len(raw)
            return
        clipped = raw[:remaining].decode("utf-8", errors="ignore")
        if clipped:
            self._parts.append(clipped)
        self._total = self._max_bytes
        self.truncated = True

    @property
    def text(self) -> str:
        out = "".join(self._parts)
        if self.truncated:
            limit_label = (
                "4 MiB"
                if self._max_bytes == MONTY_MAX_STDOUT_BYTES
                else f"{self._max_bytes} bytes"
            )
            out = f"{out.rstrip()}\n[stdout truncated at {limit_label}]"
        return out.strip()


def _denied_dynamic_import(node: ast.Call) -> str | None:
    func = node.func
    name: str | None = None
    if isinstance(func, ast.Name):
        name = func.id
    elif isinstance(func, ast.Attribute):
        name = func.attr
    if name not in ("__import__", "import_module"):
        return None
    if not node.args or not isinstance(node.args[0], ast.Constant):
        return None
    mod = node.args[0].value
    if isinstance(mod, str):
        root = mod.split(".", 1)[0]
        if root in MONTY_DENIED_IMPORTS:
            return root
    return None


def _check_denied_imports(code: str) -> str | None:
    """Return a refusal note when ``code`` imports ``os``, ``pathlib``, or ``subprocess``."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in MONTY_DENIED_IMPORTS:
                    return f"Import of {root!r} is not allowed."
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            if root in MONTY_DENIED_IMPORTS:
                return f"Import of {root!r} is not allowed."
        elif isinstance(node, ast.Call):
            denied = _denied_dynamic_import(node)
            if denied is not None:
                return f"Import of {denied!r} is not allowed."
    return None


def _close_pool_instance(pool: Any) -> None:
    if pool is None:
        return
    try:
        pool.__exit__(None, None, None)
    except Exception:
        pass


def shutdown_shared_pool() -> None:
    """Close all active Monty sessions and tear down the shared worker pool."""
    global _SHARED_POOL, _SHARED_POOL_BIN
    with _POOL_LOCK:
        active = list(_ACTIVE_INTERPRETERS)
        pool = _SHARED_POOL
        _SHARED_POOL = None
        _SHARED_POOL_BIN = None
    for interp in active:
        interp.close()
    _close_pool_instance(pool)


def _ensure_atexit_registered() -> None:
    global _ATEXIT_REGISTERED
    if not _ATEXIT_REGISTERED:
        atexit.register(shutdown_shared_pool)
        _ATEXIT_REGISTERED = True


def _resolve_monty_binary_path(explicit: str | None) -> str:
    from pydantic_monty._binary import find_monty_binary

    found = find_monty_binary(explicit)
    if any(
        ord(ch) < 32 or ord(ch) == 127 or 0xD800 <= ord(ch) <= 0xDFFF for ch in found
    ):
        raise ValueError("Invalid control character in Monty worker binary path")
    if not os.path.isfile(found):
        raise FileNotFoundError(f"Monty worker binary not found: {found}")
    if not os.access(found, os.X_OK):
        raise PermissionError(f"Monty worker binary is not executable: {found}")
    return found


def _get_shared_pool(binary_path: str | None = None) -> Any:
    """Lazily start or return the process-wide shared ``Monty`` worker pool."""
    global _SHARED_POOL, _SHARED_POOL_BIN
    import pydantic_monty as pm

    resolved_bin = _resolve_monty_binary_path(binary_path)
    with _POOL_LOCK:
        _ensure_atexit_registered()
        if _SHARED_POOL is not None and _SHARED_POOL_BIN == resolved_bin:
            return _SHARED_POOL

    pool = pm.Monty(
        binary_path=resolved_bin,
        min_processes=1,
        request_timeout=MONTY_DEFAULT_TIMEOUT_SECONDS + _DEFAULT_REQUEST_TIMEOUT_GRACE,
    )
    pool.__enter__()
    stale_pool: Any = None
    extra_pool: Any = None
    with _POOL_LOCK:
        if _SHARED_POOL is not None and _SHARED_POOL_BIN == resolved_bin:
            extra_pool = pool
            chosen = _SHARED_POOL
        else:
            stale_pool = _SHARED_POOL
            _SHARED_POOL = pool
            _SHARED_POOL_BIN = resolved_bin
            chosen = pool
    _close_pool_instance(extra_pool)
    _close_pool_instance(stale_pool)
    return chosen


def _is_monty_timeout(exc: BaseException) -> bool:
    inner_fn = getattr(exc, "exception", None)
    if callable(inner_fn):
        try:
            if isinstance(inner_fn(), TimeoutError):
                return True
        except Exception:
            pass
    return isinstance(exc, TimeoutError) or str(exc).startswith("TimeoutError:")


def _wrap_callback(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Adapt host callbacks for Monty external_lookup without leaking tracebacks."""
    if not callable(fn):
        return fn  # type: ignore[return-value]

    def _wrapped(*args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    return _wrapped


class MontyPythonInterpreter(PythonInterpreter):
    """Stateful ``PythonInterpreter`` backed by crash-isolated ``pydantic-monty``."""

    def __init__(
        self,
        state_initialization: str | None = None,
        stdout_label: str = STDOUT_LABEL,
        stderr_label: str = STDERR_LABEL,
        authorized_imports: Any = None,
        additional_functions: dict[str, Callable[..., Any]] | None = None,
        timeout_seconds: float = MONTY_DEFAULT_TIMEOUT_SECONDS,
        max_memory_bytes: int = MONTY_MAX_MEMORY_BYTES,
        max_recursion_depth: int = MONTY_MAX_RECURSION_DEPTH,
        max_stdout_bytes: int = MONTY_MAX_STDOUT_BYTES,
        binary_path: str | None = None,
    ) -> None:
        super().__init__(
            state_initialization=state_initialization,
            stdout_label=stdout_label,
            stderr_label=stderr_label,
        )
        del authorized_imports  # D-04: uniform pure-Rust stdlib + denied OS imports
        self.additional_functions = dict(_MISSING_BUILTINS)
        if additional_functions:
            self.additional_functions.update(additional_functions)
        self.timeout_seconds = float(timeout_seconds)
        self.max_memory_bytes = int(max_memory_bytes)
        self.max_recursion_depth = int(max_recursion_depth)
        self.max_stdout_bytes = int(max_stdout_bytes)
        self._binary_path = binary_path
        self._lock = threading.Lock()
        self._session: Any = None
        self._session_ctx: Any = None
        self._external_lookup = {
            name: _wrap_callback(fn) for name, fn in self.additional_functions.items()
        }
        with _POOL_LOCK:
            _ACTIVE_INTERPRETERS.add(self)

    def _discard_session_unlocked(self) -> None:
        ctx = self._session_ctx
        self._session = None
        self._session_ctx = None
        if ctx is not None:
            try:
                ctx.__exit__(None, None, None)
            except Exception:
                pass

    def _ensure_session_unlocked(self) -> tuple[Any | None, str]:
        if self._session is not None:
            return (self._session, "")
        try:
            import pydantic_monty as pm

            pool = _get_shared_pool(self._binary_path)
            limits = pm.ResourceLimits(
                max_memory=self.max_memory_bytes,
                max_duration_secs=self.timeout_seconds,
                max_recursion_depth=self.max_recursion_depth,
            )
            ctx = pool.checkout(limits=limits)
            session = ctx.__enter__()
            self._session_ctx = ctx
            self._session = session
        except Exception as exc:
            self._discard_session_unlocked()
            return (None, f"Monty Python VM unavailable: {exc}")

        if self.state_initialization:
            _init_out, init_err = self._run_snippet_unlocked(self.state_initialization)
            if init_err:
                self._discard_session_unlocked()
                return (None, init_err)
        return (self._session, "")

    def _run_snippet_unlocked(self, code: str) -> tuple[str, str]:
        denied = _check_denied_imports(code)
        if denied is not None:
            return ("", denied)
        if self._session is None:
            return ("", "Monty Python VM unavailable: no active session")
        import pydantic_monty as pm

        collector = _StdoutCollector(self.max_stdout_bytes)
        crash_types: tuple[type[BaseException], ...] = (
            pm.MontyCrashedError,
            pm.MontyDisconnectError,
            pm.MontyShutdown,
        )
        try:
            self._session.feed_run(
                code,
                external_lookup=self._external_lookup or None,
                print_callback=collector,
                os=None,
            )
            return (collector.text, "")
        except crash_types as exc:
            self._discard_session_unlocked()
            return (
                collector.text,
                f"Monty VM crashed ({exc}); REPL state was reset.",
            )
        except pm.MontyError as exc:
            if _is_monty_timeout(exc):
                self._discard_session_unlocked()
                return (
                    collector.text,
                    f"{exc} (REPL state was reset after time limit.)",
                )
            return (collector.text, str(exc))
        except Exception as exc:
            return (collector.text, str(exc))

    def clear_state(self) -> None:
        """Close the current VM session; next execution starts a fresh worker."""
        with self._lock:
            self._discard_session_unlocked()

    def close(self) -> None:
        """Deterministically release the checked-out Monty session (idempotent)."""
        self.clear_state()

    def execute_code(self, code: str) -> tuple[str, str]:
        """Run one Python snippet in the checked-out Monty worker session."""
        with self._lock:
            session, err = self._ensure_session_unlocked()
            if session is None:
                return ("", err)
            return self._run_snippet_unlocked(code)

    def get_tool(self) -> Any:
        """Build the ``python_repl`` Strands tool with a closeable handle attached."""
        tool = super().get_tool()
        try:
            tool._interpreter = self
        except (AttributeError, TypeError):
            pass
        return tool


def close_repl_tool(tool: Any) -> None:
    """Best-effort close of a ``MontyPythonInterpreter`` backing a ``python_repl`` tool."""
    interp = getattr(tool, "_interpreter", None)
    close_fn = getattr(interp, "close", None)
    if callable(close_fn):
        try:
            close_fn()
        except Exception:
            pass


def _close_tool_children(tool: Any) -> None:
    close_children = getattr(tool, "_close_children", None)
    if callable(close_children):
        try:
            close_children()
        except Exception:
            pass


def close_agent_repls(agent: Any) -> None:
    """Close any ``python_repl`` interpreter attached to ``agent`` or its registry."""
    registry = getattr(getattr(agent, "tool_registry", None), "registry", None)
    if isinstance(registry, dict):
        close_repl_tool(registry.get("python_repl"))
        _close_tool_children(registry.get("subagent"))
    close_repl_tool(getattr(agent, "_python_repl_tool", None))
    _close_tool_children(getattr(agent, "_subagent_tool", None))
    for extra in getattr(agent, "_delegate_repl_tools", None) or ():
        close_repl_tool(extra)
        _close_tool_children(extra)
