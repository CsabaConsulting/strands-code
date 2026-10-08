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

import shutil
import sys
from typing import Any, Sequence

from strands_code_cli.steering import stdin_guard

CANCELLED = object()
"""Sentinel: the user pressed Ctrl-C inside the dialog (must re-raise)."""


def _choice_fragments(
    values: Sequence[tuple[Any, str]],
    selected: int,
    *,
    top: int = 0,
    visible: int | None = None,
) -> list[tuple[str, str]]:
    """Render the visible window with the highlight; no trailing newline.

    Long lists render only ``values[top:top + visible]`` so the frame fits
    the terminal; the highlight always sits on ``selected`` inside it.
    """
    window = values[top:] if visible is None else values[top : top + visible]
    parts: list[tuple[str, str]] = []
    for pos, (_, label) in enumerate(window, start=top):
        mark = "(*)" if pos == selected else "( )"
        parts.append(("", f" {mark} {label}"))
        parts.append(("", "\n"))
    if parts:
        parts.pop()
    return parts


def _build_app(
    title: str,
    values: list[tuple[Any, str]],
    default: int,
    *,
    input: Any = None,
    output: Any = None,
    visible_rows: int | None = None,
) -> Any:
    """Build the choice application (seam for headless tests).

    Bespoke control, not the stock ``RadioList``: that widget ships its own
    control-level bindings (Enter = "check the item", ``Keys.Any`` type to
    find) which shadow app-level ones — observed as Enter doing nothing
    and ESC hanging. Every key here is owned at control level, so no
    inherited binding can intercept: arrows move, Enter/Space confirms,
    ESC denies, Ctrl-C exits with :data:`CANCELLED`.

    Lists longer than the terminal scroll: only ``visible_rows`` options
    render and the window follows the highlight, so the marker can never
    disappear below the frame.
    """
    from prompt_toolkit.application import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.output import create_output
    from prompt_toolkit.widgets import Frame

    count = len(values)
    if visible_rows is None:
        # Frame borders plus margin; never fewer than 3 rows.
        visible_rows = max(3, shutil.get_terminal_size().lines - 4)
    visible = max(1, min(visible_rows, count))
    selected = min(default, count - 1)
    state = {"selected": selected, "top": max(0, selected - visible + 1)}

    def _fragments() -> list[tuple[str, str]]:
        # Newlines are separate fragments: popping the trailing one must
        # never drop the last option (observed: "Start new session" and
        # "Never" silently missing from the rendered list).
        return _choice_fragments(
            values, state["selected"], top=state["top"], visible=visible
        )

    bindings = KeyBindings()

    @bindings.add("up")
    def _up(event: Any) -> None:
        state["selected"] = max(0, state["selected"] - 1)
        if state["selected"] < state["top"]:
            state["top"] = state["selected"]

    @bindings.add("down")
    def _down(event: Any) -> None:
        state["selected"] = min(count - 1, state["selected"] + 1)
        if state["selected"] >= state["top"] + visible:
            state["top"] = state["selected"] - visible + 1

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
    # Single choke point for every mid-turn dialog: hold the stdin
    # guard for the dialog's whole lifetime so the steering reader
    # never steals its keys, and drain prompt_toolkit typeahead on
    # entry so mashed keys from a lagged dialog cannot auto-confirm
    # the next one (G-7-1-R2b RC-1 + RC-2). Kernel-buffered bytes are
    # left alone — legitimately typed steering survives for after.
    stdin_guard.set()
    try:
        try:
            from prompt_toolkit.input import create_input
            from prompt_toolkit.input.typeahead import clear_typeahead

            clear_typeahead(create_input())
        except Exception:
            pass  # hygiene is best-effort; the dialog still runs
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
    finally:
        stdin_guard.clear()
