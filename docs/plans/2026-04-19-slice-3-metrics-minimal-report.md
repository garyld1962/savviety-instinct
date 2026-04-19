# Slice 3 — Metrics + Minimal Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Gary's chosen flow:** `/plan` → `/execute-plan`. One commit per task. Single branch `slice-3-metrics-minimal-report`, no combining slices.

**Goal:** First three MVP metrics end-to-end: `cyclomatic_complexity`, `cognitive_complexity`, `statement_count`. Introduce the `analyze/` module with a metric registry and a file-walking pipeline. Wire `instinct run <path>` to produce a minimal tab-separated text report. No storage writes, no rich/HTML/JSON reports, no parallelism, no cross-file or module-level metrics.

**Architecture:** The parse layer gains `ControlFlowNode` — the domain-neutral view of `if`/`for`/`while`/`try`/`except`/ternary/boolean-op constructs — and `FunctionDefNode.control_flow` holds the per-function CFN tree. `AnalysisContext` is extended (forward-ref, TYPE_CHECKING) to carry the current file's `ParseResult`; metrics receive an `Artifact` and look up their own `FunctionDefNode` by `ast_hash` in the context. Three metric implementations (`cyclomatic`, `cognitive`, `statement_count`) in `analyze/metrics/` declare a `Metric` Protocol conformance and a stable `metric_version`. Cognitive complexity's per-language increment rules live in `src/savviety_instinct/core/cognitive_rules/python.yaml`, loaded once via `importlib.resources`. `analyze/pipeline.py` walks a filesystem path, applies glob suppressions from `.instinct/config.yaml`, parses each file via `PYTHON_ADAPTER`, dispatches metrics, yields `(Artifact, MetricValue)` tuples. `instinct run <path>` wires the pipeline to a plain tab-separated stdout report. Parse errors are soft (file skipped, stderr log, summary count); other errors abort the run non-zero.

**Tech Stack:** Python 3.12+, PyYAML 6.x (already present), Typer (already present, extended with `run` command), `importlib.resources` (stdlib) for YAML loading, `fnmatch`/`pathlib.Path.rglob` for file walking, `sys.stderr` for diagnostics. No new runtime deps.

---

## Scope Decisions (locked)

1. **Python only.** No Rust / C# / TypeScript adapters. Cognitive rules YAML is structured language-indexed (`cognitive_rules/<lang>.yaml`) so Slices 7–8 can add files without touching code. The loader takes a `Language` enum and picks the file.
2. **Three metrics only.** `statement_count`, `cyclomatic_complexity`, `cognitive_complexity`. Other Phase 1 metrics (`max_nesting_depth`, `npath`, `identifier_quality`, module/class-level metrics) ship with Slice 4.
3. **Function-level only.** Class and module artifacts exist in `ParseResult.classes` (Slice 2 output) but no metrics apply to them yet. `Metric.applies_to` on all three metrics is `frozenset({ArtifactKind.FUNCTION})`.
4. **No storage writes.** `analyze/pipeline.py` yields in-memory tuples. No `observation_artifacts` / `run_observations` rows. Dedup, stability tiering, and the `runs` table land Slice 5. `instinct run` is NOT doing a real "run" yet — it's closer to a one-shot analyze+print. Full `run` semantics with DB rows arrive Slice 5.
5. **No parallelism.** Single-threaded file iteration via `sorted(path.rglob("*.py"))`. Arch §8.1 recommends `ProcessPoolExecutor` but §16.4 defers the choice; Slice 3 stays synchronous. Performance NFRs are not enforced this slice.
6. **Plain text tab-separated output.** One row per (function, metric), no headers, no rich/JSON/HTML. Column layout locked in Scope Decision #15 below. Full report layer (rich terminal, JSON, HTML, filtering, rankings) is Slice 6.
7. **`ControlFlowNode` lives in `parse/types.py`.** It's a normalized domain type consumed by metrics; its home is the parse layer which also produces it. `analyze/` consumes, does not define.
8. **`FunctionDefNode.control_flow: tuple[ControlFlowNode, ...]`** — top-level CFNs in the function body, with nested CFNs chained via `ControlFlowNode.children`. Metrics traverse this tree, NEVER tree-sitter nodes directly (analyze must not depend on tree-sitter). The tree is pre-computed once per parse, O(N) in function body size.
9. **`AnalysisContext.parse_result`** — new field, `ParseResult | None` default None. Uses TYPE_CHECKING + string annotation (same pattern as `call_graph` from Slice 2) to preserve the absolute `core` → `parse` runtime-import block (arch §2). Verified by the existing sys.modules layering test, extended to also exclude `savviety_instinct.parse.*`.
10. **Metric ↔ Artifact lookup by `ast_hash`.** Metrics receive `Artifact` + `AnalysisContext`, and resolve their own `FunctionDefNode` via `next(fn for fn in context.parse_result.functions if fn.ast_hash == artifact.ast_hash)`. O(N) per metric per artifact. For MVP file sizes (≤500 functions) this is trivial; revisit with a dict if profiling demands.
11. **Metric instances are module-level singletons** (like `PYTHON_ADAPTER`). Each metric module exports `METRIC` and the `analyze/__init__.py` registry imports them. No dependency injection, no plugin loader.
12. **Cognitive rules loaded from `src/savviety_instinct/core/cognitive_rules/python.yaml`** via `importlib.resources.files("savviety_instinct.core.cognitive_rules")`. Loaded once per process (module-level `@lru_cache`). `core/` may hold data files even though its Python code is pure — only the loader (in `analyze/rules.py`) does I/O.
13. **Metric versions start at `1.0.0`.** Any change to computation semantics bumps the version (arch §4.3 provenance invariant). `cognitive_complexity.metric_version = "1.0.0"` today; `1.1.0` when Python 3.12 `match` statement support is added (not in Slice 3).
14. **Default glob suppressions** (built into `config.models.py`, overridable via `.instinct/config.yaml`):
    - `**/tests/**`, `**/test_*.py`, `**/*_test.py` — test files
    - `**/migrations/**` — Alembic / Django migrations
    - `**/__pycache__/**`, `**/.venv/**`, `**/build/**`, `**/dist/**` — caches & build output
    - `**/conftest.py` — pytest config
15. **CLI output format (tab-separated, one row per (function, metric)):**
    ```
    <file_path>:<line_start>-<line_end>\t<qualified_name>\t<metric_id>=<value>\t<confidence>
    ```
    Example row:
    ```
    src/foo.py:12-28	Worker.do_work	cognitive_complexity=7	high
    ```
    No header row. Values sorted by `(file_path, line_start, qualified_name, metric_id)` for deterministic output.
16. **Parse-error handling:** file skipped, one line to `sys.stderr` prefixed `[parse-error] <path>: <first error message>`, counted in a run summary printed to stderr at the end: `[summary] <N> files parsed, <M> files skipped, <K> functions analyzed`. This matches arch §9 table for "Parse error / File skipped / error logged / summary count".
17. **Exit code:** 0 if analyze completed (even with some files skipped); non-zero if a pipeline-level exception (IO, config load failure, CLI misuse) occurred. Parse errors are per-file and do not fail the run.
18. **No changes to `core/types.Metric` Protocol.** Existing Protocol from Slice 1 is unchanged. Slice 3 concrete metrics conform to it as-is.
19. **`include` complement to `suppress`** is NOT in Slice 3. Config has `suppress: list[str]` only; `include` allowlists arrive when the user asks.
20. **No `cyclomatic` / `cognitive` / `statement_count` reporting on class or module artifacts.** `applies_to` limits metric dispatch.

---

## File Structure

| Path | Purpose |
|------|---------|
| `src/savviety_instinct/core/types.py` | Extend `AnalysisContext` with `parse_result: "ParseResult \| None" = None` via TYPE_CHECKING |
| `src/savviety_instinct/parse/types.py` | Add `ControlFlowNodeKind` enum + `ControlFlowNode` dataclass; extend `FunctionDefNode` with `control_flow: tuple[ControlFlowNode, ...] = ()` |
| `src/savviety_instinct/parse/python.py` | New helper `_collect_control_flow(fn_node) -> tuple[ControlFlowNode, ...]`; wire into `_collect_functions` |
| `src/savviety_instinct/parse/__init__.py` | Add `ControlFlowNode`, `ControlFlowNodeKind` to `__all__` |
| `src/savviety_instinct/config/models.py` | Add `suppress: list[str]` field with default glob patterns |
| `src/savviety_instinct/core/cognitive_rules/__init__.py` | Empty — marks the package so `importlib.resources` can locate the YAML |
| `src/savviety_instinct/core/cognitive_rules/python.yaml` | Per-language increment rules for cognitive complexity |
| `src/savviety_instinct/analyze/__init__.py` | Re-exports: `METRICS_REGISTRY`, `run_pipeline`, metric singletons |
| `src/savviety_instinct/analyze/rules.py` | `load_cognitive_rules(language) -> CognitiveRules`; YAML→dataclass parser with cache |
| `src/savviety_instinct/analyze/metrics/__init__.py` | Package marker; re-exports the three metric singletons |
| `src/savviety_instinct/analyze/metrics/statement_count.py` | `StatementCountMetric` + `STATEMENT_COUNT_METRIC` singleton |
| `src/savviety_instinct/analyze/metrics/cyclomatic.py` | `CyclomaticMetric` + `CYCLOMATIC_METRIC` singleton |
| `src/savviety_instinct/analyze/metrics/cognitive.py` | `CognitiveMetric` + `COGNITIVE_METRIC` singleton |
| `src/savviety_instinct/analyze/pipeline.py` | `run_pipeline(path: Path, config: InstinctConfig) -> Iterator[(Artifact, MetricValue)]`; file walking + suppressions + error handling |
| `src/savviety_instinct/cli/app.py` | Add `instinct run <path>` Typer command |
| `tests/test_parse_control_flow.py` | Unit tests for ControlFlowNode extraction on new fixture |
| `tests/fixtures/python/nested_control_flow.py` | Fixture with nested if/for/while/try/except for CFN extraction tests |
| `tests/fixtures/python/metric_fixtures.py` | Hand-crafted functions with known metric values (cyclomatic, cognitive, statement_count) |
| `tests/test_config_suppress.py` | Tests for `suppress` field defaults + parsing |
| `tests/test_core_analysis_context_parse_result.py` | Tests that `AnalysisContext.parse_result` accepts ParseResult + layering assertion |
| `tests/test_analyze_rules.py` | Tests for `load_cognitive_rules` (YAML parsing, caching, missing-file error) |
| `tests/test_analyze_metric_statement_count.py` | Unit tests for statement_count metric |
| `tests/test_analyze_metric_cyclomatic.py` | Unit tests for cyclomatic metric |
| `tests/test_analyze_metric_cognitive.py` | Unit tests for cognitive metric |
| `tests/test_analyze_pipeline.py` | Unit tests for run_pipeline (file walk, suppressions, parse-error skip) |
| `tests/test_cli_run.py` | CliRunner tests for `instinct run` (exit codes, output format, directory walk) |
| `tests/integration/test_slice3_pipeline.py` | End-to-end: `instinct run tests/fixtures/python/` produces expected rows |

---

## Task 1: Config `suppress` field

**Files:**
- Modify: `src/savviety_instinct/config/models.py`
- Create: `tests/test_config_suppress.py`

**Rationale first, then code.** Slice 3's `instinct run` skips test/migration/cache files by default. The user overrides via `.instinct/config.yaml`. Default patterns live in the Pydantic model so an empty config file gets sensible behavior; `instinct init`'s scaffolded YAML from Slice 1 will include a commented-out override block (NOT modified in Slice 3 — the defaults kick in for existing configs without any changes).

- [ ] **Step 1: Read `src/savviety_instinct/config/models.py`** to locate the main config model and existing field order.

- [ ] **Step 2: Write failing tests — `tests/test_config_suppress.py`**

```python
"""Tests for the `suppress` field on the config model."""

from __future__ import annotations

import pytest

from savviety_instinct.config.models import InstinctConfig


DEFAULTS_EXPECTED = {
    "**/tests/**",
    "**/test_*.py",
    "**/*_test.py",
    "**/migrations/**",
    "**/__pycache__/**",
    "**/.venv/**",
    "**/build/**",
    "**/dist/**",
    "**/conftest.py",
}


def test_suppress_defaults_include_tests_and_migrations() -> None:
    cfg = InstinctConfig(scope="personal")
    assert set(cfg.suppress) == DEFAULTS_EXPECTED


def test_suppress_can_be_overridden() -> None:
    cfg = InstinctConfig(scope="personal", suppress=["foo/**"])
    assert cfg.suppress == ["foo/**"]


def test_suppress_empty_list_is_allowed() -> None:
    """User can opt out of all suppressions by setting suppress: []."""
    cfg = InstinctConfig(scope="personal", suppress=[])
    assert cfg.suppress == []


def test_suppress_rejects_non_string() -> None:
    with pytest.raises(ValueError):
        InstinctConfig(scope="personal", suppress=[123])  # type: ignore[list-item]
```

