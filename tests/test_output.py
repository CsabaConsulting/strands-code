"""REPL output must preserve ANSI escapes (no raw ?[ sequences on screen).

prompt_toolkit's default ``patch_stdout`` routes writes through
``Vt100_Output.write``, which replaces every ESC byte with ``?``. The
REPL must patch stdout in raw mode instead.
"""

from strands_code_cli.output import output_context


def test_output_context_uses_raw_mode():
    with output_context() as proxy:
        assert proxy.raw is True
