"""CallGraph — a thin typed wrapper around networkx.DiGraph.

Arch §5.5. The adjacency store is `networkx` because it gives us path and
centrality algorithms for free (Henry–Kafura, chain-depth-to-effect in later
slices). The wrapper exists because callers shouldn't handle networkx's
stringly-typed attribute bags.

Node attributes: `ast_hash: str`, `file_path: str`.
Edge attributes: none in Slice 2; Slice 3+ may add `is_conditional: bool` etc.
"""

from __future__ import annotations

import networkx as nx


class CallGraph:
    """Intra-file call graph. One instance per file in Slice 2; project-wide
    composition lands when cross-file resolution arrives (post-MVP).
    """

    def __init__(self) -> None:
        self._g: nx.DiGraph = nx.DiGraph()

    def add_function(self, qualified_name: str, *, ast_hash: str, file_path: str) -> None:
        self._g.add_node(qualified_name, ast_hash=ast_hash, file_path=file_path)

    def add_call(self, caller: str, callee: str, *, is_resolved: bool = True) -> None:
        """Record a call edge. Unresolved callees (those not in the graph) are dropped.

        Scope Decision #2: we do not create `ExternalCallee` placeholder nodes.
        Callers need the ability to look up all calls-originating-from-a-function
        via `callees_of`; keeping the adjacency clean means those callers don't
        have to filter out external nodes.
        """
        if caller not in self._g:
            raise KeyError(f"caller {caller!r} not in graph; add_function() first")
        if not is_resolved or callee not in self._g:
            return
        self._g.add_edge(caller, callee)

    def functions(self) -> tuple[str, ...]:
        return tuple(self._g.nodes())

    def edge_count(self) -> int:
        return int(self._g.number_of_edges())

    def callees_of(self, qualified_name: str) -> tuple[str, ...]:
        if qualified_name not in self._g:
            raise KeyError(f"unknown function {qualified_name!r}")
        return tuple(self._g.successors(qualified_name))

    def callers_of(self, qualified_name: str) -> tuple[str, ...]:
        if qualified_name not in self._g:
            raise KeyError(f"unknown function {qualified_name!r}")
        return tuple(self._g.predecessors(qualified_name))

    def as_networkx(self) -> nx.DiGraph:
        """Escape hatch for later slices that need nx algorithms directly."""
        return self._g
