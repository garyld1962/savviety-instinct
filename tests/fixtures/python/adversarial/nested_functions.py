"""Adversarial fixture: nested functions, closures, class-in-function.

Per Slice 2 design decision, `_collect_functions` does NOT recurse into
nested `function_definition` or `class_definition` nodes. Nested functions
(`increment`) and class-in-function methods (`Inner.method`) therefore do
not appear in `ParseResult.functions`. Ref: Slice 4a plan Known Gap #3.

This fixture pins that design: 2 outer functions enumerated, nested
increment() and Inner.method() deliberately absent. Their statement
bodies DO contribute to the outer function's statement_count (because
`function_definition` / `class_definition` are themselves statement nodes).

Expected:
  functions: 2 (make_counter, make_types) — nested NOT enumerated
  classes: 1 (Inner) — class IS enumerated even though nested in a function
"""
from __future__ import annotations


def make_counter():
    count = 0

    def increment():
        nonlocal count
        count += 1
        return count

    return increment


def make_types():
    class Inner:
        def method(self):
            return "inner"

    return Inner
