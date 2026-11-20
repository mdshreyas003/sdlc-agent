"""Per-item metrics and the results table, driven by stub answers with known metric values."""

import datetime as dt

from eval_support import CUTOFF, FIXTURE_RECORDS

from whycode.contract import Anchor, Answer, DecisionView, EvidenceItem, Sentence
from whycode.eval.corpus import MemoryCorpus
from whycode.eval.gold import Case
from whycode.eval.judge import JudgeInput, Verdict
from whycode.eval.models import ModelCall, Usage
from whycode.eval.runner import AnswerRecord
from whycode.eval.scoring import report, score

CORPUS = MemoryCorpus(FIXTURE_RECORDS)
ZONE = Anchor(kind="file", id="pkg/sql/configure_zone.go")


def case(id, type, answerable=True, facts=("f1",), dead=(), exclude=(), as_of=CUTOFF):
    return Case(id=id, question_id=id, type=type, question=f"question {id}?", anchor=ZONE, as_of=as_of,
                exclude=frozenset(exclude), answerable=answerable, gold_facts=list(facts),
                superseded_facts=list(dead))


def answered(text, refused=False, evidence=(), cites=(), decisions=()):
    return Answer(anchor=ZONE, refused=refused, confidence="Medium", decisions=list(decisions),
                  evidence_chain=[EvidenceItem(node_id=n, kind="pr", quote=q) for n, q in evidence],
                  sentences=[Sentence(text=text, cites=list(cites))])


def record(case_id, answer, system="stub", seconds=1.5, usage=None, error=None):
    return AnswerRecord(case_id=case_id, system=system, answer=answer, seconds=seconds, usage=usage, error=error)


class ScriptedJudge:
    """Answers from verdicts keyed by question; asking about any other question fails the test (KeyError), so
    `ScriptedJudge({})` shows a score that needed no judge call."""

    def __init__(self, verdicts):
        self.verdicts = verdicts

    def __call__(self, item: JudgeInput) -> Verdict:
        return self.verdicts[item.question]


LOOKUP = case("L", "lookup", facts=("f1", "f2"))
SUPERSEDED = case("S", "supersession", facts=("g1",), dead=("dead1",))
UNANSWERABLE = case("U", "unanswerable", answerable=False, facts=())
TRAP = case("T", "trap", answerable=False, facts=())
JUDGE = ScriptedJudge({
    "question L?": Verdict(covered=[True, False]),
    "question S?": Verdict(covered=[True], presented_as_live=[False], reports_change=True),
})
OPUS_CALL = Usage(calls=[ModelCall(model="claude-opus-5-5", input_tokens=1000, output_tokens=100)])


def test_answerable_item_scores_correctness_citations_cost_and_latency():
    answer = answered("Dropped indexes are skipped.", evidence=[("pr:121026", "their descriptors may already be gone")],
                      cites=["pr:121026", "pr:999"])
    row = score(LOOKUP, record("L", answer, usage=OPUS_CALL), CORPUS, JUDGE)

    assert (row.correctness, row.cites, row.valid_cites, row.citation_precision) == (0.5, 2, 1, 0.5)
    assert (row.refusal_correct, row.invented, row.supersession_caught) == (1.0, None, None)
    assert (row.seconds, row.cost_usd, row.input_tokens, row.output_tokens) == (1.5, 0.006, 1000, 100)


def test_superseded_decision_reported_as_superseded_is_caught():
    dead = DecisionView(id="pr:116000", choice="CREATE DATABASE runs declaratively", rationale="transactional",
                        quote="CREATE DATABASE now runs in the declarative schema changer", date=dt.date(2023, 12, 1),
                        status="superseded", superseded_by="pr:116879", link="soft")
    row = score(SUPERSEDED, record("S", answered("It was reverted.", decisions=[dead])), CORPUS, JUDGE)

    assert (row.correctness, row.supersession_caught, row.cites, row.valid_cites) == (1.0, 1.0, 1, 1)


def test_dead_decision_presented_as_live_is_not_caught():
    judge = ScriptedJudge({"question S?": Verdict(covered=[True], presented_as_live=[True], reports_change=True)})
    row = score(SUPERSEDED, record("S", answered("It runs declaratively.")), CORPUS, judge)

    assert row.supersession_caught == 0.0


def test_refusal_on_an_unanswerable_question_is_correct_and_costs_no_judge_call():
    judge = ScriptedJudge({})
    row = score(UNANSWERABLE, record("U", answered("Not established.", refused=True)), CORPUS, judge)

    assert (row.refusal_correct, row.invented, row.correctness, row.citation_precision) == (1.0, 0.0, None, None)


def test_answering_a_trap_is_an_invented_answer():
    row = score(TRAP, record("T", answered("Yes, because of the lease change.", cites=["pr:126100"])), CORPUS, JUDGE)

    assert (row.refusal_correct, row.invented, row.citation_precision) == (0.0, 1.0, 1.0)


