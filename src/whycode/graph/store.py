"""Graph store: writes a built `Graph` into Neo4j idempotently, and reads it back.

`replace` makes the database hold exactly the given graph: nodes and edges are upserted on their stable ids
(MERGE on the id only, every other property overwritten), then anything the graph no longer contains is
deleted. Re-running a build therefore leaves node and edge counts unchanged, and rebuilding with an earlier
cutoff removes what is now after it.

Answer-time reads do not come through here: they go through the fixed, read-only query patterns in
`whycode.answer.patterns`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from typing import Any

from neo4j import Driver

from whycode.graph import EDGE_TYPES, NODE_LABELS, Edge, Graph, Node

_BATCH = 1000
_ALL_LABELS = sorted(NODE_LABELS)

_UPSERT_NODES = """
UNWIND $rows AS row
MERGE (n:Node {id: row.id})
SET n = row.props
WITH n, row
REMOVE n:$($all_labels)
SET n:$(row.labels)
"""

_UPSERT_EDGES = """
UNWIND $rows AS row
MATCH (a:Node {id: row.source}), (b:Node {id: row.target})
MERGE (a)-[r:%s {id: row.id}]->(b)
SET r = row.props
"""


def _chunks(rows: list[dict[str, Any]]) -> Iterator[list[dict[str, Any]]]:
    for i in range(0, len(rows), _BATCH):
        yield rows[i: i + _BATCH]


def _storable(props: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for key, value in props.items():
        if value is None:
            continue
        if isinstance(value, (set, frozenset, tuple)):
            value = sorted(value) if isinstance(value, (set, frozenset)) else list(value)
        out[key] = value
    return out


class GraphStore:
    def __init__(self, driver: Driver, database: str | None = None):
        self.driver = driver
        self.database = database or "neo4j"

    def _run(self, query: str, **params: Any):
        return self.driver.execute_query(query, params, database_=self.database)

    def init_schema(self) -> None:
        self._run("CREATE CONSTRAINT node_id IF NOT EXISTS FOR (n:Node) REQUIRE n.id IS UNIQUE")

    def replace(self, graph: Graph) -> None:
        self.init_schema()
        node_rows = [
            {"id": n.id, "labels": sorted(n.labels), "props": _storable({**n.props, "id": n.id})}
            for n in graph.nodes.values()
        ]
        for rows in _chunks(node_rows):
            self._run(_UPSERT_NODES, rows=rows, all_labels=_ALL_LABELS)
        by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for e in graph.edges():
            if e.type not in EDGE_TYPES:  # types are interpolated into Cypher: closed set only
                raise ValueError(f"unknown edge type {e.type}")
            by_type[e.type].append(
                {"id": e.id, "source": e.source, "target": e.target, "props": _storable({**e.props, "id": e.id})}
            )
        for edge_type, rows in sorted(by_type.items()):
            for chunk in _chunks(rows):
                self._run(_UPSERT_EDGES % edge_type, rows=chunk)
        edge_ids = [e.id for e in graph.edges()]
        self._run("MATCH (:Node)-[r]->(:Node) WHERE NOT r.id IN $ids DELETE r", ids=edge_ids)
        self._run("MATCH (n:Node) WHERE NOT n.id IN $ids DETACH DELETE n", ids=list(graph.nodes))

    def snapshot(self) -> Graph:
        """The whole stored graph (meant for fixture-sized graphs: tests, debugging, the human view)."""
        nodes = self._run("MATCH (n:Node) RETURN n.id AS id, labels(n) AS labels, properties(n) AS props").records
        edges = self._run(
            "MATCH (a:Node)-[r]->(b:Node) RETURN a.id AS source, type(r) AS type, b.id AS target, "
            "properties(r) AS props"
        ).records
        return Graph(
            (Node(r["id"], frozenset(r["labels"]) - {"Node"}, dict(r["props"])) for r in nodes),
            (Edge(r["source"], r["type"], r["target"], dict(r["props"])) for r in edges),
        )

    def counts(self) -> dict[str, int]:
        """Node counts per label plus `edges`, for build reports."""
        labels = self._run(
            "MATCH (n:Node) UNWIND labels(n) AS label WITH label WHERE label <> 'Node' "
            "RETURN label, count(*) AS count ORDER BY label"
        ).records
        edges = self._run("MATCH (:Node)-[r]->(:Node) RETURN count(r) AS count").records[0]["count"]
        return {**{r["label"]: r["count"] for r in labels}, "edges": edges}
