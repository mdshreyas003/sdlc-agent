"""Seam 2: the Person to Ask (departed people come with the next-best active person) and Anchor resolution (one
entity-matching model step for free-form questions, refused when unsure), over the fixture graph through the `why`
MCP tool, with scripted composer and matcher. Assertions are on the Answer contract only."""

from __future__ import annotations

import pytest
from doubles import FaithfulComposer
from mcp import Client

from whycode.answer.engine import AnswerEngine
from whycode.answer.patterns import GraphReader
from whycode.answer.resolve import EntityChoice
from whycode.contract import Answer
from whycode.fixtures import fixture_graph
from whycode.graph.store import GraphStore
from whycode.mcp_server import build_server

pytestmark = pytest.mark.anyio

EXEC = "pkg/sql.(*SchemaChanger).exec"
SANITY_SETTING = "sql.schemachanger.strict_planning_sanity_check.enabled"


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


class ScriptedMatcher:
    """Stands in for the entity-matching model: answers from a script keyed by question; records what it saw."""

    def __init__(self, script=None):
        self.script = script or {}
        self.asked = []

    def match(self, question, candidates):
        self.asked.append((question, [c.id for c in candidates]))
        entity_id, sure = self.script.get(question, (None, False))
        return EntityChoice(entity_id=entity_id, sure=sure, reason="scripted")


async def ask(reader, anchor, matcher=None) -> Answer:
    engine = AnswerEngine(reader, FaithfulComposer(), matcher=matcher)
    async with Client(build_server(engine)) as client:
        result = await client.call_tool("why", {"anchor": anchor})
    assert result.is_error is False, result.content
    return Answer.model_validate(result.structured_content)


def people(answer: Answer):
    return {p.handle: p for p in answer.people}


# --- Person to Ask ---------------------------------------------------------------------------------------------

async def test_departed_people_come_with_the_next_best_active_person_from_that_area_of_the_code(reader):
    answer = await ask(reader, SANITY_SETTING)

    found = people(answer)
    # #110500's author and approver have been inactive for over a year; nobody active touched its file since.
    assert (found["postamar"].active, found["ajwerner"].active) == (False, False)
    assert found["postamar"].ask_instead == found["ajwerner"].ask_instead == "annrpom"
    # annrpom wrote #122400, the latest Change in the nearest area someone active worked on (pkg/sql/schemachanger).
    suggested = found["annrpom"]
    assert (suggested.active, suggested.role, suggested.via) == (True, "author", "pr:122400")
    assert answer.people[0].handle == "annrpom"  # the first person listed is the one to ask


async def test_an_active_author_of_the_anchors_decisions_is_preferred_to_anyone_else(reader):
    answer = await ask(reader, "pkg/sql/schema_changer.go")

    found = people(answer)
    assert found["vivekmenezes"].active is False  # the online schema change RFC's author
    assert found["vivekmenezes"].ask_instead == "fqazi"  # author of #98100, whose Decision governs the file
    assert found["fqazi"].via is None
    assert all(p.via is None for p in answer.people)  # nobody had to be brought in from outside the answer


async def test_a_refusal_suggests_the_next_best_person_too(reader):
    answer = await ask(reader, "scbuild.Build")

    assert answer.refused is True
    assert all(p.active for p in answer.people)  # annrpom, rafiss, fqazi: nobody departed, nothing to suggest
    assert all(p.ask_instead is None for p in answer.people)


async def test_people_with_nobody_departed_carry_no_suggestion(reader):
    answer = await ask(reader, EXEC)

    assert answer.people and all(p.active and p.ask_instead is None and p.via is None for p in answer.people)
