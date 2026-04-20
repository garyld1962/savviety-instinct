"""Adversarial fixture: PEP 572 walrus operator in expressions.

Walrus in if-condition, in list-comprehension guard. Tests whether the
parser handles `named_expression` nodes in both statement and comprehension
contexts without crashing on identifier extraction.

Expected:
  functions: 2 (count_trim, find_matching)
  all delegation_kind: NONE
"""
from __future__ import annotations


def count_trim(data):
    if (n := len(data)) > 10:
        return n
    return 0


def find_matching(items, predicate):
    return [y for x in items if (y := predicate(x)) is not None]
