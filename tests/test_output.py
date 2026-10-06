"""REPL output must preserve ANSI escapes (no raw ?[ sequences on screen).

prompt_toolkit's default ``patch_stdout`` routes writes through
``Vt100_Output.write``, which replaces every ESC byte with ``?``. The
REPL must patch stdout in raw mode instead.

Dynamic transcript text (G-6-R2-3) must render literally through
``print_plain`` — markup chars from repo/model/exception content can
neither garble nor raise ``MarkupError``.
"""

import io
from types import SimpleNamespace

from prompt_toolkit.history import InMemoryHistory
from rich.console import Console

import strands_code_cli.loop as loop_module
from strands_code_cli.output import output_context, print_plain
from strands_code_cli.session_index import SessionIndex


def test_output_context_uses_raw_mode():
    with output_context() as proxy:
        assert proxy.raw is True


def test_print_plain_renders_markup_chars_literally(capsys):
    console = Console(width=120)
    print_plain(console, "boom [/] and [/red] stay literal")
    print_plain(console, "Turn failed (ValueError): boom [/]", style="red")
    out = capsys.readouterr().out
    assert "boom [/] and [/red] stay literal" in out
    assert "Turn failed (ValueError): boom [/]" in out


def _oneshot_loop(monkeypatch, first_line):
    """Fake PromptSession yielding one line, then EOF (run_loop harness)."""
    monkeypatch.setattr(loop_module, "_history", lambda: InMemoryHistory())
    lines = iter([first_line])

    class _FakeSession:
        def __init__(self, history=None, completer=None):
            pass

        def prompt(self, *args, **kwargs):
            try:
                return next(lines)
            except StopIteration:
                raise EOFError

    monkeypatch.setattr(loop_module, "PromptSession", _FakeSession)


def test_loop_reply_with_markup_chars_survives(tmp_path, monkeypatch, capfd):
    monkeypatch.chdir(tmp_path)
    _oneshot_loop(monkeypatch, "/[/]")
    agent = SimpleNamespace(messages=[], add_hook=lambda *a, **k: None)
    loop_module.run_loop(
        agent,
        session_id="markup-reply",
        index=SessionIndex(tmp_path / "index"),
        model_id="test-model",
    )
    assert "/[/]" in capfd.readouterr().out


def test_loop_turn_failure_with_markup_chars_fails_turn_not_session(
    tmp_path, monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    _oneshot_loop(monkeypatch, "hi")
    # Explicit StringIO console: turn prints run inside output_context's
    # swapped stdout, which pytest capture sees inconsistently.
    buffer = io.StringIO()
    monkeypatch.setattr(
        loop_module, "console", Console(file=buffer, width=120, legacy_windows=False)
    )

    class _BoomAgent:
        def __init__(self):
            self.messages = []

        def add_hook(self, *args, **kwargs):
            pass

        def __call__(self, text, **kwargs):
            raise ValueError("boom [/] in exception text")

    loop_module.run_loop(
        _BoomAgent(),
        session_id="markup-failure",
        index=SessionIndex(tmp_path / "index"),
        model_id="test-model",
    )
    out = buffer.getvalue()
    assert "Turn failed (ValueError): boom [/] in exception text" in out
    assert "Session saved." in out
