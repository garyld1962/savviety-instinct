"""Tests for PythonAdapter — tree-sitter-based parsing of Python sources."""

from __future__ import annotations

from pathlib import Path

from savviety_instinct.core.types import Language
from savviety_instinct.parse.python import PYTHON_ADAPTER
from savviety_instinct.parse.types import ParseErrorKind, ParseResult

FIXTURES = Path(__file__).parent / "fixtures" / "python"


def _parse(name: str) -> ParseResult:
    return PYTHON_ADAPTER.parse_path(FIXTURES / name)


def test_adapter_language_is_python() -> None:
    assert PYTHON_ADAPTER.language == Language.PYTHON


def test_simple_module_extracts_two_functions() -> None:
    result = _parse("simple_module.py")
    assert result.ok
    names = {fn.name for fn in result.functions}
    assert names == {"helper", "main"}


def test_simple_module_function_has_ast_hash() -> None:
    result = _parse("simple_module.py")
    helper = next(fn for fn in result.functions if fn.name == "helper")
    assert helper.ast_hash  # non-empty string
    assert helper.is_method is False
    assert helper.enclosing_class is None


def test_simple_module_captures_call_site() -> None:
    result = _parse("simple_module.py")
    # main() calls helper()
    call = next(
        c for c in result.call_sites if c.callee_name == "helper" and c.enclosing_function == "main"
    )
    assert call.is_resolved is True


def test_with_class_extracts_methods_as_functions() -> None:
    result = _parse("with_class.py")
    assert result.ok
    qualified = {fn.qualified_name for fn in result.functions}
    assert "module_level" in qualified
    assert "Worker.do_work" in qualified
    assert "Worker.other" in qualified


def test_with_class_method_is_method_flag_set() -> None:
    result = _parse("with_class.py")
    do_work = next(fn for fn in result.functions if fn.qualified_name == "Worker.do_work")
    assert do_work.is_method is True
    assert do_work.enclosing_class == "Worker"


def test_with_class_class_node_lists_methods() -> None:
    result = _parse("with_class.py")
    worker = next(c for c in result.classes if c.name == "Worker")
    assert set(worker.method_qualified_names) == {"Worker.do_work", "Worker.other"}


def test_syntax_error_reports_error_not_crash() -> None:
    result = _parse("syntax_error.py")
    assert not result.ok
    assert any(err.kind == ParseErrorKind.SYNTAX for err in result.errors)


def test_same_shape_functions_produce_same_ast_hash() -> None:
    """alpha and beta differ only in identifier names; their ast_hash must match.

    Confirms normalize_sexp + tree-sitter sexp() produce identifier-invariant
    hashes — tree-sitter's str(node) omits identifier text natively.
    """
    result = _parse("same_shape_different_names.py")
    alpha = next(fn for fn in result.functions if fn.name == "alpha")
    beta = next(fn for fn in result.functions if fn.name == "beta")
    assert alpha.ast_hash == beta.ast_hash


def test_parse_source_matches_parse_path() -> None:
    """The two entry points are equivalent for the same bytes."""
    source = (FIXTURES / "simple_module.py").read_bytes()
    by_path = PYTHON_ADAPTER.parse_path(FIXTURES / "simple_module.py")
    by_bytes = PYTHON_ADAPTER.parse_source(source, str(FIXTURES / "simple_module.py"))
    assert {fn.name for fn in by_path.functions} == {fn.name for fn in by_bytes.functions}


def test_parse_path_nonexistent_file_returns_io_error() -> None:
    """The IO error path returns a ParseResult with kind=IO — no exception."""
    result = PYTHON_ADAPTER.parse_path(Path("/nonexistent/path/to/nowhere.py"))
    assert not result.ok
    assert any(err.kind == ParseErrorKind.IO for err in result.errors)
    assert result.functions == ()


def test_nested_functions_are_not_collected() -> None:
    """Slice 2 scope: only top-level and method definitions are extracted.

    Functions nested inside other functions are intentionally skipped — the
    enclosing function is the unit of analysis for MVP metrics.
    """
    source = b"def outer():\n    def inner():\n        return 1\n    return inner()\n"
    result = PYTHON_ADAPTER.parse_source(source, "inline.py")
    names = {fn.name for fn in result.functions}
    assert names == {"outer"}


def test_cross_class_method_name_does_not_resolve() -> None:
    """Regression guard: two classes with same method short name must not
    be confused.

    Fix for critical bug where _node_byte_range_for_qualified matched on
    short name, collapsing both classes' methods to the same byte range.
    """
    result = PYTHON_ADAPTER.parse_path(FIXTURES / "two_classes_shared_method.py")
    assert result.ok
    # Both classes have a `run` method.
    qualified = {fn.qualified_name for fn in result.functions}
    assert "A.run" in qualified
    assert "B.run" in qualified
    # Each method's call sites must be attributed to the correct enclosing function.
    a_run_calls = [c for c in result.call_sites if c.enclosing_function == "A.run"]
    b_run_calls = [c for c in result.call_sites if c.enclosing_function == "B.run"]
    # A.run calls inner_a; B.run calls inner_b. Neither call site should be
    # attributed to the wrong class.
    a_callees = {c.callee_name for c in a_run_calls}
    b_callees = {c.callee_name for c in b_run_calls}
    assert "inner_a" in a_callees
    assert "inner_b" in b_callees
    assert "inner_a" not in b_callees
    assert "inner_b" not in a_callees
