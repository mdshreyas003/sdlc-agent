"""Answer engine behind `why(anchor)`: resolve, traverse, compose, verify, score.

1. Resolve the Anchor to one Code Entity: exact key or alias first; otherwise one entity-matching step over
   the code-like tokens of a free-form question. Zero or several candidates: refuse, never guess.
2. Traverse fixed read-only patterns: Anchor -> governing Decisions -> Discussions -> closing Changes ->
   People and Incidents. No planning, no model-written queries.
3. Compose sentences from the retrieved nodes only (the `Composer` seam).
4. Verify in code, then score confidence from graph properties and what verification dropped.

Every Decision is treated as live until ticket 04 adds Supersession to the traversal.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from whycode.answer.compose import ComposeRequest, Composer, EvidenceNode
from whycode.answer.confidence import ConfidenceInputs, DecisionGrounding, score_confidence
from whycode.answer.patterns import GraphReader
from whycode.answer.verify import verify
from whycode.contract import Anchor, Answer, DecisionView, EvidenceItem, IncidentRef, PersonView

MAX_ANCHOR_CHARS = 2000
MAX_EXACT_CHARS = 300
MAX_TOKENS = 30
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


class AnswerEngine:
    def __init__(self, reader: GraphReader, composer: Composer):
        self.reader = reader
        self.composer = composer

    def why(self, anchor: str) -> Answer:
        entity = self._resolve(anchor)
        if entity is None:
            return Answer(anchor=None, refused=True, confidence="Low")
        target = Anchor(kind=entity["kind"], id=entity["key"])
        rows = self.reader.governing(entity["id"])
        if not rows:
            return self._refusal(target, entity["id"])

        evidence = _Evidence()
        decisions: list[DecisionView] = []
        grounding: list[DecisionGrounding] = []
        discussions: dict[str, dict[str, Any]] = {}
        speakers: list[str] = []
        for row in rows:
            d, s = row["decision"], row["discussion"]
            link = "hard" if any(g["link"] == "hard" for g in row["governs"]) else "soft"
            decisions.append(DecisionView(
                id=d["id"], choice=d["choice"], rationale=d["rationale"], quote=d["quote"],
                date=_date(d["date"]), link=link, discussion_id=s["id"],
                alternatives_rejected=list(d.get("alternatives_rejected") or []),
                governs=sorted({g["entity"] for g in row["governs"]}),
            ))
            grounding.append(DecisionGrounding(link=link, source=s["kind"], has_rationale=bool(d["rationale"])))
            discussions[s["id"]] = s
            if d.get("speaker"):
                speakers.append(d["speaker"])
            evidence.add(EvidenceNode(id=d["id"], kind="decision", title=d["choice"], url=s.get("url"),
                                      date=d["date"], text=d["quote"]), quote=d["quote"])
            evidence.add(_node(s), quote=d["quote"])

        issues = [i for i, s in discussions.items() if s["kind"] == "issue"]
        closers = self.reader.closers(issues) if issues else []
        for change in closers:
            evidence.add(_node(change))
        changes = [i for i, s in discussions.items() if s["kind"] == "pull_request"] + [c["id"] for c in closers]
        incident_rows = self.reader.incidents(changes + list(discussions))
        for incident in incident_rows:
            evidence.add(_node(incident, kind="incident"))
        reviewed = [i for i, s in discussions.items() if s["kind"] in ("pull_request", "rfc")]
        people = self._people(reviewed, speakers)

        request = ComposeRequest(anchor=target, decisions=decisions, evidence=list(evidence.nodes.values()),
                                 people=people)
        verified = verify(self.composer.compose(request), list(evidence.nodes.values()))
        incidents = [IncidentRef(id=i["id"], url=i.get("url")) for i in incident_rows]
        if not verified.sentences:
            return Answer(anchor=target, refused=True, confidence="Low",
                          evidence_chain=list(evidence.items.values()), people=people, incidents=incidents)
        return Answer(
            anchor=target,
            refused=False,
            confidence=score_confidence(ConfidenceInputs(tuple(grounding), dropped=verified.dropped)),
            decisions=decisions,
            evidence_chain=list(evidence.items.values()),
            people=people,
            incidents=incidents,
            sentences=verified.sentences,
        )

    def _resolve(self, anchor: str) -> dict[str, Any] | None:
        text = anchor.strip()
        if not text or len(text) > MAX_ANCHOR_CHARS or any(ord(c) < 32 and c not in "\t\n\r" for c in text):
            return None
        if len(text) <= MAX_EXACT_CHARS:
            exact = self.reader.resolve(text)
            if exact:
                return exact[0] if len(exact) == 1 else None  # an ambiguous alias is refused, not guessed
        found: dict[str, dict[str, Any]] = {}
        for token in _code_tokens(text):
            rows = self.reader.resolve(token)
            if len(rows) == 1:
                found[rows[0]["id"]] = rows[0]
        return next(iter(found.values())) if len(found) == 1 else None

    def _people(self, reviewed_records: list[str], speakers: list[str]) -> list[PersonView]:
        seen: dict[tuple[str, str], PersonView] = {}
        rows = self.reader.people(reviewed_records) if reviewed_records else []
        rows += [{**r, "role": "author"} for r in (self.reader.people_by_handle(speakers) if speakers else [])]
        for r in rows:
            seen.setdefault((r["handle"], r["role"]), PersonView(handle=r["handle"], role=r["role"],
                                                                 active=bool(r["active"])))
        return sorted(seen.values(), key=lambda p: (not p.active, p.role != "author", p.handle))

    def _refusal(self, target: Anchor, entity_id: str) -> Answer:
        evidence = _Evidence()
        changes = self.reader.nearest_changes(entity_id)
        for change in changes:
            evidence.add(_node(change))
        nearby = self.reader.nearby_decisions(entity_id)
        for row in nearby:
            d, s = row["decision"], row["discussion"]
            evidence.add(EvidenceNode(id=d["id"], kind="decision", title=d["choice"], url=s.get("url"),
                                      date=d["date"], text=d["quote"]), quote=d["quote"])
            evidence.add(_node(s, text=""), quote=d["quote"])
        records = [c["id"] for c in changes] + [r["discussion"]["id"] for r in nearby
                                                 if r["discussion"]["kind"] in ("pull_request", "rfc")]
        return Answer(anchor=target, refused=True, confidence="Low", evidence_chain=list(evidence.items.values()),
                      people=self._people(list(dict.fromkeys(records)), []))
