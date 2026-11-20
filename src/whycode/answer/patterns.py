"""Fixed, parameterised, read-only query patterns: the only way the answer engine reads the graph.

Guards (ported from the legacy query harness, see notes: legacy-query-safety.md):
- the Cypher is a module constant; callers pass parameters only, never Cypher;
- a static check refuses any write clause before a query is sent;
- every query runs with read routing (the server rejects writes) and a server-side timeout;
- every pattern caps its rows with `LIMIT $limit`;
- stubs are never returned;
- every traversal sees history through a `HistoryView`: only as of `$as_of` (an ISO date; records, Decisions and
  edges dated after it are absent), with the node ids in `$exclude` absent along with everything that rests on
  them (a scoreboard query's `as_of` and `exclude`);
- `selfcheck()` EXPLAINs every pattern and requires a read-only plan; run it at startup to fail fast.

Rows come back typed (`Record`, `DecisionRow`, `Governing`, `SupersessionRow`, `EntityRow`), never as raw dicts.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from neo4j import Driver, Query, RoutingControl

from whycode.contract import GovernsLink, SupersessionOrigin
from whycode.graph import day

TIMEOUT_S = 10.0
ROW_LIMIT = 50
_WRITE = re.compile(r"\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP|LOAD|FOREACH|CALL|DETACH)\b", re.IGNORECASE)
_REAL = "NOT coalesce({v}.stub, false)"
_SEEN = "{v}.date <= $as_of AND NOT {v}.id IN $exclude"  # dated on or before as_of, and not excluded
# A Decision `d`, its Discussion `s` and its GOVERNS edge `g` are all visible (an excluded implementing Change hides g).
_GOVERNS_SEEN = (f"{_REAL.format(v='s')} AND {_SEEN.format(v='s')} AND {_SEEN.format(v='d')}\n"
                 "  AND g.observed_at <= $as_of AND NOT coalesce(g.change, \"\") IN $exclude")
ALL_HISTORY = "9999-12-31"

PATTERNS: dict[str, str] = {
    # Anchor -> Code Entity, by exact key or exact alias.
    "resolve": """
MATCH (e:CodeEntity) WHERE e.key = $name OR $name IN e.aliases
RETURN e.id AS id, e.kind AS kind, e.key AS key, e.file AS file
ORDER BY e.id LIMIT $limit""",
    # Free-form question -> a shortlist of Code Entities whose own names hold its words (for the matching step).
    "candidates": """
MATCH (e:CodeEntity)
WITH e, [n IN [e.name, coalesce(e.receiver, "")] + coalesce(e.names, []) WHERE n <> "" | toLower(n)] AS names
WITH e, size([w IN $words WHERE any(n IN names WHERE n CONTAINS w)]) AS hits
WHERE hits > 0
RETURN e.id AS id, e.kind AS kind, e.key AS key, e.file AS file
ORDER BY hits DESC, size(e.key), e.id LIMIT $limit""",
    # Anchor -> governing Decisions (on the anchor or on entities it contains) -> their Discussions.
    "governing": f"""
