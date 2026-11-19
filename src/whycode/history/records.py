"""History records: what every history source yields, whatever system it reads from.

A source (fixture replay now, cached GitHub in ticket 02) maps its payloads onto these records; the rest of
the build only ever sees records. Datetimes are timezone-aware UTC.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal

PostKind = Literal["title", "description", "review", "review_comment", "comment"]


@dataclass(frozen=True, slots=True)
class Post:
    """One authored piece of text inside a Discussion (a PR or issue description, a review, a comment)."""

    kind: PostKind
    author: str
    at: dt.datetime
    body: str
    review_state: str | None = None  # APPROVED / CHANGES_REQUESTED / COMMENTED / DISMISSED, reviews only
    path: str | None = None  # file a review comment is attached to


@dataclass(frozen=True, slots=True)
class FileChange:
    path: str
    status: str  # added / removed / modified / renamed
    patch: str | None = None  # unified diff hunks; None when GitHub omits it (large or binary files)
    previous_path: str | None = None


@dataclass(frozen=True, slots=True)
class Commit:
    sha: str  # full 40-hex SHA
    message: str
    author: str | None
    at: dt.datetime | None


@dataclass(frozen=True, slots=True)
class PullRequest:
    number: int
    title: str
    body: str
    author: str
    url: str
    created_at: dt.datetime
    merged_at: dt.datetime | None
    base_ref: str
    labels: tuple[str, ...] = ()
    files: tuple[FileChange, ...] = ()
    commits: tuple[Commit, ...] = ()
    posts: tuple[Post, ...] = ()  # reviews, review comments and conversation comments; bots already dropped


@dataclass(frozen=True, slots=True)
class Issue:
    number: int
    title: str
    body: str
    author: str
    url: str
    created_at: dt.datetime
    closed_at: dt.datetime | None
    labels: tuple[str, ...] = ()
    posts: tuple[Post, ...] = ()  # conversation comments; bots already dropped


@dataclass(frozen=True, slots=True)
class Rfc:
    path: str  # repository path, e.g. docs/RFCS/20151014_online_schema_change.md
    text: str  # the whole file as of the cutoff commit
    date: dt.date  # from the file name (YYYYMMDD_name.md)
    authors: tuple[str, ...]  # GitHub logins
    url: str

    @property
    def stem(self) -> str:
        return self.path.rsplit("/", 1)[-1].removesuffix(".md")


@dataclass(frozen=True, slots=True)
class History:
    """One scoped slice of a repository's history, as of the cutoff (see `load_history`)."""

    repo: str  # owner/name
    cutoff: dt.date
    rfcs: tuple[Rfc, ...]
    pull_requests: tuple[PullRequest, ...]
    issues: tuple[Issue, ...]
