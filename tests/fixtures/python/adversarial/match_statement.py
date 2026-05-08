"""Adversarial fixture: PEP 634 match/case patterns.

Two functions using `match` with literal patterns, OR-patterns, sequence
patterns, capture variables, and a guard. Tree-sitter-python parses these
cleanly, but savviety_instinct.parse.python has no mapping for
`match_statement` in `_STATEMENT_NODE_TYPES` or `_TS_TO_CFN_KIND`.

Bug B1 (fixed in parse-bugs branch):
  Originally `match_statement` and `case_clause` were missing from
  `_STATEMENT_NODE_TYPES` and `_TS_TO_CFN_KIND`, so match-only bodies
  scored statement_count=0 and cyclomatic=1. The fix added MATCH and
  CASE ControlFlowNodeKinds and recursive case-body statement counting.

Expected (post-fix):
  functions: 2 (classify_shape, unpack_point)
  all delegation_kind: NONE
  classify_shape: statement_count=4 (1 match + 3 case returns),
                  cyclomatic=4, cognitive=3
  unpack_point:   statement_count=4, cyclomatic=4, cognitive=3
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
