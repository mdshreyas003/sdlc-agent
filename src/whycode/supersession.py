"""Supersession detector: which later Decisions supersede or refine earlier ones.

Edges go from the later node to the earlier Decision: `SUPERSEDES` (the earlier one is dead) or `REFINES` (it
is narrowed or extended, so partly live). Every edge carries `basis` (explicit | inferred), the verbatim `quote`
that states or justifies it, `source` (the record whose text holds that quote), a `locator` in that record, and
`observed_at` (when the later node took effect).

**Explicit** Supersession is parsed with no model (`origin: stated`):
- a revert: Change R reverts Change P (`Revert "<title>"`, `This reverts commit <sha>`; see `whycode.linker`),
  so every Decision of P is superseded;
- an RFC `Status:` of superseded, obsolete or rejected: every Decision of that RFC is superseded. For
  `superseded by #N` the later record is the RFC whose `RFC PR` is N (or the record N, when ingested); otherwise
  (obsolete, rejected, or a successor that was not ingested) the RFC itself declares its Decisions dead;
- `supersedes #N` / `superseded by #N` written in a pull request's or issue's title or description.

Edges start at Decisions whenever they can (the schema's Decision -> supersedes -> Decision): the superseding node
of an explicit case is each Decision of the later record that governs a Code Entity the earlier Decision governs.
A record starts the edge only when the later record yields no such Decision (a revert that records no Decision of
its own, a successor whose Decisions are about other code), or when an RFC declares its own Decisions dead.

**Inferred** Supersession (`origin: derived`): pairs of Decisions that govern the same Code Entity, where B took
effect later than A and comes from another Discussion, are candidates (`candidate_pairs`: the most specific code
both govern, so two Decisions on different functions of one file are not paired; at most `MAX_LATER` later
Decisions per Decision). The judge (Opus 5.5
behind the `SupersessionJudge` seam) labels it supersedes / refines / unrelated with a quote; the model proposes,
code decides: a label becomes an edge only when its quote has at least `MIN_DECISION_QUOTE_WORDS` words and is
verbatim in B's Discussion. Pairs that need no judgment are skipped: those already linked explicitly, and those
whose A was already explicitly superseded when B took effect.

`judge_report` scores the judge against the explicit cases (`whycode supersession-report`).

Known limits: a revert of a revert does not bring the reverted Decisions back; an RFC's status comes from its
text as of the build, so the status edge is dated by the superseding RFC (or, failing that, the RFC itself).
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
            # With no ingested successor, the RFC itself is what declares its Decisions dead.
            for superseder in index.superseders(earlier, later) if later else [rid]:
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
MAX_LATER = 5
"""Each Decision is judged against at most this many later Decisions (the nearest in time)."""


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


def candidate_pairs(graph: Graph, max_later: int | None = None) -> list[tuple[str, str, tuple[str, ...]]]:
    """(earlier, later, shared entities) for the pairs of Decisions to judge, oldest later Decision first.

    A pair shares a Code Entity among the most specific ones each Decision governs (a file counts only for a
    Decision that governs nothing inside it), the later one is from another Discussion and strictly later.
    Each earlier Decision is paired with its `max_later` nearest later Decisions (default `MAX_LATER`), which
    bounds the judge's cost at that many calls per Decision.
    """
    max_later = MAX_LATER if max_later is None else max_later
    index = _Index(graph)
    parent = {e.target: e.source for e in graph.edges("CONTAINS")
              if "CodeEntity" in graph.nodes[e.source].labels and "CodeEntity" in graph.nodes[e.target].labels}

    def ancestors(entity: str) -> set[str]:
        out = set()
        while (entity := parent.get(entity)) is not None and entity not in out:
            out.add(entity)
        return out

    governed_by: dict[str, set[str]] = defaultdict(set)
    for decision, entities in index.governs.items():
        inside = set().union(*(ancestors(e) for e in entities))
        for entity in entities - inside:
            governed_by[entity].add(decision)
    shared: dict[tuple[str, str], set[str]] = defaultdict(set)
    for entity, decisions in governed_by.items():
        for a in decisions:
            for b in decisions:
                pa, pb = index.decisions[a].props, index.decisions[b].props
                if pa["discussion_id"] != pb["discussion_id"] and pa["date"] < pb["date"]:
                    shared[(a, b)].add(entity)

    def when(decision: str) -> str:
        return index.decisions[decision].props["date"]

    nearest: dict[str, list[str]] = defaultdict(list)
    for a, b in sorted(shared, key=lambda pair: (when(pair[1]), pair[1])):
        nearest[a].append(b)
    keep = {(a, b) for a, laters in nearest.items() for b in laters[:max_later]}
    return [(a, b, tuple(sorted(shared[(a, b)]))) for a, b in
            sorted(keep, key=lambda pair: (when(pair[1]), when(pair[0]), pair))]


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


# --- the judge scored against explicit Supersession ------------------------------------------------------------

_STATEMENTS = (  # what makes a case explicit; masked out of B's discussion before the judge reads it
    re.compile(r'(?im)^revert ".*"$'),
    re.compile(r"(?i)\bthis reverts commit [0-9a-f]{7,40}\b"),
    re.compile(r"(?i)\breverts?\b:?\s+(?:pr\s+)?(?:[\w.-]+/[\w.-]+)?#\d{1,7}\b"),
    _SUPERSEDE_TEXT,
)
MASK = "[explicit statement removed]"


def mask_statements(text: str) -> str:
    for pattern in _STATEMENTS:
        text = pattern.sub(MASK, text)
    return text


@dataclass(frozen=True, slots=True)
class JudgedCase:
    earlier: DecisionSummary
    later: DecisionSummary
    explicit: bool  # gold: history states that B supersedes A
    label: str  # the judge's label; "unrelated" when its quote failed the verbatim check
    quote: str
    reason: str

    @property
    def predicted(self) -> bool:
        return self.label == "supersedes"


@dataclass(frozen=True)
class JudgeReport:
    judge: str
    cases: list[JudgedCase]
    unjudgeable: int  # explicitly superseded Decisions with no superseding Decision (a record or a status)

    def _count(self, explicit: bool, predicted: bool) -> int:
        return sum(c.explicit == explicit and c.predicted == predicted for c in self.cases)

    @property
    def true_positives(self) -> int:
        return self._count(True, True)

    @property
    def false_positives(self) -> int:
        return self._count(False, True)

    @property
    def false_negatives(self) -> int:
        return self._count(True, False)

    @property
    def precision(self) -> float | None:
        flagged = self.true_positives + self.false_positives
        return self.true_positives / flagged if flagged else None

    @property
    def recall(self) -> float | None:
        explicit = self.true_positives + self.false_negatives
        return self.true_positives / explicit if explicit else None

    def markdown(self) -> str:
        def pct(value: float | None, num: int, den: int) -> str:
            return f"{value:.0%} ({num} of {den})" if value is not None else "n/a (0 of 0)"

        def row(explicit: bool) -> str:
            cases = [c for c in self.cases if c.explicit == explicit]
            counts = [sum(c.label == label for c in cases) for label in ("supersedes", "refines", "unrelated")]
            name = "explicit Supersession" if explicit else "no explicit link"
            return f"| {name} (n={len(cases)}) | " + " | ".join(map(str, counts)) + " |"

        def listed(title: str, cases: list[JudgedCase]) -> list[str]:
            lines = [f"### {title} ({len(cases)})", ""]
            for c in cases:
                lines.append(f"- {c.earlier.discussion_id} -> {c.later.discussion_id}: judge said {c.label}. "
                             f"A: {c.earlier.choice} B: {c.later.choice}"
                             + (f' Quote: "{c.quote}". {c.reason}' if c.quote else ""))
            return [*lines, ""]

        tp, fp, fn = self.true_positives, self.false_positives, self.false_negatives
        return "\n".join([
            "# Supersession judge against explicit Supersession", "",
            (f"Judge `{self.judge}`. Gold: Supersession that history states (reverts, RFC status headers, "
             "\"supersedes #N\"). Each pair was judged with that statement masked out of B's discussion. Negatives "
             "are the other candidate pairs around the explicit cases (same Code Entity, B later): pairs into an "
             "explicitly superseded Decision, and pairs out of an explicit superseder."), "",
            "| pairs | judge: supersedes | judge: refines | judge: unrelated (or quote rejected) |",
            "|---|---|---|---|", row(True), row(False), "",
            f"Precision {pct(self.precision, tp, tp + fp)}, recall {pct(self.recall, tp, tp + fn)}.", "",
            ("Precision is a lower bound: a negative the judge calls supersedes may be a real Supersession history "
             "never stated; check the false positives below by hand. Refines counts as not supersedes."),
            (f"{self.unjudgeable} explicitly superseded Decisions have no superseding Decision (a revert or status "
             "with no Decision of its own) and are not judged pairwise."), "",
            *listed("False positives (judge: supersedes, no explicit link)",
                    [c for c in self.cases if not c.explicit and c.predicted]),
            *listed("False negatives (explicit, judge did not say supersedes)",
                    [c for c in self.cases if c.explicit and not c.predicted]),
        ]).rstrip() + "\n"


def judge_report(graph: Graph, judge: SupersessionJudge) -> JudgeReport:
    """Ask the judge about every explicit Decision -> Decision Supersession and the candidate pairs around it."""
    index = _Index(graph)
    explicit = [e for e in graph.edges("SUPERSEDES") if e.props.get("basis") == EXPLICIT]
    gold = {(e.target, e.source) for e in explicit if e.source in index.decisions}
    superseded, superseders = {a for a, _ in gold}, {b for _, b in gold}
    unjudgeable = len({e.target for e in explicit} - superseded)
    pairs = dict.fromkeys(sorted(gold, key=lambda p: (index.decisions[p[1]].props["date"], p)))
    for a, b, _ in candidate_pairs(graph):
        if a in superseded or b in superseders:
            pairs.setdefault((a, b))
    shared = {(a, b): s for a, b, s in candidate_pairs(graph)}
    cases = []
    for a, b in pairs:
        earlier, later = summary(graph, a), summary(graph, b)
        text = graph.nodes[later.discussion_id].props.get("text") or ""
        judgment = judge.judge(CandidatePair(earlier, later, shared.get((a, b), ()), mask_statements(text)))
        quote = judgment.quote.strip()
        kept = judgment.label == "unrelated" or (word_count(quote) >= MIN_DECISION_QUOTE_WORDS
                                                 and is_verbatim(quote, text))
        cases.append(JudgedCase(earlier, later, (a, b) in gold, judgment.label if kept else "unrelated", quote,
                                judgment.reason))
    return JudgeReport(getattr(judge, "name", type(judge).__name__), cases, unjudgeable)
