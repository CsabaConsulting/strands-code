"""Slash completer: builtin heads plus local skills (SKILL-01, D-02/D-03)."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from prompt_toolkit.completion import Completer, Completion, DynamicCompleter, FuzzyCompleter
from prompt_toolkit.document import Document

WordList = list[tuple[str, str]]
"""``(bare, display)`` pairs: bare names match, display text completes."""


class SlashCompleter(Completer):
    """Complete ``/<name>`` slashes from a refreshable word callable.

    Fires only while the line is a bare slash head (starts with ``/``,
    no space yet). Matching is a bare-name prefix filter; the outer
    :class:`FuzzyCompleter` adds fuzzy narrowing. Skill displays use
    the full ``local:<name>`` form (D-02); shadowed skills never reach
    the word list (built by the caller from unshadowed entries).

    Args:
        get_words: Zero-arg callable returning fresh ``(bare, display)``
            pairs on every invocation (add/remove needs no restart).
    """

    def __init__(self, get_words: Callable[[], WordList]) -> None:
        self._get_words = get_words

    def get_completions(
        self, document: Document, complete_event
    ) -> Iterable[Completion]:
        text = document.text_before_cursor
        if not text.startswith("/") or " " in text:
            return
        query = text[1:]
        for bare, display in self._get_words():
            if bare.startswith(query):
                yield Completion(display, start_position=-len(text))


def build_completer(get_words: Callable[[], WordList]) -> DynamicCompleter:
    """Fuzzy slash completer rebuilt from the word callable per keystroke.

    Args:
        get_words: Zero-arg callable returning ``(bare, display)`` pairs.

    Returns:
        A :class:`DynamicCompleter` wrapping a fuzzy ``SlashCompleter``.
    """
    return DynamicCompleter(lambda: FuzzyCompleter(SlashCompleter(get_words)))
