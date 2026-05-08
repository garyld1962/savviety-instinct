"""Adversarial fixture: PEP 654 exception groups (try / except*).

Two `except*` clauses — one for a single type, one for a tuple. Exception
groups are a Python 3.11+ construct; tree-sitter-python parses them as
`except_group_clause` (distinct from `except_clause`).

Bug B3 (fixed in parse-bugs branch):
  Originally `except_group_clause` was missing from `_TS_TO_CFN_KIND`
  and `_STATEMENT_NODE_TYPES`, so `except*` arms were not counted as
  decisions. The fix maps `except_group_clause → EXCEPT` (treated
  identically to `except_clause`) and adds it to the statement-node set.

Expected (post-fix):
  functions: 2 (handle_many, run_all)
  all delegation_kind: NONE
  handle_many: cyclomatic=3 (1 base + 2 except* arms), cognitive=2
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
