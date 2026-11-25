"""Slash completer: builtin heads plus local and marketplace skills (SKILL-01, SKILL-03)."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from prompt_toolkit.completion import (
    Completer,
    Completion,
    DynamicCompleter,
    FuzzyCompleter,
)
from prompt_toolkit.document import Document

WordList = list[tuple[str, str]]
"""``(bare, display)`` pairs: bare names match, display text completes."""


class SlashCompleter(Completer):
    """Complete ``/<name>`` slashes from a refreshable word callable.

    Fires only while the line is a bare slash head (starts with ``/``,
    no space yet). A ``/<namespace>:`` prefix dynamically filters live
    entries whose display begins with ``/<namespace>:`` so ``/local:``
    matches local skills and ``/<marketplace>:`` matches that catalog's
    skills without hardcoding namespaces. Unknown namespaces offer nothing.
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
        prefix: str | None = None
        if ":" in query:
            head, _, tail = query.partition(":")
            prefix = f"/{head}:"
            query = tail
        for bare, display in self._get_words():
            if prefix is not None and not display.startswith(prefix):
                continue
            if bare.startswith(query):
                yield Completion(display, start_position=-len(text))


def build_completer(get_words: Callable[[], WordList]) -> DynamicCompleter:
    """Fuzzy slash completer rebuilt from the word callable per keystroke."""
    return DynamicCompleter(lambda: FuzzyCompleter(SlashCompleter(get_words)))
