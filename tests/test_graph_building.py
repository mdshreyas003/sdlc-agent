"""Seam 1: graph building. Fixture history + recorded extraction responses in, graph contents out."""

from __future__ import annotations

from whycode.fixtures import fixture_graph
from whycode.quotes import is_verbatim

BACKOFF_QUOTE = (
    "We chose a capped exponential backoff rather than a fixed retry interval because a fixed interval either "
    "retries too aggressively during long outages or too slowly after short ones."
)
VALIDATION_QUOTE = (
    "Descriptor validation errors cannot be fixed by retrying, so the schema changer should stop retrying and "
    "fail the job instead of spinning until the backoff cap."
)


def test_decisions_exist_only_when_their_quote_is_verbatim_in_their_source(empty_store):
    empty_store.replace(fixture_graph())
    graph = empty_store.snapshot()

    quotes = {d.props["quote"] for d in graph.labelled("Decision")}
    assert BACKOFF_QUOTE in quotes
    assert "We picked exponential backoff since fixed intervals are bad." not in quotes
    assert "Schema changes always run synchronously inside the issuing transaction." not in quotes

    # A real quote proposed for the wrong Discussion is rejected: only #101200 yields it.
    yielders = {e.source for e in graph.edges("YIELDS") if graph.nodes[e.target].props["quote"] == VALIDATION_QUOTE}
    assert yielders == {"pr:101200"}


BACKFILL_QUOTE = (
    "The backfill is run by `SchemaChanger.runBackfill` once all nodes have seen the write-only state, so that no "
    "node can write a row the backfill misses."
)
ROLLOUT_QUOTE = (
    "The declarative schema changer is gated by the `sql.defaults.use_declarative_schema_changer` cluster setting "
    "so that it can be enabled statement by statement and disabled in production if a bug is found, without a "
    "binary change."
)
SANITY_QUOTE = (
    "The schema changer plan sanity check walks every stage of the plan and is too expensive to run on every "
    "statement in production."
)
ISSUE_QUOTE = (
    "We should back off exponentially between retries instead of retrying immediately; a constant delay would "
    "still hammer the cluster during a long outage."
)


def decision_quoting(graph, quote):
    (decision,) = [d for d in graph.labelled("Decision") if d.props["quote"] == quote]
    return decision.id


def governed(graph, decision, link):
    return {e.target for e in graph.edges("GOVERNS") if e.source == decision and e.props["link"] == link}


def test_hard_links_follow_the_implementing_diff_and_soft_links_follow_names_in_the_text(empty_store):
    empty_store.replace(fixture_graph())
    graph = empty_store.snapshot()

    backoff = decision_quoting(graph, BACKOFF_QUOTE)
    # #98100's diff adds the setting and edits exec; it only calls isPermanentSchemaChangeError.
    assert governed(graph, backoff, "hard") == {
        "file:pkg/sql/schema_changer.go",
        "function:pkg/sql.(*SchemaChanger).exec",
        "setting:schemachanger.job.max_retry_backoff",
    }
    assert governed(graph, backoff, "soft") == {"setting:schemachanger.job.max_retry_backoff"}

    # A Decision stated in an issue thread is implemented by the Change that closes the issue (#98100 fixes #98001),
    # and dates from the comment that states it.
    issue_decision = decision_quoting(graph, ISSUE_QUOTE)
    assert governed(graph, issue_decision, "hard") == governed(graph, backoff, "hard")
    assert graph.nodes[issue_decision].props["date"] == "2023-03-03"

    sanity = decision_quoting(graph, SANITY_QUOTE)
    assert governed(graph, sanity, "hard") == {
        "file:pkg/sql/schemachanger/scrun/scrun.go",
        "function:pkg/sql/schemachanger/scrun.makeState",
        "setting:sql.schemachanger.strict_planning_sanity_check.enabled",
    }

    # RFCs implement nothing themselves: only names written in the quoted section link.
    backfill = decision_quoting(graph, BACKFILL_QUOTE)
    assert governed(graph, backfill, "hard") == set()
    assert governed(graph, backfill, "soft") == {"function:pkg/sql.(*SchemaChanger).runBackfill"}
    rollout = decision_quoting(graph, ROLLOUT_QUOTE)
    assert governed(graph, rollout, "soft") == {"setting:sql.defaults.use_declarative_schema_changer"}

    # #122400 touches scbuild.Build but yields no Decision, so nothing governs it.
    assert not [e for e in graph.edges("GOVERNS") if e.target == "function:pkg/sql/schemachanger/scbuild.Build"]


def test_derived_nodes_and_edges_are_tagged_derived_and_rest_on_a_quote(empty_store):
    empty_store.replace(fixture_graph())
    graph = empty_store.snapshot()

    assert graph.labelled("Decision")
    for node in graph.nodes.values():
        assert node.props["origin"] == ("derived" if "Decision" in node.labels else "stated"), node.id
        if "Decision" in node.labels:
            assert node.props["quote"]
    assert {e.props["basis"] for e in graph.edges("REFINES")} == {"inferred"}
    for edge in graph.edges():
        inferred = edge.props.get("basis") == "inferred"  # Supersession judged by the model
        assert edge.props["origin"] == ("derived" if edge.type in {"YIELDS", "GOVERNS"} or inferred else "stated"), edge
        assert edge.props["locator"] and edge.props["observed_at"], edge
        if edge.type in ("SUPERSEDES", "REFINES"):  # explicit or inferred, it rests on a quote in its source record
            assert is_verbatim(edge.props["quote"], graph.nodes[edge.props["source"]].props["text"]), edge
        elif edge.props["origin"] == "derived":
            assert edge.props["quote"] == graph.nodes[edge.target if edge.type == "YIELDS" else edge.source].props["quote"]


