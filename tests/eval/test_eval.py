"""Benchmark machinery (EVAL-4): no Neo4j, no network, no real LLM."""

import json

import pytest

from hackfront.agent import llm
from hackfront.agent.harness import Harness, canon_url
from hackfront.agent.verify import lax, verify
from hackfront.eval import run as R, score as S, systems as X

DOCS = {"u/a": "tiered storage uploads closed segments", "u/b": "idempotent producer sequence numbers",
        "u/c": "raft quorum voters need explicit ids"}


def test_bm25_ranks_and_skips():
    idx = X.BM25(DOCS)
    assert idx.top("why do voters need ids", 3)[0] == "u/c"
    assert "u/c" not in idx.top("why do voters need ids", 3, skip={"u/c"})
    assert idx.top("zzz", 3) == []


def test_canon_url_keeps_only_jira_comment_query():
    assert canon_url("https://s/archives/C/p1?thread_ts=1&cid=C") == "https://s/archives/C/p1"
    assert canon_url("https://j/browse/K-1?focusedCommentId=9") == "https://j/browse/K-1?focusedCommentId=9"


def test_harness_exclude_hides_ablated_artifacts():
    h = Harness(None, exclude={"u/a"})
    assert [r["url"] for r in h._keep([{"url": "u/a?x=1"}, {"url": "u/b"}])] == ["u/b"]


def test_lax_keeps_what_verify_drops():
    ev = {"n1": {"id": "n1", "url": "u/a", "text": "closed segments are uploaded"}}
    ans = {"summary": "", "claims": [{"text": "t", "status": "supported", "note": "",
                                      "cites": [{"id": "n1", "quote": "made up words"}]}]}
    assert verify(ans, ev, True)["claims"][0]["status"] == "inferred"
    assert lax(ans, ev, True)["claims"][0]["cites"] == [{"node": "n1", "quote": "made up words"}]


def test_bootstrap():
    assert S.boot([1.0, 1.0, 1.0]) == (1.0, 1.0, 1.0)
    m, lo, hi = S.boot([0, 1] * 20)
    assert lo < m < hi
    assert S.boot_diff({"a": 1.0, "b": 1.0}, {"a": 0.0, "b": 0.0, "c": 5.0})[0] == 1.0


def q(tier, **kw):
    return {"id": "Q1", "tier": tier, "question": "why?", "gold_facts": ["f1", "f2"], "split": "dev",
            "gold_evidence": [{"url": "u/a", "quote": "x"}, {"url": "u/b", "quote": "y"}], **kw}


def ans(claims, abstained=False):
    return {"claims": claims, "abstained": abstained, "answer": "ans", "seconds": 1.0, "tokens": 10}


def test_per_answer_answerable_scores_citations_and_recall():
    claim = {"text": "t", "status": "supported", "cites": [{"url": "u/a", "quote": "closed segments"},
                                                          {"url": "u/zzz", "quote": "invented"}]}
    row = S.per_answer(q("A"), ans([claim]), {"u/a": "tiered storage uploads closed segments"}, lambda *_: 0.5)
    assert (row["cites"], row["valid"], row["recall"], row["correct"], row["wrongly_refused"]) == (2, 1, 0.5, 0.5, 0.0)


def test_per_answer_unanswerable_counts_false_answers():
    claim = {"text": "t", "status": "supported", "cites": []}
    assert S.per_answer(q("C"), ans([claim]), {}, None)["false_answer"] == 1.0
    assert S.per_answer(q("T"), ans([], abstained=True), {}, None)["false_answer"] == 0.0


def test_report_renders_all_sections():
    rows = [{"qid": f"Q{i}", "tier": t, "system": s, "cites": 2, "valid": 1, "seconds": 1.0, "tokens": 5, "error": False,
             **({"correct": 1.0, "recall": 1.0, "wrongly_refused": 0.0} if t == "A" else {"false_answer": float(s == "B1")})}
            for i, t in enumerate("AACC") for s in ("B1", "S")]
    text = S.report(rows, ["B1", "S"])
    assert "## Answerable" in text and "false-answer" in text and "Paired difference" in text and "50%" in text


def test_collect_resumes_records_errors_and_ablates_only_tier_c(tmp_path):
    calls = []

    def runner(question, exclude):
        calls.append(exclude)
        if len(calls) == 2:
            raise RuntimeError("boom")
        return {"system": "S", **ans([])}

    qs = [q("A", id="Q1"), q("C", id="Q2"), q("A", id="Q3")]
    path = tmp_path / "answers.jsonl"
    R.collect(qs, {"S": runner}, path)
    rows = [json.loads(l) for l in path.read_text().splitlines()]
    assert [r["qid"] for r in rows] == ["Q1", "Q2", "Q3"] and rows[1]["error"].startswith("RuntimeError")
    assert calls == [set(), {"u/a", "u/b"}, set()]
    R.collect(qs, {"S": runner}, path)  # resume: nothing left to run
    assert len(calls) == 3


class FakeLLM:
    chat = completions = property(lambda self: self)

    def create(self, model, messages, max_tokens):
        title = json.loads(messages[0]["content"].split("matching this JSON Schema:\n")[-1])["title"]
        out = {"ClosedBook": {"answer": "no idea", "knows": False},
               "Synthesis": {"summary": "", "gaps": [], "claims": [
                   {"text": "uploads", "status": "supported", "note": "", "cites": [{"id": "u/a", "quote": "closed segments"}]}]}}[title]
        msg = type("M", (), {"content": json.dumps(out)})
        return type("R", (), {"choices": [type("C", (), {"message": msg})], "usage": type("U", (), {"total_tokens": 7})})


@pytest.fixture
def fake_llm():
    llm._clients["azure"] = FakeLLM()
    yield
    llm._clients.pop("azure", None)


def test_b0_and_b1_use_same_record_shape(fake_llm):
    arts = {u: {"kind": "x", "time": None, "title": "", "text": t} for u, t in DOCS.items()}
    a0 = X.b0("why upload segments?", "azure")
    assert a0["abstained"] and a0["tokens"] == 7 and a0["claims"][0]["cites"] == []
    a1 = X.b1("why upload closed segments?", "azure", arts=arts, index=X.BM25(DOCS), exclude=set())
    assert not a1["abstained"] and a1["claims"][0]["cites"] == [{"url": "u/a", "quote": "closed segments"}]
    gone = X.b1("why upload closed segments?", "azure", arts=arts, index=X.BM25(DOCS), exclude={"u/a"})
    assert gone["claims"][0]["cites"] == [] or gone["claims"][0]["cites"][0]["url"] != "u/a"


def test_supported_claim_without_cite_is_not_an_answer():
    bare = X._record("B1", [{"text": "the evidence does not say", "status": "supported", "cites": []}], 0.0, 0)
    cited = X._record("B1", [{"text": "t", "status": "supported", "cites": [{"url": "u/a", "quote": ""}]}], 0.0, 0)
    assert bare["abstained"] and not cited["abstained"]
