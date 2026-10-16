"""REPL output context: preserve ANSI escapes under prompt_toolkit.

prompt_toolkit's ``patch_stdout`` routes writes through
``Vt100_Output.write``, which replaces every ESC byte with ``?``
(prompt_toolkit 3.x, ``output/vt100.py``) — so Rich styling arrives as
literal ``?[1m`` sequences. ``raw=True`` switches the proxy to
``write_raw`` and preserves escapes. This helper mirrors
``patch_stdout`` exactly (same proxy, same stdio swap) and additionally
yields the proxy so tests can pin the contract.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from typing import Iterator

from prompt_toolkit.patch_stdout import StdoutProxy
from rich.console import Console


@contextmanager
def output_context() -> Iterator[StdoutProxy]:
    """Stdout patch that preserves ANSI escapes (see module docstring)."""
    with StdoutProxy(raw=True) as proxy:
        original_stdout, original_stderr = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = proxy  # type: ignore[assignment]
        try:
            yield proxy
        finally:
            sys.stdout, sys.stderr = original_stdout, original_stderr


def print_plain(console: Console, text: str, *, style: str | None = None) -> None:
    """Print dynamic text with Rich markup parsing off.

    Static styling rides the ``style`` kwarg; the content itself is
    never parsed, so repo/model/exception text containing ``[...]``
    can neither garble nor raise ``MarkupError`` (G-6-R2-3). All
    transcript prints of non-constant strings route through here.
    """
    console.print(text, style=style, markup=False)