MATCH (a:CodeEntity {{id: $id}})-[:CONTAINS*0..2]->(e:CodeEntity)
MATCH (d:Decision)-[g:GOVERNS]->(e)
MATCH (s:Discussion)-[:YIELDS]->(d)
WHERE {_GOVERNS_SEEN}
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
    # Person to Ask: active authors and approving reviewers of the latest Changes touching files under each area
    # path prefix, the nearest area (lowest rank) first; each person once, with the Change that puts them there.
    "area_people": f"""
UNWIND range(0, size($prefixes) - 1) AS rank
MATCH (c:Change)-[:TOUCHES]->(f:CodeEntity {{kind: "file"}})
WHERE f.key STARTS WITH $prefixes[rank] AND {_REAL.format(v="c")} AND {_SEEN.format(v="c")}
MATCH (p:Person)-[r:AUTHORED|REVIEWED]->(c)
WHERE coalesce(p.active, false) AND (type(r) = 'AUTHORED' OR r.state = 'APPROVED')
WITH p, rank, c, type(r) <> 'AUTHORED' AS approver
ORDER BY rank, c.date DESC, approver, c.id
WITH p, collect({{rank: rank, date: c.date, approver: approver, change: c.id}})[0] AS best
RETURN p.handle AS handle, best.change AS via, CASE best.approver WHEN true THEN 'approver' ELSE 'author' END AS role
ORDER BY best.rank, best.date DESC, best.approver, handle LIMIT $limit""",
    # Refusals: Decisions that govern what contains the anchor (nearby, but not governing it).
    "nearby_decisions": f"""
MATCH (parent:CodeEntity)-[:CONTAINS]->(:CodeEntity {{id: $id}})
MATCH (d:Decision)-[g:GOVERNS]->(parent)
MATCH (s:Discussion)-[:YIELDS]->(d)
WHERE {_GOVERNS_SEEN}
WITH DISTINCT d, s
RETURN d {{.id, .choice, .quote, .date}} AS decision, s {{.id, .kind, .title, .url}} AS discussion
ORDER BY decision.date DESC, decision.id LIMIT $limit""",
    # check_change: the Code Entities of a diff's files with every CodeEntity field (to rebuild a CodeIndex), plus
    # the settings the diff names by literal and the settings of the files' packages (their Go variables).
    "diff_entities": """
MATCH (e:CodeEntity)
WHERE (e.kind = 'file' AND e.key IN $paths)
   OR (e.kind IN ['function', 'setting'] AND e.parent IN $paths)
   OR (e.kind = 'setting' AND (e.package IN $packages OR e.key IN $literals
                              OR any(n IN coalesce(e.names, []) WHERE n IN $literals)))
RETURN e {.kind, .key, .parent, .package, .package_name, .name, .receiver, .pointer_receiver, .go_var, .names}
       AS entity
ORDER BY entity.kind, entity.key LIMIT $limit""",
    # check_change: the Decisions governing exactly these Code Entities, their Discussions and governs links.
    "governing_exact": f"""
MATCH (d:Decision)-[g:GOVERNS]->(e:CodeEntity)
WHERE e.id IN $ids
MATCH (s:Discussion)-[:YIELDS]->(d)
WHERE {_GOVERNS_SEEN}
WITH d, s, collect(DISTINCT {{entity: e.id, link: g.link, change: g.change}}) AS governs
RETURN d {{.id, .choice, .rationale, .quote, .date}} AS decision,
       s {{.id, .kind, .title, .url, .date}} AS discussion, governs
ORDER BY decision.date DESC, decision.id LIMIT $limit""",
    # check_change: the lines Changes added to and removed from files.
    "change_lines": f"""
MATCH (c:Change)-[t:TOUCHES]->(f:CodeEntity {{kind: 'file'}})
WHERE c.id IN $ids AND f.key IN $paths AND {_REAL.format(v="c")}
RETURN c.id AS change, f.key AS path, coalesce(t.added, []) AS added, coalesce(t.removed, []) AS removed
ORDER BY change, path LIMIT $limit""",
    # check_change: which Change closed which Incident, for these Changes and Discussions.
    "incident_links": f"""
MATCH (c:Change)-[:CLOSES]->(i:Incident)
WHERE (i.id IN $ids OR c.id IN $ids) AND {_SEEN.format(v="c")} AND {_SEEN.format(v="i")}
RETURN DISTINCT c.id AS change, i.id AS incident
ORDER BY incident, change LIMIT $limit""",
}

_SAMPLE = {"name": "x", "id": "x", "ids": ["x"], "handles": ["x"], "limit": 1, "as_of": ALL_HISTORY,
           "exclude": ["x"], "words": ["x"], "prefixes": ["x"], "paths": ["x"], "packages": ["x"],
           "literals": ["x"]}
DIFF_ENTITY_LIMIT = 5000
"""check_change reads at most this many Code Entities for one diff (the files' functions and settings)."""


@dataclass(frozen=True, slots=True)
class HistoryView:
    """A query's view of history: nothing dated after `as_of` (None: all of it), and none of the `exclude`d records,
    nor what rests on them."""

    as_of: dt.date | None = None
    exclude: frozenset[str] = frozenset()

    @classmethod
    def of(cls, as_of: dt.date | None = None, exclude: Iterable[str] = ()) -> HistoryView:
        return cls(as_of, frozenset(exclude))

    def params(self) -> dict[str, Any]:
        return {"as_of": self.as_of.isoformat() if self.as_of else ALL_HISTORY, "exclude": sorted(self.exclude)}


