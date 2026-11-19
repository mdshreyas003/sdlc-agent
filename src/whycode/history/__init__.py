"""History source: the scoped slice of project history, cut off at a configurable date.

`HistorySource` is the seam: the fixture source replays recorded payloads; ticket 02's GitHub source fetches
and caches real ones. `load_history` applies the cutoff rules to whatever a source yields, so a source that
over-fetches still cannot leak post-cutoff history into the graph.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Iterable
from typing import Protocol

from whycode.history.records import Commit, FileChange, History, Issue, Post, PullRequest, Rfc

__all__ = [
    "Commit", "FileChange", "History", "HistorySource", "Issue", "Post", "PullRequest", "Rfc", "load_history",
]


class HistorySource(Protocol):
    repo: str  # owner/name

    def rfcs(self) -> Iterable[Rfc]: ...

    def pull_requests(self) -> Iterable[PullRequest]: ...

    def issues(self) -> Iterable[Issue]: ...


def load_history(source: HistorySource, cutoff: dt.date) -> History:
    """Everything the source knows, as it stood at the end of the cutoff day (UTC).

    - a PR counts only if it was merged on or before the cutoff (by `merged_at`, never by commit date);
    - an issue counts if it was opened on or before the cutoff; a later close is undone;
    - an RFC counts if its file date is on or before the cutoff;
    - posts (reviews, comments) written after the cutoff are dropped from every record.
    """
    end = dt.datetime.combine(cutoff + dt.timedelta(days=1), dt.time(), tzinfo=dt.UTC)

    def before(at: dt.datetime | None) -> bool:
        return at is not None and at < end

    def posts(items: tuple[Post, ...]) -> tuple[Post, ...]:
        return tuple(p for p in items if before(p.at))

    pulls = tuple(
        dataclasses.replace(pr, posts=posts(pr.posts))
        for pr in sorted(source.pull_requests(), key=lambda pr: pr.number)
        if before(pr.merged_at)
    )
    issues = tuple(
        dataclasses.replace(
            issue, posts=posts(issue.posts), closed_at=issue.closed_at if before(issue.closed_at) else None
        )
        for issue in sorted(source.issues(), key=lambda issue: issue.number)
        if before(issue.created_at)
    )
    rfcs = tuple(rfc for rfc in sorted(source.rfcs(), key=lambda rfc: rfc.path) if rfc.date <= cutoff)
    return History(repo=source.repo, cutoff=cutoff, rfcs=rfcs, pull_requests=pulls, issues=issues)
