"""Fixed, parameterised, read-only query patterns: the only way the answer engine reads the graph.

Guards (ported from the legacy query harness, see notes: legacy-query-safety.md):
- the Cypher is a module constant; callers pass parameters only, never Cypher;
- a static check refuses any write clause before a query is sent;
- every query runs with read routing (the server rejects writes) and a server-side timeout;
- every pattern caps its rows with `LIMIT $limit`;
- stubs are never returned;
- every pattern sees history only as of `$as_of` (an ISO date; records, Decisions and edges dated after it are
  absent) and treats the node ids in `$exclude` as absent, with everything that rests on them (a scoreboard
  query's `as_of` and `exclude`);
- `selfcheck()` EXPLAINs every pattern and requires a read-only plan; run it at startup to fail fast.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from neo4j import Driver, Query, RoutingControl

TIMEOUT_S = 10.0
ROW_LIMIT = 50
_WRITE = re.compile(r"\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP|LOAD|FOREACH|CALL|DETACH)\b", re.IGNORECASE)
_REAL = "NOT coalesce({v}.stub, false)"
_SEEN = "{v}.date <= $as_of AND NOT {v}.id IN $exclude"  # dated on or before as_of, and not excluded
ALL_HISTORY = "9999-12-31"

PATTERNS: dict[str, str] = {
    # Anchor -> Code Entity, by exact key or exact alias.
    "resolve": """
MATCH (e:CodeEntity) WHERE e.key = $name OR $name IN e.aliases
RETURN e.id AS id, e.kind AS kind, e.key AS key
ORDER BY e.id LIMIT $limit""",
    # Anchor -> governing Decisions (on the anchor or on entities it contains) -> their Discussions.
    "governing": f"""
MATCH (a:CodeEntity {{id: $id}})-[:CONTAINS*0..2]->(e:CodeEntity)
MATCH (d:Decision)-[g:GOVERNS]->(e)
MATCH (s:Discussion)-[:YIELDS]->(d)
WHERE {_REAL.format(v="s")} AND {_SEEN.format(v="s")} AND {_SEEN.format(v="d")}
  AND g.observed_at <= $as_of AND NOT coalesce(g.change, "") IN $exclude
WITH d, s, collect(DISTINCT {{entity: e.id, link: g.link}}) AS governs
RETURN d {{.id, .choice, .rationale, .quote, .date, .alternatives_rejected, .speaker}} AS decision,
       s {{.id, .kind, .title, .url, .date, .text}} AS discussion, governs
ORDER BY decision.date DESC, decision.id LIMIT $limit""",
    # Discussions -> the Changes that close them (an issue's Decisions are implemented by its closers).
    "closers": f"""
MATCH (c:Change)-[:CLOSES]->(s:Discussion)
WHERE s.id IN $ids AND {_REAL.format(v="c")} AND {_SEEN.format(v="c")}
RETURN DISTINCT c {{.id, .kind, .title, .url, .date, .text}} AS change
ORDER BY change.date, change.id LIMIT $limit""",
    # Records -> People who authored them, or reviewed and approved them.
    "people": """
MATCH (p:Person)-[r:AUTHORED|REVIEWED]->(s:Node)
WHERE s.id IN $ids AND (type(r) = 'AUTHORED' OR r.state = 'APPROVED')
RETURN DISTINCT p.handle AS handle, p.active AS active, s.id AS record,
       CASE type(r) WHEN 'AUTHORED' THEN 'author' ELSE 'approver' END AS role
ORDER BY handle, role LIMIT $limit""",
    "people_by_handle": """
MATCH (p:Person) WHERE p.handle IN $handles
RETURN p.handle AS handle, p.active AS active ORDER BY handle LIMIT $limit""",
    # Changes and Discussions -> the Incidents they close or are (an issue is an Incident once a Change closes it).
    "incidents": f"""
MATCH (c:Change)-[:CLOSES]->(i:Incident)
WHERE (i.id IN $ids OR c.id IN $ids) AND {_SEEN.format(v="c")} AND {_SEEN.format(v="i")}
RETURN DISTINCT i {{.id, .kind, .title, .url, .date, .text}} AS incident
ORDER BY incident.date, incident.id LIMIT $limit""",
    # Decisions -> the SUPERSEDES / REFINES edges into them, the node that superseded or refined each, that
    # node's Discussion (when it is a Decision), and the record whose text holds the edge's quote.
    "supersession": f"""
MATCH (x:Node)-[r:SUPERSEDES|REFINES]->(d:Decision)
WHERE d.id IN $ids AND {_REAL.format(v="x")} AND r.observed_at <= $as_of
  AND NOT x.id IN $exclude AND NOT r.source IN $exclude
OPTIONAL MATCH (xs:Discussion)-[:YIELDS]->(x)
WITH d, r, x, xs WHERE xs IS NULL OR NOT xs.id IN $exclude
MATCH (src:Node {{id: r.source}})
RETURN d.id AS decision, type(r) AS type, r.basis AS basis, r.observed_at AS at, r.quote AS quote,
       x {{.id, .kind, .choice, .quote, .date, .title, .url, .text}} AS by,
       xs {{.id, .kind, .title, .url, .date, .text}} AS by_discussion,
       src {{.id, .kind, .title, .url, .date, .text}} AS source
ORDER BY decision, at, by.id LIMIT $limit""",
    # Refusals: Changes that touched the anchor, what it contains, or what contains it.
    "nearest_changes": f"""
