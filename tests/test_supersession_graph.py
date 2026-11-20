"""Seam 1, Supersession: fixture history + recorded extractions + scripted judge in, SUPERSEDES / REFINES edges out."""

from __future__ import annotations

from whycode.fixtures import fixture_graph

VALIDATION_QUOTE = (
    "Descriptor validation errors cannot be fixed by retrying, so the schema changer should stop retrying and "
    "fail the job instead of spinning until the backoff cap."
)
KEEP_RETRYING_QUOTE = (
    "During upgrades, descriptors can fail validation transiently while the cluster version gate is being crossed, "
    "so treating validation errors as permanent failed jobs that would have succeeded on retry."
)


def decision_quoting(graph, quote):
    (decision,) = [d for d in graph.labelled("Decision") if d.props["quote"] == quote]
    return decision.id


def relations(graph, edge_type):
    return {(e.source, e.target): e for e in graph.edges(edge_type)}


def test_a_revert_makes_the_reverting_decision_supersede_the_reverted_one_explicitly(empty_store):
    empty_store.replace(fixture_graph())
    graph = empty_store.snapshot()

    reverted, reverting = decision_quoting(graph, VALIDATION_QUOTE), decision_quoting(graph, KEEP_RETRYING_QUOTE)
    edge = relations(graph, "SUPERSEDES")[(reverting, reverted)]
    assert edge.props["basis"] == "explicit"
    assert edge.props["origin"] == "stated"
    assert edge.props["observed_at"] == "2023-05-10"  # #101450 merged
    assert edge.props["source"] == "pr:101450"
    assert edge.props["quote"] in graph.nodes["pr:101450"].props["text"]


CHILD_TXN_QUOTE = (
    "`scrun.RunStatementPhase` runs each schema change statement in a child transaction that commits before the "
    "user's transaction, so a failed backfill never rolls back the user's other writes."
)
STATEMENT_PHASE_QUOTE = (
    "`scrun.RunStatementPhase` executes the statement phase inside the user's transaction so that later statements "
    "in the same transaction observe the change."
)


def test_an_rfc_whose_status_says_superseded_is_superseded_by_the_rfc_that_replaced_it(empty_store):
    empty_store.replace(fixture_graph())
    graph = empty_store.snapshot()

    old = decision_quoting(graph, CHILD_TXN_QUOTE)
    new = decision_quoting(graph, STATEMENT_PHASE_QUOTE)
    by = {source: e for (source, target), e in relations(graph, "SUPERSEDES").items() if target == old}
    # The new RFC's Decision on the same function, and the old RFC's own Status header.
    assert set(by) == {new, "rfc:20200909_transactional_schema_changes"}
    for edge in by.values():
        assert edge.props["basis"] == "explicit"
        assert edge.props["quote"] == "superseded by #59288"
        assert edge.props["source"] == "rfc:20200909_transactional_schema_changes"
        assert edge.props["observed_at"] == "2021-01-15"  # when the superseding RFC was written
    # Decisions of RFCs with a live status are untouched.
    assert not [e for e in graph.edges("SUPERSEDES") if graph.nodes[e.target].props["discussion_id"]
                in ("rfc:20151014_online_schema_change", "rfc:20210115_new_schema_changer")]


SANITY_QUOTE = (
    "The schema changer plan sanity check walks every stage of the plan and is too expensive to run on every "
    "statement in production."
)
ALWAYS_ON_QUOTE = (
    "Running the plan sanity check on every statement costs less than one percent of planning time since the "
    "planner rewrite, so it is always enabled again."
)
REJECTED_RFC = """- Feature Name: Asynchronous schema change statements
- Status: rejected
- Start Date: 2019-03-01
- Authors: Vivek Menezes
- RFC PR: #35000

# Detailed design

`SchemaChanger.exec` returns to the client as soon as the job is queued, and the
client polls SHOW JOBS to learn when the schema change finished.
"""
ASYNC_QUOTE = "`SchemaChanger.exec` returns to the client as soon as the job is queued"


def extended_fixture(tmp_path):
    """The fixture history plus a PR that says "Supersedes #110500" and a rejected RFC."""
    import json
    import shutil

    from whycode.build import build_graph
    from whycode.decisions import RecordedDecisionProposer
    from whycode.fixtures import FIXTURE_CUTOFF, FIXTURE_DIR, FIXTURE_REPO, fixture_code_index
    from whycode.history import load_history
    from whycode.history.fixture import FixtureHistorySource

    root = tmp_path / "fixture"
    shutil.copytree(FIXTURE_DIR, root)
    pull = json.loads((root / "pulls" / "110500.json").read_text())
    pull["pull"] |= {
        "number": 116000, "title": "scrun: always run the strict planning sanity check",
        "body": f"Supersedes #110500. {ALWAYS_ON_QUOTE}\n\nRelease note: None", "user": {"login": "annrpom"},
        "html_url": "https://github.com/cockroachdb/cockroach/pull/116000",
        "created_at": "2024-01-08T10:00:00Z", "merged_at": "2024-01-10T10:00:00Z",
    }
    pull["commits"][0]["sha"] = "a1" * 20
    pull["reviews"] = []
    (root / "pulls" / "116000.json").write_text(json.dumps(pull))
    (root / "rfcs" / "20190301_async_schema_changes.md").write_text(REJECTED_RFC)
    extractions = json.loads((root / "extractions.json").read_text())
    extractions["pr:116000"] = [{"choice": "Always run the plan sanity check", "rationale": "It is cheap now.",
                                 "quote": ALWAYS_ON_QUOTE}]
    extractions["rfc:20190301_async_schema_changes"] = [
        {"choice": "Return from SchemaChanger.exec once the job is queued", "rationale": "Clients poll.",
         "quote": ASYNC_QUOTE}]
    (root / "extractions.json").write_text(json.dumps(extractions))
    history = load_history(FixtureHistorySource(root, repo=FIXTURE_REPO), FIXTURE_CUTOFF)
    return build_graph(history, fixture_code_index(), RecordedDecisionProposer(root / "extractions.json"))


