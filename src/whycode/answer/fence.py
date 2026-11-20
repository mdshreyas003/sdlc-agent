"""`check_change(diff)`: Fence Warnings for the Live Decisions a proposed Change would contradict or reverse.

No model is involved; code decides from the graph:

1. Parse the unified diff (`git diff` output) into file diffs.
2. Rebuild a `CodeIndex` from the graph's Code Entities for those files (fixed pattern `diff_entities`) and map
   every changed line to the function or setting it lies in (`CodeIndex.changed_lines`). Files the index does not
   hold touch nothing.
3. Read the Decisions that govern exactly the touched functions and settings (and the file itself, when a
   changed line lies outside all of them), and drop the superseded ones (the same Supersession statuses `why`
   shows): a superseded Decision never warns, a refined one does (partly live).
4. For each remaining Decision, look for evidence, strongest first:
   - `reverses`: a changed line undoes a line that a Change implementing the Decision wrote in that file (the diff
     removes a line it added, or restores a line it removed), and the line lies in code the Decision governs
     (a governed function or setting, or the file itself for a line outside any function or setting). Trivial
     lines (braces, `return err`, comments, import paths) are not evidence.
   - `changes`: the diff edits a function or setting the Decision governs (hard or soft link). Editing a governed
     *file* outside the governed functions and settings is not enough: every Change that touched a file governs
     it, so that would warn on almost any edit.
5. Score confidence with the `why` scorer for that Decision alone (link, source, rationale, inferred
   Supersession), one level lower for `changes`; attach the Incidents the Decision prevented (closed by its
   implementing Changes, or its own issue when that is an Incident). Return the strongest `MAX_WARNINGS`.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from whycode.answer.confidence import ConfidenceInputs, DecisionGrounding, score_confidence
from whycode.answer.engine import supersession_statuses
from whycode.answer.patterns import ALL_HISTORY, GraphReader
from whycode.codeindex import ChangedLine, CodeEntity, CodeIndex
from whycode.contract import ChangeCheck, Confidence, FenceWarning
from whycode.history.records import FileChange

MAX_WARNINGS = 10
MAX_DIFF_CHARS = 2_000_000
MAX_FILES = 200
MAX_LITERALS = 200
MAX_REVERSED_LINES = 10
_LEVELS: tuple[Confidence, ...] = ("Low", "Medium", "High")
_LITERAL = re.compile(r'"([^"\\\n]{1,200})"')
_IDENT = re.compile(r"[A-Za-z_]\w{2,}")
_IMPORT_SPEC = re.compile(r'^(?:[\w.]+\s+)?"[^"]*"$')
_TRIVIAL_WORDS = frozenset("""
break case chan const continue default defer else fallthrough for func goto import interface map package range
return select struct switch type var nil true false err error string bool int int32 int64 uint uint32 uint64 byte
rune len cap make new append panic ctx context Context
""".split())
_KIND_ORDER = {"function": 0, "setting": 1, "file": 2}


# --- unified diff parsing -------------------------------------------------------------------------------------

def _strip_path(raw: str) -> str | None:
    path = raw.split("\t", 1)[0].strip().strip('"')
    if path == "/dev/null":
        return None
    return path[2:] if path.startswith(("a/", "b/")) else path


@dataclass
class _FileDiff:
    old: str | None = None
    new: str | None = None
    status: str = "modified"
    hunks: list[str] | None = None

    def change(self) -> FileChange | None:
        path = self.new or self.old
        if path is None or not self.hunks:
            return None
        status = self.status
        if self.old is None:
            status = "added"
        elif self.new is None:
            status = "removed"
        elif self.old != self.new:
            status = "renamed"
        return FileChange(path=path, status=status, patch="\n".join(self.hunks),
                          previous_path=self.old if status == "renamed" else None)


def parse_diff(text: str) -> list[FileChange]:
    """The file diffs of a unified diff (`git diff`, `diff -u`, with or without `a/` `b/` prefixes)."""
    lines = text[:MAX_DIFF_CHARS].replace("\r\n", "\n").split("\n")
    files: list[_FileDiff] = []
    current: _FileDiff | None = None
    for i, line in enumerate(lines):
        if line.startswith("diff --git "):
            current = _FileDiff()
            files.append(current)
            parts = line[len("diff --git "):].split(" ")
            if len(parts) == 2:
                current.old, current.new = _strip_path(parts[0]), _strip_path(parts[1])
        elif line.startswith("--- ") and i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
            if current is None or current.hunks:
                current = _FileDiff()
                files.append(current)
            current.old = _strip_path(line[4:])
        elif line.startswith("+++ ") and current is not None and not current.hunks:
            current.new = _strip_path(line[4:])
        elif current is None:
            continue
        elif line.startswith("@@"):
            current.hunks = (current.hunks or []) + [line]
        elif current.hunks and line[:1] in (" ", "+", "-", "\\"):
            current.hunks.append(line)
        elif current.hunks and line == "":
            current.hunks.append(" ")  # a blank context line whose leading space was trimmed
        elif line.startswith("new file mode"):
            current.status = "added"
        elif line.startswith("deleted file mode"):
            current.status = "removed"
    out = []
    for f in files:
        if f.status == "added":
            f.old = None
        elif f.status == "removed":
            f.new = None
        if (change := f.change()) is not None:
            out.append(change)
    return out[:MAX_FILES]


# --- evidence -------------------------------------------------------------------------------------------------

def _significant(text: str) -> bool:
    """A line that says something about behaviour: not blank, a comment, an import path or only keywords."""
    t = text.strip()
    if not t or t.startswith(("//", "/*", "* ", "*/")) or _IMPORT_SPEC.match(t):
        return False
    return any(word not in _TRIVIAL_WORDS for word in _IDENT.findall(t))


def _entity(row: dict[str, Any]) -> CodeEntity:
    return CodeEntity(kind=row["kind"], key=row["key"], parent=row.get("parent"), package=row.get("package") or "",
                      package_name=row.get("package_name") or "", name=row.get("name") or "",
                      receiver=row.get("receiver"), pointer_receiver=bool(row.get("pointer_receiver")),
                      go_var=row.get("go_var"), names=tuple(row.get("names") or ()))


def _key(entity_id: str) -> str:
    return entity_id.split(":", 1)[1]


@dataclass(frozen=True, slots=True)
class _Undone:
    line: str  # as the implementing Change wrote it (trimmed)
    entity: str  # where it lies: a governed function or setting, or the file
    restores: bool  # True: the diff restores a line the Change removed; False: removes a line it added


@dataclass(frozen=True, slots=True)
class _Touched:
    file: str  # file node id
    lines: tuple[ChangedLine, ...]


class FenceChecker:
    def __init__(self, reader: GraphReader, supersession: bool = True, max_warnings: int = MAX_WARNINGS):
        self.reader = reader
        self.supersession = supersession
        self.max_warnings = max_warnings

    def check(self, diff: str, as_of: dt.date | None = None, exclude: Iterable[str] = ()) -> ChangeCheck:
        """Fence Warnings for a proposed diff. `as_of` and `exclude` are the same view of history as for `why`."""
        scope = {"as_of": as_of.isoformat() if as_of else ALL_HISTORY, "exclude": sorted(set(exclude))}
        changes = parse_diff(diff)
        if not changes:
            return ChangeCheck()
        touched = self._touched(changes)
        if not touched:
            return ChangeCheck()
        specific = {e.id for t in touched.values() for line in t.lines for e in line.entities}
        entity_ids = sorted({t.file for t in touched.values()} | specific)
        # A file's own Decisions matter only for lines outside every function and setting (every Change that
        # touched the file governs it, so asking for them otherwise would only crowd out the specific ones).
        file_level = {t.file for t in touched.values()
                      if any(not line.entities and _significant(line.text) for line in t.lines)}
        if not specific | file_level:
            return ChangeCheck(touched=entity_ids)
        rows = self.reader.governing_exact(sorted(specific | file_level), **scope)
        statuses = (supersession_statuses(self.reader, {r["decision"]["id"]: r["discussion"]["id"] for r in rows},
                                          scope) if self.supersession and rows else {})
        rows = [r for r in rows if getattr(statuses.get(r["decision"]["id"]), "status", None) != "superseded"]

        implementing = sorted({g["change"] for r in rows for g in r["governs"] if g["link"] == "hard" and g["change"]})
        written: dict[tuple[str, str], tuple[set[str], set[str]]] = {}
        if implementing:
            for w in self.reader.change_lines(implementing, sorted(touched)):
                written[(w["change"], w["path"])] = (set(w["added"]), set(w["removed"]))
        records = {r["decision"]["id"]: self._records(r) for r in rows}
        links = self.reader.incident_links(sorted(set().union(*records.values())), **scope) if records else []

        warnings = []
        for row in rows:
            decision_id = row["decision"]["id"]
            incidents = sorted({link["incident"] for link in links
                                if link["change"] in records[decision_id] or link["incident"] in records[decision_id]})
            warning = self._warning(row, statuses.get(decision_id), touched, written, incidents)
            if warning is not None:
                warnings.append(warning)
        warnings.sort(key=lambda w: (w.kind != "reverses", -_LEVELS.index(w.confidence), w.status != "live",
                                     -(w.date or dt.date.min).toordinal(), w.decision_id))
        return ChangeCheck(touched=entity_ids, warnings=warnings[: self.max_warnings],
                           omitted=max(0, len(warnings) - self.max_warnings))

    def _touched(self, changes: list[FileChange]) -> dict[str, _Touched]:
        """File key -> the file's node id and its changed lines, for the diff's files the code index holds."""
        paths = sorted({c.path for c in changes} | {c.previous_path for c in changes if c.previous_path})
        packages = sorted({p.rsplit("/", 1)[0] for p in paths if "/" in p})
        literals = sorted({m for c in changes for line in (c.patch or "").splitlines() if line[:1] in "+-"
                           for m in _LITERAL.findall(line)})[:MAX_LITERALS]
        index = CodeIndex(_entity(row) for row in self.reader.diff_entities(paths, packages, literals))
        out: dict[str, _Touched] = {}
        for change in changes:
            file = index.file_of(change)
            if file is None:
                continue
            previous = out.get(file.key)
            lines = (previous.lines if previous else ()) + tuple(index.changed_lines(change))
            out[file.key] = _Touched(file.id, lines)
        return out

    @staticmethod
    def _records(row: dict[str, Any]) -> set[str]:
        """The Decision's Discussion and the Changes implementing it (where its Incidents are closed)."""
        return {row["discussion"]["id"]} | {g["change"] for g in row["governs"] if g["link"] == "hard" and g["change"]}

    def _warning(self, row: dict[str, Any], status, touched: dict[str, _Touched],
                 written: dict[tuple[str, str], tuple[set[str], set[str]]], incidents: list[str]) -> FenceWarning | None:
        d, s = row["decision"], row["discussion"]
        governed = {g["entity"] for g in row["governs"]}
        hard = {g["entity"] for g in row["governs"] if g["link"] == "hard"}
        undone_by_change: dict[str, list[_Undone]] = defaultdict(list)
        for change in sorted({g["change"] for g in row["governs"] if g["link"] == "hard" and g["change"]}):
            for path, t in touched.items():
                if (change, path) in written:
                    undone_by_change[change] += _undone(t, governed, *written[(change, path)])
        undone_by_change = {c: u for c, u in undone_by_change.items() if u}

        kind, entity, change_id, undone = "changes", None, None, []
        if undone_by_change:
            kind = "reverses"
            change_id = max(sorted(undone_by_change), key=lambda c: len(undone_by_change[c]))
            undone = undone_by_change[change_id]
            counts = Counter(u.entity for u in undone)
            entity = min(counts, key=lambda e: (-counts[e], _KIND_ORDER.get(e.split(":", 1)[0], 3), e))
        else:
            edited = {e.id for t in touched.values() for line in t.lines for e in line.entities} & governed
            if not edited:
                return None
            entity = min(edited, key=lambda e: (e not in hard, _KIND_ORDER.get(e.split(":", 1)[0], 3), e))

        link = "hard" if kind == "reverses" or entity in hard else "soft"
        grounding = DecisionGrounding(link=link, source=s["kind"], has_rationale=bool(d.get("rationale")),
                                      status=status.status if status else "live",
                                      supersession=status.edge["basis"] if status else None)
        confidence = score_confidence(ConfidenceInputs((grounding,)))
        if kind == "changes":
            confidence = _LEVELS[max(_LEVELS.index(confidence) - 1, 0)]
        return FenceWarning(
            decision_id=d["id"], entity_id=entity, quote=d["quote"], incident_ids=incidents, confidence=confidence,
            kind=kind, choice=d["choice"], status=status.status if status else "live", discussion_id=s["id"],
            url=s.get("url"), date=dt.date.fromisoformat(d["date"][:10]) if d.get("date") else None,
            change_id=change_id, reversed_lines=list(dict.fromkeys(u.line for u in undone))[:MAX_REVERSED_LINES],
            reason=_reason(kind, entity, link, s["id"], change_id, undone, status, incidents),
        )


