"""Code index: the Code Entities (packages, files, functions, cluster settings) at the cutoff commit.

`CodeIndex` is a plain value: build it with `parse_go_tree` (tree-sitter over a checkout) or from entities
directly. It answers the three questions the build asks of code:

- `touched_by(change)`: which entities a Change's diff touches (the basis of hard governs links);
- `changed_lines(change)`: each added or removed line of a diff with the entities it lies in (`check_change`);
- `mentions(text)`: which entities a piece of text names exactly (the basis of soft governs links);
- each entity's `aliases`: the exact spellings an Anchor may use (stored in the graph for resolution).

Matching is exact, never fuzzy: an alias that names more than one entity is ignored.

A changed line lies in the declaration that encloses it: the hunk header (`git diff` prints the nearest top-level
line above the hunk there), or a top-level line inside the hunk above it (a `func` declaration, a setting
registration `x = settings.Register...Setting(`; any other top-level line, such as a closing brace or a comment,
ends the enclosing declaration). A line also touches the functions it declares and the settings it names (key or
name literal, or the Go variable within the setting's package).
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
    names: tuple[str, ...] = ()  # a setting's other user-visible names (settings.WithName / WithRetiredName)
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
        elif self.kind == "setting":
            out = [*self.names, *([self.go_var] if self.go_var else [])]
        return tuple(dict.fromkeys(a for a in out if a and a != self.key))


def entity_id(kind: str, key: str) -> str:
    return f"{kind}:{key}"


_FUNC = re.compile(
    r"\bfunc\s+(?:\(\s*(?:[A-Za-z_]\w*\s+)?(\*?)\s*([A-Za-z_]\w*)(?:\[[^\]]*\])?\s*\)\s*)?([A-Za-z_]\w*)\s*[\[(]"
)
_HUNK = re.compile(r"^@@ [^@]* @@(.*)$")
_REGISTRATION = re.compile(r"^\s*(?:var\s+)?([A-Za-z_]\w*)\s*(?:[\w.*\[\]]+\s*)?=\s*settings\.Register\w*Setting\(")
_LABEL = re.compile(r"^[A-Za-z_]\w*:\s*$")


@dataclass(frozen=True, slots=True)
class ChangedLine:
    """An added (`+`) or removed (`-`) line of a file diff and the functions and settings it lies in or names
    (empty: the line is at file level, e.g. an import or a type)."""

    sign: str
    text: str  # without the sign
    entities: frozenset[CodeEntity]


def _alternation(names: Iterable[str], before: str, after: str) -> re.Pattern | None:
    names = sorted(names, key=len, reverse=True)
    return re.compile(before + "|".join(re.escape(n) for n in names) + after) if names else None


class CodeIndex:
    def __init__(self, entities: Iterable[CodeEntity]):
        self.entities: tuple[CodeEntity, ...] = tuple(sorted(entities, key=lambda e: (e.kind, e.key)))
        self._by_key = {e.key: e for e in self.entities}
        self._functions: dict[tuple[str, str | None, str], CodeEntity] = {
            (e.parent, e.receiver, e.name): e for e in self.entities if e.kind == "function"
        }
        self._settings_by_key = {e.key: e for e in self.entities if e.kind == "setting"}
        self._settings_by_var: dict[tuple[str | None, str], list[CodeEntity]] = defaultdict(list)
        self._settings_by_go_var: dict[str, list[CodeEntity]] = defaultdict(list)
        for s in self._settings_by_key.values():
            if s.go_var:
                self._settings_by_var[(s.parent, s.go_var)].append(s)
                self._settings_by_go_var[s.go_var].append(s)
        self._setting_literals = {name: s for s in self._settings_by_key.values() for name in (s.key, *s.names)}
        self._setting_literal_re = _alternation(self._setting_literals, '"(', ')"')
        self._go_var_re = _alternation(self._settings_by_go_var, r"\b(", r")\b")
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

    def file_of(self, change: FileChange) -> CodeEntity | None:
        """The file entity a diff edits (by its path, or its previous path for a rename); None if not indexed."""
        file = self._by_key.get(change.path) or (change.previous_path and self._by_key.get(change.previous_path))
        return file if file is not None and file.kind == "file" else None

    def touched_by(self, change: FileChange) -> set[CodeEntity]:
        """Entities a file diff touches: the file, and the functions and settings its changed lines lie in or
        name (see the module docstring).

        No line-level anchoring: diffs of files the index does not hold touch nothing.
        """
        file = self.file_of(change)
        if file is None:
            return set()
        return {file}.union(*(line.entities for line in self.changed_lines(change)))

    def changed_lines(self, change: FileChange) -> list[ChangedLine]:
        """The added and removed lines of a file diff, in order, each with the entities it lies in or names."""
        file = self.file_of(change)
        if file is None:
            return []
        out: list[ChangedLine] = []
        enclosing: frozenset[CodeEntity] = frozenset()
        for line in (change.patch or "").splitlines():
            if header := _HUNK.match(line):
                enclosing = self._scope(file, header.group(1).strip()) or frozenset()
                continue
            sign, text = line[:1], line[1:]
            if sign not in (" ", "+", "-") or line.startswith(("+++ ", "--- ")):
                continue  # "\ No newline at end of file", file headers
            scope = self._scope(file, text)
            if sign != " ":
                own = enclosing if scope is None or text[:1] in "})" else scope
                named = self._declared(file.key, text) | self._named_settings(file, text)
                out.append(ChangedLine(sign, text, own | named))
            if scope is not None:
                enclosing = scope
        return out

    def _scope(self, file: CodeEntity, text: str) -> frozenset[CodeEntity] | None:
        """The declaration a line opens: the functions a top-level `func` line declares, the setting a
        registration line declares, nothing for any other top-level line; None for a line inside the current
        declaration (indented, blank, or a label)."""
        if not text.strip():
            return None
        if m := _REGISTRATION.match(text):
            return frozenset(self._settings_by_var.get((file.key, m.group(1)), ()))
        if text[0].isspace() or _LABEL.match(text):
            return None
        return frozenset(self._declared(file.key, text)) if text.startswith("func") else frozenset()

    def _named_settings(self, file: CodeEntity, text: str) -> set[CodeEntity]:
        out: set[CodeEntity] = set()
        if self._setting_literal_re:
            out |= {self._setting_literals[m.group(1)] for m in self._setting_literal_re.finditer(text)}
        if self._go_var_re:
            for m in self._go_var_re.finditer(text):
                out |= {s for s in self._settings_by_go_var[m.group(1)] if s.package == file.package}
        return out

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
        if entity.kind in ("file", "function"):
            yield from entity.aliases
        elif entity.kind == "setting":
            yield from entity.names
            if entity.go_var and re.search(r"[a-z][A-Z]", entity.go_var):
                yield entity.go_var

    def _unique_names(self, names_of) -> dict[str, CodeEntity]:
        owners: dict[str, set[CodeEntity]] = defaultdict(set)
        for entity in self.entities:
            for name in names_of(entity):
                owners[name].add(entity)
        return {name: next(iter(es)) for name, es in owners.items() if len(es) == 1}
