"""Ingesting the slice from GitHub: a fake GitHub serving the miniature history (plus records the slice must
leave out) through the real client, cache and source; assertions on the graph built from what was ingested."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from fake_github import miniature_checkout, miniature_github

from whycode.build import build_graph
from whycode.codeindex.go import parse_go_tree
from whycode.decisions import NoDecisionProposer
from whycode.history import load_history
from whycode.history.github import CachedTransport, GitHubClient, GitHubHistorySource
from whycode.history.scope import Scope

CUTOFF = dt.date(2024, 6, 30)
TOKEN = "ghp_test-token-never-stored"
SCOPE = Scope(
    repo="cockroachdb/cockroach",
    cutoff_commit="0" * 40,
    pr_paths=("pkg/sql/schemachanger", "pkg/sql/schema_changer.go"),
    code_paths=("pkg/sql",),
    rfc_dir="docs/RFCS",
    rfc_stems=("20151014_online_schema_change", "20210115_new_schema_changer", "20240715_schema_change_retry_policy"),
    issue_labels=("A-schema-changes", "A-schema-descriptors"),
)


@pytest.fixture
def checkout(tmp_path) -> Path:
    return miniature_checkout(tmp_path / "checkout")


def ingest(transport, checkout: Path, limit: int | None = None, sleep=lambda s: None, clock=None):
    client = GitHubClient(transport, token=TOKEN, sleep=sleep, clock=clock or (lambda: 1_700_000_000.0))
    source = GitHubHistorySource(client, SCOPE, checkout, CUTOFF, limit=limit)
    history = load_history(source, CUTOFF)
    return build_graph(history, parse_go_tree(checkout, SCOPE.code_paths), NoDecisionProposer())


def real(graph, label):
    return {n.id for n in graph.labelled(label) if not n.is_stub}


def links(graph, edge_type):
    return {(e.source, e.target) for e in graph.edges(edge_type)}


def test_ingests_scoped_pull_requests_their_linked_issues_labelled_issues_and_rfcs_up_to_the_cutoff(
        tmp_path, checkout):
    graph = ingest(CachedTransport(miniature_github(), tmp_path / "cache"), checkout)

    # Pull requests merged into master by the cutoff that touch the scoped code; not backports, not others,
    # not the RFC pull requests, not #127200 or #128000 (merged after the cutoff).
    assert real(graph, "PullRequest") == {"pr:98100", "pr:101200", "pr:101450", "pr:104500", "pr:110500",
                                          "pr:122400"}
    # A-schema issues and issues the pull requests close; #127000 was opened after the cutoff; #97000 is a
    # pull request, so it stays a stub.
    assert real(graph, "Issue") == {"issue:98001", "issue:101400", "issue:99500"}
    assert graph.nodes["issue:97000"].is_stub
    assert real(graph, "Rfc") == {"rfc:20151014_online_schema_change", "rfc:20210115_new_schema_changer"}

    # RFC authors are the logins of their RFC pull requests.
    assert ("person:vivekmenezes", "rfc:20151014_online_schema_change") in links(graph, "AUTHORED")
    assert ("person:ajwerner", "rfc:20210115_new_schema_changer") in links(graph, "AUTHORED")
    # Every page of every paginated endpoint was read: the second review (the approval), the diff.
    approvals = {(e.source, e.target) for e in graph.edges("REVIEWED") if e.props["state"] == "APPROVED"}
    assert ("person:rafiss", "pr:98100") in approvals
    assert ("pr:98100", "function:pkg/sql.(*SchemaChanger).exec") in links(graph, "TOUCHES")
    assert ("pr:98100", "issue:98001") in links(graph, "CLOSES")
    assert "issue:98001" in real(graph, "Incident")

    texts = " ".join(str(n.props.get("text", "")) for n in graph.nodes.values())
    assert "Seeing the tight retry loop again" not in texts  # a 2024-08-01 comment
    assert all(e.props["observed_at"] <= "2024-06-30" for e in graph.edges())


def test_a_rerun_reads_the_local_cache_and_makes_no_github_calls(tmp_path, checkout):
    fake = miniature_github()
    first = ingest(CachedTransport(fake, tmp_path / "cache"), checkout)
    calls = len(fake.calls)

    again = ingest(CachedTransport(fake, tmp_path / "cache"), checkout)
    offline = ingest(CachedTransport(None, tmp_path / "cache"), checkout)  # no network at all

    assert calls > 0 and len(fake.calls) == calls
    for graph in (again, offline):
        assert set(graph.nodes) == set(first.nodes)
        assert {e.id for e in graph.edges()} == {e.id for e in first.edges()}


def test_waits_out_a_rate_limit_and_never_stores_the_token(tmp_path, checkout):
    fake = miniature_github()
    fake.rate_limit_next(1)
    slept: list[float] = []

    graph = ingest(CachedTransport(fake, tmp_path / "cache"), checkout, sleep=slept.append, clock=lambda: fake.now)

    assert "pr:98100" in real(graph, "PullRequest")
    assert sum(slept) >= 30  # until the reset time GitHub announced
    assert fake.calls[0].headers["Authorization"] == f"Bearer {TOKEN}"
    for path in (tmp_path / "cache").rglob("*"):
        if path.is_file():
            assert TOKEN not in path.read_text()


def test_a_limit_keeps_the_most_recent_pull_requests_and_labelled_issues(tmp_path, checkout):
    graph = ingest(CachedTransport(miniature_github(), tmp_path / "cache"), checkout, limit=1)

    assert real(graph, "PullRequest") == {"pr:122400"}  # merged 2024-04-10
    assert real(graph, "Issue") == {"issue:101400"}  # opened 2023-05-08
