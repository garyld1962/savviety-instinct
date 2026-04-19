"""Build a CallGraph from a ParseResult.

Arch §5.3 pipeline stage 3. Intra-file only in Slice 2 (Scope Decision #2).
Module-level call sites (enclosing_function is None) are ignored: they have no
caller to attach an edge to and MVP metrics reason about call depth relative to
function definitions.
"""

from __future__ import annotations

from savviety_instinct.graph.types import CallGraph
from savviety_instinct.parse.types import ParseResult


def build_call_graph(parse_result: ParseResult) -> CallGraph:
    g = CallGraph()
    for fn in parse_result.functions:
        g.add_function(
            fn.qualified_name,
            ast_hash=fn.ast_hash,
            file_path=parse_result.file_path,
        )

    # Index short-name → qualified so `self.do_work()` (bare `do_work`) resolves
    # to `Worker.do_work` when the class is unambiguous within the file.
    name_to_qualified: dict[str, list[str]] = {}
    for fn in parse_result.functions:
        name_to_qualified.setdefault(fn.name, []).append(fn.qualified_name)
        name_to_qualified.setdefault(fn.qualified_name, []).append(fn.qualified_name)

    for call in parse_result.call_sites:
        if call.enclosing_function is None:
            # Module-level call: no caller node to attach an edge to.
            continue
        if not call.is_resolved:
            continue
        targets = name_to_qualified.get(call.callee_name, [])
        # Ambiguous short-name resolution (multiple classes define the same
        # method name) is handled by adding edges to ALL candidates. A later
        # slice with type-flow info will narrow this.
        for target in targets:
            g.add_call(
                caller=call.enclosing_function,
                callee=target,
                is_resolved=True,
            )
    return g
