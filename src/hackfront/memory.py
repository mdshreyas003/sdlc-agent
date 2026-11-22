"""Memory: reviewable knowledge entries (ADR | rule | episode) proposed from evidence, approved by a human.

Nothing here is automatic past *proposing*. Lifecycle (docs/memory.md):
  draft ──refine(new PR)──> staged ──approve──> approved ──edit/refine──> staged (old version keeps being served)
  draft|staged ──reject(reason)──> rejected (same evidence never re-proposed)      approved ──retire──> retired
Only `served` (the last approved snapshot) is visible to agents. Entries cite evidence ids; approve needs at least one.
`triage` and `draft_body` are plain functions: a model-backed drafter can replace `draft_body` without touching the flow.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

KINDS = ("adr", "rule", "episode")
SIGNALS = {  # deterministic triage: what in the evidence says which kind of knowledge this is
    "adr": r"\b(decided|decision|we will|going with|chose|instead of|rather than|trade-?off|alternative|rejected|because)\b",
    "rule": r"\b(always|never|must|must not|should not|do not|don't|convention|make sure|required)\b",
    "episode": r"\b(regression|revert(ed)?|outage|incident|root cause|broke|hotfix|rollback|workaround)\b",
}
TEMPLATE = {
    "adr": ("Context", "Decision", "Consequences"),
    "rule": ("Rule", "Applies to", "Why"),
    "episode": ("What happened", "Cause", "Fix"),
}
ANCHOR_WEIGHT, DIRECT_WEIGHT = 6, 2
REPLACES = re.compile(r"\b(replaces|supersedes|superseded by)\b", re.I)
OPEN, DONE = ("draft", "staged", "approved"), ("rejected", "retired")


class Conflict(Exception):
    """Entry changed since the caller read it, or the move is not allowed from its status."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text or "") if len(s.strip()) > 12]


def triage(evidence: list[dict]) -> dict:
    """{kind, scores, reason, picked} or {kind: None, reason} when nothing is worth remembering. No model."""
    scores, hits = {k: 0 for k in KINDS}, {k: [] for k in KINDS}
    for e in evidence:
        weight = {"anchor": ANCHOR_WEIGHT, "direct": DIRECT_WEIGHT}.get(e.get("relation"), 1)  # the record itself > what mentions it > linked
        for s in _sentences(e.get("quote", "")):
            for kind, rx in SIGNALS.items():
                if re.search(rx, s, re.I):
                    hits[kind].append((e["id"], s))
                    scores[kind] += weight
    for kind in KINDS:  # picked sentences: the anchor's own first
        hits[kind].sort(key=lambda h: next((e.get("relation") not in ("anchor", "direct") for e in evidence if e["id"] == h[0]), True))
    best = max(KINDS, key=lambda k: (scores[k], -KINDS.index(k)))  # ties go to the earlier kind: adr > rule > episode
    if not scores[best]:
        return {"kind": None, "scores": scores, "picked": [], "reason": "No decision, rule or incident language in the evidence. Nothing proposed."}
    return {"kind": best, "scores": scores, "picked": hits[best][:4],
            "reason": f"{scores[best]} sentence(s) read as {best}; others: " + ", ".join(f"{k} {n}" for k, n in scores.items() if k != best)}


def draft_body(kind: str, picked: list[tuple[str, str]]) -> str:
    """Skeleton filled with verbatim sentences from the evidence. Gaps are marked TODO for the reviewer, never invented."""
    quotes = [s for _, s in picked]
    first, rest = (quotes[0] if quotes else "TODO"), (quotes[1:] or ["TODO"])
    return "\n\n".join(f"## {h}\n{t}" for h, t in zip(TEMPLATE[kind], [first, "\n".join(f"- {q}" for q in rest), "TODO: confirm and complete."]))


def _title(anchor: str, kind: str, picked) -> str:
    base = picked[0][1][:70].rstrip(" .,;:") if picked else anchor
    return f"{anchor}: {base}" if anchor and anchor not in base else base


