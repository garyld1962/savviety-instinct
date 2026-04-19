# Slice 4a — Function-Level Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.
>
> **Gary's chosen flow:** `/plan` → `/execute-plan`. One commit per task. Branch `slice-4a-function-metrics`, split from parent Slice 4 because module-level and class-level metrics (LCOM-HS, trivial_delegation_ratio, median_function_length) are Slice 4b.

**Goal:** Three more function-level AST metrics — `max_nesting_depth`, `npath`, `identifier_quality` — to round out Phase 1's per-function signal alongside Slice 3's cyclomatic/cognitive/statement_count trio. No new infrastructure (no cross-file graph, no module graph, no git history, no storage writes).

**Architecture:** All three metrics operate on the existing Slice 3 foundation: `FunctionDefNode.control_flow` tree + `FunctionDefNode.statement_count`. `max_nesting_depth` is a CFN-tree traversal computing the deepest nesting of block-level control structures. `npath` is a recursive path-product computation over the CFN tree applying arch §1.3's formula. `identifier_quality` requires one new parse-layer field — `FunctionDefNode.identifier_names: tuple[str, ...]` — carrying all identifier occurrences from the function body; the metric then applies a heuristic (length ≥ 3, not in stopword list) to compute a ratio. Metrics register into `METRICS_REGISTRY` and dispatch through the existing `analyze/pipeline.py` unchanged.

**Tech Stack:** Python 3.12+, tree-sitter-python 0.23.x (existing), no new deps.

---

## Scope Decisions (locked)

