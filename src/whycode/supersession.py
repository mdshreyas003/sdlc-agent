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

**Inferred** Supersession (`origin: derived`): every pair of Decisions that govern the same Code Entity (not a
package), where B took effect later than A and comes from another Discussion, is a candidate. The judge (Opus 5.5
behind the `SupersessionJudge` seam) labels it supersedes / refines / unrelated with a quote; the model proposes,
code decides: a label becomes an edge only when its quote has at least `MIN_DECISION_QUOTE_WORDS` words and is
verbatim in B's Discussion. Pairs that need no judgment are skipped: those already linked explicitly, and those
whose A was already explicitly superseded when B took effect.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from whycode import ids
from whycode.discussions import Discussion
from whycode.graph import DERIVED, STATED, Edge, Graph
from whycode.history.records import History
from whycode.history.rfc import parse_header
from whycode.llm import LlmClient, LlmError
from whycode.quotes import MIN_DECISION_QUOTE_WORDS, is_verbatim, word_count

log = logging.getLogger(__name__)

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


# --- inferred Supersession -------------------------------------------------------------------------------------

Label = Literal["supersedes", "refines", "unrelated"]
EDGE_TYPE = {"supersedes": "SUPERSEDES", "refines": "REFINES"}


class Judgment(BaseModel):
    label: Label = Field(description="supersedes: B overrides A, so A no longer holds. refines: B narrows or extends "
                                     "A, so A still partly holds. unrelated: anything else, including B restating or "
                                     "implementing A.")
    quote: str = Field(description="For supersedes or refines: a passage copied character for character from B's "
                                   "discussion that shows how B changes A. Empty for unrelated.")
    reason: str = Field(description="One sentence explaining the label.")


@dataclass(frozen=True, slots=True)
class DecisionSummary:
    id: str
    discussion_id: str
    discussion_title: str
    choice: str
    rationale: str
    quote: str
    date: str


@dataclass(frozen=True, slots=True)
class CandidatePair:
    earlier: DecisionSummary
    later: DecisionSummary
    shared: tuple[str, ...]  # Code Entity ids both Decisions govern
    later_text: str  # B's Discussion, where the justification quote must come from


class SupersessionJudge(Protocol):
    def judge(self, pair: CandidatePair) -> Judgment: ...


def summary(graph: Graph, decision_id: str) -> DecisionSummary:
    d = graph.nodes[decision_id].props
    return DecisionSummary(id=decision_id, discussion_id=d["discussion_id"],
                           discussion_title=graph.nodes[d["discussion_id"]].props.get("title") or "",
                           choice=d["choice"], rationale=d["rationale"], quote=d["quote"], date=d["date"])


def candidate_pairs(graph: Graph) -> list[tuple[str, str, tuple[str, ...]]]:
    """(earlier, later, shared entities) for every pair of Decisions that govern the same Code Entity, the later
    one from another Discussion and strictly later, oldest later Decision first."""
    index = _Index(graph)
    governed_by: dict[str, set[str]] = defaultdict(set)
    for decision, entities in index.governs.items():
        for entity in entities:
            governed_by[entity].add(decision)
    shared: dict[tuple[str, str], set[str]] = defaultdict(set)
    for entity, decisions in governed_by.items():
        for a in decisions:
            for b in decisions:
                pa, pb = index.decisions[a].props, index.decisions[b].props
                if pa["discussion_id"] != pb["discussion_id"] and pa["date"] < pb["date"]:
                    shared[(a, b)].add(entity)
    return [(a, b, tuple(sorted(es))) for (a, b), es in
            sorted(shared.items(), key=lambda kv: (index.decisions[kv[0][1]].props["date"],
                                                   index.decisions[kv[0][0]].props["date"], kv[0]))]


