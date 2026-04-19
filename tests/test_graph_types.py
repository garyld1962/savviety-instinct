"""Tests for graph.types — CallGraph wrapper around networkx.DiGraph."""

from __future__ import annotations

import pytest

from savviety_instinct.graph.types import CallGraph


def test_empty_graph_has_no_functions() -> None:
    g = CallGraph()
    assert g.functions() == ()
    assert g.edge_count() == 0


def test_add_function_registers_node() -> None:
    g = CallGraph()
    g.add_function("main", ast_hash="abc", file_path="x.py")
    assert "main" in g.functions()


def test_add_function_is_idempotent() -> None:
    g = CallGraph()
    g.add_function("main", ast_hash="abc", file_path="x.py")
    g.add_function("main", ast_hash="abc", file_path="x.py")
    assert g.functions() == ("main",)


def test_add_call_creates_edge() -> None:
    g = CallGraph()
    g.add_function("main", ast_hash="a", file_path="x.py")
    g.add_function("helper", ast_hash="b", file_path="x.py")
    g.add_call(caller="main", callee="helper")
    assert g.edge_count() == 1
    assert "helper" in g.callees_of("main")


def test_add_call_creates_nodes_lazily_for_callers_only_if_known() -> None:
    """Adding a call when the caller is unregistered is a programmer error."""
    g = CallGraph()
    g.add_function("helper", ast_hash="b", file_path="x.py")
    with pytest.raises(KeyError, match="caller 'main' not in graph"):
        g.add_call(caller="main", callee="helper")


def test_unresolved_callee_is_dropped() -> None:
    """Scope Decision #2: drop unresolved edges; keep the code path simple."""
    g = CallGraph()
    g.add_function("main", ast_hash="a", file_path="x.py")
    # `external_thing` isn't a registered function; call silently drops.
    g.add_call(caller="main", callee="external_thing", is_resolved=False)
    assert g.edge_count() == 0


def test_callees_of_unknown_function_raises() -> None:
    g = CallGraph()
    with pytest.raises(KeyError, match="unknown function 'nope'"):
        g.callees_of("nope")


def test_callers_of_returns_incoming_edges() -> None:
    g = CallGraph()
    g.add_function("a", ast_hash="1", file_path="x.py")
    g.add_function("b", ast_hash="2", file_path="x.py")
    g.add_function("c", ast_hash="3", file_path="x.py")
    g.add_call("a", "c")
    g.add_call("b", "c")
    assert set(g.callers_of("c")) == {"a", "b"}
