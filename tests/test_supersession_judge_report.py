"""The supersession judge scored against explicit Supersession: precision and recall, with scripted judges."""

from __future__ import annotations

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


class QuotesTheRevert:
    """A judge that cheats: it says supersedes, quoting the revert statement, whenever that statement is in the text
    it is shown (the quote is verbatim in B's discussion, so it would count)."""

    def judge(self, pair):
        from whycode.supersession import Judgment

        if REVERT_STATEMENT in pair.later_text:
            return Judgment(label="supersedes", quote=f"{REVERT_STATEMENT}. During upgrades, descriptors can fail",
                            reason="it says so")
        return Judgment(label="unrelated", quote="", reason="nothing stated")


REVERT_STATEMENT = "This reverts commit 3f6c1e2a9b8d7c6e5f4a3b2c1d0e9f8a7b6c5d4e"


def test_the_judge_never_sees_the_statement_that_makes_a_case_explicit():
    report = judge_report(fixture_graph(), QuotesTheRevert())

    assert report.true_positives == 0 and report.false_negatives == 2  # the revert was masked out of #101450


def test_a_supersedes_label_whose_quote_is_not_verbatim_does_not_count():
    judge = ScriptedJudge({(VALIDATION_QUOTE, KEEP_RETRYING_QUOTE): ("supersedes", "it reverted the earlier change")})
    report = judge_report(fixture_graph(), judge)

    assert report.true_positives == 0 and report.false_negatives == 2


def test_the_command_reports_on_the_built_graph_with_the_recorded_judge(whycode_env, tmp_path, capsys):
    from whycode.cli import main

    assert main(["build"]) == 0
    out = tmp_path / "judge.md"
    assert main(["supersession-report", "--judge", "recorded", "--out", str(out)]) == 0

    assert "Precision 100% (2 of 2), recall 100% (2 of 2)" in out.read_text()
    assert out.read_text().strip() in capsys.readouterr().out