def test_a_rebuild_leaves_node_and_edge_counts_unchanged(empty_store):
    empty_store.replace(fixture_graph())
    first = empty_store.snapshot()
    empty_store.replace(fixture_graph())
    second = empty_store.snapshot()

    assert len(second.nodes) == len(first.nodes)
    assert len(second.edges()) == len(first.edges())
    assert set(second.nodes) == set(first.nodes)
    assert {e.id for e in second.edges()} == {e.id for e in first.edges()}


AFTER_CUTOFF = {
    "pr:127200",  # PR merged 2024-07-15
    "issue:127000",  # issue opened 2024-07-02
    "rfc:20240715_schema_change_retry_policy",
}


def test_nothing_after_the_cutoff_date_is_ingested(empty_store):
    empty_store.replace(fixture_graph())
    graph = empty_store.snapshot()

    assert not AFTER_CUTOFF & set(graph.nodes)
    texts = " ".join(str(n.props.get("text", "")) for n in graph.nodes.values())
    assert "must never be ingested" not in texts
    assert "Seeing the tight retry loop again" not in texts  # a 2024-08-01 comment on a pre-cutoff issue
    assert all(e.props["observed_at"] <= "2024-06-30" for e in graph.edges())
    assert graph.nodes["issue:98001"].props.get("closed_at")  # closed before the cutoff


def test_rebuilding_with_an_earlier_cutoff_removes_what_is_now_after_it(empty_store):
    import datetime as dt

    empty_store.replace(fixture_graph())
    empty_store.replace(fixture_graph(cutoff=dt.date(2023, 4, 30)))
    graph = empty_store.snapshot()

    assert "pr:98100" in graph.nodes  # merged 2023-03-20
    assert "pr:101200" not in graph.nodes  # merged 2023-05-02
    assert BACKOFF_QUOTE in {d.props["quote"] for d in graph.labelled("Decision")}
    assert SANITY_QUOTE not in {d.props["quote"] for d in graph.labelled("Decision")}


def pr(number):
    return f"pr:{number}"


def issue(number):
    return f"issue:{number}"


def links(graph, edge_type):
    return {(e.source, e.target) for e in graph.edges(edge_type)}


def test_stated_links_come_from_structure_and_identifiers_written_in_text(empty_store):
    empty_store.replace(fixture_graph())
    graph = empty_store.snapshot()

    # "Fixes #N" in a pull request closes the issue.
    assert (pr(98100), issue(98001)) in links(graph, "CLOSES")
    assert (pr(101450), issue(101400)) in links(graph, "CLOSES")

    # A revert names the reverted commit by full SHA (a commit #101200 contains) and repeats its title exactly.
    reverted = "commit:3f6c1e2a9b8d7c6e5f4a3b2c1d0e9f8a7b6c5d4e"
    assert (pr(101450), reverted) in links(graph, "REVERTS")
    assert (pr(101200), reverted) in links(graph, "CONTAINS")
    assert (pr(101450), pr(101200)) in links(graph, "REVERTS")

    # Other written identifiers are references; targets never ingested are stubs.
    assert (pr(98100), issue(97000)) in links(graph, "REFERENCES")  # "Informs #97000"
    assert graph.nodes[issue(97000)].is_stub
    assert (issue(101400), pr(101200)) in links(graph, "REFERENCES")  # "See #101200" in an issue comment
    assert ("rfc:20151014_online_schema_change", pr(2842)) in links(graph, "REFERENCES")  # RFC PR header
    assert ("rfc:20151014_online_schema_change", issue(2036)) in links(graph, "REFERENCES")  # Cockroach Issue header
    assert (pr(110500), "rfc:20210115_new_schema_changer") in links(graph, "REFERENCES")  # path to an RFC file
    assert not [e for e in graph.edges() if "CRDB" in e.target]  # "Epic: CRDB-12345" is a Jira key

    # Code structure.
    assert ("package:pkg/sql", "file:pkg/sql/schema_changer.go") in links(graph, "CONTAINS")
    assert ("file:pkg/sql/schema_changer.go", "function:pkg/sql.(*SchemaChanger).exec") in links(graph, "CONTAINS")
    assert ("file:pkg/sql/schema_changer.go", "setting:schemachanger.job.max_retry_backoff") in links(graph, "CONTAINS")

    # Incidents: bug, regression or release-blocker issues that a Change closes.
    assert {n.id for n in graph.labelled("Incident")} == {issue(98001), issue(101400)}


def test_people_link_to_what_they_authored_and_approved_and_are_flagged_when_departed(empty_store):
    empty_store.replace(fixture_graph())
    graph = empty_store.snapshot()

    assert ("person:fqazi", pr(98100)) in links(graph, "AUTHORED")
    assert ("person:vivekmenezes", "rfc:20151014_online_schema_change") in links(graph, "AUTHORED")
    approved = {(e.source, e.target) for e in graph.edges("REVIEWED") if e.props["state"] == "APPROVED"}
    assert ("person:rafiss", pr(98100)) in approved
    assert ("person:spilchen", pr(98100)) not in approved  # commented, never approved

    # Inactive for 12 months or more at the cutoff means departed.
    active = {n.id: n.props["active"] for n in graph.labelled("Person")}
    assert active["person:postamar"] is False  # last seen 2023-06-01
    assert active["person:ajwerner"] is False
    assert active["person:fqazi"] is True
    assert active["person:annrpom"] is True
    assert not [p for p in active if p.endswith("[bot]")]