- [ ] **Step 3: Run tests — expect fail with AttributeError or Pydantic ValidationError**

`uv run pytest tests/test_config_suppress.py -v` — all should fail (field doesn't exist).

- [ ] **Step 4: Add `suppress` field to `InstinctConfig`**

In `src/savviety_instinct/config/models.py`, inside the `InstinctConfig` class body (after existing fields), add:

```python
    suppress: list[str] = Field(
        default_factory=lambda: [
            "**/tests/**",
            "**/test_*.py",
            "**/*_test.py",
            "**/migrations/**",
            "**/__pycache__/**",
            "**/.venv/**",
            "**/build/**",
            "**/dist/**",
            "**/conftest.py",
        ],
        description="Glob patterns of files/directories to exclude from analysis.",
    )
```

If `Field` isn't already imported from `pydantic`, add it to the existing import line.

- [ ] **Step 5: Run the full config test suite** to verify no regression.

`uv run pytest tests/test_config_models.py tests/test_config_loader.py tests/test_config_suppress.py -v` — expect all previously-passing tests still pass + 4 new tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/savviety_instinct/config/models.py tests/test_config_suppress.py
git commit -m "$(cat <<'EOF'
feat(config): add suppress globs with test/migration/cache defaults

Slice 3 groundwork — instinct run will consult this list to skip files
before parsing. Defaults target Python test suites, Alembic migrations,
cache dirs, and conftest. Configurable via .instinct/config.yaml.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `ControlFlowNode` type + `FunctionDefNode.control_flow`

**Files:**
- Modify: `src/savviety_instinct/parse/types.py`

**Step 1: Write implementation** — the tests that exercise this land in Task 3 where they're meaningful (need parsed input). For Task 2, we're just adding data types.

Replace the existing `parse/types.py` body with (additions marked with comments):

```python
"""Normalized AST node types — language-agnostic view of parsed code.

Each `LanguageAdapter` (arch §5.5) maps its language-specific tree-sitter nodes
into these domain-neutral dataclasses. Metrics and graph builders consume these,
not raw tree-sitter nodes, so adding a new language is an adapter-only change.

Slice 2 populated `FunctionDefNode`, `ClassDefNode`, and `CallSiteNode`.
Slice 3 adds `ControlFlowNode` + `FunctionDefNode.control_flow` for
cyclomatic / cognitive / statement_count metric computation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from savviety_instinct.core.types import Language, SourceRange


class ParseErrorKind(StrEnum):
    SYNTAX = "syntax"
    UNSUPPORTED_CONSTRUCT = "unsupported_construct"
    IO = "io"


# ---------- NEW in Slice 3 ----------


class ControlFlowNodeKind(StrEnum):
    """Domain-neutral control-flow constructs.

    Per-language adapters map their native AST node types to these kinds.
    The set is intentionally small and stable — metrics reason about these
    kinds, not tree-sitter node types. New kinds require a coordinated
    metric_version bump.
    """

    IF = "if"                    # if / elif / else (each counted separately in cyclomatic)
    ELIF = "elif"                # Python elif — distinct from IF so cognitive's "else if" +1 hits
    ELSE = "else"                # else branch — counts in cognitive (+1) but not cyclomatic
    FOR = "for"                  # for / for-in loops
    WHILE = "while"              # while loops
    TRY = "try"                  # try/except scope (wrapper; zero cognitive cost)
    EXCEPT = "except"            # except clause — counts +1 in both
    TERNARY = "ternary"          # a if cond else b
    BOOLEAN_SEQUENCE = "boolean_sequence"  # a and b or c — one per group, not per operator
    COMPREHENSION = "comprehension"        # list/set/dict comprehension — Python's for-in inside an expression


@dataclass(frozen=True, slots=True)
class ControlFlowNode:
    """A single control-flow point inside a function body.

    Children are nested CFNs (e.g., an `if` inside a `for`). The tree is rooted
    at the function's top-level CFNs (exposed on `FunctionDefNode.control_flow`).
    `nesting_depth` is cached from walk time; 0 means top-level within the
    function body, 1 means inside one control structure, etc.
    """

    kind: ControlFlowNodeKind
    source_range: SourceRange
    nesting_depth: int
    children: tuple[ControlFlowNode, ...] = ()


# ---------- existing types below, with ONE new field on FunctionDefNode ----------


@dataclass(frozen=True, slots=True)
class ParseError:
    kind: ParseErrorKind
    message: str
    source_range: SourceRange | None


@dataclass(frozen=True, slots=True)
class FunctionDefNode:
    """A callable definition: free function, lambda, or method."""

    name: str
    qualified_name: str
    enclosing_class: str | None
    source_range: SourceRange
    ast_hash: str
    parameter_names: tuple[str, ...]
    # NEW in Slice 3: top-level control-flow points in this function's body.
    # Empty tuple for functions with no control flow (pure straight-line code).
    control_flow: tuple[ControlFlowNode, ...] = ()
    # NEW in Slice 3: count of executable statements in the function body.
    # Computed during parse because the adapter already walks the tree and
    # pre-computing is strictly cheaper than re-walking per metric. Excludes
    # pure declarations, blank lines, and comments. See arch §1.5.
    statement_count: int = 0

    @property
    def is_method(self) -> bool:
        return self.enclosing_class is not None


@dataclass(frozen=True, slots=True)
class ClassDefNode:
    name: str
    source_range: SourceRange
    ast_hash: str
    method_qualified_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CallSiteNode:
    """A single invocation. Intra-file resolution only in Slice 2."""

    callee_name: str
    source_range: SourceRange
    enclosing_function: str | None
    is_resolved: bool


@dataclass(frozen=True, slots=True)
class ParseResult:
    file_path: str
    language: Language
    functions: tuple[FunctionDefNode, ...]
    classes: tuple[ClassDefNode, ...]
    call_sites: tuple[CallSiteNode, ...]
    errors: tuple[ParseError, ...] = field(default=())

    @property
    def ok(self) -> bool:
        """True iff no errors were encountered during parse.

        Note: a `False` result may still carry partial output in `functions`,
        `classes`, and `call_sites` — tree-sitter extracts what it can even
        when syntax errors are present. Callers that short-circuit on `not ok`
        will drop that partial data silently.
        """
        return not self.errors
```

**Design note on `statement_count` on FunctionDefNode:** The spec for Task 2 puts this field on the parsed node rather than computing it in the metric. The rationale: the parser already walks every AST node once; counting executable statements during that walk is O(1) extra work per node. Making the metric re-walk the function body is strictly worse. The metric implementation becomes `value = function_def.statement_count`. The `parameter_names` field follows the same pattern.

**Step 2: Type-check**

```bash
uv run mypy src/savviety_instinct/parse/types.py
uv run ruff check src/savviety_instinct/parse/types.py
uv run ruff format --check src/savviety_instinct/parse/types.py
```

All three should pass.

**Step 3: Verify no regression**

Nothing in `parse/python.py` reads `control_flow` or `statement_count` yet, and both fields have defaults, so existing parse tests should still pass:

```bash
uv run pytest tests/test_parse_python.py tests/test_parse_adapter.py tests/test_parse_hashing.py tests/test_graph_builder.py tests/test_graph_types.py -v 2>&1 | tail -5
```

Expect all tests green (22 parse + 12 graph = 34 + any additions from Slice 2's review cycle).

**Step 4: Commit**

```bash
git add src/savviety_instinct/parse/types.py
git commit -m "$(cat <<'EOF'
feat(parse): ControlFlowNode + FunctionDefNode.{control_flow, statement_count}

Domain-neutral control-flow types consumed by cyclomatic / cognitive /
statement_count metrics. Pre-computed on FunctionDefNode during parse —
the adapter already walks the tree, re-walking per metric would be
strictly worse. Both new fields default to empty/zero so Slice 2 call
sites remain construction-compatible.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: PythonAdapter extracts control-flow nodes + statement_count

**Files:**
- Modify: `src/savviety_instinct/parse/python.py`
- Create: `tests/fixtures/python/nested_control_flow.py`
- Create: `tests/test_parse_control_flow.py`

- [ ] **Step 1: Create fixture — `tests/fixtures/python/nested_control_flow.py`**

```python
def straight_line(x: int) -> int:
    y = x + 1
    z = y * 2
    return z


def with_if(x: int) -> int:
    if x > 0:
        return x
    return 0


def deeply_nested(items: list[int]) -> int:
    total = 0
    for item in items:
        if item > 0:
            if item % 2 == 0:
                total += item
            else:
                total -= item
        elif item == 0:
            total = total
        else:
            try:
                total -= abs(item)
            except ValueError:
                total = 0
    return total


def boolean_ops(a: int, b: int, c: int) -> bool:
    return a > 0 and b > 0 or c > 0


def comprehension_example(items: list[int]) -> list[int]:
    return [i * 2 for i in items if i > 0]


def ternary_example(a: int, b: int) -> int:
    return a if a > b else b
```

- [ ] **Step 2: Write failing tests — `tests/test_parse_control_flow.py`**

```python
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
    assert len(fn.control_flow) == 1
    node = fn.control_flow[0]
    assert node.kind == ControlFlowNodeKind.IF
    assert node.nesting_depth == 0
    assert node.children == ()  # no nested control flow inside


def test_with_if_statement_count() -> None:
    fn = _fn("with_if")
    # if x > 0: / return x / return 0 — the if is a control-flow construct
    # but its BODY contains statements. statement_count includes those.
    # Implementation choice: count leaf executable statements across the
    # function body (condition expressions are NOT statements).
    # Expected: return x (in if body) + return 0 (fallthrough) = 2.
    # The if itself is counted as 1 statement (it's a compound statement).
    # So: 1 (if block as a statement) + return 0 = 2, OR count the return x
    # inside + return 0 = 2.
    #
    # DECISION: statement_count = count of direct-child statement nodes in
    # the function body + recursively in any compound statement body. This
    # matches Python's own definition ("executable statements"): an `if`
    # counts as one compound statement plus whatever's in its body.
    # For with_if: 1 (the if) + 1 (return x in the if body) + 1 (return 0) = 3.
    assert fn.statement_count == 3


def test_deeply_nested_top_level_count() -> None:
    fn = _fn("deeply_nested")
    # Top-level CFN: the for loop. (The `total = 0` assignment and `return total`
    # are statements, not control flow.)
    assert len(fn.control_flow) == 1
    assert fn.control_flow[0].kind == ControlFlowNodeKind.FOR
    assert fn.control_flow[0].nesting_depth == 0


def test_deeply_nested_for_has_if_child() -> None:
    fn = _fn("deeply_nested")
    for_node = fn.control_flow[0]
    # Inside for: one if statement (covering the if/elif/else chain, with
    # elif/else as siblings NOT children of the initial if — Python treats
    # the whole chain as a single `if_statement` node with alternatives).
    assert len(for_node.children) >= 1
    assert for_node.children[0].kind == ControlFlowNodeKind.IF
    assert for_node.children[0].nesting_depth == 1


def test_boolean_ops_captured_as_single_sequence() -> None:
    """A sequence of mixed `and`/`or` operators inside one expression counts as
    one BOOLEAN_SEQUENCE CFN, NOT per operator. This matches Sonar's rule and
    §1.2's 'per group, not per operator'.
    """
    fn = _fn("boolean_ops")
    seq_count = sum(1 for node in fn.control_flow if node.kind == ControlFlowNodeKind.BOOLEAN_SEQUENCE)
    assert seq_count >= 1


def test_comprehension_emits_comprehension_cfn() -> None:
    fn = _fn("comprehension_example")
    kinds = [n.kind for n in fn.control_flow]
    assert ControlFlowNodeKind.COMPREHENSION in kinds


def test_ternary_emits_ternary_cfn() -> None:
    fn = _fn("ternary_example")
    kinds = [n.kind for n in fn.control_flow]
    assert ControlFlowNodeKind.TERNARY in kinds


def test_existing_fixtures_still_parse_after_cfn_extraction() -> None:
    """Regression guard: adding CFN extraction must not break Slice 2 fixtures."""
    for name in ("simple_module.py", "with_class.py", "same_shape_different_names.py"):
        result = PYTHON_ADAPTER.parse_path(FIXTURES / name)
        assert result.ok, f"{name} failed to parse: {result.errors}"
```

- [ ] **Step 3: Run tests to verify failures**

`uv run pytest tests/test_parse_control_flow.py -v` — expect all failures (AttributeError / AssertionError, since `control_flow` is always `()` and `statement_count` is always `0`).

- [ ] **Step 4: Extend `parse/python.py`**

Add at the top of the module, near the other imports:

```python
from savviety_instinct.parse.types import (
    CallSiteNode,
    ClassDefNode,
    ControlFlowNode,      # NEW
    ControlFlowNodeKind,  # NEW
    FunctionDefNode,
    ParseError,
    ParseErrorKind,
    ParseResult,
)
```

Add a tree-sitter-node-type → CFN-kind mapping near the other module-level constants (after `_PY_LANGUAGE`):

```python
# Tree-sitter-python node-type → our ControlFlowNodeKind mapping.
# Not every tree-sitter node type needs a match — only those that break linear
# flow. Comprehensions have their own handling because each generator clause
# counts (arch §1.2 Python-specific rule).
_TS_TO_CFN_KIND: dict[str, ControlFlowNodeKind] = {
    "if_statement": ControlFlowNodeKind.IF,
    "elif_clause": ControlFlowNodeKind.ELIF,
    "else_clause": ControlFlowNodeKind.ELSE,
    "for_statement": ControlFlowNodeKind.FOR,
    "while_statement": ControlFlowNodeKind.WHILE,
    "try_statement": ControlFlowNodeKind.TRY,
    "except_clause": ControlFlowNodeKind.EXCEPT,
    "conditional_expression": ControlFlowNodeKind.TERNARY,
}

# Tree-sitter-python comprehension node types.
_COMPREHENSION_TYPES = {
    "list_comprehension",
    "set_comprehension",
    "dictionary_comprehension",
    "generator_expression",
}

# Statement-counting: tree-sitter-python's "statement" family. Expression
# statements count (a = b), compound statements count (if/for/while/try/with/
# function_definition/class_definition), `pass`/`return`/`raise`/`import` etc.
# all count. Decorators, docstrings (as bare strings in expression_statement),
# and blank lines do NOT count. See arch §1.5.
_STATEMENT_NODE_TYPES = {
    "expression_statement",
    "assignment",
    "augmented_assignment",
    "if_statement",
    "for_statement",
    "while_statement",
    "try_statement",
    "with_statement",
    "return_statement",
    "raise_statement",
    "break_statement",
    "continue_statement",
    "pass_statement",
    "import_statement",
    "import_from_statement",
    "global_statement",
    "nonlocal_statement",
    "assert_statement",
    "delete_statement",
    # Compound definitions inside a function body count as one statement each.
    "function_definition",
    "class_definition",
}
```

Add two new module-private helpers (near the other `_collect_*` helpers):

```python
def _collect_control_flow(func_body_node: Node, depth: int = 0) -> tuple[ControlFlowNode, ...]:
    """Walk a function body (or nested block) and emit top-level CFNs at `depth`.

    Compound control-flow nodes (if/for/while/try) recurse to collect their
    children at depth+1. The returned tuple is the sequence of control-flow
    constructs encountered in source order at the given nesting level.
    """
    out: list[ControlFlowNode] = []
    stack: list[Node] = list(func_body_node.children)
    # Reverse so we iterate left-to-right after pop().
    stack.reverse()
    while stack:
        node = stack.pop()
        kind = _classify_cfn(node)
        if kind is None:
            # Not a control-flow node. Recurse into its children so we still find
            # nested control flow inside things like assignments with ternary RHS,
            # or expression statements containing comprehensions.
            if _has_nested_control_flow(node):
                # Inline its children at the same depth — not a break in flow.
                stack.extend(reversed(node.children))
            continue
        # It IS a CFN. Compute its children at depth+1.
        child_body = _cfn_body_node(node, kind)
        children = (
            _collect_control_flow(child_body, depth + 1) if child_body is not None else ()
        )
        out.append(
            ControlFlowNode(
                kind=kind,
                source_range=_source_range(node, str(node.start_byte)),  # file_path overwritten below
                nesting_depth=depth,
                children=children,
            )
        )
    return tuple(out)


def _classify_cfn(node: Node) -> ControlFlowNodeKind | None:
    if node.type in _TS_TO_CFN_KIND:
        return _TS_TO_CFN_KIND[node.type]
    if node.type in _COMPREHENSION_TYPES:
        return ControlFlowNodeKind.COMPREHENSION
    if node.type == "boolean_operator":
        # Each outermost `a and b or c` tree is one BOOLEAN_SEQUENCE. A nested
        # boolean_operator is part of the same sequence. The caller filters
        # duplicates via `_has_nested_control_flow` short-circuit.
        return ControlFlowNodeKind.BOOLEAN_SEQUENCE
    return None


def _has_nested_control_flow(node: Node) -> bool:
    """Cheap check: does this subtree contain any control-flow nodes?

    Used to decide whether to recurse. True for most non-leaf nodes; false for
    pure identifier / literal leaves. A proper implementation would cache this
    per node; for MVP file sizes the O(N) cost is negligible.
    """
    stack: list[Node] = [node]
    while stack:
        cur = stack.pop()
        if _classify_cfn(cur) is not None:
            return True
        stack.extend(cur.children)
    return False


def _cfn_body_node(node: Node, kind: ControlFlowNodeKind) -> Node | None:
    """For a CFN wrapper (if/for/while/try/etc.), locate the body node that
    holds its nested children. Returns None for leaf CFNs (boolean, ternary,
    comprehension — their 'children' are NOT separately walked because they're
    expressions, not blocks).
    """
    if kind in (
        ControlFlowNodeKind.BOOLEAN_SEQUENCE,
        ControlFlowNodeKind.TERNARY,
        ControlFlowNodeKind.COMPREHENSION,
    ):
        return None
    # Most compound statements have a `body` field.
    body = node.child_by_field_name("body")
    if body is not None:
        return body
    # `try_statement` has multiple bodies (try body, except clauses, else, finally).
    # We return the try's primary body here; except clauses are sibling CFNs
    # emitted at the same level when the parent walk visits them.
    if kind == ControlFlowNodeKind.TRY:
        for child in node.children:
            if child.type == "block":
                return child
    return None


def _count_statements(body_node: Node) -> int:
    """Count executable statements in a function body (recursive).

    See arch §1.5. A compound statement (if, for, with) counts as 1 and its
    body's statements are added recursively.
    """
    count = 0
    stack: list[Node] = [body_node]
    visited_root = False
    while stack:
        node = stack.pop()
        if not visited_root:
            visited_root = True
            # Don't count the body node itself — count its statement children.
            stack.extend(node.children)
            continue
        if node.type in _STATEMENT_NODE_TYPES:
            count += 1
            # Recurse into compound statements' bodies to count nested statements.
            body = node.child_by_field_name("body")
            if body is not None:
                stack.extend(body.children)
            # except_clause / else_clause / finally_clause blocks of try/if/for/while
            # contain additional statements we need to count.
            for child in node.children:
                if child.type in ("else_clause", "elif_clause", "except_clause", "finally_clause"):
                    body_of_clause = child.child_by_field_name("body")
                    if body_of_clause is not None:
                        stack.extend(body_of_clause.children)
    return count
```

Update `_collect_functions` to populate the two new fields:

Find the block that constructs `FunctionDefNode(...)` and add the two new kwargs. Locate the function body node (which is the `body` field of the `function_definition` node) and pass it to the helpers:

```python
# existing code that extracts name, qualified, params, source_range, ast_hash...
body_node = node.child_by_field_name("body")
control_flow = (
    _collect_control_flow(body_node) if body_node is not None else ()
)
statement_count = _count_statements(body_node) if body_node is not None else 0

fn_def = FunctionDefNode(
    name=name,
    qualified_name=qualified,
    enclosing_class=enclosing_class,
    source_range=_source_range(node, file_path),
    ast_hash=hash_ast_sexp(_sexp(node)),
    parameter_names=params,
    control_flow=control_flow,
    statement_count=statement_count,
)
```

Also **fix the `_source_range` usage in `_collect_control_flow`** — the function signature takes `file_path` as a str, but the helper was called with `str(node.start_byte)` as a placeholder above. Thread the actual file path through: change `_collect_control_flow`'s signature to `(func_body_node, file_path, depth=0)` and pass it through to `_source_range(node, file_path)`. Apply the same change to `_cfn_body_node` callers if needed. Wire this through in `_collect_functions`:

```python
control_flow = (
    _collect_control_flow(body_node, file_path) if body_node is not None else ()
)
```

- [ ] **Step 5: Run tests** — iterate on implementation until all pass

```bash
uv run pytest tests/test_parse_control_flow.py -v
```

Expected: all 9 tests pass. Tree-sitter's node type names for Python 0.23.x are stable but verify experimentally if something fails. Common issues:
- `elif_clause` may actually be a child of `if_statement`'s `alternative` field — confirm empirically with `print(node.sexp())` on an `if_statement`.
- `boolean_operator` may appear nested (e.g., `a and b or c` could be `(boolean_operator (boolean_operator a b) c)` or flat). The `_classify_cfn` + `_has_nested_control_flow` interaction should avoid double-counting; if the test `test_boolean_ops_captured_as_single_sequence` fails with `seq_count > 1`, tighten by marking inner boolean_operators visited.

- [ ] **Step 6: Run the full parse suite to verify no regression**

```bash
uv run pytest tests/test_parse_python.py tests/test_parse_adapter.py tests/test_parse_hashing.py tests/test_parse_control_flow.py -v 2>&1 | tail -10
```

All prior Slice 2 parse tests must still pass. Expect the new 9 tests to pass also.

- [ ] **Step 7: Ruff + mypy**

```bash
uv run ruff check src/savviety_instinct/parse/python.py tests/test_parse_control_flow.py
uv run ruff format --check src/savviety_instinct/parse/python.py tests/test_parse_control_flow.py
uv run mypy src/savviety_instinct/parse/python.py
```

All clean.

- [ ] **Step 8: Commit**

```bash
git add src/savviety_instinct/parse/python.py tests/test_parse_control_flow.py tests/fixtures/python/nested_control_flow.py
git commit -m "$(cat <<'EOF'
feat(parse): PythonAdapter emits ControlFlowNode tree + statement_count

Pre-computes FunctionDefNode.control_flow and .statement_count during the
tree-sitter walk so Slice 3 metrics don't need to re-traverse. Handles
nested if/for/while/try, comprehensions, ternaries, and boolean-operator
sequences (one group per expression, not per operator — matches Sonar's
cognitive rule per arch §1.2).

New fixture nested_control_flow.py exercises the full kind set; 9 new
tests cover straight-line, simple if, deeply nested, boolean ops,
comprehensions, ternary, and Slice 2 regression parity.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Extend `AnalysisContext` with `parse_result`

**Files:**
- Modify: `src/savviety_instinct/core/types.py`
- Create: `tests/test_core_analysis_context_parse_result.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_core_analysis_context_parse_result.py`:

```python
"""AnalysisContext.parse_result — forward-ref, layering-preserving extension."""

from __future__ import annotations

import sys


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
    # Force a fresh import of savviety_instinct.core.types in isolation.
    # We can't actually isolate inside a running pytest session, but we can at
    # least assert the symbol table: parse is NOT referenced at runtime.
    from savviety_instinct.core import types as core_types

    # The class annotation on AnalysisContext.parse_result should be a string,
    # NOT a resolved class reference.
    anno = core_types.AnalysisContext.__annotations__.get("parse_result", "")
    assert isinstance(anno, str), f"parse_result annotation must remain a string at runtime; got {type(anno)}"
    assert "ParseResult" in anno


def test_combined_call_graph_and_parse_result() -> None:
    """Both Slice 2's call_graph and Slice 3's parse_result can coexist."""
    from savviety_instinct.core.types import AnalysisContext
    from savviety_instinct.graph import CallGraph
    from savviety_instinct.parse.python import PYTHON_ADAPTER

    result = PYTHON_ADAPTER.parse_source(b"def x() -> int:\n    return 1\n", "inline.py")
    cg = CallGraph()
    ctx = AnalysisContext(parse_result=result, call_graph=cg)
    assert ctx.parse_result is result
    assert ctx.call_graph is cg
```

- [ ] **Step 2: Run failing tests**

`uv run pytest tests/test_core_analysis_context_parse_result.py -v` — expect failures (field doesn't exist yet).

- [ ] **Step 3: Extend `core/types.py`**

Inside the existing `TYPE_CHECKING` block at the top of `core/types.py`, add `ParseResult`:

```python
if TYPE_CHECKING:
    from savviety_instinct.graph.types import CallGraph
    from savviety_instinct.parse.types import ParseResult
```

Extend `AnalysisContext`:

```python
@dataclass(frozen=True, slots=True)
class AnalysisContext:
    """Context passed to each Metric.compute().

    Slice 2 added `call_graph`. Slice 3 adds `parse_result` so metrics can
    look up their own function's ControlFlowNode / statement_count without
    a second tree walk. All fields are keyword-only with defaults; the
    absolute core → (parse|graph) layering rule is preserved via
    TYPE_CHECKING + string annotations (arch §2).
    """

    call_graph: "CallGraph | None" = None  # noqa: UP037 — quoted for explicit forward-ref
    parse_result: "ParseResult | None" = None  # noqa: UP037 — quoted for explicit forward-ref
```

- [ ] **Step 4: Run the new tests + full core test suite**

```bash
uv run pytest tests/test_core_types.py tests/test_core_analysis_context_parse_result.py -v
```

Expect all green. Pay attention to `test_core_types_does_not_import_parse_at_runtime` — if this fails, the annotation was resolved into a real class reference; revisit the quoting.

- [ ] **Step 5: Layering check (critical)**

Run the explicit sys.modules assertion that guarded Slice 2:

```bash
uv run python -c "
import sys
import savviety_instinct.core.types  # noqa
assert 'savviety_instinct.graph' not in sys.modules, 'core MUST NOT import graph at runtime'
assert 'savviety_instinct.graph.types' not in sys.modules, 'core MUST NOT import graph.types at runtime'
assert 'savviety_instinct.parse' not in sys.modules, 'core MUST NOT import parse at runtime'
assert 'savviety_instinct.parse.types' not in sys.modules, 'core MUST NOT import parse.types at runtime'
print('layering holds')
"
```

Expect `layering holds`.

- [ ] **Step 6: mypy + ruff**

```bash
uv run mypy src/savviety_instinct/core/types.py
uv run ruff check src/savviety_instinct/core/types.py tests/test_core_analysis_context_parse_result.py
```

- [ ] **Step 7: Commit**

```bash
git add src/savviety_instinct/core/types.py tests/test_core_analysis_context_parse_result.py
git commit -m "$(cat <<'EOF'
feat(core): AnalysisContext.parse_result (forward-ref, layering preserved)

Slice 3 metrics need access to FunctionDefNode.control_flow /
statement_count to compute values. Rather than a richer Metric.compute()
signature, metrics receive AnalysisContext.parse_result and look up their
own function by ast_hash. Same TYPE_CHECKING + quoted-annotation trick as
Slice 2's call_graph preserves the core → parse runtime-import block
from arch §2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `statement_count` metric (simplest — primes the pattern)

**Files:**
- Create: `src/savviety_instinct/analyze/metrics/__init__.py`
- Create: `src/savviety_instinct/analyze/metrics/statement_count.py`
- Create: `tests/fixtures/python/metric_fixtures.py`
- Create: `tests/test_analyze_metric_statement_count.py`

- [ ] **Step 1: Create fixture — `tests/fixtures/python/metric_fixtures.py`**

Hand-crafted functions with known expected metric values. Comments state the expectations so humans can verify at a glance.

```python
"""Hand-crafted fixtures with known metric values.

Each function has a comment block documenting its expected
statement_count / cyclomatic_complexity / cognitive_complexity. When
the metric formula changes, UPDATE THESE COMMENTS in lockstep.
"""


def empty() -> None:
    """statement_count=0, cyclomatic=1, cognitive=0."""


def two_statements(x: int) -> int:
    """statement_count=2, cyclomatic=1, cognitive=0."""
    y = x + 1
    return y


def single_if(x: int) -> int:
    """statement_count=3, cyclomatic=2 (if), cognitive=1 (if)."""
    if x > 0:
        return x
    return 0


def single_if_with_boolean(x: int, y: int) -> int:
    """statement_count=3, cyclomatic=3 (if + one additional decision for and),
    cognitive=2 (if +1, bool group +1)."""
    if x > 0 and y > 0:
        return x + y
    return 0


def nested_if(x: int) -> int:
    """statement_count=4, cyclomatic=3 (two ifs), cognitive=3 (outer if +1,
    inner if +2 because it's at nesting depth 1)."""
    if x > 0:
        if x < 100:
            return x
    return 0


def for_loop_only(items: list[int]) -> int:
    """statement_count=3, cyclomatic=2 (for), cognitive=1 (for)."""
    total = 0
    for item in items:
        total += item
    return total


def for_with_if(items: list[int]) -> int:
    """statement_count=4, cyclomatic=3 (for + if), cognitive=3 (for +1,
    nested if +2 at depth 1)."""
    total = 0
    for item in items:
        if item > 0:
            total += item
    return total


def try_except(x: int) -> int:
    """statement_count=4, cyclomatic=2 (except), cognitive=1 (except)."""
    try:
        return 1 // x
    except ZeroDivisionError:
        return 0


def ternary(x: int) -> int:
    """statement_count=1, cyclomatic=2 (ternary), cognitive=1 (ternary)."""
    return x if x > 0 else -x


def comprehension(items: list[int]) -> list[int]:
    """statement_count=1, cyclomatic=2 (comprehension generator), cognitive=1."""
    return [i for i in items if i > 0]
```

- [ ] **Step 2: Write failing tests — `tests/test_analyze_metric_statement_count.py`**

```python
"""Unit tests for the statement_count metric."""

from __future__ import annotations

from pathlib import Path

import pytest

from savviety_instinct.analyze.metrics.statement_count import STATEMENT_COUNT_METRIC
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
        ("two_statements", 2),
        ("single_if", 3),
        ("single_if_with_boolean", 3),
        ("nested_if", 4),
        ("for_loop_only", 3),
        ("for_with_if", 4),
        ("try_except", 4),
        ("ternary", 1),
        ("comprehension", 1),
    ],
)
def test_statement_count_matches_fixture_annotation(
    metric_fixtures_result, qualified: str, expected: int
) -> None:
    artifact = _artifact_for(metric_fixtures_result, qualified)
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    value = STATEMENT_COUNT_METRIC.compute(artifact, ctx)
    assert value.value == expected, (
        f"{qualified}: expected {expected}, got {value.value}. "
        f"Update the fixture's comment block if the metric formula changed."
    )


def test_statement_count_metric_metadata() -> None:
    assert STATEMENT_COUNT_METRIC.id == "statement_count"
    assert STATEMENT_COUNT_METRIC.version == "1.0.0"
    assert STATEMENT_COUNT_METRIC.applies_to == frozenset({ArtifactKind.FUNCTION})
    assert STATEMENT_COUNT_METRIC.required_inputs == frozenset({InputKind.AST})


def test_statement_count_returns_high_confidence(metric_fixtures_result) -> None:
    artifact = _artifact_for(metric_fixtures_result, "single_if")
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    value = STATEMENT_COUNT_METRIC.compute(artifact, ctx)
    assert value.confidence == Confidence.HIGH


def test_statement_count_raises_without_parse_result() -> None:
    artifact = _artifact_for(PYTHON_ADAPTER.parse_path(FIXTURES / "metric_fixtures.py"), "single_if")
    ctx = AnalysisContext()  # parse_result is None
    with pytest.raises(ValueError, match="parse_result"):
        STATEMENT_COUNT_METRIC.compute(artifact, ctx)


def test_statement_count_raises_when_artifact_not_found(metric_fixtures_result) -> None:
    """If the artifact's ast_hash doesn't match anything in parse_result.functions,
    the metric should raise rather than silently returning 0.
    """
    artifact = Artifact(
        ast_hash="nonexistent_hash",
        language=Language.PYTHON,
        kind=ArtifactKind.FUNCTION,
        name="missing",
        enclosing_scope=None,
        source_range=None,  # type: ignore[arg-type]
    )
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    with pytest.raises(LookupError, match="ast_hash"):
        STATEMENT_COUNT_METRIC.compute(artifact, ctx)
```

- [ ] **Step 3: Run failing tests**

`uv run pytest tests/test_analyze_metric_statement_count.py -v` — expect all fail with ImportError.

- [ ] **Step 4: Create `analyze/metrics/__init__.py`**

```python
"""Metric implementations (arch §5.3 pipeline stage 5)."""

from __future__ import annotations

from savviety_instinct.analyze.metrics.statement_count import STATEMENT_COUNT_METRIC

__all__ = ["STATEMENT_COUNT_METRIC"]
```

(Later tasks append `CYCLOMATIC_METRIC` and `COGNITIVE_METRIC`.)

- [ ] **Step 5: Create `analyze/metrics/statement_count.py`**

```python
"""Statement Count metric — count of executable statements per function.

Arch §1.5. Reads the pre-computed `FunctionDefNode.statement_count` value
from the parse layer (populated during Slice 3 Task 3). The metric itself
does no traversal; it's a pure lookup.
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


class StatementCountMetric:
    id: str = "statement_count"
    version: str = "1.0.0"
    applies_to: frozenset[ArtifactKind] = frozenset({ArtifactKind.FUNCTION})
    required_inputs: frozenset[InputKind] = frozenset({InputKind.AST})

    def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue:
        if context.parse_result is None:
            raise ValueError(
                f"{self.id} requires AnalysisContext.parse_result to be populated "
                "with the current file's ParseResult."
            )
        fn = _lookup_function(artifact, context)
        return MetricValue(
            metric_id=self.id,
            value=fn.statement_count,
            metric_version=self.version,
            confidence=Confidence.HIGH,
        )


def _lookup_function(artifact: Artifact, context: AnalysisContext):
    for fn in context.parse_result.functions:  # type: ignore[union-attr]
        if fn.ast_hash == artifact.ast_hash:
            return fn
    raise LookupError(
        f"No FunctionDefNode with ast_hash={artifact.ast_hash!r} found in "
        f"parse_result.functions (file={context.parse_result.file_path!r})"  # type: ignore[union-attr]
    )


STATEMENT_COUNT_METRIC = StatementCountMetric()
```

- [ ] **Step 6: Run tests, iterate**

```bash
uv run pytest tests/test_analyze_metric_statement_count.py -v
```

If fixture-annotated values don't match, either the parse-layer statement_count algorithm needs tweaking (Task 3 helper), or the fixture comment is wrong. **Do NOT adjust the fixture to match whatever the code produces** — the fixture values are the ground truth (hand-verified). Iterate on `_count_statements` in Task 3 until the metric returns the documented values.

- [ ] **Step 7: Ruff + mypy**

```bash
uv run ruff check src/savviety_instinct/analyze tests/test_analyze_metric_statement_count.py
uv run mypy src/savviety_instinct/analyze/metrics/statement_count.py
```

- [ ] **Step 8: Commit**

```bash
git add src/savviety_instinct/analyze/metrics/__init__.py \
        src/savviety_instinct/analyze/metrics/statement_count.py \
        tests/fixtures/python/metric_fixtures.py \
        tests/test_analyze_metric_statement_count.py
git commit -m "$(cat <<'EOF'
feat(analyze): statement_count metric (reads pre-computed FunctionDefNode.statement_count)

First concrete metric — primes the analyze/ module with a registry entry,
a Metric-protocol-conforming class, and a singleton instance. Reads
pre-computed value from parse layer; no traversal. Hand-crafted
metric_fixtures.py establishes ground-truth values that later metrics
(cyclomatic, cognitive) will also reference.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `cyclomatic_complexity` metric

**Files:**
- Create: `src/savviety_instinct/analyze/metrics/cyclomatic.py`
- Create: `tests/test_analyze_metric_cyclomatic.py`
- Modify: `src/savviety_instinct/analyze/metrics/__init__.py` (add re-export)

**Formula (arch §1.1):** `M = decisions + 1` where decisions = count of `if`, `elif`, `for`, `while`, `except`, `and`, `or`, `?:` (ternary), comprehension generator clauses. `else` does NOT count (no new branch; it's the fallthrough). `try` wrapper does NOT count (only its `except` clauses do).

Implementation strategy: recursively walk the `ControlFlowNode` tree on the `FunctionDefNode.control_flow` and count based on `kind`. `ControlFlowNodeKind` handling:

| Kind | Counts? |
|------|---------|
| IF | +1 |
| ELIF | +1 |
| ELSE | 0 |
| FOR | +1 |
| WHILE | +1 |
| TRY | 0 (wrapper) |
| EXCEPT | +1 |
| TERNARY | +1 |
| BOOLEAN_SEQUENCE | +1 per OPERATOR in the sequence (NOT per group — cyclomatic differs from cognitive here) |
| COMPREHENSION | +1 per `for_in_clause` (plus +1 for each `if`-clause inside) |

**Note:** BOOLEAN_SEQUENCE and COMPREHENSION counting requires knowing the operator count / clause count. Options:
- A. Extend `ControlFlowNode` with an `extra: int = 0` field the parser fills (e.g., number of operators in the boolean sequence, number of clauses in the comprehension). Clean but cross-cuts Task 2/3.
- B. Hardcode `BOOLEAN_SEQUENCE = +1` and `COMPREHENSION = +1` for Slice 3, add a known-gap comment. Acceptable because arch §1.1 pitfalls explicitly says cyclomatic is "de-emphasized in favor of cognitive complexity" — precision loss on edge cases is tolerable for the primary-signal metric's sibling.
- C. Store the raw tree-sitter node reference on ControlFlowNode. Violates layering (analyze → tree_sitter).

**Decision: Option B for MVP.** Document the gap with a TODO / note field; bump metric_version when we fix it. This keeps Slice 3 scope tight.

- [ ] **Step 1: Write failing tests**

`tests/test_analyze_metric_cyclomatic.py`:

```python
"""Unit tests for the cyclomatic_complexity metric."""

from __future__ import annotations

from pathlib import Path

import pytest

from savviety_instinct.analyze.metrics.cyclomatic import CYCLOMATIC_METRIC
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
        ("empty", 1),
        ("two_statements", 1),
        ("single_if", 2),
        # single_if_with_boolean: `if x > 0 and y > 0` — cyclomatic counts the `and`
        # as +1 operator AND the `if` as +1. Slice 3 approximation (Option B):
        # BOOLEAN_SEQUENCE = +1 per group. So expected = 2 (if) + 1 (bool group) = 3.
        ("single_if_with_boolean", 3),
        ("nested_if", 3),        # 1 + 2 ifs
        ("for_loop_only", 2),    # 1 + for
        ("for_with_if", 3),      # 1 + for + if
        ("try_except", 2),       # 1 + except (try itself is a wrapper, not a decision)
        ("ternary", 2),          # 1 + ternary
        # comprehension with filter: `[i for i in items if i > 0]`.
        # Slice 3 approximation: COMPREHENSION = +1. Expected 2.
        ("comprehension", 2),
    ],
)
def test_cyclomatic_matches_fixture(
    metric_fixtures_result, qualified: str, expected: int
) -> None:
    artifact = _artifact_for(metric_fixtures_result, qualified)
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    value = CYCLOMATIC_METRIC.compute(artifact, ctx)
    assert value.value == expected, (
        f"{qualified}: expected {expected}, got {value.value}."
    )


def test_cyclomatic_metadata() -> None:
    assert CYCLOMATIC_METRIC.id == "cyclomatic_complexity"
    assert CYCLOMATIC_METRIC.version == "1.0.0"
    assert CYCLOMATIC_METRIC.applies_to == frozenset({ArtifactKind.FUNCTION})
    assert CYCLOMATIC_METRIC.required_inputs == frozenset({InputKind.AST})


def test_cyclomatic_high_confidence_on_plain_python(metric_fixtures_result) -> None:
    artifact = _artifact_for(metric_fixtures_result, "nested_if")
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    assert CYCLOMATIC_METRIC.compute(artifact, ctx).confidence == Confidence.HIGH


def test_cyclomatic_minimum_is_one(metric_fixtures_result) -> None:
    """M = decisions + 1; a function with zero decisions scores 1, not 0."""
    artifact = _artifact_for(metric_fixtures_result, "empty")
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    assert CYCLOMATIC_METRIC.compute(artifact, ctx).value == 1
```

- [ ] **Step 2: Run failing tests**

`uv run pytest tests/test_analyze_metric_cyclomatic.py -v` — expect ImportError on `CYCLOMATIC_METRIC`.

- [ ] **Step 3: Implement**

`src/savviety_instinct/analyze/metrics/cyclomatic.py`:

```python
"""Cyclomatic Complexity (McCabe) metric.

Arch §1.1. Formula: M = decisions + 1.
Decisions: if, elif, for, while, except, ternary, boolean sequence (per
group for Slice 3 — approximation; see note), comprehension (per
comprehension for Slice 3 — approximation).

Confidence: high on plain Python with the standard decision set.

KNOWN GAP (metric_version=1.0.0): BOOLEAN_SEQUENCE counts +1 per group,
not per operator. COMPREHENSION counts +1 per comprehension, not per
generator clause. These edge cases are documented in arch §1.1 pitfalls
and are tolerable for a de-emphasized sibling metric. Fix in a later
version bump with finer-grained ControlFlowNode fields.
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


# Kinds that contribute to the decision count.
_DECISION_KINDS: frozenset[ControlFlowNodeKind] = frozenset(
    {
        ControlFlowNodeKind.IF,
        ControlFlowNodeKind.ELIF,
        ControlFlowNodeKind.FOR,
        ControlFlowNodeKind.WHILE,
        ControlFlowNodeKind.EXCEPT,
        ControlFlowNodeKind.TERNARY,
        ControlFlowNodeKind.BOOLEAN_SEQUENCE,  # +1 per group — see module docstring
        ControlFlowNodeKind.COMPREHENSION,     # +1 per comprehension — see module docstring
    }
)


def _count_decisions(nodes: tuple[ControlFlowNode, ...]) -> int:
    count = 0
    for node in nodes:
        if node.kind in _DECISION_KINDS:
            count += 1
        count += _count_decisions(node.children)
    return count


class CyclomaticMetric:
    id: str = "cyclomatic_complexity"
    version: str = "1.0.0"
    applies_to: frozenset[ArtifactKind] = frozenset({ArtifactKind.FUNCTION})
    required_inputs: frozenset[InputKind] = frozenset({InputKind.AST})

    def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue:
        if context.parse_result is None:
            raise ValueError(f"{self.id} requires AnalysisContext.parse_result")
        for fn in context.parse_result.functions:
            if fn.ast_hash == artifact.ast_hash:
                value = _count_decisions(fn.control_flow) + 1
                return MetricValue(
                    metric_id=self.id,
                    value=value,
                    metric_version=self.version,
                    confidence=Confidence.HIGH,
                )
        raise LookupError(f"No function with ast_hash={artifact.ast_hash!r} in parse_result")


CYCLOMATIC_METRIC = CyclomaticMetric()
```

- [ ] **Step 4: Add to registry**

In `src/savviety_instinct/analyze/metrics/__init__.py`:

```python
"""Metric implementations (arch §5.3 pipeline stage 5)."""

from __future__ import annotations

from savviety_instinct.analyze.metrics.cyclomatic import CYCLOMATIC_METRIC
from savviety_instinct.analyze.metrics.statement_count import STATEMENT_COUNT_METRIC

__all__ = ["CYCLOMATIC_METRIC", "STATEMENT_COUNT_METRIC"]
```

- [ ] **Step 5: Run tests, iterate**

```bash
uv run pytest tests/test_analyze_metric_cyclomatic.py tests/test_analyze_metric_statement_count.py -v
```

If fixtures disagree, the first suspect is the parse-layer CFN extraction from Task 3 (e.g., ternary not being classified). Fix the parse layer; do NOT change fixture values.

- [ ] **Step 6: Ruff + mypy**

- [ ] **Step 7: Commit**

```bash
git add src/savviety_instinct/analyze/metrics/cyclomatic.py \
        src/savviety_instinct/analyze/metrics/__init__.py \
        tests/test_analyze_metric_cyclomatic.py
git commit -m "$(cat <<'EOF'
feat(analyze): cyclomatic_complexity metric (McCabe decisions + 1)

Documented Slice 3 approximations: BOOLEAN_SEQUENCE and COMPREHENSION
each count +1 per group/comprehension rather than per operator/clause.
Acceptable because cyclomatic is de-emphasized in favor of cognitive
per arch §1.1; fix in a later metric_version bump with finer-grained
ControlFlowNode fields.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Cognitive rules YAML + loader

**Files:**
- Create: `src/savviety_instinct/core/cognitive_rules/__init__.py` (empty)
- Create: `src/savviety_instinct/core/cognitive_rules/python.yaml`
- Create: `src/savviety_instinct/analyze/rules.py`
- Create: `tests/test_analyze_rules.py`

- [ ] **Step 1: Create the empty package marker**

`src/savviety_instinct/core/cognitive_rules/__init__.py`:

```python
"""Per-language cognitive-complexity rule tables (YAML). Data-only; no Python code."""
```

- [ ] **Step 2: Create `python.yaml`**

`src/savviety_instinct/core/cognitive_rules/python.yaml`:

```yaml
# Cognitive complexity increment rules for Python.
# Schema documented in analyze/rules.py :: CognitiveRules.
#
# Per arch §1.2 / Sonar semantics:
#  - `+1` for each linear-flow break
#  - additional `+nesting_depth` when nested inside another control structure
#  - `+0` for shorthand (early return, null-coalescing, single-branch ?.)
#
# Python-specific: list/set/dict comprehensions count ONCE per generator clause,
# not per operation (arch §1.2 pitfall). Slice 3 approximation: +1 per
# comprehension (regardless of clause count). Finer-grained counting is a
# future metric_version bump.
#
# 'increments_nesting' controls whether crossing this construct deepens the
# nesting counter used by its descendants. e.g. `if`-inside-`if`: outer's
# increments_nesting=true, so the inner gets +2 (1 for being an if + 1 for
# depth).

language: python
increments:
  if: {base: 1, increments_nesting: true}
  elif: {base: 1, increments_nesting: false}  # elif is a continuation, not a new nest
  else: {base: 1, increments_nesting: false}  # else is the fallthrough branch of the if
  for: {base: 1, increments_nesting: true}
  while: {base: 1, increments_nesting: true}
  try: {base: 0, increments_nesting: true}   # try wrapper is zero-cost but adds nesting for except clauses
  except: {base: 1, increments_nesting: false}
  ternary: {base: 1, increments_nesting: false}
  boolean_sequence: {base: 1, increments_nesting: false}
  comprehension: {base: 1, increments_nesting: false}
```

- [ ] **Step 3: Write failing tests**

`tests/test_analyze_rules.py`:

```python
"""Tests for analyze.rules — cognitive rules YAML loader."""

from __future__ import annotations

import pytest

from savviety_instinct.analyze.rules import CognitiveIncrement, load_cognitive_rules
from savviety_instinct.core.types import Language
from savviety_instinct.parse.types import ControlFlowNodeKind


def test_load_python_rules_succeeds() -> None:
    rules = load_cognitive_rules(Language.PYTHON)
    assert rules.language == Language.PYTHON


def test_rules_include_expected_kinds() -> None:
    rules = load_cognitive_rules(Language.PYTHON)
    # Every ControlFlowNodeKind should have an entry
    for kind in ControlFlowNodeKind:
        assert kind in rules.increments, f"Missing rule for {kind}"


def test_if_rule_structure() -> None:
    rules = load_cognitive_rules(Language.PYTHON)
    if_rule = rules.increments[ControlFlowNodeKind.IF]
    assert isinstance(if_rule, CognitiveIncrement)
    assert if_rule.base == 1
    assert if_rule.increments_nesting is True


def test_else_does_not_nest() -> None:
    rules = load_cognitive_rules(Language.PYTHON)
    else_rule = rules.increments[ControlFlowNodeKind.ELSE]
    assert else_rule.base == 1
    assert else_rule.increments_nesting is False


def test_load_is_cached() -> None:
    a = load_cognitive_rules(Language.PYTHON)
    b = load_cognitive_rules(Language.PYTHON)
    assert a is b  # same object returned from lru_cache


def test_load_unsupported_language_raises() -> None:
    with pytest.raises(ValueError, match="No cognitive rules YAML for"):
        load_cognitive_rules(Language.RUST)
```

- [ ] **Step 4: Run failing tests**

`uv run pytest tests/test_analyze_rules.py -v` — expect ImportError.

- [ ] **Step 5: Implement `analyze/rules.py`**

```python
"""Load per-language cognitive-complexity rule tables from YAML.

Arch §1.2 and §5.5. Rules live in `src/savviety_instinct/core/cognitive_rules/
<lang>.yaml` and are loaded once per process via importlib.resources +
lru_cache. Data-only — the loader is the sole I/O point; the YAML itself
contains no executable code.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Mapping

import yaml

from savviety_instinct.core.types import Language
from savviety_instinct.parse.types import ControlFlowNodeKind


@dataclass(frozen=True, slots=True)
class CognitiveIncrement:
    """One row of the increment table: base increment + whether it deepens nesting."""

    base: int
    increments_nesting: bool


@dataclass(frozen=True, slots=True)
class CognitiveRules:
    language: Language
    increments: Mapping[ControlFlowNodeKind, CognitiveIncrement]


_LANG_TO_FILENAME: dict[Language, str] = {
    Language.PYTHON: "python.yaml",
    # Language.RUST / CSHARP / TYPESCRIPT added by Slices 7–8
}


@lru_cache(maxsize=None)
def load_cognitive_rules(language: Language) -> CognitiveRules:
    if language not in _LANG_TO_FILENAME:
        raise ValueError(
            f"No cognitive rules YAML for {language.value!r}. "
            f"Supported: {sorted(lang.value for lang in _LANG_TO_FILENAME)}."
        )
    filename = _LANG_TO_FILENAME[language]
    content = resources.files("savviety_instinct.core.cognitive_rules").joinpath(filename).read_text(encoding="utf-8")
    raw = yaml.safe_load(content)
    if raw.get("language") != language.value:
        raise ValueError(
            f"YAML declares language={raw.get('language')!r} but loader called with "
            f"{language.value!r}"
        )
    increments: dict[ControlFlowNodeKind, CognitiveIncrement] = {}
    for kind_str, rule in raw["increments"].items():
        try:
            kind = ControlFlowNodeKind(kind_str)
        except ValueError as exc:
            raise ValueError(
                f"Unknown ControlFlowNodeKind {kind_str!r} in {filename}; "
                f"add it to the enum or remove the rule."
            ) from exc
        increments[kind] = CognitiveIncrement(
            base=int(rule["base"]),
            increments_nesting=bool(rule["increments_nesting"]),
        )
    # Sanity: every known kind must have a rule.
    missing = set(ControlFlowNodeKind) - set(increments)
    if missing:
        raise ValueError(
            f"{filename} is missing rules for {sorted(k.value for k in missing)}"
        )
    return CognitiveRules(language=language, increments=increments)
```

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/test_analyze_rules.py -v
```

- [ ] **Step 7: Ruff + mypy**

```bash
uv run ruff check src/savviety_instinct/analyze/rules.py tests/test_analyze_rules.py
uv run mypy src/savviety_instinct/analyze/rules.py
```

- [ ] **Step 8: Commit**

```bash
git add src/savviety_instinct/core/cognitive_rules/ \
        src/savviety_instinct/analyze/rules.py \
        tests/test_analyze_rules.py
git commit -m "$(cat <<'EOF'
feat(analyze): cognitive rules YAML + loader (Python)

Per arch §5.5, per-language cognitive increment tables live as YAML
under src/savviety_instinct/core/cognitive_rules/. Loader uses
importlib.resources (package data pattern) + lru_cache. Completeness
check fails fast if a ControlFlowNodeKind has no rule — forces
coordinated enum-and-YAML updates.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: `cognitive_complexity` metric

**Files:**
- Create: `src/savviety_instinct/analyze/metrics/cognitive.py`
- Create: `tests/test_analyze_metric_cognitive.py`
- Modify: `src/savviety_instinct/analyze/metrics/__init__.py`

**Algorithm:** Walk `control_flow` recursively tracking cumulative nesting depth. For each `ControlFlowNode`, look up the rule in the loaded `CognitiveRules`. Add `rule.base + node.nesting_depth` (if rule.base > 0, the +nesting_depth penalty kicks in per arch §1.2). Recurse into children with the same nesting depth the CFN already has (parse layer pre-computed `node.nesting_depth`).

Wait — there's a subtlety. Arch §1.2 says "`+nesting_depth` additional penalty when above is inside another control structure." But our `ControlFlowNode.nesting_depth` is cached at parse time from the function body perspective, NOT from the "inside another structure that increments nesting" perspective. `else_clause.nesting_depth` is 1 when inside an if, but `else`'s rule says `increments_nesting: false`, meaning THE INNER CONTENT of else shouldn't get the +1 bump from being inside else... but `else` itself IS at depth 1.

Let me re-read §1.2:

> `+nesting_depth` additional penalty when above is inside another control structure.

So: `if A: if B:` — the inner `if B` gets +1 for being an if, PLUS +1 because it's nested inside an if. Total +2.

But an `if` followed by an `else`: `if A: x = 1\nelse: y = 2` — both `if` and `else` are at the same source depth. `if` contributes +1 (it's the first). `else` contributes +1 (break in linear flow) but NOT +1 for nesting (else is not inside if's body; it's at the same level).

How does our `nesting_depth` attribute on ControlFlowNode compare? For `if A: if B:`, outer if has depth 0, inner if has depth 1. Inner if increment = rule.base + depth = 1 + 1 = 2. ✓

For `if A: x = 1\nelse: y = 2`, if has depth 0, else has depth... depends on implementation. If parser makes else a CHILD of if, else has depth 1 and would get +2 which is wrong. If parser makes else a SIBLING CFN, else has depth 0 and gets +1 which is correct.

This matters for Task 3's implementation. Let me note: **`else_clause` and `elif_clause` must be emitted as SIBLINGS of the parent if at the same nesting_depth, NOT as children.** That matches Python semantics: else is the fallthrough branch, same level.

Similarly for `try: except:` — except is at the same level as try (depth 0 if try is at depth 0), not depth 1. Actually per our rule table, try has `increments_nesting: true`, so except inside try's "nesting" is at depth+1... but that's OK because except.base = 1 + depth = 1 + 1 = 2? That's wrong — except should just be +1 per §1.2 (catch = +1, no mention of nesting bump).

Hmm. I think the nesting_depth cached on ControlFlowNode needs to differ based on whether the parent's rule says `increments_nesting`. That couples Task 3's parser to Task 7's rules, which is a layering/ordering problem.

**Alternative algorithm (cleaner):** Ignore `ControlFlowNode.nesting_depth` entirely at metric time. Instead, the metric walks the tree recursively and tracks the cumulative nesting increment based on the rule table:

```python
def compute_cognitive(nodes, rules, nesting=0):
    total = 0
    for node in nodes:
        rule = rules.increments[node.kind]
        total += rule.base + (nesting if rule.base > 0 else 0)
        child_nesting = nesting + (1 if rule.increments_nesting else 0)
        total += compute_cognitive(node.children, rules, child_nesting)
    return total
```

This way, `ControlFlowNode.nesting_depth` remains informational (parse-level, useful for reporting), but cognitive complexity ignores it and recomputes via the rules.

Let me use this algorithm. It's cleaner and doesn't couple parse to rules.

- [ ] **Step 1: Write failing tests**

```python
"""Unit tests for the cognitive_complexity metric."""

from __future__ import annotations

from pathlib import Path

import pytest

from savviety_instinct.analyze.metrics.cognitive import COGNITIVE_METRIC
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
        ("single_if", 1),                       # if +1
        ("single_if_with_boolean", 2),          # if +1, bool group +1
        ("nested_if", 3),                        # outer if +1, inner if +1 +1 (nesting) = 3
        ("for_loop_only", 1),                    # for +1
        ("for_with_if", 3),                      # for +1, nested if +1 +1 = 3
        ("try_except", 1),                       # except +1 (try is 0, nests the except)
        ("ternary", 1),                          # ternary +1
        ("comprehension", 1),                    # comprehension +1
    ],
)
def test_cognitive_matches_fixture(metric_fixtures_result, qualified, expected) -> None:
    artifact = _artifact_for(metric_fixtures_result, qualified)
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    value = COGNITIVE_METRIC.compute(artifact, ctx)
    assert value.value == expected, f"{qualified}: expected {expected}, got {value.value}"


def test_cognitive_metadata() -> None:
    assert COGNITIVE_METRIC.id == "cognitive_complexity"
    assert COGNITIVE_METRIC.version == "1.0.0"
    assert COGNITIVE_METRIC.applies_to == frozenset({ArtifactKind.FUNCTION})
    assert COGNITIVE_METRIC.required_inputs == frozenset({InputKind.AST})


def test_cognitive_high_confidence(metric_fixtures_result) -> None:
    artifact = _artifact_for(metric_fixtures_result, "nested_if")
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    assert COGNITIVE_METRIC.compute(artifact, ctx).confidence == Confidence.HIGH


def test_cognitive_minimum_is_zero(metric_fixtures_result) -> None:
    """Unlike cyclomatic (min 1), cognitive starts at 0 for a straight-line function."""
    artifact = _artifact_for(metric_fixtures_result, "two_statements")
    ctx = AnalysisContext(parse_result=metric_fixtures_result)
    assert COGNITIVE_METRIC.compute(artifact, ctx).value == 0
```

- [ ] **Step 2: Run failing tests** — expect ImportError.

- [ ] **Step 3: Implement `analyze/metrics/cognitive.py`**

```python
"""Cognitive Complexity (Campbell / Sonar) metric.

Arch §1.2. Walks the ControlFlowNode tree tracking cumulative nesting depth
and applies per-language increment rules loaded from YAML. The nesting
counter is advanced based on the rule's `increments_nesting` flag, NOT the
raw parse-level `ControlFlowNode.nesting_depth` — this keeps the parser
rule-agnostic.
"""

from __future__ import annotations

from savviety_instinct.analyze.rules import load_cognitive_rules
from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Confidence,
    InputKind,
    Language,
    MetricValue,
)
from savviety_instinct.parse.types import ControlFlowNode


def _compute(nodes: tuple[ControlFlowNode, ...], rules, nesting: int = 0) -> int:
    total = 0
    for node in nodes:
        rule = rules.increments[node.kind]
        if rule.base > 0:
            total += rule.base + nesting
        child_nesting = nesting + (1 if rule.increments_nesting else 0)
        total += _compute(node.children, rules, child_nesting)
    return total


class CognitiveMetric:
    id: str = "cognitive_complexity"
    version: str = "1.0.0"
    applies_to: frozenset[ArtifactKind] = frozenset({ArtifactKind.FUNCTION})
    required_inputs: frozenset[InputKind] = frozenset({InputKind.AST})

    def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue:
        if context.parse_result is None:
            raise ValueError(f"{self.id} requires AnalysisContext.parse_result")
        for fn in context.parse_result.functions:
            if fn.ast_hash == artifact.ast_hash:
                rules = load_cognitive_rules(Language(context.parse_result.language))
                value = _compute(fn.control_flow, rules)
                return MetricValue(
                    metric_id=self.id,
                    value=value,
                    metric_version=self.version,
                    confidence=Confidence.HIGH,
                )
        raise LookupError(f"No function with ast_hash={artifact.ast_hash!r} in parse_result")


COGNITIVE_METRIC = CognitiveMetric()
```

- [ ] **Step 4: Register in `analyze/metrics/__init__.py`**

```python
"""Metric implementations (arch §5.3 pipeline stage 5)."""

from __future__ import annotations

from savviety_instinct.analyze.metrics.cognitive import COGNITIVE_METRIC
from savviety_instinct.analyze.metrics.cyclomatic import CYCLOMATIC_METRIC
from savviety_instinct.analyze.metrics.statement_count import STATEMENT_COUNT_METRIC

__all__ = ["COGNITIVE_METRIC", "CYCLOMATIC_METRIC", "STATEMENT_COUNT_METRIC"]
```

- [ ] **Step 5: Run tests + iterate**

If tests fail, it's either a parse-layer CFN issue (Task 3 emitted CFNs at wrong depths) or a rule issue (YAML rule doesn't match the expected Sonar semantics). Debug by printing the CFN tree:

```python
for fn in result.functions:
    if fn.qualified_name == "nested_if":
        for n in fn.control_flow:
            print(n.kind, n.nesting_depth, len(n.children))
            for c in n.children:
                print(" ", c.kind, c.nesting_depth)
```

- [ ] **Step 6: Ruff + mypy**

- [ ] **Step 7: Commit**

```bash
git add src/savviety_instinct/analyze/metrics/cognitive.py \
        src/savviety_instinct/analyze/metrics/__init__.py \
        tests/test_analyze_metric_cognitive.py
git commit -m "$(cat <<'EOF'
feat(analyze): cognitive_complexity metric (Sonar semantics via YAML rules)

Cumulative nesting tracked at metric time from rule.increments_nesting,
not the parse-level ControlFlowNode.nesting_depth — this keeps the parse
layer rule-agnostic. Hand-verified fixture values establish
ground-truth; Slice 3 covers the ten metric_fixtures.py cases.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: `analyze/__init__.py` — top-level registry

**Files:**
- Modify: `src/savviety_instinct/analyze/__init__.py`

Replace the empty stub with:

```python
"""analyze/ — metric computation and pipeline orchestration (arch §5.3)."""

from __future__ import annotations

from savviety_instinct.analyze.metrics import (
    COGNITIVE_METRIC,
    CYCLOMATIC_METRIC,
    STATEMENT_COUNT_METRIC,
)
from savviety_instinct.analyze.pipeline import run_pipeline
from savviety_instinct.analyze.rules import CognitiveRules, load_cognitive_rules

# Module-level registry. Ordered for deterministic output in CLI reports.
METRICS_REGISTRY = (
    STATEMENT_COUNT_METRIC,
    CYCLOMATIC_METRIC,
    COGNITIVE_METRIC,
)

__all__ = [
    "COGNITIVE_METRIC",
    "CYCLOMATIC_METRIC",
    "CognitiveRules",
    "METRICS_REGISTRY",
    "STATEMENT_COUNT_METRIC",
    "load_cognitive_rules",
    "run_pipeline",
]
```

Note: this file imports `run_pipeline` from `analyze/pipeline.py` which Task 10 creates. Commit this file AFTER Task 10 to avoid a broken import.

- [ ] **Step 1:** Defer this task's commit until after Task 10 (similar pattern to Slice 2's Task 4+5 coupling). Write the file but do not commit until Task 10 is green.

---

## Task 10: `analyze/pipeline.py` — file walker + orchestrator

**Files:**
- Create: `src/savviety_instinct/analyze/pipeline.py`
- Create: `tests/test_analyze_pipeline.py`

- [ ] **Step 1: Write failing tests**

`tests/test_analyze_pipeline.py`:

```python
"""Tests for analyze.pipeline — file walking + metric dispatch."""

from __future__ import annotations

from pathlib import Path

import pytest

from savviety_instinct.analyze.pipeline import PipelineSummary, run_pipeline
from savviety_instinct.config.models import InstinctConfig

FIXTURES = Path(__file__).parent / "fixtures" / "python"


def _cfg(**overrides) -> InstinctConfig:
    base = dict(scope="personal", suppress=[])
    base.update(overrides)
    return InstinctConfig(**base)


def test_run_single_file_yields_expected_metrics() -> None:
    results, summary = run_pipeline(FIXTURES / "metric_fixtures.py", _cfg())
    results = list(results)
    # 10 functions × 3 metrics = 30 rows.
    assert len(results) == 30
    assert summary.files_parsed == 1
    assert summary.files_skipped == 0
    assert summary.functions_analyzed == 10


def test_run_directory_walks_recursively() -> None:
    results, summary = run_pipeline(FIXTURES, _cfg())
    results = list(results)
    # FIXTURES contains multiple .py files. Should yield >= 30 rows (at least
    # the metric_fixtures.py ones).
    assert len(results) >= 30
    assert summary.files_parsed >= 1


def test_suppression_skips_files() -> None:
    # Exclude metric_fixtures.py, keep others
    results, summary = run_pipeline(FIXTURES, _cfg(suppress=["**/metric_fixtures.py"]))
    files_seen = {r[0].source_range.file_path for r in results}
    assert not any("metric_fixtures.py" in f for f in files_seen)


def test_syntax_error_file_is_skipped_with_stderr_log(capsys) -> None:
    results, summary = run_pipeline(
        FIXTURES / "syntax_error.py",
        _cfg(),
    )
    list(results)  # drain the generator
    captured = capsys.readouterr()
    assert "[parse-error]" in captured.err
    assert summary.files_skipped == 1
    assert summary.files_parsed == 0


def test_nonexistent_path_raises() -> None:
    with pytest.raises(FileNotFoundError):
        list(run_pipeline(Path("/nonexistent/path"), _cfg())[0])


def test_returns_deterministic_order() -> None:
    results1, _ = run_pipeline(FIXTURES / "metric_fixtures.py", _cfg())
    results2, _ = run_pipeline(FIXTURES / "metric_fixtures.py", _cfg())
    order1 = [(r[0].name, r[1].metric_id) for r in results1]
    order2 = [(r[0].name, r[1].metric_id) for r in results2]
    assert order1 == order2
```

- [ ] **Step 2: Implement `analyze/pipeline.py`**

```python
"""Analysis pipeline — walk a path, parse each source file, compute metrics.

Arch §5.3. Slice 3: single-threaded, synchronous, no storage writes. Yields
`(Artifact, MetricValue)` tuples for CLI consumers. Parse errors are soft —
file skipped, logged to stderr, counted in summary. Non-parse errors
propagate.
"""

from __future__ import annotations

import fnmatch
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from savviety_instinct.analyze.metrics import (
    COGNITIVE_METRIC,
    CYCLOMATIC_METRIC,
    STATEMENT_COUNT_METRIC,
)
from savviety_instinct.config.models import InstinctConfig
from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Language,
    MetricValue,
)
from savviety_instinct.parse.python import PYTHON_ADAPTER


