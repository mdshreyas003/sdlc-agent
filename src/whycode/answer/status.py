"""The Live Decision rule, shared by `why` and `check_change`: each Decision's Supersession status.

A Decision with a SUPERSEDES edge into it is superseded. Otherwise, one with a REFINES edge from a Decision that is
not itself superseded is refined (a refinement that was later reverted no longer narrows anything). Among several
edges the strongest names the superseder: explicit before inferred, a Decision before a record, then the earliest.
A Live Decision is one with no status here, or a refined one (partly live).
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from whycode.answer.confidence import DecisionGrounding
from whycode.answer.patterns import ALL, GraphReader, Governing, HistoryView, SupersessionRow
from whycode.contract import GovernsLink, SupersessionOrigin

NotLive = Literal["superseded", "refined"]


@dataclass(frozen=True, slots=True)
class SupersessionStatus:
    """Why a Decision is not (fully) live: the strongest edge into it and what it names."""

    status: NotLive
    edge: SupersessionRow
    by: str | None  # the superseding or refining node; None when the Decision's own record declares it dead

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
    def witnesses(self) -> frozenset[str]:
        """The node ids that show the Decision is not live: what superseded or refined it, and the record saying so."""
        return frozenset({self.by, self.source} - {None})


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
    return out


def grounding(row: Governing, status: SupersessionStatus | None, link: GovernsLink | None = None) -> DecisionGrounding:
    """What the confidence scorer needs to know about one Decision (`link` defaults to the row's own)."""
    return DecisionGrounding(link=link or row.link, source=row.discussion.kind,
                             has_rationale=bool(row.decision.rationale),
                             status=status.status if status else "live",
                             supersession=status.basis if status else None)
