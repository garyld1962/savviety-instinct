"""Property-based invariant tests for metric value ranges.

For each metric, hypothesis generates many small-but-valid Python source
strings and asserts the output satisfies the metric's value-range
invariant. These catch silent violations on inputs outside the
hand-curated fixture set.

Invariants checked:
  - statement_count              >= 0
  - cyclomatic_complexity        >= 1
  - cognitive_complexity         >= 0
  - max_nesting_depth            >= 0
  - npath                        >= 1
  - identifier_quality           in [0.0, 1.0]
  - trivial_delegation_ratio     in [0.0, 1.0]
  - function_length_bimodality   in [0.0, 1.0]

Strategy: assemble small function / module sources from a fixed vocabulary
of single-line statements. This keeps hypothesis's search space bounded
while still exercising varied control-flow, nesting, and identifier
patterns. We deliberately avoid generating arbitrary Python syntax
(ambient complexity with little marginal coverage per iteration).
"""

from __future__ import annotations

import string

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from savviety_instinct.analyze import (
    COGNITIVE_METRIC,
    CYCLOMATIC_METRIC,
    FUNCTION_LENGTH_BIMODALITY_METRIC,
    IDENTIFIER_QUALITY_METRIC,
    MAX_NESTING_DEPTH_METRIC,
    MEDIAN_FUNCTION_LENGTH_METRIC,
    NPATH_METRIC,
    STATEMENT_COUNT_METRIC,
    TRIVIAL_DELEGATION_RATIO_METRIC,
)
from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Language,
    SourceRange,
)
from savviety_instinct.parse.python import PYTHON_ADAPTER
from savviety_instinct.parse.types import FunctionDefNode

# ---------- Source-generation strategies ----------

# Single-line statements only — sidesteps indentation complexity in hypothesis
# while still exercising varied control-flow. These must all be valid Python
# when indented one level under a `def:` line.
_SIMPLE_STATEMENTS: tuple[str, ...] = (
    "pass",
    "x = 1",
    "y = x + 1",
    "z = x * 2",
    "result = x + y",
    "return x",
    "return 0",
    "return x + 1",
    "if x > 0: return x",
    "if y < 0: return -y",
    "for i in range(10): x = x + i",
    "while x > 0: x = x - 1",
    "return x if x > 0 else -x",
    "return [i for i in range(10) if i > 0]",
    "return sum(j for j in range(5))",
    "return {k: k * 2 for k in range(3)}",
)


@st.composite
def simple_function_source(draw: st.DrawFn) -> str:
    """Generate a small, syntactically valid function definition."""
    suffix = draw(st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=4))
    n_params = draw(st.integers(min_value=0, max_value=3))
    params = [f"p{i}" for i in range(n_params)]
    n_stmts = draw(st.integers(min_value=1, max_value=5))
    stmts = [draw(st.sampled_from(_SIMPLE_STATEMENTS)) for _ in range(n_stmts)]
    body = "\n    ".join(stmts)
    return f"def fn_{suffix}({', '.join(params)}):\n    {body}\n"


@st.composite
def simple_module_source(draw: st.DrawFn) -> str:
    """Generate a module with 4..32 small functions (spans bimodality's n-tiers)."""
    n_fns = draw(st.integers(min_value=4, max_value=32))
    sources = [draw(simple_function_source()) for _ in range(n_fns)]
    # Rename so names don't collide across draws.
    renamed = []
    for i, src in enumerate(sources):
        renamed.append(src.replace("def fn_", f"def m{i:02d}_", 1))
    return "\n".join(renamed)


# ---------- Helpers ----------


def _function_artifact(fn: FunctionDefNode, file_path: str = "<hypothesis>") -> Artifact:
    return Artifact(
        ast_hash=fn.ast_hash,
        language=Language.PYTHON,
        kind=ArtifactKind.FUNCTION,
        name=fn.name,
        enclosing_scope=fn.enclosing_class,
        source_range=fn.source_range,
    )


def _module_artifact(file_path: str, line_end: int) -> Artifact:
    return Artifact(
        ast_hash="synthetic",
        language=Language.PYTHON,
        kind=ArtifactKind.MODULE,
        name=file_path,
        enclosing_scope=None,
        source_range=SourceRange(file_path=file_path, line_start=1, line_end=line_end),
    )


_FN_SETTINGS = settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)

_MOD_SETTINGS = settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


# ---------- Function-level invariants ----------


@given(source=simple_function_source())
@_FN_SETTINGS
def test_statement_count_non_negative(source: str) -> None:
    result = PYTHON_ADAPTER.parse_source(source.encode(), "<hypothesis>")
    if not result.ok or not result.functions:
        return  # skip malformed draws
    fn = result.functions[0]
    ctx = AnalysisContext(parse_result=result)
    value = STATEMENT_COUNT_METRIC.compute(_function_artifact(fn), ctx)
    assert value.value >= 0, f"statement_count={value.value} for:\n{source}"


