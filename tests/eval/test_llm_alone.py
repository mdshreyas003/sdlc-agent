"""LLM-alone baseline: the same answering model with no retrieval at all, answering through the answer contract."""

from eval_support import CUTOFF, FIXTURE_RECORDS, ScriptedModel

from whycode.contract import Anchor
from whycode.eval.baselines import BaselineAnswer, CitedSentence, EvidenceQuote, FoundDecision
from whycode.eval.corpus import MemoryCorpus
from whycode.eval.gold import Case
from whycode.eval.llm_alone import LlmAlone
from whycode.eval.runner import Query
from whycode.eval.scoring import check_citations

CORPUS = MemoryCorpus(FIXTURE_RECORDS)
ZONE = "Why does zone configuration skip dropped indexes?"


def from_memory(output, system, user):
    """What a model answering from memory might say: one real record with a real quote, one invented record."""
    return BaselineAnswer(
        refused=False, confidence="High",
        decisions=[FoundDecision(choice="Skip dropped indexes", rationale="Descriptors may be gone",
                                 quote="ignores indexes in the DROP state", source_id="pr:121026", date="2024-06-22",
                                 status="live")],
        evidence=[EvidenceQuote(node_id="pr:121026", quote="ignores indexes in the DROP state"),
                  EvidenceQuote(node_id="pr:555555", quote="zone configs are cached")],
        sentences=[CitedSentence(text="Dropped indexes are skipped.", cites=["pr:121026", "pr:555555"])])


def llm_alone(model):
    return LlmAlone(CORPUS, model, prompt="LLM ALONE PROMPT", answer_model="claude-opus-5-5")


def says_what_it_was_told(output, system, user):
    """A model that can only repeat what it was shown: the question, the Code Entity, the as-of date, and the id of
    any record whose id or text reached it (so a leaked record shows up as a citation)."""
    told = [probe for probe in (ZONE, "pkg/sql/configure_zone.go", CUTOFF.isoformat()) if probe in user]
    leaked = [r.id for r in FIXTURE_RECORDS if r.id in user or r.text[:40] in user]
    return BaselineAnswer(refused=False, confidence="Low", decisions=[],
                          evidence=[EvidenceQuote(node_id=i, quote="") for i in leaked],
                          sentences=[CitedSentence(text=f"Told: {t}", cites=leaked) for t in told])


def test_the_model_is_told_the_question_the_code_entity_and_the_date_but_never_a_record():
    query = Query(question=ZONE, anchor=Anchor(kind="file", id="pkg/sql/configure_zone.go"), as_of=CUTOFF)

    answer = llm_alone(ScriptedModel(says_what_it_was_told))(query).answer

    # The only way it can honour as_of is to be told the date.
    assert [s.text for s in answer.sentences] == [f"Told: {ZONE}", "Told: pkg/sql/configure_zone.go",
                                                  "Told: 2024-06-30"]
    assert answer.evidence_chain == []  # no record reached it


def test_its_answer_goes_through_the_contract_unverified_so_invented_citations_count_against_it():
    result = llm_alone(ScriptedModel(from_memory))(Query(question=ZONE, as_of=CUTOFF))

    answer = result.answer
    assert answer.refused is False and answer.confidence == "High"
    assert [(e.node_id, e.kind) for e in answer.evidence_chain] == [("pr:121026", "pr"), ("pr:555555", "unknown")]
    assert result.usage.cost_usd() == (1000 * 4 + 100 * 20) / 1e6
    case = Case(id="c", question_id="c", type="lookup", question=ZONE, anchor=None, as_of=CUTOFF,
                exclude=frozenset(), answerable=True, gold_facts=["f"], superseded_facts=[])
    assert check_citations(answer, case, CORPUS) == (2, 1)


def test_a_window_visible_query_says_all_history_is_in_scope():
    answer = llm_alone(ScriptedModel(says_what_it_was_told))(Query(question=ZONE, as_of=None)).answer

    assert [s.text for s in answer.sentences] == [f"Told: {ZONE}"]  # no as-of date
