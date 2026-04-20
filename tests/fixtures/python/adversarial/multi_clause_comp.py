"""Adversarial fixture: comprehensions with multiple for/if clauses.

`pairs` has 2× `for` + 2× `if`; `nested_dict` has a nested comprehension
inside a dict comprehension. These stress how many CFNs the parser emits
per comprehension (one-per-outermost vs one-per-clause).

Expected:
  functions: 2 (pairs, nested_dict)
  all delegation_kind: NONE
"""
from __future__ import annotations


def pairs(xs, ys):
    return [(x, y) for x in xs for y in ys if x != y if x + y > 0]


def nested_dict(rows):
    return {k: [v for v in row if v > 0] for row in rows for k in row.keys() if row}
