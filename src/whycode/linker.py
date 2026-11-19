"""Linker: Stated Links from identifiers people wrote down. No fuzzy, keyword-topic or timing matching.

Rules (ported in spirit from the legacy text-reference extraction, extended for CockroachDB conventions):
- `#N` counts only after a keyword (`Fixes #N`, `Informs: #N`, `See #N`, `PR #N`, ...) or as `(#N)`; a bare
  `#333` is never a reference (CSS colours, anchors). `owner/repo#N` and GitHub pull/issue URLs also count.
- Closing keywords (close/fix/resolve and their forms, optional colon, lists like `Fixes #1, #2`) give
  CLOSES, but only in a pull request's title, description or commit messages, as on GitHub. Elsewhere they
  are plain REFERENCES.
- Reverts give REVERTS: `This reverts commit <full sha>`, `Reverts owner/repo#N` / `revert #N`, and a
  `Revert "<title>"` title that equals exactly one other pull request's title. Abbreviated SHAs never link.
- Commit URLs need the full 40-hex SHA. A GitHub URL inside another URL's query string is ignored.
- RFC file names (`docs/RFCS/20210115_new_schema_changer.md`) link only to RFCs that were ingested.
- RFC headers: every number in `RFC PR`, `Cockroach Issue` and `Status` is a reference, stored as written.
- One link per (source, target): REVERTS beats CLOSES beats REFERENCES; the first locator wins. No self-links.

Each link carries a locator `<field>#<start>-<end>` (character span in the exact stored text).
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

from whycode import ids
from whycode.history.records import History
from whycode.history.rfc import parse_header

_URL = r"https?://github\.com/[\w.-]+/[\w.-]+/(?:pull|issues)/\d+"
_SHORT = r"(?:[\w.-]+/[\w.-]+)?#\d{1,7}"
_REF = rf"(?:{_URL}|{_SHORT})"
_LIST = rf"{_REF}(?:[ \t]*(?:,|and|&)[ \t]*{_REF})*"
_ONE_REF = re.compile(
    r"https?://github\.com/(?P<uo>[\w.-]+)/(?P<ur>[\w.-]+)/(?P<uk>pull|issues)/(?P<un>\d+)"
    r"|(?:(?P<so>[\w.-]+)/(?P<sr>[\w.-]+))?#(?P<sn>\d{1,7})"
)
_CLOSING = re.compile(rf"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b:?\s+(?P<list>{_LIST})")
_REVERTING = re.compile(rf"(?i)\breverts?\b:?\s+(?:pr\s+)?(?P<list>{_LIST})")
_REFERRING = re.compile(
    rf"(?i)\b(?P<kw>prs?|pull(?:\s+requests?)?|refs?|see(?:\s+also)?|follows?|informs?|part\s+of|touches|"
    rf"related\s+to|addresses|backport\s+of)\b:?\s+(?P<list>{_LIST})"
)
_PAREN = re.compile(r"\((#\d{1,7})\)")
_PAGE_URL = re.compile(r"(?<![=&?])https?://github\.com/([\w.-]+)/([\w.-]+)/(pull|issues)/(\d+)")
_COMMIT_URL = re.compile(r"(?<![=&?])https?://github\.com/([\w.-]+)/([\w.-]+)/commit/([0-9a-f]{40})\b")
_REVERTS_COMMIT = re.compile(r"(?i)\bthis reverts commit ([0-9a-f]{40})\b")
_REVERT_TITLE = re.compile(r'^Revert "(.+)"$')
_RFC_NAME = re.compile(r"(?<![A-Za-z0-9_])(\d{8}_[A-Za-z0-9_]+?)(?:\.md)?(?![A-Za-z0-9_])")
_HEADER_NUMBER = re.compile(
    r"https?://github\.com/([\w.-]+)/([\w.-]+)/(pull|issues?)/(\d+)|#?(?<![\w/])(\d{3,7})\b"
)

_STRENGTH = {"REVERTS": 3, "CLOSES": 2, "REFERENCES": 1}
INCIDENT_LABELS = frozenset({"C-bug", "regression", "release-blocker", "GA-blocker", "C-technical-advisory"})


@dataclass(frozen=True, slots=True)
class StatedLink:
    source: str
    type: str  # REFERENCES | CLOSES | REVERTS
    target: str
    locator: str
    observed_at: dt.date


@dataclass(frozen=True, slots=True)
class _Field:
    name: str
    text: str
    at: dt.date
    closing: bool = False  # closing keywords take effect here
    revert: bool = False  # revert statements take effect here


def _url_kind(path_part: str) -> ids.NumberKind:
    return "pr" if path_part == "pull" else "issue"


class _Scanner:
    """Finds identifiers in one text field. A number's kind (pr | issue) comes from the ingested records when
    the number was ingested, else from what its context implies."""

    def __init__(self, history: History):
        self.repo = history.repo
        self.rfc_stems = {rfc.stem for rfc in history.rfcs}
        self.prs = {pr.number for pr in history.pull_requests}
        self.issues = {issue.number for issue in history.issues}

    def target(self, number: str | int, hint: ids.NumberKind, repo: str | None = None) -> str:
        if repo and repo != self.repo:
            return ids.number_id(hint, number, repo)
        n = int(number)
        if n in self.prs:
            return ids.pr_id(n)
        if n in self.issues:
            return ids.issue_id(n)
        return ids.number_id(hint, n)

    def _ref(self, m: re.Match, hint: ids.NumberKind) -> str:
        if m.group("un"):
            return self.target(m.group("un"), _url_kind(m.group("uk")), f"{m.group('uo')}/{m.group('ur')}")
        return self.target(m.group("sn"), hint, f"{m.group('so')}/{m.group('sr')}" if m.group("so") else None)

    def _list(self, pattern: re.Pattern, text: str, kind: str, hint):
        for m in pattern.finditer(text):
            span_start = m.start("list")
            for ref in _ONE_REF.finditer(m.group("list")):
                yield kind, self._ref(ref, hint(m)), span_start + ref.start(), span_start + ref.end()

    def scan(self, f: _Field):
        text = f.text
        if f.revert:
            for m in _REVERTS_COMMIT.finditer(text):
                yield "REVERTS", ids.commit_id(m.group(1)), m.start(1), m.end(1)
        yield from self._list(_REVERTING, text, "REVERTS" if f.revert else "REFERENCES", lambda m: "pr")
        yield from self._list(_CLOSING, text, "CLOSES" if f.closing else "REFERENCES", lambda m: "issue")
        yield from self._list(_REFERRING, text, "REFERENCES",
                              lambda m: "pr" if m.group("kw").lower().startswith(("pr", "pull")) else "issue")
        for m in _PAREN.finditer(text):  # "(#218)": squash-merge titles name pull requests
            yield "REFERENCES", self.target(m.group(1)[1:], "pr"), m.start(1), m.end(1)
        for m in _PAGE_URL.finditer(text):
            yield ("REFERENCES", self.target(m.group(4), _url_kind(m.group(3)), f"{m.group(1)}/{m.group(2)}"),
                   m.start(), m.end())
        for m in _COMMIT_URL.finditer(text):
            yield "REFERENCES", ids.commit_id(m.group(3)), m.start(), m.end()
        for m in _RFC_NAME.finditer(text):
            if m.group(1) in self.rfc_stems:
                yield "REFERENCES", ids.rfc_id(m.group(1)), m.start(), m.end()


_HEADER_HINTS: dict[str, ids.NumberKind] = {"RFC PR": "pr", "Cockroach Issue": "issue", "Status": "pr"}


def stated_links(history: History) -> list[StatedLink]:
    scanner = _Scanner(history)
    best: dict[tuple[str, str], StatedLink] = {}

    def add(link: StatedLink) -> None:
        if link.source == link.target:
            return
        key = (link.source, link.target)
        current = best.get(key)
        if current is None or _STRENGTH[link.type] > _STRENGTH[current.type]:
            best[key] = link

    def scan(source: str, fields: list[_Field]) -> None:
        for f in fields:
            for kind, target, start, end in scanner.scan(f):
                add(StatedLink(source, kind, target, f"{f.name}#{start}-{end}", f.at))

    titles: dict[str, list[int]] = {}
    for pr in history.pull_requests:
        titles.setdefault(pr.title, []).append(pr.number)

    for pr in history.pull_requests:
        source, merged = ids.pr_id(pr.number), pr.merged_at.date()
        scan(source, [
            _Field("title", pr.title, merged, closing=True, revert=True),
            _Field("body", pr.body, merged, closing=True, revert=True),
            *(_Field(f"post[{i}]", p.body, p.at.date()) for i, p in enumerate(pr.posts)),
        ])
        for commit in pr.commits:
            scan(ids.commit_id(commit.sha),
                 [_Field("message", commit.message, (commit.at or pr.merged_at).date(), closing=True, revert=True)])
        if (m := _REVERT_TITLE.match(pr.title)) and len(originals := titles.get(m.group(1), [])) == 1:
            add(StatedLink(source, "REVERTS", ids.pr_id(originals[0]), "title", merged))

    for issue in history.issues:
        source = ids.issue_id(issue.number)
        scan(source, [
            _Field("title", issue.title, issue.created_at.date()),
            _Field("body", issue.body, issue.created_at.date()),
            *(_Field(f"post[{i}]", p.body, p.at.date()) for i, p in enumerate(issue.posts)),
        ])

    for rfc in history.rfcs:
        source = ids.rfc_id(rfc.stem)
        for name, field in parse_header(rfc.text).items():
            if name not in ("RFC PR", "Cockroach Issue", "Status"):
                continue
            for m in _HEADER_NUMBER.finditer(field.value):
                if m.group(4):  # a URL: its path says pull or issue
                    target = scanner.target(m.group(4), _url_kind(m.group(3)), f"{m.group(1)}/{m.group(2)}")
                else:
                    target = scanner.target(m.group(5), _HEADER_HINTS[name])
                add(StatedLink(source, "REFERENCES", target,
                               f"header:{name}#{field.start + m.start()}-{field.start + m.end()}", rfc.date))
        scan(source, [_Field("text", rfc.text, rfc.date)])

    return sorted(best.values(), key=lambda link: (link.source, link.target))


def incident_labels(labels: tuple[str, ...]) -> bool:
    """An issue with one of these labels is an Incident once a Change closes it."""
    return bool(INCIDENT_LABELS & set(labels))
