"""Wave 0 + concurrency + resource-limit tests for MontyPythonInterpreter (SANDBOX-02)."""

from __future__ import annotations

import threading
import types

import pydantic_monty as pm
import pytest

from strands_code_cli.sandbox.monty import (
    MONTY_DEFAULT_TIMEOUT_SECONDS,
    MONTY_MAX_MEMORY_BYTES,
    MONTY_MAX_RECURSION_DEPTH,
    MONTY_MAX_STDOUT_BYTES,
    MontyPythonInterpreter,
    close_agent_repls,
    close_repl_tool,
    shutdown_shared_pool,
)


@pytest.fixture(autouse=True)
def _cleanup_monty_pool():
    yield
    shutdown_shared_pool()


class TestMontyPythonInterpreter:
    def test_stateful_execution_stdout_builtins_and_errors(self):
        interp = MontyPythonInterpreter()
        assert interp.max_memory_bytes == MONTY_MAX_MEMORY_BYTES == 256 * 1024 * 1024
        assert interp.timeout_seconds == MONTY_DEFAULT_TIMEOUT_SECONDS == 60.0
        assert interp.max_recursion_depth == MONTY_MAX_RECURSION_DEPTH == 200
        assert interp.max_stdout_bytes == MONTY_MAX_STDOUT_BYTES == 4 * 1024 * 1024

        out1, err1 = interp.execute_code("val = 40\nprint('hello', ascii('a'))")
        assert err1 == ""
        assert out1 == "hello 'a'"

        out2, err2 = interp.execute_code("print(val + 2)")
        assert err2 == ""
        assert out2 == "42"

        out3, err3 = interp.execute_code("print('partial')\n1 / 0")
        assert out3 == "partial"
        assert "ZeroDivisionError" in err3

        # Session survives normal MontyRuntimeError.
        out4, err4 = interp.execute_code("print(val)")
        assert err4 == ""
        assert out4 == "40"

        tool = interp.get_tool()
        assert tool.tool_name == "python_repl"
        assert getattr(tool, "_interpreter", None) is interp
        assert tool(code="print(val + 8)") == "STDOUT:\n48"
        assert tool(code="x_only = 1") == "Code executed successfully."
        assert "STDERR:" in tool(code="def (")

    def test_pure_stdlib_allowed_and_os_pathlib_subprocess_denied(self):
        interp = MontyPythonInterpreter()
        out, err = interp.execute_code(
            "import math, json, re, collections, datetime, base64, dataclasses\n"
            "print(math.floor(3.9), json.dumps({'ok': bool(re.match('a+', 'aaa'))}))"
        )
        assert err == ""
        assert out == '3 {"ok": true}'

        for bad in (
            "import os",
            "import os as _o",
            "from os import path",
            "import pathlib",
            "from pathlib import Path",
            "import subprocess",
            "from subprocess import run",
            "__import__('os')",
            "importlib.import_module('subprocess')",
        ):
            stdout, stderr = interp.execute_code(bad)
            assert stdout == ""
            assert "not allowed" in stderr, (
                f"expected denial for {bad!r}, got {stderr!r}"
            )

    def test_external_lookup_callbacks_and_clear_state_with_init(self):
        seen: list[str] = []

        def greet(name: str) -> str:
            seen.append(name)
            return f"hi {name}"

        interp = MontyPythonInterpreter(
            state_initialization="BASE = 10",
            additional_functions={"greet": greet},
        )
        out1, err1 = interp.execute_code("tmp = 5\nprint(BASE + tmp, greet('ada'))")
        assert err1 == ""
        assert out1 == "15 hi ada"
        assert seen == ["ada"]

        interp.clear_state()
        _, err_missing = interp.execute_code("print(tmp)")
        assert "not defined" in err_missing

        out2, err2 = interp.execute_code("print(BASE)")
        assert err2 == ""
        assert out2 == "10"

    def test_fails_closed_when_monty_missing_or_binary_unavailable(
        self, monkeypatch, tmp_path
    ):
        import sys

        import strands_code_cli.sandbox.monty as monty_mod

        healthy = MontyPythonInterpreter()
        assert healthy.execute_code("keep_alive = 123") == ("", "")
        healthy_pool = monty_mod._SHARED_POOL
        assert healthy_pool is not None

        interp = MontyPythonInterpreter(binary_path="/nonexistent/path/to/monty")
        out, err = interp.execute_code("print(1 + 1)")
        assert out == ""
        assert "Monty Python VM unavailable" in err
        assert monty_mod._SHARED_POOL is healthy_pool

        not_exec = tmp_path / "not_exec_monty"
        not_exec.write_text("not executable", encoding="utf-8")
        not_exec.chmod(0o644)
        _, err_nx = MontyPythonInterpreter(binary_path=str(not_exec)).execute_code(
            "print(1)"
        )
        assert "not executable" in err_nx
        assert monty_mod._SHARED_POOL is healthy_pool

        _, err_ctrl = MontyPythonInterpreter(
            binary_path="/tmp/bad\nmonty"
        ).execute_code("print(1)")
        assert "control character" in err_ctrl
        _, err_bidi = MontyPythonInterpreter(
            binary_path="/tmp/bad\u202emonty"
        ).execute_code("print(1)")
        assert "control character" in err_bidi
        assert monty_mod._SHARED_POOL is healthy_pool
        assert healthy.execute_code("print(keep_alive)") == ("123", "")

        interp2 = MontyPythonInterpreter()
        monkeypatch.setitem(sys.modules, "pydantic_monty", None)
        out2, err2 = interp2.execute_code("print(1 + 1)")
        assert out2 == ""
        assert "Monty Python VM unavailable" in err2

    def test_stdout_cap_and_resource_limits(self):
        from strands_code_cli.sandbox.monty import _StdoutCollector

        default_collector = _StdoutCollector()
        default_collector("stdout", "a" * (MONTY_MAX_STDOUT_BYTES + 16))
        assert "[stdout truncated at 4 MiB]" in default_collector.text

        capped = MontyPythonInterpreter(max_stdout_bytes=64)
        out, err = capped.execute_code("print('x' * 200)")
        assert err == ""
        assert "[stdout truncated at 64 bytes]" in out
        assert len(out.encode("utf-8")) < 200

        timed = MontyPythonInterpreter(timeout_seconds=0.05)
        out_t, err_t = timed.execute_code(
            "print('before timeout')\nwhile True:\n    pass"
        )
        assert out_t == "before timeout"
        assert "TimeoutError" in err_t
        assert "REPL state was reset" in err_t
        assert timed._session is None
        assert timed.execute_code("print('recovered')") == ("recovered", "")

        bounded_mem = MontyPythonInterpreter(max_memory_bytes=1024 * 1024)
        out_m, err_m = bounded_mem.execute_code(
            "print('before oom')\nbig = [0] * 10_000_000"
        )
        assert out_m == "before oom"
        assert "MemoryError" in err_m

        deep = MontyPythonInterpreter(max_recursion_depth=25)
        _, err_r = deep.execute_code("def f(n):\n    return f(n + 1)\nf(0)")
        assert "RecursionError" in err_r

    def test_real_monty_crashed_error_salvages_stdout_and_recovers(self, monkeypatch):
        import strands_code_cli.sandbox.monty as monty_mod

        short_pool = pm.Monty(min_processes=1, request_timeout=0.05)
        short_pool.__enter__()
        try:
            monkeypatch.setattr(
                monty_mod, "_get_shared_pool", lambda _bin=None: short_pool
            )
            interp = MontyPythonInterpreter(state_initialization="KEEP = 7")
            out_ok, err_ok = interp.execute_code("ephemeral = 99\nprint(KEEP)")
            assert (out_ok, err_ok) == ("7", "")

            out_crash, err_crash = interp.execute_code(
                "print('before worker kill')\nwhile True:\n    pass"
            )
            assert out_crash == "before worker kill"
            assert "crashed" in err_crash.lower()
            assert "REPL state was reset" in err_crash
            assert interp._session is None

            # Fresh worker recovery preserves state_initialization and drops ephemeral var.
            out_after, err_after = interp.execute_code("print(KEEP)")
            assert (out_after, err_after) == ("7", "")
            _, err_eph = interp.execute_code("print(ephemeral)")
            assert "not defined" in err_eph
        finally:
            short_pool.__exit__(None, None, None)

    def test_concurrent_sessions_isolated_and_deterministic_teardown(self):
        a = MontyPythonInterpreter()
        b = MontyPythonInterpreter()
        results: dict[str, tuple[str, str]] = {}

        def _worker(key: str, interp: MontyPythonInterpreter, val: int) -> None:
            interp.execute_code(f"secret = {val}")
            results[key] = interp.execute_code("print(secret)")

        t1 = threading.Thread(target=_worker, args=("a", a, 101))
        t2 = threading.Thread(target=_worker, args=("b", b, 202))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)
        assert results == {"a": ("101", ""), "b": ("202", "")}

        tool_a = a.get_tool()
        fake_agent = types.SimpleNamespace(
            tool_registry=types.SimpleNamespace(registry={"python_repl": tool_a})
        )
        close_agent_repls(fake_agent)
        assert a._session is None
        close_repl_tool(b.get_tool())
        assert b._session is None
        shutdown_shared_pool()

    def test_nyquist_monty_edge_branches(self, monkeypatch):
        from strands_code_agent.python_environments.base import PythonInterpreter
        from strands_code_cli.sandbox.monty import (
            _check_denied_imports,
            _close_pool_instance,
            _close_tool_children,
            _is_monty_timeout,
            _StdoutCollector,
            _wrap_callback,
        )

        # _StdoutCollector empty chunk, exact fill, and post-truncation skip.
        col = _StdoutCollector(max_bytes=4)
        col("stdout", "")
        col("stdout", "abcd")
        col("stdout", "e")
        assert col.truncated is True
        assert "[stdout truncated at 4 bytes]" in col.text

        # Dynamic import non-string arg and safe __import__('math').
        assert _check_denied_imports("__import__(dyn)") is None
        assert _check_denied_imports("__import__('math')") is None

        # Pool close exception, timeout helper edge, non-callable callback.
        class _BadPool:
            def __exit__(self, *a):
                raise RuntimeError("pool close boom")

        _close_pool_instance(_BadPool())

        class _BadExc(Exception):
            def exception(self):
                raise RuntimeError("broken exception()")

        assert _is_monty_timeout(_BadExc()) is False
        assert _wrap_callback(42) == 42  # type: ignore[arg-type]

        # state_initialization failing discards session.
        bad_init = MontyPythonInterpreter(state_initialization="import os")
        assert "not allowed" in bad_init.execute_code("print(1)")[1]
        assert bad_init._session is None

        # _session is None fallback & unexpected feed_run RuntimeError.
        plain = MontyPythonInterpreter()
        assert "no active session" in plain._run_snippet_unlocked("print(1)")[1]

        class _BoomSession:
            def feed_run(self, *a, **kw):
                raise RuntimeError("unexpected host failure")

        plain._session = _BoomSession()
        assert plain._run_snippet_unlocked("print(1)") == (
            "",
            "unexpected host failure",
        )
        plain._session = None

        # _session_ctx.__exit__ error tolerated on discard.
        class _BadCtx:
            def __exit__(self, *a):
                raise RuntimeError("ctx exit boom")

        plain._session_ctx = _BadCtx()
        plain.clear_state()

        # get_tool read-only return, close_repl_tool & _close_tool_children error safety.
        ro = object()
        monkeypatch.setattr(PythonInterpreter, "get_tool", lambda self: ro)
        assert plain.get_tool() is ro

        class _BadClose:
            def close(self):
                raise RuntimeError("close boom")

        close_repl_tool(types.SimpleNamespace(_interpreter=_BadClose()))
        _close_tool_children(
            types.SimpleNamespace(
                _close_children=lambda: (_ for _ in ()).throw(RuntimeError("boom"))
            )
        )
