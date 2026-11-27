"""Slash and inline @file fuzzy completers (SKILL-01, SKILL-03, TOOL-05)."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable

from prompt_toolkit.completion import (
    Completer,
    Completion,
    DynamicCompleter,
    FuzzyCompleter,
    merge_completers,
)
from prompt_toolkit.document import Document

WordList = list[tuple[str, str]]
"""``(bare, display)`` pairs: bare names match, display text completes."""

_AT_QUERY_RE = re.compile(r'(?:^|[\s(\["\'])@([^\s"\']*)$')


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


class AtFileCompleter(Completer):
    """Complete inline ``@<path>`` tokens from a refreshable workspace file callable."""

    def __init__(self, get_files: Callable[[], list[str]]) -> None:
        self._get_files = get_files

    def get_completions(
        self, document: Document, complete_event
    ) -> Iterable[Completion]:
        before = document.text_before_cursor
        if before.startswith("/") and " " not in before:
            return
        match = _AT_QUERY_RE.search(before)
        if match is None:
            return
        query = match.group(1)
        lowered_q = query.lower()
        start_pos = -(len(query) + 1)
        for path in self._get_files():
            if lowered_q and lowered_q not in path.lower():
                continue
            display = f'@"{path}"' if any(c.isspace() for c in path) else f"@{path}"
            yield Completion(display, start_position=start_pos)


def build_completer(
    get_words: Callable[[], WordList],
    get_files: Callable[[], list[str]] | None = None,
) -> DynamicCompleter:
    """Fuzzy completer rebuilt from live slash words and optional @file candidates."""
    if get_files is None:
        return DynamicCompleter(lambda: FuzzyCompleter(SlashCompleter(get_words)))
    return DynamicCompleter(
        lambda: FuzzyCompleter(
            merge_completers([SlashCompleter(get_words), AtFileCompleter(get_files)])
        )
    )
