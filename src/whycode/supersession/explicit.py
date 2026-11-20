"""Explicit Supersession, parsed with no model (`origin: stated`): reverts, RFC `Status:` headers, and
`supersedes #N` / `superseded by #N` written in a pull request's or issue's title or description."""

from __future__ import annotations

import re
from collections.abc import Iterable

from whycode import ids
from whycode.discussions import Discussion
from whycode.graph import Edge, Graph
from whycode.history.records import History
from whycode.history.rfc import parse_header
from whycode.supersession.index import DecisionIndex, supersession_edge

DEAD_RFC_STATUSES = frozenset({"superseded", "obsolete", "rejected"})

_NUMBER = re.compile(r"#(\d{1,7})\b|https?://github\.com/[\w.-]+/[\w.-]+/(?:pull|issues)/(\d+)")
SUPERSEDE_TEXT = re.compile(
    r"(?i)\b(?P<verb>supersedes|superseded\s+by)\b:?\s+"
    r"(?P<ref>#\d{1,7}\b|https?://github\.com/[\w.-]+/[\w.-]+/(?:pull|issues)/\d+)"
)
_STATEMENT_FIELDS = ("title", "body")


def explicit_supersessions(graph: Graph, history: History, discussions: Iterable[Discussion]) -> list[Edge]:
    index = DecisionIndex(graph)
    return [*_reverts(index, history), *_rfc_statuses(index, history), *_statements(index, discussions)]


def _record_text(history: History, record: str, field: str) -> str | None:
    """The exact text of one field of a Change, for quoting a revert statement by its locator."""
    for pr in history.pull_requests:
        if ids.pr_id(pr.number) == record:
            return {"title": pr.title, "body": pr.body}.get(field)
        for commit in pr.commits:
            if ids.commit_id(commit.sha) == record and field == "message":
                return commit.message
    return None


def _quote_at(history: History, record: str, locator: str) -> str | None:
    field, _, span = locator.partition("#")
    text = _record_text(history, record, field)
    if text is None:
        return None
    if not span:
        return text
    start, end = (int(x) for x in span.split("-"))
    return text[start:end]


def _reverts(index: DecisionIndex, history: History) -> list[Edge]:
    statements: dict[tuple[str, str], tuple[str, str, str]] = {}  # (R, P) -> (record, locator, quote)
    for e in sorted(index.graph.edges("REVERTS"), key=lambda e: (not index.is_pr(e.source), e.props["locator"])):
        reverting = e.source if index.is_pr(e.source) else index.pr_of_commit.get(e.source)
        reverted = e.target if index.is_pr(e.target) else index.pr_of_commit.get(e.target)
        if not (reverting and reverted) or reverting == reverted or not index.real(reverted):
            continue
        quote = _quote_at(history, e.source, e.props["locator"])
        if quote and (reverting, reverted) not in statements:
            statements[(reverting, reverted)] = (e.source, e.props["locator"], quote)
    out = []
    for (reverting, reverted), (record, locator, quote) in sorted(statements.items()):
        for earlier in index.of_record.get(reverted, ()):
            for later in index.superseders(earlier, reverting):
                out.append(supersession_edge(later, earlier, quote=quote, record=record, locator=locator,
                                 at=index.date(reverting), via="revert"))
    return out


def _rfc_statuses(index: DecisionIndex, history: History) -> list[Edge]:
    rfc_pr: dict[str, str] = {}  # header RFC PR target -> RFC id
    for e in index.graph.edges("REFERENCES"):
        if e.props["locator"].startswith("header:RFC PR#"):
            rfc_pr.setdefault(e.target, e.source)
    out = []
    for rfc in history.rfcs:
        rid = ids.rfc_id(rfc.stem)
        node = index.graph.nodes.get(rid)
        if node is None or node.props.get("status") not in DEAD_RFC_STATUSES:
            continue
        header = parse_header(rfc.text)["Status"]
        quote, locator = header.value, f"header:Status#{header.start}-{header.end}"
        later = None
        if node.props["status"] == "superseded":
            for e in index.graph.edges("REFERENCES"):
                if e.source == rid and e.props["locator"].startswith("header:Status#"):
                    candidate = rfc_pr.get(e.target) or e.target
                    if candidate != rid and index.real(candidate):
                        later = candidate
                        break
        at = index.date(later) if later else node.props["date"]
        for earlier in index.of_record.get(rid, ()):
            # With no ingested successor, the RFC itself is what declares its Decisions dead.
            for superseder in index.superseders(earlier, later) if later else [rid]:
                out.append(supersession_edge(superseder, earlier, quote=quote, record=rid, locator=locator, at=at,
                                 via="rfc-status"))
    return out


def _resolve(index: DecisionIndex, ref: str) -> str | None:
    """An ingested record named by `#N` or a GitHub URL: a pull request, an issue, or the RFC whose RFC PR is N."""
    m = _NUMBER.search(ref)
    number = m.group(1) or m.group(2)
    for candidate in (ids.pr_id(number), ids.issue_id(number)):
        if index.real(candidate):
            return candidate
    for e in index.graph.edges("REFERENCES"):
        if e.props["locator"].startswith("header:RFC PR#") and e.target in (ids.pr_id(number), ids.issue_id(number)):
            return e.source
    return None


def _statements(index: DecisionIndex, discussions: Iterable[Discussion]) -> list[Edge]:
    out = []
    for d in discussions:
        if d.kind == "rfc":
            continue  # an RFC states Supersession in its Status header
        for segment in d.segments:
            if segment.locator not in _STATEMENT_FIELDS:
                continue
            for m in SUPERSEDE_TEXT.finditer(segment.text):
                other = _resolve(index, m.group("ref"))
                if other is None or other == d.id:
                    continue
                later, earlier_record = (d.id, other) if m.group("verb").lower() == "supersedes" else (other, d.id)
                at = index.date(later)
                for earlier in index.of_record.get(earlier_record, ()):
                    if index.decisions[earlier].props["date"] > at:
                        continue
                    for superseder in index.superseders(earlier, later):
                        out.append(supersession_edge(superseder, earlier, quote=m.group(0), record=d.id,
                                         locator=f"{segment.locator}#{m.start()}-{m.end()}", at=at,
                                         via="supersedes-text"))
    return out
