"""The fact-level judge, and its agreement with hand labels.

The judge reads one rendered answer and says, per required fact, whether the answer states it;
per superseded fact, whether the answer presents it as live; and whether the answer reports that
an earlier choice was reversed or narrowed. Its instructions are the committed prompt
`eval/prompts/judge.md`. Judge output is a model opinion, so its agreement with hand-labelled
answers (`eval/judge_agreement/labels.yaml`) is reported next to every score.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from whycode.contract import Answer
from whycode.eval.models import StructuredModel

MIN_LABELLED = 15  # ticket 03: agreement is reported against at least 15 hand-labelled answers


class Verdict(BaseModel):
    covered: list[bool]  # one per required fact, in order
    presented_as_live: list[bool] = []  # one per superseded fact, in order
    reports_change: bool = False  # the answer says an earlier choice was reversed, replaced or narrowed

    def fitted(self, n_facts: int, n_superseded: int) -> Verdict:
        """Pad with False or truncate so each list has one entry per fact."""
        return Verdict(covered=(self.covered + [False] * n_facts)[:n_facts],
                       presented_as_live=(self.presented_as_live + [False] * n_superseded)[:n_superseded],
                       reports_change=self.reports_change)


@dataclass(frozen=True)
class JudgeInput:
    question: str
    answer_text: str
    gold_facts: tuple[str, ...]
    superseded_facts: tuple[str, ...] = ()


Judge = Callable[[JudgeInput], Verdict]


def render_answer(answer: Answer) -> str:
    """The answer as the judge (and a human labeller) reads it: Decisions with status, then sentences."""
    lines = [f"Refused: {'yes' if answer.refused else 'no'}"]
    if answer.decisions:
        lines.append("Decisions:")
        for decision in answer.decisions:
            status = (decision.status if not decision.superseded_by
                      else f"{decision.status}, superseded by {decision.superseded_by}")
            lines.append(f"- [{status}] {decision.choice} Rationale: {decision.rationale} "
                         f"(dated {decision.date.isoformat()})")
    lines.append("Answer:")
    lines.append(" ".join(s.text for s in answer.sentences) or "(no text)")
    return "\n".join(lines)


def render_judge_input(item: JudgeInput) -> str:
    def numbered(facts: Sequence[str]) -> str:
        return "\n".join(f"{i}. {f}" for i, f in enumerate(facts, 1)) or "(none)"

    return (f"Question: {item.question}\n\nRequired facts (in order):\n{numbered(item.gold_facts)}\n\n"
            f"Superseded facts (in order):\n{numbered(item.superseded_facts)}\n\nAnswer:\n{item.answer_text}")


class FactJudge:
    def __init__(self, model: StructuredModel, prompt: str):
        self.model, self.prompt = model, prompt

    def __call__(self, item: JudgeInput) -> Verdict:
        verdict = self.model.parse(system=self.prompt, user=render_judge_input(item), output=Verdict).value
        return verdict.fitted(len(item.gold_facts), len(item.superseded_facts))


# --- agreement with hand labels ------------------------------------------------------------------

class HandLabels(BaseModel):
    model_config = ConfigDict(extra="forbid")

    covered: list[bool] | None = None
    presented_as_live: list[bool] | None = None
    reports_change: bool | None = None


class LabelledAnswer(BaseModel):
    """One answer a human labelled the way the judge would."""

    model_config = ConfigDict(extra="forbid")

    id: str
    human_labelled: bool = False
    question: str
    gold_facts: list[str]
    superseded_facts: list[str] = []
    answer: str  # rendered with `render_answer`
    labels: HandLabels = HandLabels()
    source: str = ""  # run directory, case id and system the answer came from

    def complete(self) -> bool:
        lab = self.labels
        if lab.covered is None or len(lab.covered) != len(self.gold_facts):
            return False
        if self.superseded_facts:
            return (lab.presented_as_live is not None and len(lab.presented_as_live) == len(self.superseded_facts)
                    and lab.reports_change is not None)
        return True


def load_labels(path: Path) -> list[LabelledAnswer]:
    return [LabelledAnswer.model_validate(x) for x in yaml.safe_load(path.read_text(encoding="utf-8")) or []]


def save_labels(path: Path, items: Sequence[LabelledAnswer]) -> None:
    data = [i.model_dump(mode="json") for i in items]
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")


@dataclass(frozen=True)
class Agreement:
    answers: int  # hand-labelled answers compared
    judgments: int  # binary judgments compared (facts, superseded facts, reports_change)
    agreement: float  # share of judgments where judge and human agree
    kappa: float  # Cohen's kappa over the same judgments
    correctness_mae: float  # mean |judge - human| of the per-answer correctness score
    skipped: int  # items not counted (not human_labelled, or labels incomplete)

    @property
    def enough(self) -> bool:
        return self.answers >= MIN_LABELLED

    def summary(self) -> str:
        verdict = "meets" if self.enough else f"below the {MIN_LABELLED} required for"
        return (f"Judge agreement on {self.answers} hand-labelled answers ({self.judgments} judgments; "
                f"{verdict} the ticket bar): {self.agreement:.0%} agreement, Cohen's kappa {self.kappa:.2f}, "
                f"correctness MAE {self.correctness_mae:.2f}. {self.skipped} unlabelled items skipped.")


def cohen_kappa(pairs: Sequence[tuple[bool, bool]]) -> float:
    """Cohen's kappa for two raters over binary judgments; 1.0 when both agree on a single class."""
    n = len(pairs)
    observed = sum(a == b for a, b in pairs) / n
    p_a, p_b = sum(a for a, _ in pairs) / n, sum(b for _, b in pairs) / n
    expected = p_a * p_b + (1 - p_a) * (1 - p_b)
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def agreement(items: Sequence[LabelledAnswer], judge: Judge) -> Agreement:
    counted = [i for i in items if i.human_labelled and i.complete()]
    pairs: list[tuple[bool, bool]] = []
    errors: list[float] = []
    for item in counted:
        verdict = judge(JudgeInput(item.question, item.answer, tuple(item.gold_facts), tuple(item.superseded_facts)))
        lab = item.labels
        pairs += zip(verdict.covered, lab.covered or [], strict=True)
        if item.superseded_facts:
            pairs += zip(verdict.presented_as_live, lab.presented_as_live or [], strict=True)
            pairs.append((verdict.reports_change, bool(lab.reports_change)))
        n = len(item.gold_facts) or 1
        errors.append(abs(sum(verdict.covered) - sum(lab.covered or [])) / n)
    if not pairs:
        return Agreement(0, 0, float("nan"), float("nan"), float("nan"), len(items))
    return Agreement(answers=len(counted), judgments=len(pairs), agreement=sum(a == b for a, b in pairs) / len(pairs),
                     kappa=cohen_kappa(pairs), correctness_mae=sum(errors) / len(errors),
                     skipped=len(items) - len(counted))
