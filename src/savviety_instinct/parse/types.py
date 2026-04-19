"""Normalized AST node types — language-agnostic view of parsed code.

Each `LanguageAdapter` (arch §5.5) maps its language-specific tree-sitter nodes
into these domain-neutral dataclasses. Metrics and graph builders consume these,
not raw tree-sitter nodes, so adding a new language is an adapter-only change.

Slice 2 populates `FunctionDefNode`, `ClassDefNode`, and `CallSiteNode`.
`ControlFlowNode` etc. arrive with the complexity metrics in Slice 3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from savviety_instinct.core.types import Language, SourceRange


class ParseErrorKind(StrEnum):
    SYNTAX = "syntax"
    UNSUPPORTED_CONSTRUCT = "unsupported_construct"
    IO = "io"


@dataclass(frozen=True, slots=True)
class ParseError:
    kind: ParseErrorKind
    message: str
    source_range: SourceRange | None  # None for IO errors where we never parsed a range


@dataclass(frozen=True, slots=True)
class FunctionDefNode:
    """A callable definition: free function, lambda, or method."""

    name: str  # the symbol under which callers find it
    qualified_name: str  # e.g., "MyClass.method" for methods, plain name for free fns
    enclosing_class: str | None  # for methods; None for free functions
    source_range: SourceRange
    ast_hash: str  # computed per arch §4.2
    parameter_names: tuple[str, ...]  # for future signature hashing; not used in Slice 2

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
    method_qualified_names: tuple[str, ...]  # forward index into FunctionDefNode.qualified_name


@dataclass(frozen=True, slots=True)
class CallSiteNode:
    """A single invocation. Intra-file resolution only in Slice 2."""

    callee_name: str  # the textual name at the call site
    source_range: SourceRange
    enclosing_function: str | None  # qualified name of the function containing this call,
    # or None if the call is at module level
    is_resolved: bool  # True if a local FunctionDefNode matched callee_name


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
