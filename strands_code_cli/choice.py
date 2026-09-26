"""Arrow-key choice dialogs for interactive prompts (replaces bare input()).

Bare ``input()`` leaves SIGINT racing the turn's signal-handler chain and
the steering reader: a second Ctrl-C landing mid-unwind wedged the
terminal (needed a full terminal kill). A prompt_toolkit application owns
SIGINT (loop-level ``send_sigint`` binding) and termios (finally-restored
``raw_mode``) for the dialog's duration, so Ctrl-C can neither leak raw
mode nor strand the reader.

Cancel contract (load-bearing, preserved from the typed prompt): Ctrl-C
in a dialog re-raises :class:`KeyboardInterrupt` so the loop's two-press
cancel handler still runs. ESC (or dialog abort) returns None, which
callers map to the fail-closed answer (deny / start-new). Unexpected
prompt_toolkit failures also return None — a broken prompt must deny,
never crash the turn.

Non-tty callers (tests, pipes) never reach the dialog: callers branch on
``sys.stdin.isatty()`` and keep their typed ``input()`` path, so existing
input fakes keep working unchanged.
"""

from __future__ import annotations

import sys
from typing import Any, Sequence

CANCELLED = object()
"""Sentinel: the user pressed Ctrl-C inside the dialog (must re-raise)."""


def _choice_fragments(
    values: Sequence[tuple[Any, str]], selected: int
) -> list[tuple[str, str]]:
    """Render all options with the highlight; no trailing newline."""
    parts: list[tuple[str, str]] = []
    for pos, (_, label) in enumerate(values):
        mark = "(*)" if pos == selected else "( )"
        parts.append(("", f" {mark} {label}"))
        parts.append(("", "\n"))
    parts.pop()
    return parts


def _build_app(
    title: str,
    values: list[tuple[Any, str]],
    default: int,
    *,
    input: Any = None,
    output: Any = None,
) -> Any:
    """Build the choice application (seam for headless tests).

    Bespoke control, not the stock ``RadioList``: that widget ships its own
    control-level bindings (Enter = "check the item", ``Keys.Any`` type to
    find) which shadow app-level ones — observed as Enter doing nothing
    and ESC hanging. Every key here is owned at control level, so no
    inherited binding can intercept: arrows move, Enter/Space confirms,
    ESC denies, Ctrl-C exits with :data:`CANCELLED`.
    """
    from prompt_toolkit.application import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.output import create_output
    from prompt_toolkit.widgets import Frame

    state = {"selected": min(default, len(values) - 1)}

    def _fragments() -> list[tuple[str, str]]:
        # Newlines are separate fragments: popping the trailing one must
        # never drop the last option (observed: "Start new session" and
        # "Never" silently missing from the rendered list).
        return _choice_fragments(values, state["selected"])

    bindings = KeyBindings()

    @bindings.add("up")
    def _up(event: Any) -> None:
        state["selected"] = max(0, state["selected"] - 1)

    @bindings.add("down")
    def _down(event: Any) -> None:
        state["selected"] = min(len(values) - 1, state["selected"] + 1)

    @bindings.add("enter")
    @bindings.add(" ")
    def _confirm(event: Any) -> None:
        event.app.exit(result=values[state["selected"]][0])

    @bindings.add("c-c")
    def _cancel(event: Any) -> None:
        # Ctrl-C must cancel the turn, not deny the prompt: exit with the
        # sentinel and re-raise below, after prompt_toolkit restored the
        # terminal and the previous SIGINT disposition.
        event.app.exit(result=CANCELLED)

    @bindings.add("escape")
    def _deny(event: Any) -> None:
        event.app.exit(result=None)

    control = FormattedTextControl(
        _fragments, key_bindings=bindings, focusable=True, show_cursor=False
    )
    kwargs: dict[str, Any] = {
        "layout": Layout(Frame(Window(content=control, dont_extend_height=True), title=title)),
        "full_screen": False,
        # Render straight to the real terminal: the turn's output proxy
        # must not capture raw escape sequences into the transcript.
        "output": output if output is not None else create_output(stdout=sys.__stdout__),
    }
    if input is not None:
        kwargs["input"] = input
    return Application(**kwargs)


def radio_choice(
    title: str,
    options: Sequence[tuple[Any, str]],
    *,
    default: int = 0,
) -> Any | None:
    """Arrow-key single choice; Enter confirms, ESC denies, Ctrl-C cancels.

    Args:
        title: Header line printed above the options.
        options: ``(value, label)`` pairs; the confirmed value is returned.
        default: Index of the initially highlighted option.

    Returns:
        The chosen value, or None on ESC/abort/failure.

    Raises:
        KeyboardInterrupt: The user pressed Ctrl-C (cancel path).
        RuntimeError: No tty — the caller must use its typed fallback.
    """
    if not sys.stdin.isatty():
        raise RuntimeError("radio_choice needs a tty")
    values = list(options)
    if not values:
        return None
    try:
        result = _build_app(title, values, default).run()
    except Exception:
        return None  # broken prompt denies, never crashes the turn
    if result is CANCELLED:
        raise KeyboardInterrupt
    return result
