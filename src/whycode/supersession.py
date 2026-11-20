"""Supersession detector: which later Decisions supersede or refine earlier ones.

Edges go from the later node to the earlier Decision: `SUPERSEDES` (the earlier one is dead) or `REFINES` (it
is narrowed or extended, so partly live). Every edge carries `basis` (explicit | inferred), the verbatim `quote`
that states or justifies it, `source` (the record whose text holds that quote), a `locator` in that record, and
`observed_at` (when the later node took effect).

**Explicit** Supersession is parsed with no model (`origin: stated`):
- a revert: Change R reverts Change P (`Revert "<title>"`, `This reverts commit <sha>`; see `whycode.linker`),
  so every Decision of P is superseded;
- an RFC `Status:` of superseded, obsolete or rejected: every Decision of that RFC is superseded. The RFC itself
  is always one superseding node (its own header says so); for `superseded by #N` the RFC whose `RFC PR` is N
  (or the record N, when ingested) is another;
- `supersedes #N` / `superseded by #N` written in a pull request's or issue's title or description.

The superseding node of an explicit case is each Decision of the later record that governs a Code Entity the
earlier Decision governs; when there is none, the later record itself.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable

from whycode import ids
from whycode.discussions import Discussion
from whycode.graph import DERIVED, STATED, Edge, Graph
from whycode.history.records import History
from whycode.history.rfc import parse_header

EXPLICIT = "explicit"
INFERRED = "inferred"
DEAD_RFC_STATUSES = frozenset({"superseded", "obsolete", "rejected"})

_NUMBER = re.compile(r"#(\d{1,7})\b|https?://github\.com/[\w.-]+/[\w.-]+/(?:pull|issues)/(\d+)")
_SUPERSEDE_TEXT = re.compile(
    r"(?i)\b(?P<verb>supersedes|superseded\s+by)\b:?\s+"
    r"(?P<ref>#\d{1,7}\b|https?://github\.com/[\w.-]+/[\w.-]+/(?:pull|issues)/\d+)"
)
_STATEMENT_FIELDS = ("title", "body")


class _Index:
    """What the detector needs to know about the Decisions and records already in the graph."""

    def __init__(self, graph: Graph):
        self.graph = graph
        self.decisions = {d.id: d for d in graph.labelled("Decision")}
        self.of_record: dict[str, list[str]] = defaultdict(list)
        for e in graph.edges("YIELDS"):
            self.of_record[e.source].append(e.target)
        self.governs: dict[str, set[str]] = defaultdict(set)
        for e in graph.edges("GOVERNS"):
            if not e.target.startswith("package:"):
                self.governs[e.source].add(e.target)
        self.pr_of_commit = {e.target: e.source for e in graph.edges("CONTAINS")
                             if e.target.startswith("commit:") and e.source.startswith("pr:")}

    def real(self, node_id: str) -> bool:
        node = self.graph.nodes.get(node_id)
        return node is not None and not node.is_stub

    def date(self, node_id: str) -> str:
        return self.graph.nodes[node_id].props["date"]

    def superseders(self, earlier: str, later_record: str) -> list[str]:
        """The later record's Decisions that govern code `earlier` governs; else the record itself."""
        shared = [d for d in sorted(self.of_record.get(later_record, ()))
                  if self.governs[d] & self.governs[earlier]]
        return shared or [later_record]


def _edge(source: str, target: str, *, quote: str, record: str, locator: str, at: str, via: str,
          type_: str = "SUPERSEDES", basis: str = EXPLICIT, **props) -> Edge:
    return Edge(source, type_, target, {
        "origin": STATED if basis == EXPLICIT else DERIVED, "basis": basis, "quote": quote, "source": record,
        "locator": locator, "observed_at": at, "via": via, **props,
    })


def explicit_supersessions(graph: Graph, history: History, discussions: Iterable[Discussion]) -> list[Edge]:
    index = _Index(graph)
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


def _reverts(index: _Index, history: History) -> list[Edge]:
    statements: dict[tuple[str, str], tuple[str, str, str]] = {}  # (R, P) -> (record, locator, quote)
    for e in sorted(index.graph.edges("REVERTS"), key=lambda e: (not e.source.startswith("pr:"), e.props["locator"])):
        reverting = e.source if e.source.startswith("pr:") else index.pr_of_commit.get(e.source)
        reverted = e.target if e.target.startswith("pr:") else index.pr_of_commit.get(e.target)
        if not (reverting and reverted) or reverting == reverted or not index.real(reverted):
            continue
        quote = _quote_at(history, e.source, e.props["locator"])
        if quote and (reverting, reverted) not in statements:
            statements[(reverting, reverted)] = (e.source, e.props["locator"], quote)
    out = []
    for (reverting, reverted), (record, locator, quote) in sorted(statements.items()):
        for earlier in index.of_record.get(reverted, ()):
            for later in index.superseders(earlier, reverting):
                out.append(_edge(later, earlier, quote=quote, record=record, locator=locator,
                                 at=index.date(reverting), via="revert"))
    return out


def _rfc_statuses(index: _Index, history: History) -> list[Edge]:
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
            out.append(_edge(rid, earlier, quote=quote, record=rid, locator=locator, at=at, via="rfc-status"))
            if later:
                for superseder in index.superseders(earlier, later):
                    out.append(_edge(superseder, earlier, quote=quote, record=rid, locator=locator, at=at,
                                     via="rfc-status"))
    return out


def _resolve(index: _Index, ref: str) -> str | None:
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


def _statements(index: _Index, discussions: Iterable[Discussion]) -> list[Edge]:
    out = []
    for d in discussions:
        if d.kind == "rfc":
            continue  # an RFC states Supersession in its Status header
        for segment in d.segments:
            if segment.locator not in _STATEMENT_FIELDS:
                continue
            for m in _SUPERSEDE_TEXT.finditer(segment.text):
                other = _resolve(index, m.group("ref"))
                if other is None or other == d.id:
                    continue
                later, earlier_record = (d.id, other) if m.group("verb").lower() == "supersedes" else (other, d.id)
                at = index.date(later)
                for earlier in index.of_record.get(earlier_record, ()):
                    if index.decisions[earlier].props["date"] > at:
                        continue
                    for superseder in index.superseders(earlier, later):
                        out.append(_edge(superseder, earlier, quote=m.group(0), record=d.id,
                                         locator=f"{segment.locator}#{m.start()}-{m.end()}", at=at,
                                         via="supersedes-text"))
    return out
