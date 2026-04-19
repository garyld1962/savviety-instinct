"""Python LanguageAdapter using tree-sitter-python.

Responsibilities (arch §5.5):
- Parse Python source bytes into a tree-sitter tree.
- Walk the tree to extract FunctionDef, ClassDef, and CallSite nodes.
- Compute `ast_hash` per function/class via `parse.hashing`.
- Report syntax errors as ParseError, not exceptions.

Intra-file resolution: a CallSite is `is_resolved=True` iff its `callee_name`
matches a FunctionDef.name defined in the same file at any scope. Cross-file
resolution is deferred (Scope Decision #2).
"""

from __future__ import annotations

from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language as TSLanguage
from tree_sitter import Node, Parser, Tree

from savviety_instinct.core.types import Language, SourceRange
from savviety_instinct.parse.hashing import hash_ast_sexp
from savviety_instinct.parse.types import (
    CallSiteNode,
    ClassDefNode,
    FunctionDefNode,
    ParseError,
    ParseErrorKind,
    ParseResult,
)

_PY_LANGUAGE = TSLanguage(tspython.language())


def _make_parser() -> Parser:
    parser = Parser()
    parser.language = _PY_LANGUAGE
    return parser


class PythonAdapter:
    """tree-sitter-python adapter. Stateless; safe to share across calls."""

    language: Language = Language.PYTHON

    def __init__(self) -> None:
        self._parser = _make_parser()

    def parse_path(self, path: Path) -> ParseResult:
        try:
            source = path.read_bytes()
        except OSError as exc:
            return ParseResult(
                file_path=str(path),
                language=Language.PYTHON,
                functions=(),
                classes=(),
                call_sites=(),
                errors=(ParseError(kind=ParseErrorKind.IO, message=str(exc), source_range=None),),
            )
        return self.parse_source(source, str(path))

    def parse_source(self, source: bytes, file_path: str) -> ParseResult:
        tree = self._parser.parse(source)
        errors = tuple(_collect_syntax_errors(tree, source, file_path))
        functions = tuple(_collect_functions(tree, source, file_path))
        classes = tuple(_collect_classes(tree, source, file_path, functions))
        local_names = {fn.name for fn in functions} | {fn.qualified_name for fn in functions}
        call_sites = tuple(_collect_call_sites(tree, source, file_path, local_names, functions))

        return ParseResult(
            file_path=file_path,
            language=Language.PYTHON,
            functions=functions,
            classes=classes,
            call_sites=call_sites,
            errors=errors,
        )


# ---------- helpers (module-private) ----------


def _source_range(node: Node, file_path: str) -> SourceRange:
    start, end = node.start_point, node.end_point
    return SourceRange(
        file_path=file_path,
        line_start=start[0] + 1,  # tree-sitter is 0-indexed; editors are 1-indexed
        line_end=end[0] + 1,
    )


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _sexp(node: Node) -> str:
    """Get the s-expression for a node. tree-sitter 0.23 uses str(node); older
    versions had .sexp(). Check both defensively."""
    if hasattr(node, "sexp"):
        return node.sexp()  # type: ignore[no-any-return]
    return str(node)


def _collect_syntax_errors(tree: Tree, source: bytes, file_path: str) -> list[ParseError]:
    errors: list[ParseError] = []
    stack: list[Node] = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.is_error or node.is_missing:
            errors.append(
                ParseError(
                    kind=ParseErrorKind.SYNTAX,
                    message=f"tree-sitter parse error at L{node.start_point[0] + 1}",
                    source_range=_source_range(node, file_path),
                )
            )
        stack.extend(node.children)
    return errors


