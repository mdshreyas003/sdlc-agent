"""Scoring: five metrics per system and tier, with bootstrap confidence intervals (FR-23).

Per answered question (tiers A/B, "answerable"):  correct (judge: share of gold facts covered), recall (gold artifacts
cited), wrongly_refused (system abstained).
Per unanswerable question (tiers C/N/T):          false_answer (system claimed something as supported).
Over all answers:                                  hallucinated-citation rate (cites whose url/quote is not in the graph),
                                                   seconds and tokens per question.
Judge output is an LLM opinion; audit a sample by hand before quoting numbers (see data/EVAL_PLAN.md).
"""

from __future__ import annotations

import random
import statistics

from pydantic import BaseModel

from ..agent import llm

ANSWERABLE, SHOULD_ABSTAIN = ("A", "B"), ("C", "N", "T")

JUDGE = """You are grading an answer to a software-engineering question against a list of required facts.
For each required fact, say whether the answer states it or clearly implies it. Judge only the answer text, not your
own knowledge. An answer that refuses or says the reason is unknown covers no fact.

Question: {question}
Required facts (in order):
{facts}

Answer:
{answer}"""


class Judge(BaseModel):
    covered: list[bool]  # one entry per required fact, same order


def judge(provider: str, question: str, facts: list[str], answer: str) -> float:
    if not answer.strip() or not facts:
        return 0.0
    out = llm.structured(provider, JUDGE, Judge, None, question=question,
                         facts="\n".join(f"{i}. {f}" for i, f in enumerate(facts, 1)), answer=answer).covered
    out = (out + [False] * len(facts))[: len(facts)]
    return sum(out) / len(facts)


def squash(text: str) -> str:
    return " ".join((text or "").split()).casefold()


def per_answer(q: dict, a: dict, texts: dict[str, str], judge_fn) -> dict:
    """Metrics for one (question, answer). texts: canon_url -> full artifact text."""
    cites = [c for cl in a["claims"] for c in cl["cites"]]
    valid = sum(c["url"] in texts and (not c.get("quote") or squash(c["quote"]) in squash(texts[c["url"]])) for c in cites)
    row = {"cites": len(cites), "valid": valid, "seconds": a["seconds"], "tokens": a["tokens"], "error": bool(a.get("error"))}
    if q["tier"] in ANSWERABLE:
        gold = {e["url"] for e in q["gold_evidence"]}
        row |= {"correct": judge_fn(q["question"], q["gold_facts"], a["answer"]) if not a.get("error") else 0.0,
                "recall": len(gold & {c["url"] for c in cites}) / len(gold), "wrongly_refused": float(a["abstained"])}
    else:
        row["false_answer"] = float(not a["abstained"])
    return row


def boot(values: list[float], n: int = 1000, seed: int = 0) -> tuple[float, float, float]:
    """mean and 95% percentile bootstrap interval, resampling questions."""
    if not values:
        return float("nan"), float("nan"), float("nan")
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(n))
    return statistics.fmean(values), means[int(0.025 * n)], means[int(0.975 * n) - 1]


def boot_diff(a: dict[str, float], b: dict[str, float], n: int = 1000, seed: int = 0) -> tuple[float, float, float]:
    """Paired difference a-b over the questions both answered."""
    shared = sorted(a.keys() & b.keys())
    return boot([a[k] - b[k] for k in shared], n, seed)


def fmt(t: tuple[float, float, float], pct: bool = True) -> str:
    m, lo, hi = t
    if m != m:
        return "-"
    return f"{m*100:.0f}% [{lo*100:.0f}-{hi*100:.0f}]" if pct else f"{m:.1f} [{lo:.1f}-{hi:.1f}]"


def report(rows: list[dict], systems: list[str], baseline_of: str = "S") -> str:
    """rows: per_answer outputs plus {qid, tier, system}. Returns markdown tables."""
    by = lambda s, tiers, key: {r["qid"]: r[key] for r in rows if r["system"] == s and r["tier"] in tiers and key in r}  # noqa: E731
    out = ["# Benchmark results\n", "Mean over questions with 95% bootstrap interval in brackets. "
           "Differences smaller than the interval width are noise.\n"]
    out += ["## Answerable questions (tiers A, B)\n", "| system | n | correct | evidence recall | wrongly refused |", "|---|---|---|---|---|"]
    for s in systems:
        c, rc, wr = (by(s, ANSWERABLE, k) for k in ("correct", "recall", "wrongly_refused"))
        out.append(f"| {s} | {len(c)} | {fmt(boot(list(c.values())))} | {fmt(boot(list(rc.values())))} | {fmt(boot(list(wr.values())))} |")
    out += ["\n## Questions with no evidence: false-answer rate (lower is better)\n",
            "| system | " + " | ".join(f"{t} n | {t}" for t in SHOULD_ABSTAIN) + " | all |", "|---|" + "---|" * 7]
    for s in systems:
        cells = []
        for t in SHOULD_ABSTAIN:
            v = by(s, (t,), "false_answer")
            cells += [str(len(v)), fmt(boot(list(v.values())))]
        out.append(f"| {s} | " + " | ".join(cells) + f" | {fmt(boot(list(by(s, SHOULD_ABSTAIN, 'false_answer').values())))} |")
    out += ["\n## Citations, cost, failures\n", "| system | cites | hallucinated cites | seconds/question | tokens/question | errors |",
            "|---|---|---|---|---|---|"]
    for s in systems:
        mine = [r for r in rows if r["system"] == s]
        cites, valid = sum(r["cites"] for r in mine), sum(r["valid"] for r in mine)
        out.append(f"| {s} | {cites} | {('%.0f%%' % (100 * (1 - valid / cites))) if cites else '-'} | "
                   f"{statistics.fmean(r['seconds'] for r in mine):.1f} | {statistics.fmean(r['tokens'] for r in mine):.0f} | "
                   f"{sum(r['error'] for r in mine)} |" if mine else f"| {s} | - | - | - | - | - |")
    if baseline_of in systems:
        out += [f"\n## Paired difference, {baseline_of} minus each other system\n",
                "| vs | correct (higher is better) | false-answer (lower is better) |", "|---|---|---|"]
        for s in systems:
            if s != baseline_of:
                out.append(f"| {s} | {fmt(boot_diff(by(baseline_of, ANSWERABLE, 'correct'), by(s, ANSWERABLE, 'correct')))} | "
                           f"{fmt(boot_diff(by(baseline_of, SHOULD_ABSTAIN, 'false_answer'), by(s, SHOULD_ABSTAIN, 'false_answer')))} |")
    return "\n".join(out) + "\n"