1. **Function-level only.** Module-level and class-level metrics (`trivial_delegation_ratio`, `median_function_length`, `LCOM-HS`) land in Slice 4b. Reasoning: keeps the merge reviewable and defers the `ArtifactKind.MODULE` pipeline changes.
2. **No cross-file or module-graph metrics.** Afferent coupling, efferent coupling, instability, abstractness, Henry-Kafura, module_locality require infrastructure we haven't built. Deferred to a dedicated "graph infrastructure" slice.
3. **No temporal metrics.** Change frequency, bug-fix density, author count, stability tier need git history (pydriller/gix). Deferred.
4. **No class-level metrics.** LCOM-HS and class-level abstractness need method↔attribute-read graph extraction. Deferred to 4b (we'll assess then whether the parse-layer work is worth it).
5. **`identifier_quality` stopword list locked for Slice 4a (§1.2):**
   ```
   STOPWORDS = {"i", "j", "k", "x", "y", "z", "tmp", "foo", "bar", "baz"}
   ```
   Heuristic: `meaningful` iff `len(identifier) >= 3 AND identifier not in STOPWORDS`. The quality score = `len(unique_meaningful) / max(len(unique_all), 1)`. This matches arch §4.1 as closely as a heuristic allows; LLM-augmented refinement is R2.
6. **Identifier extraction in parse layer, not metric layer.** `analyze/` must never import tree-sitter. Add `FunctionDefNode.identifier_names: tuple[str, ...]` — all identifier OCCURRENCES (including duplicates) from the function body. Metric dedupes via `set(...)`. Pre-computation is O(1) extra work since the parse walk already visits every node.
7. **Identifier extraction scope:** function body only. Does NOT include the function's own name (that's `FunctionDefNode.name`) or parameter names (that's `FunctionDefNode.parameter_names`). The metric combines all three sources: `name + parameter_names + identifier_names` for the denominator and numerator.
8. **Max-nesting counts block-level control only.** `IF`/`ELIF`/`FOR`/`WHILE`/`TRY`/`EXCEPT` increment depth; `TERNARY`, `BOOLEAN_SEQUENCE`, `COMPREHENSION` do NOT (they're expression-level, don't change indentation). `ELSE` also does NOT (sibling of IF at same structural depth).
9. **NPATH overflow behavior:** no cap in Slice 4a. Return the raw computed integer. Slice 5 (storage) adds `npath_overflow` boolean when BLOB serialization concerns arise. Python ints are arbitrary precision so no overflow exception can occur.
10. **Lambdas and nested function definitions reset the count.** Already implicit because `parse/python.py`'s `_collect_functions` does not recurse into `function_definition` children (Slice 2's design). Lambdas today are NOT treated as function resets — see Known Gap #3.
11. **Metric versions start at `1.0.0`.** Same as Slice 3 metrics. Parallel numbering, not tied to other metrics' versions.
12. **No changes to `Metric` Protocol** (from Slice 1). Three new metric classes conform to the existing Protocol as-is.
13. **`identifier_quality` confidence is `Confidence.LOW`** per arch §4.1 ("low individually — heuristic"). Other two metrics return `Confidence.HIGH`.
14. **Empty function handling:** if a function has ZERO identifiers (e.g., `def empty(): pass` with no body variables, no params, and empty name — which can't happen in valid Python), `identifier_quality` returns `1.0` with `Confidence.LOW` and a note. The function name is always non-empty so in practice this path is unreachable; documented for robustness.
15. **Known gaps** (documented in code, fix via future metric_version bump):
    - **Gap #1:** Lambdas' internal control flow is currently attributed to the enclosing function. Affects `max_nesting_depth` (lambda bodies look nested) and `npath` (lambda expressions contribute paths). Fix would require parse-layer change to either recurse into lambdas as separate functions or exclude their internal CFNs.
    - **Gap #2:** `identifier_quality` uses distinct-name counting (via `set(...)`). Doesn't distinguish identifier USAGE frequency from DECLARATION count. Formally fine per arch §4.1 spec.
    - **Gap #3:** Context-aware exemption (e.g., "x in math context") not implemented — all single-letter names except `i`/`j`/`k` are stopworded unconditionally. The spec notes this is acceptable for the R1 heuristic.
    - **Gap #4:** NPATH formula simplification: we implement block-level contributions only. Condition NPATH (`NPATH(c)` in `if (c) S1`) is approximated as 1 unless the condition contains a `BOOLEAN_SEQUENCE` CFN, in which case +1 per sequence. Matches the Slice 3 cyclomatic approximation — acceptable imprecision for a de-emphasized metric.

---

## File Structure

| Path | Purpose |
|------|---------|
| `tests/fixtures/python/metric_fixtures.py` | Extend existing fixtures with max_nesting_depth / npath / identifier_quality expected values in docstrings |
| `src/savviety_instinct/parse/types.py` | Add `identifier_names: tuple[str, ...] = ()` to `FunctionDefNode` |
| `src/savviety_instinct/parse/python.py` | Add `_collect_identifiers(body_node)` helper; wire into `_collect_functions` |
| `src/savviety_instinct/analyze/metrics/max_nesting_depth.py` | `MAX_NESTING_DEPTH_METRIC` singleton |
| `src/savviety_instinct/analyze/metrics/npath.py` | `NPATH_METRIC` singleton |
| `src/savviety_instinct/analyze/metrics/identifier_quality.py` | `IDENTIFIER_QUALITY_METRIC` singleton + stopword list |
| `src/savviety_instinct/analyze/metrics/__init__.py` | Re-export three new metrics |
| `src/savviety_instinct/analyze/__init__.py` | Add new metrics to `METRICS_REGISTRY` |
| `tests/test_parse_identifier_names.py` | Tests for parse-layer identifier extraction |
| `tests/test_analyze_metric_max_nesting_depth.py` | Unit tests with `metric_fixtures.py` parametrized cases |
| `tests/test_analyze_metric_npath.py` | Unit tests |
| `tests/test_analyze_metric_identifier_quality.py` | Unit tests |
| `tests/integration/test_slice4a_metrics.py` | End-to-end: `instinct run` produces all 6 metrics (3 old + 3 new) per function |

---

## Task 1: Extend `metric_fixtures.py` docstrings with new expectations

**Files:**
- Modify: `tests/fixtures/python/metric_fixtures.py`

**Rationale:** `metric_fixtures.py` already contains 10 functions with cyclomatic/cognitive/statement_count ground-truth docstrings (Slice 3). Task 1 adds max_nesting_depth / npath / identifier_quality expectations alongside. Later tasks reference these values directly in parametrized tests.

**Computed expected values (ground truth — hand-verified against formulas):**

| Function | max_nesting_depth | npath | identifier_quality |
|----------|-------------------|-------|--------------------|
| `empty` | 0 | 1 | 1.0 (only `empty` as identifier) |
| `two_statements` | 0 | 1 | ~0.33 (meaningful: `two_statements`; non: `x, y`) |
| `single_if` | 1 | 3 | 0.5 (meaningful: `single_if`; non: `x`) |
| `single_if_with_boolean` | 1 | 4 | ~0.33 (meaningful: `single_if_with_boolean`; non: `x, y`) |
| `nested_if` | 2 | 5 | 0.5 (meaningful: `nested_if`; non: `x`) |
| `for_loop_only` | 1 | 3 | 1.0 (all of {`for_loop_only`, `items`, `total`, `item`}) |
| `for_with_if` | 2 | 5 | 1.0 (same — `item` is length 4) |
| `try_except` | 1 | 2 | 0.5 (meaningful: `try_except, ZeroDivisionError`; non: `x`) — actually 2/3 ≈ 0.67, see below |
| `ternary` | 0 | 3 | 0.5 (meaningful: `ternary`; non: `x`) |
| `comprehension` | 0 | 3 | ~0.67 (meaningful: `comprehension, items`; non: `i`) |

**NPATH computation reference** (arch §1.3):
- `empty`: trivial body → 1
- `two_statements`: `y = x + 1` × `return y` = 1 × 1 = 1
- `single_if`: `if (c) S1` + `return 0` = (1 + 1 + 1) × 1 = 3
- `single_if_with_boolean`: condition has +1 for `and`, so `if (c) S1` = (1+1) + 1 + 1 = 4. Body: 4 × 1 = 4
- `nested_if`: inner if = 1+1+1 = 3; outer if = 1 + 3 + 1 = 5; body = 5 × 1 = 5
- `for_loop_only`: `for` = 1 + 1 + 1 = 3; body = 1 × 3 × 1 = 3
- `for_with_if`: inner if = 3; `for` = 1 + 3 + 1 = 5; body = 1 × 5 × 1 = 5
- `try_except`: NPATH(try S catch C) = NPATH(S) + NPATH(C) = 1 + 1 = 2
- `ternary`: treated like if/else at expression level = 1 + 1 + 1 = 3
- `comprehension`: treated as loop-with-filter = 1 + 1 + 1 = 3

**Identifier_quality computation reference:**

For each function, unique identifiers = `{name} ∪ set(parameter_names) ∪ set(identifier_names_in_body)`. Meaningful iff `len >= 3 AND not in STOPWORDS`. STOPWORDS = `{i, j, k, x, y, z, tmp, foo, bar, baz}`.

- `empty`: `{empty}` → meaningful `{empty}` → 1/1 = 1.0
- `two_statements`: `{two_statements, x, y}` → meaningful `{two_statements}` → 1/3 ≈ 0.333
- `single_if`: `{single_if, x}` → meaningful `{single_if}` → 1/2 = 0.5
- `single_if_with_boolean`: `{single_if_with_boolean, x, y}` → meaningful `{single_if_with_boolean}` → 1/3 ≈ 0.333
- `nested_if`: `{nested_if, x}` → meaningful `{nested_if}` → 1/2 = 0.5
- `for_loop_only`: `{for_loop_only, items, total, item}` → ALL meaningful (all length ≥ 3, none stopworded) → 4/4 = 1.0
- `for_with_if`: same as for_loop_only → 1.0
- `try_except`: `{try_except, x, ZeroDivisionError}` → meaningful `{try_except, ZeroDivisionError}` → 2/3 ≈ 0.667
- `ternary`: `{ternary, x}` → meaningful `{ternary}` → 1/2 = 0.5
- `comprehension`: `{comprehension, items, i}` → meaningful `{comprehension, items}` → 2/3 ≈ 0.667

**Step 1: Modify each function's docstring**

Replace each docstring with expanded form. Example for `empty`:

```python
def empty() -> None:
    """statement_count=0, cyclomatic=1, cognitive=0, max_nesting=0, npath=1, identifier_quality=1.0."""
```

Apply the same pattern to all 10 functions. The existing cyclomatic/cognitive/statement_count values are CORRECT from Slice 3 — do not change them. Just append the three new values.

For floats, use `~` prefix for approximations:
```python
def two_statements(x: int) -> int:
    """statement_count=2, cyclomatic=1, cognitive=0, max_nesting=0, npath=1, identifier_quality=~0.333."""
    y = x + 1
    return y
```

**Step 2: Commit**

```bash
git add tests/fixtures/python/metric_fixtures.py
git commit -m "$(cat <<'EOF'
test: extend metric_fixtures docstrings with Slice 4a expected values

Documents expected max_nesting_depth, npath, and identifier_quality for
each of the 10 existing fixture functions. Ground truth — later tasks'
parametrized tests verify against these values; don't adjust fixtures
to match code output, iterate code to match fixtures.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

No behavior change, no tests run. The docstring updates document expectations for Tasks 3–5.

---

## Task 2: `FunctionDefNode.identifier_names` + parse extraction

**Files:**
- Modify: `src/savviety_instinct/parse/types.py`
- Modify: `src/savviety_instinct/parse/python.py`
- Create: `tests/test_parse_identifier_names.py`

**Step 1: Write failing tests**

```python
"""Tests for FunctionDefNode.identifier_names extraction."""

from __future__ import annotations

from pathlib import Path

from savviety_instinct.parse.python import PYTHON_ADAPTER


FIXTURES = Path(__file__).parent / "fixtures" / "python"


def _fn(qualified_name: str):
    result = PYTHON_ADAPTER.parse_path(FIXTURES / "metric_fixtures.py")
    return next(fn for fn in result.functions if fn.qualified_name == qualified_name)


def test_empty_function_has_no_body_identifiers() -> None:
    fn = _fn("empty")
    assert fn.identifier_names == ()


def test_two_statements_collects_body_identifiers() -> None:
    fn = _fn("two_statements")
    # body: y = x + 1; return y → x and y appear
    names = set(fn.identifier_names)
    assert "x" in names
    assert "y" in names


def test_identifier_names_excludes_function_name() -> None:
    """The function's own name is on FunctionDefNode.name, not in identifier_names."""
    fn = _fn("two_statements")
    assert "two_statements" not in fn.identifier_names


def test_identifier_names_excludes_parameter_names() -> None:
    """Parameter names are on FunctionDefNode.parameter_names, not in identifier_names.

    Parameters may still appear if used in the body — that's a body reference,
    not a definition. For `two_statements(x)` with `y = x + 1; return y`, the
    body uses `x`, so `x` IS in identifier_names (as a body reference). What's
    EXCLUDED is the parameter declaration slot itself.
    """
    fn = _fn("two_statements")
    # `x` used in body → should appear
    assert "x" in fn.identifier_names


def test_for_loop_collects_loop_variable() -> None:
    fn = _fn("for_loop_only")
    names = set(fn.identifier_names)
    assert "total" in names
    assert "item" in names
    assert "items" in names  # used in the for iterator expression


def test_comprehension_collects_iterator_variable() -> None:
    fn = _fn("comprehension")
    names = set(fn.identifier_names)
    assert "items" in names
    assert "i" in names


def test_try_except_collects_exception_type() -> None:
    """Exception class names are identifiers worth tracking for quality."""
    fn = _fn("try_except")
    names = set(fn.identifier_names)
    assert "ZeroDivisionError" in names


def test_identifier_names_is_tuple() -> None:
    """API contract: frozen sequence of strings."""
    fn = _fn("two_statements")
    assert isinstance(fn.identifier_names, tuple)
```

**Step 2: Run failing tests** → `AttributeError` on `identifier_names`.

**Step 3: Add the field to `FunctionDefNode`**

In `src/savviety_instinct/parse/types.py`, inside `FunctionDefNode`, add after `statement_count`:

```python
    # Slice 4a: all identifier occurrences in the function body (INCLUDING
    # duplicates; metric layer dedupes). Does NOT include the function's
    # own name or parameter slot declarations — those live on `name` and
    # `parameter_names`. Parameter references inside the body DO appear
    # (they're body usages, not declarations).
    identifier_names: tuple[str, ...] = ()
```

Update the module docstring to mention Slice 4a.

**Step 4: Extract identifiers in `parse/python.py`**

Add helper near `_count_statements`:

```python
def _collect_identifiers(body_node: Node, source: bytes) -> tuple[str, ...]:
    """Collect all identifier occurrences from a function body.

    Walks the subtree rooted at `body_node`, emitting the text of every
    `identifier`-kind tree-sitter node. Includes duplicates (order-preserved);
    the caller dedupes via `set()` if distinct-count is wanted. Excludes
    the function's own name slot and parameter declaration slots.

    Tree-sitter-python identifier-bearing node types:
      - identifier         — general variable/attribute/callable refs
      - type_identifier    — type annotations (if present)
      - attribute          — `foo.bar` — emits both `foo` and `bar`
    """
    out: list[str] = []
    stack: list[Node] = list(body_node.children)
    while stack:
        node = stack.pop()
        if node.type == "identifier":
            out.append(_text(node, source))
        # Recurse into everything except nested function_definition / class_definition
        # (their internal identifiers belong to those functions, not the parent).
        if node.type in ("function_definition", "class_definition", "lambda"):
            # Known Gap #1 from plan: lambdas aren't separated yet. For Slice 4a
            # we exclude lambda internals from the parent's identifier_names to
            # avoid double-attribution. max_nesting_depth and npath still have
            # the gap because their CFN input differs — separate concern.
            continue
        stack.extend(node.children)
    return tuple(out)
```

Wire into `_collect_functions` where `FunctionDefNode` is constructed:

```python
body_node = node.child_by_field_name("body")
control_flow = _collect_control_flow(body_node, file_path) if body_node else ()
statement_count = _count_statements(body_node) if body_node else 0
identifier_names = _collect_identifiers(body_node, source) if body_node else ()

fn_def = FunctionDefNode(
    name=name,
    qualified_name=qualified,
    enclosing_class=enclosing_class,
    source_range=_source_range(node, file_path),
    ast_hash=hash_ast_sexp(_sexp(node)),
    parameter_names=params,
    control_flow=control_flow,
    statement_count=statement_count,
    identifier_names=identifier_names,
)
```

**Step 5: Run tests + full parse suite**

```bash
uv run pytest tests/test_parse_identifier_names.py -v
uv run pytest tests/test_parse_python.py tests/test_parse_control_flow.py tests/test_parse_adapter.py -v 2>&1 | tail -5
```

All tests in both suites pass; no regressions.

**Step 6: Ruff + mypy + commit**

```bash
uv run ruff check src/savviety_instinct/parse tests/test_parse_identifier_names.py
uv run mypy src/savviety_instinct/parse/python.py src/savviety_instinct/parse/types.py

git add src/savviety_instinct/parse/types.py src/savviety_instinct/parse/python.py tests/test_parse_identifier_names.py
git commit -m "$(cat <<'EOF'
feat(parse): FunctionDefNode.identifier_names for identifier_quality metric

Collects all identifier occurrences from the function body during the
tree-sitter walk — no second traversal needed. Excludes function/class/
lambda internals (they belong to nested scopes, not the enclosing
function). Identifier_quality metric (Slice 4a Task 5) consumes this
field; stopword / length heuristics live in the metric.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `max_nesting_depth` metric

**Files:**
- Create: `src/savviety_instinct/analyze/metrics/max_nesting_depth.py`
- Create: `tests/test_analyze_metric_max_nesting_depth.py`
- Modify: `src/savviety_instinct/analyze/metrics/__init__.py`

**Formula (arch §1.4):** maximum depth of nested BLOCK-LEVEL control structures. Per Scope Decision #8, counted kinds = `{IF, ELIF, ELSE, FOR, WHILE, TRY, EXCEPT}`. Expression-level CFNs (`TERNARY`, `BOOLEAN_SEQUENCE`, `COMPREHENSION`) do NOT contribute.

**Step 1: Failing tests**

```python
"""Unit tests for max_nesting_depth metric."""

from __future__ import annotations

from pathlib import Path

import pytest

from savviety_instinct.analyze.metrics.max_nesting_depth import MAX_NESTING_DEPTH_METRIC
from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Confidence,
    InputKind,
    Language,
)
from savviety_instinct.parse.python import PYTHON_ADAPTER

FIXTURES = Path(__file__).parent / "fixtures" / "python"


@pytest.fixture
def metric_fixtures_result():
    return PYTHON_ADAPTER.parse_path(FIXTURES / "metric_fixtures.py")


def _artifact_for(result, qualified_name: str) -> Artifact:
    fn = next(f for f in result.functions if f.qualified_name == qualified_name)
    return Artifact(
        ast_hash=fn.ast_hash,
        language=Language.PYTHON,
        kind=ArtifactKind.FUNCTION,
        name=fn.name,
        enclosing_scope=fn.enclosing_class,
        source_range=fn.source_range,
    )


@pytest.mark.parametrize(
    "qualified,expected",
    [
        ("empty", 0),
        ("two_statements", 0),
        ("single_if", 1),
        ("single_if_with_boolean", 1),     # boolean in condition doesn't add depth
        ("nested_if", 2),
        ("for_loop_only", 1),
        ("for_with_if", 2),
        ("try_except", 1),
        ("ternary", 0),                    # ternary is expression-level
        ("comprehension", 0),              # comprehension is expression-level
    ],
)
def test_max_nesting_matches_fixture(metric_fixtures_result, qualified, expected) -> None:
    artifact = _artifact_for(metric_fixtures_result, qualified)
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    value = MAX_NESTING_DEPTH_METRIC.compute(artifact, ctx)
    assert value.value == expected, f"{qualified}: expected {expected}, got {value.value}"


def test_max_nesting_metadata() -> None:
    assert MAX_NESTING_DEPTH_METRIC.id == "max_nesting_depth"
    assert MAX_NESTING_DEPTH_METRIC.version == "1.0.0"
    assert MAX_NESTING_DEPTH_METRIC.applies_to == frozenset({ArtifactKind.FUNCTION})
    assert MAX_NESTING_DEPTH_METRIC.required_inputs == frozenset({InputKind.AST})


def test_max_nesting_high_confidence(metric_fixtures_result) -> None:
    artifact = _artifact_for(metric_fixtures_result, "nested_if")
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    assert MAX_NESTING_DEPTH_METRIC.compute(artifact, ctx).confidence == Confidence.HIGH


def test_max_nesting_empty_is_zero(metric_fixtures_result) -> None:
    artifact = _artifact_for(metric_fixtures_result, "empty")
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    assert MAX_NESTING_DEPTH_METRIC.compute(artifact, ctx).value == 0
```

**Step 2: Run failing tests** → ImportError.

**Step 3: Implement**

```python
"""Maximum Nesting Depth metric (arch §1.4).

Walks the `ControlFlowNode` tree counting the deepest nesting of
block-level control structures. Expression-level CFNs (TERNARY,
BOOLEAN_SEQUENCE, COMPREHENSION) don't contribute — they're inline,
don't change indentation, and aren't what §1.4 targets.
"""

from __future__ import annotations

from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Confidence,
    InputKind,
    MetricValue,
)
from savviety_instinct.parse.types import ControlFlowNode, ControlFlowNodeKind


# Block-level kinds that deepen visible indentation.
_BLOCK_KINDS: frozenset[ControlFlowNodeKind] = frozenset(
    {
        ControlFlowNodeKind.IF,
        ControlFlowNodeKind.ELIF,
        ControlFlowNodeKind.ELSE,
        ControlFlowNodeKind.FOR,
        ControlFlowNodeKind.WHILE,
        ControlFlowNodeKind.TRY,
        ControlFlowNodeKind.EXCEPT,
    }
)


def _max_depth(nodes: tuple[ControlFlowNode, ...], current: int = 0) -> int:
    best = current
    for node in nodes:
        if node.kind not in _BLOCK_KINDS:
            # Expression-level CFN — don't add depth, but still recurse (shouldn't
            # have block-level children, but be defensive).
            best = max(best, _max_depth(node.children, current))
            continue
        # This CFN adds a level of visible nesting.
        child_depth = _max_depth(node.children, current + 1)
        best = max(best, current + 1, child_depth)
    return best


class MaxNestingDepthMetric:
    id: str = "max_nesting_depth"
    version: str = "1.0.0"
    applies_to: frozenset[ArtifactKind] = frozenset({ArtifactKind.FUNCTION})
    required_inputs: frozenset[InputKind] = frozenset({InputKind.AST})

    def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue:
        if context.parse_result is None:
            raise ValueError(f"{self.id} requires AnalysisContext.parse_result")
        for fn in context.parse_result.functions:
            if fn.ast_hash == artifact.ast_hash:
                value = _max_depth(fn.control_flow)
                return MetricValue(
                    metric_id=self.id,
                    value=value,
                    metric_version=self.version,
                    confidence=Confidence.HIGH,
                )
        raise LookupError(
            f"No function with ast_hash={artifact.ast_hash!r} in parse_result"
        )


MAX_NESTING_DEPTH_METRIC = MaxNestingDepthMetric()
```

**Step 4: Register + test + commit**

Update `src/savviety_instinct/analyze/metrics/__init__.py`:

```python
from savviety_instinct.analyze.metrics.cognitive import COGNITIVE_METRIC
from savviety_instinct.analyze.metrics.cyclomatic import CYCLOMATIC_METRIC
from savviety_instinct.analyze.metrics.max_nesting_depth import MAX_NESTING_DEPTH_METRIC
from savviety_instinct.analyze.metrics.statement_count import STATEMENT_COUNT_METRIC

__all__ = [
    "COGNITIVE_METRIC",
    "CYCLOMATIC_METRIC",
    "MAX_NESTING_DEPTH_METRIC",
    "STATEMENT_COUNT_METRIC",
]
```

Run tests, ruff, mypy. Commit:

```bash
git add src/savviety_instinct/analyze/metrics/max_nesting_depth.py \
        src/savviety_instinct/analyze/metrics/__init__.py \
        tests/test_analyze_metric_max_nesting_depth.py
git commit -m "$(cat <<'EOF'
feat(analyze): max_nesting_depth metric (block-level CFN traversal)

Per arch §1.4. Counts depth over IF/ELIF/ELSE/FOR/WHILE/TRY/EXCEPT only
— expression-level CFNs (TERNARY, BOOLEAN_SEQUENCE, COMPREHENSION) are
inline and don't change visible indentation. Cognitive metric ignores
`ControlFlowNode.nesting_depth` for rule-agnosticism; max_nesting_depth
uses it directly because it IS the structural-nesting metric.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `npath` metric

**Files:**
- Create: `src/savviety_instinct/analyze/metrics/npath.py`
- Create: `tests/test_analyze_metric_npath.py`
- Modify: `src/savviety_instinct/analyze/metrics/__init__.py`

**Formula (arch §1.3):** recursive path-product. See plan header for the formula table. Slice 4a approximations per Scope Decision #9 (no overflow cap) and Gap #4 (condition NPATH approximated).

**Algorithm:**

```
npath_of_function = product_of_sibling_npaths(function.control_flow) × (1 if no CFNs else not_applicable)

Where product_of_sibling_npaths(nodes) =
  multiply npath(node) for node in nodes
  (empty list → 1)

And npath(node) based on kind:
  IF:            (product_of_sibling(else/elif siblings)) + npath(body) + 1
                 if siblings include ELSE: replace +1 with npath(else_body)
                 (Slice 4a approximation: we walk the children as the body)
  ELIF:          (handled as part of IF's alternative computation)
  ELSE:          (handled as part of IF's alternative computation)
  FOR, WHILE:    npath(body) + 1
  TRY:           npath(try_body) + sum(npath(except_body) for except_siblings)
  EXCEPT:        (handled as part of TRY computation)
  TERNARY:       3 (1 + 1 + 1 — condition + true branch + false branch)
  BOOLEAN_SEQ:   2 (+1 per boolean operator; Slice 4a approximation: 1 group = +1 so npath = 2)
  COMPREHENSION: 3 (approximated as if/for hybrid)

The trick: our CFN tree emits elif/else/except as SIBLINGS at same depth,
not nested under the parent. So computing NPATH(if/else) means looking at
adjacent siblings in the parent's child list.
```

**Step 1: Failing tests** — use the `npath` column from metric_fixtures.py expected values.

**Step 2: Implementation**

```python
"""NPATH Complexity metric (arch §1.3).

Walks the ControlFlowNode tree applying the recursive formula. CFN siblings
are multiplied (sequence of statements). IF/ELIF/ELSE and TRY/EXCEPT
relationships are recovered by looking at adjacent siblings in the parent's
child list — tree structure emits them flat, not nested.

KNOWN GAPS (metric_version=1.0.0):
- Condition NPATH (NPATH(c) in `if (c) S1`) approximated as 1 + 1·bool_group_count.
  Finer per-operator counting is deferred.
- Comprehension approximated as NPATH=3 (if/for hybrid) regardless of clause count.
- Lambda bodies are attributed to the enclosing function (see Slice 4a Known Gap #1).

No MAX_NPATH cap — Python ints are arbitrary precision. Slice 5 adds overflow
handling when BLOB persistence arrives.
"""

from __future__ import annotations

from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Confidence,
    InputKind,
    MetricValue,
)
from savviety_instinct.parse.types import ControlFlowNode, ControlFlowNodeKind


def _npath_of_node(node: ControlFlowNode, following: list[ControlFlowNode]) -> tuple[int, int]:
    """Compute NPATH contribution of a single CFN.

    Returns (npath_value, consumed_siblings) — how many siblings (including self)
    were absorbed. `following` is the list of nodes AFTER this one in the parent's
    children; used to look up elif/else/except siblings.
    """
    if node.kind == ControlFlowNodeKind.IF:
        body_npath = _npath_of_children(node.children)
        # Look for immediately-following ELIF/ELSE siblings.
        consumed = 1
        total = 1 + body_npath  # condition (1) + then body
        for sibling in following:
            if sibling.kind == ControlFlowNodeKind.ELIF:
                elif_body_npath = _npath_of_children(sibling.children)
                total += 1 + elif_body_npath  # +condition +body
                consumed += 1
            elif sibling.kind == ControlFlowNodeKind.ELSE:
                else_body_npath = _npath_of_children(sibling.children)
                total += else_body_npath  # else adds its body's paths
                consumed += 1
                break  # else terminates the chain
            else:
                break
        # If no else encountered, add the implicit +1 for the "no-branch-taken" path.
        has_else = any(
            s.kind == ControlFlowNodeKind.ELSE
            for s in following[: consumed - 1]
        )
        if not has_else:
            total += 1
        return total, consumed

    if node.kind in (ControlFlowNodeKind.ELIF, ControlFlowNodeKind.ELSE):
        # Shouldn't appear as a first-child — handled by IF's scan. Treat as body.
        return _npath_of_children(node.children), 1

    if node.kind == ControlFlowNodeKind.TRY:
        body_npath = _npath_of_children(node.children)
        consumed = 1
        total = body_npath
        # Following EXCEPT siblings each add their body's npath.
        for sibling in following:
            if sibling.kind == ControlFlowNodeKind.EXCEPT:
                total += _npath_of_children(sibling.children)
                consumed += 1
            else:
                break
        return total, consumed

    if node.kind == ControlFlowNodeKind.EXCEPT:
        # Handled by TRY's scan. Treat as body.
        return _npath_of_children(node.children), 1

    if node.kind in (ControlFlowNodeKind.FOR, ControlFlowNodeKind.WHILE):
        body_npath = _npath_of_children(node.children)
        return 1 + body_npath + 1, 1  # condition + body + no-iteration path

    if node.kind == ControlFlowNodeKind.TERNARY:
        return 3, 1

    if node.kind == ControlFlowNodeKind.BOOLEAN_SEQUENCE:
        return 2, 1  # +1 per group (Slice 4a approximation)

    if node.kind == ControlFlowNodeKind.COMPREHENSION:
        return 3, 1  # for + if approximation

    # Unknown kind — degrade to 1 so we don't crash.
    return 1, 1


def _npath_of_children(nodes: tuple[ControlFlowNode, ...]) -> int:
    """Multiply NPATHs of sibling CFNs, walking the list and consuming chains."""
    if not nodes:
        return 1  # pure straight-line code
    result = 1
    i = 0
    lst = list(nodes)
    while i < len(lst):
        following = lst[i + 1 :]
        npath, consumed = _npath_of_node(lst[i], following)
        result *= npath
        i += consumed
    return result


class NPathMetric:
    id: str = "npath"
    version: str = "1.0.0"
    applies_to: frozenset[ArtifactKind] = frozenset({ArtifactKind.FUNCTION})
    required_inputs: frozenset[InputKind] = frozenset({InputKind.AST})

    def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue:
        if context.parse_result is None:
            raise ValueError(f"{self.id} requires AnalysisContext.parse_result")
        for fn in context.parse_result.functions:
            if fn.ast_hash == artifact.ast_hash:
                value = _npath_of_children(fn.control_flow)
                return MetricValue(
                    metric_id=self.id,
                    value=value,
                    metric_version=self.version,
                    confidence=Confidence.HIGH,
                )
        raise LookupError(f"No function with ast_hash={artifact.ast_hash!r} in parse_result")


NPATH_METRIC = NPathMetric()
```

**Note:** the `has_else` check in the IF branch has a bug — it searches `following[: consumed - 1]` but `consumed` was already counted inside the loop. Re-verify at test time. Rewrite if needed — the fixture ground-truth will catch off-by-one.

**Step 2–5:** tests, register, commit similarly to Task 3. Parametrized against npath column in metric_fixtures.

Commit message:

```
feat(analyze): npath metric (recursive path-product, approximated)

Per arch §1.3. Approximations documented in module docstring: condition
npath simplified (no per-operator count), comprehension treated as
single hybrid, no MAX_NPATH cap (Slice 5 adds overflow handling).
Lambda internals attributed to enclosing function (Slice 4a Gap #1).
```

---

## Task 5: `identifier_quality` heuristic metric

**Files:**
- Create: `src/savviety_instinct/analyze/metrics/identifier_quality.py`
- Create: `tests/test_analyze_metric_identifier_quality.py`
- Modify: `src/savviety_instinct/analyze/metrics/__init__.py`

**Heuristic (Scope Decision #5):**
- `STOPWORDS = {"i", "j", "k", "x", "y", "z", "tmp", "foo", "bar", "baz"}`
- Meaningful: `len(identifier) >= 3 AND identifier not in STOPWORDS`
- Quality: `len(unique_meaningful) / max(len(unique_all), 1)`
- Confidence: `LOW` (per arch §4.1)

**Step 1: Failing tests** — parametrize against identifier_quality column. Use `pytest.approx()` for float comparison.

**Step 2: Implementation**

```python
"""Identifier Quality heuristic metric (arch §4.1).

R1 heuristic; LLM-augmented refinement is R2 (arch §4.1 release note).
Combines the function's own name, parameter names, and body identifier
occurrences into a single set; counts how many are "meaningful" per a
simple length + stopword heuristic.

Confidence: LOW (per §4.1 "heuristic, low confidence").

KNOWN GAPS (metric_version=1.0.0):
- Context-aware exemption (e.g., 'x' meaningful in math context) not implemented.
- Idiomatic short names (`n`, `m`) not distinguished from poor names.
- Occurrence frequency ignored; distinct names only.
"""

from __future__ import annotations

from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Confidence,
    InputKind,
    MetricValue,
)


# Stopword list locked for Slice 4a; Scope Decision #5 in the plan.
STOPWORDS: frozenset[str] = frozenset(
    {"i", "j", "k", "x", "y", "z", "tmp", "foo", "bar", "baz"}
)


def _is_meaningful(identifier: str) -> bool:
    return len(identifier) >= 3 and identifier not in STOPWORDS


class IdentifierQualityMetric:
    id: str = "identifier_quality"
    version: str = "1.0.0"
    applies_to: frozenset[ArtifactKind] = frozenset({ArtifactKind.FUNCTION})
    required_inputs: frozenset[InputKind] = frozenset({InputKind.AST})

    def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue:
        if context.parse_result is None:
            raise ValueError(f"{self.id} requires AnalysisContext.parse_result")
        for fn in context.parse_result.functions:
            if fn.ast_hash == artifact.ast_hash:
                all_identifiers = (
                    {fn.name}
                    | set(fn.parameter_names)
                    | set(fn.identifier_names)
                )
                meaningful = {i for i in all_identifiers if _is_meaningful(i)}
                quality = len(meaningful) / max(len(all_identifiers), 1)
                return MetricValue(
                    metric_id=self.id,
                    value=quality,
                    metric_version=self.version,
                    confidence=Confidence.LOW,
                )
        raise LookupError(f"No function with ast_hash={artifact.ast_hash!r} in parse_result")


IDENTIFIER_QUALITY_METRIC = IdentifierQualityMetric()
```

**Step 3+:** register, test (with `pytest.approx` for floats), commit.

---

## Task 6: Register in `analyze/__init__.py`'s `METRICS_REGISTRY`

**Files:**
- Modify: `src/savviety_instinct/analyze/__init__.py`

Add the three new metrics to `METRICS_REGISTRY` tuple. Order: the existing three first (statement_count, cyclomatic, cognitive), then max_nesting_depth, npath, identifier_quality. Deterministic CLI output relies on this order.

```python
METRICS_REGISTRY = (
    STATEMENT_COUNT_METRIC,
    CYCLOMATIC_METRIC,
    COGNITIVE_METRIC,
    MAX_NESTING_DEPTH_METRIC,
    NPATH_METRIC,
    IDENTIFIER_QUALITY_METRIC,
)
```

Add imports + `__all__` entries. Commit separately (small, surgical).

---

## Task 7: Integration test

**Files:**
- Create: `tests/integration/test_slice4a_metrics.py`

Verify that `instinct run tests/fixtures/python/metric_fixtures.py` now produces 60 rows (10 functions × 6 metrics). Spot-check a few new-metric values end-to-end.

```python
def test_cli_emits_six_metrics_per_function(tmp_path, monkeypatch) -> None:
    _write_config(tmp_path / ".instinct")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["run", str(FIXTURES / "metric_fixtures.py")],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    rows = [l.split("\t") for l in result.output.splitlines() if "\t" in l]
    assert len(rows) == 60  # 10 functions × 6 metrics

    # All expected metric IDs present.
    metric_ids = {r[2].split("=")[0] for r in rows}
    assert metric_ids == {
        "statement_count",
        "cyclomatic_complexity",
        "cognitive_complexity",
        "max_nesting_depth",
        "npath",
        "identifier_quality",
    }
```

---

## Task 8: Lint sweep + self-dogfood + PR

```bash
uv run pytest --cov=src/savviety_instinct
uv run pre-commit run --all-files
uv run instinct run src/savviety_instinct/analyze/ 2>&1 | head -20
git push -u origin slice-4a-function-metrics
gh pr create ...
```

PR title: `Slice 4a: function-level metrics (max_nesting_depth, npath, identifier_quality)`

---

## Self-Review

**Spec coverage (against arch §1.3, §1.4, §4.1):**
- [x] `max_nesting_depth` → Task 3
- [x] `npath` → Task 4 with overflow/approximation gaps documented
- [x] `identifier_quality` heuristic → Task 5 with explicit stopword list + LOW confidence

**Layering:** `analyze/` imports `parse.types.ControlFlowNodeKind` (data type, fine). `parse/python.py` gains one helper; no new tree-sitter exports leak through.

**Approximations documented:** NPATH condition simplification, comprehension simplification, lambda attribution, context-blind stopword. All four flagged with `KNOWN GAP (metric_version=1.0.0)` in respective module docstrings.

**Determinism:** `identifier_names` is order-preserving tuple. Metric uses `set()` for dedupe — sets iterate unsorted but `len()` is deterministic. Quality score stable across runs.

---

## Execution Handoff

**1. Subagent-Driven (recommended)** — 8 tasks, each 1–2 files, similar shape to Slice 3. Good for per-task review.

**2. Inline Execution** — Smaller slice; could fit in one session without subagents.

Subagent-Driven matches the Slice 3 rhythm.
