"""The one word-for-word quote rule.

Used by the Decision extractor, the answer verifier, and (by design) the gold-quote check and the eval
citation metric, so every part of the system agrees on what "verbatim" means:

- whitespace runs (spaces, tabs, newlines) collapse to one space, ends are trimmed;
- case is folded;
- curly quotes and apostrophes fold to straight ones, on both sides;
- then the quote must be a plain substring of the source.

Nothing else is forgiven: no ellipsis or elision, no markdown stripping, no fuzzy matching.
"""

from __future__ import annotations

_FOLD = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})

MIN_DECISION_QUOTE_WORDS = 5
"""A Decision must rest on a quote of at least this many words, so a word like "LGTM" cannot anchor one."""


def normalize(text: str) -> str:
    return " ".join(text.translate(_FOLD).split()).casefold()


def is_verbatim(quote: str, source: str) -> bool:
    """True when `quote` is non-empty and appears word for word in `source`."""
    needle = normalize(quote)
    return bool(needle) and needle in normalize(source)


def word_count(quote: str) -> int:
    return len(quote.split())