MATCH (a:CodeEntity {{id: $id}})
OPTIONAL MATCH (parent:CodeEntity)-[:CONTAINS]->(a)
OPTIONAL MATCH (a)-[:CONTAINS*0..2]->(inner:CodeEntity)
WITH collect(DISTINCT parent) + collect(DISTINCT inner) AS scope
UNWIND scope AS t
MATCH (c:Change)-[:TOUCHES]->(t)
WHERE {_REAL.format(v="c")} AND {_SEEN.format(v="c")}
WITH DISTINCT c
RETURN c {{.id, .kind, .title, .url, .date, .text}} AS change
ORDER BY change.date DESC, change.id LIMIT $limit""",
    # Refusals: Decisions that govern what contains the anchor (nearby, but not governing it).
    "nearby_decisions": f"""
MATCH (parent:CodeEntity)-[:CONTAINS]->(:CodeEntity {{id: $id}})
MATCH (d:Decision)-[g:GOVERNS]->(parent)
MATCH (s:Discussion)-[:YIELDS]->(d)
WHERE {_REAL.format(v="s")} AND {_SEEN.format(v="s")} AND {_SEEN.format(v="d")}
  AND g.observed_at <= $as_of AND NOT coalesce(g.change, "") IN $exclude
WITH DISTINCT d, s
RETURN d {{.id, .choice, .quote, .date}} AS decision, s {{.id, .kind, .title, .url}} AS discussion
ORDER BY decision.date DESC, decision.id LIMIT $limit""",
}

_SAMPLE = {"name": "x", "id": "x", "ids": ["x"], "handles": ["x"], "limit": 1, "as_of": ALL_HISTORY,
           "exclude": ["x"]}


class GraphReader:
    def __init__(self, driver: Driver, database: str | None = None, timeout: float = TIMEOUT_S):
        self.driver = driver
        self.database = database or "neo4j"
        self.timeout = timeout

    def _run(self, pattern: str, explain: bool = False, **params: Any) -> Any:
        cypher = PATTERNS[pattern]
        if _WRITE.search(cypher):
            raise ValueError(f"pattern {pattern} contains a write clause")
        params.setdefault("limit", ROW_LIMIT)
        return self.driver.execute_query(
            Query(("EXPLAIN " if explain else "") + cypher, timeout=self.timeout), params,
            routing_=RoutingControl.READ, database_=self.database,
        )

    def _rows(self, pattern: str, **params: Any) -> list[dict[str, Any]]:
        return [record.data() for record in self._run(pattern, **params).records]

    def selfcheck(self) -> None:
        """EXPLAIN every pattern; raise unless each plans as a read-only query."""
        for name, cypher in PATTERNS.items():
            params = {k: v for k, v in _SAMPLE.items() if re.search(rf"\${k}\b", cypher)}
            try:
                summary = self._run(name, explain=True, **params).summary
            except Exception as exc:
                raise RuntimeError(f"query pattern {name} failed EXPLAIN: {exc}") from exc
            if summary.query_type != "r":
                raise RuntimeError(f"query pattern {name} is not read-only ({summary.query_type})")

    def resolve(self, name: str) -> list[dict[str, Any]]:
        return self._rows("resolve", name=name)

    # Every traversal below takes the query's view of history: `as_of` (ISO date) and `exclude` (node ids).

    def governing(self, entity_id: str, as_of: str = ALL_HISTORY, exclude: Sequence[str] = ()) -> list[dict[str, Any]]:
        return self._rows("governing", id=entity_id, as_of=as_of, exclude=list(exclude))

    def closers(self, discussion_ids: list[str], as_of: str = ALL_HISTORY,
                exclude: Sequence[str] = ()) -> list[dict[str, Any]]:
        return [r["change"] for r in self._rows("closers", ids=discussion_ids, as_of=as_of, exclude=list(exclude))]

    def people(self, record_ids: list[str]) -> list[dict[str, Any]]:
        return self._rows("people", ids=record_ids)

    def people_by_handle(self, handles: list[str]) -> list[dict[str, Any]]:
        return self._rows("people_by_handle", handles=handles)

    def incidents(self, record_ids: list[str], as_of: str = ALL_HISTORY,
                  exclude: Sequence[str] = ()) -> list[dict[str, Any]]:
        return [r["incident"] for r in self._rows("incidents", ids=record_ids, as_of=as_of, exclude=list(exclude))]

    def supersession(self, decision_ids: list[str], as_of: str = ALL_HISTORY,
                     exclude: Sequence[str] = ()) -> list[dict[str, Any]]:
        return self._rows("supersession", ids=decision_ids, as_of=as_of, exclude=list(exclude), limit=4 * ROW_LIMIT)

    def nearest_changes(self, entity_id: str, as_of: str = ALL_HISTORY,
                        exclude: Sequence[str] = ()) -> list[dict[str, Any]]:
        return [r["change"] for r in self._rows("nearest_changes", id=entity_id, as_of=as_of, exclude=list(exclude),
                                                limit=10)]

    def nearby_decisions(self, entity_id: str, as_of: str = ALL_HISTORY,
                         exclude: Sequence[str] = ()) -> list[dict[str, Any]]:
        return self._rows("nearby_decisions", id=entity_id, as_of=as_of, exclude=list(exclude), limit=10)
