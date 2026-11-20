"""Per-item metrics and the results table.

Every system is scored on the same Cases through the answer contract:

- answer correctness: share of gold facts the judge finds in the answer (answerable cases; a refusal scores 0)
- citation precision: share of the distinct node ids an answer cites that resolve to a record the
  system could see (not ablated, not after its as-of date) with every attached quote verbatim. A
  derived Decision id (in the Decisions or the Evidence Chain) counts when its quote is verbatim in a record
  the answer cites.
- supersession catch rate: cases with superseded facts; caught when the answer reports the change
  and presents no superseded fact as live
- refusal accuracy: refused exactly when the case is unanswerable
- invented-answer rate: unanswerable cases (ablated, traps) the system answered anyway
- cost (US$) and latency (seconds) per case

The table shows each metric per question type with a 95% bootstrap interval, plus paired
differences between a reference system and every other system.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from pydantic import BaseModel

from whycode.contract import Answer
from whycode.eval.corpus import Corpus, CorpusRecord, is_verbatim
from whycode.eval.gold import Case
from whycode.eval.judge import Judge, JudgeInput, Verdict, render_answer
from whycode.eval.runner import AnswerRecord
from whycode.eval.stats import N_BOOT, SEED, boot, boot_diff, fmt

TYPE_ORDER = ("lookup", "multi_hop", "incident", "supersession", "window-before", "window-after", "unanswerable", "trap")


class ItemScore(BaseModel):
    case_id: str
    question_id: str
    type: str
    system: str
    correctness: float | None = None
    citation_precision: float | None = None
    cites: int = 0
    valid_cites: int = 0
    supersession_caught: float | None = None
    refusal_correct: float
    invented: float | None = None
    seconds: float
    cost_usd: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    error: bool = False
    verdict: Verdict | None = None


def score(case: Case, record: AnswerRecord, corpus: Corpus, judge: Judge) -> ItemScore:
    usage = record.usage
    base = dict(case_id=case.id, question_id=case.question_id, type=case.type, system=record.system,
                seconds=record.seconds, cost_usd=usage.cost_usd() if usage else None,
                input_tokens=usage.input_tokens if usage else 0, output_tokens=usage.output_tokens if usage else 0)
    answer = record.answer
    if record.error or answer is None:
        return ItemScore(**base, error=True, refusal_correct=0.0,
                         correctness=0.0 if case.answerable else None,
                         invented=None if case.answerable else 0.0,
                         supersession_caught=0.0 if case.superseded_facts else None)
    cites, valid = check_citations(answer, case, corpus)
    row = ItemScore(**base, cites=cites, valid_cites=valid, citation_precision=valid / cites if cites else None,
                    refusal_correct=float(answer.refused == (not case.answerable)),
                    invented=None if case.answerable else float(not answer.refused))
    if case.answerable or case.superseded_facts:
        verdict = None if answer.refused else judge(JudgeInput(
            case.question, render_answer(answer), tuple(case.gold_facts), tuple(case.superseded_facts)))
        if case.answerable:
            row.correctness = sum(verdict.covered) / len(case.gold_facts) if verdict and case.gold_facts else 0.0
        if case.superseded_facts:
            row.supersession_caught = float(bool(verdict) and verdict.reports_change
                                            and not any(verdict.presented_as_live))
        row.verdict = verdict
    return row


def check_citations(answer: Answer, case: Case, corpus: Corpus) -> tuple[int, int]:
    """(distinct node ids cited, how many of them are valid) for one answer."""
    quotes: dict[str, list[str]] = {}
    for item in answer.evidence_chain:
        quotes.setdefault(item.node_id, []).extend([item.quote] if item.quote else [])
    for decision in answer.decisions:
        quotes.setdefault(decision.id, []).append(decision.quote)
    for sentence in answer.sentences:
        for node_id in sentence.cites:
            quotes.setdefault(node_id, [])

    def visible(node_id: str) -> CorpusRecord | None:
        record = corpus.get(node_id)
        return record if record is not None and record.visible(case.as_of, case.exclude) else None

    records = {n: r for n in quotes if (r := visible(n)) is not None}
    decisions = {d.id: d.quote for d in answer.decisions}
    # A derived Decision may also appear only in the Evidence Chain (e.g. the one that superseded another).
    decisions |= {e.node_id: e.quote for e in answer.evidence_chain if e.kind == "decision" and e.quote
                  and e.node_id not in decisions}

    def valid(node_id: str) -> bool:
        if node_id in records:
            return all(is_verbatim(q, records[node_id].source_text) for q in quotes[node_id])
        if node_id in decisions:  # a derived Decision: grounded in a record this answer cites
            return any(is_verbatim(decisions[node_id], r.source_text) for r in records.values())
        return False

    return len(quotes), sum(valid(n) for n in quotes)


# --- the results table ---------------------------------------------------------------------------

Metric = tuple[str, str, str, str]  # (field, title, better, format kind)
METRICS: tuple[Metric, ...] = (
    ("correctness", "Answer correctness", "higher is better", "pct"),
    ("citation_precision", "Citation precision", "higher is better", "pct"),
    ("supersession_caught", "Supersession catch rate", "higher is better", "pct"),
    ("refusal_correct", "Refusal accuracy", "higher is better", "pct"),
    ("invented", "Invented-answer rate", "lower is better", "pct"),
    ("seconds", "Latency", "seconds per case, lower is better", "num"),
    ("cost_usd", "Cost", "US$ per case, lower is better", "usd"),
)
PAIRED = ("correctness", "supersession_caught", "refusal_correct", "invented")


def report(scores: Sequence[ItemScore], systems: Sequence[str], *, header: str, reference: str | None = None,
           n_boot: int = N_BOOT, seed: int = SEED) -> str:
    def values(system: str, field: str, keep: Callable[[ItemScore], bool]) -> dict[str, float]:
        return {s.case_id: v for s in scores if s.system == system and keep(s)
                and (v := getattr(s, field)) is not None}

    def cell(vals: dict[str, float], kind: str) -> str:
        return f"{fmt(boot(list(vals.values()), n_boot, seed), kind)} n={len(vals)}" if vals else "-"  # type: ignore[arg-type]

    present = {s.type for s in scores}
    types = [t for t in TYPE_ORDER if t in present] + sorted(present - set(TYPE_ORDER))
    out = [header.rstrip(), "",
           "Each cell: mean over cases, 95% bootstrap interval, number of cases. "
           "Differences smaller than the interval width are noise.", ""]
    for field, title, better, kind in METRICS:
        out += [f"## {title} ({better})", "", "| question type | " + " | ".join(systems) + " |",
                "|---|" + "---|" * len(systems)]
        for t in [*types, "all"]:
            keep = (lambda s: True) if t == "all" else (lambda s, t=t: s.type == t)
            row = [cell(values(name, field, keep), kind) for name in systems]
            if t != "all" and all(c == "-" for c in row):
                continue
            out.append(f"| {t} | " + " | ".join(row) + " |")
        out.append("")
    errors = {name: sum(s.error for s in scores if s.system == name) for name in systems}
    out += ["Errors (failed calls, scored as failures): " + ", ".join(f"{k} {v}" for k, v in errors.items()), ""]
    if reference in systems:
        everyone = lambda s: True  # noqa: E731
        out += [f"## Paired differences ({reference} minus each system, all cases both answered)", "",
                "| vs | " + " | ".join(t for f, t, *_ in METRICS if f in PAIRED) + " |", "|---|" + "---|" * len(PAIRED)]
        for name in systems:
            if name == reference:
                continue
            cells = []
            for field in PAIRED:
                a, b = values(reference, field, everyone), values(name, field, everyone)
                shared = len(a.keys() & b.keys())
                cells.append(f"{fmt(boot_diff(a, b, n_boot, seed), 'diff')} n={shared}" if shared else "-")
            out.append(f"| {name} | " + " | ".join(cells) + " |")
        out.append("")
    return "\n".join(out)
