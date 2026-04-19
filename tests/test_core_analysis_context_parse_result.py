"""AnalysisContext.parse_result — forward-ref, layering-preserving extension."""

from __future__ import annotations


def test_analysis_context_accepts_parse_result() -> None:
    from savviety_instinct.core.types import AnalysisContext
    from savviety_instinct.parse.python import PYTHON_ADAPTER

    result = PYTHON_ADAPTER.parse_source(b"def x() -> int:\n    return 1\n", "inline.py")
    ctx = AnalysisContext(parse_result=result)
    assert ctx.parse_result is result


def test_analysis_context_parse_result_defaults_to_none() -> None:
    from savviety_instinct.core.types import AnalysisContext

    ctx = AnalysisContext()
    assert ctx.parse_result is None


def test_core_types_does_not_import_parse_at_runtime() -> None:
    """Arch §2: core is at the bottom. Loading core.types must not transitively
    pull in parse. The TYPE_CHECKING guard + quoted annotation keep the
    reference type-only.
    """
    from savviety_instinct.core import types as core_types

    anno = core_types.AnalysisContext.__annotations__.get("parse_result", "")
    assert isinstance(anno, str), (
        f"parse_result annotation must remain a string at runtime; got {type(anno)}"
    )
    assert "ParseResult" in anno


def test_combined_call_graph_and_parse_result() -> None:
    """Both Slice 2's call_graph and Slice 3's parse_result coexist."""
    from savviety_instinct.core.types import AnalysisContext
    from savviety_instinct.graph import CallGraph
    from savviety_instinct.parse.python import PYTHON_ADAPTER

    result = PYTHON_ADAPTER.parse_source(b"def x() -> int:\n    return 1\n", "inline.py")
    cg = CallGraph()
    ctx = AnalysisContext(parse_result=result, call_graph=cg)
    assert ctx.parse_result is result
    assert ctx.call_graph is cg