def _undone(touched: _Touched, governed: set[str], added: set[str], removed: set[str]) -> list[_Undone]:
    """The diff's lines that undo what a Change wrote in this file, inside code the Decision governs."""
    out = []
    for line in touched.lines:
        text = line.text.strip()
        restores = line.sign == "+"
        if not _significant(text) or text not in (removed if restores else added):
            continue
        specific = {e.id for e in line.entities}
        inside = specific & governed if specific else ({touched.file} & governed)
        for entity in sorted(inside):
            out.append(_Undone(text, entity, restores))
    return out


def _reason(kind: str, entity: str, link: str, discussion: str, change: str | None, undone: list[_Undone],
            status, incidents: list[str]) -> str:
    where = _key(entity)
    if kind == "reverses":
        removed = list(dict.fromkeys(u.line for u in undone if not u.restores))
        restored = list(dict.fromkeys(u.line for u in undone if u.restores))
        parts = []
        if removed:
            parts.append(f"removes {len(removed)} line(s) it added")
        if restored:
            parts.append(f"restores {len(restored)} line(s) it removed")
        example = (removed or restored)[0]
        text = (f"This diff undoes {change}, which implemented this Decision: it {' and '.join(parts)} in {where} "
                f"(e.g. `{example}`).")
    else:
        how = "its implementing Change touched it" if link == "hard" else f"{discussion} names it"
        text = (f"This diff edits {where}, which this Decision governs ({how}); check that the edit does not "
                f"contradict it.")
    if status is not None and status.status == "refined":
        by = status.by or status.edge["source"]["id"]
        text += (f" The Decision is partly live: {by} refined it on {status.edge['at'][:10]}; what that did not "
                 f"change still holds.")
    if incidents:
        text += f" Incidents it prevented: {', '.join(incidents)}."
    return text