def test_supersedes_written_in_a_pull_request_and_a_rejected_rfc_are_explicit_supersessions(empty_store, tmp_path):
    empty_store.replace(extended_fixture(tmp_path))
    graph = empty_store.snapshot()

    sanity, always_on = decision_quoting(graph, SANITY_QUOTE), decision_quoting(graph, ALWAYS_ON_QUOTE)
    edge = relations(graph, "SUPERSEDES")[(always_on, sanity)]
    assert (edge.props["basis"], edge.props["quote"], edge.props["source"]) == ("explicit", "Supersedes #110500",
                                                                                 "pr:116000")
    assert edge.props["observed_at"] == "2024-01-10"

    rejected = decision_quoting(graph, ASYNC_QUOTE)
    (by,) = [e for e in graph.edges("SUPERSEDES") if e.target == rejected]
    assert (by.source, by.props["quote"], by.props["basis"]) == ("rfc:20190301_async_schema_changes", "rejected",
                                                                 "explicit")


TWENTY_SECONDS_QUOTE = "Capping the backoff at 20 seconds keeps a stuck job visible in SHOW JOBS without hammering the cluster."
TEN_SECONDS_QUOTE = "Lower the default cap to 10s because 20s left stuck jobs waiting too long after short outages."
FINALIZED_QUOTE = (
    "This treats descriptor validation errors as permanent again once the cluster version is finalized; until then "
    "the schema changer keeps retrying them"
)
BACKOFF_QUOTE = (
    "We chose a capped exponential backoff rather than a fixed retry interval because a fixed interval either "
    "retries too aggressively during long outages or too slowly after short ones."
)


def window_graph(judge):
    from whycode.fixtures import FIXTURE_WINDOW_END

    return fixture_graph(cutoff=FIXTURE_WINDOW_END, judge=judge)


def test_the_judges_labels_become_supersedes_and_refines_edges_tagged_derived(empty_store):
    from doubles import ScriptedJudge

    judge = ScriptedJudge({
        (TWENTY_SECONDS_QUOTE, TEN_SECONDS_QUOTE): ("supersedes", "Lower the default cap to 10s"),
        (KEEP_RETRYING_QUOTE, FINALIZED_QUOTE): ("refines", "until then the schema changer keeps retrying them"),
        # Asked only if the judge sees a pair it should not: already linked by the revert.
        (VALIDATION_QUOTE, KEEP_RETRYING_QUOTE): ("refines", "treating validation errors as permanent failed jobs"),
    })
    empty_store.replace(window_graph(judge))
    graph = empty_store.snapshot()

    twenty, ten = decision_quoting(graph, TWENTY_SECONDS_QUOTE), decision_quoting(graph, TEN_SECONDS_QUOTE)
    keep, finalized = decision_quoting(graph, KEEP_RETRYING_QUOTE), decision_quoting(graph, FINALIZED_QUOTE)
    supersedes, refines = relations(graph, "SUPERSEDES"), relations(graph, "REFINES")

    edge = supersedes[(ten, twenty)]
    assert (edge.props["origin"], edge.props["basis"]) == ("derived", "inferred")
    assert (edge.props["quote"], edge.props["source"]) == ("Lower the default cap to 10s", "pr:127200")
    assert edge.props["observed_at"] == "2024-07-15"
    edge = refines[(finalized, keep)]
    assert (edge.props["origin"], edge.props["basis"], edge.props["source"]) == ("derived", "inferred", "pr:104500")
    # "unrelated" makes no edge, and a pair already explicitly linked is not judged again.
    backoff = decision_quoting(graph, BACKOFF_QUOTE)
    assert (ten, backoff) not in supersedes and (ten, backoff) not in refines
    validation = decision_quoting(graph, VALIDATION_QUOTE)
    assert (keep, validation) not in refines and supersedes[(keep, validation)].props["basis"] == "explicit"


def test_a_judgment_whose_quote_is_not_verbatim_in_the_later_discussion_makes_no_edge(empty_store):
    from doubles import ScriptedJudge

    judge = ScriptedJudge({(TWENTY_SECONDS_QUOTE, TEN_SECONDS_QUOTE): ("supersedes", "The 20s default was a mistake")})
    empty_store.replace(window_graph(judge))
    graph = empty_store.snapshot()

    twenty = decision_quoting(graph, TWENTY_SECONDS_QUOTE)
    assert not [e for e in graph.edges() if e.type in ("SUPERSEDES", "REFINES") and e.target == twenty]


def test_a_revert_that_records_no_decision_makes_the_reverting_change_the_superseding_node(empty_store):
    from whycode.fixtures import FIXTURE_WINDOW_END

    empty_store.replace(fixture_graph(cutoff=FIXTURE_WINDOW_END))  # #128000 reverts #104500 in the window
    graph = empty_store.snapshot()

    finalized = decision_quoting(graph, FINALIZED_QUOTE)
    (edge,) = [e for e in graph.edges("SUPERSEDES") if e.target == finalized]
    assert (edge.source, edge.props["basis"], edge.props["observed_at"]) == ("pr:128000", "explicit", "2024-08-05")
