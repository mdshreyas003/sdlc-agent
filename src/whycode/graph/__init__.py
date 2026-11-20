"""The graph as data: nodes and edges, before they are written or after they are read back.

Schema (labels on nodes, types on edges):
- Nodes: Change (PullRequest, Commit), Discussion (PullRequest, Issue, Rfc), Incident, Person, Decision,
  CodeEntity (Package, File, Function, Setting), Stub (referenced, never ingested, never cited).
- Stated edges: CONTAINS, TOUCHES, CLOSES, REFERENCES, REVERTS, AUTHORED, REVIEWED. A pull request's TOUCHES
  edge to a file also carries `added` / `removed`: the distinct lines its diff added and removed there (trimmed).
- Derived edges: YIELDS (Discussion -> Decision), GOVERNS (Decision -> CodeEntity, link hard|soft).
  Ticket 04 adds SUPERSEDES / REFINES (Decision -> Decision, explicit|inferred).

Every node and edge carries `origin` (stated | derived). Every edge carries a `locator` (where in the source
it was found) and `observed_at` (a date from the source, never wall-clock time). Derived nodes and edges
also carry the verbatim `quote` they rest on.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

STATED = "stated"
DERIVED = "derived"


def day(value: str | None) -> dt.date | None:
    """The day of a date or timestamp the graph stores as ISO text (None stays None)."""
    return dt.date.fromisoformat(value[:10]) if value else None

EDGE_TYPES = frozenset({
    "CONTAINS", "TOUCHES", "CLOSES", "REFERENCES", "REVERTS", "AUTHORED", "REVIEWED",
    "YIELDS", "GOVERNS", "SUPERSEDES", "REFINES",
})
NODE_LABELS = frozenset({
    "Change", "PullRequest", "Commit", "Discussion", "Issue", "Rfc", "Incident", "Person", "Decision",
    "CodeEntity", "Package", "File", "Function", "Setting", "Stub",
})


@dataclass(frozen=True, slots=True)
class Node:
    id: str
    labels: frozenset[str]
    props: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)

    @property
    def is_stub(self) -> bool:
        return "Stub" in self.labels


@dataclass(frozen=True, slots=True)
class Edge:
    source: str
    type: str
    target: str
    props: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)

    @property
    def id(self) -> str:
        """Identity is (source, type, target, locator): the same pair linked from two places is two edges."""
        locator = str(self.props.get("locator", ""))
        return hashlib.sha256(f"{self.source}\0{self.type}\0{self.target}\0{locator}".encode()).hexdigest()[:32]


class Graph:
    def __init__(self, nodes: Iterable[Node] = (), edges: Iterable[Edge] = ()):
        self.nodes: dict[str, Node] = {}
        self._edges: dict[str, Edge] = {}
        for node in nodes:
            self.add_node(node)
        for edge in edges:
            self.add_edge(edge)

    def add_node(self, node: Node) -> None:
        unknown = node.labels - NODE_LABELS
        if unknown:
            raise ValueError(f"unknown node labels {sorted(unknown)}")
        existing = self.nodes.get(node.id)
        if existing is None or existing.is_stub:
            self.nodes[node.id] = node
        elif not node.is_stub:
            self.nodes[node.id] = Node(node.id, existing.labels | node.labels, {**existing.props, **node.props})

    def add_label(self, node_id: str, label: str) -> None:
        node = self.nodes[node_id]
        self.nodes[node_id] = Node(node.id, node.labels | {label}, node.props)

    def add_edge(self, edge: Edge) -> None:
        if edge.type not in EDGE_TYPES:
            raise ValueError(f"unknown edge type {edge.type}")
        self._edges.setdefault(edge.id, edge)

    def edges(self, type: str | None = None) -> list[Edge]:
        return [e for e in self._edges.values() if type is None or e.type == type]

    def labelled(self, label: str) -> list[Node]:
        return [n for n in self.nodes.values() if label in n.labels]
