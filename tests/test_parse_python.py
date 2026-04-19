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
