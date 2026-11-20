"""Seam 2, Supersession: `why` over the fixture graph (recorded extractions and judgments), scripted composers.
Assertions are on the Answer contract only."""

from __future__ import annotations

import datetime as dt

import pytest
from doubles import FaithfulComposer, StaleComposer
from mcp import Client

from whycode.answer.engine import AnswerEngine
from whycode.answer.patterns import GraphReader
from whycode.contract import Answer
from whycode.fixtures import fixture_graph
from whycode.graph.store import GraphStore
from whycode.mcp_server import build_server

pytestmark = pytest.mark.anyio

PERMANENT = "pkg/sql.isPermanentSchemaChangeError"
VALIDATION_QUOTE = (
    "Descriptor validation errors cannot be fixed by retrying, so the schema changer should stop retrying and "
    "fail the job instead of spinning until the backoff cap."
)
KEEP_RETRYING_QUOTE = (
    "During upgrades, descriptors can fail validation transiently while the cluster version gate is being crossed, "
    "so treating validation errors as permanent failed jobs that would have succeeded on retry."
)
FINALIZED_QUOTE = (
    "This treats descriptor validation errors as permanent again once the cluster version is finalized; until then "
    "the schema changer keeps retrying them"
)
CHILD_TXN_QUOTE = (
    "`scrun.RunStatementPhase` runs each schema change statement in a child transaction that commits before the "
    "user's transaction, so a failed backfill never rolls back the user's other writes."
)
STATEMENT_PHASE_QUOTE = (
    "`scrun.RunStatementPhase` executes the statement phase inside the user's transaction so that later statements "
    "in the same transaction observe the change."
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def reader(neo4j_driver):
    neo4j_driver.execute_query("MATCH (n) DETACH DELETE n")
    GraphStore(neo4j_driver).replace(fixture_graph())
    reader = GraphReader(neo4j_driver)
    reader.selfcheck()
    return reader


async def ask(reader, anchor, composer=None) -> Answer:
    async with Client(build_server(AnswerEngine(reader, composer or FaithfulComposer()))) as client:
        result = await client.call_tool("why", {"anchor": anchor})
    assert result.is_error is False, result.content
    return Answer.model_validate(result.structured_content)


def by_quote(answer: Answer):
    return {d.quote: d for d in answer.decisions}


async def test_a_reverted_decision_is_superseded_explicitly_by_the_revert_and_says_when(reader):
    answer = await ask(reader, PERMANENT)

    decisions = by_quote(answer)
    reverted, revert = decisions[VALIDATION_QUOTE], decisions[KEEP_RETRYING_QUOTE]
    assert reverted.status == "superseded"
    assert reverted.superseded_by == revert.id
    assert reverted.superseded_at == dt.date(2023, 5, 10)  # #101450 merged
    assert reverted.explicit_or_inferred == "explicit"
    assert reverted.supersession_source == "pr:101450"
    evidence = {e.node_id for e in answer.evidence_chain}
    assert {reverted.superseded_by, reverted.supersession_source} <= evidence
    assert decisions[FINALIZED_QUOTE].status == "live"


async def test_a_refinement_is_shown_as_partly_live_and_an_inferred_one_lowers_confidence(reader):
    answer = await ask(reader, PERMANENT)

    decisions = by_quote(answer)
    refined, refining = decisions[KEEP_RETRYING_QUOTE], decisions[FINALIZED_QUOTE]
    assert refined.status == "refined"
    assert refined.superseded_by == refining.id
    assert refined.explicit_or_inferred == "inferred"
    assert refined.superseded_at == dt.date(2023, 6, 20)
    assert refined.supersession_quote in FINALIZED_QUOTE  # the judge's justification, verbatim in #104500
    assert refined.supersession_source == "pr:104500"
    # The strongest Decision is a reviewed PR's hard link (High alone), but part of the picture is model judgment.
    assert answer.confidence == "Medium"


async def test_a_superseded_decision_is_never_presented_as_live(reader):
    faithful = await ask(reader, PERMANENT)
    stale = await ask(reader, PERMANENT, StaleComposer())

    reverted = by_quote(stale)[VALIDATION_QUOTE]
    assert reverted.status == "superseded"
    assert not [d for d in stale.decisions if d.status == "live" and d.quote == VALIDATION_QUOTE]
    # A sentence that cites the dead Decision without what superseded it does not survive.
    for sentence in stale.sentences:
        if reverted.id in sentence.cites:
            assert reverted.superseded_by in sentence.cites
    assert StaleComposer.PRESENTS_AS_LIVE not in [s.text for s in stale.sentences]
    assert len(stale.sentences) == len(faithful.sentences)
    assert (faithful.confidence, stale.confidence) == ("Medium", "Low")


async def test_an_rfc_superseded_by_a_later_rfc_is_labelled_superseded_by_its_decision(reader):
    answer = await ask(reader, "scrun.RunStatementPhase")

    decisions = by_quote(answer)
    old, new = decisions[CHILD_TXN_QUOTE], decisions[STATEMENT_PHASE_QUOTE]
    assert (old.status, old.superseded_by, old.explicit_or_inferred) == ("superseded", new.id, "explicit")
    assert old.supersession_quote == "superseded by #59288"
    assert old.superseded_at == dt.date(2021, 1, 15)
    assert new.status == "live"


async def test_the_offline_template_composer_states_the_supersession_history(reader):
    from whycode.answer.compose import TemplateComposer

    answer = await ask(reader, PERMANENT, TemplateComposer())

    assert len(answer.sentences) == len(answer.decisions)  # nothing dropped
    reverted = by_quote(answer)[VALIDATION_QUOTE]
    (sentence,) = [s for s in answer.sentences if s.cites[0] == reverted.id]
    assert "Superseded on 2023-05-10" in sentence.text and reverted.superseded_by in sentence.cites
    refined = by_quote(answer)[KEEP_RETRYING_QUOTE]
    (sentence,) = [s for s in answer.sentences if s.cites[0] == refined.id]
    assert "Refined on 2023-06-20" in sentence.text
