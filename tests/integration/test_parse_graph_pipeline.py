"""Integration: parse a Python fixture end-to-end, build call graph, assert shape.

This is the Slice 2 acceptance: a source file goes in, a CallGraph with correct
nodes and edges comes out, with no crashes on the syntax-error fixture.
"""

from __future__ import annotations

from pathlib import Path

from savviety_instinct.core.types import AnalysisContext
from savviety_instinct.graph import build_call_graph
from savviety_instinct.parse import PYTHON_ADAPTER

FIXTURES = Path(__file__).parent.parent / "fixtures" / "python"


def test_pipeline_simple_module_produces_graph() -> None:
    result = PYTHON_ADAPTER.parse_path(FIXTURES / "simple_module.py")
    assert result.ok
    graph = build_call_graph(result)
    ctx = AnalysisContext(call_graph=graph)
    # AnalysisContext can carry the graph into metric computation (Slice 3+).
    assert ctx.call_graph is graph
    assert "main" in graph.functions()
    assert "helper" in graph.callees_of("main")


def test_pipeline_handles_syntax_error_without_crash() -> None:
    result = PYTHON_ADAPTER.parse_path(FIXTURES / "syntax_error.py")
    assert not result.ok
    # Graph builder on an errored ParseResult must still produce a valid graph
    # (empty or partial) — arch §9 says degrade, don't crash.
    graph = build_call_graph(result)
    # No assertion on exact shape; tree-sitter may still extract the partial
    # `def broken(` as a FunctionDefNode. Key assertion: no exception.
    assert graph is not None


def test_pipeline_class_methods_resolve_via_bare_name() -> None:
    result = PYTHON_ADAPTER.parse_path(FIXTURES / "with_class.py")
    graph = build_call_graph(result)
    # other() -> self.do_work() -> Worker.do_work
    assert "Worker.do_work" in graph.callees_of("Worker.other")
    # do_work() -> module_level()
    assert "module_level" in graph.callees_of("Worker.do_work")