def propose(ws_entries: list[dict], anchor: str, evidence: list[dict], who: str = "system") -> dict:
    """Decide what to do with fresh evidence. Returns {action, entry?, note}. Caller persists `entry`.

    action: created | refined | unchanged | suppressed | nothing. Re-running on the same evidence is harmless."""
    verdict = triage(evidence)
    if verdict["kind"] is None:
        return {"action": "nothing", "entry": None, "note": verdict["reason"]}
    ids = {e["id"] for e in evidence}
    direct = {e["id"] for e in evidence if e.get("relation") in ("anchor", "direct")} or ids  # shared ancestors alone do not merge entries
    # a source that says it "replaces"/"supersedes" an earlier decision starts a new entry that points back, not a refinement
    replaces = any(REPLACES.search(e.get("quote", "")) for e in evidence if e.get("relation") in ("anchor", "direct"))
    supersedes = None
    own_text = " ".join(e.get("quote", "") for e in evidence if e.get("relation") in ("anchor", "direct"))
    for old in ws_entries:
        overlap = direct & {e["id"] for e in old["evidence"]}
        if not overlap and old.get("anchor") and re.search(rf"(?<![\w-]){re.escape(old['anchor'])}(?![\w-])", own_text):
            overlap = {old["anchor"]}  # the new source names the entry's own anchor ("Keeps the limit from #218"): same topic
        if old["kind"] != verdict["kind"] or not overlap:
            continue
        if old["status"] == "rejected":
            return {"action": "suppressed", "entry": old, "note": f"Rejected earlier ({old.get('reason') or 'no reason given'}). Reopen it to reconsider."}
        if old["status"] == "retired":
            continue
        if replaces and old["status"] in ("approved", "staged"):
            supersedes = supersedes or old["id"]
            continue
        fresh = [e for e in evidence if e["id"] not in {x["id"] for x in old["evidence"]}]
        if not fresh:
            return {"action": "unchanged", "entry": old, "note": "No new evidence for this entry."}
        merged = old["evidence"] + [_ev(e) for e in fresh]
        entry = _revise(old, evidence=merged, body=old["body"] + "\n\n## New evidence\n" + "\n".join(f"- {e['id']}" for e in fresh),
                        note=f"Refined from {anchor}: +{len(fresh)} item(s)", who=who, status="staged")
        return {"action": "refined", "entry": entry, "note": f"Added {len(fresh)} item(s); moved to staged for review."}
    entry = {"id": uuid.uuid4().hex[:10], "kind": verdict["kind"], "status": "draft", "title": _title(anchor, verdict["kind"], verdict["picked"]),
             "body": draft_body(verdict["kind"], verdict["picked"]), "evidence": [_ev(e) for e in evidence], "anchor": anchor,
             "triage": verdict["reason"], "supersedes": supersedes, "version": 1, "served": None, "created_at": now(), "updated_at": now(),
             "revisions": [{"version": 1, "at": now(), "by": who, "note": f"Proposed from {anchor}"}]}
    return {"action": "created", "entry": entry, "note": verdict["reason"]}


def _ev(e: dict) -> dict:
    return {k: e.get(k) for k in ("id", "kind", "title", "quote", "url", "time")}


def _revise(old: dict, *, who: str, note: str, status: str | None = None, **fields) -> dict:
    new = {**old, **fields, "version": old["version"] + 1, "updated_at": now()}
    new["status"] = status or old["status"]
    new["revisions"] = old["revisions"] + [{"version": new["version"], "at": now(), "by": who, "note": note, "diff_from": old["version"]}]
    return new


def edit(entry: dict, version: int, who: str, title: str | None = None, body: str | None = None, kind: str | None = None) -> dict:
    """Human edit. Optimistic: `version` must match. Editing approved memory stages a new version; agents keep the old one."""
    if entry["version"] != version:
        raise Conflict(f"Changed by someone else (now v{entry['version']}). Reload before editing.")
    if entry["status"] in DONE:
        raise Conflict(f"A {entry['status']} entry cannot be edited. Reopen it first.")
    if kind is not None and kind not in KINDS:
        raise ValueError("kind must be adr, rule or episode")
    status = "staged" if entry["status"] == "approved" else entry["status"]
    return _revise(entry, who=who, note="Edited" + (f" (re-kinded to {kind})" if kind and kind != entry["kind"] else ""), status=status,
                   **{k: v for k, v in (("title", title), ("body", body), ("kind", kind)) if v is not None})


