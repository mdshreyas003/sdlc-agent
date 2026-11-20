"""Gold set: verbatim quote check against the raw corpus, the human_verified gate, splits and cases."""

import pytest
from eval_support import CUTOFF, FIXTURE_RECORDS

from whycode.contract import Anchor
from whycode.eval.corpus import MemoryCorpus, is_verbatim
from whycode.eval.gold import (
    GoldEvidence,
    GoldQuestion,
    GoldSetError,
    WindowAfter,
    assign_split,
    build_cases,
    check_gold,
    load_gold,
    save_gold,
    select,
)

CORPUS = MemoryCorpus(FIXTURE_RECORDS)


def question(**kw):
    base = dict(id="Q1", type="lookup", origin="human", question="Why does zone configuration skip dropped indexes?",
                gold_facts=["Dropped indexes may already have lost their descriptors"],
                gold_evidence=[GoldEvidence(node_id="pr:121026", quote="because their descriptors may already be gone")],
                split="dev", human_verified=True)
    return GoldQuestion(**(base | kw))


def problems(*questions):
    return [(p.question_id, p.message) for p in check_gold(list(questions), CORPUS, cutoff=CUTOFF)]


def test_verbatim_rule_forgives_only_whitespace():
    text = "Zone configuration now ignores indexes in the DROP state,\n  because their descriptors"
    assert is_verbatim("ignores indexes in the DROP state, because", text)
    assert not is_verbatim("ignores INDEXES in the drop state, because", text)  # case matters
    assert not is_verbatim("ignores indexes in the DROP state because", text)  # punctuation matters
    assert not is_verbatim("ignores indexes ... because", text)
    assert not is_verbatim("", text)


def test_a_verbatim_quote_passes_the_gold_check():
    assert problems(question()) == []


def test_quotes_are_checked_against_the_title_too():
    q = question(gold_evidence=[GoldEvidence(node_id="pr:121026", quote="skip dropped indexes when configuring zones")])
    assert problems(q) == []


def test_paraphrased_quote_unknown_record_and_elision_are_reported():
    q = question(gold_evidence=[
        GoldEvidence(node_id="pr:121026", quote="because the descriptors might be gone"),
        GoldEvidence(node_id="pr:999", quote="anything"),
        GoldEvidence(node_id="pr:121026", quote="Zone configuration ... gone"),
    ])
    found = problems(q)
    assert ("Q1", "quote not verbatim in pr:121026: because the descriptors might be gone") in found
    assert ("Q1", "unknown record pr:999") in found
    assert ("Q1", "quote uses elision (...): Zone configuration ... gone") in found
    assert len(found) == 3


def test_evidence_after_the_cutoff_is_invisible_to_a_pre_cutoff_question():
    q = question(gold_evidence=[GoldEvidence(node_id="pr:127500", quote="made upgrades fail")])
    assert problems(q) == [("Q1", "evidence pr:127500 is dated 2024-07-15, after the cutoff")]


def test_structure_rules():
    dup = question(id="Q1")
    no_facts = question(id="Q2", gold_facts=[])
    one_record_multi_hop = question(id="Q3", type="multi_hop")
    no_dead_facts = question(id="Q4", type="supersession")
    window_without_after = question(id="Q5", type="window")
    bad_ablation = question(id="Q6", type="unanswerable", answerable=False, gold_facts=[], gold_evidence=[],
                            ablates="Q404")
    answerable_trap = question(id="Q7", type="trap")

    found = problems(question(), dup, no_facts, one_record_multi_hop, no_dead_facts, window_without_after,
                     bad_ablation, answerable_trap)
    assert found == [
        ("Q1", "duplicate question id"),
        ("Q2", "an answerable question needs gold_facts and gold_evidence"),
        ("Q3", "a multi_hop question needs evidence from at least two records"),
        ("Q4", "a supersession question needs superseded_facts"),
        ("Q5", "a window question needs an `after` answer"),
        ("Q6", "ablates unknown or unanswerable question Q404"),
        ("Q7", "a trap question must be unanswerable"),
    ]


def test_window_after_evidence_may_come_from_the_window():
    q = question(type="window", after=WindowAfter(
        gold_facts=["The setting was reverted"], superseded_facts=["The setting forces declarative DDL"],
        gold_evidence=[GoldEvidence(node_id="pr:127500", quote="made upgrades fail")]))
    assert problems(q) == []


def test_only_human_verified_questions_count():
    qs = [question(id="V", human_verified=True), question(id="U", human_verified=False),
          question(id="T", split="test", human_verified=True)]

    assert [q.id for q in select(qs, "dev")] == ["V"]
    assert [q.id for q in select(qs, "dev", include_unverified=True)] == ["V", "U"]
    assert [q.id for q in select(qs, "test")] == ["T"]
    with pytest.raises(GoldSetError, match="test split counts only human-verified"):
        select(qs, "test", include_unverified=True)


def test_window_questions_become_a_before_and_an_after_case():
    q = question(id="W", type="window", anchor=Anchor(kind="setting", id="sql.schema.force_declarative"),
                 superseded_facts=[],
                 after=WindowAfter(gold_facts=["It was reverted"], superseded_facts=["It forces declarative DDL"],
                                   gold_evidence=[GoldEvidence(node_id="pr:127500", quote="made upgrades fail")]))
    before, after = build_cases([q], [q], cutoff=CUTOFF)

    assert (before.id, before.type, before.as_of, before.gold_facts) == (
        "W@before", "window-before", CUTOFF, ["Dropped indexes may already have lost their descriptors"])
    assert (after.id, after.type, after.as_of, after.gold_facts, after.superseded_facts) == (
        "W@after", "window-after", None, ["It was reverted"], ["It forces declarative DDL"])
    assert before.anchor == after.anchor == q.anchor


def test_unanswerable_by_ablation_hides_the_ablated_question_evidence():
    base = question(id="A")
    ablated = question(id="C", type="unanswerable", answerable=False, gold_facts=[], gold_evidence=[], ablates="A",
                       exclude=["rfc:20181003_schemas"], split="test")
    (case,) = build_cases([ablated], [base, ablated], cutoff=CUTOFF)

    assert case.exclude == frozenset({"pr:121026", "rfc:20181003_schemas"})
    assert not case.answerable and case.as_of == CUTOFF


def test_yaml_round_trip_keeps_every_field_and_always_writes_the_gate(tmp_path):
    qs = [question(), question(id="Q2", human_verified=False, anchor=Anchor(kind="file", id="pkg/sql/configure_zone.go"))]
    save_gold(tmp_path / "human.yaml", qs)

    assert load_gold(tmp_path) == qs
    assert (tmp_path / "human.yaml").read_text().count("human_verified:") == 2


def test_split_assignment_is_deterministic_and_about_thirty_percent_dev():
    splits = [assign_split(f"auto-{i}") for i in range(1000)]

    assert splits == [assign_split(f"auto-{i}") for i in range(1000)]
    assert 250 < splits.count("dev") < 350
