"""Seam 2: the `why` MCP tool over the fixture graph, with scripted composers. Assertions are on the Answer
contract only."""

from __future__ import annotations

import os
import sys

import pytest
from doubles import (
    DROPPED_SENTENCES,
    FABRICATED_ID,
    INVENTED_URL,
    FabricatingComposer,
    FaithfulComposer,
    OnlyFabricationsComposer,
)
from mcp import Client, StdioServerParameters

from whycode.answer.engine import AnswerEngine
from whycode.answer.patterns import GraphReader
from whycode.contract import Answer
from whycode.eval.corpus import MemoryCorpus
from whycode.eval.gold import Case
from whycode.eval.scoring import check_citations
from whycode.fixtures import fixture_graph
from whycode.graph.corpus import corpus_records
from whycode.graph.store import GraphStore
from whycode.mcp_server import build_server

pytestmark = pytest.mark.anyio

EXEC = "pkg/sql.(*SchemaChanger).exec"
BACKOFF_QUOTE = (
    "We chose a capped exponential backoff rather than a fixed retry interval because a fixed interval either "
    "retries too aggressively during long outages or too slowly after short ones."
)
SANITY_QUOTE = (
    "The schema changer plan sanity check walks every stage of the plan and is too expensive to run on every "
    "statement in production."
)


def pr(number):
    return f"pr:{number}"


def issue(number):
    return f"issue:{number}"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def fixture_store(neo4j_driver):
    neo4j_driver.execute_query("MATCH (n) DETACH DELETE n")
    store = GraphStore(neo4j_driver)
    store.replace(fixture_graph())
    return store


@pytest.fixture(scope="module")
def reader(fixture_store, neo4j_driver):
    reader = GraphReader(neo4j_driver)
    reader.selfcheck()
    return reader


async def ask(reader, anchor, composer=None) -> Answer:
    async with Client(build_server(AnswerEngine(reader, composer or FaithfulComposer()))) as client:
        result = await client.call_tool("why", {"anchor": anchor})
    assert result.is_error is False, result.content
    return Answer.model_validate(result.structured_content)


def cited(answer: Answer) -> set[str]:
    return {c for s in answer.sentences for c in s.cites}


async def test_why_is_a_read_only_tool_returning_the_answer_contract(reader):
    async with Client(build_server(AnswerEngine(reader, FaithfulComposer()))) as client:
        (tool,) = [t for t in (await client.list_tools()).tools if t.name == "why"]
    assert tool.output_schema["title"] == "Answer"
    assert tool.annotations.read_only_hint is True


async def test_a_governed_function_returns_its_decisions_with_the_full_evidence_chain(reader):
    answer = await ask(reader, EXEC)

    assert answer.refused is False
    assert answer.anchor.model_dump() == {"kind": "function", "id": EXEC}
    backoff = next(d for d in answer.decisions if d.quote == BACKOFF_QUOTE)
    assert backoff.link == "hard"
    assert backoff.status == "live"
    assert backoff.date.isoformat() == "2023-03-20"  # #98100 merged
    assert backoff.discussion_id == pr(98100)
    evidence = {e.node_id: e for e in answer.evidence_chain}
    assert evidence[backoff.id].quote == BACKOFF_QUOTE
    assert evidence[pr(98100)].url == "https://github.com/cockroachdb/cockroach/pull/98100"
    assert {(p.handle, p.role, p.active) for p in answer.people} >= {("fqazi", "author", True),
                                                                    ("rafiss", "approver", True)}
    assert [i.id for i in answer.incidents] == [issue(98001)]  # the regression #98100 fixed
    assert answer.sentences and cited(answer) <= set(evidence)
    assert answer.confidence == "High"


async def test_a_governed_file_returns_decisions_governing_it_or_code_inside_it(reader):
    answer = await ask(reader, "pkg/sql/schema_changer.go")

    assert answer.refused is False
    assert answer.anchor.kind == "file"
    sources = {d.discussion_id for d in answer.decisions}
    # #98100, #101200, #101450 touch the file; the online schema change RFC names runBackfill inside it.
    assert {pr(98100), pr(101200), pr(101450), "rfc:20151014_online_schema_change"} <= sources
    assert all(d.quote and d.date for d in answer.decisions)
    assert {issue(98001), issue(101400)} == {i.id for i in answer.incidents}


async def test_a_governed_setting_returns_its_decision_and_flags_departed_people(reader):
    answer = await ask(reader, "sql.schemachanger.strict_planning_sanity_check.enabled")

    assert answer.refused is False
    assert answer.anchor.kind == "setting"
    assert [d.quote for d in answer.decisions] == [SANITY_QUOTE]
    assert answer.decisions[0].discussion_id == pr(110500)
    # The author and the approver have been inactive for over a year at the cutoff; the next-best active person
    # is suggested beside them (tests/test_why_people_and_resolve.py).
    assert {(p.handle, p.role, p.active) for p in answer.people if p.via is None} == {
        ("postamar", "author", False), ("ajwerner", "approver", False)}


