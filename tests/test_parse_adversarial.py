"""Adversarial parser fixtures for modern Python constructs.

Each fixture under tests/fixtures/python/adversarial/ isolates one modern
Python construct (PEP 634 match, PEP 572 walrus, async generator,
decorator stacking, multi-clause comprehensions, nested functions,
PEP 695 generics, PEP 654 except groups). These tests assert:

1. Parse succeeds without errors (tree-sitter accepts the syntax).
2. Expected function count (pins current parser semantics).
3. Expected class count.
4. Specific structural details worth pinning (delegation_kind,
   statement_count, uniqueness).

Known bugs discovered via these fixtures are marked `xfail(strict=True)`
with fixture-file references. When the bug is fixed, the `xfail` flips
to `XPASS` and strict mode raises — forcing the fixer to remove the
marker and make the assertion real.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from savviety_instinct.parse.python import PYTHON_ADAPTER
from savviety_instinct.parse.types import DelegationKind

ADVERSARIAL = Path(__file__).parent / "fixtures" / "python" / "adversarial"


def _parse(fixture_name: str):
    return PYTHON_ADAPTER.parse_path(ADVERSARIAL / fixture_name)


# ---------- match_statement.py ----------


def test_match_statement_parses_cleanly() -> None:
    result = _parse("match_statement.py")
    assert result.ok
    assert result.errors == ()


def test_match_statement_function_count() -> None:
    result = _parse("match_statement.py")
    names = {f.name for f in result.functions}
    assert names == {"classify_shape", "unpack_point"}


def test_match_statement_delegation_kinds_all_none() -> None:
    result = _parse("match_statement.py")
    assert all(f.delegation_kind is DelegationKind.NONE for f in result.functions)


def test_match_statement_counts_are_positive() -> None:
    """Each match-only function has at least one statement.

    Bug B1 fix (parse-bugs branch): match_statement is now a recognised
    statement node, and case_clause bodies are recursed into for inner
    statements. classify_shape and unpack_point both report 4 statements
    (1 match + 3 case body returns).
    """
    result = _parse("match_statement.py")
    for f in result.functions:
        assert f.statement_count >= 1, f"{f.name}: statement_count={f.statement_count}"


# ---------- walrus.py ----------


def test_walrus_parses_cleanly() -> None:
    result = _parse("walrus.py")
    assert result.ok


def test_walrus_function_count_and_counts() -> None:
    result = _parse("walrus.py")
    assert {f.name for f in result.functions} == {"count_trim", "find_matching"}
    # count_trim: `if ... return ...; return` = 3 statements
    by_name = {f.name: f for f in result.functions}
    assert by_name["count_trim"].statement_count == 3
    # find_matching: single `return` statement with an embedded comprehension
    assert by_name["find_matching"].statement_count == 1


def test_walrus_delegation_kinds_all_none() -> None:
    result = _parse("walrus.py")
    assert all(f.delegation_kind is DelegationKind.NONE for f in result.functions)


# ---------- async_generator.py ----------


def test_async_generator_parses_cleanly() -> None:
    result = _parse("async_generator.py")
    assert result.ok


def test_async_generator_function_count() -> None:
    result = _parse("async_generator.py")
    assert {f.name for f in result.functions} == {"gen_chunks", "gather", "passthrough"}


def test_async_passthrough_is_not_classified_as_trivial() -> None:
    """Per R1 Known Gap, `async def f(src): return await src.read()` is NOT
    classified as passthrough. Pins that behavior."""
    result = _parse("async_generator.py")
    passthrough = next(f for f in result.functions if f.name == "passthrough")
    assert passthrough.delegation_kind is DelegationKind.NONE


# ---------- decorator_stack.py ----------


def test_decorator_stack_parses_cleanly() -> None:
    result = _parse("decorator_stack.py")
    assert result.ok


def test_decorator_stack_function_count() -> None:
    result = _parse("decorator_stack.py")
    # 4 functions: cached_helper + 3 methods (name-getter, name-setter, from_id)
    assert len(result.functions) == 4
    assert {f.name for f in result.functions} == {"cached_helper", "name", "from_id"}


def test_decorator_stack_class_detected() -> None:
    result = _parse("decorator_stack.py")
    assert {c.name for c in result.classes} == {"Thing"}


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Bug: qualified_name uniqueness violated — @property getter and "
        "@setter both produce 'Thing.name'. Downstream consumers keyed by "
        "qualified_name will collapse the two. See "
        "tests/fixtures/python/adversarial/decorator_stack.py docstring."
    ),
)
def test_decorator_stack_qualified_names_unique() -> None:
    result = _parse("decorator_stack.py")
    qnames = [f.qualified_name for f in result.functions]
    assert len(qnames) == len(set(qnames)), f"duplicates in {qnames}"


# ---------- multi_clause_comp.py ----------


def test_multi_clause_comp_parses_cleanly() -> None:
    result = _parse("multi_clause_comp.py")
    assert result.ok


def test_multi_clause_comp_function_count() -> None:
    result = _parse("multi_clause_comp.py")
    assert {f.name for f in result.functions} == {"pairs", "nested_dict"}


def test_multi_clause_comp_emits_cfn_for_comprehension() -> None:
    """Each function body is a single `return <comprehension>` — at least
    one COMPREHENSION CFN should surface (nested comprehensions in
    `nested_dict` may or may not produce multiple; we just pin ≥1)."""
    result = _parse("multi_clause_comp.py")
    for f in result.functions:
        assert len(f.control_flow) >= 1, f"{f.name}: no CFNs emitted"


# ---------- nested_functions.py ----------


def test_nested_functions_parses_cleanly() -> None:
    result = _parse("nested_functions.py")
    assert result.ok


def test_nested_functions_only_outer_enumerated() -> None:
    """Slice 2 design: `_collect_functions` does not recurse into nested
    function_definition / class_definition. The nested `increment` and
    `Inner.method` are intentionally absent. Pin this until (if) a later
    slice widens the contract."""
    result = _parse("nested_functions.py")
    assert {f.name for f in result.functions} == {"make_counter", "make_types"}


def test_nested_functions_inner_class_still_enumerated() -> None:
    """Classes nested inside a function body ARE enumerated (the class-collect
    pass is independent of function-recursion). Their methods are not."""
    result = _parse("nested_functions.py")
    assert {c.name for c in result.classes} == {"Inner"}


# ---------- generics_pep695.py ----------


def test_generics_pep695_parses_cleanly() -> None:
    result = _parse("generics_pep695.py")
    assert result.ok


def test_generics_pep695_function_count() -> None:
    result = _parse("generics_pep695.py")
    names = {f.name for f in result.functions}
    assert names == {"identity", "head", "__init__", "get"}


def test_generics_pep695_class_detected() -> None:
    result = _parse("generics_pep695.py")
    assert {c.name for c in result.classes} == {"Container"}


def test_generics_pep695_parameters_extracted_correctly() -> None:
    """Parameter extraction must ignore the PEP 695 type-parameter list
    (the `[T]` bracket) and return only runtime parameters."""
    result = _parse("generics_pep695.py")
    by_name = {f.name: f for f in result.functions}
    assert by_name["identity"].parameter_names == ("x",)
    assert by_name["head"].parameter_names == ("xs",)
    assert by_name["__init__"].parameter_names == ("self", "value")
    assert by_name["get"].parameter_names == ("self",)


# ---------- exception_groups.py ----------


def test_exception_groups_parses_cleanly() -> None:
    result = _parse("exception_groups.py")
    assert result.ok


def test_exception_groups_function_count() -> None:
    result = _parse("exception_groups.py")
    assert {f.name for f in result.functions} == {"handle_many", "run_all"}
