"""Slash completer: builtin heads plus local skills (SKILL-01, D-02/D-03)."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from prompt_toolkit.completion import Completer, Completion, DynamicCompleter, FuzzyCompleter
from prompt_toolkit.document import Document

from strands_code_cli.skills import SKILLS_SOURCE

WordList = list[tuple[str, str]]
"""``(bare, display)`` pairs: bare names match, display text completes."""


class SlashCompleter(Completer):
    """Complete ``/<name>`` slashes from a refreshable word callable.

    Fires only while the line is a bare slash head (starts with ``/``,
    no space yet). Matching is a bare-name prefix filter; the outer
    :class:`FuzzyCompleter` adds fuzzy narrowing. Skill displays use
    the ``/local:<name>`` completion form (D-02) so the accepted line
    re-enters dispatch as a slash; shadowed skills never reach
    the word list (built by the caller from unshadowed entries).
    A ``/<source>:`` prefix narrows to that namespace: ``/local:``
    offers every local skill, ``/local:gr`` filters by the tail.
    Unknown namespaces offer nothing.

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
        namespaced = ":" in query
        if namespaced:
            head, _, tail = query.partition(":")
            if head != SKILLS_SOURCE:
                return
            query = tail
        for bare, display in self._get_words():
            if namespaced and not display.startswith(f"/{SKILLS_SOURCE}:"):
                continue
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