def inferred_supersessions(graph: Graph, discussions: Iterable[Discussion], explicit: Iterable[Edge],
                           judge: SupersessionJudge) -> list[Edge]:
    by_id = {d.id: d for d in discussions}
    linked, dead_since = set(), {}
    for e in explicit:
        linked.add((e.target, e.source))
        if e.type == "SUPERSEDES":
            dead_since[e.target] = min(e.props["observed_at"], dead_since.get(e.target, e.props["observed_at"]))
    name = getattr(judge, "name", type(judge).__name__)
    out = []
    for earlier, later, shared in candidate_pairs(graph):
        b = summary(graph, later)
        if (earlier, later) in linked or dead_since.get(earlier, "9999") <= b.date:
            continue
        discussion = by_id[b.discussion_id]
        judgment = judge.judge(CandidatePair(summary(graph, earlier), b, shared, discussion.text))
        if judgment.label not in EDGE_TYPE:
            continue
        quote = judgment.quote.strip()
        segment = next((s for s in discussion.segments if is_verbatim(quote, s.text)), None)
        if word_count(quote) < MIN_DECISION_QUOTE_WORDS or segment is None:
            log.info("dropped %s judgment %s -> %s: quote not verbatim in %s", judgment.label, earlier, later,
                     b.discussion_id)
            continue
        out.append(_edge(later, earlier, type_=EDGE_TYPE[judgment.label], basis=INFERRED, quote=quote,
                         record=b.discussion_id, locator=segment.locator, at=b.date, via="judge", judge=name,
                         reason=judgment.reason))
    return out


def supersessions(graph: Graph, history: History, discussions: Iterable[Discussion],
                  judge: SupersessionJudge | None) -> list[Edge]:
    """Explicit Supersession always; inferred Supersession when a judge is given."""
    discussions = list(discussions)
    explicit = explicit_supersessions(graph, history, discussions)
    return explicit + (inferred_supersessions(graph, discussions, explicit, judge) if judge else [])


class RecordedSupersessionJudge:
    """Replays recorded judgments keyed by "<earlier decision id> -> <later decision id>" (the fixture's stand-in
    for the model). Raises KeyError for a pair with no recording, so an unexpected question fails loudly."""

    name = "recorded"

    def __init__(self, path: Path):
        data = json.loads(Path(path).read_text())
        self._recorded = {k: Judgment.model_validate({f: v[f] for f in ("label", "quote", "reason")})
                          for k, v in data.items() if not k.startswith("_")}

    def judge(self, pair: CandidatePair) -> Judgment:
        return self._recorded[f"{pair.earlier.id} -> {pair.later.id}"]


JUDGE_SYSTEM = """You judge whether a later Decision changes an earlier one in the CockroachDB SQL schema \
changer. Both Decisions govern the same code. Label the pair:

- supersedes: B overrides A. After B, A no longer holds (B reverses it, replaces it, or contradicts it).
- refines: B narrows or extends A. A still holds in part (B adds an exception, changes a default or a limit, or \
covers a case A left open).
- unrelated: B does not change A. This includes B restating A, implementing A as proposed, or deciding \
something else about the same code.

When the evidence is thin, answer unrelated: a wrong supersedes label hides a Decision that is still live.

For supersedes or refines, give `quote`: a passage copied character for character from B's discussion (at \
least five words, from one post or section) that shows how B changes A. Do not paraphrase, fix typos or \
shorten with "...". A label whose quote is not found verbatim in B's discussion is discarded."""


def render_pair(pair: CandidatePair) -> str:
    def decision(tag: str, d: DecisionSummary) -> str:
        return (f"{tag} ({d.date}, from {d.discussion_id}: {d.discussion_title})\n"
                f"Choice: {d.choice}\nRationale: {d.rationale}\nQuote: {d.quote}")

    return "\n\n".join([
        decision("Earlier Decision A", pair.earlier), decision("Later Decision B", pair.later),
        "Code both govern: " + ", ".join(pair.shared),
        f"B's discussion ({pair.later.discussion_id}):\n{pair.later_text}",
    ])


class AnthropicSupersessionJudge:
    """Production adapter: Opus 5.5 with structured output, responses cached on disk by the LlmClient."""

    def __init__(self, llm: LlmClient, model: str):
        self.llm = llm
        self.model = model
        self.name = model

    def judge(self, pair: CandidatePair) -> Judgment:
        try:
            return self.llm.parse(model=self.model, system=JUDGE_SYSTEM, user=render_pair(pair), output=Judgment,
                                  effort="medium")
        except LlmError as exc:
            log.warning("supersession judgment failed for %s -> %s: %s", pair.earlier.id, pair.later.id, exc)
            return Judgment(label="unrelated", quote="", reason=f"judge failed: {exc}")