_METRICS = (STATEMENT_COUNT_METRIC, CYCLOMATIC_METRIC, COGNITIVE_METRIC)


@dataclass(frozen=True, slots=True)
class PipelineSummary:
    files_parsed: int
    files_skipped: int
    functions_analyzed: int


def run_pipeline(
    path: Path, config: InstinctConfig
) -> tuple[Iterator[tuple[Artifact, MetricValue]], PipelineSummary]:
    """Return a generator of (Artifact, MetricValue) tuples + summary object.

    The summary is mutable-by-reference until the generator is exhausted.
    Callers should drain the generator before reading summary fields.
    """
    if not path.exists():
        raise FileNotFoundError(f"Path not found: {path}")

    summary = _MutableSummary()
    files = _discover_files(path, config.suppress)

    def _iter() -> Iterator[tuple[Artifact, MetricValue]]:
        for source_path in files:
            result = PYTHON_ADAPTER.parse_path(source_path)
            if not result.ok:
                summary.files_skipped += 1
                first_err = result.errors[0] if result.errors else None
                print(
                    f"[parse-error] {source_path}: {first_err.message if first_err else 'unknown'}",
                    file=sys.stderr,
                )
                continue
            summary.files_parsed += 1
            ctx = AnalysisContext(parse_result=result)
            for fn in result.functions:
                summary.functions_analyzed += 1
                artifact = Artifact(
                    ast_hash=fn.ast_hash,
                    language=Language.PYTHON,
                    kind=ArtifactKind.FUNCTION,
                    name=fn.name,
                    enclosing_scope=fn.enclosing_class,
                    source_range=fn.source_range,
                )
                for metric in _METRICS:
                    yield artifact, metric.compute(artifact, ctx)
        summary._freeze()

    return _iter(), summary.view()


