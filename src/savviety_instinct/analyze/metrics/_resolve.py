"""Shared FunctionDefNode resolution for function-scoped metrics.

Identity is `source_range` (file + line span), unique per occurrence within
a parse_result. `ast_hash` is NOT an identity: it is deliberately
identifier/literal-blind (arch §4.2), so two different functions can share
a hash — common in delegation-heavy code where wrappers are shape-identical.
Hash-based lookup returned whichever function matched first, which silently
mis-attributed identifier-dependent metric values (identifier_quality).

Known residual corner: SourceRange is line-based, so two lambdas defined on
the same line still collide. First match wins there; acceptable until
SourceRange grows column precision.
"""

from __future__ import annotations

from savviety_instinct.core.types import AnalysisContext, Artifact
from savviety_instinct.parse.types import FunctionDefNode


def resolve_function_node(
    metric_id: str, artifact: Artifact, context: AnalysisContext
) -> FunctionDefNode:
    """Return the FunctionDefNode this artifact was built from.

    Raises ValueError if the context has no parse_result, LookupError if no
    function in the parse_result matches the artifact's source_range.
    """
    if context.parse_result is None:
        raise ValueError(f"{metric_id} requires AnalysisContext.parse_result to be populated.")
    for fn in context.parse_result.functions:
        if fn.source_range == artifact.source_range:
            return fn
    raise LookupError(
        f"No FunctionDefNode with source_range={artifact.source_range!r} found in "
        f"parse_result.functions (file={context.parse_result.file_path!r})"
    )
