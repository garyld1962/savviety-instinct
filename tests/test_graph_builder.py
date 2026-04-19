"""Tests for graph.builder — build CallGraph from ParseResult."""

from __future__ import annotations

from pathlib import Path

from savviety_instinct.graph.builder import build_call_graph
from savviety_instinct.parse.python import PYTHON_ADAPTER

FIXTURES = Path(__file__).parent / "fixtures" / "python"


def test_simple_module_graph_has_two_nodes_one_edge() -> None:
    result = PYTHON_ADAPTER.parse_path(FIXTURES / "simple_module.py")
    g = build_call_graph(result)
    assert set(g.functions()) == {"helper", "main"}
    assert g.edge_count() == 1
    assert g.callees_of("main") == ("helper",)


def test_with_class_graph_includes_methods_and_external_call() -> None:
    result = PYTHON_ADAPTER.parse_path(FIXTURES / "with_class.py")
    g = build_call_graph(result)
    # module_level, Worker.do_work, Worker.other
    assert set(g.functions()) == {"module_level", "Worker.do_work", "Worker.other"}
    # do_work calls module_level
    assert "module_level" in g.callees_of("Worker.do_work")
    # other calls self.do_work → resolves via bare-name match on `do_work`
    assert "Worker.do_work" in g.callees_of("Worker.other")


def test_unresolved_external_call_is_dropped() -> None:
    """A call to a name not defined in the file adds no edge."""
    from savviety_instinct.core.types import Language, SourceRange
    from savviety_instinct.parse.types import (
        CallSiteNode,
        FunctionDefNode,
        ParseResult,
    )

    fn = FunctionDefNode(
        name="main",
        qualified_name="main",
        enclosing_class=None,
        source_range=SourceRange(file_path="x.py", line_start=1, line_end=3),
        ast_hash="abc",
        parameter_names=(),
    )
    call = CallSiteNode(
        callee_name="requests",  # unresolved
        source_range=SourceRange(file_path="x.py", line_start=2, line_end=2),
        enclosing_function="main",
        is_resolved=False,
    )
    result = ParseResult(
        file_path="x.py",
        language=Language.PYTHON,
        functions=(fn,),
        classes=(),
        call_sites=(call,),
    )
    g = build_call_graph(result)
    assert g.edge_count() == 0
    assert set(g.functions()) == {"main"}


def test_module_level_call_has_no_edge_source() -> None:
    """A call at module scope (enclosing_function=None) contributes no edge."""
    from savviety_instinct.core.types import Language, SourceRange
    from savviety_instinct.parse.types import (
        CallSiteNode,
        FunctionDefNode,
        ParseResult,
    )

    fn = FunctionDefNode(
        name="helper",
        qualified_name="helper",
        enclosing_class=None,
        source_range=SourceRange(file_path="x.py", line_start=1, line_end=2),
        ast_hash="abc",
        parameter_names=(),
    )
    call = CallSiteNode(
        callee_name="helper",
        source_range=SourceRange(file_path="x.py", line_start=4, line_end=4),
        enclosing_function=None,  # top-level
        is_resolved=True,
    )
    result = ParseResult(
        file_path="x.py",
        language=Language.PYTHON,
        functions=(fn,),
        classes=(),
        call_sites=(call,),
    )
    g = build_call_graph(result)
    assert g.edge_count() == 0
