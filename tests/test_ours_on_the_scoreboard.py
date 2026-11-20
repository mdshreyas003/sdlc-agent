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
                            exclude=frozenset(exclude))).answer


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


def test_our_system_reports_the_model_usage_of_every_answer_for_the_cost_column(reader, tmp_path):
    from fake_anthropic import FakeApi, client_for

    from whycode.answer.compose import AnthropicComposer
    from whycode.answer.resolve import AnthropicEntityMatcher
    from whycode.eval.runner import Answered
    from whycode.llm import COMPOSER_MODEL, MATCHER_MODEL

    matcher_api = FakeApi({"entity_id": "function:pkg/sql.(*SchemaChanger).exec", "sure": True, "reason": "retries"})
    composer_api = FakeApi({"sentences": [{"text": "Retries back off exponentially.",
                                           "cites": [{"node_id": "pr:98100", "quote": ""}]}]})
    engine = AnswerEngine(reader, AnthropicComposer(client_for(composer_api, tmp_path), COMPOSER_MODEL),
                          matcher=AnthropicEntityMatcher(client_for(matcher_api, tmp_path), MATCHER_MODEL))
    ours = scoreboard_system("ours", engine)
    query = Query(question="Why does the schema changer back off between job retries?")

    first, again = ours.run(query), ours.run(query)  # the second from the model cache

    assert isinstance(first, Answered) and first.answer.anchor_matched and not first.answer.refused
    assert [c.model for c in first.usage.calls] == ["claude-opus-5-5", "claude-opus-5-5"]  # matcher, composer
    assert first.usage.cost_usd() == pytest.approx(2 * (10 * 4.0 + 5 * 20.0) / 1e6)  # Opus 5.5 prices
    # A cached response still costs what it cost to make, so the cost column does not depend on a warm cache.
    assert len(matcher_api.requests) == len(composer_api.requests) == 1
    assert again.usage == first.usage


# --- one scoreboard run: `whycode-eval run` with both of our systems, a scripted fact judge ------------------

REVERTED_CHOICE = "Treat descriptor validation errors as permanent schema change errors"
TWENTY_CHOICE = "Default the schema change retry backoff cap to 20 seconds"
TEN_CHOICE = "cap from 20 seconds to 10 seconds"
F_REVERTED = "Treating descriptor validation errors as permanent was reverted"
F_PERMANENT = "Descriptor validation errors are permanent schema change errors"
F_TWENTY = "The retry backoff cap defaults to 20 seconds"
F_TEN = "The default retry backoff cap was lowered to 10 seconds"
REVERT_STATEMENT = "This reverts commit 3f6c1e2a9b8d7c6e5f4a3b2c1d0e9f8a7b6c5d4e"


def _lines(answer_text, *statuses):
    return [line for line in answer_text.splitlines() if line.startswith(tuple(f"- [{s}" for s in statuses))]


FACT_CHECKS = {  # how the scripted judge decides a fact is stated (or presented as current) by an answer
    F_REVERTED: lambda text: any(REVERTED_CHOICE in line for line in _lines(text, "superseded")),
    F_PERMANENT: lambda text: any(REVERTED_CHOICE in line for line in _lines(text, "live", "refined")),
    F_TWENTY: lambda text: any(TWENTY_CHOICE in line for line in _lines(text, "live", "refined")),
    F_TEN: lambda text: any(TEN_CHOICE in line for line in _lines(text, "live", "refined")),
}


class FactJudgeModel:
    """A StructuredModel standing in for the scoreboard's Opus judge."""

    def parse(self, *, system, user, output):
        from whycode.eval.judge import Verdict
        from whycode.eval.models import Parsed, Usage

        def facts(title):
            block = user.split(f"{title} (in order):\n", 1)[1].split("\n\n", 1)[0]
            return [line.split(". ", 1)[1] for line in block.splitlines() if ". " in line]

        text = user.split("\nAnswer:\n", 1)[1]
        verdict = Verdict(covered=[FACT_CHECKS[f](text) for f in facts("Required facts")],
                          presented_as_live=[FACT_CHECKS[f](text) for f in facts("Superseded facts")],
                          reports_change=bool(_lines(text, "superseded")))
        return Parsed(output.model_validate(verdict.model_dump()), Usage())


