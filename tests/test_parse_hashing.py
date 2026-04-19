"""Tests for parse.hashing — ast_hash determinism and shape-normalization."""

from __future__ import annotations

from savviety_instinct.parse import hashing


def test_hash_algorithm_is_known() -> None:
    """HASH_ALGORITHM must be one of the two supported backends."""
    assert hashing.HASH_ALGORITHM in {"blake3", "xxhash"}


def test_hash_is_hex_string() -> None:
    digest = hashing.hash_ast_sexp("(function_definition name: (identifier))")
    assert isinstance(digest, str)
    assert all(c in "0123456789abcdef" for c in digest)
    assert len(digest) >= 16  # blake3 32-byte hex = 64 chars; xxhash64 hex = 16


def test_hash_is_deterministic() -> None:
    sexp = "(function_definition name: (identifier))"
    assert hashing.hash_ast_sexp(sexp) == hashing.hash_ast_sexp(sexp)


def test_hash_differs_for_different_shapes() -> None:
    a = hashing.hash_ast_sexp("(function_definition name: (identifier))")
    b = hashing.hash_ast_sexp("(class_definition name: (identifier))")
    assert a != b


def test_normalize_strips_whitespace() -> None:
    a = hashing.normalize_sexp("  (function_definition   name: (identifier))  ")
    b = hashing.normalize_sexp("(function_definition name: (identifier))")
    assert a == b


def test_normalize_preserves_node_type_names() -> None:
    raw = "(function_definition body: (block))"
    normalized = hashing.normalize_sexp(raw)
    # node type names like 'function_definition' are structural; must survive
    assert "(function_definition" in normalized
    assert "(block)" in normalized
