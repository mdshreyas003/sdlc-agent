"""What the Supersession detector knows about the graph's Decisions and records, and the shape of its edges."""

from __future__ import annotations

from collections import defaultdict
from typing import Final

from whycode.contract import SupersessionOrigin
from whycode.graph import DERIVED, STATED, Edge, Graph

EXPLICIT: Final[SupersessionOrigin] = "explicit"
INFERRED: Final[SupersessionOrigin] = "inferred"


class DecisionIndex:
    """What the detector needs to know about the Decisions and records already in the graph."""

    def __init__(self, graph: Graph):
        self.graph = graph
        self.decisions = {d.id: d for d in graph.labelled("Decision")}
        self.of_record: dict[str, list[str]] = defaultdict(list)
        for e in graph.edges("YIELDS"):
            self.of_record[e.source].append(e.target)
        self.governs_any: dict[str, set[str]] = defaultdict(set)  # Decision -> every Code Entity it governs
        self.governs: dict[str, set[str]] = defaultdict(set)  # the same without packages (too wide to share)
        for e in graph.edges("GOVERNS"):
            self.governs_any[e.source].add(e.target)
            if "Package" not in graph.nodes[e.target].labels:
                self.governs[e.source].add(e.target)
        self.pr_of_commit = {e.target: e.source for e in graph.edges("CONTAINS")
                             if "Commit" in graph.nodes[e.target].labels and self.is_pr(e.source)}

    def is_pr(self, node_id: str) -> bool:
        node = self.graph.nodes.get(node_id)
        return node is not None and "PullRequest" in node.labels

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


def supersession_edge(source: str, target: str, *, quote: str, record: str, locator: str, at: str, via: str,
          type_: str = "SUPERSEDES", basis: SupersessionOrigin = EXPLICIT, **props) -> Edge:
    """A SUPERSEDES or REFINES edge from the later node to the earlier Decision (module docstring of
    `whycode.supersession`)."""
    return Edge(source, type_, target, {
        "origin": STATED if basis == EXPLICIT else DERIVED, "basis": basis, "quote": quote, "source": record,
        "locator": locator, "observed_at": at, "via": via, **props,
    })
