"""What both baselines ask the answering model for, and how it maps onto the answer contract.

The baselines are not verified: whatever node ids and quotes the model writes go into the
Answer as-is, so citation precision measures them honestly against the raw corpus.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, Field

from whycode.contract import Answer, DecisionView, EvidenceItem, Sentence
from whycode.eval.corpus import CorpusRecord
from whycode.eval.runner import Query


class CitedSentence(BaseModel):
    text: str
    cites: list[str] = Field(description="node ids of the records this sentence rests on")


class FoundDecision(BaseModel):
    choice: str = Field(description="what was chosen")
    rationale: str = Field(description="why it was chosen")
    quote: str = Field(description="a word-for-word quote from the source record stating the choice or its reason")
    source_id: str = Field(description="node id of the record the quote comes from")
    date: str = Field(description="date of the source record, YYYY-MM-DD")
    status: Literal["live", "superseded", "refined"]
    superseded_by: str | None = Field(default=None, description="node id of the record that superseded it")


class EvidenceQuote(BaseModel):
    node_id: str
    quote: str = Field(description="word-for-word quote from that record")


class BaselineAnswer(BaseModel):
    refused: bool = Field(description="true when the records do not establish the reason")
    confidence: Literal["High", "Medium", "Low"]
    decisions: list[FoundDecision]
    evidence: list[EvidenceQuote]
    sentences: list[CitedSentence]


def render_query(query: Query) -> str:
    about = f"\nCode Entity asked about: {query.anchor.kind} `{query.anchor.id}`" if query.anchor else ""
    return f"Question: {query.question}{about}"


def refusal(query: Query, text: str) -> Answer:
    return Answer(anchor=query.anchor, refused=True, confidence="Low", sentences=[Sentence(text=text, cites=[])])


def to_answer(found: BaselineAnswer, query: Query, lookup: Callable[[str], CorpusRecord | None]) -> Answer:
    decisions = []
    for d in found.decisions:
        source = lookup(d.source_id)
        try:
            date = dt.date.fromisoformat(d.date)
        except ValueError:
            if source is None or source.date is None:
                continue  # no date can be given without inventing one
            date = source.date
        decisions.append(DecisionView(id=d.source_id, choice=d.choice, rationale=d.rationale, quote=d.quote,
                                      date=date, status=d.status, superseded_by=d.superseded_by, link="soft"))
    evidence = []
    for e in found.evidence:
        record = lookup(e.node_id)
        evidence.append(EvidenceItem(node_id=e.node_id, kind=record.kind if record else "unknown",
                                     url=record.url if record else None, quote=e.quote))
    return Answer(anchor=query.anchor, refused=found.refused, confidence=found.confidence, decisions=decisions,
                  evidence_chain=evidence, sentences=[Sentence(text=s.text, cites=s.cites) for s in found.sentences])
