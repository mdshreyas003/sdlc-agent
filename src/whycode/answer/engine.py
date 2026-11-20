"""Answer engine behind `why(anchor)`: resolve, traverse, compose, verify, score.

1. Resolve the Anchor to one Code Entity: exact key or alias first; then exactly one Code Entity named by the
   code-like tokens of a free-form question; otherwise one entity-matching model step (the `EntityMatcher` seam)
   over a shortlist of Code Entities found from the question's words. Unsure, off the shortlist, or no matcher:
   refuse, never guess. A matched Anchor rests on model judgment, so its answer is at most Medium confidence.
2. Traverse fixed read-only patterns: Anchor -> governing Decisions -> Supersession -> Discussions -> closing
   Changes -> People and Incidents. No planning, no model-written queries.
3. Compose sentences from the retrieved nodes only (the `Composer` seam).
4. Verify in code, then score confidence from graph properties and what verification dropped.

Supersession sets each Decision's status. A Decision with a SUPERSEDES edge into it is superseded. Otherwise,
one with a REFINES edge from a Decision that is not itself superseded is refined (a refinement that was later
reverted no longer narrows anything). Among several edges the strongest names the superseder: explicit before
inferred, a Decision before a record, then the earliest. `supersession=False` builds the scoreboard's
"without supersession" system: every Decision is treated as live.

Person to Ask: the authors and approving reviewers of the Decisions' records, active first. Each departed one's
`ask_instead` is the next-best active person: the first active person already listed, else the author or approver
of the latest Change touching the nearest enclosing area of the code (the Anchor's file, then its directories up
to two levels deep), who is then listed with `via` naming that Change.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from whycode.answer.compose import Composer, ComposeRequest, EvidenceNode
from whycode.answer.confidence import ConfidenceInputs, DecisionGrounding, score_confidence
from whycode.answer.patterns import ALL_HISTORY, GraphReader
from whycode.answer.resolve import EntityCandidate, EntityMatcher, question_words
from whycode.answer.verify import Superseded, verify
from whycode.contract import Anchor, Answer, DecisionView, EvidenceItem, IncidentRef, PersonView

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


def _areas(entity: dict[str, Any]) -> list[str]:
    """Path prefixes of the areas enclosing a Code Entity, nearest first: its file, then its directories."""
    if entity.get("file"):
        path, out = entity["file"], [entity["file"]]
    elif entity["kind"] == "package":
        path, out = entity["key"].rstrip("/") + "/", []
    else:
        return []
    parts = path.rstrip("/").split("/")
    top = len(parts) - (0 if path.endswith("/") else 1)
    return out + ["/".join(parts[:i]) + "/" for i in range(top, MIN_AREA_DEPTH - 1, -1)]


@dataclass(frozen=True, slots=True)
class _Resolved:
    entity: dict[str, Any]
    matched: bool  # chosen by the entity-matching model step, not by an exact name


def _date(value: str | None) -> dt.date | None:
    return dt.date.fromisoformat(value[:10]) if value else None


def _node(row: dict[str, Any], kind: str | None = None, text: str | None = None) -> EvidenceNode:
    return EvidenceNode(id=row["id"], kind=kind or row.get("kind") or "record", title=row.get("title"),
                        url=row.get("url"), date=row.get("date"), text=text if text is not None else row.get("text") or "")


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
                                           title=node.title, date=_date(node.date))


@dataclass(frozen=True, slots=True)
class _Status:
    status: str  # superseded | refined
    edge: dict[str, Any]  # a `supersession` pattern row
    by: str | None  # superseding node, None when the Decision's own record declares it dead


def _rank(row: dict[str, Any], own_record: str) -> tuple:
    by = row["by"]
    return (row["basis"] != "explicit", by.get("choice") is None, by["id"] == own_record, row["at"], by["id"])


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
        scope = {"as_of": as_of.isoformat() if as_of else ALL_HISTORY, "exclude": sorted(set(exclude))}
        resolved = self._resolve(anchor)
        if resolved is None:
            return Answer(anchor=None, refused=True, confidence="Low", refusal_reason="unresolved")
        entity, matched = resolved.entity, resolved.matched
        target = Anchor(kind=entity["kind"], id=entity["key"])
        rows = self.reader.governing(entity["id"], **scope)
        if not rows:
            return self._refusal(target, entity, scope, matched)

        evidence = _Evidence()
        decisions: list[DecisionView] = []
        grounding: list[DecisionGrounding] = []
        discussions: dict[str, dict[str, Any]] = {}
        speakers: list[str] = []
        statuses = self._statuses({r["decision"]["id"]: r["discussion"]["id"] for r in rows}, scope)
        superseded: dict[str, Superseded] = {}
        for row in rows:
            d, s = row["decision"], row["discussion"]
            link = "hard" if any(g["link"] == "hard" for g in row["governs"]) else "soft"
            st = statuses.get(d["id"])
            history = {}
            if st is not None:
                history = dict(status=st.status, superseded_by=st.by, superseded_at=_date(st.edge["at"]),
                               explicit_or_inferred=st.edge["basis"], supersession_quote=st.edge["quote"],
                               supersession_source=st.edge["source"]["id"])
            decisions.append(DecisionView(
                id=d["id"], choice=d["choice"], rationale=d["rationale"], quote=d["quote"],
                date=_date(d["date"]), link=link, discussion_id=s["id"],
                alternatives_rejected=list(d.get("alternatives_rejected") or []),
                governs=sorted({g["entity"] for g in row["governs"]}), **history,
            ))
            grounding.append(DecisionGrounding(link=link, source=s["kind"], has_rationale=bool(d["rationale"]),
                                               status=st.status if st else "live",
                                               supersession=st.edge["basis"] if st else None))
            discussions[s["id"]] = s
            if d.get("speaker"):
                speakers.append(d["speaker"])
            evidence.add(EvidenceNode(id=d["id"], kind="decision", title=d["choice"], url=s.get("url"),
                                      date=d["date"], text=d["quote"]), quote=d["quote"])
            evidence.add(_node(s), quote=d["quote"])
        for decision_id, st in statuses.items():
            self._add_superseder(evidence, st)
            if st.status == "superseded":
                witnesses = {st.by, st.edge["source"]["id"]} - {None}
                superseded[decision_id] = Superseded(quote=next(d.quote for d in decisions if d.id == decision_id),
                                                     witnesses=frozenset(witnesses))

        issues = [i for i, s in discussions.items() if s["kind"] == "issue"]
        closers = self.reader.closers(issues, **scope) if issues else []
        for change in closers:
            evidence.add(_node(change))
        changes = [i for i, s in discussions.items() if s["kind"] == "pr"] + [c["id"] for c in closers]
        incident_rows = self.reader.incidents(changes + list(discussions), **scope)
        for incident in incident_rows:
            evidence.add(_node(incident, kind="incident"))
        reviewed = [i for i, s in discussions.items() if s["kind"] in ("pr", "rfc")]
        people = self._people(reviewed, speakers, entity, scope)

        request = ComposeRequest(anchor=target, decisions=decisions, evidence=list(evidence.nodes.values()),
                                 people=people)
        verified = verify(self.composer.compose(request), list(evidence.nodes.values()), superseded)
        incidents = [IncidentRef(id=i["id"], url=i.get("url")) for i in incident_rows]
        if not verified.sentences:
            return Answer(anchor=target, refused=True, confidence="Low", refusal_reason="unverified",
                          anchor_matched=matched, evidence_chain=list(evidence.items.values()), people=people,
                          incidents=incidents)
        return Answer(
            anchor=target,
            refused=False,
            anchor_matched=matched,
            confidence=score_confidence(ConfidenceInputs(tuple(grounding), dropped=verified.dropped,
                                                         anchor_matched=matched)),
            decisions=decisions,
            evidence_chain=list(evidence.items.values()),
            people=people,
            incidents=incidents,
            sentences=verified.sentences,
        )

    def _statuses(self, own_record: dict[str, str], scope: dict[str, Any]) -> dict[str, _Status]:
        """Decision id -> its Supersession status, for the Decisions that are not live."""
        if not self.supersession or not own_record:
            return {}
        rows = self.reader.supersession(sorted(own_record), **scope)
        refiners = sorted({r["by"]["id"] for r in rows if r["type"] == "REFINES"})
        dead_refiners = {r["decision"] for r in (self.reader.supersession(refiners, **scope) if refiners else [])
                         if r["type"] == "SUPERSEDES"}
        edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            edges[r["decision"]].append(r)
        out = {}
        for decision_id, found in edges.items():
            for status, type_ in (("superseded", "SUPERSEDES"), ("refined", "REFINES")):
                candidates = [r for r in found if r["type"] == type_ and r["by"]["id"] not in
                              (dead_refiners if type_ == "REFINES" else ())]
                if candidates:
                    best = min(candidates, key=lambda r: _rank(r, own_record[decision_id]))
                    by = best["by"]["id"]
                    out[decision_id] = _Status(status, best, None if by == own_record[decision_id] else by)
                    break
        return out

    @staticmethod
    def _add_superseder(evidence: _Evidence, st: _Status) -> None:
        by, source, quote = st.edge["by"], st.edge["source"], st.edge["quote"]
        if by.get("choice") is not None:  # a Decision: grounded by its own quote in its Discussion
            home = st.edge["by_discussion"]
            evidence.add(EvidenceNode(id=by["id"], kind="decision", title=by["choice"], url=home.get("url"),
                                      date=by["date"], text=by["quote"]), quote=by["quote"])
            evidence.add(_node(home), quote=quote if home["id"] == source["id"] else by["quote"])
        evidence.add(_node(source), quote=quote)
        if by["id"] != source["id"] and by.get("choice") is None:
            evidence.add(_node(by))

    def _resolve(self, anchor: str) -> _Resolved | None:
        text = anchor.strip()
        if not text or len(text) > MAX_ANCHOR_CHARS or any(ord(c) < 32 and c not in "\t\n\r" for c in text):
            return None
        if len(text) <= MAX_EXACT_CHARS:
            exact = self.reader.resolve(text)
            if exact:  # an ambiguous alias is refused, not guessed
                return _Resolved(exact[0], matched=False) if len(exact) == 1 else None
        found: dict[str, dict[str, Any]] = {}
        for token in _code_tokens(text):
            rows = self.reader.resolve(token)
            if len(rows) == 1:
                found[rows[0]["id"]] = rows[0]
        if len(found) == 1:
            return _Resolved(next(iter(found.values())), matched=False)
        return self._match(text, list(found.values()))

    def _match(self, question: str, named: list[dict[str, Any]]) -> _Resolved | None:
        """The one entity-matching model step: the entities the question names (several) and those whose names
        hold its words are the shortlist; the matcher must be sure, and must pick from the shortlist."""
        if self.matcher is None:
            return None
        words = question_words(question)
        found = self.reader.candidates(words, MAX_CANDIDATES) if words else []
        shortlist = {r["id"]: r for r in [*named, *found][:MAX_CANDIDATES]}
        if not shortlist:
            return None
        candidates = [EntityCandidate(id=r["id"], kind=r["kind"], key=r["key"]) for r in shortlist.values()]
        choice = self.matcher.match(question, candidates)
        if not choice.sure or choice.entity_id not in shortlist:
            return None
        return _Resolved(shortlist[choice.entity_id], matched=True)

    def _people(self, reviewed_records: list[str], speakers: list[str], entity: dict[str, Any],
                scope: dict[str, Any]) -> list[PersonView]:
        seen: dict[tuple[str, str], PersonView] = {}
        rows = self.reader.people(reviewed_records) if reviewed_records else []
        rows += [{**r, "role": "author"} for r in (self.reader.people_by_handle(speakers) if speakers else [])]
        for r in rows:
            seen.setdefault((r["handle"], r["role"]), PersonView(handle=r["handle"], role=r["role"],
                                                                 active=bool(r["active"])))
        people = sorted(seen.values(), key=lambda p: (not p.active, p.role != "author", p.handle))
        return self._with_next_best(people, entity, scope)

    def _with_next_best(self, people: list[PersonView], entity: dict[str, Any],
                        scope: dict[str, Any]) -> list[PersonView]:
        """Point every departed person at the next-best active person, bringing one in from the area if needed."""
        if all(p.active for p in people):
            return people
        best = next((p for p in people if p.active), None)
        if best is None:
            areas = _areas(entity)
            rows = self.reader.area_people(areas, **scope) if areas else []  # active people only
            if not rows:
                return people
            row = rows[0]
            best = PersonView(handle=row["handle"], role=row["role"], active=True, via=row["via"])
            people = [best, *people]
        return [p if p.active else p.model_copy(update={"ask_instead": best.handle}) for p in people]

    def _refusal(self, target: Anchor, entity: dict[str, Any], scope: dict[str, Any], matched: bool) -> Answer:
        entity_id = entity["id"]
        evidence = _Evidence()
        changes = self.reader.nearest_changes(entity_id, **scope)
        for change in changes:
            evidence.add(_node(change))
        nearby = self.reader.nearby_decisions(entity_id, **scope)
        for row in nearby:
            d, s = row["decision"], row["discussion"]
            evidence.add(EvidenceNode(id=d["id"], kind="decision", title=d["choice"], url=s.get("url"),
                                      date=d["date"], text=d["quote"]), quote=d["quote"])
            evidence.add(_node(s, text=""), quote=d["quote"])
        records = [c["id"] for c in changes] + [r["discussion"]["id"] for r in nearby
                                                 if r["discussion"]["kind"] in ("pr", "rfc")]
        return Answer(anchor=target, refused=True, confidence="Low", refusal_reason="ungoverned",
                      anchor_matched=matched, evidence_chain=list(evidence.items.values()),
                      people=self._people(list(dict.fromkeys(records)), [], entity, scope))
