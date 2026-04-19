"""Tests for ControlFlowNode extraction from PythonAdapter."""

from __future__ import annotations

from pathlib import Path

from savviety_instinct.parse.python import PYTHON_ADAPTER
from savviety_instinct.parse.types import ControlFlowNodeKind

FIXTURES = Path(__file__).parent / "fixtures" / "python"


def _fn(qualified_name: str):
    result = PYTHON_ADAPTER.parse_path(FIXTURES / "nested_control_flow.py")
    return next(fn for fn in result.functions if fn.qualified_name == qualified_name)


def test_straight_line_has_no_control_flow() -> None:
    fn = _fn("straight_line")
    assert fn.control_flow == ()


def test_straight_line_statement_count() -> None:
    fn = _fn("straight_line")
    # y = ..., z = ..., return z — three executable statements
    assert fn.statement_count == 3


def test_with_if_has_single_top_level_if() -> None:
    fn = _fn("with_if")
    top = [n for n in fn.control_flow if n.kind == ControlFlowNodeKind.IF]
    assert len(top) == 1
    node = top[0]
    assert node.nesting_depth == 0


def test_with_if_statement_count() -> None:
    fn = _fn("with_if")
    # 1 (if as compound statement) + 1 (return x inside if) + 1 (return 0) = 3
    assert fn.statement_count == 3


def test_deeply_nested_top_level_has_for() -> None:
    fn = _fn("deeply_nested")
    top_kinds = [n.kind for n in fn.control_flow]
    assert ControlFlowNodeKind.FOR in top_kinds
    # The `for` is at depth 0
    for_node = next(n for n in fn.control_flow if n.kind == ControlFlowNodeKind.FOR)
    assert for_node.nesting_depth == 0


def test_deeply_nested_for_has_if_child() -> None:
    fn = _fn("deeply_nested")
    for_node = next(n for n in fn.control_flow if n.kind == ControlFlowNodeKind.FOR)
    # Inside for: an if at depth 1
    nested_ifs = [c for c in for_node.children if c.kind == ControlFlowNodeKind.IF]
    assert len(nested_ifs) >= 1
    assert nested_ifs[0].nesting_depth == 1


def test_boolean_ops_captured_as_single_sequence() -> None:
    """A sequence of mixed `and`/`or` operators inside one expression counts as
    one BOOLEAN_SEQUENCE CFN, NOT per operator. This matches Sonar's rule and
    §1.2's 'per group, not per operator'.
    """
    fn = _fn("boolean_ops")

    # Recursive count of BOOLEAN_SEQUENCE across all CFNs (top + children).
    def _count(nodes):
        return sum(
            (1 if n.kind == ControlFlowNodeKind.BOOLEAN_SEQUENCE else 0) + _count(n.children)
            for n in nodes
        )

    assert _count(fn.control_flow) == 1


def test_comprehension_emits_comprehension_cfn() -> None:
    fn = _fn("comprehension_example")

    def _collect_kinds(nodes, out=None):
        if out is None:
            out = []
        for n in nodes:
            out.append(n.kind)
            _collect_kinds(n.children, out)
        return out

    kinds = _collect_kinds(fn.control_flow)
    assert ControlFlowNodeKind.COMPREHENSION in kinds


def test_ternary_emits_ternary_cfn() -> None:
    fn = _fn("ternary_example")

    def _collect_kinds(nodes, out=None):
        if out is None:
            out = []
        for n in nodes:
            out.append(n.kind)
            _collect_kinds(n.children, out)
        return out

    kinds = _collect_kinds(fn.control_flow)
    assert ControlFlowNodeKind.TERNARY in kinds


def test_existing_fixtures_still_parse_after_cfn_extraction() -> None:
    """Regression guard: adding CFN extraction must not break Slice 2 fixtures."""
    for name in ("simple_module.py", "with_class.py", "same_shape_different_names.py"):
        result = PYTHON_ADAPTER.parse_path(FIXTURES / name)
        assert result.ok, f"{name} failed to parse: {result.errors}"