ALL = HistoryView()
"""All of history, nothing excluded."""


@dataclass(frozen=True, slots=True)
class Record:
    """A history record (Discussion, Change, Incident) as a pattern returns it."""

    id: str
    kind: str
    title: str | None = None
    url: str | None = None
    date: str | None = None  # ISO, as stored
    text: str = ""

    @classmethod
    def of(cls, row: Mapping[str, Any]) -> Record:
        return cls(id=row["id"], kind=row.get("kind") or "record", title=row.get("title"), url=row.get("url"),
                   date=row.get("date"), text=row.get("text") or "")

    @property
    def day(self) -> dt.date | None:
        return day(self.date)


@dataclass(frozen=True, slots=True)
class DecisionRow:
    id: str
    choice: str
    quote: str
    date: str  # ISO, as stored
    rationale: str = ""
    alternatives_rejected: tuple[str, ...] = ()
    speaker: str | None = None

    @classmethod
    def of(cls, row: Mapping[str, Any]) -> DecisionRow:
        return cls(id=row["id"], choice=row["choice"], quote=row["quote"], date=row["date"],
                   rationale=row.get("rationale") or "",
                   alternatives_rejected=tuple(row.get("alternatives_rejected") or ()), speaker=row.get("speaker"))

    @property
    def day(self) -> dt.date:
        return day(self.date)


@dataclass(frozen=True, slots=True)
class Governs:
    """One GOVERNS edge: the Code Entity, its link, and (hard) the Change implementing the Decision there."""

    entity: str
    link: GovernsLink
    change: str | None = None


@dataclass(frozen=True, slots=True)
class Governing:
    """A Decision, the Discussion it came from, and the Code Entities (in the query's scope) it governs."""

    decision: DecisionRow
    discussion: Record
    governs: tuple[Governs, ...]

    @classmethod
    def of(cls, row: Mapping[str, Any]) -> Governing:
        return cls(DecisionRow.of(row["decision"]), Record.of(row["discussion"]),
                   tuple(Governs(g["entity"], g["link"], g.get("change")) for g in row["governs"]))

    @property
    def link(self) -> GovernsLink:
        """`hard` when the Change implementing the Decision touched any governed entity, else `soft`."""
        return "hard" if self.hard_entities else "soft"

    @property
    def entities(self) -> frozenset[str]:
        return frozenset(g.entity for g in self.governs)

    @property
    def hard_entities(self) -> frozenset[str]:
        return frozenset(g.entity for g in self.governs if g.link == "hard")

    @property
    def implementing(self) -> frozenset[str]:
        """The Changes implementing the Decision (their diffs made the hard links)."""
        return frozenset(g.change for g in self.governs if g.link == "hard" and g.change)


SupersessionType = Literal["SUPERSEDES", "REFINES"]


@dataclass(frozen=True, slots=True)
class SupersessionRow:
    """A SUPERSEDES or REFINES edge into `decision`: what superseded or refined it (`by`, a Decision with its
    Discussion, or a record), when, on what basis, and the verbatim `quote` in the `source` record."""

    decision: str
    type: SupersessionType
    basis: SupersessionOrigin
    at: str  # ISO, as stored
    quote: str
    by: DecisionRow | Record
    by_discussion: Record | None  # when `by` is a Decision
    source: Record

    @classmethod
    def of(cls, row: Mapping[str, Any]) -> SupersessionRow:
        x = row["by"]
        by = DecisionRow.of(x) if x.get("choice") is not None else Record.of(x)
        home = row.get("by_discussion")
        return cls(decision=row["decision"], type=row["type"], basis=row["basis"], at=row["at"], quote=row["quote"],
                   by=by, by_discussion=Record.of(home) if home else None, source=Record.of(row["source"]))

    @property
    def by_decision(self) -> bool:
        return isinstance(self.by, DecisionRow)

    @property
    def day(self) -> dt.date:
        return day(self.at)


@dataclass(frozen=True, slots=True)
class EntityRow:
    """A Code Entity as `resolve`, `candidates` and the Anchor need it."""

    id: str
    kind: str
    key: str
    file: str | None = None

    @classmethod
    def of(cls, row: Mapping[str, Any]) -> EntityRow:
        return cls(id=row["id"], kind=row["kind"], key=row["key"], file=row.get("file"))


