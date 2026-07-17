"""NPATH Complexity metric (arch §1.3).

Walks ControlFlowNode tree applying recursive path-product formula. CFN
siblings at the same depth are multiplied (sequence rule). IF/ELIF/ELSE
and TRY/EXCEPT relationships are recovered by scanning adjacent siblings
(our CFN tree emits these flat, not nested).

EMPIRICAL OBSERVATION (Slice 4a Task 4):
- BOOLEAN_SEQUENCE is emitted as a SIBLING AFTER the IF node, at the same
  depth. It is NOT inside the IF's children. It follows after any ELIF/ELSE
  siblings that belong to the same if-chain.
- Example: `if x > 0 and y > 0:` emits [IF, BOOLEAN_SEQUENCE] as siblings.
- Example: `if cond: ... elif other: ...` emits [IF, ELIF] as siblings.

KNOWN GAPS (metric_version=1.0.0):
- Condition NPATH approximated: +1 per BOOLEAN_SEQUENCE immediately following
  the if-chain (before the next non-elif/else/boolean_sequence sibling).
- COMPREHENSION approximated as NPATH=3 (if/for hybrid).
- TERNARY approximated as NPATH=3.
- No MAX_NPATH cap — Python ints arbitrary precision (storage-layer concern
  lands in Slice 5).
- Lambda bodies attributed to enclosing function (Slice 2 design).
"""

from __future__ import annotations

from savviety_instinct.analyze.metrics._resolve import resolve_function_node
from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Confidence,
    InputKind,
    MetricValue,
)
from savviety_instinct.parse.types import ControlFlowNode, ControlFlowNodeKind


def _npath_of_children(nodes: tuple[ControlFlowNode, ...]) -> int:
    """Multiply NPATHs across sibling CFNs (sequence rule). Empty = 1.

    Walks left-to-right consuming chains (if+elif+else, try+except).
    BOOLEAN_SEQUENCE that immediately follows an if-chain is consumed as
    part of that chain's condition NPATH (+1 per occurrence).
    """
    if not nodes:
        return 1
    lst = list(nodes)
    result = 1
    i = 0
    while i < len(lst):
        node = lst[i]
        if node.kind == ControlFlowNodeKind.IF:
            npath, consumed = _if_chain_npath(lst, i)
            result *= npath
            i += consumed
        elif node.kind == ControlFlowNodeKind.TRY:
            npath, consumed = _try_chain_npath(lst, i)
            result *= npath
            i += consumed
        elif node.kind in (
            ControlFlowNodeKind.ELIF,
            ControlFlowNodeKind.ELSE,
            ControlFlowNodeKind.EXCEPT,
        ):
            # Unattached (shouldn't happen). Defensive: treat body as sequence.
            result *= _npath_of_children(node.children)
            i += 1
        else:
            result *= _leaf_npath(node)
            i += 1
    return result


