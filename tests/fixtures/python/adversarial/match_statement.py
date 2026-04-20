"""Adversarial fixture: PEP 634 match/case patterns.

Two functions using `match` with literal patterns, OR-patterns, sequence
patterns, capture variables, and a guard. Tree-sitter-python parses these
cleanly, but savviety_instinct.parse.python has no mapping for
`match_statement` in `_STATEMENT_NODE_TYPES` or `_TS_TO_CFN_KIND`.

KNOWN BUG (discovered 2026-04-20 via this fixture):
  match-only function bodies yield statement_count=0. This breaks
  median_function_length, function_length_bimodality, and
  trivial_delegation_ratio for any Python 3.10+ module using match.
  Follow-up: add `match_statement` and `case_clause` to the
  statement-node set and the CFN-kind map. See test for xfail marker.

Expected (correct behavior, xfail until fixed):
  functions: 2 (classify_shape, unpack_point)
  all delegation_kind: NONE
  classify_shape.statement_count: ≥ 1 (currently 0)
  unpack_point.statement_count: ≥ 1 (currently 0)
"""
from __future__ import annotations


def classify_shape(shape):
    match shape:
        case "circle":
            return "round"
        case "square" | "rectangle":
            return "rectangular"
        case _:
            return "unknown"


def unpack_point(point):
    match point:
        case (0, 0):
            return "origin"
        case (x, y) if x == y:
            return "diagonal"
        case (_, _):
            return "other"
