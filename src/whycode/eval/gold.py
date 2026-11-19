"""The gold set: questions, their expected answers, the gold check and the human_verified gate.

Gold files are YAML lists under `eval/gold/` (`human.yaml`, `window.yaml`, the generated
`automatic.yaml`). A question counts toward scores only when it is `human_verified` and passes
`check_gold`: every gold quote is checked word for word against the raw corpus.

Each question becomes one or two scored `Case`s: a Held-out Window question is asked once as of
the cutoff (`@before`) and once with the window visible (`@after`).
"""

from __future__ import annotations

import datetime as dt
import hashlib
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from whycode.contract import Anchor
from whycode.eval.corpus import Corpus, is_verbatim

QuestionType = Literal["lookup", "multi_hop", "incident", "supersession", "unanswerable", "trap", "window"]
Split = Literal["dev", "test"]
UNANSWERABLE_TYPES = ("unanswerable", "trap")
DEV_SHARE = 0.3
ELISIONS = ("...", "…")


class GoldSetError(ValueError):
    """The gold set cannot be scored as asked."""


class _Gold(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class GoldEvidence(_Gold):
    node_id: str
    quote: str  # word for word from the record's title or text


class WindowAfter(_Gold):
    """The answer once the Held-out Window is visible."""

    gold_facts: list[str]
    gold_evidence: list[GoldEvidence] = []
    superseded_facts: list[str] = []  # true as of the cutoff, dead once the window is visible


class GoldQuestion(_Gold):
    id: str
    type: QuestionType
    origin: Literal["automatic", "human"]
    question: str
    anchor: Anchor | None = None
    answerable: bool = True
    gold_facts: list[str] = []  # atomic facts a correct answer states
    gold_evidence: list[GoldEvidence] = []
    superseded_facts: list[str] = []  # dead Decisions a correct answer never presents as live
    ablates: str | None = None  # unanswerable by ablation: hide this question's gold evidence
    exclude: list[str] = []  # node ids hidden from every system for this question (e.g. the answer key)
    after: WindowAfter | None = None  # Held-out Window questions only
    split: Split
    human_verified: bool = False
    note: str = ""


class GoldProblem(_Gold):
    question_id: str
    message: str


class Case(_Gold):
    """One scored item: what every system is asked, and what a correct answer looks like."""

    id: str
    question_id: str
    type: str
    question: str
    anchor: Anchor | None
    as_of: dt.date | None  # None = all history, including the Held-out Window
    exclude: frozenset[str]
    answerable: bool
    gold_facts: list[str]
    superseded_facts: list[str]


def load_gold(gold_dir: Path) -> list[GoldQuestion]:
    questions = []
    for path in sorted(gold_dir.glob("*.yaml")):
        for item in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
            questions.append(GoldQuestion.model_validate(item))
    return questions


def save_gold(path: Path, questions: Sequence[GoldQuestion]) -> None:
    items = []
    for q in questions:
        item = q.model_dump(mode="json", exclude_defaults=True)
        item["human_verified"] = q.human_verified  # the gate is always written, never implied
        items.append(item)
    path.write_text(yaml.safe_dump(items, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")


def assign_split(question_id: str) -> Split:
    """Deterministic dev/test assignment by id hash: about 30% dev, 70% test."""
    bucket = int(hashlib.sha256(question_id.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "dev" if bucket < DEV_SHARE else "test"


def select(questions: Sequence[GoldQuestion], split: Split, include_unverified: bool = False) -> list[GoldQuestion]:
    """The questions of one split that count: human-verified only (unverified allowed for dev smoke runs)."""
    if split == "test" and include_unverified:
        raise GoldSetError("the test split counts only human-verified questions")
    return [q for q in questions if q.split == split and (q.human_verified or include_unverified)]


def check_gold(questions: Sequence[GoldQuestion], corpus: Corpus, *, cutoff: dt.date,
               every: Sequence[GoldQuestion] | None = None) -> list[GoldProblem]:
    """Every problem that keeps a question from being scored. `every` resolves `ablates` targets."""
    by_id = {q.id: q for q in (every if every is not None else questions)}
    seen: Counter[str] = Counter()
    found: list[GoldProblem] = []
    for q in questions:
        seen[q.id] += 1
        problems = _structure(q, by_id) if seen[q.id] == 1 else ["duplicate question id"]
        problems += _evidence(q.gold_evidence, corpus, cutoff)
        if q.after is not None:
            problems += _evidence(q.after.gold_evidence, corpus, None)
        found += [GoldProblem(question_id=q.id, message=m) for m in problems]
    return found


def _structure(q: GoldQuestion, by_id: dict[str, GoldQuestion]) -> list[str]:
    out = []
    if not q.question.strip():
        out.append("empty question")
    if q.type in UNANSWERABLE_TYPES and q.answerable:
        out.append(f"a {q.type} question must be unanswerable")
    elif q.type not in UNANSWERABLE_TYPES and not q.answerable:
        out.append(f"a {q.type} question must be answerable")
    if q.answerable and not (q.gold_facts and q.gold_evidence):
        out.append("an answerable question needs gold_facts and gold_evidence")
    if q.type == "multi_hop" and len({e.node_id for e in q.gold_evidence}) < 2:
        out.append("a multi_hop question needs evidence from at least two records")
    if q.type == "supersession" and not q.superseded_facts:
        out.append("a supersession question needs superseded_facts")
    if (q.type == "window") != (q.after is not None):
        out.append("a window question needs an `after` answer" if q.type == "window"
                   else "only a window question has an `after` answer")
    if q.ablates is not None and not (q.ablates in by_id and by_id[q.ablates].answerable):
        out.append(f"ablates unknown or unanswerable question {q.ablates}")
    return out


def _evidence(evidence: Sequence[GoldEvidence], corpus: Corpus, cutoff: dt.date | None) -> list[str]:
    out = []
    for e in evidence:
        record = corpus.get(e.node_id)
        if any(mark in e.quote for mark in ELISIONS):
            out.append(f"quote uses elision (...): {e.quote[:60]}")
        elif record is None:
            out.append(f"unknown record {e.node_id}")
        elif not is_verbatim(e.quote, record.source_text):
            out.append(f"quote not verbatim in {e.node_id}: {e.quote[:60]}")
        elif cutoff is not None and not record.visible(cutoff):
            out.append(f"evidence {e.node_id} is dated {record.date}, after the cutoff")
    return out


def build_cases(selected: Sequence[GoldQuestion], every: Sequence[GoldQuestion], *, cutoff: dt.date) -> list[Case]:
    by_id = {q.id: q for q in every}
    cases = []
    for q in selected:
        exclude = frozenset(q.exclude)
        if q.ablates is not None:
            exclude |= {e.node_id for e in by_id[q.ablates].gold_evidence}
        common = dict(question_id=q.id, question=q.question, anchor=q.anchor, exclude=exclude,
                      answerable=q.answerable)
        if q.after is None:
            cases.append(Case(id=q.id, type=q.type, as_of=cutoff, gold_facts=q.gold_facts,
                              superseded_facts=q.superseded_facts, **common))
            continue
        cases.append(Case(id=f"{q.id}@before", type="window-before", as_of=cutoff, gold_facts=q.gold_facts,
                          superseded_facts=q.superseded_facts, **common))
        cases.append(Case(id=f"{q.id}@after", type="window-after", as_of=None, gold_facts=q.after.gold_facts,
                          superseded_facts=q.after.superseded_facts, **common))
    return cases
