"""Seam 2, `check_change`: Fence Warnings for proposed diffs over the fixture graph (recorded extractions and
judgments). The diffs are `git diff` output against the fixture code (`fixtures/miniature/proposed/`).
Assertions are on the contract only (`ChangeCheck`, `FenceWarning`)."""

from __future__ import annotations

import pytest
from doubles import FaithfulComposer
from mcp import Client

from whycode.answer.engine import AnswerEngine
from whycode.answer.patterns import GraphReader
from whycode.audit import GraphResolver
from whycode.contract import ChangeCheck
from whycode.fixtures import fixture_graph, proposed_diff
from whycode.graph.store import GraphStore
from whycode.mcp_server import build_server

pytestmark = pytest.mark.anyio

EXEC = "function:pkg/sql.(*SchemaChanger).exec"
PERMANENT = "function:pkg/sql.isPermanentSchemaChangeError"
BACKOFF_SETTING = "setting:schemachanger.job.max_retry_backoff"
BACKOFF_QUOTE = (
    "We chose a capped exponential backoff rather than a fixed retry interval because a fixed interval either "
    "retries too aggressively during long outages or too slowly after short ones."
)
TWENTY_SECONDS_QUOTE = "Capping the backoff at 20 seconds keeps a stuck job visible in SHOW JOBS without hammering the cluster."
ISSUE_BACKOFF_QUOTE = (
    "We should back off exponentially between retries instead of retrying immediately; a constant delay would "
    "still hammer the cluster during a long outage."
)
VALIDATION_QUOTE = (  # #101200, superseded by its revert #101450
    "Descriptor validation errors cannot be fixed by retrying, so the schema changer should stop retrying and "
    "fail the job instead of spinning until the backoff cap."
)
KEEP_RETRYING_QUOTE = (  # #101450, refined by #104500
    "During upgrades, descriptors can fail validation transiently while the cluster version gate is being crossed, "
    "so treating validation errors as permanent failed jobs that would have succeeded on retry."
)
FINALIZED_QUOTE = (  # #104500
    "This treats descriptor validation errors as permanent again once the cluster version is finalized; until then "
    "the schema changer keeps retrying them"
)
CHILD_TXN_QUOTE = (  # RFC 20200909, superseded by RFC 20210115
    "`scrun.RunStatementPhase` runs each schema change statement in a child transaction that commits before the "
    "user's transaction, so a failed backfill never rolls back the user's other writes."
)
STATEMENT_PHASE_QUOTE = (
    "`scrun.RunStatementPhase` executes the statement phase inside the user's transaction so that later statements "
    "in the same transaction observe the change."
)
OUTSIDE_THE_INDEX = """--- a/pkg/util/retry/retry.go
+++ b/pkg/util/retry/retry.go
@@ -10,3 +10,3 @@ func Start(opts Options) Retry {
-	opts.MaxBackoff = 20 * time.Second
+	opts.MaxBackoff = 5 * time.Minute
"""


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


async def check(reader, diff: str, supersession: bool = True) -> ChangeCheck:
    engine = AnswerEngine(reader, FaithfulComposer(), supersession=supersession)
    async with Client(build_server(engine)) as client:
        result = await client.call_tool("check_change", {"diff": diff})
    assert result.is_error is False, result.content
    return ChangeCheck.model_validate(result.structured_content)


def by_quote(result: ChangeCheck):
    return {w.quote: w for w in result.warnings}


async def test_a_diff_that_removes_the_retry_backoff_is_warned_by_the_decision_that_fixed_the_hot_loop(reader):
    result = await check(reader, proposed_diff("remove-retry-backoff"))

    # The hunk header names isPermanentSchemaChangeError, but every changed line is inside exec; one of them reads
    # the setting through its Go variable.
    assert set(result.touched) == {"file:pkg/sql/schema_changer.go", EXEC, BACKOFF_SETTING}
    warnings = by_quote(result)
    assert set(warnings) == {BACKOFF_QUOTE, TWENTY_SECONDS_QUOTE, ISSUE_BACKOFF_QUOTE}
    backoff = warnings[BACKOFF_QUOTE]
    assert backoff.entity_id == EXEC
    assert backoff.kind == "reverses"
    assert backoff.change_id == "pr:98100"
    assert backoff.incident_ids == ["issue:98001"]  # the hot-loop regression #98100 fixed
    assert backoff.confidence == "High"
    assert backoff.status == "live"
    assert "opts.MaxBackoff = schemaChangeJobMaxRetryBackoff.Get(sc.settings)" in backoff.reversed_lines
    assert backoff.discussion_id == "pr:98100"


