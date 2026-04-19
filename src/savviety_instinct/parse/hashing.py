"""Deterministic AST hashing for artifact identity (arch §4.2, D6).

Produces the `ast_hash` used as the dedup key on `observation_artifacts`. The
hash is computed over a whitespace-normalized s-expression of a tree-sitter
node. Tree-sitter's str(node) output already omits identifier text AND literal
values — emitting only node-type names and field labels — so the AST-shape
identity that D6 requires is delivered by tree-sitter itself. Normalization
here is a belt-and-suspenders whitespace collapse in case sexp formatting ever
varies across grammar versions.

Hasher selection (arch §16.2): `blake3` if importable, else `xxhash`. The
choice is captured at import time in `HASH_ALGORITHM` so `tool_version` /
provenance can record which backend produced a given digest (a future
grammar/hasher bump is a deliberate `metric_version` event).
"""

from __future__ import annotations

import re

try:
    import blake3 as _blake3

    _HASHER = "blake3"
except ImportError:  # pragma: no cover - fallback path
    import xxhash as _xxhash

    _HASHER = "xxhash"

HASH_ALGORITHM: str = _HASHER

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_sexp(sexp: str) -> str:
    """Collapse whitespace variance in a tree-sitter s-expression.

    Tree-sitter's str(node) output emits only node-type names and field labels
    — no identifier text, no literal values — so whitespace collapse is the
    only normalization needed.
    """
    return _WHITESPACE_RE.sub(" ", sexp).strip()


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
