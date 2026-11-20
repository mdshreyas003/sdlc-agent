"""Parse a Go checkout into a `CodeIndex` with tree-sitter (py-tree-sitter 0.26 API, see notes: go-parsing.md).

Indexes, for each scope entry (a directory, taken recursively, or a single file): the packages, their non-test,
non-generated files, their functions and methods, and the cluster settings registered through
`settings.Register*Setting`. A setting key may be a string literal or a string constant declared in the same
package (any file of the package directory, scoped or not); keys from other packages are skipped rather than
guessed. `settings.WithName` / `settings.WithRetiredName` names become the setting's other names (aliases).
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
_NAME_OPTIONS = ("WithName", "WithRetiredName")
_STRINGS = ("interpreted_string_literal", "raw_string_literal")


def parse_go_tree(root: Path, scope: Iterable[str] = ("",)) -> CodeIndex:
    """Index the Go code under `root` named by `scope` (paths relative to `root`); keys are relative paths."""
    root = Path(root)
    trees: dict[Path, Node | None] = {}

    def tree(path: Path) -> Node | None:
        if path not in trees:
            src = path.read_bytes()
            generated = b"Code generated" in src[:500] and b"DO NOT EDIT" in src[:500]
            trees[path] = None if generated else _PARSER.parse(src).root_node
        return trees[path]

    consts: dict[Path, dict[str, str]] = {}

    def package_consts(directory: Path) -> dict[str, str]:
        if directory not in consts:
            consts[directory] = {}
            for path in sorted(directory.glob("*.go")):
                if not path.name.endswith("_test.go") and (node := tree(path)) is not None:
                    consts[directory].update(_string_consts(node))
        return consts[directory]

    entities: dict[str, CodeEntity] = {}
    for prefix in scope:
        target = root / prefix
        paths = [target] if target.is_file() else sorted(target.rglob("*.go"))
        for path in paths:
            if path.suffix != ".go" or path.name.endswith("_test.go") or (node := tree(path)) is None:
                continue
            rel = path.relative_to(root).as_posix()
            for entity in _entities(rel, node, package_consts(path.parent)):
                entities.setdefault(entity.key, entity)
    return CodeIndex(entities.values())


def _text(node: Node | None) -> str:
    return node.text.decode() if node is not None and node.text is not None else ""


def _string(node: Node | None, consts: dict[str, str]) -> str | None:
    """The value of a string literal, or of a same-package string constant; None for anything else."""
    if node is None:
        return None
    if node.type in _STRINGS:
        return _text(node)[1:-1]
    if node.type == "identifier":
        return consts.get(_text(node))
    return None


def _string_consts(tree: Node) -> dict[str, str]:
    out: dict[str, str] = {}
    for decl in tree.named_children:
        if decl.type != "const_declaration":
            continue
        for spec in decl.named_children:
            if spec.type != "const_spec" or (values := spec.child_by_field_name("value")) is None:
                continue
            exprs = [v for v in values.named_children if v.type != "comment"]
            for name, value in zip(spec.children_by_field_name("name"), exprs):
                if value.type in _STRINGS:
                    out[_text(name)] = _text(value)[1:-1]
    return out


def _entities(rel: str, tree: Node, consts: dict[str, str]) -> list[CodeEntity]:
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
        key = _string(args[1], consts) if len(args) > 2 else None
        if not key:
            continue
        call = caps["args"][0].parent
        out.append(CodeEntity(
            kind="setting", key=key, name=key, go_var=_go_var(call), names=_option_names(args[3:], consts),
            **common,
            details={"register": _text(caps["fn"][0]), "default": _text(args[3]) if len(args) > 3 else ""},
        ))
    return out


def _option_names(options: list[Node], consts: dict[str, str]) -> tuple[str, ...]:
    """Names given by `settings.WithName(...)` / `settings.WithRetiredName(...)` options."""
    names = []
    for option in options:
        fn = option.child_by_field_name("function") if option.type == "call_expression" else None
        if fn is None or fn.type != "selector_expression":
            continue
        if _text(fn.child_by_field_name("operand")) != "settings":
            continue
        if _text(fn.child_by_field_name("field")) not in _NAME_OPTIONS:
            continue
        arguments = option.child_by_field_name("arguments")
        values = [a for a in arguments.named_children if a.type != "comment"] if arguments else []
        if values and (name := _string(values[0], consts)):
            names.append(name)
    return tuple(dict.fromkeys(names))


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