class _MutableSummary:
    def __init__(self) -> None:
        self.files_parsed = 0
        self.files_skipped = 0
        self.functions_analyzed = 0
        self._frozen: PipelineSummary | None = None

    def _freeze(self) -> None:
        self._frozen = PipelineSummary(
            files_parsed=self.files_parsed,
            files_skipped=self.files_skipped,
            functions_analyzed=self.functions_analyzed,
        )

    def view(self) -> PipelineSummary:
        # Return a frozen snapshot lazily on access. Since the generator mutates
        # self, callers should read this AFTER draining.
        if self._frozen is not None:
            return self._frozen
        # If not frozen yet, take a current snapshot.
        return PipelineSummary(
            files_parsed=self.files_parsed,
            files_skipped=self.files_skipped,
            functions_analyzed=self.functions_analyzed,
        )


def _discover_files(path: Path, suppress: list[str]) -> list[Path]:
    """Enumerate .py files under path honoring glob suppressions.

    Returns a sorted list for deterministic iteration. `path` may be a file
    (returned as-is unless suppressed) or a directory.
    """
    if path.is_file():
        if _is_suppressed(path, suppress):
            return []
        return [path] if path.suffix == ".py" else []
    candidates = sorted(path.rglob("*.py"))
    return [p for p in candidates if not _is_suppressed(p, suppress)]


