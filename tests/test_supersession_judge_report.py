"""The supersession judge scored against explicit Supersession: precision and recall, with scripted judges."""

from __future__ import annotations

import pytest
from doubles import ScriptedJudge

from whycode.fixtures import fixture_graph
from whycode.supersession import judge_report

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
def fixture_env(neo4j_uri_auth, neo4j_driver, monkeypatch):
    """The `whycode` command pointed at the test database (wiped), offline."""
    uri, (user, password) = neo4j_uri_auth
    for name, value in {"NEO4J_URI": uri, "NEO4J_USERNAME": user, "NEO4J_PASSWORD": password}.items():
        monkeypatch.setenv(name, value)
    neo4j_driver.execute_query("MATCH (n) DETACH DELETE n")


def test_precision_and_recall_of_the_judge_against_explicit_supersession():
    judge = ScriptedJudge({
        (VALIDATION_QUOTE, KEEP_RETRYING_QUOTE): ("supersedes", "treating validation errors as permanent failed jobs"),
        (CHILD_TXN_QUOTE, STATEMENT_PHASE_QUOTE): ("unrelated", ""),  # misses the RFC supersession
        (VALIDATION_QUOTE, FINALIZED_QUOTE): ("supersedes", "treats descriptor validation errors as permanent again"),
    })
    report = judge_report(fixture_graph(), judge)

    assert (report.true_positives, report.false_negatives, report.false_positives) == (1, 1, 1)
    assert (report.precision, report.recall) == (0.5, 0.5)
    text = report.markdown()
    assert "Precision 50% (1 of 2)" in text and "recall 50% (1 of 2)" in text
    assert "rfc:20200909_transactional_schema_changes -> rfc:20210115_new_schema_changer" in text  # the miss
    # The judge never sees the statement that makes a case explicit.
    later_texts = [p.later_text for p in judge.pairs if p.later.quote == KEEP_RETRYING_QUOTE]
    assert later_texts and not [t for t in later_texts if "This reverts commit" in t or 'Revert "' in t]


def test_a_supersedes_label_whose_quote_is_not_verbatim_does_not_count():
    judge = ScriptedJudge({(VALIDATION_QUOTE, KEEP_RETRYING_QUOTE): ("supersedes", "it reverted the earlier change")})
    report = judge_report(fixture_graph(), judge)

    assert report.true_positives == 0 and report.false_negatives == 2


def test_the_command_reports_on_the_built_graph_with_the_recorded_judge(fixture_env, tmp_path, capsys):
    from whycode.cli import main

    assert main(["build"]) == 0
    out = tmp_path / "judge.md"
    assert main(["supersession-report", "--judge", "recorded", "--out", str(out)]) == 0

    assert "Precision 100% (2 of 2), recall 100% (2 of 2)" in out.read_text()
    assert out.read_text().strip() in capsys.readouterr().out
