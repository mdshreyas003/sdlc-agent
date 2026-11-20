"""The one word-for-word quote rule.

Shared by the Decision extractor, the answer verifier, the scoreboard's gold check and its citation metric
(`whycode.eval.corpus` re-exports it), so every part of the system agrees on what "verbatim" means:
whitespace runs (spaces, tabs, newlines) collapse to one space, and then the quote must be a plain substring of
the source, case included. Nothing else is forgiven: no case folding, no typography folding, no ellipsis or
elision, no markdown stripping, no fuzzy matching. An empty quote never matches.
"""

from __future__ import annotations

MIN_DECISION_QUOTE_WORDS = 5
"""A Decision must rest on a quote of at least this many words, so a word like "LGTM" cannot anchor one."""


def squash(text: str) -> str:
    """Collapse every whitespace run to one space."""
    return " ".join(text.split())


def is_verbatim(quote: str, text: str) -> bool:
    """True when `quote` is non-empty and appears word for word in `text`."""
    needle = squash(quote)
    return bool(needle) and needle in squash(text)


def word_count(quote: str) -> int:
    return len(quote.split())