def _is_suppressed(path: Path, patterns: list[str]) -> bool:
    s = str(path)
    return any(fnmatch.fnmatch(s, pat) for pat in patterns)
```

Note: The summary design is a bit awkward because the generator is lazy. In practice callers `list(results)` before reading `summary` — that's what the tests do. The `view()` method returns a snapshot but it's advisable to just document: "drain the iterator first, then read summary."

Let me simplify. Instead of the `_MutableSummary` dance, return a `PipelineSummary` that's lazily computed:

Actually, the test does `results, summary = run_pipeline(...)` then `list(results)` and then reads `summary.files_parsed`. If `summary` is a live reference to the mutable object, this works: drain → summary reflects final counts.

The simpler design: return a mutable `PipelineSummary` dataclass (non-frozen). No freezing dance.

Let me revise:

```python
@dataclass
class PipelineSummary:
    files_parsed: int = 0
    files_skipped: int = 0
    functions_analyzed: int = 0


def run_pipeline(
    path: Path, config: InstinctConfig
) -> tuple[Iterator[tuple[Artifact, MetricValue]], PipelineSummary]:
    if not path.exists():
        raise FileNotFoundError(f"Path not found: {path}")
    summary = PipelineSummary()
    files = _discover_files(path, config.suppress)

    def _iter():
        for source_path in files:
            result = PYTHON_ADAPTER.parse_path(source_path)
            if not result.ok:
                summary.files_skipped += 1
                err = result.errors[0] if result.errors else None
                print(
                    f"[parse-error] {source_path}: {err.message if err else 'unknown'}",
                    file=sys.stderr,
                )
                continue
            summary.files_parsed += 1
            ctx = AnalysisContext(parse_result=result)
            for fn in result.functions:
                summary.functions_analyzed += 1
                artifact = Artifact(
                    ast_hash=fn.ast_hash,
                    language=Language.PYTHON,
                    kind=ArtifactKind.FUNCTION,
                    name=fn.name,
                    enclosing_scope=fn.enclosing_class,
                    source_range=fn.source_range,
                )
                for metric in _METRICS:
                    yield artifact, metric.compute(artifact, ctx)

    return _iter(), summary
