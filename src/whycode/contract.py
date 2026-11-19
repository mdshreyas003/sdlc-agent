"""The answer contract shared by the MCP server, the eval harness and the human view.

Transcribed from `.scratch/why-mvp/spec.md` ("Answer contract"). Ticket 01 owns this
module and may refine it; because tickets 03-05 build against it in parallel, keep
changes additive (new optional fields) rather than renaming or removing fields.
Vocabulary follows `GLOSSARY.md`.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict

AnchorKind = Literal["function", "file", "package", "setting"]
Confidence = Literal["High", "Medium", "Low"]
DecisionStatus = Literal["live", "superseded", "refined"]
SupersessionOrigin = Literal["explicit", "inferred"]
GovernsLink = Literal["hard", "soft"]
PersonRole = Literal["author", "approver"]


class _Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Anchor(_Contract):
    """The Code Entity a question is asked about."""

    kind: AnchorKind
    id: str


class DecisionView(_Contract):
    id: str
    choice: str
    rationale: str
    quote: str
    date: dt.date
    status: DecisionStatus = "live"
    superseded_by: str | None = None
    explicit_or_inferred: SupersessionOrigin | None = None
    link: GovernsLink


class EvidenceItem(_Contract):
    """One link of the Evidence Chain; `node_id` always resolves to a graph record."""

    node_id: str
    kind: str
    url: str | None = None
    quote: str | None = None


class PersonView(_Contract):
    """A Person to Ask candidate; `active` is False when departed (inactive 12+ months)."""

    handle: str
    role: PersonRole
    active: bool


class IncidentRef(_Contract):
    id: str
    url: str | None = None


class Sentence(_Contract):
    text: str
    cites: list[str]


class Answer(_Contract):
    """Result of `why(anchor)`.

    `anchor` is None only when a free-form question could not be resolved to a
    Code Entity, in which case `refused` is True.
    """

    anchor: Anchor | None
    refused: bool
    confidence: Confidence
    decisions: list[DecisionView] = []
    evidence_chain: list[EvidenceItem] = []
    people: list[PersonView] = []
    incidents: list[IncidentRef] = []
    sentences: list[Sentence] = []


class FenceWarning(_Contract):
    """A proposed Change would contradict or reverse a Live Decision."""

    decision_id: str
    entity_id: str
    reason: str
    quote: str
    incident_ids: list[str] = []
    confidence: Confidence
