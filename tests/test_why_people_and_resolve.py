"""Seam 2: the Person to Ask (departed people come with the next-best active person) and Anchor resolution (one
entity-matching model step for free-form questions, refused when unsure), over the fixture graph through the `why`
MCP tool, with scripted composer and matcher. Assertions are on the Answer contract only."""

from __future__ import annotations

import pytest
from doubles import FaithfulComposer, OnlyFabricationsComposer
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
    """Stands in for the entity-matching model: answers from a script keyed by question; for any other question it
    is sure of `otherwise` (None: unsure of anything)."""

    def __init__(self, script=None, otherwise=None):
        self.script = script or {}
        self.otherwise = otherwise

    def match(self, question, candidates):
        entity_id, sure = self.script.get(question, (self.otherwise, self.otherwise is not None))
        return EntityChoice(entity_id=entity_id, sure=sure, reason="scripted")


class SureOnSecondAsk:
    """A matcher that is unsure the first time and sure of `entity_id` from then on: only a loop would get an answer."""

    def __init__(self, entity_id):
        self.entity_id, self.asked = entity_id, 0

    def match(self, question, candidates):
        self.asked += 1
        return EntityChoice(entity_id=self.entity_id, sure=self.asked > 1, reason="scripted")


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


# --- Anchor resolution -----------------------------------------------------------------------------------------

BACKOFF_QUESTION = "Why does the schema changer back off between retries?"
VAGUE_QUESTION = "why is the schema changer so slow?"


async def test_a_question_naming_no_code_entity_is_matched_by_one_model_step_and_says_so(reader):
    matcher = ScriptedMatcher({BACKOFF_QUESTION: (f"function:{EXEC}", True)})

    answer = await ask(reader, BACKOFF_QUESTION, matcher)
    exact = await ask(reader, EXEC)

    assert answer.anchor.model_dump() == {"kind": "function", "id": EXEC}
    assert answer.anchor_matched is True and answer.refused is False
    assert answer.decisions == exact.decisions
    assert (exact.confidence, answer.confidence) == ("High", "Medium")  # the Anchor itself rests on a model's pick
    assert exact.anchor_matched is False


async def test_the_shortlist_holds_the_code_entities_whose_names_hold_the_questions_words(reader):
    # A pick off the shortlist is refused, so an answered pick shows the setting was on it.
    matcher = ScriptedMatcher({BACKOFF_QUESTION: ("setting:schemachanger.job.max_retry_backoff", True)})

    answer = await ask(reader, BACKOFF_QUESTION, matcher)

    assert (answer.anchor.kind, answer.anchor.id, answer.refused) == ("setting", "schemachanger.job.max_retry_backoff",
                                                                      False)


async def test_an_unsure_match_is_a_clear_refusal(reader):
    matcher = ScriptedMatcher({VAGUE_QUESTION: (f"function:{EXEC}", False)})

    answer = await ask(reader, VAGUE_QUESTION, matcher)

    assert (answer.anchor, answer.refused, answer.refusal_reason) == (None, True, "unresolved")
    assert answer.decisions == [] and answer.sentences == [] and answer.confidence == "Low"


async def test_matching_is_one_step_never_a_loop(reader):
    answer = await ask(reader, VAGUE_QUESTION, SureOnSecondAsk(f"function:{EXEC}"))

    assert (answer.anchor, answer.refusal_reason) == (None, "unresolved")  # a second ask would have been sure


async def test_a_match_outside_the_shortlist_is_refused_however_sure(reader):
    matcher = ScriptedMatcher({VAGUE_QUESTION: ("function:pkg/sql.(*SchemaChanger).madeUp", True)})

    answer = await ask(reader, VAGUE_QUESTION, matcher)

    assert answer.anchor is None and answer.refused is True


async def test_an_exactly_named_code_entity_needs_no_model_step(reader):
    # A matcher sure of another entity for every question: had it been asked, the Anchor would be that entity.
    matcher = ScriptedMatcher(otherwise="setting:sql.schemachanger.strict_planning_sanity_check.enabled")

    named = await ask(reader, "Why does `SchemaChanger.exec` back off between retries?", matcher)
    exact = await ask(reader, "schemachanger.job.max_retry_backoff", matcher)
    nothing_to_match = await ask(reader, "why?", matcher)

    assert named.anchor.id == EXEC and exact.anchor.id == "schemachanger.job.max_retry_backoff"
    assert not named.anchor_matched and not exact.anchor_matched
    assert (nothing_to_match.anchor, nothing_to_match.refusal_reason) == (None, "unresolved")


async def test_every_refusal_says_why(reader):
    ungoverned = await ask(reader, "scbuild.Build")
    unresolved = await ask(reader, "pkg/sql/no_such_file.go")
    async with Client(build_server(AnswerEngine(reader, OnlyFabricationsComposer()))) as client:
        result = await client.call_tool("why", {"anchor": EXEC})
    unverified = Answer.model_validate(result.structured_content)
    answered = await ask(reader, EXEC)

    assert [a.refusal_reason for a in (ungoverned, unresolved, unverified, answered)] == [
        "ungoverned", "unresolved", "unverified", None]