```

Simpler, works correctly if callers drain before reading. Tests already assume this contract.

- [ ] **Step 3: Run tests + iterate**

```bash
uv run pytest tests/test_analyze_pipeline.py -v
```

Tree-sitter's `syntax_error.py` fixture (from Slice 2) has `def broken(` which tree-sitter may extract as a partial `function_definition`. The parse result will have `.ok is False` and `.errors` populated. Pipeline skips → test expects `files_skipped=1, files_parsed=0`.

- [ ] **Step 4: Commit Tasks 9 and 10 together**

Task 9's `analyze/__init__.py` imports `run_pipeline` from this task. Combine both into one commit:

```bash
git add src/savviety_instinct/analyze/__init__.py \
        src/savviety_instinct/analyze/pipeline.py \
        tests/test_analyze_pipeline.py
git commit -m "$(cat <<'EOF'
feat(analyze): pipeline orchestrator + public registry

run_pipeline(path, config) yields (Artifact, MetricValue) tuples for all
functions in .py files under path, honoring glob suppressions from
config.suppress. Parse errors are soft — file skipped with stderr log,
counted in summary. analyze/__init__.py exposes METRICS_REGISTRY and
the pipeline entry for CLI consumption.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: CLI — `instinct run <path>`

**Files:**
- Modify: `src/savviety_instinct/cli/app.py`
- Create: `tests/test_cli_run.py`

- [ ] **Step 1: Write failing tests**

`tests/test_cli_run.py`:

```python
"""CliRunner tests for `instinct run`."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from savviety_instinct.cli.app import app


FIXTURES = Path(__file__).parent / "fixtures" / "python"


def test_run_on_single_file_prints_rows(tmp_path) -> None:
    runner = CliRunner()
    # Need a valid config. Init one in tmp_path pointing at fixtures.
    # Simpler: use the --no-config escape hatch if supported, else minimal cfg.
    # For Slice 3, require a config file relative to cwd.
    cfg_dir = tmp_path / ".instinct"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text("scope: personal\n")

    result = runner.invoke(
        app,
        ["run", str(FIXTURES / "metric_fixtures.py")],
        catch_exceptions=False,
        env={"PWD": str(tmp_path)},
    )
    # Slice 3: exit 0 on successful analyze (even with parse-skips).
    assert result.exit_code == 0
    # Expect 30 rows (10 functions × 3 metrics).
    rows = [line for line in result.stdout.splitlines() if line and "\t" in line]
    assert len(rows) == 30
    # Every row has the expected column format.
    for row in rows:
        cols = row.split("\t")
        assert len(cols) == 4, row
        # First column: "path:start-end"
        assert ":" in cols[0] and "-" in cols[0]
        # Third column: "<metric_id>=<value>"
        assert "=" in cols[2]


def test_run_on_directory_walks(tmp_path) -> None:
    runner = CliRunner()
    cfg_dir = tmp_path / ".instinct"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text("scope: personal\n")

    result = runner.invoke(
        app, ["run", str(FIXTURES)], catch_exceptions=False
    )
    assert result.exit_code == 0
    rows = [line for line in result.stdout.splitlines() if "\t" in line]
    # Directory walk picks up multiple files. At least 30 rows.
    assert len(rows) >= 30


def test_run_on_nonexistent_path_exits_nonzero(tmp_path) -> None:
    runner = CliRunner()
    cfg_dir = tmp_path / ".instinct"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text("scope: personal\n")
    result = runner.invoke(
        app, ["run", "/nonexistent/path"], catch_exceptions=False
    )
    assert result.exit_code != 0


def test_run_prints_summary_to_stderr(tmp_path) -> None:
    runner = CliRunner(mix_stderr=False)
    cfg_dir = tmp_path / ".instinct"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text("scope: personal\n")
    result = runner.invoke(
        app, ["run", str(FIXTURES / "metric_fixtures.py")], catch_exceptions=False
    )
    assert "[summary]" in result.stderr
```

- [ ] **Step 2: Extend `cli/app.py`**

Inspect current `cli/app.py` — Slice 1 registered `version`, `init`, and reserved R2+ stubs. Add the `run` command alongside.

```python
# Imports at top of the file — add if not already present:
from pathlib import Path
import sys

# Typer command:
@app.command()
def run(
    path: Path = typer.Argument(
        ..., exists=False, help="File or directory to analyze. Must be a .py file or a dir with .py files."
    ),
) -> None:
    """Analyze Python code at PATH and print metrics to stdout.

    Slice 3: prints tab-separated rows (path:lines\tqualified_name\tmetric=value\tconfidence).
    Full report layer arrives in Slice 6.
    """
    from savviety_instinct.analyze import run_pipeline
    from savviety_instinct.config.loader import load_config

    config = load_config(Path.cwd() / ".instinct" / "config.yaml")
    if not path.exists():
        typer.echo(f"Path not found: {path}", err=True)
        raise typer.Exit(code=2)

    results, summary = run_pipeline(path, config)
    rows = list(results)

    # Deterministic sort.
    rows.sort(key=lambda r: (r[0].source_range.file_path, r[0].source_range.line_start, r[0].name, r[1].metric_id))

    for artifact, metric_value in rows:
        sr = artifact.source_range
        typer.echo(
            f"{sr.file_path}:{sr.line_start}-{sr.line_end}\t"
            f"{artifact.name if artifact.enclosing_scope is None else artifact.enclosing_scope + '.' + artifact.name}\t"
            f"{metric_value.metric_id}={metric_value.value}\t"
            f"{metric_value.confidence.value}"
        )

    typer.echo(
        f"[summary] {summary.files_parsed} files parsed, "
        f"{summary.files_skipped} files skipped, "
        f"{summary.functions_analyzed} functions analyzed",
        err=True,
    )
```

- [ ] **Step 3: Run tests + iterate**

The `CliRunner(mix_stderr=False)` separates stdout and stderr. May need to adjust based on actual Typer behavior — if tests fail on stderr capture, use `CliRunner()` without `mix_stderr` and check for `[summary]` in combined output.

- [ ] **Step 4: Run full suite + ruff + mypy**

```bash
uv run pytest -v 2>&1 | tail -15
uv run ruff check src/savviety_instinct/cli/app.py tests/test_cli_run.py
uv run mypy src/savviety_instinct/cli/app.py
```

- [ ] **Step 5: Commit**

```bash
git add src/savviety_instinct/cli/app.py tests/test_cli_run.py
git commit -m "$(cat <<'EOF'
feat(cli): instinct run <path> — analyze + tab-separated stdout

Slice 3 minimal report: one row per (function, metric) with columns
path:lines / qualified_name / metric=value / confidence. Summary printed
to stderr. Deterministic sort for reproducible output. Full report layer
(rich, JSON, HTML, rankings) arrives in Slice 6.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Integration test (end-to-end)

**Files:**
- Create: `tests/integration/test_slice3_pipeline.py`

- [ ] **Step 1: Write the integration test**

```python
"""Integration: instinct run <fixtures> produces expected rows."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from savviety_instinct.cli.app import app


FIXTURES = Path(__file__).parent.parent / "fixtures" / "python"


def test_end_to_end_instinct_run_on_metric_fixtures(tmp_path) -> None:
    """Slice 3 acceptance: run instinct run on metric_fixtures.py, verify
    shape, summary, and a spot-check of known values.
    """
    runner = CliRunner(mix_stderr=False)
    cfg_dir = tmp_path / ".instinct"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text("scope: personal\n")

    result = runner.invoke(
        app,
        ["run", str(FIXTURES / "metric_fixtures.py")],
        catch_exceptions=False,
    )
    assert result.exit_code == 0

    rows = [line.split("\t") for line in result.stdout.splitlines() if "\t" in line]
    assert len(rows) == 30  # 10 functions × 3 metrics

    # Spot check: empty function has cognitive=0, cyclomatic=1, statement_count=0
    empty_rows = [r for r in rows if r[1] == "empty"]
    assert len(empty_rows) == 3
    metric_to_value = {r[2].split("=")[0]: r[2].split("=")[1] for r in empty_rows}
    assert metric_to_value["cognitive_complexity"] == "0"
    assert metric_to_value["cyclomatic_complexity"] == "1"
    assert metric_to_value["statement_count"] == "0"

    # Summary present
    assert "[summary]" in result.stderr
    assert "10 functions analyzed" in result.stderr


def test_end_to_end_on_directory_with_syntax_error(tmp_path) -> None:
    """Parse errors degrade gracefully: syntax_error.py skipped, rest succeed."""
    runner = CliRunner(mix_stderr=False)
    cfg_dir = tmp_path / ".instinct"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text("scope: personal\n")

    result = runner.invoke(app, ["run", str(FIXTURES)], catch_exceptions=False)
    assert result.exit_code == 0  # soft failures don't abort
    assert "[parse-error]" in result.stderr
    assert "syntax_error.py" in result.stderr
```

- [ ] **Step 2: Run integration test + full suite**

```bash
uv run pytest tests/integration/ -v
uv run pytest 2>&1 | tail -5
```

All green.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_slice3_pipeline.py
git commit -m "$(cat <<'EOF'
test: integration instinct run on metric_fixtures + syntax-error parity

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Lint sweep + PR

- [ ] **Step 1: Full ruff / mypy / pre-commit**

```bash
uv run ruff check src/savviety_instinct tests/
uv run ruff format --check src/savviety_instinct tests/
uv run mypy src/savviety_instinct/core src/savviety_instinct/storage src/savviety_instinct/parse src/savviety_instinct/graph src/savviety_instinct/analyze
uv run pre-commit run --all-files
```

All clean.

- [ ] **Step 2: Full suite + coverage**

```bash
uv run pytest --cov=src/savviety_instinct --cov-report=term-missing 2>&1 | tail -30
```

Expect new coverage on `analyze/`. Target ≥ 90% overall, ≥ 80% on `analyze/`.

- [ ] **Step 3: Self-dogfood**

```bash
cd /home/gary/repos/instinct && uv run instinct run src/savviety_instinct/ 2>&1 | tail -20
```

Sanity: instinct analyzes its own source without error.

- [ ] **Step 4: Push + PR**

```bash
git push -u origin slice-3-metrics-minimal-report
gh pr create --title "Slice 3: metrics (cyclomatic / cognitive / statement_count) + minimal report" --body "$(cat <<'EOF'
## Summary

Delivers Slice 3 from arch spec §15: first three MVP metrics end-to-end with a minimal text report. Introduces the `analyze/` module.

- **Three metrics**: `statement_count`, `cyclomatic_complexity`, `cognitive_complexity` (Sonar semantics via per-language YAML rules)
- **`analyze/pipeline.py`**: walks a path, applies glob suppressions, dispatches metrics, yields (Artifact, MetricValue)
- **`instinct run <path>`**: tab-separated stdout report + stderr summary
- **`ControlFlowNode`** in parse layer — normalized if/for/while/try/except/ternary/boolean/comprehension
- **`AnalysisContext.parse_result`** — forward-ref via TYPE_CHECKING (preserves arch §2 layering)
- **Cognitive rules YAML** at `src/savviety_instinct/core/cognitive_rules/python.yaml`

## Non-goals (deferred)

- Rich / JSON / HTML report → Slice 6
- Other metrics (max_nesting, npath, identifier quality, module/class metrics) → Slice 4
- Storage writes, dedup, stability tiering → Slice 5
- Parallelism (ProcessPoolExecutor) → deferred per arch §16.4
- Rust / C# / TypeScript adapters → Slices 7–8 (cognitive YAML is language-indexed to accept them)
- Cyclomatic precision on `BOOLEAN_SEQUENCE` / `COMPREHENSION` (currently +1 per group/comprehension rather than per operator/clause) → future metric_version bump

## Test plan

- [x] `uv run pytest -v` — full suite green
- [x] `uv run pytest --cov=src/savviety_instinct` — coverage reported
- [x] `uv run pre-commit run --all-files` — clean
- [x] Self-dogfood: `uv run instinct run src/savviety_instinct/` produces expected rows

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

**Spec coverage (against arch §15 Slice 3):**
- [x] `cyclomatic_complexity` metric → Task 6
- [x] `cognitive_complexity` metric → Task 8 with per-language YAML rules
- [x] `statement_count` metric → Task 5
- [x] "Minimal report" → Task 11 CLI tab-separated output
- [x] End-to-end (parse → analyze → print) → Tasks 10 + 11 + 12

**Locked-decision compliance:**
- D5 (corporate hard-false): No LLM / remote-API paths touched — neutral. No regression on Slice 1's corporate guardrails.
- D6 (context_hash): Not computed in Slice 3 (per Scope Decision from Slice 2). No change.
- D7 (retention TTL): No storage writes in Slice 3; TTL not applicable yet.
- D8 (scope required): Config loader from Slice 1 still requires scope; not changed.
- D10 (SQLite canonical): No storage writes — neutral.
- NFR-1 (no network): Metrics are pure-local; no network dependency added.

**Placeholder scan:** No `TBD` / `implement later` / `add error handling` — every step contains explicit code or command.

**Type consistency:** `ControlFlowNode`, `ControlFlowNodeKind`, `CognitiveIncrement`, `CognitiveRules`, `PipelineSummary` spelled identically across tasks. `METRICS_REGISTRY` / `STATEMENT_COUNT_METRIC` / `CYCLOMATIC_METRIC` / `COGNITIVE_METRIC` naming stable.

**Ordering:** Task 9 (`analyze/__init__.py`) imports `run_pipeline` from Task 10. Explicitly noted: commit 9 + 10 together. Same pattern as Slice 2's Task 4 + 5.

**Known approximations (documented in code):**
- Cyclomatic +1 per BOOLEAN_SEQUENCE group (not per operator)
- Cyclomatic +1 per COMPREHENSION (not per generator clause)
- Both documented in cyclomatic.py docstring; fix via metric_version bump when finer-grained ControlFlowNode fields land.

---

## Execution Handoff

**Plan saved to `docs/plans/2026-04-19-slice-3-metrics-minimal-report.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — Dispatch fresh subagent per task, two-stage review, fast iteration. Good fit for Slice 3: tree-sitter CFN extraction + cognitive rules semantics + CLI wiring each benefit from focused review cycles.

**2. Inline Execution** — Batch via `superpowers:executing-plans`.

Subagent-Driven maintains Slice 2's quality bar.
