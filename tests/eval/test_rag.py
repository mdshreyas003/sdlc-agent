"""Vector-RAG baseline: same corpus, same answering model, answers through the answer contract."""

import re

from eval_support import CUTOFF, FIXTURE_RECORDS, HashEmbedder, ScriptedModel, anthropic_client, text_reply

from whycode.contract import Anchor
from whycode.eval.baselines import BaselineAnswer, CitedSentence, EvidenceQuote, FoundDecision
from whycode.eval.corpus import CorpusRecord, MemoryCorpus
from whycode.eval.gold import Case
from whycode.eval.models import AnthropicStructured
from whycode.eval.rag import VectorIndex, VectorRag, chunk_record
from whycode.eval.runner import Query
from whycode.eval.scoring import check_citations

CORPUS = MemoryCorpus(FIXTURE_RECORDS)
ZONE = "Why does zone configuration skip dropped indexes?"


def cite_first_passage(output, system, user):
    node_id = re.search(r'<passage node_id="([^"]+)"', user)[1]
    quote = "ignores indexes in the DROP state" if node_id == "pr:121026" else "made up quote"
    return BaselineAnswer(
        refused=False, confidence="Medium",
        decisions=[FoundDecision(choice="Skip dropped indexes", rationale="Descriptors may be gone", quote=quote,
                                 source_id=node_id, date="2024-06-22", status="live")],
        evidence=[EvidenceQuote(node_id=node_id, quote=quote)],
        sentences=[CitedSentence(text="Dropped indexes are skipped.", cites=[node_id])])


def rag(model):
    return VectorRag(CORPUS, VectorIndex(CORPUS.records(), HashEmbedder()), model, prompt="RAG PROMPT",
                     answer_model="claude-opus-5-5")


def test_answers_from_the_best_matching_record_with_verbatim_citations():
    model = ScriptedModel(cite_first_passage)
    query = Query(question=ZONE, anchor=Anchor(kind="file", id="pkg/sql/configure_zone.go"), as_of=CUTOFF)

    result = rag(model)(query)

    answer = result.answer
    assert (answer.anchor, answer.refused) == (query.anchor, False)
    assert [(e.node_id, e.kind) for e in answer.evidence_chain] == [("pr:121026", "pr")]
    assert answer.decisions[0].id == "pr:121026" and answer.decisions[0].status == "live"
    assert result.usage.cost_usd() == (1000 * 4 + 100 * 20) / 1e6
    assert model.calls[0][0] == "RAG PROMPT"
    case = Case(id="c", question_id="c", type="lookup", question=ZONE, anchor=None, as_of=CUTOFF,
                exclude=frozenset(), answerable=True, gold_facts=["f"], superseded_facts=[])
    assert check_citations(answer, case, CORPUS) == (1, 1)


def test_ablated_and_post_cutoff_records_never_reach_the_model():
    model = ScriptedModel(cite_first_passage)
    rag(model)(Query(question="Why was the force_declarative setting reverted after upgrades failed?",
                     as_of=CUTOFF, exclude=frozenset({"pr:125000"})))

    shown = set(re.findall(r'<passage node_id="([^"]+)"', model.calls[0][1]))
    hidden = {"pr:125000",  # ablated
              "pr:127500", "issue:130001"}  # dated inside the Held-out Window
    assert shown == {r.id for r in FIXTURE_RECORDS} - hidden


def test_window_visible_query_can_see_post_cutoff_records():
    model = ScriptedModel(cite_first_passage)
    rag(model)(Query(question="Why was the force_declarative setting reverted after upgrades failed?", as_of=None))

    assert 'node_id="pr:127500"' in model.calls[0][1]


def test_nothing_visible_means_a_refusal_without_a_model_call():
    model = ScriptedModel(cite_first_passage)
    everything = frozenset(r.id for r in FIXTURE_RECORDS)

    result = rag(model)(Query(question=ZONE, as_of=CUTOFF, exclude=everything))

    assert result.answer.refused and model.calls == []


def test_long_records_are_chunked_with_overlap_and_nothing_is_lost():
    words = " ".join(f"w{i}" for i in range(1200))
    chunks = chunk_record(CorpusRecord(id="rfc:x", kind="rfc", text=words), size=500, overlap=100)

    assert all(len(c.text) <= 500 for c in chunks) and len(chunks) > 10
    assert {w for c in chunks for w in c.text.split()} == set(words.split())
    assert chunks[0].text.split()[-1] in chunks[1].text  # consecutive chunks overlap


def test_vectors_are_cached_by_model_and_content(tmp_path):
    class Counting(HashEmbedder):
        calls = 0

        def embed_documents(self, texts):
            Counting.calls += 1
            return super().embed_documents(texts)

    VectorIndex(CORPUS.records(), Counting(), cache_dir=tmp_path)
    again = VectorIndex(CORPUS.records(), Counting(), cache_dir=tmp_path)

    assert Counting.calls == 1 and again.matrix.shape[0] == len(again.chunks)


def test_runs_end_to_end_through_the_anthropic_adapter():
    requests = []
    reply = cite_first_passage(None, None, '<passage node_id="pr:121026"')
    client = anthropic_client([text_reply(reply)], requests)

    result = rag(AnthropicStructured(client, "claude-opus-5-5"))(Query(question=ZONE, as_of=CUTOFF))

    assert result.answer.evidence_chain[0].node_id == "pr:121026"
    assert result.usage.calls[0].model == "claude-opus-5-5"
    body = requests[0]
    assert body["model"] == "claude-opus-5-5"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert "temperature" not in body and "fallbacks" not in body
