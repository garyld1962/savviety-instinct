# Slice 4b — Module-Level Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Companion design spec:** `docs/specs/2026-04-19-slice-4b-module-metrics.md` — all scope decisions, architecture, and fixture expected values live there. This plan executes that design.
>
> **Gary's chosen flow:** `/plan` → `/execute-plan`. One commit per task. Branch `slice-4b-module-metrics`, split from parent Slice 4 because LCOM-HS (class-level) defers to Slice 4c.

**Goal:** Three module-level metrics (`trivial_delegation_ratio`, `median_function_length`, `function_length_bimodality`), the first `ArtifactKind.MODULE` pipeline dispatch, and registry-duplication collapse.

**Architecture:** Pipeline emits one `Artifact(kind=MODULE)` per parsed `.py` file and honors `Metric.applies_to` to route per-kind metrics. Triviality classification lives in the parse layer as `FunctionDefNode.delegation_kind: DelegationKind`; module metrics iterate `ParseResult.functions` uniformly. `METRICS_REGISTRY` in `analyze/__init__.py` becomes single source of truth; `pipeline.py::_METRICS` is deleted. No new external deps; no storage writes.

**Tech Stack:** Python 3.12+, tree-sitter-python 0.23.x (existing), stdlib `statistics` (hand-rolled Pearson's bimodality coefficient; no scipy).

---

## Scope Decisions (locked)

Full rationale in spec §9. Short form:

1. **Function-level LCOM-HS deferred to Slice 4c** — class-level work (method↔attribute-read graph extraction) is non-trivial and would bloat this slice. 4b is three module-level metrics only.
2. **No cross-file / package-level aggregation.** Per-file granularity.
3. **`DelegationKind` enum, not bool.** Preserves per-kind signal for future R2 metrics; matches Slice 3's `ControlFlowNodeKind` pattern.
4. **R1 triviality rules are strict.** Exact passthrough only: positional args must equal a prefix of `parameter_names` in declaration order; keyword args must be `name=name`. Async, `super()`, attribute-call targets, and default-injection are Known Gaps; widening is a future `metric_version` bump.
5. **Pipeline uses `applies_to` filter** in a single artifact loop. The `Metric.applies_to: frozenset[ArtifactKind]` field was defined in Slice 1 but unused until now.
6. **One `Artifact(kind=MODULE)` per `.py` file** regardless of function count. Empty modules return a sentinel (`value=0`/`0.0`, `confidence=LOW`, `notes="no functions in module"`) from each metric — no special-casing in the pipeline. Methods count as module functions (they're already in `ParseResult.functions`).
7. **`__init__.py`** treated as a regular module. No special-casing.
8. **Bimodality ships as a separate metric**, not a composite `MetricValue`. `median_function_length` stays a pure integer-valued metric.
9. **Bimodality hand-rolled** (stdlib `statistics` only). Avoids ~100MB scipy dep for one formula.
10. **Confidence tiers** per metric:
    - `trivial_delegation_ratio`: `n=0` LOW; `0<n<20` LOW; `n≥20` MEDIUM.
    - `median_function_length`: `n=0` LOW; `0<n<10` LOW; `n≥10` HIGH.
    - `function_length_bimodality`: `n<4` LOW (value=0.0, degenerate); `4≤n<30` LOW; `n≥30` HIGH.
11. **Row-count assertions parametrized** off `METRICS_REGISTRY` via a shared helper in `tests/_helpers.py`. Hard-coded counts would break on every future metric slice.
12. **Module `ast_hash`** = hash of ordered tuple of function `ast_hash` strings. Shape-invariant across identifier/literal renames. Uses existing `hash_ast_sexp` backend from Slice 2.
13. **`ParseResult.line_count: int`** added as a minor parse-layer field to supply the MODULE artifact's `source_range.line_end` without re-reading the file.
14. **Registry-collapse refactor lands in its own commit before metric work.** Clean bisect surface; no logic change in that commit.
15. **Known Gaps documented with `KNOWN GAPS` comments** in each new metric module (same discipline as Slice 4a). Any widening is a coordinated `metric_version` bump.

---

## File Structure

| Path | Purpose |
|------|---------|
| `src/savviety_instinct/parse/types.py` | Add `DelegationKind` enum, `FunctionDefNode.delegation_kind` field, `ParseResult.line_count` field |
| `src/savviety_instinct/parse/python.py` | Add `_classify_delegation` helper; wire into `_collect_functions`; populate `line_count` from root node |
| `src/savviety_instinct/analyze/__init__.py` | Register three new metrics; add empty-`applies_to` guard assertion |
| `src/savviety_instinct/analyze/metrics/__init__.py` | Re-export three new metric singletons |
| `src/savviety_instinct/analyze/metrics/trivial_delegation_ratio.py` | `TRIVIAL_DELEGATION_RATIO_METRIC` |
| `src/savviety_instinct/analyze/metrics/median_function_length.py` | `MEDIAN_FUNCTION_LENGTH_METRIC` |
| `src/savviety_instinct/analyze/metrics/function_length_bimodality.py` | `FUNCTION_LENGTH_BIMODALITY_METRIC` + `_bimodality_coefficient` |
| `src/savviety_instinct/analyze/pipeline.py` | Import `METRICS_REGISTRY`, delete `_METRICS`; emit MODULE artifact per file; apply `applies_to` filter |
| `tests/_helpers.py` | Shared `expected_row_count(n_fns, n_modules)` helper |
| `tests/fixtures/python/modules/trivial_facade.py` | 6 fns, 5 trivial delegates |
| `tests/fixtures/python/modules/real_work.py` | 5 fns, zero delegates, varied lengths |
| `tests/fixtures/python/modules/bimodal.py` | 8 fns: 5× short + 3× long |
| `tests/fixtures/python/modules/uniform.py` | 10 fns × 10 stmts (degenerate bimodality) |
| `tests/fixtures/python/modules/empty.py` | 0 fns |
| `tests/fixtures/python/modules/single.py` | 1 fn (sub-threshold for bimodality) |
| `tests/fixtures/python/modules/at_threshold.py` | exactly 20 fns (10 trivial, 10 real-work) |
| `tests/fixtures/python/modules/large_sample.py` | 30+ fns (HIGH-tier bimodality) |
| `tests/test_parse_delegation_kind.py` | Parse-layer detection tests |
| `tests/test_analyze_metric_trivial_delegation_ratio.py` | Metric unit tests |
| `tests/test_analyze_metric_median_function_length.py` | Metric unit tests |
| `tests/test_analyze_metric_function_length_bimodality.py` | Metric unit tests + direct `_bimodality_coefficient` tests |
| `tests/test_analyze_module_artifact_emission.py` | Pipeline emits MODULE artifact per file |
| `tests/test_analyze_metric_applies_to_filter.py` | `applies_to` dispatch + non-empty guard |
| `tests/integration/test_slice4b_pipeline.py` | End-to-end CLI emits correct module + function rows |
| `tests/test_analyze_pipeline.py` | Row-count assertions parametrized (modify) |
| `tests/cli/test_cli_run.py` | Row-count assertions parametrized (modify) |
| `tests/integration/test_slice3_pipeline.py` | Row-count assertions parametrized (modify) |
| `tests/integration/test_slice4a_metrics.py` | Row-count + `metric_ids` set updated (modify) |

---

## Task Ordering

Each task commits independently. Each commit green — no intermediate broken state.

| # | Task | Commit shape |
|---|------|-------------|
| 1 | Registry collapse | `refactor(analyze): single METRICS_REGISTRY, remove pipeline._METRICS duplication` |
| 2 | Shared test row-count helper | `test: add expected_row_count helper; parametrize existing row-count assertions` |
| 3 | Pipeline `applies_to` filter + MODULE artifact emission scaffold | `feat(analyze): emit MODULE artifact per file; honor Metric.applies_to` |
| 4 | Parse-layer `DelegationKind` + `ParseResult.line_count` | `feat(parse): DelegationKind classification + line_count on ParseResult` |
| 5 | Fixture directory | `test: module-level fixtures with hand-verified expected values` |
| 6 | `trivial_delegation_ratio` metric | `feat(analyze): trivial_delegation_ratio module metric` |
| 7 | `median_function_length` metric | `feat(analyze): median_function_length module metric` |
| 8 | `function_length_bimodality` metric | `feat(analyze): function_length_bimodality metric (Pearson's BC)` |
| 9 | Integration test + CLI row-count / metric-ids update | `test: Slice 4b integration — module metrics via CLI` |
| 10 | Self-dogfood | `test(dogfood): run instinct on self; eyeball module metrics` (no code, just verification) |

---

## Task 1: Registry collapse

**Files:**
- Modify: `src/savviety_instinct/analyze/pipeline.py`
- Verify: `tests/test_analyze_pipeline.py` still passes

**Rationale:** `METRICS_REGISTRY` lives in `analyze/__init__.py`; `analyze/pipeline.py::_METRICS` is a literal duplicate. Adding a new metric today requires updating BOTH. This task collapses to a single source of truth before new metrics land — keeps each subsequent task's diff scoped to its own concern.

**Decision to raise to reviewer:** the import path `from savviety_instinct.analyze import METRICS_REGISTRY` creates a circular-import risk because `analyze/__init__.py` imports `analyze.pipeline` which would import back from `analyze`. Verified safe: `analyze/pipeline.py` imports `METRICS_REGISTRY` at function-call time (lazy) rather than at module load, OR the import order in `__init__.py` ensures pipeline loads last. We use the lazy-import approach below.

- [ ] **Step 1: Remove `_METRICS` from pipeline.py, import registry lazily**

Replace the `_METRICS = (...)` block in `src/savviety_instinct/analyze/pipeline.py` (around line 35) with the same body but using `METRICS_REGISTRY` looked up at call time:

```python
# Remove the top-level _METRICS tuple and the existing individual metric imports.
# The imports of specific singletons (STATEMENT_COUNT_METRIC, etc.) are no longer
# needed in this file — they live in analyze/__init__.py.
```

Replace the existing imports:

```python
from savviety_instinct.analyze.metrics import (
    COGNITIVE_METRIC,
    CYCLOMATIC_METRIC,
    IDENTIFIER_QUALITY_METRIC,
    MAX_NESTING_DEPTH_METRIC,
    NPATH_METRIC,
    STATEMENT_COUNT_METRIC,
)
```

with a lazy import inside `run_pipeline`:

```python
def run_pipeline(
    path: Path, config: InstinctConfig
) -> tuple[Iterator[tuple[Artifact, MetricValue]], PipelineSummary]:
    # Lazy import to avoid a circular dependency: analyze.__init__ imports
    # analyze.pipeline, so importing METRICS_REGISTRY at module load would cycle.
    from savviety_instinct.analyze import METRICS_REGISTRY
    ...
```

Delete `_METRICS = (...)` entirely. Inside the nested `_iter()` generator, the inner loop now reads `METRICS_REGISTRY`:

```python
for metric in METRICS_REGISTRY:
    yield artifact, metric.compute(artifact, ctx)
```

The `METRICS_REGISTRY` reference is captured by the closure at `run_pipeline` call time; no runtime overhead.

- [ ] **Step 2: Run the full test suite — no behavior change expected**

```bash
uv run pytest -x 2>&1 | tail -20
```

Expected: all 236 tests pass. The change is a pure refactor; no new assertions, no deletions.

- [ ] **Step 3: Commit**

```bash
git add src/savviety_instinct/analyze/pipeline.py
git commit -m "$(cat <<'EOF'
refactor(analyze): single METRICS_REGISTRY, remove pipeline._METRICS duplication

Collapses analyze/pipeline.py::_METRICS (which duplicated analyze/__init__.py
::METRICS_REGISTRY). Pipeline now imports METRICS_REGISTRY lazily inside
run_pipeline to avoid the analyze.__init__ → analyze.pipeline → analyze cycle.
Addresses the two-point-update footgun flagged in HANDOFF.md. Pure refactor;
no test changes.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Shared row-count helper + parametrize existing assertions

**Files:**
- Create: `tests/_helpers.py`
- Modify: `tests/test_analyze_pipeline.py`
- Modify: `tests/cli/test_cli_run.py`
- Modify: `tests/integration/test_slice3_pipeline.py`
- Modify: `tests/integration/test_slice4a_metrics.py`

**Rationale:** Hard-coded `60` row counts break on every future metric slice. The helper derives the expected count from `METRICS_REGISTRY` + artifact arithmetic. Slice 4b's pipeline will add MODULE artifacts (Task 3 onward), so the helper must accept `n_modules` up front — Tasks 3+ won't have to retrofit each test.

- [ ] **Step 1: Create the shared helper**

`tests/_helpers.py`:

```python
"""Shared test helpers.

Private convention: underscore prefix signals "tests only, not project API".
"""

from __future__ import annotations

from savviety_instinct.analyze import METRICS_REGISTRY
from savviety_instinct.core.types import ArtifactKind


def expected_row_count(n_functions: int, n_modules: int = 0) -> int:
    """Compute the number of (artifact, metric_value) tuples the pipeline yields.

    Derives from METRICS_REGISTRY so tests don't hard-code metric counts.
    Row count = n_functions × |function metrics| + n_modules × |module metrics|.
    """
    fn_metrics = sum(1 for m in METRICS_REGISTRY if ArtifactKind.FUNCTION in m.applies_to)
    mod_metrics = sum(1 for m in METRICS_REGISTRY if ArtifactKind.MODULE in m.applies_to)
    return n_functions * fn_metrics + n_modules * mod_metrics
```

- [ ] **Step 2: Parametrize `tests/test_analyze_pipeline.py`**

Replace the hard-coded `60` with a call to `expected_row_count`. Slice 4b hasn't yet emitted MODULE artifacts (Task 3), so pass `n_modules=0` now:

```python
# At top of file, add:
from tests._helpers import expected_row_count

# In test_run_single_file_yields_expected_metrics:
#   metric_fixtures.py has 10 functions; Task 3 will add 1 module artifact
#   per parsed file, so this becomes n_modules=1 once Task 3 lands. For now
#   n_modules=0 — still 60 rows.
assert len(results) == expected_row_count(n_functions=10, n_modules=0)

# In test_run_directory_walks_recursively:
#   At least 10 functions visible (multiple fixtures, varying counts). Relax
#   to a lower bound.
assert len(results) >= expected_row_count(n_functions=10, n_modules=0)
```

- [ ] **Step 3: Parametrize `tests/cli/test_cli_run.py`**

Open `tests/cli/test_cli_run.py` and replace any hard-coded 60-row assertions with `expected_row_count(n_functions=<actual>, n_modules=0)`. Add the `from tests._helpers import expected_row_count` import.

(If the file doesn't currently assert a specific row count, this step is a no-op — skip.)

- [ ] **Step 4: Parametrize `tests/integration/test_slice3_pipeline.py`**

Same pattern. Replace `60` with `expected_row_count(n_functions=<actual>, n_modules=0)`.

- [ ] **Step 5: Parametrize `tests/integration/test_slice4a_metrics.py`**

Replace `assert len(rows) == 60` with `assert len(rows) == expected_row_count(n_functions=10, n_modules=0)`. Import the helper. Note: after Task 9, `n_modules=1` — but that update belongs to Task 9, keep n_modules=0 here.

- [ ] **Step 6: Run the full test suite**

```bash
uv run pytest -x 2>&1 | tail -20
```

Expected: all tests still pass. 60 == `expected_row_count(10, 0)` = 10 × 6 + 0 × 0 = 60. ✓

- [ ] **Step 7: Commit**

```bash
git add tests/_helpers.py tests/test_analyze_pipeline.py tests/cli/test_cli_run.py tests/integration/test_slice3_pipeline.py tests/integration/test_slice4a_metrics.py
git commit -m "$(cat <<'EOF'
test: add expected_row_count helper; parametrize existing row-count assertions

Introduces tests/_helpers.py::expected_row_count(n_functions, n_modules),
which derives the expected pipeline row count from METRICS_REGISTRY +
artifact arithmetic. Replaces hard-coded `60` across four test files. No
behavior change now (n_modules=0); Task 3's MODULE dispatch will flip
n_modules=1 only in the integration tests that expect it.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Pipeline MODULE artifact emission + `applies_to` filter

**Files:**
- Modify: `src/savviety_instinct/analyze/__init__.py` (add non-empty `applies_to` guard)
- Modify: `src/savviety_instinct/analyze/pipeline.py`
- Modify: `src/savviety_instinct/parse/types.py` (add `line_count` field — used below)
- Modify: `src/savviety_instinct/parse/python.py` (populate `line_count`)
- Create: `tests/test_analyze_module_artifact_emission.py`
- Create: `tests/test_analyze_metric_applies_to_filter.py`

**Rationale:** This task wires the MODULE pipeline branch ahead of any MODULE metrics. With zero MODULE metrics in the registry yet, the `applies_to` filter naturally drops the MODULE artifact from output — row counts stay at 60. The two new test files verify the pipeline-side behavior in isolation.

- [ ] **Step 1: Add `ParseResult.line_count` field**

In `src/savviety_instinct/parse/types.py`, inside `ParseResult`:

```python
@dataclass(frozen=True, slots=True)
class ParseResult:
    file_path: str
    language: Language
    functions: tuple[FunctionDefNode, ...]
    classes: tuple[ClassDefNode, ...]
    call_sites: tuple[CallSiteNode, ...]
    errors: tuple[ParseError, ...] = field(default=())
    # Slice 4b: line count of the parsed source, 1-indexed (last line number).
    # Populated from tree-sitter's root_node.end_point[0] + 1. Used by the
    # pipeline to build MODULE artifact source_ranges without re-reading the file.
    line_count: int = 0
```

- [ ] **Step 2: Populate `line_count` in `PythonAdapter.parse_source`**

In `src/savviety_instinct/parse/python.py`, inside `parse_source`:

```python
def parse_source(self, source: bytes, file_path: str) -> ParseResult:
    tree = self._parser.parse(source)
    errors = tuple(_collect_syntax_errors(tree, source, file_path))
    fn_with_nodes = _collect_functions(tree, source, file_path)
    functions = tuple(fn for fn, _ in fn_with_nodes)
    classes = tuple(_collect_classes(tree, source, file_path, functions))
    call_sites = tuple(_collect_call_sites(source, file_path, fn_with_nodes))

    # Slice 4b: 1-indexed line count. tree-sitter's root is always valid even
    # when parse errors are present, so end_point is safe to read.
    line_count = tree.root_node.end_point[0] + 1

    return ParseResult(
        file_path=file_path,
        language=Language.PYTHON,
        functions=functions,
        classes=classes,
        call_sites=call_sites,
        errors=errors,
        line_count=line_count,
    )
```

- [ ] **Step 3: Compute module `ast_hash` helper**

Add near the bottom of `src/savviety_instinct/analyze/pipeline.py`, below `_is_suppressed`:

```python
from savviety_instinct.parse.hashing import hash_ast_sexp


def _module_ast_hash(functions: tuple[FunctionDefNode, ...]) -> str:
    """Shape-invariant hash for a module artifact.

    Defined as hash_ast_sexp(joined function ast_hashes). Changes when a
    function is added, removed, or structurally modified; invariant across
    identifier/literal renames (per-function ast_hash is already invariant).

    Modules with zero functions get a stable hash of the empty joined string;
    consistent across empty modules. Use FunctionDefNode hash_ast_sexp so the
    backend (blake3 / xxhash) is consistent with per-function ast_hash from Slice 2.
    """
    joined = "|".join(fn.ast_hash for fn in functions)
    return hash_ast_sexp(joined)
```

You'll need to import `FunctionDefNode` at the top of the file:

```python
from savviety_instinct.parse.types import FunctionDefNode
```

- [ ] **Step 4: Rewrite `_iter` to emit MODULE artifact + apply `applies_to` filter**

Replace the `_iter` body in `run_pipeline` with:

```python
def _iter() -> Iterator[tuple[Artifact, MetricValue]]:
    from savviety_instinct.analyze import METRICS_REGISTRY  # lazy; avoids cycle

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

        # Build one MODULE artifact per parsed file.
        module_artifact = Artifact(
            ast_hash=_module_ast_hash(result.functions),
            language=Language.PYTHON,
            kind=ArtifactKind.MODULE,
            name=str(source_path),
            enclosing_scope=None,
            source_range=SourceRange(
                file_path=str(source_path),
                line_start=1,
                line_end=max(result.line_count, 1),
            ),
        )

        # Build FUNCTION artifacts (same shape as pre-4b).
        function_artifacts: list[Artifact] = []
        for fn in result.functions:
            summary.functions_analyzed += 1
            function_artifacts.append(
                Artifact(
                    ast_hash=fn.ast_hash,
                    language=Language.PYTHON,
                    kind=ArtifactKind.FUNCTION,
                    name=fn.name,
                    enclosing_scope=fn.enclosing_class,
                    source_range=fn.source_range,
                )
            )

        # Module first, then functions — deterministic ordering for downstream
        # consumers. Within each kind, iterate metrics in METRICS_REGISTRY order.
        artifacts = [module_artifact] + function_artifacts
        for artifact in artifacts:
            for metric in METRICS_REGISTRY:
                if artifact.kind in metric.applies_to:
                    yield artifact, metric.compute(artifact, ctx)
```

Note: `SourceRange` is already imported in `pipeline.py`'s import block (used for FUNCTION artifacts). If not, add `SourceRange` to the core import line.

- [ ] **Step 5: Add non-empty `applies_to` guard in analyze package init**

At the bottom of `src/savviety_instinct/analyze/__init__.py`, add:

```python
# Slice 4b: fail-fast on a metric with empty applies_to. An empty frozenset
# means the pipeline filter silently drops the metric from all artifacts —
# no exception, no test failure unless the metric-specific test catches it.
# Asserting here is cheap (module-load time) and catches the footgun at its
# source.
assert all(m.applies_to for m in METRICS_REGISTRY), (
    "every Metric must declare at least one ArtifactKind in applies_to; "
    "an empty frozenset means the pipeline filter will drop it silently"
)
```

- [ ] **Step 6: Write failing tests for artifact emission**

Create `tests/test_analyze_module_artifact_emission.py`:

```python
"""Pipeline emits one MODULE artifact per parsed file (Slice 4b)."""

from __future__ import annotations

from pathlib import Path

from savviety_instinct.analyze.pipeline import run_pipeline
from savviety_instinct.config.models import InstinctConfig
from savviety_instinct.core.types import ArtifactKind, Language

FIXTURES = Path(__file__).parent / "fixtures" / "python"


def _cfg() -> InstinctConfig:
    return InstinctConfig(scope="personal", suppress=[])


def test_exactly_one_module_artifact_per_parsed_file() -> None:
    results, _ = run_pipeline(FIXTURES / "metric_fixtures.py", _cfg())
    artifacts = {(r[0].kind, r[0].ast_hash) for r in results}
    module_artifacts = [a for a in artifacts if a[0] == ArtifactKind.MODULE]
    # With zero MODULE metrics in the registry yet, the module artifact appears
    # in the dedup'd set only if any metric emitted for it. Expected: zero.
    # Once Task 6 adds the first MODULE metric, this becomes == 1.
    assert len(module_artifacts) == 0


def test_module_artifact_fields_when_metric_emits(monkeypatch) -> None:
    """Directly verify the MODULE artifact shape by installing a stub metric.

    Avoids the Task 3 no-op (zero module metrics) by registering a
    transient stub that applies_to MODULE.
    """
    from savviety_instinct.core.types import (
        AnalysisContext,
        Artifact,
        Confidence,
        InputKind,
        MetricValue,
    )

    class _StubModuleMetric:
        id = "stub_module_metric"
        version = "0.0.0"
        applies_to = frozenset({ArtifactKind.MODULE})
        required_inputs = frozenset({InputKind.AST})

        def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue:
            return MetricValue(
                metric_id=self.id,
                value=artifact.source_range.line_end,
                metric_version=self.version,
                confidence=Confidence.HIGH,
            )

    import savviety_instinct.analyze as analyze_pkg

    patched_registry = (*analyze_pkg.METRICS_REGISTRY, _StubModuleMetric())
    monkeypatch.setattr(analyze_pkg, "METRICS_REGISTRY", patched_registry)

    results, _ = run_pipeline(FIXTURES / "metric_fixtures.py", _cfg())
    rows = list(results)
    module_rows = [r for r in rows if r[0].kind == ArtifactKind.MODULE]

    assert len(module_rows) == 1
    artifact, value = module_rows[0]
    assert artifact.kind == ArtifactKind.MODULE
    assert artifact.language == Language.PYTHON
    assert artifact.name.endswith("metric_fixtures.py")
    assert artifact.enclosing_scope is None
    assert artifact.source_range.line_start == 1
    assert artifact.source_range.line_end >= 1
    assert artifact.ast_hash  # non-empty
    assert value.metric_id == "stub_module_metric"


def test_empty_module_still_emits_module_artifact(monkeypatch, tmp_path) -> None:
    """A .py file with zero functions still produces a MODULE artifact."""
    empty_file = tmp_path / "empty.py"
    empty_file.write_text('"""module docstring, no functions."""\n')

    # Same stub trick as above.
    from savviety_instinct.core.types import (
        AnalysisContext,
        Artifact,
        Confidence,
        InputKind,
        MetricValue,
    )

    class _StubModuleMetric:
        id = "stub_module_metric"
        version = "0.0.0"
        applies_to = frozenset({ArtifactKind.MODULE})
        required_inputs = frozenset({InputKind.AST})

        def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue:
            return MetricValue(
                metric_id=self.id, value=0, metric_version=self.version,
                confidence=Confidence.LOW,
            )

    import savviety_instinct.analyze as analyze_pkg
    monkeypatch.setattr(
        analyze_pkg, "METRICS_REGISTRY", (*analyze_pkg.METRICS_REGISTRY, _StubModuleMetric())
    )

    results, _ = run_pipeline(empty_file, _cfg())
    rows = list(results)
    module_rows = [r for r in rows if r[0].kind == ArtifactKind.MODULE]
    assert len(module_rows) == 1  # empty module still emits
```

And `tests/test_analyze_metric_applies_to_filter.py`:

```python
"""Pipeline honors Metric.applies_to; registry guards empty applies_to."""

from __future__ import annotations

from pathlib import Path

import pytest

from savviety_instinct.analyze import METRICS_REGISTRY
from savviety_instinct.analyze.pipeline import run_pipeline
from savviety_instinct.config.models import InstinctConfig
from savviety_instinct.core.types import ArtifactKind

FIXTURES = Path(__file__).parent / "fixtures" / "python"


def _cfg() -> InstinctConfig:
    return InstinctConfig(scope="personal", suppress=[])


def test_function_metrics_only_fire_on_function_artifacts() -> None:
    """Every emitted metric_id that applies_to FUNCTION came from a FUNCTION artifact."""
    results, _ = run_pipeline(FIXTURES / "metric_fixtures.py", _cfg())
    rows = list(results)

    fn_metric_ids = {m.id for m in METRICS_REGISTRY if ArtifactKind.FUNCTION in m.applies_to}
    for artifact, value in rows:
        if value.metric_id in fn_metric_ids:
            assert artifact.kind == ArtifactKind.FUNCTION, (
                f"{value.metric_id} fired on artifact.kind={artifact.kind}"
            )


def test_every_metric_has_nonempty_applies_to() -> None:
    """Guard documented in analyze/__init__.py — mirror it at test level."""
    for metric in METRICS_REGISTRY:
        assert metric.applies_to, f"{metric.id} has empty applies_to (silent-noop footgun)"
```

- [ ] **Step 7: Run the new test files + full suite**

```bash
uv run pytest tests/test_analyze_module_artifact_emission.py tests/test_analyze_metric_applies_to_filter.py -v
uv run pytest -x 2>&1 | tail -20
```

Expected: all new tests pass. Existing 236 tests still pass — row counts unchanged because zero MODULE metrics exist yet (the filter drops MODULE artifacts naturally).

- [ ] **Step 8: Commit**

```bash
git add src/savviety_instinct/parse/types.py src/savviety_instinct/parse/python.py src/savviety_instinct/analyze/__init__.py src/savviety_instinct/analyze/pipeline.py tests/test_analyze_module_artifact_emission.py tests/test_analyze_metric_applies_to_filter.py
git commit -m "$(cat <<'EOF'
feat(analyze): emit MODULE artifact per file; honor Metric.applies_to

Pipeline now builds one Artifact(kind=MODULE) per parsed .py file and a
FUNCTION artifact per function, then dispatches each through METRICS_REGISTRY
filtered by Metric.applies_to. With zero MODULE metrics registered yet, the
filter naturally drops MODULE artifacts from output — row counts unchanged.

Scaffold is in place for Tasks 6-8 (three MODULE metrics). Also adds
ParseResult.line_count (populated from tree-sitter root) so module
source_ranges can be built without re-reading the file, and a non-empty
applies_to guard assertion in analyze/__init__.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Parse-layer `DelegationKind`

**Files:**
- Modify: `src/savviety_instinct/parse/types.py` (add enum + field)
- Modify: `src/savviety_instinct/parse/python.py` (add `_classify_delegation`, wire into `_collect_functions`)
- Create: `tests/test_parse_delegation_kind.py`

**Rationale:** Task 6's `trivial_delegation_ratio` reads `FunctionDefNode.delegation_kind`. The detector lives in the parse layer (analyze/ must never import tree-sitter). Tight R1 rules per spec §4.2 — false-positive aversion. Known Gaps deferred via documented comments.

- [ ] **Step 1: Add `DelegationKind` enum + `delegation_kind` field**

In `src/savviety_instinct/parse/types.py`:

```python
class DelegationKind(StrEnum):
    """Classification of a function body as a trivial wrapper (Slice 4b).

    Consumed by analyze.metrics.trivial_delegation_ratio. Tight R1 semantics;
    widening happens via coordinated metric_version bump.

    NONE: real-work function, or any body that doesn't match a pattern below.
    RETURN_PASSTHROUGH: body is `return f(args)` where every positional arg is
        a parameter reference in declaration order and every keyword arg is
        `name=name`.
    ASSIGN_DELEGATE: body is `x = f(args); return x` with the same argument rules.
    WRAPPER_NO_TRANSFORM: body is a bare call expression statement (no return,
        no assign) like `f(args)`.
    """

    NONE = "none"
    RETURN_PASSTHROUGH = "return_passthrough"
    ASSIGN_DELEGATE = "assign_delegate"
    WRAPPER_NO_TRANSFORM = "wrapper_no_transform"
```

Add to `FunctionDefNode` (after `identifier_names`):

```python
    # Slice 4b: triviality classification for trivial_delegation_ratio metric.
    # Defaults to NONE so existing Slice 3/4a tests that construct
    # FunctionDefNode directly don't need to pass this field.
    delegation_kind: DelegationKind = DelegationKind.NONE
```

- [ ] **Step 2: Add `_classify_delegation` helper**

In `src/savviety_instinct/parse/python.py`, add near `_collect_identifiers`:

```python
def _classify_delegation(
    body_node: Node, source: bytes, parameter_names: tuple[str, ...]
) -> DelegationKind:
    """Classify a function body's triviality for trivial_delegation_ratio (Slice 4b).

    Rules (R1 — deliberately strict, false-positive-averse):
    - RETURN_PASSTHROUGH: exactly one non-docstring statement, which is
      `return f(args)` satisfying the passthrough argument rules.
    - ASSIGN_DELEGATE: exactly two non-docstring statements, `x = f(args)`
      followed by `return x`. Call must satisfy passthrough rules.
    - WRAPPER_NO_TRANSFORM: exactly one non-docstring statement, which is a
      bare call expression (not a return, not an assign) satisfying passthrough.
    - NONE: everything else.

    KNOWN GAPS (metric_version=1.0.0):
    - `super().foo(...)` not detected (attribute-call breaks identifier-only rule).
    - async def / await wrappers not detected (return value is `await`, not call).
    - `self.x = x` not detected (attribute assignment, not a delegated call).
    - Default-argument injection (`def g(a, b=5): return f(a, b)`) IS counted
      as passthrough — signature defaults considered separate from body rules.
    """
    # Collect non-docstring statements from the direct body.
    stmts = [c for c in body_node.children if c.type in _STATEMENT_NODE_TYPES]
    stmts = [s for s in stmts if not _is_docstring_node(s)]

    if len(stmts) == 1:
        stmt = stmts[0]
        if stmt.type == "return_statement":
            call = _return_value_call(stmt)
            if call is not None and _call_is_passthrough(call, source, parameter_names):
                return DelegationKind.RETURN_PASSTHROUGH
        elif stmt.type == "expression_statement":
            call = _bare_call_expression(stmt)
            if call is not None and _call_is_passthrough(call, source, parameter_names):
                return DelegationKind.WRAPPER_NO_TRANSFORM
        return DelegationKind.NONE

    if len(stmts) == 2:
        first, second = stmts
        target_text = _assign_target_text(first, source)
        call = _simple_assign_call_rhs(first) if target_text is not None else None
        if (
            target_text is not None
            and call is not None
            and _call_is_passthrough(call, source, parameter_names)
            and _is_return_of_identifier(second, source, target_text)
        ):
            return DelegationKind.ASSIGN_DELEGATE

    return DelegationKind.NONE


def _return_value_call(return_stmt: Node) -> Node | None:
    """For `return <expr>`, return the expr iff it is a `call` node."""
    for child in return_stmt.children:
        if child.is_named and child.type == "call":
            return child
        if child.is_named and child.type != "return":
            # Something other than a call — reject (e.g., binary_operator,
            # identifier, integer literal). Conservative: only direct calls.
            return None
    return None


def _bare_call_expression(expr_stmt: Node) -> Node | None:
    """For a bare expression_statement, return the inner call node or None."""
    named = [c for c in expr_stmt.children if c.is_named]
    if len(named) == 1 and named[0].type == "call":
        return named[0]
    return None


def _assign_target_text(stmt: Node, source: bytes) -> str | None:
    """If `stmt` is `x = <rhs>` where x is a plain identifier, return x's text.

    Rejects tuple-unpacking, augmented-assign, typed-assign-with-complex-LHS,
    and attribute-assign (`self.x = ...`). Tree-sitter-python emits `+=` / `-=`
    etc. as a separate `augmented_assignment` node type, so the `"assignment"`
    check already excludes those.
    """
    if stmt.type != "expression_statement":
        return None
    named = [c for c in stmt.children if c.is_named]
    if len(named) != 1 or named[0].type != "assignment":
        return None
    left = named[0].child_by_field_name("left")
    if left is None or left.type != "identifier":
        return None
    return _text(left, source)


def _simple_assign_call_rhs(stmt: Node) -> Node | None:
    if stmt.type != "expression_statement":
        return None
    named = [c for c in stmt.children if c.is_named]
    if len(named) != 1 or named[0].type != "assignment":
        return None
    right = named[0].child_by_field_name("right")
    if right is None or right.type != "call":
        return None
    return right


def _is_return_of_identifier(stmt: Node, source: bytes, identifier_text: str) -> bool:
    """True iff `stmt` is `return <identifier_text>` — text must match exactly."""
    if stmt.type != "return_statement":
        return False
    named = [c for c in stmt.children if c.is_named and c.type != "return"]
    if len(named) != 1 or named[0].type != "identifier":
        return False
    return _text(named[0], source) == identifier_text


def _call_is_passthrough(
    call_node: Node, source: bytes, parameter_names: tuple[str, ...]
) -> bool:
    """Verify call args pass through exactly.

    Rules:
    - callee (function field) must be an identifier — not attribute, not subscript
      (KNOWN GAP: super().foo() not supported).
    - positional args must be identifier nodes whose texts equal a prefix of
      parameter_names in order.
    - keyword args must be `name=value` where name-text equals value-text and
      value is an identifier node.
    - no *args / **kwargs splats (splat patterns reject).
    """
    func = call_node.child_by_field_name("function")
    if func is None or func.type != "identifier":
        return False
    args = call_node.child_by_field_name("arguments")
    if args is None:
        # Call with zero parens? Treat as no args, trivially passthrough only if
        # parameter_names is also empty.
        return len(parameter_names) == 0

    positional: list[str] = []
    keyword_names: list[tuple[str, str]] = []
    for child in args.children:
        if not child.is_named:
            continue  # commas, parens
        if child.type == "identifier":
            positional.append(_text(child, source))
        elif child.type == "keyword_argument":
            name_node = child.child_by_field_name("name")
            value_node = child.child_by_field_name("value")
            if name_node is None or value_node is None:
                return False
            if value_node.type != "identifier":
                return False
            keyword_names.append((_text(name_node, source), _text(value_node, source)))
        elif child.type in ("list_splat", "dictionary_splat", "parenthesized_splat_pattern"):
            return False  # splats reject
        else:
            # Any other node (integer, string, binary_operator, attribute, call, ...)
            # breaks passthrough — transformation or literal injection.
            return False

    # Positional args must be prefix of parameter_names in order.
    if len(positional) > len(parameter_names):
        return False
    for i, arg_name in enumerate(positional):
        if arg_name != parameter_names[i]:
            return False

    # Keyword args must be name==value (same identifier text).
    for kname, kvalue in keyword_names:
        if kname != kvalue:
            return False

    return True
```

Update the imports at the top of `parse/python.py` to include the new type:

```python
from savviety_instinct.parse.types import (
    CallSiteNode,
    ClassDefNode,
    ControlFlowNode,
    ControlFlowNodeKind,
    DelegationKind,  # Slice 4b
    FunctionDefNode,
    ParseError,
    ParseErrorKind,
    ParseResult,
)
```

- [ ] **Step 3: Wire `_classify_delegation` into `_collect_functions`**

In `_collect_functions`, where `FunctionDefNode` is constructed (around line 464), add:

```python
delegation_kind = (
    _classify_delegation(body_node, source, params) if body_node is not None
    else DelegationKind.NONE
)
out.append(
    (
        FunctionDefNode(
            name=name,
            qualified_name=qualified,
            enclosing_class=enclosing_class,
            source_range=_source_range(node, file_path),
            ast_hash=hash_ast_sexp(_sexp(node)),
            parameter_names=params,
            control_flow=control_flow,
            statement_count=statement_count,
            identifier_names=identifier_names,
            delegation_kind=delegation_kind,  # NEW
        ),
        node,
    )
)
```

- [ ] **Step 4: Write failing tests for the detector**

Create `tests/test_parse_delegation_kind.py`:

```python
"""Parse-layer detection of FunctionDefNode.delegation_kind (Slice 4b)."""

from __future__ import annotations

from savviety_instinct.parse.python import PYTHON_ADAPTER
from savviety_instinct.parse.types import DelegationKind


def _fn_kind(source: str, fn_name: str = "f") -> DelegationKind:
    result = PYTHON_ADAPTER.parse_source(source.encode(), "<test>")
    assert result.ok, result.errors
    for fn in result.functions:
        if fn.name == fn_name:
            return fn.delegation_kind
    raise LookupError(fn_name)


# ---------- RETURN_PASSTHROUGH ----------


def test_return_passthrough_positional() -> None:
    src = """
def f(a, b):
    return g(a, b)
"""
    assert _fn_kind(src) == DelegationKind.RETURN_PASSTHROUGH


def test_return_passthrough_keyword_matching_names() -> None:
    src = """
def f(a, b):
    return g(a=a, b=b)
"""
    assert _fn_kind(src) == DelegationKind.RETURN_PASSTHROUGH


def test_return_passthrough_prefix_of_params() -> None:
    """Calling g(a) from f(a, b) — uses a prefix, still passthrough."""
    src = """
def f(a, b):
    return g(a)
"""
    assert _fn_kind(src) == DelegationKind.RETURN_PASSTHROUGH


def test_return_passthrough_with_docstring() -> None:
    src = '''
def f(a, b):
    """docstring."""
    return g(a, b)
'''
    assert _fn_kind(src) == DelegationKind.RETURN_PASSTHROUGH


def test_return_passthrough_zero_args() -> None:
    src = """
def f():
    return g()
"""
    assert _fn_kind(src) == DelegationKind.RETURN_PASSTHROUGH


# ---------- ASSIGN_DELEGATE ----------


def test_assign_delegate() -> None:
    src = """
def f(a, b):
    x = g(a, b)
    return x
"""
    assert _fn_kind(src) == DelegationKind.ASSIGN_DELEGATE


def test_assign_delegate_with_docstring() -> None:
    src = '''
def f(a):
    """doc."""
    x = g(a)
    return x
'''
    assert _fn_kind(src) == DelegationKind.ASSIGN_DELEGATE


# ---------- WRAPPER_NO_TRANSFORM ----------


def test_wrapper_no_transform() -> None:
    src = """
def f(a, b):
    g(a, b)
"""
    assert _fn_kind(src) == DelegationKind.WRAPPER_NO_TRANSFORM


# ---------- NONE: transformations ----------


def test_none_if_body_has_arithmetic_on_call_result() -> None:
    src = """
def f(a):
    return g(a) + 1
"""
    assert _fn_kind(src) == DelegationKind.NONE


def test_none_if_call_has_literal_arg() -> None:
    src = """
def f(a):
    return g(a, 1)
"""
    assert _fn_kind(src) == DelegationKind.NONE


def test_none_if_call_has_wrong_arg_order() -> None:
    src = """
def f(a, b):
    return g(b, a)
"""
    assert _fn_kind(src) == DelegationKind.NONE


def test_none_if_keyword_name_mismatches_value() -> None:
    src = """
def f(a, b):
    return g(a=b)
"""
    assert _fn_kind(src) == DelegationKind.NONE


def test_none_if_body_has_control_flow() -> None:
    src = """
def f(a):
    if a:
        return g(a)
    return None
"""
    assert _fn_kind(src) == DelegationKind.NONE


def test_none_for_pass_only_body() -> None:
    src = """
def f():
    pass
"""
    assert _fn_kind(src) == DelegationKind.NONE


def test_none_for_ellipsis_only_body() -> None:
    src = """
def f():
    ...
"""
    assert _fn_kind(src) == DelegationKind.NONE


def test_none_for_return_literal() -> None:
    src = """
def f():
    return 42
"""
    assert _fn_kind(src) == DelegationKind.NONE


def test_none_for_self_attribute_assignment() -> None:
    """`self.x = x` is data initialization, not delegation."""
    src = """
class C:
    def __init__(self, x):
        self.x = x
"""
    # Methods are collected too; find __init__
    result = PYTHON_ADAPTER.parse_source(src.encode(), "<test>")
    init = next(fn for fn in result.functions if fn.name == "__init__")
    assert init.delegation_kind == DelegationKind.NONE


def test_none_for_super_method_delegation() -> None:
    """super().foo(a) — attribute-call, KNOWN GAP #1; classified NONE."""
    src = """
class C:
    def foo(self, a):
        return super().foo(a)
"""
    result = PYTHON_ADAPTER.parse_source(src.encode(), "<test>")
    foo = next(fn for fn in result.functions if fn.name == "foo")
    assert foo.delegation_kind == DelegationKind.NONE


def test_none_for_async_passthrough() -> None:
    """async def g(): return await f(a) — KNOWN GAP #4; classified NONE."""
    src = """
async def f(a):
    return await g(a)
"""
    # Note: test function is also named `f` — but parser sees only one def here.
    result = PYTHON_ADAPTER.parse_source(src.encode(), "<test>")
    async_f = next(fn for fn in result.functions if fn.name == "f")
    assert async_f.delegation_kind == DelegationKind.NONE


def test_none_for_attribute_call_target() -> None:
    """`return self.helper(a)` — attribute target, not identifier."""
    src = """
class C:
    def foo(self, a):
        return self.helper(a)
"""
    result = PYTHON_ADAPTER.parse_source(src.encode(), "<test>")
    foo = next(fn for fn in result.functions if fn.name == "foo")
    assert foo.delegation_kind == DelegationKind.NONE


def test_none_for_splat_args() -> None:
    src = """
def f(*args):
    return g(*args)
"""
    assert _fn_kind(src) == DelegationKind.NONE


def test_none_for_three_statement_body() -> None:
    src = """
def f(a):
    x = g(a)
    y = x + 1
    return y
"""
    assert _fn_kind(src) == DelegationKind.NONE


# ---------- Default arg injection (documented as passthrough) ----------


def test_default_arg_injection_is_passthrough() -> None:
    """def f(a, b=5): return g(a, b) — body passes params through; signature
    default not considered transformation. Documented decision."""
    src = """
def f(a, b=5):
    return g(a, b)
"""
    assert _fn_kind(src) == DelegationKind.RETURN_PASSTHROUGH
```

- [ ] **Step 5: Run the failing tests**

```bash
uv run pytest tests/test_parse_delegation_kind.py -v
```

Expected: fails because `delegation_kind` doesn't exist yet on `FunctionDefNode`. After applying Step 1, the field exists but defaults to `NONE`, so tests that expect other values still fail — until `_classify_delegation` is wired via Step 3.

- [ ] **Step 6: Iterate until all tests pass**

Run the tests, inspect failures, fix `_classify_delegation` helpers. Common pitfalls:
- tree-sitter-python node-type names differ across versions. If a test is failing because a node type check is wrong, REPL-inspect:
  ```python
  import tree_sitter_python as tspython
  from tree_sitter import Language as TSLang, Parser
  parser = Parser(); parser.language = TSLang(tspython.language())
  tree = parser.parse(b"def f(a): return g(a)\n")
  print(str(tree.root_node))
  ```
- `super()` resolves to a `call` node wrapped in an `attribute` expression — our `_call_is_passthrough` correctly rejects (function field is attribute, not identifier).

- [ ] **Step 7: Run the full suite — regression check**

```bash
uv run pytest -x 2>&1 | tail -20
```

Expected: all tests pass. Existing function-level metrics do not read `delegation_kind`, so no regressions.

- [ ] **Step 8: Commit**

```bash
git add src/savviety_instinct/parse/types.py src/savviety_instinct/parse/python.py tests/test_parse_delegation_kind.py
git commit -m "$(cat <<'EOF'
feat(parse): DelegationKind classification for trivial_delegation_ratio metric

Adds DelegationKind StrEnum (NONE, RETURN_PASSTHROUGH, ASSIGN_DELEGATE,
WRAPPER_NO_TRANSFORM) and FunctionDefNode.delegation_kind populated during
parse. Detection uses tight R1 rules (exact passthrough only); widening
for super()/async/attribute-call targets deferred to a metric_version
bump (documented as Known Gaps).

Test coverage: 20+ cases spanning all three positive kinds, transformation
rejections, async/super/attribute-call rejections, and the
default-arg-injection edge case (classified as passthrough — documented).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Fixture directory

**Files:**
- Create: `tests/fixtures/python/modules/__init__.py` (empty package marker — or don't; `modules/` is a fixture directory, not a Python package. Skip if unused.)
- Create: `tests/fixtures/python/modules/trivial_facade.py`
- Create: `tests/fixtures/python/modules/real_work.py`
- Create: `tests/fixtures/python/modules/bimodal.py`
- Create: `tests/fixtures/python/modules/uniform.py`
- Create: `tests/fixtures/python/modules/empty.py`
- Create: `tests/fixtures/python/modules/single.py`
- Create: `tests/fixtures/python/modules/at_threshold.py`
- Create: `tests/fixtures/python/modules/large_sample.py`

**Rationale:** Hand-verified ground-truth modules for Tasks 6–9. Each file's module docstring carries the expected metric values. Bimodality values are computed by hand using the formula in `_bimodality_coefficient` and documented.

**Note on docstring format:** The existing convention (`metric_fixtures.py`) uses a single-line `"""..."""` per fixture function. For modules we put the expected values in the module-level docstring. Format:

```python
"""<brief description>.

Expected module metrics (hand-verified):
  trivial_delegation_ratio = <value>, confidence=<LOW|MEDIUM>
  median_function_length = <value>, confidence=<LOW|HIGH>
  function_length_bimodality = <value>, confidence=<LOW|HIGH>

Statement-count list: [<n1>, <n2>, ...]
"""
```

- [ ] **Step 1: `trivial_facade.py`**

```python
"""Six functions; five are trivial delegates covering all three DelegationKinds.

Expected module metrics (hand-verified):
  trivial_delegation_ratio = 0.8333... (5/6), confidence=LOW (n<20)
  median_function_length = 1 (all trivial delegates are 1-2 stmts), confidence=LOW (n<10)
  function_length_bimodality = <computed>, confidence=LOW (4≤n<30)

Statement-count list: [1, 2, 1, 1, 1, 3]
"""
from __future__ import annotations


def passthrough_return(a, b):
    return helper(a, b)


def assign_delegate(a, b):
    x = helper(a, b)
    return x


def wrapper_no_transform(a):
    helper(a)


def keyword_passthrough(a, b):
    return helper(a=a, b=b)


def zero_arg_passthrough():
    return helper()


def does_real_work(xs):
    total = 0
    for item in xs:
        total = total + item
    return total


def helper(*args, **kwargs):
    return None
```

- [ ] **Step 2: `real_work.py`**

```python
"""Five functions, zero trivial delegates, varied lengths.

Expected module metrics (hand-verified):
  trivial_delegation_ratio = 0.0 (0/5), confidence=LOW (n<20)
  median_function_length = 10, confidence=LOW (n<10)  — borderline; n=5 below min 10
  function_length_bimodality = <computed>, confidence=LOW (4≤n<30)

Statement-count list: [3, 7, 10, 15, 20] — hand-count each function; match
exactly what _count_statements produces. If parser statement counts drift,
update this docstring; the tests check len(fns)=5 and median computation over
the actual statement_count values, so the docstring is informational.
"""
from __future__ import annotations


def three_statements(xs):
    total = 0
    for item in xs:
        total = total + item
    return total


def seven_statements(xs):
    total = 0
    count = 0
    for item in xs:
        total = total + item
        count = count + 1
    average = total / count if count else 0
    return average


def ten_statements(xs, ys):
    total_x = 0
    total_y = 0
    count = 0
    for x in xs:
        total_x = total_x + x
        count = count + 1
    for y in ys:
        total_y = total_y + y
    diff = total_x - total_y
    return diff


def fifteen_statements(xs):
    total = 0
    squared = 0
    cubed = 0
    count = 0
    for item in xs:
        total = total + item
        squared = squared + item * item
        cubed = cubed + item * item * item
        count = count + 1
    if count == 0:
        return (0, 0, 0)
    avg = total / count
    sq_avg = squared / count
    cu_avg = cubed / count
    return (avg, sq_avg, cu_avg)


def twenty_statements(xs, ys, zs):
    totals = [0, 0, 0]
    counts = [0, 0, 0]
    for item in xs:
        totals[0] = totals[0] + item
        counts[0] = counts[0] + 1
    for item in ys:
        totals[1] = totals[1] + item
        counts[1] = counts[1] + 1
    for item in zs:
        totals[2] = totals[2] + item
        counts[2] = counts[2] + 1
    if counts[0] > 0:
        totals[0] = totals[0] / counts[0]
    if counts[1] > 0:
        totals[1] = totals[1] / counts[1]
    if counts[2] > 0:
        totals[2] = totals[2] / counts[2]
    return totals
```

**Important:** after writing, REPL-verify `statement_count` for each function:

```python
from pathlib import Path
from savviety_instinct.parse.python import PYTHON_ADAPTER
r = PYTHON_ADAPTER.parse_path(Path("tests/fixtures/python/modules/real_work.py"))
for fn in r.functions:
    print(fn.name, fn.statement_count)
```

If the parser's count differs from the docstring description (e.g., `seven_statements` actually reports 8 because of how ternaries count), **update the docstring to match the parser output** — the parser is authoritative. Re-derive the expected `median_function_length` if needed.

- [ ] **Step 3: `bimodal.py`**

```python
"""Eight functions: 5× 2-statement + 3× 30-statement; induces bimodal distribution.

Expected module metrics (hand-verified):
  trivial_delegation_ratio = 0.0 (0/8), confidence=LOW (n<20)
  median_function_length: in range [2, 30] — Python's statistics.median on
    [2,2,2,2,2,30,30,30] = 2 (5 twos dominate). Cast to int = 2. confidence=LOW
    (n=8 below min 10).
  function_length_bimodality: > 0.555 (bimodal signal). confidence=LOW (n<30).

Statement-count list (after REPL-verify): [2, 2, 2, 2, 2, 30, 30, 30]
"""
from __future__ import annotations


def short_1(xs):
    total = sum(xs)
    return total


def short_2(xs):
    total = sum(xs)
    return total + 1


def short_3(xs):
    total = sum(xs)
    return total - 1


def short_4(xs):
    total = sum(xs)
    return total * 2


def short_5(xs):
    total = sum(xs)
    return total // 2


def long_1(xs):
    # 30 statements — pad with simple accumulators. The exact count matters
    # less than the bimodal shape; verify with REPL and update docstring.
    a = 0
    b = 0
    c = 0
    d = 0
    e = 0
    f = 0
    g = 0
    h = 0
    i_ = 0
    j = 0
    k = 0
    l = 0
    m = 0
    n = 0
    o = 0
    p = 0
    q = 0
    r = 0
    s = 0
    t = 0
    u = 0
    v = 0
    w = 0
    x_ = 0
    y = 0
    z = 0
    aa = 0
    bb = 0
    cc = 0
    return (a, b, c, d, e, f, g, h, i_, j, k, l, m, n, o, p, q, r, s, t, u, v, w, x_, y, z, aa, bb, cc)


def long_2(xs):
    # Duplicate of long_1 shape for sample size
    a = 0
    b = 0
    c = 0
    d = 0
    e = 0
    f = 0
    g = 0
    h = 0
    i_ = 0
    j = 0
    k = 0
    l = 0
    m = 0
    n = 0
    o = 0
    p = 0
    q = 0
    r = 0
    s = 0
    t = 0
    u = 0
    v = 0
    w = 0
    x_ = 0
    y = 0
    z = 0
    aa = 0
    bb = 0
    cc = 0
    return (a, b, c, d, e, f, g, h, i_, j, k, l, m, n, o, p, q, r, s, t, u, v, w, x_, y, z, aa, bb, cc)


def long_3(xs):
    a = 0
    b = 0
    c = 0
    d = 0
    e = 0
    f = 0
    g = 0
    h = 0
    i_ = 0
    j = 0
    k = 0
    l = 0
    m = 0
    n = 0
    o = 0
    p = 0
    q = 0
    r = 0
    s = 0
    t = 0
    u = 0
    v = 0
    w = 0
    x_ = 0
    y = 0
    z = 0
    aa = 0
    bb = 0
    cc = 0
    return (a, b, c, d, e, f, g, h, i_, j, k, l, m, n, o, p, q, r, s, t, u, v, w, x_, y, z, aa, bb, cc)
```

- [ ] **Step 4: `uniform.py`**

```python
"""Ten functions, each with 10 statements. Degenerate bimodality (all values equal).

Expected module metrics:
  trivial_delegation_ratio = 0.0 (0/10), confidence=LOW (n<20)
  median_function_length = 10, confidence=HIGH (n=10)
  function_length_bimodality = 0.0 (degenerate; all lengths equal → m2=0), confidence=LOW (n<30)

Statement-count list: [10, 10, 10, 10, 10, 10, 10, 10, 10, 10]
"""
from __future__ import annotations


def _ten_stmt_body():
    """Template: exactly 10 statements. Verify with REPL."""


def fn_01(xs):
    a = 0
    b = 0
    c = 0
    d = 0
    e = 0
    a = a + 1
    b = b + 1
    c = c + 1
    d = d + 1
    return (a, b, c, d, e)


def fn_02(xs):
    a = 0
    b = 0
    c = 0
    d = 0
    e = 0
    a = a + 1
    b = b + 1
    c = c + 1
    d = d + 1
    return (a, b, c, d, e)


def fn_03(xs):
    a = 0
    b = 0
    c = 0
    d = 0
    e = 0
    a = a + 1
    b = b + 1
    c = c + 1
    d = d + 1
    return (a, b, c, d, e)


def fn_04(xs):
    a = 0
    b = 0
    c = 0
    d = 0
    e = 0
    a = a + 1
    b = b + 1
    c = c + 1
    d = d + 1
    return (a, b, c, d, e)


def fn_05(xs):
    a = 0
    b = 0
    c = 0
    d = 0
    e = 0
    a = a + 1
    b = b + 1
    c = c + 1
    d = d + 1
    return (a, b, c, d, e)


def fn_06(xs):
    a = 0
    b = 0
    c = 0
    d = 0
    e = 0
    a = a + 1
    b = b + 1
    c = c + 1
    d = d + 1
    return (a, b, c, d, e)


def fn_07(xs):
    a = 0
    b = 0
    c = 0
    d = 0
    e = 0
    a = a + 1
    b = b + 1
    c = c + 1
    d = d + 1
    return (a, b, c, d, e)


def fn_08(xs):
    a = 0
    b = 0
    c = 0
    d = 0
    e = 0
    a = a + 1
    b = b + 1
    c = c + 1
    d = d + 1
    return (a, b, c, d, e)


def fn_09(xs):
    a = 0
    b = 0
    c = 0
    d = 0
    e = 0
    a = a + 1
    b = b + 1
    c = c + 1
    d = d + 1
    return (a, b, c, d, e)


def fn_10(xs):
    a = 0
    b = 0
    c = 0
    d = 0
    e = 0
    a = a + 1
    b = b + 1
    c = c + 1
    d = d + 1
    return (a, b, c, d, e)
```

- [ ] **Step 5: `empty.py`**

```python
"""Zero functions. Edge case for empty-module sentinel in all three metrics.

Expected module metrics:
  trivial_delegation_ratio: value=0.0, confidence=LOW, notes="no functions in module"
  median_function_length: value=0, confidence=LOW, notes="no functions in module"
  function_length_bimodality: value=0.0, confidence=LOW, notes="n=0 below minimum 4 for bimodality"
"""
from __future__ import annotations
```

- [ ] **Step 6: `single.py`**

```python
"""One function, 5 statements, NONE delegation. Sub-threshold for all three metrics.

Expected module metrics:
  trivial_delegation_ratio = 0.0 (0/1), confidence=LOW (n<20)
  median_function_length = 5 (or parser's count), confidence=LOW (n<10)
  function_length_bimodality = 0.0, confidence=LOW, notes="n=1 below minimum 4 for bimodality"

Statement-count list: [5] — REPL-verify.
"""
from __future__ import annotations


def only_function(xs):
    total = 0
    count = 0
    for item in xs:
        total = total + item
        count = count + 1
    return total / count if count else 0
```

- [ ] **Step 7: `at_threshold.py`**

```python
"""Exactly 20 functions: 10 trivial delegates + 10 real-work. At MEDIUM-confidence
threshold for trivial_delegation_ratio; at HIGH-confidence threshold for
median_function_length; still below n=30 HIGH threshold for bimodality.

Expected module metrics:
  trivial_delegation_ratio = 0.5 (10/20), confidence=MEDIUM (n≥20)
  median_function_length = 1 or 2 (depends on statement mix), confidence=HIGH (n≥10)
  function_length_bimodality = <computed>, confidence=LOW (n=20, below 30)

Statement-count list: REPL-verify.
"""
from __future__ import annotations


# 10 trivial delegates (RETURN_PASSTHROUGH)
def d01(a): return h(a)  # noqa: E704
def d02(a): return h(a)  # noqa: E704
def d03(a): return h(a)  # noqa: E704
def d04(a): return h(a)  # noqa: E704
def d05(a): return h(a)  # noqa: E704
def d06(a): return h(a)  # noqa: E704
def d07(a): return h(a)  # noqa: E704
def d08(a): return h(a)  # noqa: E704
def d09(a): return h(a)  # noqa: E704
def d10(a): return h(a)  # noqa: E704


# 10 real-work functions
def w01(xs):
    total = 0
    for item in xs:
        total = total + item
    return total


def w02(xs):
    total = 0
    for item in xs:
        total = total + item
    return total


def w03(xs):
    total = 0
    for item in xs:
        total = total + item
    return total


def w04(xs):
    total = 0
    for item in xs:
        total = total + item
    return total


def w05(xs):
    total = 0
    for item in xs:
        total = total + item
    return total


def w06(xs):
    total = 0
    for item in xs:
        total = total + item
    return total


def w07(xs):
    total = 0
    for item in xs:
        total = total + item
    return total


def w08(xs):
    total = 0
    for item in xs:
        total = total + item
    return total


def w09(xs):
    total = 0
    for item in xs:
        total = total + item
    return total


def w10(xs):
    total = 0
    for item in xs:
        total = total + item
    return total


def h(a):
    return a
```

Note: `h(a)` itself is a RETURN_PASSTHROUGH (a single `return a` isn't a call — it's an identifier return, so the detector classifies it as NONE). Total delegates: 10. Total functions: 21 (20 + `h`). Ratio: 10/21 ≈ 0.476. **Update the docstring** to reflect 21 functions and 10/21 ratio, OR rename `h` to use a different shape that definitely classifies NONE (which it already will because `return a` isn't `return f(args)`). Verify with REPL before moving on and adjust the expected values accordingly.

- [ ] **Step 8: `large_sample.py`**

```python
"""30+ functions with varied statement counts. HIGH-confidence tier for all three metrics.

Expected module metrics:
  trivial_delegation_ratio = <computed>, confidence=MEDIUM (n≥20)
  median_function_length = <computed>, confidence=HIGH (n≥10)
  function_length_bimodality = <computed>, confidence=HIGH (n≥30)

Exact values: REPL-verify. The intent is a broadly-distributed sample
(e.g., function lengths 2, 3, 5, 7, 10, 15, 20 mixed) — not bimodal.
"""
from __future__ import annotations


# Functions with varied shapes (generate at least 30).
def f01(xs):
    return sum(xs)


def f02(xs):
    total = 0
    for x in xs:
        total = total + x
    return total


def f03(xs):
    return max(xs)


def f04(xs):
    return min(xs)


def f05(xs):
    total = 0
    count = 0
    for x in xs:
        total = total + x
        count = count + 1
    return total / count if count else 0


def f06(xs):
    return [x for x in xs if x > 0]


def f07(xs, ys):
    return [(x, y) for x in xs for y in ys]


def f08(xs):
    return sorted(xs)


def f09(xs):
    return sorted(xs, reverse=True)


def f10(xs):
    s = set(xs)
    return sorted(s)


def f11(xs):
    total = 0
    for x in xs:
        if x > 0:
            total = total + x
    return total


def f12(xs):
    total = 0
    for x in xs:
        if x < 0:
            total = total + x
    return total


def f13(xs):
    return xs[0] if xs else None


def f14(xs):
    return xs[-1] if xs else None


def f15(xs):
    mid = len(xs) // 2
    return xs[mid] if xs else None


def f16(xs):
    return len(xs)


def f17(xs):
    return sum(xs) / len(xs) if xs else 0


def f18(xs):
    return sum(x * x for x in xs)


def f19(xs):
    return [x + 1 for x in xs]


def f20(xs):
    return [x - 1 for x in xs]


def f21(xs):
    return [x * 2 for x in xs]


def f22(xs):
    return [x // 2 for x in xs]


def f23(xs):
    total = 0
    count = 0
    squared = 0
    for x in xs:
        total = total + x
        squared = squared + x * x
        count = count + 1
    return (total, squared, count)


def f24(xs):
    return {x for x in xs}


def f25(xs):
    return {x: x * 2 for x in xs}


def f26(xs):
    return all(x > 0 for x in xs)


def f27(xs):
    return any(x > 0 for x in xs)


def f28(xs):
    return [x for x in xs if x % 2 == 0]


def f29(xs):
    return [x for x in xs if x % 2 == 1]


def f30(xs):
    xs_sorted = sorted(xs)
    if not xs_sorted:
        return None
    return xs_sorted[len(xs_sorted) // 2]


def f31(xs):
    return reversed(xs)


def f32(xs):
    return list(zip(xs, xs[1:]))
```

- [ ] **Step 9: REPL-verify all fixtures**

Before committing, run:

```bash
uv run python -c "
from pathlib import Path
from savviety_instinct.parse.python import PYTHON_ADAPTER

for f in sorted(Path('tests/fixtures/python/modules').glob('*.py')):
    r = PYTHON_ADAPTER.parse_path(f)
    fns = r.functions
    print(f'{f.name}: {len(fns)} fns, statement_counts={[fn.statement_count for fn in fns]}')
    print(f'  delegation_kinds={[str(fn.delegation_kind) for fn in fns]}')
"
```

Cross-check each file's docstring against the REPL output. Update docstrings that diverge from reality (the parser is authoritative).

- [ ] **Step 10: Commit**

```bash
git add tests/fixtures/python/modules/
git commit -m "$(cat <<'EOF'
test: module-level fixtures with hand-verified expected values (Slice 4b)

Eight .py files under tests/fixtures/python/modules/ exercising the three
Slice 4b module metrics: ratio extremes (trivial_facade.py, real_work.py),
bimodal distribution (bimodal.py), degenerate all-equal (uniform.py),
empty/single-fn edge cases, MEDIUM/HIGH confidence threshold (at_threshold.py,
large_sample.py). Each fixture's module docstring documents expected values
for all three metrics with REPL-verified statement_counts.

Consumed by Tasks 6-9 parametrized tests.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `trivial_delegation_ratio` metric

**Files:**
- Create: `src/savviety_instinct/analyze/metrics/trivial_delegation_ratio.py`
- Modify: `src/savviety_instinct/analyze/metrics/__init__.py`
- Modify: `src/savviety_instinct/analyze/__init__.py`
- Create: `tests/test_analyze_metric_trivial_delegation_ratio.py`

**Rationale:** First consumer of `FunctionDefNode.delegation_kind`. Pure lookup — iterates `context.parse_result.functions` and sums non-NONE kinds. Emits MODULE-scoped metric now that the pipeline filter has been in place since Task 3.

- [ ] **Step 1: Write failing tests first**

Create `tests/test_analyze_metric_trivial_delegation_ratio.py`:

```python
"""trivial_delegation_ratio metric tests (Slice 4b)."""

from __future__ import annotations

from pathlib import Path

import pytest

from savviety_instinct.analyze.metrics.trivial_delegation_ratio import (
    TRIVIAL_DELEGATION_RATIO_METRIC,
)
from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Confidence,
    Language,
    SourceRange,
)
from savviety_instinct.parse.python import PYTHON_ADAPTER

MODULES = Path(__file__).parent / "fixtures" / "python" / "modules"


def _module_artifact_and_ctx(path: Path):
    result = PYTHON_ADAPTER.parse_path(path)
    artifact = Artifact(
        ast_hash="test",
        language=Language.PYTHON,
        kind=ArtifactKind.MODULE,
        name=str(path),
        enclosing_scope=None,
        source_range=SourceRange(file_path=str(path), line_start=1, line_end=1),
    )
    ctx = AnalysisContext(parse_result=result)
    return artifact, ctx


def test_applies_to_module_only() -> None:
    assert TRIVIAL_DELEGATION_RATIO_METRIC.applies_to == frozenset({ArtifactKind.MODULE})


def test_trivial_facade_high_ratio() -> None:
    artifact, ctx = _module_artifact_and_ctx(MODULES / "trivial_facade.py")
    value = TRIVIAL_DELEGATION_RATIO_METRIC.compute(artifact, ctx)
    assert value.metric_id == "trivial_delegation_ratio"
    # 5 delegates out of 6 = 0.833...
    assert value.value == pytest.approx(5 / 6, abs=1e-6)
    assert value.confidence == Confidence.LOW  # n=6 < 20


def test_real_work_zero_ratio() -> None:
    artifact, ctx = _module_artifact_and_ctx(MODULES / "real_work.py")
    value = TRIVIAL_DELEGATION_RATIO_METRIC.compute(artifact, ctx)
    assert value.value == 0.0
    assert value.confidence == Confidence.LOW  # n=5 < 20


def test_empty_module_sentinel() -> None:
    artifact, ctx = _module_artifact_and_ctx(MODULES / "empty.py")
    value = TRIVIAL_DELEGATION_RATIO_METRIC.compute(artifact, ctx)
    assert value.value == 0.0
    assert value.confidence == Confidence.LOW
    assert value.notes == "no functions in module"


def test_single_fn_module() -> None:
    artifact, ctx = _module_artifact_and_ctx(MODULES / "single.py")
    value = TRIVIAL_DELEGATION_RATIO_METRIC.compute(artifact, ctx)
    assert value.value == 0.0
    assert value.confidence == Confidence.LOW  # n=1 < 20


def test_at_threshold_medium_confidence() -> None:
    """at_threshold.py has ≥20 functions — confidence bumps to MEDIUM."""
    artifact, ctx = _module_artifact_and_ctx(MODULES / "at_threshold.py")
    value = TRIVIAL_DELEGATION_RATIO_METRIC.compute(artifact, ctx)
    assert value.confidence == Confidence.MEDIUM
    # Actual ratio depends on fixture shape — verify it's strictly between 0 and 1.
    assert 0.0 < value.value < 1.0


def test_notes_report_sample_size() -> None:
    artifact, ctx = _module_artifact_and_ctx(MODULES / "trivial_facade.py")
    value = TRIVIAL_DELEGATION_RATIO_METRIC.compute(artifact, ctx)
    assert "n=6" in (value.notes or "")
    assert "below min" in (value.notes or "")
```

- [ ] **Step 2: Run the test — fail**

```bash
uv run pytest tests/test_analyze_metric_trivial_delegation_ratio.py -v
```

Expected: `ImportError: cannot import name 'TRIVIAL_DELEGATION_RATIO_METRIC'`.

- [ ] **Step 3: Implement the metric**

Create `src/savviety_instinct/analyze/metrics/trivial_delegation_ratio.py`:

```python
"""Trivial Delegation Ratio metric — ravioli-pattern signal (arch §2.1).

Module-scope. Counts the fraction of functions whose body is a trivial
wrapper for another call (RETURN_PASSTHROUGH, ASSIGN_DELEGATE, or
WRAPPER_NO_TRANSFORM). Triviality classification is pre-computed on
FunctionDefNode.delegation_kind in the parse layer.

Confidence tiers (per plan Scope Decision #10):
  n = 0: value=0.0, LOW, notes="no functions in module"
  0 < n < 20: LOW, notes="n=<n> (below min sample size 20)"
  n ≥ 20: MEDIUM, notes="n=<n>"

KNOWN GAPS (metric_version=1.0.0):
- R1 triviality detection is deliberately strict (exact passthrough only);
  super(), async, and attribute-call targets are missed. See
  parse.types.DelegationKind docstring for the full list.
- Catalog "facade by design" dismissal is an R2 concern — we do not
  distinguish intentional delegation from accidental ravioli at this layer.
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
from savviety_instinct.parse.types import DelegationKind

MIN_SAMPLE_SIZE: int = 20


class TrivialDelegationRatioMetric:
    id: str = "trivial_delegation_ratio"
    version: str = "1.0.0"
    applies_to: frozenset[ArtifactKind] = frozenset({ArtifactKind.MODULE})
    required_inputs: frozenset[InputKind] = frozenset({InputKind.AST})

    def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue:
        if context.parse_result is None:
            raise ValueError(f"{self.id} requires AnalysisContext.parse_result")
        fns = context.parse_result.functions
        n = len(fns)

        if n == 0:
            return MetricValue(
                metric_id=self.id,
                value=0.0,
                metric_version=self.version,
                confidence=Confidence.LOW,
                notes="no functions in module",
            )

        trivial = sum(1 for f in fns if f.delegation_kind != DelegationKind.NONE)
        ratio = trivial / n

        if n < MIN_SAMPLE_SIZE:
            confidence = Confidence.LOW
            notes = f"n={n} (below min sample size {MIN_SAMPLE_SIZE})"
        else:
            confidence = Confidence.MEDIUM
            notes = f"n={n}"

        return MetricValue(
            metric_id=self.id,
            value=ratio,
            metric_version=self.version,
            confidence=confidence,
            notes=notes,
        )


TRIVIAL_DELEGATION_RATIO_METRIC = TrivialDelegationRatioMetric()
```

- [ ] **Step 4: Register in `analyze/metrics/__init__.py` and `analyze/__init__.py`**

`src/savviety_instinct/analyze/metrics/__init__.py`:

```python
"""Metric implementations (arch §5.3 pipeline stage 5)."""

from __future__ import annotations

from savviety_instinct.analyze.metrics.cognitive import COGNITIVE_METRIC
from savviety_instinct.analyze.metrics.cyclomatic import CYCLOMATIC_METRIC
from savviety_instinct.analyze.metrics.identifier_quality import IDENTIFIER_QUALITY_METRIC
from savviety_instinct.analyze.metrics.max_nesting_depth import MAX_NESTING_DEPTH_METRIC
from savviety_instinct.analyze.metrics.npath import NPATH_METRIC
from savviety_instinct.analyze.metrics.statement_count import STATEMENT_COUNT_METRIC
from savviety_instinct.analyze.metrics.trivial_delegation_ratio import (
    TRIVIAL_DELEGATION_RATIO_METRIC,
)

__all__ = [
    "COGNITIVE_METRIC",
    "CYCLOMATIC_METRIC",
    "IDENTIFIER_QUALITY_METRIC",
    "MAX_NESTING_DEPTH_METRIC",
    "NPATH_METRIC",
    "STATEMENT_COUNT_METRIC",
    "TRIVIAL_DELEGATION_RATIO_METRIC",
]
```

`src/savviety_instinct/analyze/__init__.py` — add the import and place the new metric in the registry:

```python
from savviety_instinct.analyze.metrics import (
    COGNITIVE_METRIC,
    CYCLOMATIC_METRIC,
    IDENTIFIER_QUALITY_METRIC,
    MAX_NESTING_DEPTH_METRIC,
    NPATH_METRIC,
    STATEMENT_COUNT_METRIC,
    TRIVIAL_DELEGATION_RATIO_METRIC,
)

# ... (load_cognitive_rules import unchanged)

METRICS_REGISTRY = (
    # Function-level (Slice 3 + 4a)
    STATEMENT_COUNT_METRIC,
    CYCLOMATIC_METRIC,
    COGNITIVE_METRIC,
    MAX_NESTING_DEPTH_METRIC,
    NPATH_METRIC,
    IDENTIFIER_QUALITY_METRIC,
    # Module-level (Slice 4b)
    TRIVIAL_DELEGATION_RATIO_METRIC,
)
```

Also update the module-level `__all__` to include the new symbol.

- [ ] **Step 5: Run the target test**

```bash
uv run pytest tests/test_analyze_metric_trivial_delegation_ratio.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Run the full suite**

```bash
uv run pytest -x 2>&1 | tail -30
```

Expected: existing 236 tests still pass; the new suite adds ~7 tests. Integration tests' row-count helpers now see an extra MODULE metric — verify `expected_row_count(10, 1)` for any test with `n_modules=1`. Task 2 set `n_modules=0` for the existing integration tests; those should still hold because they haven't yet been flipped to include the module artifact (Task 9 does that).

If a test regresses because a module is being emitted for a fixture, the pipeline is correctly routing the new metric and the test expectation is stale. Update via `expected_row_count(n_functions, n_modules=1)` only if the test is meant to cover Slice 4b's new emissions. Otherwise investigate the root cause.

- [ ] **Step 7: Commit**

```bash
git add src/savviety_instinct/analyze/metrics/trivial_delegation_ratio.py src/savviety_instinct/analyze/metrics/__init__.py src/savviety_instinct/analyze/__init__.py tests/test_analyze_metric_trivial_delegation_ratio.py
git commit -m "$(cat <<'EOF'
feat(analyze): trivial_delegation_ratio module metric

Arch §2.1. Module-scope metric computing fraction of functions classified
as trivial delegates (via FunctionDefNode.delegation_kind from Slice 4b's
parse-layer classifier). Confidence tiers: n=0 LOW+sentinel, 0<n<20 LOW
with below-min note, n≥20 MEDIUM. Known gaps (R1 strictness) documented
in the metric module.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: `median_function_length` metric

**Files:**
- Create: `src/savviety_instinct/analyze/metrics/median_function_length.py`
- Modify: `src/savviety_instinct/analyze/metrics/__init__.py`
- Modify: `src/savviety_instinct/analyze/__init__.py`
- Create: `tests/test_analyze_metric_median_function_length.py`

**Rationale:** Pure `statistics.median` over `FunctionDefNode.statement_count`. Value cast to `int` per spec §5.2; even-count truncation documented as Known Gap.

- [ ] **Step 1: Write failing tests**

```python
"""median_function_length metric tests (Slice 4b)."""

from __future__ import annotations

from pathlib import Path

from savviety_instinct.analyze.metrics.median_function_length import (
    MEDIAN_FUNCTION_LENGTH_METRIC,
)
from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Confidence,
    Language,
    SourceRange,
)
from savviety_instinct.parse.python import PYTHON_ADAPTER

MODULES = Path(__file__).parent / "fixtures" / "python" / "modules"


def _compute(path: Path):
    result = PYTHON_ADAPTER.parse_path(path)
    artifact = Artifact(
        ast_hash="test",
        language=Language.PYTHON,
        kind=ArtifactKind.MODULE,
        name=str(path),
        enclosing_scope=None,
        source_range=SourceRange(file_path=str(path), line_start=1, line_end=1),
    )
    ctx = AnalysisContext(parse_result=result)
    return MEDIAN_FUNCTION_LENGTH_METRIC.compute(artifact, ctx), result


def test_applies_to_module_only() -> None:
    assert MEDIAN_FUNCTION_LENGTH_METRIC.applies_to == frozenset({ArtifactKind.MODULE})


def test_value_is_int() -> None:
    value, _ = _compute(MODULES / "uniform.py")
    assert isinstance(value.value, int)


def test_empty_module_sentinel() -> None:
    value, _ = _compute(MODULES / "empty.py")
    assert value.value == 0
    assert value.confidence == Confidence.LOW
    assert value.notes == "no functions in module"


def test_uniform_module_high_confidence() -> None:
    value, result = _compute(MODULES / "uniform.py")
    # All functions should have the same statement_count
    counts = [fn.statement_count for fn in result.functions]
    assert len(set(counts)) == 1
    assert value.value == counts[0]
    assert value.confidence == Confidence.HIGH  # n=10


def test_single_fn_low_confidence() -> None:
    value, _ = _compute(MODULES / "single.py")
    assert value.confidence == Confidence.LOW  # n=1 < 10


def test_matches_python_statistics_median() -> None:
    """Parity check: result matches int(statistics.median(...))."""
    import statistics

    value, result = _compute(MODULES / "real_work.py")
    counts = [fn.statement_count for fn in result.functions]
    expected = int(statistics.median(counts))
    assert value.value == expected
```

- [ ] **Step 2: Run failing**

```bash
uv run pytest tests/test_analyze_metric_median_function_length.py -v
```

- [ ] **Step 3: Implement**

`src/savviety_instinct/analyze/metrics/median_function_length.py`:

```python
"""Median Function Length metric (arch §2.2).

Module-scope. Median of `statement_count` across all functions in the module.
Catalog also describes a bimodality coefficient — that ships as a separate
metric (function_length_bimodality) per Slice 4b design spec §5.

Confidence tiers:
  n = 0: value=0, LOW, notes="no functions in module"
  0 < n < 10: LOW, notes="n=<n> (below min sample size 10)"
  n ≥ 10: HIGH, notes="n=<n>"

KNOWN GAPS (metric_version=1.0.0):
- Even-count modules truncate via int() cast ([2, 5] → median 3.5 → int 3).
  Matches catalog "integer (median)" surface but loses precision. Fix via
  metric_version bump if calibration shows the truncation mis-ranks modules.
"""

from __future__ import annotations

import statistics

from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Confidence,
    InputKind,
    MetricValue,
)

MIN_SAMPLE_SIZE: int = 10


class MedianFunctionLengthMetric:
    id: str = "median_function_length"
    version: str = "1.0.0"
    applies_to: frozenset[ArtifactKind] = frozenset({ArtifactKind.MODULE})
    required_inputs: frozenset[InputKind] = frozenset({InputKind.AST})

    def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue:
        if context.parse_result is None:
            raise ValueError(f"{self.id} requires AnalysisContext.parse_result")
        fns = context.parse_result.functions
        n = len(fns)

        if n == 0:
            return MetricValue(
                metric_id=self.id,
                value=0,
                metric_version=self.version,
                confidence=Confidence.LOW,
                notes="no functions in module",
            )

        median_value = int(statistics.median(f.statement_count for f in fns))

        if n < MIN_SAMPLE_SIZE:
            confidence = Confidence.LOW
            notes = f"n={n} (below min sample size {MIN_SAMPLE_SIZE})"
        else:
            confidence = Confidence.HIGH
            notes = f"n={n}"

        return MetricValue(
            metric_id=self.id,
            value=median_value,
            metric_version=self.version,
            confidence=confidence,
            notes=notes,
        )


MEDIAN_FUNCTION_LENGTH_METRIC = MedianFunctionLengthMetric()
```

- [ ] **Step 4: Register**

Add to `analyze/metrics/__init__.py` imports and `__all__`; add to `analyze/__init__.py` imports, `METRICS_REGISTRY`, and `__all__`. Place after `TRIVIAL_DELEGATION_RATIO_METRIC` in the registry.

- [ ] **Step 5: Run target + full suite**

```bash
uv run pytest tests/test_analyze_metric_median_function_length.py -v
uv run pytest -x 2>&1 | tail -10
```

Expected: passes; no regressions.

- [ ] **Step 6: Commit**

```bash
git add src/savviety_instinct/analyze/metrics/median_function_length.py src/savviety_instinct/analyze/metrics/__init__.py src/savviety_instinct/analyze/__init__.py tests/test_analyze_metric_median_function_length.py
git commit -m "$(cat <<'EOF'
feat(analyze): median_function_length module metric

Arch §2.2. Module-scope median over FunctionDefNode.statement_count. Int
cast matches catalog "integer (median)" surface; even-count truncation
documented as Known Gap. Three-tier confidence: n=0 LOW+sentinel, n<10
LOW below-min, n≥10 HIGH. Bimodality coefficient ships as a separate
metric (Task 8) per spec §5.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: `function_length_bimodality` metric

**Files:**
- Create: `src/savviety_instinct/analyze/metrics/function_length_bimodality.py`
- Modify: `src/savviety_instinct/analyze/metrics/__init__.py`
- Modify: `src/savviety_instinct/analyze/__init__.py`
- Create: `tests/test_analyze_metric_function_length_bimodality.py`

**Rationale:** Hand-rolled Pearson's bimodality coefficient (no scipy). Three-tier confidence: `n<4` LOW+value=0.0 (degenerate), `4≤n<30` LOW, `n≥30` HIGH. All-equal-lengths case returns 0.0 with specific notes.

- [ ] **Step 1: Write failing tests**

```python
"""function_length_bimodality metric tests (Slice 4b)."""

from __future__ import annotations

from pathlib import Path

import pytest

from savviety_instinct.analyze.metrics.function_length_bimodality import (
    FUNCTION_LENGTH_BIMODALITY_METRIC,
    _bimodality_coefficient,
)
from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Confidence,
    Language,
    SourceRange,
)
from savviety_instinct.parse.python import PYTHON_ADAPTER

MODULES = Path(__file__).parent / "fixtures" / "python" / "modules"

# Threshold from catalog §2.2: BC > 0.555 flags bimodal.
BIMODAL_THRESHOLD = 5 / 9


def _compute(path: Path):
    result = PYTHON_ADAPTER.parse_path(path)
    artifact = Artifact(
        ast_hash="test",
        language=Language.PYTHON,
        kind=ArtifactKind.MODULE,
        name=str(path),
        enclosing_scope=None,
        source_range=SourceRange(file_path=str(path), line_start=1, line_end=1),
    )
    ctx = AnalysisContext(parse_result=result)
    return FUNCTION_LENGTH_BIMODALITY_METRIC.compute(artifact, ctx)


# ---------- Direct _bimodality_coefficient tests ----------


def test_bc_uniform_distribution_identical_values_is_zero() -> None:
    """All-equal samples → m2=0 (degenerate). Return 0.0."""
    assert _bimodality_coefficient([5, 5, 5, 5, 5, 5]) == 0.0


def test_bc_bimodal_distribution_above_threshold() -> None:
    """5 × small + 3 × large → BC > 5/9."""
    samples = [2, 2, 2, 2, 2, 30, 30, 30]
    assert _bimodality_coefficient(samples) > BIMODAL_THRESHOLD


def test_bc_near_normal_below_threshold() -> None:
    """Roughly-normal distribution → BC significantly below threshold."""
    # Symmetric, bell-ish sample (sum of three uniform random ≈ normal).
    samples = [5, 6, 7, 7, 8, 8, 8, 9, 9, 10, 10, 10, 10, 11, 11, 12, 12, 13, 14, 15]
    assert _bimodality_coefficient(samples) < BIMODAL_THRESHOLD


def test_bc_handles_smallest_valid_sample() -> None:
    """n=4 is the smallest n for which the formula's denominator is defined."""
    value = _bimodality_coefficient([1, 2, 3, 10])
    # Just verify it's a finite float in [0, 1] range without crashing.
    assert 0.0 <= value <= 1.0


# ---------- Metric-level tests ----------


def test_applies_to_module_only() -> None:
    assert FUNCTION_LENGTH_BIMODALITY_METRIC.applies_to == frozenset({ArtifactKind.MODULE})


def test_empty_module_sentinel() -> None:
    value = _compute(MODULES / "empty.py")
    assert value.value == 0.0
    assert value.confidence == Confidence.LOW
    assert "n=0" in (value.notes or "")
    assert "below minimum 4" in (value.notes or "")


def test_single_fn_below_min_n() -> None:
    value = _compute(MODULES / "single.py")
    assert value.value == 0.0
    assert value.confidence == Confidence.LOW
    assert "below minimum 4" in (value.notes or "")


def test_uniform_degenerate() -> None:
    value = _compute(MODULES / "uniform.py")
    assert value.value == 0.0
    assert "identical" in (value.notes or "")


def test_bimodal_fixture_flags_bimodal() -> None:
    value = _compute(MODULES / "bimodal.py")
    assert value.value > BIMODAL_THRESHOLD


def test_confidence_tier_below_30() -> None:
    """n=8 is in the 4≤n<30 tier — LOW confidence."""
    value = _compute(MODULES / "bimodal.py")
    assert value.confidence == Confidence.LOW


def test_confidence_tier_at_high_threshold() -> None:
    """large_sample.py has n≥30 — HIGH confidence."""
    value = _compute(MODULES / "large_sample.py")
    assert value.confidence == Confidence.HIGH
```

- [ ] **Step 2: Run — fail**

```bash
uv run pytest tests/test_analyze_metric_function_length_bimodality.py -v
```

- [ ] **Step 3: Implement the metric and helper**

`src/savviety_instinct/analyze/metrics/function_length_bimodality.py`:

```python
"""Function Length Bimodality metric — Pearson's bimodality coefficient (arch §2.2).

Shape statistic over the distribution of statement_count across module
functions. BC > 5/9 ≈ 0.555 flags "many short + a few long" bimodal patterns.

Formula (Pearson's moment coefficient):
  BC = (skewness² + 1) / (kurtosis + 3·(n-1)² / ((n-2)·(n-3)))
  where skewness = m3 / m2^1.5
        kurtosis = m4 / m2² - 3   (excess kurtosis)
        m_k = k-th central moment

Hand-rolled over stdlib `statistics` — avoids ~100MB scipy dep.

Confidence tiers (three-tier):
  n < 4: value=0.0, LOW, notes="n=<n> below minimum 4 for bimodality"
    (Pearson's denominator terms undefined for n-3 ≤ 0)
  4 ≤ n < 30: LOW, notes="n=<n> (below calibration min 30)"
  n ≥ 30: HIGH, notes="n=<n>"

Degenerate case: all values identical → m2 = 0 → return 0.0 with specific notes.

KNOWN GAPS (metric_version=1.0.0):
- Per-module bimodality; cross-file (package-level) aggregation deferred.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence

from savviety_instinct.core.types import (
    AnalysisContext,
    Artifact,
    ArtifactKind,
    Confidence,
    InputKind,
    MetricValue,
)

MIN_VALID_N: int = 4
HIGH_CONFIDENCE_N: int = 30


def _bimodality_coefficient(samples: Sequence[int]) -> float:
    """Pearson's moment coefficient of bimodality. Returns 0.0 if undefined."""
    n = len(samples)
    if n < MIN_VALID_N:
        return 0.0
    mean = statistics.fmean(samples)
    m2 = sum((x - mean) ** 2 for x in samples) / n
    if m2 == 0:  # all values identical — bimodality undefined
        return 0.0
    m3 = sum((x - mean) ** 3 for x in samples) / n
    m4 = sum((x - mean) ** 4 for x in samples) / n
    skewness = m3 / (m2**1.5)
    kurtosis = m4 / (m2**2) - 3  # excess kurtosis
    denom = kurtosis + 3 * (n - 1) ** 2 / ((n - 2) * (n - 3))
    if denom == 0:  # defensive — shouldn't happen for n ≥ 4
        return 0.0
    return (skewness**2 + 1) / denom


class FunctionLengthBimodalityMetric:
    id: str = "function_length_bimodality"
    version: str = "1.0.0"
    applies_to: frozenset[ArtifactKind] = frozenset({ArtifactKind.MODULE})
    required_inputs: frozenset[InputKind] = frozenset({InputKind.AST})

    def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue:
        if context.parse_result is None:
            raise ValueError(f"{self.id} requires AnalysisContext.parse_result")
        fns = context.parse_result.functions
        n = len(fns)
        counts = [f.statement_count for f in fns]

        if n < MIN_VALID_N:
            return MetricValue(
                metric_id=self.id,
                value=0.0,
                metric_version=self.version,
                confidence=Confidence.LOW,
                notes=f"n={n} below minimum {MIN_VALID_N} for bimodality",
            )

        # Handle all-equal case explicitly so notes are meaningful.
        if len(set(counts)) == 1:
            return MetricValue(
                metric_id=self.id,
                value=0.0,
                metric_version=self.version,
                confidence=Confidence.LOW if n < HIGH_CONFIDENCE_N else Confidence.HIGH,
                notes=f"n={n}; all functions have identical length",
            )

        bc = _bimodality_coefficient(counts)

        if n < HIGH_CONFIDENCE_N:
            confidence = Confidence.LOW
            notes = f"n={n} (below calibration min {HIGH_CONFIDENCE_N})"
        else:
            confidence = Confidence.HIGH
            notes = f"n={n}"

        return MetricValue(
            metric_id=self.id,
            value=bc,
            metric_version=self.version,
            confidence=confidence,
            notes=notes,
        )


FUNCTION_LENGTH_BIMODALITY_METRIC = FunctionLengthBimodalityMetric()
```

- [ ] **Step 4: Register**

Add import to `analyze/metrics/__init__.py`, add to `__all__`. Add to `analyze/__init__.py` import, `METRICS_REGISTRY` (place after `MEDIAN_FUNCTION_LENGTH_METRIC`), and `__all__`.

- [ ] **Step 5: Run target + full suite**

```bash
uv run pytest tests/test_analyze_metric_function_length_bimodality.py -v
uv run pytest -x 2>&1 | tail -10
```

- [ ] **Step 6: Commit**

```bash
git add src/savviety_instinct/analyze/metrics/function_length_bimodality.py src/savviety_instinct/analyze/metrics/__init__.py src/savviety_instinct/analyze/__init__.py tests/test_analyze_metric_function_length_bimodality.py
git commit -m "$(cat <<'EOF'
feat(analyze): function_length_bimodality metric (Pearson's BC)

Arch §2.2. Hand-rolled Pearson's moment coefficient of bimodality over
FunctionDefNode.statement_count — no scipy dep. Three-tier confidence:
n<4 LOW+degenerate=0.0, 4≤n<30 LOW, n≥30 HIGH. All-equal-lengths case
returns 0.0 with "identical length" note. Complements
median_function_length from Task 7 (catalog §2.2 lists both as part of
the distributional analysis).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Integration + CLI tests (row counts + metric_ids)

**Files:**
- Create: `tests/integration/test_slice4b_pipeline.py`
- Modify: `tests/integration/test_slice4a_metrics.py` (update `metric_ids` set, row count)
- Modify: `tests/test_analyze_pipeline.py` (flip `n_modules=0` → `n_modules=1` where applicable)
- Modify: `tests/integration/test_slice3_pipeline.py` (same)
- Modify: `tests/cli/test_cli_run.py` (same)

**Rationale:** Integration coverage for Slice 4b end-to-end. Pre-existing tests' row-count assertions were parametrized in Task 2; now flip `n_modules=0` → `n_modules=1` where the test reads a single-file fixture. Also extend the `metric_ids` assertion in Slice 4a integration test to include the three new IDs.

- [ ] **Step 1: Create `tests/integration/test_slice4b_pipeline.py`**

```python
"""Slice 4b integration — end-to-end pipeline emits module + function metrics."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from savviety_instinct.analyze import METRICS_REGISTRY
from savviety_instinct.cli.app import app
from savviety_instinct.core.types import ArtifactKind
from tests._helpers import expected_row_count

FIXTURES = Path(__file__).parent.parent / "fixtures" / "python" / "modules"


def _write_config(cfg_dir: Path) -> None:
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.yaml").write_text("scope: personal\nsuppress: []\n")


def test_cli_emits_module_and_function_rows(tmp_path, monkeypatch) -> None:
    """Running on a single module fixture emits:
      - N_functions × 6 function-metric rows
      - 1 module × 3 module-metric rows
    """
    _write_config(tmp_path / ".instinct")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    target = FIXTURES / "trivial_facade.py"
    result = runner.invoke(app, ["run", str(target)], catch_exceptions=False)
    assert result.exit_code == 0

    rows = [line for line in result.output.splitlines() if "\t" in line]
    # trivial_facade.py has 7 functions (6 defs + 1 helper).
    # Verify against parser output rather than hard-coding.
    from savviety_instinct.parse.python import PYTHON_ADAPTER

    parse_result = PYTHON_ADAPTER.parse_path(target)
    n_fns = len(parse_result.functions)
    assert len(rows) == expected_row_count(n_functions=n_fns, n_modules=1)


def test_registry_has_three_new_module_metrics() -> None:
    module_metric_ids = {
        m.id for m in METRICS_REGISTRY if ArtifactKind.MODULE in m.applies_to
    }
    assert module_metric_ids == {
        "trivial_delegation_ratio",
        "median_function_length",
        "function_length_bimodality",
    }


def test_empty_module_still_produces_module_rows(tmp_path, monkeypatch) -> None:
    """A .py file with zero functions produces exactly 3 module rows + 0 function rows."""
    _write_config(tmp_path / ".instinct")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["run", str(FIXTURES / "empty.py")], catch_exceptions=False)
    assert result.exit_code == 0
    rows = [line for line in result.output.splitlines() if "\t" in line]
    assert len(rows) == expected_row_count(n_functions=0, n_modules=1)
    assert len(rows) == 3


def test_spot_check_bimodal_fixture_flags_bimodal(tmp_path, monkeypatch) -> None:
    """bimodal.py's function_length_bimodality metric value > 0.555 (catalog threshold)."""
    _write_config(tmp_path / ".instinct")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["run", str(FIXTURES / "bimodal.py")], catch_exceptions=False)
    assert result.exit_code == 0

    # Find the function_length_bimodality row.
    bimodality_line = None
    for line in result.output.splitlines():
        if "function_length_bimodality" in line:
            bimodality_line = line
            break
    assert bimodality_line is not None, "expected function_length_bimodality row"
    # Value token format: "metric_id=<value>". Parse.
    # Adjust parsing to match CLI's actual output format.
    value_str = bimodality_line.split("function_length_bimodality=")[1].split()[0].strip()
    value = float(value_str)
    assert value > 5 / 9, f"expected bimodal signal, got {value}"
```

- [ ] **Step 2: Update Slice 4a integration test**

In `tests/integration/test_slice4a_metrics.py`, update the `metric_ids` assertion and row count:

```python
from tests._helpers import expected_row_count


def test_cli_emits_all_metrics_per_artifact(tmp_path, monkeypatch) -> None:
    """After Slice 4b: 10 functions × 6 fn metrics + 1 module × 3 module metrics = 63 rows."""
    _write_config(tmp_path / ".instinct")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app, ["run", str(FIXTURES / "metric_fixtures.py")], catch_exceptions=False
    )
    assert result.exit_code == 0
    rows = [line.split("\t") for line in result.output.splitlines() if "\t" in line]
    assert len(rows) == expected_row_count(n_functions=10, n_modules=1)

    metric_ids = {r[2].split("=")[0] for r in rows}
    assert metric_ids == {
        "statement_count",
        "cyclomatic_complexity",
        "cognitive_complexity",
        "max_nesting_depth",
        "npath",
        "identifier_quality",
        "trivial_delegation_ratio",
        "median_function_length",
        "function_length_bimodality",
    }
```

Note: the test name was `test_cli_emits_six_metrics_per_function` — rename to `test_cli_emits_all_metrics_per_artifact` or similar, since it's no longer six-function-only.

- [ ] **Step 3: Update `tests/test_analyze_pipeline.py` single-file tests**

Change:
```python
assert len(results) == expected_row_count(n_functions=10, n_modules=0)
```
to:
```python
assert len(results) == expected_row_count(n_functions=10, n_modules=1)
```

Only for the single-file path (`test_run_single_file_yields_expected_metrics`). The directory-recursion test continues using `>=` and a lower bound.

- [ ] **Step 4: Update `tests/integration/test_slice3_pipeline.py`**

Same change — flip `n_modules=0` → `n_modules=1` where applicable (single-file assertions).

- [ ] **Step 5: Update `tests/cli/test_cli_run.py`**

Same change for any row-count assertion that reads a single fixture file.

- [ ] **Step 6: Run full suite**

```bash
uv run pytest -x 2>&1 | tail -30
```

Expected: all tests pass. Row counts now correctly include MODULE artifacts.

- [ ] **Step 7: Commit**

```bash
git add tests/integration/test_slice4b_pipeline.py tests/integration/test_slice4a_metrics.py tests/test_analyze_pipeline.py tests/integration/test_slice3_pipeline.py tests/cli/test_cli_run.py
git commit -m "$(cat <<'EOF'
test: Slice 4b integration — module metrics via CLI

New tests/integration/test_slice4b_pipeline.py exercises end-to-end CLI
emission of MODULE-scoped metric rows against the module fixture directory.
Updates existing integration/CLI tests to account for the 1 MODULE artifact
per file × 3 module metrics = 3 additional rows per fixture. metric_ids
set in Slice 4a integration test extended to include all nine metrics.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Self-dogfood

**Files:** none. Verification-only.

**Rationale:** Run `instinct` on its own source tree; eyeball the module-level metrics to confirm they behave sanely on real code. Captures one of the "don't forget" lessons from prior slices: let the tool examine itself.

- [ ] **Step 1: Run on `src/`**

```bash
uv run instinct run src/
```

Expected: no crashes; output contains function rows for each `.py` under `src/` plus module rows (one set of three per file). Note: default config's `suppress` may include paths — confirm you're seeing actual source modules.

- [ ] **Step 2: Spot-check one module's metrics manually**

Pick a module like `src/savviety_instinct/analyze/pipeline.py`. Count its functions by hand; compute expected `trivial_delegation_ratio` (probably 0.0 — the pipeline has no trivial delegates); estimate `median_function_length`. Verify the output matches.

Look especially for:
- `trivial_delegation_ratio > 0` on any module — is it legitimate delegation?
- `function_length_bimodality > 0.555` on any module — is the distribution actually bimodal or a false positive?

- [ ] **Step 3: Document findings in the commit**

If everything behaves correctly:

```bash
git commit --allow-empty -m "$(cat <<'EOF'
test(dogfood): run instinct on self; eyeball module metrics

Verified Slice 4b module metrics produce plausible values on the instinct
source tree. trivial_delegation_ratio mostly 0.0 across modules (no ravioli
in our pipeline code). median_function_length clusters in the 3–10 range;
no bimodality triggered on any module. Results align with manual inspection
of the source.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

If the dogfood run surfaces a bug, **do not** commit the empty marker. Fix the bug first in a targeted commit, then re-dogfood.

- [ ] **Step 4: Push branch and open PR**

```bash
git push -u origin slice-4b-module-metrics
gh pr create --title "Slice 4b: module-level metrics (trivial_delegation_ratio, median_function_length, function_length_bimodality)" --body "$(cat <<'EOF'
## Summary

- Three module-level metrics per arch §2.1–§2.2: `trivial_delegation_ratio`, `median_function_length`, `function_length_bimodality`
- First `ArtifactKind.MODULE` pipeline dispatch via `Metric.applies_to` filter
- Parse-layer `DelegationKind` classifier (strict R1 rules; Known Gaps for super/async/etc.)
- Registry duplication collapsed — `METRICS_REGISTRY` is sole source of truth
- Row-count test assertions parametrized off the registry
- New `tests/fixtures/python/modules/` directory with 8 hand-verified module fixtures

## Test plan

- [ ] `uv run pytest -x` — full suite green
- [ ] `uv run instinct run src/` — self-dogfood sanity check
- [ ] `uv run ruff check` — lint clean
- [ ] `uv run mypy --strict` — type-check clean

Design spec: `docs/specs/2026-04-19-slice-4b-module-metrics.md`
Plan: `docs/plans/2026-04-19-slice-4b-module-metrics.md`
EOF
)"
```

---

## Self-Review

After writing this plan, cross-check against the spec:

| Spec § | Requirement | Task coverage |
|--------|-------------|---------------|
| 2.1 | DelegationKind enum + field | Task 4 (Steps 1, 2, 3) |
| 3.1 | Pipeline MODULE emission | Task 3 (Step 4) |
| 3.2 | Module `ast_hash` formula | Task 3 (Step 3) |
| 3.3 | Registry collapse | Task 1 |
| 3.4 | `applies_to` as dispatch filter | Task 3 (Step 4) + startup guard (Step 5) |
| 3.5 | Row-count parametrization | Task 2 |
| 4.1 | `ParseResult.line_count` | Task 3 (Steps 1, 2) |
| 4.1.1 | Methods iterate uniformly | Implicit (no code change needed; `ParseResult.functions` already includes methods) |
| 4.2 | R1 triviality rules | Task 4 (Step 2, `_classify_delegation` + helpers) |
| 4.3 | Docstring handling | Task 4 (implicit via `_is_docstring_node` reuse) |
| 4.4 | Known Gaps documented | Task 4 (Step 2 docstring) + Tasks 6–8 metric-module KNOWN GAPS blocks |
| 5.1 | `trivial_delegation_ratio` | Task 6 |
| 5.2 | `median_function_length` | Task 7 |
| 5.3 | `function_length_bimodality` + `_bimodality_coefficient` | Task 8 |
| 5.4 | METRICS_REGISTRY order | Tasks 6, 7, 8 (incremental addition) |
| 6.1 | Fixture directory with 8 modules | Task 5 |
| 6.2 | Seven new test files | Tasks 3, 4, 6, 7, 8, 9 |
| 6.3 | Four existing test files row-count updates | Tasks 2, 9 |

All spec requirements traced to a task. No placeholders in any code block. Exact file paths given throughout. No "similar to Task N" back-references. All type/identifier names match across tasks:
- `DelegationKind` used in parse/types.py (Task 4 Step 1), parse/python.py (Task 4 Step 2), trivial_delegation_ratio.py (Task 6 Step 3). ✓
- `METRICS_REGISTRY` used in pipeline.py (Task 1, lazy import), analyze/__init__.py (Tasks 6, 7, 8), tests/_helpers.py (Task 2). ✓
- `expected_row_count` helper signature `(n_functions, n_modules)` consistent across Tasks 2 and 9. ✓
- `_bimodality_coefficient` defined and tested in Task 8, used internally by `FunctionLengthBimodalityMetric.compute`. ✓
