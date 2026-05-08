"""Adversarial fixture: PEP 654 exception groups (try / except*).

Two `except*` clauses — one for a single type, one for a tuple. Exception
groups are a Python 3.11+ construct; tree-sitter-python parses them as
`except_group` (distinct from `except_clause`). The parser's CFN map may
not include `except_group`.

Expected:
  functions: 2 (handle_many, run_all)
  all delegation_kind: NONE
"""
from __future__ import annotations


def handle_many(tasks):
    try:
        run_all(tasks)
    except* ValueError as eg:
        return str(eg)
    except* (TypeError, KeyError) as eg:
        return repr(eg)
    return None


def run_all(tasks):
    raise ExceptionGroup("errors", [ValueError("v"), TypeError("t")])
