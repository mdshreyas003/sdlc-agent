"""The answer contract shared by the MCP server, the eval harness and the human view.

Transcribed from `.scratch/why-mvp/spec.md` ("Answer contract"). Ticket 01 owns this
module and may refine it; because tickets 03-05 build against it in parallel, keep
changes additive (new optional fields) rather than renaming or removing fields.
Vocabulary follows `GLOSSARY.md`.

Semantics every producer and consumer can rely on:

- Node ids are graph ids and always resolve to an ingested (non-stub) record. History records use the
  scoreboard's corpus ids: `pr:<N>`, `issue:<N>`, `commit:<full sha>`, `rfc:<file stem>`. Also
  `decision:<hash>` (Derived; grounded by its quote), `person:<login>`, and Code Entities
  `package:<path>`, `file:<path>`, `function:<pkg path>.<Func | (*Recv).Method>`, `setting:<key>`
  (`whycode.ids`, `whycode.codeindex.entity_id`).
- `Anchor.id` is the Code Entity's key without the kind prefix: `pkg/sql/schema_changer.go`,
  `pkg/sql.(*SchemaChanger).exec`, `schemachanger.job.max_retry_backoff`, `pkg/sql/schemachanger/scrun`.
- Decisions are the ones governing the Anchor or a Code Entity it contains (a file's functions and settings,
  a package's files), newest first. Their fields come from the graph, never from the composing model, and
  each quote is verbatim in the Discussion named by `discussion_id`.
- Every sentence cites at least one node id, and every cited id is in `evidence_chain`. Quotes in
  `evidence_chain` are verbatim in that node's source text (rule: `whycode.quotes.is_verbatim`).
- `refused` is True when no Decision reaches the Anchor, or nothing the composer wrote survived
  verification. A refusal still carries the nearest evidence (`evidence_chain`) and `people` to ask, but
  no `decisions` and no `sentences`. Its confidence is Low.
- Supersession (ticket 04): a Decision's `status` is `superseded` when a later Decision (or record) overrides
  it, `refined` when a later, itself not superseded, Decision narrows or extends it (partly live), else `live`.
  For the first two, `superseded_by` is the superseding or refining Decision, or the record when no Decision of
  it applies (None when the Decision's own record declares it dead, e.g. an RFC `Status: obsolete`);
  `superseded_at` is when; `explicit_or_inferred` says whether history states it or the judge inferred it; and
  `supersession_quote` is the verbatim text stating or justifying it, found in `supersession_source`. Both
  `superseded_by` and `supersession_source` are in `evidence_chain`. Superseded Decisions are the superseded
  history: they stay in `decisions`, and a sentence that cites one also cites what superseded it, so it is
  never presented as live. Supersession and history after `as_of` are invisible to a scoreboard query.
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
    """For a superseded or refined Decision: the Decision (or record) that superseded or refined it."""
    explicit_or_inferred: SupersessionOrigin | None = None
    link: GovernsLink
    """`hard` when the Change implementing the Decision touched the code; `soft` when only named in text."""
    discussion_id: str | None = None
    """The Discussion (PR, issue or RFC) the Decision was extracted from; also in `evidence_chain`."""
    alternatives_rejected: list[str] = []
    governs: list[str] = []
    """Code Entity node ids within the Anchor's scope that this Decision governs."""
    superseded_at: dt.date | None = None
    """When it was superseded or refined (the date the superseding Decision or record took effect)."""
    supersession_quote: str | None = None
    """The verbatim text that states the Supersession (a revert, an RFC status) or justifies an inferred one."""
    supersession_source: str | None = None
    """Node id of the record whose text holds `supersession_quote`."""


class EvidenceItem(_Contract):
    """One link of the Evidence Chain; `node_id` always resolves to a graph record."""

    node_id: str
    kind: str
    """decision | pr | issue | rfc | commit | incident"""
    url: str | None = None
    quote: str | None = None
    title: str | None = None
    date: dt.date | None = None


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


FenceKind = Literal["reverses", "changes"]


class FenceWarning(_Contract):
    """A proposed Change would contradict or reverse a Live Decision (ticket 05, `whycode.answer.fence`).

    `kind` is `reverses` when the diff undoes lines that a Change implementing the Decision wrote (removes lines it
    added, or restores lines it removed) inside code the Decision governs, and `changes` when it only edits a
    function or setting the Decision governs (a possible contradiction the agent must judge from the quote).
    A superseded Decision never warns; a refined one (partly live) does, with `status: refined`.
    `incident_ids` are the Incidents the Decision prevented: those closed by the Changes that implement it
    (or the Decision's own issue, when that is an Incident). Every id resolves to a graph record."""

    decision_id: str
    entity_id: str
    reason: str
    quote: str
    incident_ids: list[str] = []
    confidence: Confidence
    kind: FenceKind = "changes"
    choice: str | None = None
    status: DecisionStatus = "live"
    discussion_id: str | None = None
    """The Discussion the Decision (and its verbatim `quote`) comes from."""
    url: str | None = None
    date: dt.date | None = None
    change_id: str | None = None
    """For `reverses`: the Change implementing the Decision whose lines the diff undoes."""
    reversed_lines: list[str] = []
    """For `reverses`: the undone lines, as written in the implementing Change (whitespace trimmed; at most 10)."""


class ChangeCheck(_Contract):
    """Result of `check_change(diff)`: the Code Entities the diff touches and the Fence Warnings, strongest first
    (`reverses` before `changes`, then confidence, then newest). No warnings means no Live Decision governs what
    the diff touches, not that the change is safe."""

    touched: list[str] = []
    """Code Entity node ids the diff touches (files, functions, settings in the code index)."""
    warnings: list[FenceWarning] = []
    omitted: int = 0
    """Warnings left out past the cap (the weakest ones)."""
