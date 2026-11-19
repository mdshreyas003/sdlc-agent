"""RFC header parsing (`- Status: completed`, `- RFC PR: [#2842](...)`, ...); see notes: cockroachdb-history.md.

The header is a bullet list (`-` or `*`) in the first lines of the file, sometimes after a `# Title` line;
values may wrap onto indented continuation lines. Field-name variants are folded to one canonical name.
Values are kept exactly as written, with their character span in the file for locators.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_FIELD = re.compile(r"^[ \t]*[-*][ \t]+([A-Za-z][A-Za-z ()]*?)[ \t]*:[ \t]*(.*)$")
_CANONICAL = {
    "rfc prs": "RFC PR",
    "rfc pr": "RFC PR",
    "cockroach issue": "Cockroach Issue",
    "cockroach issues": "Cockroach Issue",
    "cockroach issue(s)": "Cockroach Issue",
    "start date": "Start Date",
    "author": "Authors",
    "authors": "Authors",
    "status": "Status",
    "feature name": "Feature Name",
}
_HEADER_LINES = 25


@dataclass(frozen=True, slots=True)
class HeaderField:
    value: str
    start: int  # character offsets of the value in the file
    end: int


def parse_header(text: str) -> dict[str, HeaderField]:
    fields: dict[str, HeaderField] = {}
    offset, current = 0, None
    for line in text.splitlines(keepends=True)[:_HEADER_LINES]:
        stripped = line.rstrip("\r\n")
        if m := _FIELD.match(stripped):
            name = _CANONICAL.get(m.group(1).strip().lower(), m.group(1).strip())
            current = name if name not in fields else None
            if current:
                fields[current] = HeaderField(m.group(2).strip(), offset + m.start(2), offset + len(stripped))
        elif current and stripped[:1] in (" ", "\t") and stripped.strip():
            prev = fields[current]
            fields[current] = HeaderField(f"{prev.value} {stripped.strip()}".strip(), prev.start,
                                          offset + len(stripped))
        else:
            current = None
        offset += len(line)
    return fields


def normalize_status(raw: str) -> str:
    """`In Progress` -> `in-progress`; `superseded by #48276` -> `superseded`; first word otherwise."""
    words = re.sub(r"[^a-z\- ]", " ", raw.lower()).split()
    if not words:
        return ""
    if words[0] == "in" and len(words) > 1 and words[1] == "progress":
        return "in-progress"
    return words[0]
