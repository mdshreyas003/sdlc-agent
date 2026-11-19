"""Stable canonical node ids, built only from native identifiers so re-runs and machines agree.

GitHub issues and pull requests share one number space, so both are keyed by repo + number and never by a
guessed kind: `github:cockroachdb/cockroach#98100`. Code Entity ids live in `whycode.codeindex.entity_id`.
"""

from __future__ import annotations

import hashlib
import re

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


def url_for(node_id: str) -> str | None:
    """The public URL of a GitHub-keyed id (also for stubs); GitHub redirects /issues/N to /pull/N."""
    if m := re.fullmatch(r"github:([\w.-]+/[\w.-]+)#(\d+)", node_id):
        return f"https://github.com/{m.group(1)}/issues/{m.group(2)}"
    if m := re.fullmatch(r"github:([\w.-]+/[\w.-]+)@([0-9a-f]{40})", node_id):
        return f"https://github.com/{m.group(1)}/commit/{m.group(2)}"
    if m := re.fullmatch(r"person:(.+)", node_id):
        return f"https://github.com/{m.group(1)}"
    return None
