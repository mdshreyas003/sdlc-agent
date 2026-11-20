"""Answer engine behind `why(anchor)`: resolve, traverse, compose, verify, score.

1. Resolve the Anchor to one Code Entity: exact key or alias first; then exactly one Code Entity named by the
   code-like tokens of a free-form question; otherwise one entity-matching model step (the `EntityMatcher` seam)
   over a shortlist of Code Entities found from the question's words. Unsure, off the shortlist, or no matcher:
   refuse, never guess. A matched Anchor rests on model judgment, so its answer is at most Medium confidence.
2. Traverse fixed read-only patterns: Anchor -> governing Decisions -> Supersession -> Discussions -> closing
   Changes -> People and Incidents. No planning, no model-written queries. When no Live Decision reaches the
   Anchor, refuse: `ungoverned` when no Decision does, `superseded` when every one that does is superseded (they
   come back as the superseded history, with their evidence and the Person to Ask; no model is asked).
3. Compose sentences from the retrieved nodes only (the `Composer` seam).
4. Verify in code, then score confidence from graph properties and what verification dropped.

Supersession sets each Decision's status (`whycode.answer.status`, the rule `check_change` shares).
`supersession=False` builds the scoreboard's "without supersession" system: every Decision is treated as live.

Person to Ask: the authors and approving reviewers of the Decisions' records, active first. Each departed one's
`ask_instead` is the next-best active person: the first active person already listed, else the author or approver
of the latest Change touching the nearest enclosing area of the code (the Anchor's file, then its directories up
to two levels deep), who is then listed with `via` naming that Change.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable
from dataclasses import dataclass

from whycode.answer.compose import Composer, ComposeRequest, EvidenceNode
from whycode.answer.confidence import ConfidenceInputs, score_confidence
from whycode.answer.patterns import DecisionRow, EntityRow, GraphReader, HistoryView, Record, SupersessionRow
from whycode.answer.resolve import EntityCandidate, EntityMatcher, question_words
from whycode.answer.status import SupersessionStatus, grounding, supersession_statuses
from whycode.answer.verify import Superseded, verify
from whycode.contract import Anchor, Answer, DecisionView, EvidenceItem, IncidentRef, PersonView
from whycode.graph import day

MAX_ANCHOR_CHARS = 2000
MAX_EXACT_CHARS = 300
MAX_TOKENS = 30
MAX_CANDIDATES = 30
MIN_AREA_DEPTH = 2  # the widest area searched for a next-best Person to Ask: `pkg/sql/`
_BACKTICKED = re.compile(r"`([^`\s]+)`")
_TOKEN = re.compile(r"[\w./()*-]+")
_CAMEL = re.compile(r"[a-z][A-Z]")


def _code_tokens(question: str) -> list[str]:
    """Tokens that look like code (paths, dotted names, snake_case, camelCase, backticked); plain words never
    count, so a loose question cannot match a function that happens to be called `output`."""
    out = [m.group(1) for m in _BACKTICKED.finditer(question)]
    for m in _TOKEN.finditer(question):
        token = m.group(0).rstrip(".,;:?!").removesuffix("()")
        if re.search(r"[A-Za-z]", token) and (re.search(r"[./_(]", token) or _CAMEL.search(token)):
            out.append(token)
    return list(dict.fromkeys(out))[:MAX_TOKENS]


def _areas(entity: EntityRow) -> list[str]:
    """Path prefixes of the areas enclosing a Code Entity, nearest first: its file, then its directories."""
    if entity.file:
        path, out = entity.file, [entity.file]
    elif entity.kind == "package":
        path, out = entity.key.rstrip("/") + "/", []
    else:
        return []
    parts = path.rstrip("/").split("/")
    top = len(parts) - (0 if path.endswith("/") else 1)
    return out + ["/".join(parts[:i]) + "/" for i in range(top, MIN_AREA_DEPTH - 1, -1)]


@dataclass(frozen=True, slots=True)
class _Resolved:
    entity: EntityRow
    matched: bool  # chosen by the entity-matching model step, not by an exact name

    @property
    def anchor(self) -> Anchor:
        return Anchor(kind=self.entity.kind, id=self.entity.key)


def _node(record: Record, kind: str | None = None, text: str | None = None) -> EvidenceNode:
    return EvidenceNode(id=record.id, kind=kind or record.kind, title=record.title, url=record.url, date=record.date,
                        text=record.text if text is None else text)


class _Evidence:
    """The Evidence Chain under construction: contract items plus the full texts the verifier checks."""

    def __init__(self):
        self.items: dict[str, EvidenceItem] = {}
        self.nodes: dict[str, EvidenceNode] = {}

    def add(self, node: EvidenceNode, quote: str | None = None) -> None:
        if node.id in self.items:
            return
        self.nodes[node.id] = node
        self.items[node.id] = EvidenceItem(node_id=node.id, kind=node.kind, url=node.url, quote=quote,
                                           title=node.title, date=day(node.date))

    def add_decision(self, decision: DecisionRow, discussion: Record, discussion_quote: str | None = None,
                     discussion_text: str | None = None) -> None:
        """A Decision, grounded by its quote, and the Discussion it came from (quoted with `discussion_quote`,
        by default the Decision's own quote)."""
        self.add(EvidenceNode(id=decision.id, kind="decision", title=decision.choice, url=discussion.url,
                              date=decision.date, text=decision.quote), quote=decision.quote)
        self.add(_node(discussion, text=discussion_text), quote=discussion_quote or decision.quote)

    def add_supersession(self, status: SupersessionStatus) -> None:
        """What superseded or refined a Decision, and the record whose text states it, along its whole chain."""
        for edge in (status.edge, *status.chain):
            self._add_superseder(edge)

    def _add_superseder(self, edge: SupersessionRow) -> None:
        if isinstance(edge.by, DecisionRow) and edge.by_discussion is not None:
            home = edge.by_discussion
            self.add_decision(edge.by, home, edge.quote if home.id == edge.source.id else None)
        self.add(_node(edge.source), quote=edge.quote)
        if isinstance(edge.by, Record) and edge.by.id != edge.source.id:
            self.add(_node(edge.by))


def _dead_in_chain(status: SupersessionStatus, known: dict[str, Superseded]) -> dict[str, Superseded]:
    """The superseded Decisions along a status's chain (they are evidence too, so never presented as live)."""
    out = {}
    edges = (status.edge, *status.chain)
    for i, later in enumerate(edges[1:], 1):
        dead = edges[i - 1].by
        if isinstance(dead, DecisionRow) and dead.id not in known:
            witnesses = {later.source.id, *(e.by.id for e in edges[i:])}
            out[dead.id] = Superseded(quote=dead.quote, witnesses=frozenset(witnesses))
    return out


class AnswerEngine:
    def __init__(self, reader: GraphReader, composer: Composer, supersession: bool = True,
                 matcher: EntityMatcher | None = None):
        self.reader = reader
        self.composer = composer
        self.supersession = supersession
        self.matcher = matcher

    def why(self, anchor: str, as_of: dt.date | None = None, exclude: Iterable[str] = ()) -> Answer:
        """The Answer for an Anchor. `as_of` and `exclude` are the scoreboard's view of history: nothing dated
        after `as_of` (None: all of it) and none of the `exclude`d records, nor what rests on them, is seen."""
        view = HistoryView.of(as_of, exclude)
        resolved = self._resolve(anchor)
        if resolved is None:
            return Answer(anchor=None, refused=True, confidence="Low", refusal_reason="unresolved")
        entity, matched = resolved.entity, resolved.matched
        rows = self.reader.governing(entity.id, view)
        if not rows:
            return self._refusal(resolved, view)

        evidence = _Evidence()
        decisions: list[DecisionView] = []
        discussions: dict[str, Record] = {}
        speakers: list[str] = []
        statuses = self._statuses({row.decision.id: row.discussion.id for row in rows}, view)
        for row in rows:
            decision, discussion = row.decision, row.discussion
            status = statuses.get(decision.id)
            history = {}
            if status is not None:
                history = dict(status=status.status, superseded_by=status.by, superseded_at=status.at,
                               explicit_or_inferred=status.basis, supersession_quote=status.edge.quote,
                               supersession_source=status.source, supersession_chain=status.chain_ids)
            decisions.append(DecisionView(
                id=decision.id, choice=decision.choice, rationale=decision.rationale, quote=decision.quote,
                date=decision.day, link=row.link, discussion_id=discussion.id,
                alternatives_rejected=list(decision.alternatives_rejected), governs=sorted(row.entities), **history,
            ))
            discussions[discussion.id] = discussion
            if decision.speaker:
                speakers.append(decision.speaker)
            evidence.add_decision(decision, discussion)
        superseded: dict[str, Superseded] = {}
        quotes = {row.decision.id: row.decision.quote for row in rows}
        for decision_id, status in statuses.items():
            evidence.add_supersession(status)
            if status.superseded:
                superseded[decision_id] = Superseded(quote=quotes[decision_id], witnesses=status.witnesses)
                superseded |= _dead_in_chain(status, superseded)
        reviewed = [i for i, s in discussions.items() if s.kind in ("pr", "rfc")]
        people = self._people(reviewed, speakers, entity, view)
        if all(row.decision.id in superseded for row in rows):  # no Live Decision: refuse, showing the history
            return Answer(anchor=resolved.anchor, refused=True, confidence="Low", refusal_reason="superseded",
                          anchor_matched=matched, decisions=decisions, evidence_chain=list(evidence.items.values()),
                          people=people)

        issues = [i for i, s in discussions.items() if s.kind == "issue"]
        closers = self.reader.closers(issues, view) if issues else []
        for change in closers:
            evidence.add(_node(change))
        changes = [i for i, s in discussions.items() if s.kind == "pr"] + [c.id for c in closers]
        incident_rows = self.reader.incidents(changes + list(discussions), view)
        for incident in incident_rows:
            evidence.add(_node(incident, kind="incident"))

        request = ComposeRequest(anchor=resolved.anchor, decisions=decisions, evidence=list(evidence.nodes.values()),
                                 people=people)
        verified = verify(self.composer.compose(request), list(evidence.nodes.values()), superseded)
        incidents = [IncidentRef(id=i.id, url=i.url) for i in incident_rows]
        if not verified.sentences:
            return Answer(anchor=resolved.anchor, refused=True, confidence="Low", refusal_reason="unverified",
                          anchor_matched=matched, evidence_chain=list(evidence.items.values()), people=people,
                          incidents=incidents)
        grounded = tuple(grounding(row, statuses.get(row.decision.id)) for row in rows)
        return Answer(
            anchor=resolved.anchor,
            refused=False,
            anchor_matched=matched,
            confidence=score_confidence(ConfidenceInputs(grounded, dropped=verified.dropped, anchor_matched=matched)),
            decisions=decisions,
            evidence_chain=list(evidence.items.values()),
            people=people,
            incidents=incidents,
            sentences=verified.sentences,
        )

    def _statuses(self, own_record: dict[str, str], view: HistoryView) -> dict[str, SupersessionStatus]:
        """Decision id -> its Supersession status, for the Decisions that are not live."""
        return supersession_statuses(self.reader, own_record, view) if self.supersession else {}

    def _resolve(self, anchor: str) -> _Resolved | None:
        text = anchor.strip()
        if not text or len(text) > MAX_ANCHOR_CHARS or any(ord(c) < 32 and c not in "\t\n\r" for c in text):
            return None
        if len(text) <= MAX_EXACT_CHARS:
            exact = self.reader.resolve(text)
            if exact:  # an ambiguous alias is refused, not guessed
                return _Resolved(exact[0], matched=False) if len(exact) == 1 else None
        found: dict[str, EntityRow] = {}
        for token in _code_tokens(text):
            rows = self.reader.resolve(token)
            if len(rows) == 1:
                found[rows[0].id] = rows[0]
        if len(found) == 1:
            return _Resolved(next(iter(found.values())), matched=False)
        return self._match(text, list(found.values()))

    def _match(self, question: str, named: list[EntityRow]) -> _Resolved | None:
        """The one entity-matching model step: the entities the question names (several) and those whose names
        hold its words are the shortlist; the matcher must be sure, and must pick from the shortlist."""
        if self.matcher is None:
            return None
        words = question_words(question)
        found = self.reader.candidates(words, MAX_CANDIDATES) if words else []
        shortlist = {r.id: r for r in [*named, *found][:MAX_CANDIDATES]}
        if not shortlist:
            return None
        candidates = [EntityCandidate(id=r.id, kind=r.kind, key=r.key) for r in shortlist.values()]
        choice = self.matcher.match(question, candidates)
        if not choice.sure or choice.entity_id not in shortlist:
            return None
        return _Resolved(shortlist[choice.entity_id], matched=True)

    def _people(self, reviewed_records: list[str], speakers: list[str], entity: EntityRow,
                view: HistoryView) -> list[PersonView]:
        seen: dict[tuple[str, str], PersonView] = {}
        rows = self.reader.people(reviewed_records) if reviewed_records else []
        rows += self.reader.people_by_handle(speakers) if speakers else []  # a speaker counts as an author
        for person in rows:
            seen.setdefault((person.handle, person.role),
                            PersonView(handle=person.handle, role=person.role, active=person.active))
        people = sorted(seen.values(), key=lambda p: (not p.active, p.role != "author", p.handle))
        return self._with_next_best(people, entity, view)

    def _with_next_best(self, people: list[PersonView], entity: EntityRow, view: HistoryView) -> list[PersonView]:
        """Point every departed person at the next-best active person, bringing one in from the area if needed."""
        if all(p.active for p in people):
            return people
        best = next((p for p in people if p.active), None)
        if best is None:
            areas = _areas(entity)
            found = self.reader.area_people(areas, view) if areas else []  # active people only
            if not found:
                return people
            best = PersonView(handle=found[0].handle, role=found[0].role, active=True, via=found[0].via)
            people = [best, *people]
        return [p if p.active else p.model_copy(update={"ask_instead": best.handle}) for p in people]

    def _refusal(self, resolved: _Resolved, view: HistoryView) -> Answer:
        """No Decision reaches the Anchor: the nearest evidence (Changes that touched it or its surroundings, Decisions
        governing what contains it) and the people of those records."""
        entity = resolved.entity
        evidence = _Evidence()
        changes = self.reader.nearest_changes(entity.id, view)
        for change in changes:
            evidence.add(_node(change))
        nearby = self.reader.nearby_decisions(entity.id, view)
        for decision, discussion in nearby:
            evidence.add_decision(decision, discussion, discussion_text="")
        records = [c.id for c in changes] + [discussion.id for _, discussion in nearby
                                             if discussion.kind in ("pr", "rfc")]
        return Answer(anchor=resolved.anchor, refused=True, confidence="Low", refusal_reason="ungoverned",
                      anchor_matched=resolved.matched, evidence_chain=list(evidence.items.values()),
                      people=self._people(list(dict.fromkeys(records)), [], entity, view))