@dataclass(frozen=True, slots=True)
class PersonRow:
    handle: str
    active: bool
    role: str = "author"  # author | approver
    via: str | None = None  # area_people: the Change that puts them in the area


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

    def _rows(self, pattern: str, view: HistoryView | None = None, **params: Any) -> list[dict[str, Any]]:
        if view is not None:
            params |= view.params()
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

    def resolve(self, name: str) -> list[EntityRow]:
        return [EntityRow.of(r) for r in self._rows("resolve", name=name)]

    def candidates(self, words: list[str], limit: int = 30) -> list[EntityRow]:
        """Code Entities whose own names (name, receiver, setting names) contain any of `words` (lower case),
        the most words first."""
        return [EntityRow.of(r) for r in self._rows("candidates", words=words, limit=limit)]

    # Every traversal below sees history through a `HistoryView`.

    def governing(self, entity_id: str, view: HistoryView = ALL) -> list[Governing]:
        return [Governing.of(r) for r in self._rows("governing", view, id=entity_id)]

    def closers(self, discussion_ids: list[str], view: HistoryView = ALL) -> list[Record]:
        return [Record.of(r["change"]) for r in self._rows("closers", view, ids=discussion_ids)]

    def people(self, record_ids: list[str]) -> list[PersonRow]:
        return [PersonRow(r["handle"], bool(r["active"]), r["role"]) for r in self._rows("people", ids=record_ids)]

    def people_by_handle(self, handles: list[str]) -> list[PersonRow]:
        return [PersonRow(r["handle"], bool(r["active"])) for r in self._rows("people_by_handle", handles=handles)]

    def incidents(self, record_ids: list[str], view: HistoryView = ALL) -> list[Record]:
        return [Record.of(r["incident"]) for r in self._rows("incidents", view, ids=record_ids)]

    def supersession(self, decision_ids: list[str], view: HistoryView = ALL) -> list[SupersessionRow]:
        return [SupersessionRow.of(r) for r in self._rows("supersession", view, ids=decision_ids,
                                                           limit=4 * ROW_LIMIT)]

    def nearest_changes(self, entity_id: str, view: HistoryView = ALL) -> list[Record]:
        return [Record.of(r["change"]) for r in self._rows("nearest_changes", view, id=entity_id, limit=10)]

    def area_people(self, prefixes: list[str], view: HistoryView = ALL) -> list[PersonRow]:
        """Active people of the latest Changes touching files under each path prefix (nearest area first)."""
        return [PersonRow(r["handle"], True, r["role"], r["via"])
                for r in self._rows("area_people", view, prefixes=prefixes, limit=10)]

    def nearby_decisions(self, entity_id: str, view: HistoryView = ALL) -> list[tuple[DecisionRow, Record]]:
        return [(DecisionRow.of(r["decision"]), Record.of(r["discussion"]))
                for r in self._rows("nearby_decisions", view, id=entity_id, limit=10)]

    # check_change (`whycode.answer.fence`).

    def diff_entities(self, paths: list[str], packages: list[str], literals: list[str]) -> list[dict[str, Any]]:
        """Every stored field of the Code Entities of a diff's files (to rebuild a `CodeIndex`)."""
        return [r["entity"] for r in self._rows("diff_entities", paths=paths, packages=packages, literals=literals,
                                                limit=DIFF_ENTITY_LIMIT)]

    def governing_exact(self, entity_ids: list[str], view: HistoryView = ALL) -> list[Governing]:
        return [Governing.of(r) for r in self._rows("governing_exact", view, ids=entity_ids, limit=4 * ROW_LIMIT)]

    def change_lines(self, change_ids: list[str], paths: list[str]) -> list[dict[str, Any]]:
        return self._rows("change_lines", ids=change_ids, paths=paths, limit=4 * ROW_LIMIT)

    def incident_links(self, record_ids: list[str], view: HistoryView = ALL) -> list[tuple[str, str]]:
        """(Change, Incident) pairs: which Change closed which Incident, for these Changes and Discussions."""
        return [(r["change"], r["incident"]) for r in self._rows("incident_links", view, ids=record_ids,
                                                                  limit=4 * ROW_LIMIT)]
