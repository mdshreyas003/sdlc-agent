"""Export the graph's citable history records in the scoreboard's corpus format (eval/README.md, "Corpus format").

Ids and texts come straight from the graph, so every node id `why` cites resolves in the corpus and every quote
is checked against the same text the answer verifier used. Ticket 02 writes the real slice's corpus with
`write_jsonl(path, corpus_records(graph))` (`whycode.eval.corpus.write_jsonl`).
"""

from __future__ import annotations

from collections import defaultdict

from whycode.eval.corpus import CorpusRecord
from whycode.graph import Graph, day

CITABLE_KINDS = frozenset({"rfc", "pr", "issue", "commit"})


def corpus_records(graph: Graph) -> list[CorpusRecord]:
    paths: dict[str, list[str]] = defaultdict(list)
    commits: dict[str, list[str]] = defaultdict(list)
    merged: dict[str, str] = {}  # commit id -> date of the pull request that merged it
    for edge in graph.edges("TOUCHES"):
        if "File" in graph.nodes[edge.target].labels:
            paths[edge.source].append(graph.nodes[edge.target].props["key"])
    for edge in graph.edges("CONTAINS"):
        if "Commit" in graph.nodes[edge.target].labels:
            commits[edge.source].append(graph.nodes[edge.target].props["sha"])
            merged[edge.target] = graph.nodes[edge.source].props["date"]
    out = []
    for node in sorted(graph.nodes.values(), key=lambda n: n.id):
        props = node.props
        if node.is_stub or props.get("kind") not in CITABLE_KINDS:
            continue
        date = merged.get(node.id) or props.get("date")
        out.append(CorpusRecord(
            id=node.id, kind=props["kind"], title=props.get("title") or "", text=props.get("text") or "",
            url=props.get("url"), date=day(date),
            number=props.get("number"), labels=list(props.get("github_labels") or []),
            paths=sorted(paths[node.id]) or ([props["path"]] if props.get("path") else []),
            commits=sorted(commits[node.id]),
        ))
    return out