async def test_making_validation_errors_always_permanent_is_warned_by_the_revert_and_its_refinement(reader):
    result = await check(reader, proposed_diff("validation-errors-always-permanent"))

    warnings = by_quote(result)
    assert set(warnings) == {FINALIZED_QUOTE, KEEP_RETRYING_QUOTE}
    finalized, revert = warnings[FINALIZED_QUOTE], warnings[KEEP_RETRYING_QUOTE]
    # The diff removes the line #104500 added ...
    assert (finalized.kind, finalized.status, finalized.change_id) == ("reverses", "live", "pr:104500")
    assert finalized.entity_id == PERMANENT
    assert finalized.confidence == "High"
    # ... and restores the line the revert #101450 removed: that Decision is refined, so partly live, and it is
    # what prevented the release blocker #101400.
    assert (revert.kind, revert.status, revert.change_id) == ("reverses", "refined", "pr:101450")
    assert revert.reversed_lines == ["if catalog.HasValidationError(err) {"]
    assert revert.incident_ids == ["issue:101400"]
    assert revert.confidence == "Medium"  # the refinement is the judge's inference
    assert [w.quote for w in result.warnings] == [FINALIZED_QUOTE, KEEP_RETRYING_QUOTE]  # strongest first


async def test_raising_the_backoff_cap_default_is_warned_on_the_setting(reader):
    result = await check(reader, proposed_diff("raise-backoff-cap-default"))

    twenty = by_quote(result)[TWENTY_SECONDS_QUOTE]
    assert twenty.entity_id == BACKOFF_SETTING
    assert (twenty.kind, twenty.reversed_lines, twenty.incident_ids) == ("reverses", ["20*time.Second,"], ["issue:98001"])


@pytest.mark.parametrize("name", ["build-rename", "zone-config-assertion"])
async def test_a_diff_touching_no_governed_entity_gets_no_warnings(reader, name):
    # zone-config-assertion edits an ungoverned function of a governed file, just below a governed function (the
    # hunk header names runBackfill, which an RFC Decision governs).
    result = await check(reader, proposed_diff(name))

    assert result.touched
    assert result.warnings == []


@pytest.mark.parametrize("diff", [OUTSIDE_THE_INDEX, "please remove the backoff", ""])
async def test_a_diff_outside_the_code_index_or_no_diff_at_all_gets_no_warnings(reader, diff):
    result = await check(reader, diff)

    assert (result.touched, result.warnings) == ([], [])


async def test_a_superseded_decision_never_triggers_a_warning(reader):
    child_txn = await check(reader, proposed_diff("statement-phase-child-txn"))
    validation = await check(reader, proposed_diff("validation-errors-always-permanent"))

    # The diff brings back the superseded RFC's child transaction: the Live Decision that superseded it warns.
    assert [w.quote for w in child_txn.warnings] == [STATEMENT_PHASE_QUOTE]
    statement_phase = child_txn.warnings[0]
    assert (statement_phase.kind, statement_phase.status) == ("changes", "live")
    assert statement_phase.confidence == "Low"  # only named in the RFC, and only edited, not reversed
    assert VALIDATION_QUOTE not in by_quote(validation)
    # Both dead Decisions do govern the code these diffs touch: treated as live, they would warn.
    assert CHILD_TXN_QUOTE in by_quote(await check(reader, proposed_diff("statement-phase-child-txn"), False))
    assert VALIDATION_QUOTE in by_quote(await check(reader, proposed_diff("validation-errors-always-permanent"), False))


async def test_every_node_id_in_a_fence_warning_resolves(reader, neo4j_driver):
    ids = set()
    for name in ("remove-retry-backoff", "validation-errors-always-permanent", "statement-phase-child-txn"):
        result = await check(reader, proposed_diff(name))
        ids |= set(result.touched)
        for w in result.warnings:
            ids |= {w.decision_id, w.entity_id, w.discussion_id, *w.incident_ids, *([w.change_id] if w.change_id else [])}

    assert GraphResolver(neo4j_driver)(ids) == ids


def test_whycode_check_change_prints_the_contract_for_a_diff_file(reader, neo4j_uri_auth, monkeypatch, capsys):
    from whycode import cli
    from whycode.fixtures import PROPOSED_DIR

    uri, (user, password) = neo4j_uri_auth
    for name, value in {"NEO4J_URI": uri, "NEO4J_USERNAME": user, "NEO4J_PASSWORD": password,
                        "NEO4J_DATABASE": "neo4j"}.items():
        monkeypatch.setenv(name, value)

    assert cli.main(["check-change", str(PROPOSED_DIR / "raise-backoff-cap-default.diff")]) == 0

    result = ChangeCheck.model_validate_json(capsys.readouterr().out)
    assert TWENTY_SECONDS_QUOTE in by_quote(result)


async def test_check_change_is_listed_next_to_why_with_its_contract():
    async with Client(build_server(AnswerEngine(reader=None, composer=FaithfulComposer()))) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}

    assert {"why", "check_change"} <= set(tools)
    assert tools["check_change"].output_schema["title"] == "ChangeCheck"
    assert tools["check_change"].annotations.read_only_hint is True