def lay_out_eval_dir(root):
    from whycode.eval.gold import GoldEvidence, GoldQuestion, WindowAfter, save_gold

    reverted = GoldQuestion(
        id="S-1", type="supersession", origin="human", split="dev", human_verified=True,
        question="Does the schema changer treat descriptor validation errors as permanent?", anchor=PERMANENT,
        gold_facts=[F_REVERTED], superseded_facts=[F_PERMANENT],
        gold_evidence=[GoldEvidence(node_id="pr:101450", quote=REVERT_STATEMENT),
                       GoldEvidence(node_id="pr:101200", quote=VALIDATION_QUOTE)])
    window = GoldQuestion(
        id="W-1", type="window", origin="human", split="dev", human_verified=True,
        question="Why does the schema change retry backoff cap default to its value?", anchor=BACKOFF_SETTING,
        gold_facts=[F_TWENTY], gold_evidence=[GoldEvidence(node_id="pr:98100", quote=TWENTY_SECONDS_QUOTE)],
        after=WindowAfter(gold_facts=[F_TEN], superseded_facts=[F_TWENTY],
                          gold_evidence=[GoldEvidence(node_id="pr:127200", quote=TEN_SECONDS_QUOTE)]))
    (root / "gold").mkdir(parents=True)
    (root / "prompts").mkdir()
    (root / "results").mkdir()
    save_gold(root / "gold" / "human.yaml", [reverted, window])
    (root / "prompts" / "judge.md").write_text("Grade the answer.\n")
    return root


def section(report, title):
    return report.split(f"## {title}", 1)[1].split("\n## ", 1)[0]


def test_the_scoreboard_scores_ours_with_and_without_supersession_and_shows_the_difference(
        reader, neo4j_uri_auth, tmp_path, monkeypatch):
    import io

    from whycode.eval import cli
    from whycode.eval.corpus import write_jsonl
    from whycode.graph.corpus import corpus_records

    uri, (user, password) = neo4j_uri_auth
    for name, value in {"NEO4J_URI": uri, "NEO4J_USERNAME": user, "NEO4J_PASSWORD": password,
                        "WHY_COMPOSER": "template"}.items():
        monkeypatch.setenv(name, value)
    corpus = tmp_path / "corpus.jsonl"
    write_jsonl(corpus, corpus_records(fixture_graph(cutoff=FIXTURE_WINDOW_END)))
    out = io.StringIO()
    deps = cli.Deps(structured=lambda model: FactJudgeModel(), tool_loop=None, embedder=None, out=out,
                    now=lambda: dt.datetime(2026, 11, 20, 12, 0, 0))

    systems = ("ours=whycode.answer.systems:ours,"
               "ours-without-supersession=whycode.answer.systems:ours_without_supersession")
    eval_dir = lay_out_eval_dir(tmp_path / "eval")
    code = cli.main(["run", "--split", "dev", "--corpus", str(corpus), "--eval-dir", str(eval_dir),
                     "--cutoff", FIXTURE_CUTOFF.isoformat(), "--reference", "ours", "--systems", systems], deps)

    assert code == 0, out.getvalue()
    report = out.getvalue()
    assert "`ours` (answer template)" in report and "`ours-without-supersession` (answer template)" in report
    catch = section(report, "Supersession catch rate")
    assert "| question type | ours | ours-without-supersession |" in catch
    assert "| supersession | 100% [100-100] n=1 | 0% [0-0] n=1 |" in catch
    assert "| window-after | 100% [100-100] n=1 | 0% [0-0] n=1 |" in catch
    assert "| window-before | 100% [100-100] n=1 | 100% [100-100] n=1 |" in section(report, "Answer correctness")
    assert "| all | 100% [100-100] n=3 | 100% [100-100] n=3 |" in section(report, "Citation precision")
