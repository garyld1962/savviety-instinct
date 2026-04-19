"""Deterministic AST hashing for artifact identity (arch §4.2, D6).

Produces the `ast_hash` used as the dedup key on `observation_artifacts`. The
hash is computed over a *normalized* s-expression of a tree-sitter node, where
normalization strips literal values so two functions with identical shape but
different constants collide on purpose. Identifier text is already excluded by
tree-sitter's `sexp()` output, so the normalizer only needs to handle literals
and whitespace.

Hasher selection (arch §16.2): `blake3` if importable, else `xxhash`. The
choice is captured at import time in `HASH_ALGORITHM` so `tool_version` /
provenance can record which backend produced a given digest (a future
grammar/hasher bump is a deliberate `metric_version` event).
"""

from __future__ import annotations

import re

try:
    import blake3 as _blake3  # type: ignore[import-untyped]

    _HASHER = "blake3"
except ImportError:  # pragma: no cover - fallback path
    import xxhash as _xxhash  # type: ignore[import-untyped]

    _HASHER = "xxhash"

HASH_ALGORITHM: str = _HASHER

_STRING_LITERAL_RE = re.compile(r'"(?:[^"\\]|\\.)*"')
_WHITESPACE_RE = re.compile(r"\s+")
# Match integer / float literal nodes produced by tree-sitter-python:
#   (integer 42)  (float 3.14)
# The number follows a space after the node type and is terminated by `)` or space.
_NUMERIC_LITERAL_RE = re.compile(r"(\((?:integer|float|number)\s+)[-+]?\d[\d_.eE+-]*(?=\s|\))")


def normalize_sexp(sexp: str) -> str:
    """Strip whitespace variance and literal values from a tree-sitter s-exp.

    Node type names (`function_definition`, `block`, `identifier`, etc.) survive
    because they define the shape. Literal values do not.
    """
    # Order matters: replace literals before collapsing whitespace to avoid
    # breaking the regex anchors.
    s = _STRING_LITERAL_RE.sub("_STR", sexp)
    s = _NUMERIC_LITERAL_RE.sub(r"\1_NUM", s)
    s = _WHITESPACE_RE.sub(" ", s).strip()
    return s


def hash_ast_sexp(sexp: str) -> str:
    """Hash a tree-sitter s-expression for use as `Artifact.ast_hash`.

    Returns a hex-encoded digest. Length depends on backend (blake3: 64 chars,
    xxhash64: 16 chars) but is stable for a given import session.
    """
    normalized = normalize_sexp(sexp)
    encoded = normalized.encode("utf-8")
    if _HASHER == "blake3":
        return _blake3.blake3(encoded).hexdigest()
    return _xxhash.xxh64(encoded).hexdigest()
