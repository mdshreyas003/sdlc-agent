"""Citation audit: ask `why` about a sample of Anchors and check that every node id in every answer resolves.

Every id an Answer carries counts: Decisions (and what supersedes them), their Discussions and governed Code
Entities, the Evidence Chain, Incidents, People (`person:<handle>`, and the Change a suggested person is active
through) and every sentence citation. An id resolves when the graph holds it as a real record (stubs, referenced
but never ingested, do not count).

    uv run whycode check-citations --sample 20      # exit code 1 if any id fails to resolve

The sample is seeded and prefers governed Code Entities (answers with Decisions), then fills up with
ungoverned ones (refusals still carry the nearest evidence and people).
"""

from __future__ import annotations

import random
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from neo4j import Driver, RoutingControl

from whycode import ids
from whycode.contract import Answer

_ANCHORS = """
MATCH (e:CodeEntity)
RETURN e.key AS key, EXISTS { MATCH (:Decision)-[:GOVERNS]->(e) } AS governed
ORDER BY e.key"""
_RESOLVE = """
MATCH (n:Node) WHERE n.id IN $ids AND NOT coalesce(n.stub, false)
RETURN n.id AS id"""


class GraphResolver:
    """Which of some node ids the graph holds as real records (read-only)."""

    def __init__(self, driver: Driver, database: str | None = None):
        self.driver = driver
        self.database = database or "neo4j"

    def __call__(self, node_ids: Iterable[str]) -> set[str]:
        records = self.driver.execute_query(_RESOLVE, {"ids": sorted(set(node_ids))}, database_=self.database,
                                            routing_=RoutingControl.READ).records
        return {r["id"] for r in records}


def sample_anchors(driver: Driver, n: int, seed: int = 0, database: str | None = None) -> list[str]:
    records = driver.execute_query(_ANCHORS, database_=database or "neo4j", routing_=RoutingControl.READ).records
    governed = [r["key"] for r in records if r["governed"]]
    others = [r["key"] for r in records if not r["governed"]]
    rng = random.Random(seed)
    picked = rng.sample(governed, min(n, len(governed)))
    return picked + rng.sample(others, min(n - len(picked), len(others)))


def answer_ids(answer: Answer) -> set[str]:
    out: set[str] = set()
    for d in answer.decisions:
        out |= {d.id, *d.governs, *(i for i in (d.discussion_id, d.superseded_by) if i)}
    out |= {e.node_id for e in answer.evidence_chain}
    out |= {i.id for i in answer.incidents}
    out |= {ids.person_id(p.handle) for p in answer.people} | {p.via for p in answer.people if p.via}
    out |= {c for s in answer.sentences for c in s.cites}
    return out


@dataclass(frozen=True, slots=True)
class Unresolved:
    anchor: str
    node_id: str


@dataclass(slots=True)
class CitationAudit:
    answers: int = 0
    answered: int = 0  # not refused
    ids_checked: int = 0
    unresolved: list[Unresolved] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.answers > 0 and not self.unresolved

    def report(self) -> dict:
        return {"answers": self.answers, "answered": self.answered, "refused": self.answers - self.answered,
                "ids_checked": self.ids_checked, "ok": self.ok,
                "unresolved": [{"anchor": u.anchor, "node_id": u.node_id} for u in self.unresolved]}


def audit_citations(why: Callable[[str], Answer], anchors: Iterable[str],
                    resolve: Callable[[Iterable[str]], set[str]]) -> CitationAudit:
    audit = CitationAudit()
    for anchor in anchors:
        answer = why(anchor)
        audit.answers += 1
        audit.answered += not answer.refused
        node_ids = answer_ids(answer)
        audit.ids_checked += len(node_ids)
        found = resolve(node_ids)
        audit.unresolved += [Unresolved(anchor, i) for i in sorted(node_ids - found)]
    return audit
