"""The Live Decision rule, shared by `why` and `check_change`: each Decision's Supersession status.

A Decision with a SUPERSEDES edge into it is superseded. Otherwise, one with a REFINES edge from a Decision that is
not itself superseded is refined (a refinement that was later reverted no longer narrows anything). Among several
edges the strongest names the superseder: explicit before inferred, a Decision before a record, then the earliest.
A Live Decision is one with no status here, or a refined one (partly live).

Each status also follows the Supersession chain from what superseded or refined the Decision: when that is a
Decision that was itself superseded, and so on, `chain` holds those later edges (the strongest SUPERSEDES edge of
each, at most `MAX_CHAIN`), so the last node is the one nothing supersedes: a Live (or refined) Decision, or a record.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Literal

from whycode.answer.confidence import DecisionGrounding
from whycode.answer.patterns import ALL, GraphReader, Governing, HistoryView, SupersessionRow
from whycode.contract import GovernsLink, SupersessionOrigin

NotLive = Literal["superseded", "refined"]
MAX_CHAIN = 10
"""At most this many further Supersessions are followed from what superseded a Decision."""


@dataclass(frozen=True, slots=True)
class SupersessionStatus:
    """Why a Decision is not (fully) live: the strongest edge into it and what it names."""

    status: NotLive
    edge: SupersessionRow
    by: str | None  # the superseding or refining node; None when the Decision's own record declares it dead
    chain: tuple[SupersessionRow, ...] = ()  # what superseded `by`, what superseded that, ... (empty if `by` is None)

    @property
    def superseded(self) -> bool:
        return self.status == "superseded"

    @property
    def basis(self) -> SupersessionOrigin:
        return self.edge.basis

    @property
    def at(self) -> dt.date:
        return self.edge.day

    @property
    def source(self) -> str:
        """The record whose text holds the edge's verbatim quote."""
        return self.edge.source.id

    @property
    def chain_ids(self) -> list[str]:
        """`by`, then each node that superseded the one before it; the last is superseded by nothing."""
        return [self.by, *(row.by.id for row in self.chain)] if self.by else []

    @property
    def witnesses(self) -> frozenset[str]:
        """The node ids that show the Decision is not live: what superseded or refined it (or anything later in its
        chain), and the record saying so."""
        return frozenset({self.source, *self.chain_ids})


def _rank(row: SupersessionRow, own_record: str) -> tuple:
    return (row.basis != "explicit", not row.by_decision, row.by.id == own_record, row.at, row.by.id)


def supersession_statuses(reader: GraphReader, own_record: Mapping[str, str],
                          view: HistoryView = ALL) -> dict[str, SupersessionStatus]:
    """Decision id -> its Supersession status, for the Decisions (id -> its Discussion id) that are not live."""
    if not own_record:
        return {}
    rows = reader.supersession(sorted(own_record), view)
    refiners = sorted({r.by.id for r in rows if r.type == "REFINES"})
    dead_refiners = {r.decision for r in (reader.supersession(refiners, view) if refiners else [])
                     if r.type == "SUPERSEDES"}
    edges: dict[str, list[SupersessionRow]] = defaultdict(list)
    for r in rows:
        edges[r.decision].append(r)
    out = {}
    for decision_id, found in edges.items():
        superseding = [r for r in found if r.type == "SUPERSEDES"]
        refining = [r for r in found if r.type == "REFINES" and r.by.id not in dead_refiners]
        status: NotLive = "superseded" if superseding else "refined"
        candidates = superseding or refining
        if candidates:
            best = min(candidates, key=lambda r: _rank(r, own_record[decision_id]))
            out[decision_id] = SupersessionStatus(status, best,
                                                  None if best.by.id == own_record[decision_id] else best.by.id)
    return _with_chains(reader, out, view)


def _with_chains(reader: GraphReader, statuses: dict[str, SupersessionStatus],
                 view: HistoryView) -> dict[str, SupersessionStatus]:
    """Each superseded status with the Supersession chain that follows its superseding Decision (a refining one is
    live by construction)."""
    strongest: dict[str, SupersessionRow | None] = {}  # Decision id -> its strongest SUPERSEDES edge, None if live
    home = {s.by: s.edge.by_discussion.id for s in statuses.values()
            if s.superseded and s.by and s.edge.by_discussion is not None}  # Decision id -> its Discussion id
    frontier = set(home)
    for _ in range(MAX_CHAIN):
        if not frontier:
            break
        rows = [r for r in reader.supersession(sorted(frontier), view) if r.type == "SUPERSEDES"]
        for decision_id in frontier:
            mine = [r for r in rows if r.decision == decision_id]
            strongest[decision_id] = min(mine, key=lambda r: _rank(r, home[decision_id])) if mine else None
        frontier = set()
        for row in rows:
            if row.by_decision and row.by.id not in strongest and row.by_discussion is not None:
                home[row.by.id] = row.by_discussion.id
                frontier.add(row.by.id)

    def chain(by: str | None) -> tuple[SupersessionRow, ...]:
        out: list[SupersessionRow] = []
        seen = {by}
        while by is not None and (row := strongest.get(by)) is not None and row.by.id not in seen:
            out.append(row)
            by = row.by.id
            seen.add(by)
        return tuple(out)

    return {d: replace(s, chain=chain(s.by)) for d, s in statuses.items()}


def grounding(row: Governing, status: SupersessionStatus | None, link: GovernsLink | None = None) -> DecisionGrounding:
    """What the confidence scorer needs to know about one Decision (`link` defaults to the row's own)."""
    return DecisionGrounding(link=link or row.link, source=row.discussion.kind,
                             has_rationale=bool(row.decision.rationale),
                             status=status.status if status else "live",
                             supersession=status.basis if status else None)
