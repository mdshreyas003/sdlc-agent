"""Automatic labels: gold questions read straight off history, with no model.

Three sources, each a link the project's own authors wrote down:

- RFC `Status:` headers: `superseded by #N` (the RFC whose `RFC PR` is N supersedes it), `rejected`, `obsolete`;
- closing links in pull requests (`Fixes #N`, `Closes`, `Resolves`, or an issue URL), typed `incident`
  when the issue carries a regression, release-blocker or bug label;
- reverts (`Revert "<title>"` or `This reverts commit <sha>`). A revert inside the Held-out Window
  of a Change merged before the cutoff becomes a window question with an answer before and after.

Every label is written `human_verified: false`; a human reviews it before it counts.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Sequence

from whycode.contract import Anchor
from whycode.eval.corpus import Corpus, CorpusRecord
from whycode.eval.gold import GoldEvidence, GoldQuestion, WindowAfter, assign_split

INCIDENT_LABELS = {"C-bug", "regression", "release-blocker", "GA-blocker"}
DEAD_STATUSES = ("rejected", "obsolete")
HEADER_LINES = 25

_FIELD = re.compile(r"^\s*[-*]\s*(?P<key>[A-Za-z][A-Za-z ()]*?)\s*:\s*(?P<value>.*\S)\s*$")
_CLOSES = re.compile(r"\b(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?):?\s+"
                     r"(?:#(?P<num>\d+)|https?://github\.com/[\w.-]+/[\w.-]+/issues/(?P<url_num>\d+))",
                     re.IGNORECASE)
_REVERT_TITLE = re.compile(r'^Revert "(?P<title>.+)"\s*$')
_REVERTS_COMMIT = re.compile(r"This reverts commit (?P<sha>[0-9a-f]{7,40})")


def generate_labels(corpus: Corpus, *, cutoff: dt.date, window_end: dt.date | None = None) -> list[GoldQuestion]:
    records = list(corpus.records())
    questions = [*_rfc_labels(records, cutoff), *_closing_labels(records, cutoff),
                 *_revert_labels(records, cutoff, window_end)]
    return sorted({q.id: q for q in questions}.values(), key=lambda q: q.id)


def _slug(node_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", node_id.lower()).strip("-")


def _label(id: str, **kw) -> GoldQuestion:
    return GoldQuestion(id=id, origin="automatic", split=assign_split(id), human_verified=False, **kw)


def _single_go_file(record: CorpusRecord) -> Anchor | None:
    files = [p for p in record.paths if p.endswith(".go") and not p.endswith("_test.go")]
    return Anchor(kind="file", id=files[0]) if len(files) == 1 else None


def _before(record: CorpusRecord, day: dt.date | None) -> bool:
    return day is None or record.date is None or record.date <= day


# --- RFC status ----------------------------------------------------------------------------------

def _header(rfc: CorpusRecord) -> dict[str, tuple[str, str]]:
    """Header field (lower-cased key) -> (value, the line as written without its bullet)."""
    fields = {}
    for line in rfc.text.splitlines()[:HEADER_LINES]:
        if m := _FIELD.match(line):
            fields.setdefault(m["key"].lower(), (m["value"], line.strip().lstrip("-*").strip()))
    return fields


def _rfc_labels(records: Sequence[CorpusRecord], cutoff: dt.date) -> list[GoldQuestion]:
    rfcs = [r for r in records if r.kind == "rfc" and _before(r, cutoff)]
    headers = {r.id: _header(r) for r in rfcs}

    def name(r: CorpusRecord) -> str:
        return headers[r.id].get("feature name", (r.title, ""))[0]

    def rfc_prs(r: CorpusRecord) -> set[str]:
        return set(re.findall(r"\d{3,}", headers[r.id].get("rfc pr", ("", ""))[0]))

    out = []
    for rfc in rfcs:
        status, status_line = headers[rfc.id].get("status", ("", ""))
        common = dict(question=f'Is the design in the "{name(rfc)}" RFC still the live Decision?',
                      superseded_facts=[f'The design in the "{name(rfc)}" RFC is the live Decision'],
                      type="supersession", id=f"auto-rfc-{_slug(rfc.id)}")
        if (m := re.match(r"superseded\b\D*(\d{3,})", status, re.IGNORECASE)) is not None:
            later = next((r for r in rfcs if r.id != rfc.id and m[1] in rfc_prs(r)), None)
            if later is None:
                continue
            out.append(_label(
                **common, gold_facts=[f'The "{name(rfc)}" RFC was superseded by the "{name(later)}" RFC'],
                gold_evidence=[GoldEvidence(node_id=rfc.id, quote=status_line),
                               GoldEvidence(node_id=later.id, quote=headers[later.id]["rfc pr"][1])],
                note="Generated from the RFC Status header and the superseding RFC's RFC PR header."))
        elif status.strip().lower() in DEAD_STATUSES:
            out.append(_label(**common, gold_facts=[f'The "{name(rfc)}" RFC was {status.strip().lower()}'],
                              gold_evidence=[GoldEvidence(node_id=rfc.id, quote=status_line)],
                              note="Generated from the RFC Status header."))
    return out


# --- closing links -------------------------------------------------------------------------------

def _closing_labels(records: Sequence[CorpusRecord], cutoff: dt.date) -> list[GoldQuestion]:
    issues = {r.number: r for r in records if r.kind == "issue" and r.number is not None}
    out = []
    for pr in records:
        if pr.kind != "pr" or not _before(pr, cutoff):
            continue
        for m in _CLOSES.finditer(pr.text):
            issue = issues.get(int(m["num"] or m["url_num"]))
            if issue is None or not _before(issue, cutoff):
                continue
            incident = bool(INCIDENT_LABELS & set(issue.labels))
            out.append(_label(
                id=f"auto-fixes-{_slug(pr.id)}-{_slug(issue.id)}", type="incident" if incident else "multi_hop",
                question=f'What problem was the change "{pr.title}" made to fix?', anchor=_single_go_file(pr),
                gold_facts=[f'It fixes the issue "{issue.title}"'],
                gold_evidence=[GoldEvidence(node_id=pr.id, quote=m[0]),
                               GoldEvidence(node_id=issue.id, quote=issue.title)],
                note="Generated from a closing link in the pull request."))
    return out


# --- reverts -------------------------------------------------------------------------------------

def _revert_labels(records: Sequence[CorpusRecord], cutoff: dt.date,
                   window_end: dt.date | None) -> list[GoldQuestion]:
    prs = [r for r in records if r.kind == "pr"]
    out = []
    for revert in prs:
        original, quote = _reverted(revert, prs)
        if original is None or not _before(original, cutoff) or not _before(revert, window_end):
            continue
        change = f'The change "{original.title}"'
        common = dict(id=f"auto-revert-{_slug(revert.id)}", anchor=_single_go_file(original),
                      question=f"Is the change \"{original.title}\" still in effect?",
                      note="Generated from a revert of an earlier pull request.")
        evidence = [GoldEvidence(node_id=revert.id, quote=quote),
                    GoldEvidence(node_id=original.id, quote=original.title)]
        if _before(revert, cutoff):
            out.append(_label(**common, type="supersession", gold_facts=[f"{change} was reverted"],
                              gold_evidence=evidence, superseded_facts=[f"{change} is in effect"]))
        else:
            out.append(_label(**common, type="window", gold_facts=[f"{change} is in effect"],
                              gold_evidence=[evidence[1]],
                              after=WindowAfter(gold_facts=[f"{change} was reverted"], gold_evidence=evidence,
                                                superseded_facts=[f"{change} is in effect"])))
    return out


def _reverted(revert: CorpusRecord, prs: Sequence[CorpusRecord]) -> tuple[CorpusRecord | None, str]:
    """The pull request `revert` reverts, and the verbatim text that says so."""
    def earlier(p: CorpusRecord) -> bool:
        return p.id != revert.id and (p.date is None or revert.date is None or p.date <= revert.date)

    if m := _REVERT_TITLE.match(revert.title):
        same = [p for p in prs if p.title == m["title"] and earlier(p)]
        if same:
            return max(same, key=lambda p: p.date or dt.date.min), revert.title
    if m := _REVERTS_COMMIT.search(revert.text):
        for p in prs:
            if earlier(p) and any(c.startswith(m["sha"]) or m["sha"].startswith(c) for c in p.commits if c):
                return p, m[0]
    return None, ""
