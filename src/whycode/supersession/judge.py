"""The supersession judge: the model seam (`SupersessionJudge`), what it is shown (`CandidatePair`), what it answers
(`Judgment`), the rule its quotes must pass, and its adapters (Opus 5.5; recorded judgments for the fixture)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from whycode.graph import Graph
from whycode.llm import LlmClient, LlmError
from whycode.quotes import MIN_DECISION_QUOTE_WORDS, is_verbatim, word_count

log = logging.getLogger(__name__)

Label = Literal["supersedes", "refines", "unrelated"]
EDGE_TYPE = {"supersedes": "SUPERSEDES", "refines": "REFINES"}


class Judgment(BaseModel):
    label: Label = Field(description="supersedes: B supersedes A, so A no longer holds. refines: B narrows or "
                                     "extends A, so A still partly holds. unrelated: anything else, including B "
                                     "restating or implementing A.")
    quote: str = Field(description="For supersedes or refines: a passage copied character for character from B's "
                                   "discussion that shows how B changes A. Empty for unrelated.")
    reason: str = Field(description="One sentence explaining the label.")


@dataclass(frozen=True, slots=True)
class DecisionSummary:
    id: str
    discussion_id: str
    discussion_title: str
    choice: str
    rationale: str
    quote: str
    date: str


@dataclass(frozen=True, slots=True)
class CandidatePair:
    earlier: DecisionSummary
    later: DecisionSummary
    shared: tuple[str, ...]  # Code Entity ids both Decisions govern
    later_text: str  # B's Discussion, where the justification quote must come from


class SupersessionJudge(Protocol):
    def judge(self, pair: CandidatePair) -> Judgment: ...


def summary(graph: Graph, decision_id: str) -> DecisionSummary:
    d = graph.nodes[decision_id].props
    return DecisionSummary(id=decision_id, discussion_id=d["discussion_id"],
                           discussion_title=graph.nodes[d["discussion_id"]].props.get("title") or "",
                           choice=d["choice"], rationale=d["rationale"], quote=d["quote"], date=d["date"])


def judge_name(judge: SupersessionJudge) -> str:
    return getattr(judge, "name", type(judge).__name__)


def quote_holds(quote: str, text: str) -> bool:
    """The model proposes, code decides: a judge's quote counts only with at least `MIN_DECISION_QUOTE_WORDS` words,
    verbatim in `text` (B's Discussion)."""
    return word_count(quote) >= MIN_DECISION_QUOTE_WORDS and is_verbatim(quote, text)


class RecordedSupersessionJudge:
    """Replays recorded judgments keyed by "<earlier decision id> -> <later decision id>" (the fixture's stand-in
    for the model). Raises KeyError for a pair with no recording, so an unexpected question fails loudly."""

    name = "recorded"

    def __init__(self, path: Path):
        data = json.loads(Path(path).read_text())
        self._recorded = {k: Judgment.model_validate({f: v[f] for f in ("label", "quote", "reason")})
                          for k, v in data.items() if not k.startswith("_")}

    def judge(self, pair: CandidatePair) -> Judgment:
        return self._recorded[f"{pair.earlier.id} -> {pair.later.id}"]


JUDGE_SYSTEM = """You judge whether a later Decision changes an earlier one in the CockroachDB SQL schema \
changer. Both Decisions govern the same code. Label the pair:

- supersedes: B supersedes A. After B, A no longer holds (B undoes it, chooses differently on the same subject, \
or contradicts it).
- refines: B narrows or extends A. A still holds in part (B adds an exception, changes a default or a limit, or \
covers a case A left open).
- unrelated: B does not change A. This includes B restating A, implementing A as proposed, or deciding \
something else about the same code.

When the evidence is thin, answer unrelated: a wrong supersedes label hides a Decision that is still live.

For supersedes or refines, give `quote`: a passage copied character for character from B's discussion (at \
least five words, from one post or section) that shows how B changes A. Do not paraphrase, fix typos or \
shorten with "...". A label whose quote is not found verbatim in B's discussion is discarded."""


def render_pair(pair: CandidatePair) -> str:
    def decision(tag: str, d: DecisionSummary) -> str:
        return (f"{tag} ({d.date}, from {d.discussion_id}: {d.discussion_title})\n"
                f"Choice: {d.choice}\nRationale: {d.rationale}\nQuote: {d.quote}")

    return "\n\n".join([
        decision("Earlier Decision A", pair.earlier), decision("Later Decision B", pair.later),
        "Code both govern: " + ", ".join(pair.shared),
        f"B's discussion ({pair.later.discussion_id}):\n{pair.later_text}",
    ])


class AnthropicSupersessionJudge:
    """Production adapter: Opus 5.5 with structured output, responses cached on disk by the LlmClient."""

    def __init__(self, llm: LlmClient, model: str):
        self.llm = llm
        self.model = model
        self.name = model

    def judge(self, pair: CandidatePair) -> Judgment:
        try:
            return self.llm.parse(model=self.model, system=JUDGE_SYSTEM, user=render_pair(pair), output=Judgment,
                                  effort="medium")
        except LlmError as exc:
            log.warning("supersession judgment failed for %s -> %s: %s", pair.earlier.id, pair.later.id, exc)
            return Judgment(label="unrelated", quote="", reason=f"judge failed: {exc}")
