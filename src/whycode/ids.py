"""Stable canonical node ids, built only from native identifiers so re-runs and machines agree.

GitHub issues and pull requests share one number space, so both are keyed by repo + number and never by a
guessed kind: `github:cockroachdb/cockroach#98100`. Code Entity ids live in `whycode.codeindex.entity_id`.
"""

from __future__ import annotations

import hashlib

from whycode.quotes import normalize


def number_id(repo: str, number: int | str) -> str:
    return f"github:{repo}#{int(number)}"


def commit_id(repo: str, sha: str) -> str:
    return f"github:{repo}@{sha.lower()}"


def rfc_id(stem: str) -> str:
    return f"rfc:{stem}"


def person_id(login: str) -> str:
    return f"person:{login}"


def decision_id(discussion_id: str, quote: str) -> str:
    """Derived from the Discussion and the (normalised) quote, never from model-chosen text."""
    digest = hashlib.sha256(f"{discussion_id}\0{normalize(quote)}".encode()).hexdigest()
    return f"decision:{digest[:16]}"


def number_url(repo: str, number: int | str) -> str:
    """GitHub redirects /issues/N to /pull/N when N is a pull request."""
    return f"https://github.com/{repo}/issues/{int(number)}"
