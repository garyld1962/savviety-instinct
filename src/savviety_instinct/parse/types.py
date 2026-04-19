"""Normalized AST node types — language-agnostic view of parsed code.

Each `LanguageAdapter` (arch §5.5) maps its language-specific tree-sitter nodes
into these domain-neutral dataclasses. Metrics and graph builders consume these,
not raw tree-sitter nodes, so adding a new language is an adapter-only change.

Slice 2 populated `FunctionDefNode`, `ClassDefNode`, and `CallSiteNode`.
Slice 3 adds `ControlFlowNode` + `FunctionDefNode.control_flow` for
cyclomatic / cognitive / statement_count metric computation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from savviety_instinct.core.types import Language, SourceRange


class ParseErrorKind(StrEnum):
    SYNTAX = "syntax"
    UNSUPPORTED_CONSTRUCT = "unsupported_construct"
    IO = "io"


class ControlFlowNodeKind(StrEnum):
    """Domain-neutral control-flow constructs.

    Per-language adapters map their native AST node types to these kinds.
    The set is intentionally small and stable — metrics reason about these
    kinds, not tree-sitter node types. New kinds require a coordinated
    metric_version bump.
    """

    IF = "if"
    ELIF = "elif"
    ELSE = "else"
    FOR = "for"
    WHILE = "while"
    TRY = "try"
    EXCEPT = "except"
    TERNARY = "ternary"
    BOOLEAN_SEQUENCE = "boolean_sequence"
    COMPREHENSION = "comprehension"


@dataclass(frozen=True, slots=True)
class ControlFlowNode:
    """A single control-flow point inside a function body.

    Children are nested CFNs (e.g., an `if` inside a `for`). The tree is rooted
    at the function's top-level CFNs (exposed on `FunctionDefNode.control_flow`).
    `nesting_depth` is cached from walk time; 0 means top-level within the
    function body, 1 means inside one control structure, etc. Metrics that need
    their own nesting semantics (cognitive_complexity) recompute via rules
    rather than relying on this cached value — it's informational.
    """

    kind: ControlFlowNodeKind
    source_range: SourceRange
    nesting_depth: int
    children: tuple[ControlFlowNode, ...] = ()


@dataclass(frozen=True, slots=True)
class ParseError:
    kind: ParseErrorKind
    message: str
    source_range: SourceRange | None


@dataclass(frozen=True, slots=True)
class FunctionDefNode:
    """A callable definition: free function, lambda, or method."""

    name: str
    qualified_name: str
    enclosing_class: str | None
    source_range: SourceRange
    ast_hash: str
    parameter_names: tuple[str, ...]
    # Slice 3: top-level control-flow points in this function's body.
    # Empty tuple for pure straight-line code.
    control_flow: tuple[ControlFlowNode, ...] = ()
    # Slice 3: count of executable statements in the function body.
    # Pre-computed during parse to avoid a second tree walk per metric.
    # Excludes pure declarations, blank lines, comments. See arch §1.5.
    statement_count: int = 0

    @property
    def is_method(self) -> bool:
        """Derived from `enclosing_class`; avoids the inconsistent-state risk of a
        separate boolean that could disagree with `enclosing_class`."""
        return self.enclosing_class is not None


@dataclass(frozen=True, slots=True)
class ClassDefNode:
    name: str
    source_range: SourceRange
    ast_hash: str
    method_qualified_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CallSiteNode:
    """A single invocation. Intra-file resolution only in Slice 2."""

    callee_name: str
    source_range: SourceRange
    enclosing_function: str | None
    is_resolved: bool


@dataclass(frozen=True, slots=True)
class ParseResult:
    file_path: str
    language: Language
    functions: tuple[FunctionDefNode, ...]
    classes: tuple[ClassDefNode, ...]
    call_sites: tuple[CallSiteNode, ...]
    errors: tuple[ParseError, ...] = field(default=())

    @property
    def ok(self) -> bool:
        """True iff no errors were encountered during parse.

        Note: a `False` result may still carry partial output in `functions`,
        `classes`, and `call_sites` — tree-sitter extracts what it can even
        when syntax errors are present. Callers that short-circuit on `not ok`
        will drop that partial data silently.
        """
        return not self.errors