def move(entry: dict, action: str, version: int, who: str, reason: str = "") -> dict:
    """approve | reject | reopen | retire. Approve needs evidence and a finished body; every move needs the current version."""
    if entry["version"] != version:
        raise Conflict(f"Changed by someone else (now v{entry['version']}). Reload first.")
    s = entry["status"]
    if action == "approve":
        if s not in ("draft", "staged"):
            raise Conflict(f"Cannot approve a {s} entry.")
        if not entry["evidence"]:
            raise Conflict("Approve needs at least one cited evidence item.")
        if "TODO" in entry["body"]:
            raise Conflict("Resolve the TODO markers before approving.")
        new = _revise(entry, who=who, note="Approved", status="approved")
        new["served"] = {"version": new["version"], "kind": new["kind"], "title": new["title"], "body": new["body"],
                         "evidence": [e["id"] for e in new["evidence"]], "approved_by": who, "approved_at": now()}
        return new
    if action == "reject":
        if s not in ("draft", "staged"):
            raise Conflict(f"Cannot reject a {s} entry. Retire approved memory instead.")
        if entry.get("served"):
            raise Conflict("Approved memory is still served. Retire it, or edit the staged version.")
        if not reason.strip():
            raise Conflict("Say why. The reason stops the same proposal coming back.")
        return _revise(entry, who=who, note=f"Rejected: {reason}", status="rejected", reason=reason.strip())
    if action == "retire":
        if s != "approved" and not (s == "staged" and entry.get("served")):  # a live entry with an update waiting can still be retired
            raise Conflict("Only approved memory can be retired.")
        return _revise(entry, who=who, note=f"Retired: {reason or 'no reason'}", status="retired", served=None, reason=reason.strip())
    if action == "reopen":
        if s not in DONE:
            raise Conflict("Only rejected or retired entries can be reopened.")
        return _revise(entry, who=who, note="Reopened", status="draft", reason=None)
    raise ValueError("action must be approve, reject, retire or reopen")


def served(entries: list[dict], anchor: str = "", evidence_ids=()) -> list[dict]:
    """What agents may read: approved snapshots only, optionally filtered by anchor words or an evidence id."""
    words = [w for w in re.split(r"\W+", anchor.lower()) if len(w) > 2]
    out = []
    for e in entries:
        s = e.get("served")
        if not s or e["status"] not in ("approved", "staged"):
            continue
        hay = f"{s['title']} {s['body']} {' '.join(s['evidence'])}".lower()
        shared = sorted(set(evidence_ids) & set(s["evidence"]))
        # an anchor already resolved through the graph (file, ticket, PR) matches on cited evidence only; free text matches on words
        hit = bool(shared) if evidence_ids else (not words or any(w in hay for w in words) or anchor in s["evidence"])
        if hit:
            out.append({"id": e["id"], **s, "matched_evidence": shared})
    return out


def drift(entry: dict, current: dict[str, dict]) -> list[dict]:
    """Evidence an open or live entry cites whose source text changed since the entry was written.

    `current` maps evidence id -> {title, quote} as the graph holds it now. Missing ids are ignored (not ingested yet)."""
    if entry["status"] in DONE:
        return []
    out = []
    for e in entry["evidence"]:
        now = current.get(e["id"])
        if now and ((now.get("quote") or "") != (e.get("quote") or "") or (now.get("title") or "") != (e.get("title") or "")):
            out.append({"id": e["id"], "title": now.get("title") or e.get("title"), "was": e.get("quote") or "", "now": now.get("quote") or ""})
    return out


def acknowledge(entry: dict, version: int, who: str, current: dict[str, dict]) -> dict:
    """The reviewer checked the changed sources: take their current text as the new baseline (history keeps a note)."""
    if entry["version"] != version:
        raise Conflict(f"Changed by someone else (now v{entry['version']}). Reload first.")
    changed = {d["id"] for d in drift(entry, current)}
    if not changed:
        raise Conflict("Nothing changed in the cited sources.")
    fresh = [{**e, **({k: current[e["id"]].get(k) for k in ("title", "quote")} if e["id"] in changed else {})} for e in entry["evidence"]]
    return _revise(entry, who=who, note=f"Re-checked after {len(changed)} cited source(s) changed", evidence=fresh)
