"""Compose: write the answer's sentences from the retrieved nodes only.

`Composer` is the model seam. The composer sees the Anchor, the governing Decisions, the evidence nodes (with
the full text each citation will be checked against) and the people; it returns draft sentences, each citing
node ids and optionally a supporting quote. Nothing it writes is trusted: `verify` decides what survives.
"""

from __future__ import annotations

import json
import logging
from typing import Protocol

from pydantic import BaseModel, Field

from whycode.contract import Anchor, DecisionView, PersonView
from whycode.llm import LlmClient, LlmError

log = logging.getLogger(__name__)


class EvidenceNode(BaseModel):
    id: str
    kind: str
    title: str | None = None
    url: str | None = None
    date: str | None = None
    text: str = Field(description="The source text citations of this node are checked against.")


class ComposeRequest(BaseModel):
    anchor: Anchor
    decisions: list[DecisionView]
    evidence: list[EvidenceNode]
    people: list[PersonView]


class DraftCite(BaseModel):
    node_id: str = Field(description="Id of an evidence node that supports the sentence.")
    quote: str = Field(default="", description="Optional passage copied verbatim from that node's text.")


class DraftSentence(BaseModel):
    text: str
    cites: list[DraftCite]


class Composition(BaseModel):
    sentences: list[DraftSentence]


class Composer(Protocol):
    def compose(self, request: ComposeRequest) -> list[DraftSentence]: ...


COMPOSER_SYSTEM = """You explain to a coding agent why a piece of CockroachDB schema-change code is the way \
it is, using only the evidence you are given.

Rules:
- Use only the Decisions and evidence nodes provided. Do not add facts from memory.
- Every sentence cites at least one evidence node id (field `cites`). Cite the Decision and the Discussion \
it came from. Never cite an id that is not in the evidence.
- When you quote, copy the passage character for character from the cited node's `text` and put it in the \
cite's `quote` field. Never paraphrase inside quotation marks.
- Say what was chosen, why, what was rejected when recorded, and when. Name the Person to Ask, and say \
when a person is departed (active: false); for a departed person, name `ask_instead` as the one to ask instead.
- Mention an Incident the Decision prevented when one is given.
- Each Decision has a `status`. A `superseded` Decision is dead: say that it was superseded, by what \
(`superseded_by`) and when (`superseded_at`), cite `superseded_by` (or `supersession_source` when it is \
empty) in the same sentence, and never describe it as how the code works now. A `refined` Decision is partly \
live: say what still holds and what the refining Decision changed. When `explicit_or_inferred` is \
`inferred`, say the change was inferred, not stated in history.
- Write 2 to 6 short sentences. No URLs."""


class AnthropicComposer:
    """Production adapter: Opus 5.5 with structured output, responses cached on disk by the LlmClient."""

    def __init__(self, llm: LlmClient, model: str):
        self.llm = llm
        self.model = model

    def compose(self, request: ComposeRequest) -> list[DraftSentence]:
        try:
            result = self.llm.parse(model=self.model, system=COMPOSER_SYSTEM,
                                    user=json.dumps(request.model_dump(mode="json"), indent=1),
                                    output=Composition, effort="medium")
        except LlmError as exc:
            log.warning("composition failed for %s: %s", request.anchor.id, exc)
            return []
        return result.sentences


class TemplateComposer:
    """Deterministic, model-free composer for offline demos: one sentence per Decision, saying when and by what a
    superseded or refined Decision was overtaken."""

    def compose(self, request: ComposeRequest) -> list[DraftSentence]:
        out = []
        for d in request.decisions:
            text = f"{d.choice} ({d.date.isoformat()}): {d.rationale}"
            cites = [DraftCite(node_id=d.id)]
            if d.discussion_id:
                cites.append(DraftCite(node_id=d.discussion_id, quote=d.quote))
            if d.status != "live":
                how = "inferred" if d.explicit_or_inferred == "inferred" else "stated in history"
                by = f" by {d.superseded_by}" if d.superseded_by else ""
                text = f"{d.status.capitalize()} on {d.superseded_at.isoformat()}{by} ({how}): {text}"
                cites.append(DraftCite(node_id=d.superseded_by or d.supersession_source))
            out.append(DraftSentence(text=text, cites=cites))
        return out