def _collect_functions(tree: Tree, source: bytes, file_path: str) -> list[FunctionDefNode]:
    out: list[FunctionDefNode] = []
    stack: list[tuple[Node, str | None]] = [(tree.root_node, None)]
    while stack:
        node, enclosing_class = stack.pop()
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                continue
            name = _text(name_node, source)
            qualified = f"{enclosing_class}.{name}" if enclosing_class else name
            params = _extract_parameter_names(node, source)
            out.append(
                FunctionDefNode(
                    name=name,
                    qualified_name=qualified,
                    enclosing_class=enclosing_class,
                    source_range=_source_range(node, file_path),
                    ast_hash=hash_ast_sexp(_sexp(node)),
                    parameter_names=params,
                )
            )
            # Do not recurse into nested functions for Slice 2
            continue
        new_enclosing = enclosing_class
        if node.type == "class_definition":
            class_name_node = node.child_by_field_name("name")
            if class_name_node is not None:
                new_enclosing = _text(class_name_node, source)
        stack.extend((child, new_enclosing) for child in node.children)
    return out


def _collect_classes(
    tree: Tree,
    source: bytes,
    file_path: str,
    functions: tuple[FunctionDefNode, ...],
) -> list[ClassDefNode]:
    out: list[ClassDefNode] = []
    method_index: dict[str, list[str]] = {}
    for fn in functions:
        if fn.enclosing_class is not None:
            method_index.setdefault(fn.enclosing_class, []).append(fn.qualified_name)

    stack: list[Node] = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                continue
            name = _text(name_node, source)
            out.append(
                ClassDefNode(
                    name=name,
                    source_range=_source_range(node, file_path),
                    ast_hash=hash_ast_sexp(_sexp(node)),
                    method_qualified_names=tuple(method_index.get(name, ())),
                )
            )
        stack.extend(node.children)
    return out


def _collect_call_sites(
    tree: Tree,
    source: bytes,
    file_path: str,
    local_names: set[str],
    functions: tuple[FunctionDefNode, ...],
) -> list[CallSiteNode]:
    ranges: list[tuple[int, int, str]] = []
    for fn in functions:
        rng = _node_byte_range_for_qualified(fn, source, tree)
        if rng is not None:
            ranges.append(rng)

    def _enclosing(call_node: Node) -> str | None:
        start = call_node.start_byte
        best: tuple[int, int, str] | None = None
        for r in ranges:
            if r[0] <= start < r[1] and (best is None or (r[1] - r[0]) < (best[1] - best[0])):
                best = r
        return best[2] if best else None

    out: list[CallSiteNode] = []
    stack: list[Node] = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type == "call":
            func_node = node.child_by_field_name("function")
            if func_node is not None:
                callee = _callee_name_from_node(func_node, source)
                if callee is not None:
                    out.append(
                        CallSiteNode(
                            callee_name=callee,
                            source_range=_source_range(node, file_path),
                            enclosing_function=_enclosing(node),
                            is_resolved=_is_resolved(callee, local_names, functions),
                        )
                    )
        stack.extend(node.children)
    return out


def _node_byte_range_for_qualified(
    fn: FunctionDefNode, source: bytes, tree: Tree
) -> tuple[int, int, str] | None:
    stack: list[Node] = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node is not None and _text(name_node, source) == fn.name:
                return (node.start_byte, node.end_byte, fn.qualified_name)
        stack.extend(node.children)
    return None


def _callee_name_from_node(node: Node, source: bytes) -> str | None:
    if node.type == "identifier":
        return _text(node, source)
    if node.type == "attribute":
        attr = node.child_by_field_name("attribute")
        if attr is not None:
            return _text(attr, source)
    return None


def _is_resolved(
    callee: str, local_names: set[str], functions: tuple[FunctionDefNode, ...]
) -> bool:
    if callee in local_names:
        return True
    return any(fn.name == callee for fn in functions)


def _extract_parameter_names(func_node: Node, source: bytes) -> tuple[str, ...]:
    params_node = func_node.child_by_field_name("parameters")
    if params_node is None:
        return ()
    names: list[str] = []
    for child in params_node.children:
        if child.type == "identifier":
            names.append(_text(child, source))
        elif child.type in {"typed_parameter", "default_parameter", "typed_default_parameter"}:
            ident = child.child_by_field_name("name")
            if ident is None:
                for grand in child.children:
                    if grand.type == "identifier":
                        names.append(_text(grand, source))
                        break
            else:
                names.append(_text(ident, source))
    return tuple(names)


# Module-level singleton — imported by parse.adapter for registry.
PYTHON_ADAPTER = PythonAdapter()
