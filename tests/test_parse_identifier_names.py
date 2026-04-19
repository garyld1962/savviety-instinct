"""Tests for FunctionDefNode.identifier_names extraction."""

from __future__ import annotations

from pathlib import Path

from savviety_instinct.parse.python import PYTHON_ADAPTER

FIXTURES = Path(__file__).parent / "fixtures" / "python"


def _fn(qualified_name: str):
    result = PYTHON_ADAPTER.parse_path(FIXTURES / "metric_fixtures.py")
    return next(fn for fn in result.functions if fn.qualified_name == qualified_name)


def test_empty_function_has_no_body_identifiers() -> None:
    fn = _fn("empty")
    assert fn.identifier_names == ()


def test_two_statements_collects_body_identifiers() -> None:
    fn = _fn("two_statements")
    names = set(fn.identifier_names)
    assert "x" in names
    assert "y" in names


def test_identifier_names_excludes_function_name() -> None:
    """The function's own name is on FunctionDefNode.name, not in identifier_names."""
    fn = _fn("two_statements")
    assert "two_statements" not in fn.identifier_names


def test_parameter_used_in_body_appears_in_identifier_names() -> None:
    """Parameters referenced in the body ARE body usages; they appear here."""
    fn = _fn("two_statements")
    assert "x" in fn.identifier_names


def test_for_loop_collects_loop_and_iter_variables() -> None:
    fn = _fn("for_loop_only")
    names = set(fn.identifier_names)
    assert "total" in names
    assert "item" in names
    assert "items" in names


def test_comprehension_collects_iterator_variable() -> None:
    fn = _fn("comprehension")
    names = set(fn.identifier_names)
    assert "items" in names
    assert "i" in names


def test_try_except_collects_exception_type() -> None:
    """Exception class names are identifiers worth tracking for quality."""
    fn = _fn("try_except")
    names = set(fn.identifier_names)
    assert "ZeroDivisionError" in names


def test_identifier_names_is_tuple() -> None:
    fn = _fn("two_statements")
    assert isinstance(fn.identifier_names, tuple)
