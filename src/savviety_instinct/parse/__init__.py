"""Public API for the parse layer.

Arch §5.5. Wrap tree-sitter; expose normalized nodes and per-language adapters.
"""

from __future__ import annotations

from savviety_instinct.parse.adapter import LanguageAdapter, get_adapter
from savviety_instinct.parse.hashing import HASH_ALGORITHM, hash_ast_sexp
from savviety_instinct.parse.python import PYTHON_ADAPTER
from savviety_instinct.parse.types import (
    CallSiteNode,
    ClassDefNode,
    FunctionDefNode,
    ParseError,
    ParseErrorKind,
    ParseResult,
)

__all__ = [
    "HASH_ALGORITHM",
    "PYTHON_ADAPTER",
    "CallSiteNode",
    "ClassDefNode",
    "FunctionDefNode",
    "LanguageAdapter",
    "ParseError",
    "ParseErrorKind",
    "ParseResult",
    "get_adapter",
    "hash_ast_sexp",
]
