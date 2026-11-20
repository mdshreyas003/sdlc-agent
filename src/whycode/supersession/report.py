"""The supersession judge scored against explicit Supersession (`whycode supersession-report`)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from whycode.graph import Graph
from whycode.supersession.explicit import SUPERSEDE_TEXT
from whycode.supersession.index import EXPLICIT, DecisionIndex
from whycode.supersession.judge import (
    CandidatePair,
    DecisionSummary,
    Label,
    SupersessionJudge,
    judge_name,
    quote_holds,
    summary,
)
from whycode.supersession.pairs import candidate_pairs

_STATEMENTS = (  # what makes a case explicit; masked out of B's discussion before the judge reads it
    re.compile(r'(?im)^revert ".*"$'),
    re.compile(r"(?i)\bthis reverts commit [0-9a-f]{7,40}\b"),
    re.compile(r"(?i)\breverts?\b:?\s+(?:pr\s+)?(?:[\w.-]+/[\w.-]+)?#\d{1,7}\b"),
    SUPERSEDE_TEXT,
)
MASK = "[explicit statement removed]"


def mask_statements(text: str) -> str:
    for pattern in _STATEMENTS:
        text = pattern.sub(MASK, text)
    return text


@dataclass(frozen=True, slots=True)
class JudgedCase:
    earlier: DecisionSummary
    later: DecisionSummary
    explicit: bool  # gold: history states that B supersedes A
    label: Label  # the judge's label; "unrelated" when its quote failed the verbatim check
    quote: str
    reason: str

    @property
    def predicted(self) -> bool:
        return self.label == "supersedes"


@dataclass(frozen=True)
class JudgeReport:
    judge: str
    cases: list[JudgedCase]
    unjudgeable: int  # explicitly superseded Decisions with no superseding Decision (a record or a status)

    def _count(self, explicit: bool, predicted: bool) -> int:
        return sum(c.explicit == explicit and c.predicted == predicted for c in self.cases)

    @property
    def true_positives(self) -> int:
        return self._count(True, True)

    @property
    def false_positives(self) -> int:
        return self._count(False, True)

    @property
    def false_negatives(self) -> int:
        return self._count(True, False)

    @property
    def precision(self) -> float | None:
        flagged = self.true_positives + self.false_positives
        return self.true_positives / flagged if flagged else None

    @property
    def recall(self) -> float | None:
        explicit = self.true_positives + self.false_negatives
        return self.true_positives / explicit if explicit else None

    def markdown(self) -> str:
        def pct(value: float | None, num: int, den: int) -> str:
            return f"{value:.0%} ({num} of {den})" if value is not None else "n/a (0 of 0)"

        def row(explicit: bool) -> str:
            cases = [c for c in self.cases if c.explicit == explicit]
            counts = [sum(c.label == label for c in cases) for label in ("supersedes", "refines", "unrelated")]
            name = "explicit Supersession" if explicit else "no explicit link"
            return f"| {name} (n={len(cases)}) | " + " | ".join(map(str, counts)) + " |"

        def listed(title: str, cases: list[JudgedCase]) -> list[str]:
            lines = [f"### {title} ({len(cases)})", ""]
            for c in cases:
                lines.append(f"- {c.earlier.discussion_id} -> {c.later.discussion_id}: judge said {c.label}. "
                             f"A: {c.earlier.choice} B: {c.later.choice}"
                             + (f' Quote: "{c.quote}". {c.reason}' if c.quote else ""))
            return [*lines, ""]

        tp, fp, fn = self.true_positives, self.false_positives, self.false_negatives
        return "\n".join([
            "# Supersession judge against explicit Supersession", "",
            (f"Judge `{self.judge}`. Gold: Supersession that history states (reverts, RFC status headers, "
             "\"supersedes #N\"). Each pair was judged with that statement masked out of B's discussion. Negatives "
             "are the other candidate pairs around the explicit cases (same Code Entity, B later): pairs into an "
             "explicitly superseded Decision, and pairs out of an explicit superseder."), "",
            "| pairs | judge: supersedes | judge: refines | judge: unrelated (or quote rejected) |",
            "|---|---|---|---|", row(True), row(False), "",
            f"Precision {pct(self.precision, tp, tp + fp)}, recall {pct(self.recall, tp, tp + fn)}.", "",
            ("Precision is a lower bound: a negative the judge calls supersedes may be a real Supersession history "
             "never stated; check the false positives below by hand. Refines counts as not supersedes."),
            (f"{self.unjudgeable} explicitly superseded Decisions have no superseding Decision (a revert or status "
             "with no Decision of its own) and are not judged pairwise."), "",
            *listed("False positives (judge: supersedes, no explicit link)",
                    [c for c in self.cases if not c.explicit and c.predicted]),
            *listed("False negatives (explicit, judge did not say supersedes)",
                    [c for c in self.cases if c.explicit and not c.predicted]),
        ]).rstrip() + "\n"


def judge_report(graph: Graph, judge: SupersessionJudge) -> JudgeReport:
    """Ask the judge about every explicit Decision -> Decision Supersession and the candidate pairs around it."""
    index = DecisionIndex(graph)
    explicit = [e for e in graph.edges("SUPERSEDES") if e.props.get("basis") == EXPLICIT]
    gold = {(e.target, e.source) for e in explicit if e.source in index.decisions}
    superseded, superseders = {a for a, _ in gold}, {b for _, b in gold}
    unjudgeable = len({e.target for e in explicit} - superseded)
    pairs = dict.fromkeys(sorted(gold, key=lambda p: (index.decisions[p[1]].props["date"], p)))
    candidates = candidate_pairs(graph).pairs
    for a, b, _ in candidates:
        if a in superseded or b in superseders:
            pairs.setdefault((a, b))
    shared = {(a, b): s for a, b, s in candidates}
    cases = []
    for a, b in pairs:
        earlier, later = summary(graph, a), summary(graph, b)
        text = graph.nodes[later.discussion_id].props.get("text") or ""
        judgment = judge.judge(CandidatePair(earlier, later, shared.get((a, b), ()), mask_statements(text)))
        quote = judgment.quote.strip()
        kept = judgment.label == "unrelated" or quote_holds(quote, text)
        cases.append(JudgedCase(earlier, later, (a, b) in gold, judgment.label if kept else "unrelated", quote,
                                judgment.reason))
    return JudgeReport(judge_name(judge), cases, unjudgeable)
