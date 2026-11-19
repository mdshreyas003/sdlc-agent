"""Stable canonical node ids, built only from native identifiers so re-runs and machines agree.

The convention is shared with the scoreboard's corpus (eval/README.md, "Corpus format"):
`rfc:<file stem>`, `pr:<n>`, `issue:<n>`, `commit:<full sha>`; plus `person:<login>` and
`decision:<hash>`. Records of another repository (only ever stubs) carry it: `issue:<owner>/<repo>#<n>`.
Code Entity ids live in `whycode.codeindex.entity_id`.

GitHub issues and pull requests share one number space. The linker uses the ingested kind when the number
was ingested; otherwise the kind its context implies (`Fixes #N` -> issue, `PR #N` -> pr). Only stubs, which
are never cited, can carry a guessed kind.
"""

from __future__ import annotations

import hashlib
import re
from typing import Literal

from whycode.quotes import normalize

NumberKind = Literal["pr", "issue"]


def number_id(kind: NumberKind, number: int | str, repo: str | None = None) -> str:
    return f"{kind}:{repo}#{int(number)}" if repo else f"{kind}:{int(number)}"


def pr_id(number: int | str) -> str:
    return number_id("pr", number)


def issue_id(number: int | str) -> str:
    return number_id("issue", number)


def commit_id(sha: str) -> str:
    return f"commit:{sha.lower()}"


def rfc_id(stem: str) -> str:
    return f"rfc:{stem}"


def person_id(login: str) -> str:
    return f"person:{login}"


def decision_id(discussion_id: str, quote: str) -> str:
    """Derived from the Discussion and the (normalised) quote, never from model-chosen text."""
    digest = hashlib.sha256(f"{discussion_id}\0{normalize(quote)}".encode()).hexdigest()
    return f"decision:{digest[:16]}"


def url_for(node_id: str, repo: str) -> str | None:
    """The public URL of a GitHub-keyed id (stubs included), for `repo` unless the id names another."""
    if m := re.fullmatch(r"(pr|issue):(?:([\w.-]+/[\w.-]+)#)?(\d+)", node_id):
        return f"https://github.com/{m.group(2) or repo}/{'pull' if m.group(1) == 'pr' else 'issues'}/{m.group(3)}"
    if m := re.fullmatch(r"commit:([0-9a-f]{40})", node_id):
        return f"https://github.com/{repo}/commit/{m.group(1)}"
    if m := re.fullmatch(r"person:(.+)", node_id):
        return f"https://github.com/{m.group(1)}"
    return None
