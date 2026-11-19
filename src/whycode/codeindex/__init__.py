"""Code index: the Code Entities (packages, files, functions, cluster settings) at the cutoff commit.

`CodeIndex` is a plain value: build it with `parse_go_tree` (tree-sitter over a checkout) or from entities
directly. It answers the three questions the build asks of code:

- `touched_by(change)`: which entities a Change's diff touches (the basis of hard governs links);
- `mentions(text)`: which entities a piece of text names exactly (the basis of soft governs links);
- each entity's `aliases`: the exact spellings an Anchor may use (stored in the graph for resolution).

Matching is exact, never fuzzy: an alias that names more than one entity is ignored.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

from whycode.history.records import FileChange

EntityKind = Literal["package", "file", "function", "setting"]


@dataclass(frozen=True, slots=True)
class CodeEntity:
    kind: EntityKind
    key: str  # package path | file path | "pkg/path.Func" / "pkg/path.(*Recv).Method" | setting key
    parent: str | None = None  # key of the containing entity (package of a file, file of a function or setting)
    package: str = ""  # package path
    package_name: str = ""  # Go package name
    name: str = ""  # function or method name; setting key; file base name; package name
    receiver: str | None = None  # method receiver type name, without '*' or type parameters
    pointer_receiver: bool = False
    go_var: str | None = None  # Go variable a setting is registered to
    details: dict[str, str] = field(default_factory=dict, compare=False, hash=False)

    @property
    def id(self) -> str:
        """Graph node id of the entity."""
        return entity_id(self.kind, self.key)

    @property
    def file(self) -> str | None:
        if self.kind == "file":
            return self.key
        return self.parent if self.kind in ("function", "setting") else None

    @property
    def aliases(self) -> tuple[str, ...]:
        """Other exact spellings that name this entity (an Anchor may use any of them)."""
        out: list[str] = []
        if self.kind == "package":
            out = [self.package_name]
        elif self.kind == "file":
            out = [self.key.rsplit("/", 1)[-1]]
        elif self.kind == "function":
            local = [self.name]
            if self.receiver:
                star = f"(*{self.receiver}).{self.name}"
                plain = f"{self.receiver}.{self.name}"
                local = [star, plain] if self.pointer_receiver else [plain]
            out = [*local, *(f"{self.package_name}.{n}" for n in local), *(f"{self.package}.{n}" for n in local)]
            if self.receiver:
                out.append(self.name)
        elif self.kind == "setting" and self.go_var:
            out = [self.go_var]
        return tuple(dict.fromkeys(a for a in out if a and a != self.key))


def entity_id(kind: str, key: str) -> str:
    return f"{kind}:{key}"


_FUNC = re.compile(
    r"\bfunc\s+(?:\(\s*(?:[A-Za-z_]\w*\s+)?(\*?)\s*([A-Za-z_]\w*)(?:\[[^\]]*\])?\s*\)\s*)?([A-Za-z_]\w*)\s*[\[(]"
)
_HUNK = re.compile(r"^@@ [^@]* @@(.*)$")


class CodeIndex:
    def __init__(self, entities: Iterable[CodeEntity]):
        self.entities: tuple[CodeEntity, ...] = tuple(sorted(entities, key=lambda e: (e.kind, e.key)))
        self._by_key = {e.key: e for e in self.entities}
        self._functions: dict[tuple[str, str | None, str], CodeEntity] = {
            (e.parent, e.receiver, e.name): e for e in self.entities if e.kind == "function"
        }
        self._settings_by_key = {e.key: e for e in self.entities if e.kind == "setting"}
        self._mention_names = self._unique_names(self._mentionable)
        self._mention_re = (
            re.compile(
                r"(?<![\w./*(])("
                + "|".join(re.escape(n) for n in sorted(self._mention_names, key=len, reverse=True))
                + r")(?![\w/])"
            )
            if self._mention_names
            else None
        )

    def get(self, key: str) -> CodeEntity | None:
        return self._by_key.get(key)

    def touched_by(self, change: FileChange) -> set[CodeEntity]:
        """Entities a file diff touches: the file, functions named by hunk headers or declared on changed
        lines, and settings whose key literal or Go variable appears on a changed line.

        No line-level anchoring: diffs of files the index does not hold touch nothing.
        """
        file = self._by_key.get(change.path) or (change.previous_path and self._by_key.get(change.previous_path))
        if file is None or file.kind != "file":
            return set()
        touched = {file}
        changed: list[str] = []
        for line in (change.patch or "").splitlines():
            if header := _HUNK.match(line):
                touched |= self._declared(file.key, header.group(1))
            elif line[:1] in "+-" and not line.startswith(("+++", "---")):
                changed.append(line[1:])
                touched |= self._declared(file.key, line[1:])
        body = "\n".join(changed)
        for setting in self._settings_by_key.values():
            if f'"{setting.key}"' in body or (
                setting.go_var and setting.package == file.package
                and re.search(rf"\b{re.escape(setting.go_var)}\b", body)
            ):
                touched.add(setting)
        return touched

    def mentions(self, text: str) -> set[CodeEntity]:
        """Entities the text names exactly. Bare function names count only when written as code
        (`name`, name(...)) or when camel-cased, so ordinary words never match."""
        if not self._mention_re or not text:
            return set()
        found: set[CodeEntity] = set()
        for m in self._mention_re.finditer(text):
            name, entity = m.group(1), self._mention_names[m.group(1)]
            if entity.kind == "function" and name == entity.name:
                as_code = (text[m.start() - 1: m.start()] == "`" and text[m.end(): m.end() + 1] == "`") or (
                    text[m.end(): m.end() + 1] == "("
                )
                if not (as_code or re.search(r"[a-z][A-Z]", name)):
                    continue
            found.add(entity)
        return found

    def _declared(self, file_key: str, text: str) -> set[CodeEntity]:
        out = set()
        for m in _FUNC.finditer(text):
            entity = self._functions.get((file_key, m.group(2), m.group(3)))
            if entity:
                out.add(entity)
        return out

    def _mentionable(self, entity: CodeEntity) -> Iterable[str]:
        yield entity.key
        if entity.kind == "file":
            yield from entity.aliases
        elif entity.kind == "function":
            yield from entity.aliases
        elif entity.kind == "setting" and entity.go_var and re.search(r"[a-z][A-Z]", entity.go_var):
            yield entity.go_var

    def _unique_names(self, names_of) -> dict[str, CodeEntity]:
        owners: dict[str, set[CodeEntity]] = defaultdict(set)
        for entity in self.entities:
            for name in names_of(entity):
                owners[name].add(entity)
        return {name: next(iter(es)) for name, es in owners.items() if len(es) == 1}
