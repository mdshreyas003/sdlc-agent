"""Decision extractor (Derived): the model proposes Decisions, code decides which ones exist.

`DecisionProposer` is the model seam: given a Discussion it returns zero or more candidates (what was
chosen, the rationale, alternatives rejected, and a verbatim quote). A candidate becomes a Decision only if
its quote has at least `MIN_DECISION_QUOTE_WORDS` words and appears word for word inside one segment of that
Discussion. The segment then fixes who said it and when; the model never chooses ids, dates or authors.

Soft governs links are the Code Entities the Decision names (in its quote, choice or rationale) that the
quoted segment also names, so a model can never link a Decision to code its source never mentions.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from whycode import ids
from whycode.codeindex import CodeEntity, CodeIndex
from whycode.discussions import Discussion
from whycode.llm import LlmClient, LlmError
from whycode.quotes import MIN_DECISION_QUOTE_WORDS, is_verbatim, word_count

log = logging.getLogger(__name__)


class DecisionCandidate(BaseModel):
    choice: str = Field(description="What was chosen, in one sentence.")
    rationale: str = Field(description="Why it was chosen, as stated in the discussion.")
    alternatives_rejected: list[str] = Field(default_factory=list, description="Alternatives the text rejects.")
    quote: str = Field(description="A passage copied character for character from the discussion that states "
                                   "the choice or its rationale. Never paraphrase, shorten with '...', or merge "
                                   "passages.")


class Extraction(BaseModel):
    decisions: list[DecisionCandidate]


class DecisionProposer(Protocol):
    def propose(self, discussion: Discussion) -> list[DecisionCandidate]: ...


@dataclass(frozen=True, slots=True)
class ExtractedDecision:
    id: str
    discussion_id: str
    choice: str
    rationale: str
    alternatives_rejected: tuple[str, ...]
    quote: str
    date: dt.date
    speaker: str | None  # author of the quoted segment (None for RFC sections: the RFC's authors stand)
    segment: str  # locator of the quoted segment
    mentions: frozenset[CodeEntity]  # soft governs links


def extract_decisions(discussion: Discussion, proposer: DecisionProposer, code: CodeIndex) -> list[ExtractedDecision]:
    out: dict[str, ExtractedDecision] = {}
    for candidate in proposer.propose(discussion):
        quote = candidate.quote.strip()
        if word_count(quote) < MIN_DECISION_QUOTE_WORDS:
            continue
        segment = next((s for s in discussion.segments if is_verbatim(quote, s.text)), None)
        if segment is None:
            continue
        decision_id = ids.decision_id(discussion.id, quote)
        if decision_id in out:
            continue
        named = code.mentions(f"{quote} {candidate.choice} {candidate.rationale}")
        out[decision_id] = ExtractedDecision(
            id=decision_id,
            discussion_id=discussion.id,
            choice=candidate.choice.strip(),
            rationale=candidate.rationale.strip(),
            alternatives_rejected=tuple(a.strip() for a in candidate.alternatives_rejected if a.strip()),
            quote=quote,
            date=discussion.decision_date(segment),
            speaker=segment.author,
            segment=segment.locator,
            mentions=frozenset(named & code.mentions(segment.text)),
        )
    return list(out.values())


class RecordedDecisionProposer:
    """Replays recorded candidates keyed by Discussion id (the fixture's stand-in for the model).

    Raises KeyError for a Discussion with no recording, so a build that asks about a record it should never
    have ingested fails loudly.
    """

    name = "recorded"

    def __init__(self, *paths: Path):
        self._recorded = {}
        for path in paths:
            data = json.loads(Path(path).read_text())
            self._recorded |= {k: [DecisionCandidate.model_validate(c) for c in v] for k, v in data.items()
                               if not k.startswith("_")}

    def propose(self, discussion: Discussion) -> list[DecisionCandidate]:
        if discussion.id not in self._recorded:
            raise KeyError(f"no recorded extraction for {discussion.id}")
        return list(self._recorded[discussion.id])


EXTRACTION_SYSTEM = """You extract Decisions from one software-engineering discussion of the CockroachDB \
SQL schema changer (a pull request with its reviews, an issue thread, or a design RFC).

A Decision is a choice the discussion makes or records about how the code should behave or be built: what \
was chosen, why, and which alternatives were rejected. Bug reports, status updates, test noise and \
procedural chatter ("LGTM", "bors r+", "rebased") are not Decisions. Most discussions hold zero, one or two \
Decisions; return an empty list when there are none.

For every Decision give a `quote`: a passage copied character for character from the discussion that \
states the choice or its rationale, at least five words long, from a single post or section. Do not \
paraphrase, fix typos, drop markdown, join separate passages or shorten with "...". A Decision whose \
quote cannot be found verbatim in the discussion is discarded.

Name the code the Decision concerns (functions, files, cluster settings) in `choice` or `rationale` \
exactly as the discussion spells it."""


def render_discussion(discussion: Discussion) -> str:
    parts = [f"Discussion {discussion.id} ({discussion.kind}): {discussion.title}"]
    for s in discussion.segments:
        who = f" by @{s.author}" if s.author else ""
        parts.append(f"--- {s.locator}{who} on {s.at.isoformat()} ---\n{s.text}")
    return "\n\n".join(parts)


class AnthropicDecisionProposer:
    """Production adapter: Sonnet 5.5 with structured output, responses cached on disk by the LlmClient."""

    def __init__(self, llm: LlmClient, model: str):
        self.llm = llm
        self.model = model
        self.name = model

    def propose(self, discussion: Discussion) -> list[DecisionCandidate]:
        try:
            result = self.llm.parse(model=self.model, system=EXTRACTION_SYSTEM,
                                    user=render_discussion(discussion), output=Extraction, effort="medium")
        except LlmError as exc:
            log.warning("extraction failed for %s: %s", discussion.id, exc)
            return []
        return result.decisions
