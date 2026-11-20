"""Inferred Supersession (`origin: derived`): the candidate pairs of Decisions, what the judge was asked about them,
and the edges its labels become."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from whycode.discussions import Discussion
from whycode.graph import Edge, Graph
from whycode.supersession.index import INFERRED, DecisionIndex, supersession_edge
from whycode.supersession.judge import EDGE_TYPE, CandidatePair, SupersessionJudge, judge_name, quote_holds, summary

log = logging.getLogger(__name__)

MAX_LATER = 5
"""The judge's default cost bound: each Decision is judged against at most this many later Decisions (the nearest
in time). `whycode build --judge-max-later N` changes it (0: no bound); the build reports what it left out."""


@dataclass(frozen=True, slots=True)
class CandidatePairs:
    """The pairs to judge, (earlier, later, shared Code Entities), oldest later Decision first; and how many pairs
    of Decisions governing the same Code Entity were left out, by reason."""

    pairs: list[tuple[str, str, tuple[str, ...]]]
    over_max_later: int  # past the cost bound
    share_only_containing_code: int  # share only a file or package that holds the code each one governs


def candidate_pairs(graph: Graph, max_later: int | None = MAX_LATER) -> CandidatePairs:
    """The pairs of Decisions to judge.

    A pair shares a Code Entity among the most specific ones each Decision governs (a file or package counts only
    for a Decision that governs nothing inside it), the later one is from another Discussion and strictly later.
    Each earlier Decision is paired with its `max_later` nearest later Decisions (None: all of them), which
    bounds the judge's cost at that many calls per Decision.
    """
    index = DecisionIndex(graph)
    parent = {e.target: e.source for e in graph.edges("CONTAINS")
              if "CodeEntity" in graph.nodes[e.source].labels and "CodeEntity" in graph.nodes[e.target].labels}

    def ancestors(entity: str) -> set[str]:
        out = set()
        while (entity := parent.get(entity)) is not None and entity not in out:
            out.add(entity)
        return out

    def when(decision: str) -> str:
        return index.decisions[decision].props["date"]

    def sharing(governs: dict[str, set[str]]) -> dict[tuple[str, str], set[str]]:
        """(earlier, later) -> the entities both govern, for Decisions of different Discussions."""
        governed_by: dict[str, set[str]] = defaultdict(set)
        for decision, entities in governs.items():
            for entity in entities:
                governed_by[entity].add(decision)
        out: dict[tuple[str, str], set[str]] = defaultdict(set)
        for entity, decisions in governed_by.items():
            for a in decisions:
                for b in decisions:
                    pa, pb = index.decisions[a].props, index.decisions[b].props
                    if pa["discussion_id"] != pb["discussion_id"] and pa["date"] < pb["date"]:
                        out[(a, b)].add(entity)
        return out

    specific = {d: es - set().union(*(ancestors(e) for e in es)) for d, es in index.governs_any.items()}
    shared = sharing(specific)
    nearest: dict[str, list[str]] = defaultdict(list)
    for a, b in sorted(shared, key=lambda pair: (when(pair[1]), pair[1])):
        nearest[a].append(b)
    keep = {(a, b) for a, laters in nearest.items() for b in laters[:max_later]}
    pairs = [(a, b, tuple(sorted(shared[(a, b)]))) for a, b in
             sorted(keep, key=lambda pair: (when(pair[1]), when(pair[0]), pair))]
    return CandidatePairs(pairs, over_max_later=len(shared) - len(keep),
                          share_only_containing_code=len(set(sharing(index.governs_any)) - set(shared)))


@dataclass(frozen=True, slots=True)
class PairingReport:
    """What the judge was asked, and every candidate pair it was not asked about, by reason (the build prints it)."""

    max_later: int | None
    judged: int
    over_max_later: int
    share_only_containing_code: int
    explicitly_linked: int  # history already states the Supersession
    already_superseded: int  # the earlier Decision was explicitly superseded before the later one took effect

    def as_dict(self) -> dict:
        return {"max_later": self.max_later, "judged": self.judged, "skipped": {
            "over_max_later": self.over_max_later, "share_only_containing_code": self.share_only_containing_code,
            "explicitly_linked": self.explicitly_linked, "already_superseded": self.already_superseded}}


def inferred_supersessions(graph: Graph, discussions: Iterable[Discussion], explicit: Iterable[Edge],
                           judge: SupersessionJudge,
                           max_later: int | None = MAX_LATER) -> tuple[list[Edge], PairingReport]:
    by_id = {d.id: d for d in discussions}
    linked, dead_since = set(), {}
    for e in explicit:
        linked.add((e.target, e.source))
        if e.type == "SUPERSEDES":
            dead_since[e.target] = min(e.props["observed_at"], dead_since.get(e.target, e.props["observed_at"]))
    name = judge_name(judge)
    candidates = candidate_pairs(graph, max_later)
    out, judged, explicitly_linked, already_superseded = [], 0, 0, 0
    for earlier, later, shared in candidates.pairs:
        b = summary(graph, later)
        if (earlier, later) in linked:
            explicitly_linked += 1
            continue
        if dead_since.get(earlier, "9999") <= b.date:
            already_superseded += 1
            continue
        judged += 1
        discussion = by_id[b.discussion_id]
        judgment = judge.judge(CandidatePair(summary(graph, earlier), b, shared, discussion.text))
        if judgment.label not in EDGE_TYPE:
            continue
        quote = judgment.quote.strip()
        segment = next((s for s in discussion.segments if quote_holds(quote, s.text)), None)
        if segment is None:
            log.info("dropped %s judgment %s -> %s: quote not verbatim in %s", judgment.label, earlier, later,
                     b.discussion_id)
            continue
        out.append(supersession_edge(later, earlier, type_=EDGE_TYPE[judgment.label], basis=INFERRED, quote=quote,
                                     record=b.discussion_id, locator=segment.locator, at=b.date, via="judge",
                                     judge=name, reason=judgment.reason))
    report = PairingReport(max_later, judged, candidates.over_max_later, candidates.share_only_containing_code,
                           explicitly_linked, already_superseded)
    log.info("supersession judge: %s", report.as_dict())
    return out, report