async def test_a_decision_reaching_the_anchor_only_by_a_soft_link_is_less_confident(reader):
    answer = await ask(reader, "SchemaChanger.runBackfill")

    assert answer.anchor.id == "pkg/sql.(*SchemaChanger).runBackfill"
    assert [d.link for d in answer.decisions] == ["soft"]
    assert answer.decisions[0].discussion_id == "rfc:20151014_online_schema_change"
    assert ("vivekmenezes", "author", False) in {(p.handle, p.role, p.active) for p in answer.people}
    assert answer.confidence == "Medium"


async def test_an_ungoverned_anchor_is_refused_with_the_nearest_evidence_and_person_to_ask(reader):
    answer = await ask(reader, "scbuild.Build")

    assert answer.anchor.model_dump() == {"kind": "function", "id": "pkg/sql/schemachanger/scbuild.Build"}
    assert answer.refused is True
    assert answer.decisions == []
    assert answer.sentences == []
    assert pr(122400) in {e.node_id for e in answer.evidence_chain}  # the Change that touched it
    assert ("annrpom", "author", True) in {(p.handle, p.role, p.active) for p in answer.people}
    assert answer.confidence == "Low"


async def test_an_anchor_that_names_no_code_entity_is_refused(reader):
    answer = await ask(reader, "pkg/sql/no_such_file.go")

    assert answer.refused is True
    assert answer.anchor is None
    assert answer.decisions == []


async def test_fabricated_citations_and_quotes_never_reach_the_output_and_confidence_drops(reader):
    honest = await ask(reader, EXEC)
    answer = await ask(reader, EXEC, FabricatingComposer())

    dumped = answer.model_dump_json()
    assert FABRICATED_ID not in dumped and INVENTED_URL not in dumped
    texts = [s.text for s in answer.sentences]
    for sentence in DROPPED_SENTENCES:  # a fabricated id, a paraphrased quote, an invented inline quote
        assert sentence not in texts
    assert len(texts) == len(honest.sentences) + 1  # the URL sentence survives, minus its URL
    assert cited(answer) <= {e.node_id for e in answer.evidence_chain}
    assert answer.decisions == honest.decisions  # Decisions come from the graph, not the composer
    assert (honest.confidence, answer.confidence) == ("High", "Medium")


async def test_an_answer_with_nothing_verifiable_is_refused(reader):
    answer = await ask(reader, EXEC, OnlyFabricationsComposer())

    assert answer.refused is True
    assert answer.sentences == []
    assert FABRICATED_ID not in answer.model_dump_json()
    assert answer.confidence == "Low"


async def test_every_node_id_in_an_answer_resolves_to_a_real_record(reader, fixture_store):
    graph = fixture_store.snapshot()
    for anchor in (EXEC, "pkg/sql/schema_changer.go", "schemachanger.job.max_retry_backoff", "scbuild.Build"):
        answer = await ask(reader, anchor)
        ids = {d.id for d in answer.decisions} | {e.node_id for e in answer.evidence_chain}
        ids |= {i.id for i in answer.incidents} | cited(answer)
        assert ids, anchor
        for node_id in ids:
            assert node_id in graph.nodes and not graph.nodes[node_id].is_stub, (anchor, node_id)


async def test_the_scoreboard_finds_every_citation_valid_against_the_corpus_exported_from_the_graph(reader):
    """Ids and quotes line up with ticket 03's corpus and its own citation check."""
    corpus = MemoryCorpus(corpus_records(fixture_graph()))
    for anchor in (EXEC, "pkg/sql/schema_changer.go", "sql.defaults.use_declarative_schema_changer", "scbuild.Build"):
        answer = await ask(reader, anchor)
        case = Case(id="c", question_id="q", type="lookup", question=anchor, anchor=None, as_of=None,
                    exclude=frozenset(), answerable=True, gold_facts=["x"], superseded_facts=[])
        cites, valid = check_citations(answer, case, corpus)
        assert cites and valid == cites, anchor


async def test_the_why_mcp_entry_point_answers_over_stdio(fixture_store, neo4j_uri_auth):
    """The command Claude Code launches (`.mcp.json`), configured from the environment, offline composer."""
    uri, (user, password) = neo4j_uri_auth
    env = {**os.environ, "NEO4J_URI": uri, "NEO4J_USERNAME": user, "NEO4J_PASSWORD": password,
           "WHY_COMPOSER": "template"}
    params = StdioServerParameters(command=sys.executable, args=["-m", "whycode.mcp_server"], env=env)
    async with Client(params) as client:
        result = await client.call_tool("why", {"anchor": "schemachanger.job.max_retry_backoff"})
    answer = Answer.model_validate(result.structured_content)

    assert answer.refused is False
    assert pr(98100) in {d.discussion_id for d in answer.decisions}
    assert answer.sentences and cited(answer) <= {e.node_id for e in answer.evidence_chain}


async def test_a_free_form_question_naming_one_code_entity_is_resolved_and_a_vague_one_is_refused(reader):
    resolved = await ask(reader, "Why does `SchemaChanger.exec` back off between retries?")
    vague = await ask(reader, "why is the schema changer so slow?")

    assert resolved.anchor.id == EXEC and resolved.refused is False
    assert vague.anchor is None and vague.refused is True
