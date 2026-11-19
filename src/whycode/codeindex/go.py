"""Parse a Go checkout into a `CodeIndex` with tree-sitter (py-tree-sitter 0.26 API, see notes: go-parsing.md).

Indexes, for each scoped package directory: the package, its non-test, non-generated files, their functions
and methods, and the cluster settings registered through `settings.Register*Setting` with a literal key.
Keys given through constants are skipped rather than guessed (ticket 02 may resolve same-package consts).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import tree_sitter_go
from tree_sitter import Language, Node, Parser, Query, QueryCursor

from whycode.codeindex import CodeEntity, CodeIndex

GO = Language(tree_sitter_go.language())
_PARSER = Parser(GO)
_SETTING_QUERY = Query(
    GO,
    """(call_expression
         function: (selector_expression operand: (identifier) @pkg field: (field_identifier) @fn)
         arguments: (argument_list) @args
         (#eq? @pkg "settings") (#match? @fn "^Register[A-Za-z]*Setting"))""",
)


def parse_go_tree(root: Path, scope: Iterable[str] = ("",)) -> CodeIndex:
    """Index every Go package under `root`/<scope prefix>; keys are paths relative to `root`."""
    root = Path(root)
    entities: dict[str, CodeEntity] = {}
    for prefix in scope:
        for path in sorted((root / prefix).rglob("*.go")):
            rel = path.relative_to(root).as_posix()
            if rel.endswith("_test.go"):
                continue
            src = path.read_bytes()
            if b"Code generated" in src[:500] and b"DO NOT EDIT" in src[:500]:
                continue
            for entity in _parse_file(rel, src):
                entities.setdefault(entity.key, entity)
    return CodeIndex(entities.values())


def _text(node: Node | None) -> str:
    return node.text.decode() if node is not None and node.text is not None else ""


def _parse_file(rel: str, src: bytes) -> list[CodeEntity]:
    tree = _PARSER.parse(src).root_node
    package = rel.rsplit("/", 1)[0] if "/" in rel else ""
    package_name = next(
        (_text(c.named_children[0]) for c in tree.named_children if c.type == "package_clause"), ""
    )
    out = [
        CodeEntity(kind="package", key=package, package=package, package_name=package_name, name=package_name),
        CodeEntity(kind="file", key=rel, parent=package, package=package, package_name=package_name,
                   name=rel.rsplit("/", 1)[-1]),
    ]
    common = {"parent": rel, "package": package, "package_name": package_name}
    for decl in tree.named_children:
        if decl.type == "function_declaration":
            name = _text(decl.child_by_field_name("name"))
            out.append(CodeEntity(kind="function", key=f"{package}.{name}", name=name, **common))
        elif decl.type == "method_declaration":
            name = _text(decl.child_by_field_name("name"))
            receiver, pointer = _receiver(decl)
            local = f"(*{receiver}).{name}" if pointer else f"{receiver}.{name}"
            out.append(CodeEntity(kind="function", key=f"{package}.{local}", name=name, receiver=receiver,
                                  pointer_receiver=pointer, **common))
    for _, caps in QueryCursor(_SETTING_QUERY).matches(tree):
        args = [a for a in caps["args"][0].named_children if a.type != "comment"]
        if len(args) < 3 or args[1].type not in ("interpreted_string_literal", "raw_string_literal"):
            continue
        key = _text(args[1])[1:-1]
        call = caps["args"][0].parent
        out.append(CodeEntity(
            kind="setting", key=key, name=key, go_var=_go_var(call), **common,
            details={"register": _text(caps["fn"][0]), "default": _text(args[3]) if len(args) > 3 else ""},
        ))
    return out


def _receiver(decl: Node) -> tuple[str, bool]:
    params = decl.child_by_field_name("receiver")
    t = params.named_children[0].child_by_field_name("type") if params and params.named_children else None
    pointer = t is not None and t.type == "pointer_type"
    if pointer:
        t = t.named_children[0]
    if t is not None and t.type == "generic_type":
        t = t.child_by_field_name("type")
    return _text(t), pointer


def _go_var(call: Node | None) -> str | None:
    node = call
    while node is not None and node.type not in ("var_spec", "source_file", "function_declaration"):
        node = node.parent
    if node is None or node.type != "var_spec":
        return None
    name = _text(node.child_by_field_name("name"))
    return None if name == "_" else name or None
