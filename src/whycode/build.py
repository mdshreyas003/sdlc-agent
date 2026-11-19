"""Graph building: history + code index + a Decision proposer -> a `Graph` ready for `GraphStore.replace`.

    graph = build_graph(load_history(source, cutoff), parse_go_tree(checkout), proposer)

Pure apart from the proposer's model calls; the same inputs (and cached model responses) give the same graph.
"""

from __future__ import annotations

from whycode import discussions as disc
from whycode import ids
from whycode.codeindex import CodeIndex
from whycode.decisions import DecisionProposer, extract_decisions
from whycode.graph import DERIVED, STATED, Edge, Graph, Node
from whycode.history.records import History


def build_graph(history: History, code: CodeIndex, proposer: DecisionProposer) -> Graph:
    graph = Graph()
    _add_code(graph, code)
    discussions = _add_history(graph, history)
    for discussion in discussions:
        _add_decisions(graph, discussion, proposer, code)
    return graph


def _add_code(graph: Graph, code: CodeIndex) -> None:
    for entity in code.entities:
        graph.add_node(Node(entity.id, frozenset({"CodeEntity", entity.kind.capitalize()}), {
            "kind": entity.kind, "key": entity.key, "name": entity.name, "aliases": list(entity.aliases),
            "package": entity.package, "file": entity.file, "receiver": entity.receiver,
            "go_var": entity.go_var, "origin": STATED,
        }))


def _discussion_node(d: disc.Discussion, node_labels: set[str], **props) -> Node:
    return Node(d.id, frozenset(node_labels), {
        "kind": d.kind, "title": d.title, "url": d.url, "date": d.date.isoformat(), "text": d.text,
        "origin": STATED, **props,
    })


def _add_history(graph: Graph, history: History) -> list[disc.Discussion]:
    out = []
    for rfc in history.rfcs:
        d = disc.from_rfc(rfc)
        graph.add_node(_discussion_node(d, {"Discussion", "Rfc"}, path=rfc.path))
        out.append(d)
    for pr in history.pull_requests:
        d = disc.from_pull_request(history.repo, pr)
        graph.add_node(_discussion_node(d, {"Change", "Discussion", "PullRequest"}, number=pr.number,
                                        merged_at=pr.merged_at.isoformat(), base_ref=pr.base_ref))
        out.append(d)
    for issue in history.issues:
        d = disc.from_issue(history.repo, issue)
        graph.add_node(_discussion_node(d, {"Discussion", "Issue"}, number=issue.number,
                                        github_labels=list(issue.labels),
                                        closed_at=issue.closed_at.isoformat() if issue.closed_at else None))
        out.append(d)
    return out


def _add_decisions(graph: Graph, discussion: disc.Discussion, proposer: DecisionProposer, code: CodeIndex) -> None:
    for decision in extract_decisions(discussion, proposer, code):
        graph.add_node(Node(decision.id, frozenset({"Decision"}), {
            "kind": "decision", "choice": decision.choice, "rationale": decision.rationale,
            "alternatives_rejected": list(decision.alternatives_rejected), "quote": decision.quote,
            "date": decision.date.isoformat(), "discussion_id": discussion.id, "speaker": decision.speaker,
            "origin": DERIVED, "extractor": getattr(proposer, "name", type(proposer).__name__),
        }))
        graph.add_edge(Edge(discussion.id, "YIELDS", decision.id, {
            "origin": DERIVED, "quote": decision.quote, "locator": decision.segment,
            "observed_at": decision.date.isoformat(),
        }))