def test_refusing_an_answerable_question_scores_zero_without_judging():
    judge = ScriptedJudge({})
    row = score(LOOKUP, record("L", answered("No Decision found.", refused=True)), CORPUS, judge)

    assert (row.correctness, row.refusal_correct) == (0.0, 0.0)


def test_citations_to_ablated_or_post_cutoff_records_are_invalid():
    hidden = case("H", "lookup", exclude=["pr:121026"])
    answer = answered("x", evidence=[("pr:121026", "their descriptors may already be gone"),
                                     ("pr:127500", "made upgrades fail")])
    row = score(hidden, record("H", answer), CORPUS, ScriptedJudge({"question H?": Verdict(covered=[True])}))

    assert (row.cites, row.valid_cites) == (2, 0)


def test_derived_decision_ids_count_when_their_quote_is_in_the_cited_evidence():
    decision = DecisionView(id="decision:7", choice="skip dropped indexes", rationale="descriptors may be gone",
                            quote="ignores indexes in the DROP state", date=dt.date(2024, 6, 22), link="hard")
    invented = decision.model_copy(update={"id": "decision:8", "quote": "zones are never configured"})
    answer = answered("x", evidence=[("pr:121026", None)], cites=["decision:7", "decision:8"],
                      decisions=[decision, invented])
    row = score(LOOKUP, record("L", answer), CORPUS, JUDGE)

    assert (row.cites, row.valid_cites) == (3, 2)  # evidence + decision:7 valid; decision:8 not grounded


def test_errors_score_as_failures_and_are_counted():
    row = score(TRAP, record("T", None, error="RuntimeError: boom", seconds=0.0), CORPUS, JUDGE)

    assert (row.error, row.refusal_correct, row.invented, row.citation_precision) == (True, 0.0, 0.0, None)


def test_report_prints_each_metric_per_question_type_with_intervals():
    oracle = {
        "L": answered("Dropped indexes are skipped.", evidence=[("pr:121026", "their descriptors may already be gone")],
                      cites=["pr:999"]),
        "S": answered("It was reverted."),
        "U": answered("Not established.", refused=True),
        "T": answered("Because of the lease change."),
    }
    refuser = {k: answered("No Decision found.", refused=True) for k in oracle}
    cases = [LOOKUP, SUPERSEDED, UNANSWERABLE, TRAP]
    rows = [score(c, record(c.id, oracle[c.id], system="ours", usage=OPUS_CALL), CORPUS, JUDGE) for c in cases]
    rows += [score(c, record(c.id, refuser[c.id], system="vector-rag"), CORPUS, JUDGE) for c in cases]

    text = report(rows, ["ours", "vector-rag"], header="split `dev`", reference="ours")

    assert "| question type | ours | vector-rag |" in text
    assert "| lookup | 50% [50-50] n=1 | 0% [0-0] n=1 |" in text  # correctness
    assert "| all | 75% [50-100] n=2 | 0% [0-0] n=2 |" in text  # correctness over L and S
    assert "| trap | 100% [100-100] n=1 | 0% [0-0] n=1 |" in text  # invented-answer rate
    assert "| all | 75% [25-100] n=4 | 50% [0-100] n=4 |" in text  # refusal accuracy
    assert "| all | 1.50 [1.50-1.50] n=4 | 1.50 [1.50-1.50] n=4 |" in text  # seconds
    assert "| all | $0.0060 [0.0060-0.0060] n=4 | - |" in text  # cost (unknown for vector-rag)
    for title in ("Answer correctness", "Citation precision", "Supersession catch rate", "Refusal accuracy",
                  "Invented-answer rate", "Latency", "Cost", "Paired differences"):
        assert f"## {title}" in text
    assert "| vector-rag | +75 pts [+50, +100] n=2 |" in text  # paired correctness difference, ours minus vector-rag


def test_a_derived_decision_in_the_evidence_chain_counts_when_its_quote_is_in_a_cited_record():
    """Our system puts the Decision that superseded or refined another into the Evidence Chain, even when it
    governs code outside the Anchor (so it is not among the answer's Decisions)."""
    superseder = EvidenceItem(node_id="decision:abc", kind="decision", quote="their descriptors may already be gone")
    invented = EvidenceItem(node_id="decision:def", kind="decision", quote="words no record holds")
    answer = Answer(anchor=ZONE, refused=False, confidence="Medium",
                    evidence_chain=[superseder, invented,
                                    EvidenceItem(node_id="pr:121026", kind="pr", quote="Zone configuration")],
                    sentences=[Sentence(text="Zones skip dropped indexes.", cites=["pr:121026"])])
    row = score(LOOKUP, record("L", answer), CORPUS, JUDGE)

    assert (row.cites, row.valid_cites) == (3, 2)
