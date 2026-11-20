"""Seam 2, superseded history: `why` over the fixture graph extended with a chain of Supersessions of the plan
sanity-check Decision (#110500 <- #116000 <- #117000), scripted composer. Assertions are on the Answer contract."""

from __future__ import annotations

import pytest
from doubles import FaithfulComposer
from fixture_history import extended_graph, pull_bundle
from mcp import Client

from whycode.answer.engine import AnswerEngine
from whycode.answer.patterns import GraphReader
from whycode.contract import Answer
from whycode.graph.store import GraphStore
from whycode.mcp_server import build_server

pytestmark = pytest.mark.anyio

SETTING = "sql.schemachanger.strict_planning_sanity_check.enabled"
SCRUN = "pkg/sql/schemachanger/scrun/scrun.go"
SANITY_QUOTE = (
    "The schema changer plan sanity check walks every stage of the plan and is too expensive to run on every "
    "statement in production."
)
ALWAYS_ON_QUOTE = (
    "Running the plan sanity check on every statement costs less than one percent of planning time since the "
    "planner rewrite, so it is always enabled again."
)
ONLY_WHEN_SET_QUOTE = (
    f"Run the plan sanity check only when `{SETTING}` is set, because running it on every statement doubled "
    "planning time for wide tables."
)


def _make_state_patch(old: str, new: str) -> str:
    """A diff inside `makeState` that names no cluster setting."""
    return ("@@ -48,7 +48,7 @@ func makeState(ctx context.Context, sv *settings.Values, state scplan.State) "
            "(scplan.State, error) {\n \tplan, err := scplan.MakePlan(ctx, state, scplan.Params{\n"
            f"-\t\tStrict: {old},\n+\t\tStrict: {new},\n \t}})")


ALWAYS_ON = pull_bundle(116000, "scrun: always run the strict planning sanity check",
                        f"Supersedes #110500. {ALWAYS_ON_QUOTE}\n\nRelease note: None", "2024-01-10T10:00:00Z",
                        {SCRUN: _make_state_patch("false", "true")}, author="annrpom")
ONLY_WHEN_SET = pull_bundle(117000, "scrun: run the sanity check only when the setting is on again",
                            f"Supersedes #116000. {ONLY_WHEN_SET_QUOTE}\n\nRelease note: None",
                            "2024-03-01T10:00:00Z", {SCRUN: _make_state_patch("true", "checked")}, author="fqazi")
EXTRACTIONS = {
    "pr:116000": [{"choice": "Always run the plan sanity check", "rationale": "It is cheap since the planner "
                   "rewrite.", "quote": ALWAYS_ON_QUOTE}],
    "pr:117000": [{"choice": "Run the plan sanity check only when the cluster setting is on",
                   "rationale": "Always running it doubled planning time.", "quote": ONLY_WHEN_SET_QUOTE}],
}


@pytest.fixture
def anyio_backend():
    return "asyncio"


def load(neo4j_driver, tmp_path, *pulls) -> GraphReader:
    neo4j_driver.execute_query("MATCH (n) DETACH DELETE n")
    GraphStore(neo4j_driver).replace(extended_graph(tmp_path, pulls=pulls, extractions=EXTRACTIONS))
    return GraphReader(neo4j_driver)


async def ask(reader, anchor) -> Answer:
    async with Client(build_server(AnswerEngine(reader, FaithfulComposer()))) as client:
        result = await client.call_tool("why", {"anchor": anchor})
    assert result.is_error is False, result.content
    return Answer.model_validate(result.structured_content)


def decision_ids(answer: Answer) -> dict[str, str]:
    """Quote -> node id of every Decision in the Evidence Chain."""
    return {e.quote: e.node_id for e in answer.evidence_chain if e.kind == "decision"}


async def test_an_anchor_whose_every_decision_is_superseded_is_refused_with_its_superseded_history(
        neo4j_driver, tmp_path):
    reader = load(neo4j_driver, tmp_path, ALWAYS_ON)  # #116000 supersedes #110500, the setting's only Decision

    answer = await ask(reader, SETTING)

    assert (answer.refused, answer.refusal_reason, answer.confidence) == (True, "superseded", "Low")
    assert answer.sentences == []
    (sanity,) = answer.decisions
    assert (sanity.quote, sanity.status) == (SANITY_QUOTE, "superseded")
    assert sanity.superseded_by == decision_ids(answer)[ALWAYS_ON_QUOTE]
    assert {"pr:110500", "pr:116000", sanity.superseded_by} <= {e.node_id for e in answer.evidence_chain}
    assert answer.people  # the Person to Ask still comes with the refusal


async def test_a_superseded_decision_names_the_chain_to_the_decision_that_holds_now(neo4j_driver, tmp_path):
    reader = load(neo4j_driver, tmp_path, ALWAYS_ON, ONLY_WHEN_SET)  # #117000 in turn supersedes #116000

    answer = await ask(reader, SETTING)

    ids = decision_ids(answer)
    always_on, only_when_set = ids[ALWAYS_ON_QUOTE], ids[ONLY_WHEN_SET_QUOTE]
    by_quote = {d.quote: d for d in answer.decisions}
    sanity = by_quote[SANITY_QUOTE]
    assert (sanity.status, sanity.superseded_by) == ("superseded", always_on)
    # #116000's Decision governs makeState, not the setting, so it is not among the Decisions: the chain says
    # that it is dead too, and what holds now.
    assert always_on not in {d.id for d in answer.decisions}
    assert sanity.supersession_chain == [always_on, only_when_set]
    assert by_quote[ONLY_WHEN_SET_QUOTE].status == "live"
    assert set(sanity.supersession_chain) <= {e.node_id for e in answer.evidence_chain}
    assert answer.refused is False