@given(source=simple_function_source())
@_FN_SETTINGS
def test_cyclomatic_at_least_one(source: str) -> None:
    result = PYTHON_ADAPTER.parse_source(source.encode(), "<hypothesis>")
    if not result.ok or not result.functions:
        return
    fn = result.functions[0]
    ctx = AnalysisContext(parse_result=result)
    value = CYCLOMATIC_METRIC.compute(_function_artifact(fn), ctx)
    assert value.value >= 1, f"cyclomatic={value.value} for:\n{source}"


@given(source=simple_function_source())
@_FN_SETTINGS
def test_cognitive_non_negative(source: str) -> None:
    result = PYTHON_ADAPTER.parse_source(source.encode(), "<hypothesis>")
    if not result.ok or not result.functions:
        return
    fn = result.functions[0]
    ctx = AnalysisContext(parse_result=result)
    value = COGNITIVE_METRIC.compute(_function_artifact(fn), ctx)
    assert value.value >= 0, f"cognitive={value.value} for:\n{source}"


@given(source=simple_function_source())
@_FN_SETTINGS
def test_max_nesting_depth_non_negative(source: str) -> None:
    result = PYTHON_ADAPTER.parse_source(source.encode(), "<hypothesis>")
    if not result.ok or not result.functions:
        return
    fn = result.functions[0]
    ctx = AnalysisContext(parse_result=result)
    value = MAX_NESTING_DEPTH_METRIC.compute(_function_artifact(fn), ctx)
    assert value.value >= 0, f"max_nesting_depth={value.value} for:\n{source}"


@given(source=simple_function_source())
@_FN_SETTINGS
def test_npath_at_least_one(source: str) -> None:
    result = PYTHON_ADAPTER.parse_source(source.encode(), "<hypothesis>")
    if not result.ok or not result.functions:
        return
    fn = result.functions[0]
    ctx = AnalysisContext(parse_result=result)
    value = NPATH_METRIC.compute(_function_artifact(fn), ctx)
    assert value.value >= 1, f"npath={value.value} for:\n{source}"


@given(source=simple_function_source())
@_FN_SETTINGS
def test_identifier_quality_in_unit_interval(source: str) -> None:
    result = PYTHON_ADAPTER.parse_source(source.encode(), "<hypothesis>")
    if not result.ok or not result.functions:
        return
    fn = result.functions[0]
    ctx = AnalysisContext(parse_result=result)
    value = IDENTIFIER_QUALITY_METRIC.compute(_function_artifact(fn), ctx)
    assert 0.0 <= value.value <= 1.0, f"identifier_quality={value.value} for:\n{source}"


# ---------- Module-level invariants ----------


@given(source=simple_module_source())
@_MOD_SETTINGS
def test_trivial_delegation_ratio_in_unit_interval(source: str) -> None:
    result = PYTHON_ADAPTER.parse_source(source.encode(), "<hypothesis>")
    if not result.ok:
        return
    ctx = AnalysisContext(parse_result=result)
    value = TRIVIAL_DELEGATION_RATIO_METRIC.compute(
        _module_artifact("<hypothesis>", result.line_count), ctx
    )
    assert 0.0 <= value.value <= 1.0, f"trivial_delegation_ratio={value.value}"


@given(source=simple_module_source())
@_MOD_SETTINGS
def test_median_function_length_non_negative(source: str) -> None:
    result = PYTHON_ADAPTER.parse_source(source.encode(), "<hypothesis>")
    if not result.ok:
        return
    ctx = AnalysisContext(parse_result=result)
    value = MEDIAN_FUNCTION_LENGTH_METRIC.compute(
        _module_artifact("<hypothesis>", result.line_count), ctx
    )
    assert value.value >= 0, f"median_function_length={value.value}"


@given(source=simple_module_source())
@_MOD_SETTINGS
def test_bimodality_in_unit_interval(source: str) -> None:
    result = PYTHON_ADAPTER.parse_source(source.encode(), "<hypothesis>")
    if not result.ok:
        return
    ctx = AnalysisContext(parse_result=result)
    value = FUNCTION_LENGTH_BIMODALITY_METRIC.compute(
        _module_artifact("<hypothesis>", result.line_count), ctx
    )
    # Pearson's BC is theoretically bounded in [0, 1] for real distributions.
    # We allow a small numerical tolerance on the upper edge.
    assert 0.0 <= value.value <= 1.0 + 1e-9, f"bimodality={value.value} outside [0, 1]"