def _if_chain_npath(lst: list[ControlFlowNode], start: int) -> tuple[int, int]:
    """Compute NPATH for an IF chain starting at lst[start].

    Returns (npath, number_of_siblings_consumed).

    Consumes: IF + any following ELIF + optional ELSE + any trailing
    BOOLEAN_SEQUENCE siblings (which represent the condition's boolean
    operators in the parsed CFN tree).

    Formula (arch §1.3):
      if (c) S1:            NPATH(c) + NPATH(S1) + 1
      if (c) S1 else S2:    NPATH(c) + NPATH(S1) + NPATH(S2)
      NPATH(c) = 1 + count(adjacent BOOLEAN_SEQUENCE siblings)
    """
    if_node = lst[start]
    condition_npath = 1  # base condition NPATH; bumped per adjacent BOOLEAN_SEQUENCE
    body_npath = _npath_of_children(if_node.children)

    consumed = 1
    has_else = False

    # Collect condition NPATH for the IF: NPATH(c) + NPATH(body)
    # We need to scan forward to consume ELIF/ELSE first, THEN look for trailing
    # BOOLEAN_SEQUENCE. The BOOLEAN_SEQUENCE for this if's condition appears
    # AFTER any ELIF/ELSE siblings (empirically observed).
    # Build the chain first, then check for trailing BOOLEAN_SEQUENCE.

    elif_else_npath = 0  # accumulated NPATH from ELIF and ELSE branches
    idx = start + 1
    while idx < len(lst):
        sibling = lst[idx]
        if sibling.kind == ControlFlowNodeKind.ELIF:
            # ELIF contributes: NPATH(elif_condition) + NPATH(elif_body)
            # NPATH(elif_condition) = 1 (approximated; no separate BOOLEAN_SEQUENCE
            # for ELIF condition in observed tree shape)
            elif_else_npath += 1 + _npath_of_children(sibling.children)
            consumed += 1
            idx += 1
        elif sibling.kind == ControlFlowNodeKind.ELSE:
            elif_else_npath += _npath_of_children(sibling.children)
            consumed += 1
            idx += 1
            has_else = True
            break
        else:
            break

    # Now check for trailing BOOLEAN_SEQUENCE siblings (the IF's condition booleans).
    # These appear after the last ELIF/ELSE in the flat sibling list.
    while idx < len(lst) and lst[idx].kind == ControlFlowNodeKind.BOOLEAN_SEQUENCE:
        condition_npath += 1  # each BOOLEAN_SEQUENCE adds +1 to condition NPATH
        consumed += 1
        idx += 1

    # Assemble: condition_npath + body_npath + elif/else_npath [+ 1 if no else]
    total = condition_npath + body_npath + elif_else_npath
    if not has_else:
        total += 1  # the "no-branch-taken" path

    return total, consumed


def _try_chain_npath(lst: list[ControlFlowNode], start: int) -> tuple[int, int]:
    """Compute NPATH for a TRY chain starting at lst[start].

    Returns (npath, number_of_siblings_consumed).

    Formula (arch §1.3):
      try S catch C1..Cn:  NPATH(S) + Σ NPATH(Ci)
    """
    try_node = lst[start]
    total = _npath_of_children(try_node.children)
    consumed = 1
    idx = start + 1
    while idx < len(lst):
        sibling = lst[idx]
        if sibling.kind == ControlFlowNodeKind.EXCEPT:
            total += _npath_of_children(sibling.children)
            consumed += 1
            idx += 1
        else:
            break
    return total, consumed


def _leaf_npath(node: ControlFlowNode) -> int:
    """NPATH for a node that is not an IF or TRY chain head.

    FOR/WHILE: 1 (condition) + NPATH(body) + 1 (no-iteration path)
    TERNARY: 3 (approximation — if/else with one condition)
    COMPREHENSION: 3 (approximation — for+if hybrid)
    BOOLEAN_SEQUENCE: 2 (standalone; normally consumed inside if-chain)
    Other: 1 (safe degradation)
    """
    if node.kind in (ControlFlowNodeKind.FOR, ControlFlowNodeKind.WHILE):
        # condition NPATH = 1; body NPATH = recursive; +1 for no-iteration path
        return 1 + _npath_of_children(node.children) + 1
    if node.kind == ControlFlowNodeKind.TERNARY:
        return 3
    if node.kind == ControlFlowNodeKind.COMPREHENSION:
        return 3
    if node.kind == ControlFlowNodeKind.BOOLEAN_SEQUENCE:
        # Standalone boolean expression not adjacent to an IF chain.
        # Contributes 2 paths (true / false of the expression).
        return 2
    # Defensive fallback for any future CFN kinds.
    return 1


class NPathMetric:
    id: str = "npath"
    version: str = "1.0.0"
    applies_to: frozenset[ArtifactKind] = frozenset({ArtifactKind.FUNCTION})
    required_inputs: frozenset[InputKind] = frozenset({InputKind.AST})
    shape_invariant: bool = True

    def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue:
        fn = resolve_function_node(self.id, artifact, context)
        return MetricValue(
            metric_id=self.id,
            value=_npath_of_children(fn.control_flow),
            metric_version=self.version,
            confidence=Confidence.HIGH,
        )


NPATH_METRIC = NPathMetric()
