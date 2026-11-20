"""The fact-level judge and its agreement with hand labels."""

import datetime as dt

import pytest
from eval_support import ScriptedModel

from whycode.contract import Answer, DecisionView, Sentence
from whycode.eval.judge import (
    FactJudge,
    HandLabels,
    JudgeInput,
    LabelledAnswer,
    Verdict,
    agreement,
    cohen_kappa,
    load_labels,
    render_answer,
    save_labels,
)


def test_kappa_matches_a_worked_example():
    # judge/human: 5 yes-yes, 3 no-no, 1 yes-no, 1 no-yes -> po 0.8, pe 0.52, kappa 0.28 / 0.48
    pairs = [(True, True)] * 5 + [(False, False)] * 3 + [(True, False), (False, True)]
    assert cohen_kappa(pairs) == pytest.approx(0.58333, abs=1e-5)
    assert cohen_kappa([(True, True)] * 4) == 1.0


def labelled(id, facts, covered, human=True, **kw):
    kw.setdefault("labels", HandLabels(covered=covered))
    return LabelledAnswer(id=id, human_labelled=human, question=f"q {id}?", gold_facts=facts, answer=f"answer {id}",
                          **kw)


def test_agreement_counts_only_complete_human_labels():
    items = [
        labelled("a", ["f1", "f2"], [True, False]),
        labelled("b", ["f1"], [True], superseded_facts=["dead"],
                 labels=HandLabels(covered=[True], presented_as_live=[False], reports_change=True)),
        labelled("c", ["f1"], [True], human=False),  # a draft: never counted
        labelled("d", ["f1", "f2"], [True]),  # incomplete labels: never counted
    ]
    verdicts = {"q a?": Verdict(covered=[True, True]),
                "q b?": Verdict(covered=[True], presented_as_live=[False], reports_change=False)}

    result = agreement(items, lambda item: verdicts[item.question])

    # judgments: a f1 agree, a f2 disagree, b f1 agree, b dead agree, b reports_change disagree
    assert (result.answers, result.judgments, result.skipped) == (2, 5, 2)
    assert result.agreement == pytest.approx(0.6)
    assert result.correctness_mae == pytest.approx(0.25)  # a: |2-1|/2, b: 0
    assert not result.enough and "below the 15 required" in result.summary()


def test_fact_judge_pads_a_short_verdict_to_one_entry_per_fact():
    model = ScriptedModel(lambda output, system, user: Verdict(covered=[True]))
    judge = FactJudge(model, prompt="JUDGE PROMPT")

    verdict = judge(JudgeInput("Why?", "Because.", ("f1", "f2", "f3"), ("dead",)))

    assert verdict == Verdict(covered=[True, False, False], presented_as_live=[False], reports_change=False)


def test_rendered_answer_shows_decision_status_for_the_judge():
    answer = Answer(anchor=None, refused=False, confidence="High", sentences=[Sentence(text="It was reverted.", cites=[])],
                    decisions=[DecisionView(id="d1", choice="Run CREATE DATABASE declaratively.", rationale="Atomicity.",
                                            quote="q", date=dt.date(2023, 12, 1), status="superseded",
                                            superseded_by="d2", link="soft")])

    text = render_answer(answer)

    assert "[superseded, superseded by d2] Run CREATE DATABASE declaratively." in text
    assert text.endswith("Answer:\nIt was reverted.")


def test_labels_file_round_trips(tmp_path):
    items = [labelled("a", ["f1"], [True]), labelled("b", ["f1"], None, human=False)]
    save_labels(tmp_path / "labels.yaml", items)

    assert load_labels(tmp_path / "labels.yaml") == items
