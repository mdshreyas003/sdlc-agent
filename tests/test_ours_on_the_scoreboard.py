"""Our system as the scoreboard sees it: `Query -> Answer` over the fixture graph built through the Held-out Window,
honouring `as_of` and `exclude`, with and without Supersession. Assertions are on the Answer contract only."""

from __future__ import annotations

import datetime as dt

import pytest
from doubles import FaithfulComposer

from whycode.answer.engine import AnswerEngine
from whycode.answer.patterns import GraphReader
from whycode.answer.systems import scoreboard_system
from whycode.contract import Anchor, Answer
from whycode.eval.runner import Query
from whycode.fixtures import FIXTURE_CUTOFF, FIXTURE_WINDOW_END, fixture_graph
from whycode.graph.store import GraphStore

BACKOFF_SETTING = Anchor(kind="setting", id="schemachanger.job.max_retry_backoff")
PERMANENT = Anchor(kind="function", id="pkg/sql.isPermanentSchemaChangeError")
TWENTY_SECONDS_QUOTE = (
    "Capping the backoff at 20 seconds keeps a stuck job visible in SHOW JOBS without hammering the cluster."
)
TEN_SECONDS_QUOTE = "Lower the default cap to 10s because 20s left stuck jobs waiting too long after short outages."
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


@pytest.fixture(scope="module")
def reader(neo4j_driver):
    neo4j_driver.execute_query("MATCH (n) DETACH DELETE n")
    GraphStore(neo4j_driver).replace(fixture_graph(cutoff=FIXTURE_WINDOW_END))
    reader = GraphReader(neo4j_driver)
    reader.selfcheck()
    return reader


@pytest.fixture(scope="module")
def ours(reader):
    return scoreboard_system("ours", AnswerEngine(reader, FaithfulComposer()))


def ask(system, anchor, as_of=None, exclude=()) -> Answer:
    return system.run(Query(question=f"Why is {anchor.id} like this?", anchor=anchor, as_of=as_of,
                            exclude=frozenset(exclude)))


def node_ids(answer: Answer) -> set[str]:
    ids = {d.id for d in answer.decisions} | {d.discussion_id for d in answer.decisions}
    ids |= {e.node_id for e in answer.evidence_chain} | {i.id for i in answer.incidents}
    return ids | {c for s in answer.sentences for c in s.cites}


def by_quote(answer: Answer):
    return {d.quote: d for d in answer.decisions}


def test_as_of_the_cutoff_nothing_from_the_held_out_window_reaches_the_answer(ours):
    before = ask(ours, BACKOFF_SETTING, as_of=FIXTURE_CUTOFF)
    after = ask(ours, BACKOFF_SETTING)

    assert by_quote(before)[TWENTY_SECONDS_QUOTE].status == "live"
    assert TEN_SECONDS_QUOTE not in by_quote(before)
    assert not {"pr:127200", "issue:127000"} & node_ids(before)
    assert [i.id for i in before.incidents] == ["issue:98001"]

    twenty, ten = by_quote(after)[TWENTY_SECONDS_QUOTE], by_quote(after)[TEN_SECONDS_QUOTE]
    assert (twenty.status, twenty.superseded_by, twenty.explicit_or_inferred) == ("superseded", ten.id, "inferred")
    assert ten.status == "live"
    assert "issue:127000" in {i.id for i in after.incidents}


def test_a_supersession_after_as_of_is_invisible_and_a_reverted_refinement_stops_refining(ours):
    before = by_quote(ask(ours, PERMANENT, as_of=FIXTURE_CUTOFF))
    after = by_quote(ask(ours, PERMANENT))
    earlier = by_quote(ask(ours, PERMANENT, as_of=dt.date(2023, 5, 5)))

    assert (before[FINALIZED_QUOTE].status, before[KEEP_RETRYING_QUOTE].status) == ("live", "refined")
    # #128000 (in the window) reverts #104500, which records no Decision: the Change itself supersedes.
    assert (after[FINALIZED_QUOTE].status, after[FINALIZED_QUOTE].superseded_by) == ("superseded", "pr:128000")
    assert after[KEEP_RETRYING_QUOTE].status == "live"
    # Between #101200 (2023-05-02) and its revert (2023-05-10), the validation Decision was still live.
    assert list(earlier) == [VALIDATION_QUOTE] and earlier[VALIDATION_QUOTE].status == "live"


def test_excluded_records_are_absent_with_everything_that_rests_on_them(ours):
    answer = ask(ours, PERMANENT, as_of=FIXTURE_CUTOFF, exclude={"pr:101450"})  # hide the revert

    decisions = by_quote(answer)
    assert KEEP_RETRYING_QUOTE not in decisions
    assert decisions[VALIDATION_QUOTE].status == "live"  # nothing visible supersedes it any more
    assert "pr:101450" not in node_ids(answer)


def test_without_supersession_every_decision_is_presented_as_live(reader):
    without = scoreboard_system("ours-without-supersession", AnswerEngine(reader, FaithfulComposer(),
                                                                          supersession=False))
    answer = ask(without, PERMANENT)

    assert {d.quote for d in answer.decisions} >= {VALIDATION_QUOTE, KEEP_RETRYING_QUOTE, FINALIZED_QUOTE}
    assert {d.status for d in answer.decisions} == {"live"}
    assert {d.superseded_by for d in answer.decisions} == {None}


def test_an_issue_decision_governs_code_only_once_the_change_implementing_it_has_merged(ours):
    exec_ = Anchor(kind="function", id="pkg/sql.(*SchemaChanger).exec")
    before = ask(ours, exec_, as_of=dt.date(2023, 3, 10))  # rafiss proposed backoff on #98001 on 2023-03-03
    after = ask(ours, exec_, as_of=dt.date(2023, 3, 20))  # #98100 implemented it

    assert before.refused is True and before.decisions == []
    assert {d.discussion_id for d in after.decisions} == {"issue:98001", "pr:98100"}
