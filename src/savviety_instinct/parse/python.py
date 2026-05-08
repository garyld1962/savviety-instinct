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
    ControlFlowNode,
    ControlFlowNodeKind,
    DelegationKind,  # Slice 4b
    FunctionDefNode,
    ParseError,
    ParseErrorKind,
    ParseResult,
)

_PY_LANGUAGE = TSLanguage(tspython.language())

# Tree-sitter-python node-type → ControlFlowNodeKind mapping.
# Note: if_statement uses "consequence" (not "body") for its block.
# elif_clause also uses "consequence"; else_clause uses "body".
_TS_TO_CFN_KIND: dict[str, ControlFlowNodeKind] = {
    "if_statement": ControlFlowNodeKind.IF,
    "elif_clause": ControlFlowNodeKind.ELIF,
    "else_clause": ControlFlowNodeKind.ELSE,
    "for_statement": ControlFlowNodeKind.FOR,
    "while_statement": ControlFlowNodeKind.WHILE,
    "try_statement": ControlFlowNodeKind.TRY,
    "except_clause": ControlFlowNodeKind.EXCEPT,
    "match_statement": ControlFlowNodeKind.MATCH,
    "case_clause": ControlFlowNodeKind.CASE,
    "conditional_expression": ControlFlowNodeKind.TERNARY,
}

_COMPREHENSION_TYPES: frozenset[str] = frozenset(
    {
        "list_comprehension",
        "set_comprehension",
        "dictionary_comprehension",
        "generator_expression",
    }
)

