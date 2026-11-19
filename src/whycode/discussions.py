"""Discussions: the conversations Decisions come out of (PR review threads, issue threads, RFCs).

A Discussion is a list of segments, each one authored piece of text with its own locator, author and time.
The Discussion node's `text` in the graph is the segments joined, so the answer verifier checks quotes against
exactly the text the extractor saw. A Decision's quote must sit inside a single segment, which also tells us
who said it and when.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Literal

from whycode import ids
from whycode.history.records import Issue, PullRequest, Rfc
from whycode.history.rfc import parse_header

DiscussionKind = Literal["pull_request", "issue", "rfc"]
SEPARATOR = "\n\n"


@dataclass(frozen=True, slots=True)
class Segment:
    locator: str  # "title", "body", "post[2]", "section[3]"
    text: str
    author: str | None
    at: dt.date


@dataclass(frozen=True, slots=True)
class Discussion:
    id: str
    kind: DiscussionKind
    title: str
    url: str
    date: dt.date  # when its Decisions took effect: merge date (PR), file date (RFC), opening date (issue)
    authors: tuple[str, ...]
    segments: tuple[Segment, ...]

    @property
    def text(self) -> str:
        return SEPARATOR.join(s.text for s in self.segments)

    def decision_date(self, segment: Segment) -> dt.date:
        """A PR's or RFC's Decisions date from the record; an issue's from the post that states them."""
        return segment.at if self.kind == "issue" else self.date


def from_pull_request(repo: str, pr: PullRequest) -> Discussion:
    assert pr.merged_at is not None, "only merged pull requests are Discussions"
    segments = [
        Segment("title", pr.title, pr.author, pr.created_at.date()),
        Segment("body", pr.body, pr.author, pr.created_at.date()),
        *(Segment(f"post[{i}]", p.body, p.author, p.at.date()) for i, p in enumerate(pr.posts)),
    ]
    return Discussion(ids.number_id(repo, pr.number), "pull_request", pr.title, pr.url, pr.merged_at.date(),
                      (pr.author,), tuple(s for s in segments if s.text.strip()))


def from_issue(repo: str, issue: Issue) -> Discussion:
    segments = [
        Segment("title", issue.title, issue.author, issue.created_at.date()),
        Segment("body", issue.body, issue.author, issue.created_at.date()),
        *(Segment(f"post[{i}]", p.body, p.author, p.at.date()) for i, p in enumerate(issue.posts)),
    ]
    return Discussion(ids.number_id(repo, issue.number), "issue", issue.title, issue.url,
                      issue.created_at.date(), (issue.author,), tuple(s for s in segments if s.text.strip()))


_HEADING = re.compile(r"^#{1,6} ", re.MULTILINE)


def from_rfc(rfc: Rfc) -> Discussion:
    """An RFC's segments are its sections (split at markdown headings), so a soft link only sees the
    section a Decision's quote came from."""
    starts = [0, *(m.start() for m in _HEADING.finditer(rfc.text) if m.start() > 0)]
    bounds = zip(starts, [*starts[1:], len(rfc.text)])
    sections = [rfc.text[a:b].strip() for a, b in bounds]
    segments = tuple(
        Segment(f"section[{i}]", text, None, rfc.date) for i, text in enumerate(sections) if text
    )
    feature = parse_header(rfc.text).get("Feature Name")
    title = f"RFC: {feature.value}" if feature and feature.value else f"RFC {rfc.stem}"
    return Discussion(ids.rfc_id(rfc.stem), "rfc", title, rfc.url, rfc.date, rfc.authors, segments)
