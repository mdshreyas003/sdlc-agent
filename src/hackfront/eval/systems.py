"""The systems under test. Every system answers one question and returns the same record:

{system, answer, claims: [{text, status, cites: [{url, quote}]}], abstained, seconds, tokens, error}

B0  the LLM alone, no data
B1  lexical RAG (BM25 top-k passages of the same artifacts, same passage length and same synthesis prompt as S), no graph,
    no verification. # ponytail: BM25 not dense vectors (no embeddings endpoint in llm.py); add one if a rival uses it
S-  our agent with the claim verifier switched off (quotes and URLs unchecked)
S   our full agent

`exclude` = canon_url set of artifacts that must be treated as absent (tier-C ablation); every system honours it.
abstained = the system established nothing: no claim is "supported" with at least one citation (B0 cannot cite, so it
abstains when it says it does not know). A "supported" claim with no cite is not an established fact.
"""

from __future__ import annotations

import math
import re
import time
from collections import Counter

from pydantic import BaseModel

from ..agent import llm, prompts as P
from ..agent.flow import render, stream
from ..agent.harness import TEXT_LEN, canon_url
from ..agent.verify import lax

TOP_K = 8
WORD = re.compile(r"[a-z0-9_.\-]+")

CLOSED_BOOK = """Answer this software-engineering "why" question from your own knowledge only. You have no documents.
If you do not actually know the reason, say so instead of guessing.

Question: {question}"""


class ClosedBook(BaseModel):
    answer: str
    knows: bool  # false = you cannot establish the reason


class BM25:
    """Okapi BM25 over {url: text}; stdlib only."""

    def __init__(self, docs: dict[str, str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tf = {u: Counter(WORD.findall(t.lower())) for u, t in docs.items()}
        self.len = {u: sum(c.values()) for u, c in self.tf.items()}
        self.avg = sum(self.len.values()) / max(len(self.len), 1)
        df = Counter(w for c in self.tf.values() for w in c)
        n = len(self.tf)
        self.idf = {w: math.log(1 + (n - d + 0.5) / (d + 0.5)) for w, d in df.items()}

    def top(self, query: str, k: int, skip: set[str] = frozenset()) -> list[str]:
        q = [w for w in WORD.findall(query.lower()) if w in self.idf]
        score = {u: sum(self.idf[w] * c[w] * (self.k1 + 1) / (c[w] + self.k1 * (1 - self.b + self.b * self.len[u] / self.avg))
                        for w in q if c[w]) for u, c in self.tf.items() if u not in skip}
        return [u for u, s in sorted(score.items(), key=lambda kv: -kv[1])[:k] if s > 0]


def graph_artifacts(driver, scopes: list[str]) -> dict[str, dict]:
    """canon_url -> artifact row for every non-stub artifact in the workspace scopes (same data the agent sees)."""
    from ..config import neo4j_database

    records, _, _ = driver.execute_query(
        "MATCH (a:Artifact) WHERE coalesce(a.is_stub, false) = false AND a.scope IN $scopes "
        "RETURN a.canonical_id AS id, a.record_kind AS kind, a.title AS title, a.text AS text, a.source_uri AS url, "
        "a.event_time AS time, coalesce(a.change_paths, []) AS paths",
        scopes=scopes, database_=neo4j_database(), routing_="r")
    return {canon_url(r["url"]): r.data() for r in records if r["url"]}


def _record(system: str, claims: list[dict], t0: float, tok0: int, error: str | None = None, answer: str = "",
            cites_needed: bool = True) -> dict:
    established = any(c["status"] == "supported" and (c["cites"] or not cites_needed) for c in claims)
    return {"system": system, "claims": claims, "abstained": not established,
            "answer": answer or " ".join(c["text"] for c in claims if c["status"] != "unknown"),
            "seconds": round(time.perf_counter() - t0, 2), "tokens": llm.TOKENS[0] - tok0, "error": error}


def b0(question: str, provider: str, **_) -> dict:
    t0, tok0 = time.perf_counter(), llm.TOKENS[0]
    out = llm.structured(provider, CLOSED_BOOK, ClosedBook, None, question=question)
    return _record("B0", [{"text": out.answer, "status": "supported" if out.knows else "unknown", "cites": []}], t0, tok0,
                   cites_needed=False)


def b1(question: str, provider: str, arts: dict[str, dict], index: BM25, exclude: set[str], **_) -> dict:
    t0, tok0 = time.perf_counter(), llm.TOKENS[0]
    urls = index.top(question, TOP_K, skip=exclude)
    evidence = {u: {"id": u, "kind": arts[u]["kind"], "time": arts[u]["time"], "url": u, "title": arts[u]["title"],
                    "paths": "", "text": (arts[u]["text"] or "")[:TEXT_LEN]} for u in urls}
    ans = lax(llm.structured(provider, P.SYNTHESIZE, P.Synthesis, None, task=P.MODE_TASK["why"], question=question,
                             sufficient=bool(urls), evidence=render(evidence, TEXT_LEN)).model_dump(), evidence, bool(urls)) \
        if urls else {"claims": [{"text": "No passage matched.", "status": "unknown", "cites": []}]}
    return _record("B1", [{"text": c["text"], "status": c["status"],
                           "cites": [{"url": ci["node"], "quote": ci.get("quote", "")} for ci in c["cites"]]}
                          for c in ans["claims"]], t0, tok0)


def agent(question: str, provider: str, driver, scopes: list[str], exclude: set[str], check_claims: bool, workspace: str,
          **_) -> dict:
    t0, tok0 = time.perf_counter(), llm.TOKENS[0]
    name = "S" if check_claims else "S-"
    for ev in stream(question, "why", provider, None, driver, None, scopes, workspace, exclude, check_claims):
        if ev["event"] == "error":
            return _record(name, [], t0, tok0, error=ev["message"])
        if ev["event"] == "done":
            state = ev["state"]
            ev_by_id = state.get("evidence") or {}
            claims = [{"text": c["text"], "status": c["status"],
                       "cites": [{"url": canon_url(ev_by_id[ci["node"]].get("url")), "quote": ci.get("quote", "")}
                                 for ci in c["cites"] if ci["node"] in ev_by_id]}
                      for c in state["final"]["claims"]]
            return _record(name, claims, t0, tok0)
    return _record(name, [], t0, tok0, error="no result")