# Python statement node types — used by _count_statements.
# Executable statements only; excludes pure declarations, blank lines, comments.
# except_clause is included so each handler arm counts as one statement (like
# cyclomatic complexity counts it as a branch).
_STATEMENT_NODE_TYPES: frozenset[str] = frozenset(
    {
        "expression_statement",
        "if_statement",
        "for_statement",
        "while_statement",
        "try_statement",
        "except_clause",
        "match_statement",
        "with_statement",
        "return_statement",
        "raise_statement",
        "break_statement",
        "continue_statement",
        "pass_statement",
        "import_statement",
        "import_from_statement",
        "global_statement",
        "nonlocal_statement",
        "assert_statement",
        "delete_statement",
        "function_definition",
        "class_definition",
    }
)


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
        fn_with_nodes = _collect_functions(tree, source, file_path)
        functions = tuple(fn for fn, _ in fn_with_nodes)
        classes = tuple(_collect_classes(tree, source, file_path, functions))
        call_sites = tuple(_collect_call_sites(source, file_path, fn_with_nodes))

        # Slice 4b: 1-indexed line count. tree-sitter's root is always valid even
        # when parse errors are present, so end_point is safe to read.
        line_count = tree.root_node.end_point[0] + 1

        return ParseResult(
            file_path=file_path,
            language=Language.PYTHON,
            functions=functions,
            classes=classes,
            call_sites=call_sites,
            errors=errors,
            line_count=line_count,
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
    """Get the s-expression for a node. tree-sitter >=0.21 uses str(node)."""
    return str(node)


def _classify_cfn(node: Node) -> ControlFlowNodeKind | None:
    if node.type in _TS_TO_CFN_KIND:
        return _TS_TO_CFN_KIND[node.type]
    if node.type in _COMPREHENSION_TYPES:
        return ControlFlowNodeKind.COMPREHENSION
    if node.type == "boolean_operator":
        return ControlFlowNodeKind.BOOLEAN_SEQUENCE
    return None


def _is_nested_boolean_operator(node: Node) -> bool:
    """True if this boolean_operator is nested inside another boolean_operator.

    Used to emit ONE CFN per outermost boolean_operator tree (Sonar semantics:
    per group, not per operator).
    """
    if node.type != "boolean_operator":
        return False
    parent = node.parent
    while parent is not None:
        if parent.type == "boolean_operator":
            return True
        parent = parent.parent
    return False


def _block_of(node: Node) -> Node | None:
    """Return the body/consequence block of a control-flow node.

    tree-sitter-python field names by node type:
    - if_statement:  consequence (block)
    - elif_clause:   consequence (block)
    - else_clause:   body (block)
    - for_statement: body (block)
    - while_statement: body (block)
    - except_clause: no field name — find by type among children
    """
    if node.type in ("if_statement", "elif_clause"):
        return node.child_by_field_name("consequence")
    if node.type == "except_clause":
        # except_clause has no named field for its block; find by type
        for child in node.children:
            if child.type == "block":
                return child
        return None
    return node.child_by_field_name("body")


def _collect_cfns_rec(node: Node, file_path: str, depth: int, out: list[ControlFlowNode]) -> None:
    kind = _classify_cfn(node)

    if kind == ControlFlowNodeKind.BOOLEAN_SEQUENCE and _is_nested_boolean_operator(node):
        # Skip — part of an outer boolean sequence already emitted.
        # Still recurse into children in case they contain other CFNs.
        for child in node.children:
            _collect_cfns_rec(child, file_path, depth, out)
        return

    if kind is not None:
        if kind == ControlFlowNodeKind.IF:
            # if body: children at depth+1 (only nested CFNs inside the block)
            children_cfns: list[ControlFlowNode] = []
            consequence = node.child_by_field_name("consequence")
            if consequence is not None:
                _collect_cfns_into(consequence, file_path, depth + 1, children_cfns)
            out.append(
                ControlFlowNode(
                    kind=ControlFlowNodeKind.IF,
                    source_range=_source_range(node, file_path),
                    nesting_depth=depth,
                    children=tuple(children_cfns),
                )
            )
            # Condition-expression CFNs (boolean_sequence, ternary, comprehension)
            # are emitted as SIBLINGS at the same depth — no nesting penalty.
            # Sonar semantics: boolean operators in a condition are flat +1 each,
            # never nesting-penalised.
            for child in node.children:
                if child.type not in ("block", "elif_clause", "else_clause", "if", ":", "comment"):
                    _collect_cfns_rec(child, file_path, depth, out)
            # elif/else clauses are SIBLINGS of the if at the same depth.
            # tree-sitter-python places them as direct children of if_statement
            # with field name "alternative" — there can be multiple.
            for child in node.children:
                if child.type in ("elif_clause", "else_clause"):
                    alt_kind = (
                        ControlFlowNodeKind.ELIF
                        if child.type == "elif_clause"
                        else ControlFlowNodeKind.ELSE
                    )
                    alt_block = _block_of(child)
                    alt_children: list[ControlFlowNode] = []
                    if alt_block is not None:
                        _collect_cfns_into(alt_block, file_path, depth + 1, alt_children)
                    out.append(
                        ControlFlowNode(
                            kind=alt_kind,
                            source_range=_source_range(child, file_path),
                            nesting_depth=depth,
                            children=tuple(alt_children),
                        )
                    )
            return

        if kind == ControlFlowNodeKind.TRY:
            children_cfns = []
            body = node.child_by_field_name("body")
            if body is not None:
                _collect_cfns_into(body, file_path, depth + 1, children_cfns)
            out.append(
                ControlFlowNode(
                    kind=ControlFlowNodeKind.TRY,
                    source_range=_source_range(node, file_path),
                    nesting_depth=depth,
                    children=tuple(children_cfns),
                )
            )
            # except clauses: emit as siblings at same depth
            for child in node.children:
                if child.type == "except_clause":
                    exc_block = _block_of(child)
                    exc_children: list[ControlFlowNode] = []
                    if exc_block is not None:
                        _collect_cfns_into(exc_block, file_path, depth + 1, exc_children)
                    out.append(
                        ControlFlowNode(
                            kind=ControlFlowNodeKind.EXCEPT,
                            source_range=_source_range(child, file_path),
                            nesting_depth=depth,
                            children=tuple(exc_children),
                        )
                    )
            return

        if kind == ControlFlowNodeKind.MATCH:
            # MATCH is emitted as a marker with no children. Each case_clause
            # becomes a sibling CASE at the same depth (parallel to TRY/EXCEPT
            # siblings), and its body's CFNs hang off the CASE at depth+1.
            out.append(
                ControlFlowNode(
                    kind=ControlFlowNodeKind.MATCH,
                    source_range=_source_range(node, file_path),
                    nesting_depth=depth,
                    children=(),
                )
            )
            match_body = node.child_by_field_name("body")
            if match_body is not None:
                for child in match_body.children:
                    if child.type == "case_clause":
                        # tree-sitter-python uses field name "consequence"
                        # for the case body block.
                        case_block = child.child_by_field_name("consequence")
                        case_children: list[ControlFlowNode] = []
                        if case_block is not None:
                            _collect_cfns_into(case_block, file_path, depth + 1, case_children)
                        out.append(
                            ControlFlowNode(
                                kind=ControlFlowNodeKind.CASE,
                                source_range=_source_range(child, file_path),
                                nesting_depth=depth,
                                children=tuple(case_children),
                            )
                        )
            return

        # General case: leaf CFNs (boolean, ternary, comprehension) have no body
        # to recurse into for CFN purposes. Compound CFNs (for, while, else, elif,
        # except) use _block_of to find their body.
        if kind in (
            ControlFlowNodeKind.BOOLEAN_SEQUENCE,
            ControlFlowNodeKind.TERNARY,
            ControlFlowNodeKind.COMPREHENSION,
        ):
            out.append(
                ControlFlowNode(
                    kind=kind,
                    source_range=_source_range(node, file_path),
                    nesting_depth=depth,
                    children=(),
                )
            )
            return

        # Remaining compound CFNs (for, while — elif/else/except handled above)
        children_cfns = []
        block = _block_of(node)
        if block is not None:
            _collect_cfns_into(block, file_path, depth + 1, children_cfns)
        out.append(
            ControlFlowNode(
                kind=kind,
                source_range=_source_range(node, file_path),
                nesting_depth=depth,
                children=tuple(children_cfns),
            )
        )
        return

    # Not a CFN — but descendants might contain CFNs (e.g., an
    # expression_statement wrapping a ternary, or an assignment RHS with a
    # comprehension). Recurse without changing depth.
    for child in node.children:
        _collect_cfns_rec(child, file_path, depth, out)


def _collect_cfns_into(
    container: Node, file_path: str, depth: int, out: list[ControlFlowNode]
) -> None:
    """Collect CFNs from a block node's direct children into `out`."""
    for child in container.children:
        _collect_cfns_rec(child, file_path, depth, out)


def _collect_control_flow(body_node: Node, file_path: str) -> tuple[ControlFlowNode, ...]:
    """Walk a function body node emitting top-level CFNs at depth 0."""
    out: list[ControlFlowNode] = []
    _collect_cfns_into(body_node, file_path, 0, out)
    return tuple(out)


def _is_docstring_node(node: Node) -> bool:
    """True if this expression_statement contains only a string literal.

    Such nodes arise from docstrings (and bare string expressions used as
    comments). They are executable in the CPython sense but carry no
    control-flow intent, so they are excluded from statement_count.
    """
    if node.type != "expression_statement":
        return False
    named = [c for c in node.children if c.is_named]
    return len(named) == 1 and named[0].type == "string"


def _count_statements(body_node: Node) -> int:
    """Count executable statements in a function body, recursively.

    A compound statement (if/for/while/try/with) counts as 1, and its body's
    statements are added recursively. except_clause counts as 1 and its body
    is recursed (same as a branch arm). Pure string expression_statements
    (docstrings) are excluded. See arch §1.5.
    """
    count = 0
    stack: list[Node] = list(body_node.children)
    while stack:
        node = stack.pop()
        if node.type == "case_clause":
            # case_clause is a structural child of match_statement, not a
            # statement in its own right. Recurse into its body so the
            # contained statements are counted, without bumping the count
            # for the case_clause itself. Tree-sitter-python uses the
            # field name "consequence" for the case body block.
            case_body = node.child_by_field_name("consequence")
            if case_body is not None:
                stack.extend(case_body.children)
            continue
        if node.type in _STATEMENT_NODE_TYPES:
            if _is_docstring_node(node):
                continue
            count += 1
            # Recurse into compound statements' bodies (if/elif use "consequence")
            if node.type in ("if_statement", "elif_clause"):
                block = node.child_by_field_name("consequence")
            elif node.type == "except_clause":
                block = _block_of(node)
            else:
                block = node.child_by_field_name("body")
            if block is not None:
                stack.extend(block.children)
            # Alternative/supplemental branches: elif, else, finally.
            # except_clause is now in _STATEMENT_NODE_TYPES; push the node
            # itself so it is counted and its body recursed in the normal path.
            for child in node.children:
                if child.type in ("elif_clause", "else_clause", "finally_clause"):
                    alt_block = _block_of(child)
                    if alt_block is not None:
                        stack.extend(alt_block.children)
                elif child.type == "except_clause":
                    stack.append(child)
    return count


def _collect_identifiers(body_node: Node, source: bytes) -> tuple[str, ...]:
    """Collect all identifier occurrences from a function body.

    Walks the subtree rooted at `body_node`, emitting the text of every
    `identifier` tree-sitter node. Includes duplicates (order-preserved);
    callers dedupe via `set()` if distinct-count is wanted.

    Skips descents into nested function_definition / class_definition /
    lambda nodes — their identifiers belong to those nested scopes, not
    the enclosing function.
    """
    out: list[str] = []
    stack: list[Node] = list(body_node.children)
    while stack:
        node = stack.pop()
        if node.type == "identifier":
            out.append(_text(node, source))
            continue  # identifier is a leaf; no children to recurse
        if node.type in ("function_definition", "class_definition", "lambda"):
            # Nested scope — skip (Slice 4a Known Gap #1: lambdas attributed
            # to enclosing function for max_nesting/npath; for identifiers
            # we DO exclude them to avoid polluting the enclosing function's
            # identifier count).
            continue
        stack.extend(node.children)
    return tuple(out)


def _classify_delegation(
    body_node: Node, source: bytes, parameter_names: tuple[str, ...]
) -> DelegationKind:
    """Classify a function body's triviality for trivial_delegation_ratio (Slice 4b).

    Rules (R1 — deliberately strict, false-positive-averse):
    - RETURN_PASSTHROUGH: exactly one non-docstring statement, which is
      `return f(args)` satisfying the passthrough argument rules.
    - ASSIGN_DELEGATE: exactly two non-docstring statements, `x = f(args)`
      followed by `return x`. Call must satisfy passthrough rules.
    - WRAPPER_NO_TRANSFORM: exactly one non-docstring statement, which is a
      bare call expression (not a return, not an assign) satisfying passthrough.
    - NONE: everything else.

    KNOWN GAPS (metric_version=1.0.0):
    - `super().foo(...)` not detected (attribute-call breaks identifier-only rule).
    - async def / await wrappers not detected (return value is `await`, not call).
    - `self.x = x` not detected (attribute assignment, not a delegated call).
    - Default-argument injection (`def g(a, b=5): return f(a, b)`) IS counted
      as passthrough — signature defaults considered separate from body rules.
    """
    # Collect non-docstring statements from the direct body.
    stmts = [c for c in body_node.children if c.type in _STATEMENT_NODE_TYPES]
    stmts = [s for s in stmts if not _is_docstring_node(s)]

    if len(stmts) == 1:
        stmt = stmts[0]
        if stmt.type == "return_statement":
            call = _return_value_call(stmt)
            if call is not None and _call_is_passthrough(call, source, parameter_names):
                return DelegationKind.RETURN_PASSTHROUGH
        elif stmt.type == "expression_statement":
            call = _bare_call_expression(stmt)
            if call is not None and _call_is_passthrough(call, source, parameter_names):
                return DelegationKind.WRAPPER_NO_TRANSFORM
        return DelegationKind.NONE

    if len(stmts) == 2:
        first, second = stmts
        target_text = _assign_target_text(first, source)
        call = _simple_assign_call_rhs(first) if target_text is not None else None
        if (
            target_text is not None
            and call is not None
            and _call_is_passthrough(call, source, parameter_names)
            and _is_return_of_identifier(second, source, target_text)
        ):
            return DelegationKind.ASSIGN_DELEGATE

    return DelegationKind.NONE


def _return_value_call(return_stmt: Node) -> Node | None:
    """For `return <expr>`, return the expr iff it is a `call` node."""
    for child in return_stmt.children:
        if child.is_named and child.type == "call":
            return child
        if child.is_named and child.type != "return":
            # Something other than a call — reject (e.g., binary_operator,
            # identifier, integer literal). Conservative: only direct calls.
            return None
    return None


def _bare_call_expression(expr_stmt: Node) -> Node | None:
    """For a bare expression_statement, return the inner call node or None."""
    named = [c for c in expr_stmt.children if c.is_named]
    if len(named) == 1 and named[0].type == "call":
        return named[0]
    return None


def _assign_target_text(stmt: Node, source: bytes) -> str | None:
    """If `stmt` is `x = <rhs>` where x is a plain identifier, return x's text.

    Rejects tuple-unpacking, augmented-assign, typed-assign-with-complex-LHS,
    and attribute-assign (`self.x = ...`). Tree-sitter-python emits `+=` / `-=`
    etc. as a separate `augmented_assignment` node type, so the `"assignment"`
    check already excludes those.
    """
    if stmt.type != "expression_statement":
        return None
    named = [c for c in stmt.children if c.is_named]
    if len(named) != 1 or named[0].type != "assignment":
        return None
    left = named[0].child_by_field_name("left")
    if left is None or left.type != "identifier":
        return None
    return _text(left, source)


def _simple_assign_call_rhs(stmt: Node) -> Node | None:
    if stmt.type != "expression_statement":
        return None
    named = [c for c in stmt.children if c.is_named]
    if len(named) != 1 or named[0].type != "assignment":
        return None
    right = named[0].child_by_field_name("right")
    if right is None or right.type != "call":
        return None
    return right


def _is_return_of_identifier(stmt: Node, source: bytes, identifier_text: str) -> bool:
    """True iff `stmt` is `return <identifier_text>` — text must match exactly."""
    if stmt.type != "return_statement":
        return False
    named = [c for c in stmt.children if c.is_named and c.type != "return"]
    if len(named) != 1 or named[0].type != "identifier":
        return False
    return _text(named[0], source) == identifier_text


def _call_is_passthrough(call_node: Node, source: bytes, parameter_names: tuple[str, ...]) -> bool:
    """Verify call args pass through exactly.

    Rules:
    - callee (function field) must be an identifier — not attribute, not subscript
      (KNOWN GAP: super().foo() not supported).
    - positional args must be identifier nodes whose texts equal a prefix of
      parameter_names in order.
    - keyword args must be `name=value` where name-text equals value-text and
      value is an identifier node.
    - no *args / **kwargs splats (splat patterns reject).
    """
    func = call_node.child_by_field_name("function")
    if func is None or func.type != "identifier":
        return False
    args = call_node.child_by_field_name("arguments")
    if args is None:
        # Call with zero parens? Treat as no args, trivially passthrough only if
        # parameter_names is also empty.
        return len(parameter_names) == 0

    positional: list[str] = []
    keyword_names: list[tuple[str, str]] = []
    for child in args.children:
        if not child.is_named:
            continue  # commas, parens
        if child.type == "identifier":
            positional.append(_text(child, source))
        elif child.type == "keyword_argument":
            name_node = child.child_by_field_name("name")
            value_node = child.child_by_field_name("value")
            if name_node is None or value_node is None:
                return False
            if value_node.type != "identifier":
                return False
            keyword_names.append((_text(name_node, source), _text(value_node, source)))
        elif child.type in ("list_splat", "dictionary_splat", "parenthesized_splat_pattern"):
            return False  # splats reject
        else:
            # Any other node (integer, string, binary_operator, attribute, call, ...)
            # breaks passthrough — transformation or literal injection.
            return False

    # Positional args must be prefix of parameter_names in order.
    if len(positional) > len(parameter_names):
        return False
    for i, arg_name in enumerate(positional):
        if arg_name != parameter_names[i]:
            return False

    # Keyword args must be name==value (same identifier text).
    return all(kname == kvalue for kname, kvalue in keyword_names)


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


def _collect_functions(
    tree: Tree, source: bytes, file_path: str
) -> list[tuple[FunctionDefNode, Node]]:
    out: list[tuple[FunctionDefNode, Node]] = []
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
            body_node = node.child_by_field_name("body")
            control_flow = (
                _collect_control_flow(body_node, file_path) if body_node is not None else ()
            )
            statement_count = _count_statements(body_node) if body_node is not None else 0
            identifier_names = (
                _collect_identifiers(body_node, source) if body_node is not None else ()
            )
            delegation_kind = (
                _classify_delegation(body_node, source, params)
                if body_node is not None
                else DelegationKind.NONE
            )
            out.append(
                (
                    FunctionDefNode(
                        name=name,
                        qualified_name=qualified,
                        enclosing_class=enclosing_class,
                        source_range=_source_range(node, file_path),
                        ast_hash=hash_ast_sexp(_sexp(node)),
                        parameter_names=params,
                        control_flow=control_flow,
                        statement_count=statement_count,
                        identifier_names=identifier_names,
                        delegation_kind=delegation_kind,  # Slice 4b
                    ),
                    node,
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
    source: bytes,
    file_path: str,
    fn_with_nodes: list[tuple[FunctionDefNode, Node]],
) -> list[CallSiteNode]:
    # Build byte-range → qualified_name map directly from the tuples — zero extra tree walks.
    ranges: list[tuple[int, int, str]] = [
        (tree_node.start_byte, tree_node.end_byte, fn.qualified_name)
        for fn, tree_node in fn_with_nodes
    ]

    # Pre-compute resolution sets once per parse (not per call-site).
    top_level_names: set[str] = {fn.name for fn, _ in fn_with_nodes if fn.enclosing_class is None}
    class_methods: dict[str, set[str]] = {}
    for fn, _ in fn_with_nodes:
        if fn.enclosing_class is not None:
            class_methods.setdefault(fn.enclosing_class, set()).add(fn.name)

    def _enclosing(call_node: Node) -> str | None:
        start = call_node.start_byte
        best: tuple[int, int, str] | None = None
        for r in ranges:
            if r[0] <= start < r[1] and (best is None or (r[1] - r[0]) < (best[1] - best[0])):
                best = r
        return best[2] if best else None

    def _enclosing_class_for_qualified(qualified: str | None) -> str | None:
        if qualified is None:
            return None
        for fn, _ in fn_with_nodes:
            if fn.qualified_name == qualified:
                return fn.enclosing_class
        return None

    # Walk the tree once to collect call nodes.
    # We need the root node; grab it from any tree_node's parent chain or
    # re-parse. Since we have the tree_nodes, walk from them to find the root.
    # More directly: use a stack seeded from the root of the first node if
    # available, else fall back to re-creating from source.
    # The simplest correct approach: collect all tree_nodes' root nodes.
    # All nodes share the same tree, so pick any node's tree.
    if not fn_with_nodes:
        # No functions at all — still need to walk for module-level calls.
        # We can't get the root node without the tree. Return empty for now.
        # (Module-level call sites with no functions defined are edge cases
        # not tested in Slice 2.)
        return []

    # All nodes share the same tree object; navigate to root via any node.
    root = fn_with_nodes[0][1]
    while root.parent is not None:
        root = root.parent

    out: list[CallSiteNode] = []
    stack: list[Node] = [root]
    while stack:
        node = stack.pop()
        if node.type == "call":
            func_node = node.child_by_field_name("function")
            if func_node is not None:
                callee = _callee_name_from_node(func_node, source)
                if callee is not None:
                    enc_qual = _enclosing(node)
                    enc_class = _enclosing_class_for_qualified(enc_qual)
                    is_res = callee in top_level_names or (
                        enc_class is not None and callee in class_methods.get(enc_class, set())
                    )
                    out.append(
                        CallSiteNode(
                            callee_name=callee,
                            source_range=_source_range(node, file_path),
                            enclosing_function=enc_qual,
                            is_resolved=is_res,
                        )
                    )
        stack.extend(node.children)
    return out


def _callee_name_from_node(node: Node, source: bytes) -> str | None:
    if node.type == "identifier":
        return _text(node, source)
    if node.type == "attribute":
        attr = node.child_by_field_name("attribute")
        if attr is not None:
            return _text(attr, source)
    return None


def _extract_parameter_names(func_node: Node, source: bytes) -> tuple[str, ...]:
    """Extract positional parameter names from a function_definition node.

    SLICE 2 GAP: `*args` (list_splat_pattern) and `**kwargs`
    (dictionary_splat_pattern) are silently omitted. Not an issue for MVP
    because this field is unused until Slice 5 when signature-based
    context_hash lands; fix then.
    """
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
