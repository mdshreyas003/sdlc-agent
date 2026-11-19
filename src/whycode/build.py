"""Graph building: history + code index + a Decision proposer -> a `Graph` ready for `GraphStore.replace`.

    graph = build_graph(load_history(source, cutoff), parse_go_tree(checkout), proposer)

Pure apart from the proposer's model calls; the same inputs (and cached model responses) give the same graph.
Order matters only in one place: Stated Links are added before Decisions, because an issue's Decisions are
implemented by the Changes that close it (their diffs give the hard governs links).
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

from whycode import discussions as disc
from whycode import ids
from whycode.codeindex import CodeEntity, CodeIndex
from whycode.decisions import DecisionProposer, ExtractedDecision, extract_decisions
from whycode.graph import DERIVED, STATED, Edge, Graph, Node
from whycode.history.records import History
from whycode.history.rfc import normalize_status, parse_header
from whycode.linker import incident_labels, stated_links

DEPARTED_AFTER = dt.timedelta(days=365)
"""A Person with no activity in this long before the cutoff is shown as departed."""


def build_graph(history: History, code: CodeIndex, proposer: DecisionProposer) -> Graph:
    return _Builder(history, code).build(proposer)


def _discussion_node(d: disc.Discussion, node_labels: set[str], **props) -> Node:
    return Node(d.id, frozenset(node_labels), {
        "kind": d.kind, "title": d.title, "url": d.url, "date": d.date.isoformat(), "text": d.text,
        "origin": STATED, **props,
    })


class _Builder:
    def __init__(self, history: History, code: CodeIndex):
        self.history = history
        self.code = code
        self.graph = Graph()
        self.discussions: list[disc.Discussion] = []
        self.touches: dict[str, set[CodeEntity]] = defaultdict(set)  # Change id -> entities its diff touches
        self.implemented_by: dict[str, set[str]] = defaultdict(set)  # Discussion id -> implementing Change ids
        self.last_active: dict[str, dt.date] = {}

    def build(self, proposer: DecisionProposer) -> Graph:
        self._add_code()
        self._add_records()
        self._add_links()
        self._add_people()
        extractor = getattr(proposer, "name", type(proposer).__name__)
        for discussion in self.discussions:
            for decision in extract_decisions(discussion, proposer, self.code):
                self._add_decision(discussion, decision, extractor)
        self._add_stubs()
        return self.graph

    def _edge(self, source: str, type_: str, target: str, locator: str, at: dt.date, **props) -> None:
        self.graph.add_edge(Edge(source, type_, target, {
            "origin": STATED, "locator": locator, "observed_at": at.isoformat(), **props,
        }))

    def _seen(self, login: str | None, at: dt.date) -> None:
        if login:
            self.last_active[login] = max(at, self.last_active.get(login, at))

    def _add_code(self) -> None:
        for e in self.code.entities:
            self.graph.add_node(Node(e.id, frozenset({"CodeEntity", e.kind.capitalize()}), {
                "kind": e.kind, "key": e.key, "name": e.name, "aliases": list(e.aliases), "package": e.package,
                "file": e.file, "receiver": e.receiver, "go_var": e.go_var, "origin": STATED,
            }))
            if e.parent and (parent := self.code.get(e.parent)):
                self._edge(parent.id, "CONTAINS", e.id, "code", self.history.cutoff)

    def _add_records(self) -> None:
        repo = self.history.repo
        for rfc in self.history.rfcs:
            d = disc.from_rfc(rfc)
            status = parse_header(rfc.text).get("Status")
            self.graph.add_node(_discussion_node(
                d, {"Discussion", "Rfc"}, path=rfc.path, status_raw=status.value if status else None,
                status=normalize_status(status.value) if status else None,
            ))
            self.discussions.append(d)
            for author in rfc.authors:
                self._seen(author, rfc.date)
                self._edge(ids.person_id(author), "AUTHORED", d.id, "authors", rfc.date)

        for pr in self.history.pull_requests:
            d = disc.from_pull_request(pr)
            self.graph.add_node(_discussion_node(d, {"Change", "Discussion", "PullRequest"}, number=pr.number,
                                                 merged_at=pr.merged_at.isoformat(), base_ref=pr.base_ref))
            self.discussions.append(d)
            self.implemented_by[d.id].add(d.id)
            self._seen(pr.author, pr.merged_at.date())
            self._edge(ids.person_id(pr.author), "AUTHORED", d.id, "user", pr.created_at.date())
            for change in pr.files:
                for entity in sorted(self.code.touched_by(change), key=lambda e: e.id):
                    self.touches[d.id].add(entity)
                    self._edge(d.id, "TOUCHES", entity.id, f"files[{change.path}]", d.date)
            for commit in pr.commits:
                cid, at = ids.commit_id(commit.sha), (commit.at or pr.merged_at).date()
                self.graph.add_node(Node(cid, frozenset({"Change", "Commit"}), {
                    "kind": "commit", "sha": commit.sha, "title": commit.message.split("\n", 1)[0],
                    "text": commit.message, "url": ids.url_for(cid, repo), "date": at.isoformat(), "origin": STATED,
                }))
                self._edge(d.id, "CONTAINS", cid, f"commits[{commit.sha}]", d.date)
                if commit.author:
                    self._seen(commit.author, at)
                    self._edge(ids.person_id(commit.author), "AUTHORED", cid, "author", at)
            self._add_reviews(d.id, pr.posts)

        for issue in self.history.issues:
            d = disc.from_issue(issue)
            self.graph.add_node(_discussion_node(
                d, {"Discussion", "Issue"}, number=issue.number, github_labels=list(issue.labels),
                closed_at=issue.closed_at.isoformat() if issue.closed_at else None,
            ))
            self.discussions.append(d)
            self._seen(issue.author, issue.created_at.date())
            self._edge(ids.person_id(issue.author), "AUTHORED", d.id, "user", issue.created_at.date())
            for post in issue.posts:
                self._seen(post.author, post.at.date())

    def _add_reviews(self, pr_id: str, posts) -> None:
        verdicts: dict[str, tuple[str, dt.date]] = {}
        for post in posts:
            self._seen(post.author, post.at.date())
            if post.kind != "review":
                continue
            state = post.review_state or "COMMENTED"
            previous = verdicts.get(post.author)
            if state != "COMMENTED" or previous is None or previous[0] == "COMMENTED":
                verdicts[post.author] = (state, post.at.date())
        for login, (state, at) in sorted(verdicts.items()):
            self._edge(ids.person_id(login), "REVIEWED", pr_id, "reviews", at, state=state)

    def _add_links(self) -> None:
        for link in stated_links(self.history):
            self._edge(link.source, link.type, link.target, link.locator, link.observed_at)
        issues = {ids.issue_id(i.number): i for i in self.history.issues}
        for edge in self.graph.edges("CLOSES"):
            if edge.target in issues and "Change" in self.graph.nodes.get(edge.source, Node("", frozenset())).labels:
                self.implemented_by[edge.target].add(edge.source)
                if incident_labels(issues[edge.target].labels):
                    self.graph.add_label(edge.target, "Incident")

    def _add_people(self) -> None:
        for login, last in sorted(self.last_active.items()):
            pid = ids.person_id(login)
            self.graph.add_node(Node(pid, frozenset({"Person"}), {
                "kind": "person", "handle": login, "url": ids.url_for(pid, self.history.repo), "last_active_at": last.isoformat(),
                "active": self.history.cutoff - last < DEPARTED_AFTER, "origin": STATED,
            }))

    def _add_decision(self, discussion: disc.Discussion, decision: ExtractedDecision, extractor: str) -> None:
        when = decision.date.isoformat()
        self.graph.add_node(Node(decision.id, frozenset({"Decision"}), {
            "kind": "decision", "choice": decision.choice, "rationale": decision.rationale,
            "alternatives_rejected": list(decision.alternatives_rejected), "quote": decision.quote, "date": when,
            "discussion_id": discussion.id, "speaker": decision.speaker, "origin": DERIVED, "extractor": extractor,
        }))
        self.graph.add_edge(Edge(discussion.id, "YIELDS", decision.id, {
            "origin": DERIVED, "quote": decision.quote, "locator": decision.segment, "observed_at": when,
        }))
        for change_id in sorted(self.implemented_by[discussion.id]):
            for entity in self.touches[change_id]:
                self.graph.add_edge(Edge(decision.id, "GOVERNS", entity.id, {
                    "origin": DERIVED, "link": "hard", "quote": decision.quote, "locator": f"touches:{change_id}",
                    "observed_at": when,
                }))
        for entity in decision.mentions:
            self.graph.add_edge(Edge(decision.id, "GOVERNS", entity.id, {
                "origin": DERIVED, "link": "soft", "quote": decision.quote,
                "locator": f"mention:{decision.segment}", "observed_at": when,
            }))

    def _add_stubs(self) -> None:
        """Records that are referenced but were never ingested: kept as stubs, never cited."""
        for edge in self.graph.edges():
            for node_id in (edge.source, edge.target):
                if node_id not in self.graph.nodes:
                    self.graph.add_node(Node(node_id, frozenset({"Stub"}), {
                        "kind": "stub", "stub": True, "url": ids.url_for(node_id, self.history.repo), "origin": STATED,
                    }))
