"""Public API for the graph layer.

Arch §5.5. Intra-file CallGraph in Slice 2; module dependency graph + cross-file
resolution are reserved for later slices.
"""

from __future__ import annotations

from savviety_instinct.graph.builder import build_call_graph
from savviety_instinct.graph.types import CallGraph

__all__ = ["CallGraph", "build_call_graph"]
