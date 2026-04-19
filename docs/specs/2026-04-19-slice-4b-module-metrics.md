# Slice 4b — Module-Level Metrics: Design Spec

> **Status:** Design approved 2026-04-19. Plan doc at `docs/plans/2026-04-19-slice-4b-module-metrics.md` (produced next via `writing-plans`).
>
> **Companion docs:** `docs/04-architecture-spec.md` §2 (layering), §5.3 (analyze), §15 (slice plan); `docs/05-metric-catalog.md` §2.1–§2.2 (metric definitions).

## 1. Goal

Ship three module-level metrics — `trivial_delegation_ratio`, `median_function_length`, `function_length_bimodality` — and the first `ArtifactKind.MODULE` pipeline dispatch. Collapse the `METRICS_REGISTRY` / `_METRICS` duplication noted in HANDOFF. No new external deps; no storage writes.

## 2. Scope

### In scope

1. Parse-layer `DelegationKind` enum + `FunctionDefNode.delegation_kind` classification field.
2. Three new metrics in `analyze/metrics/` with `applies_to={MODULE}`.
3. Pipeline emits one `Artifact(kind=MODULE)` per parsed `.py` file.
4. Pipeline loop honors `Metric.applies_to` (the field was added in Slice 1 and is unused until now).
5. Registry duplication collapse: `analyze/pipeline.py::_METRICS` deleted; pipeline imports `METRICS_REGISTRY` from `analyze/__init__.py`.
6. Row-count assertions in affected tests parametrized off `METRICS_REGISTRY` + artifact arithmetic.

### Out of scope (deferred)

- **Class-level metrics** (`LCOM-HS`, class-level abstractness) — needs method↔attribute-read graph extraction. Slice 4c.
- **Bimodality refinement** beyond Pearson's moment coefficient — catalog §2.2 permits variants. `metric_version` bump later.
- **Package-level aggregation** — our pipeline is per-file. Cross-file metrics deferred to graph-infrastructure slice.
- **Triviality detection widening** — super().method(), async def, default-argument injection — documented as Known Gaps, deferred.
- **Storage writes** — Slice 5.

## 3. Architecture & Data Flow

### 3.1 Pipeline dispatch

Current `analyze/pipeline.py` iterates only `ParseResult.functions`. New shape:

```python
for source_file in files:
    result = PYTHON_ADAPTER.parse_path(source_file)
    ctx = AnalysisContext(parse_result=result)

    module_artifact = Artifact(
        ast_hash=_module_ast_hash(result.functions),
        language=Language.PYTHON,
        kind=ArtifactKind.MODULE,
        name=str(source_file),  # relative path; CLI can pretty-print
        enclosing_scope=None,
        source_range=SourceRange(
            file_path=str(source_file),
            line_start=1,
            # len(source.splitlines()) or fall back to 1 for empty files;
            # cached on ParseResult so we don't re-read the file here.
            line_end=result.line_count,
        ),
    )
    artifacts = [module_artifact] + [_fn_artifact(fn) for fn in result.functions]

    for artifact in artifacts:
        for metric in METRICS_REGISTRY:
            if artifact.kind in metric.applies_to:
                yield artifact, metric.compute(artifact, ctx)
```

### 3.2 Module `ast_hash`

Computed as `blake3(b"|".join(fn.ast_hash.encode() for fn in functions))`. Shape-invariant across identifier/literal renames; changes when a function is added, removed, or structurally modified. Uses the same hash backend as Slice 2's per-function `ast_hash` (blake3 preferred, xxhash fallback, captured in `HASH_ALGORITHM` constant).

Rationale: matches arch §4.2's "hash of structural shape" intent. Alternative — hashing `str(tree_sitter_root)` — captures class bodies and module-level state but changes meaning. We can revisit in a later slice if module metrics depend on class/top-level-code shape.

### 3.3 Registry collapse

Before: `METRICS_REGISTRY` in `analyze/__init__.py`, duplicated as `_METRICS` in `analyze/pipeline.py`. New metric additions require updating both — historical footgun (HANDOFF §"Registry duplication smell").

After: `pipeline.py` imports `METRICS_REGISTRY` from `savviety_instinct.analyze` (the package-level export). `_METRICS` deleted.

### 3.4 `applies_to` becomes load-bearing

The `Metric` Protocol's `applies_to: frozenset[ArtifactKind]` has been present since Slice 1 but unused. Existing six metrics (all `FUNCTION`) keep `applies_to={ArtifactKind.FUNCTION}`; three new metrics use `applies_to={ArtifactKind.MODULE}`.

Safety guard: startup assertion in `analyze/__init__.py` — `assert all(m.applies_to for m in METRICS_REGISTRY)` + unit test `test_every_metric_applies_to_at_least_one_kind`. Prevents a silent no-op when a future metric ships with empty `applies_to`.

### 3.5 Expected CLI row count

Currently 60 rows per 10-function fixture (10 × 6 function metrics). After 4b:
- 10 × 6 function metrics + 1 module × 3 module metrics = **63 rows** for the same fixture.
- General formula: `len(fn_metrics) × n_functions + len(module_metrics) × n_modules`.

Row-count assertions in `tests/cli/test_cli_run.py`, `tests/test_analyze_pipeline.py`, `tests/integration/test_slice3_pipeline.py`, `tests/integration/test_slice4a_metrics.py` parametrize off `METRICS_REGISTRY` derived-partitioning. Decision: parametrize now — hard-coded counts break on every future metric slice.

## 4. Parse Layer

### 4.1 New types

In `src/savviety_instinct/parse/types.py`:

```python
class DelegationKind(StrEnum):
    NONE = "none"
    RETURN_PASSTHROUGH = "return_passthrough"
    ASSIGN_DELEGATE = "assign_delegate"
    WRAPPER_NO_TRANSFORM = "wrapper_no_transform"


@dataclass(frozen=True, slots=True)
class FunctionDefNode:
    # ... existing fields
    delegation_kind: DelegationKind = DelegationKind.NONE  # Slice 4b


@dataclass(frozen=True, slots=True)
class ParseResult:
    # ... existing fields
    line_count: int = 0  # Slice 4b — from root_node.end_point[0] + 1
```

`line_count` populated in `PythonAdapter.parse_path` from the tree-sitter root node's end position. Used by pipeline to build the module artifact's `SourceRange.line_end` without re-reading the file.

### 4.1.1 Methods and module-function iteration

`ParseResult.functions` already includes methods alongside free functions — methods carry `enclosing_class: str | None`. Module metrics iterate `ParseResult.functions` uniformly; no distinction between free functions and methods for `trivial_delegation_ratio` / `median_function_length` / `function_length_bimodality` counts.

### 4.2 Detection rules (R1 — deliberately strict)

`_classify_delegation(body_node, parameter_names) -> DelegationKind` in `parse/python.py`. Called from existing `_collect_functions` — no extra tree walk.

**RETURN_PASSTHROUGH.** Body has exactly one statement. That statement is `return_statement` whose value is a `call` expression where:
- every positional arg is an `identifier` node;
- positional arg names equal a prefix of `parameter_names` in declaration order;
- every keyword arg is `name=value` where `name == value` (both identifier, same spelling);
- no `*args` / `**kwargs` splats.

**ASSIGN_DELEGATE.** Body has exactly two statements:
- stmt 1: `x = <call>` where `<call>` satisfies RETURN_PASSTHROUGH's argument rules.
- stmt 2: `return x` where `x` matches the assignment target.

**WRAPPER_NO_TRANSFORM.** Body has exactly one statement which is an `expression_statement` wrapping a `call` (not a return, not an assign). Call satisfies RETURN_PASSTHROUGH's argument rules.

**NONE.** Everything else, including: multi-statement bodies beyond ASSIGN_DELEGATE's two; bodies with control flow; calls with transformations (`f(a) + 1`); calls with literal args (`f(a, 1)`); super()/attribute calls; async bodies; bodies with only `pass` or `...`.

### 4.3 Docstring handling

Docstrings are excluded from statement count (Slice 3's `_count_statements` behavior). Same rule here: `_classify_delegation` operates on the statement list *after* docstring filtering. A body like `"""doc""" ; return f(a, b)` has `statement_count=1` and classifies as `RETURN_PASSTHROUGH`.

### 4.4 Known Gaps

1. **Method-to-super delegation** (`return super().foo(a, b)`) → `NONE` (super() attribute access breaks "identifier-only call" rule). Catalog "facade by design" R2 dismissal may want these counted; weighing false-positive risk — kept out of R1.
2. **Decorators** (`@staticmethod`, `@functools.wraps`) don't affect classification — body rules still apply.
3. **Default-argument injection** (`def g(a, b=5):` → `return f(a, b)`) IS counted as passthrough. Defaults live on the signature, body passes params through. Documented.
4. **Async functions** (`async def g(...): return await f(a, b)`) → `NONE`. The `return` value is `await f(...)`, not a direct call. Extension is trivial but kept out of R1 for conservatism.
5. **`__init__` attribute assignment** (`self.x = x`) → `NONE`. This is data initialization, not delegation.

## 5. Metrics

All three metrics use `metric_version = "1.0.0"`, `applies_to = {ArtifactKind.MODULE}`, `required_inputs = {InputKind.AST}`.

### 5.1 `trivial_delegation_ratio`

- **Value type:** `float` in `[0.0, 1.0]`.
- **Formula:** `sum(1 for f in fns if f.delegation_kind != DelegationKind.NONE) / len(fns)`.
- **Confidence tiers:**
  - `n = 0` → `value=0.0, confidence=LOW, notes="no functions in module"`.
  - `0 < n < 20` → `value=<computed>, confidence=LOW, notes="n=<n> (below min sample size 20)"`.
  - `n ≥ 20` → `value=<computed>, confidence=MEDIUM, notes="n=<n>"`.
- Catalog §2.1 says "confidence: medium" at top tier — matches.

### 5.2 `median_function_length`

- **Value type:** `int`.
- **Formula:** `int(statistics.median(f.statement_count for f in fns))`.
- **Confidence tiers:**
  - `n = 0` → `value=0, confidence=LOW, notes="no functions in module"`.
  - `0 < n < 10` → `value=<computed>, confidence=LOW, notes="n=<n> (below min sample size 10)"`.
  - `n ≥ 10` → `value=<computed>, confidence=HIGH, notes="n=<n>"`.
- **Known Gap:** `int()` truncation on even-count modules (`[2, 5]` → median 3.5 → int 3). Catalog says "integer (median)"; truncation matches catalog surface but loses precision. Fix: change to float via `metric_version` bump if calibration data shows the truncation mis-ranks modules.

### 5.3 `function_length_bimodality`

- **Value type:** `float` in `[0.0, 1.0]` (Pearson's bimodality coefficient, BC).
- **Formula** (hand-rolled; no scipy):
  ```
  BC = (skewness² + 1) / (kurtosis + 3·(n-1)² / ((n-2)·(n-3)))
  ```
  where skewness = third central moment / second central moment^1.5, kurtosis = fourth central moment / second central moment² − 3 (excess kurtosis).
- **Confidence tiers:**
  - `n < 4` → `value=0.0, confidence=LOW, notes="n=<n> below minimum 4 for bimodality"` (Pearson's denominator terms undefined for `n-3 ≤ 0`).
  - `4 ≤ n < 30` → `value=<computed>, confidence=LOW, notes="n=<n> (below calibration min 30)"`.
  - `n ≥ 30` → `value=<computed>, confidence=HIGH, notes="n=<n>"`.
- **Degenerate case:** all function lengths identical → `m2 = 0` → `value=0.0, confidence=LOW, notes="all functions have identical length"`. Matches catalog's "bimodality > 0.555 flags suspicious distribution" — identical lengths give BC=0, well below threshold.
- **Known Gap:** cross-file (package-level) bimodality not computed — requires multi-file aggregation.

### 5.4 Registry after 4b

```python
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
    MEDIAN_FUNCTION_LENGTH_METRIC,
    FUNCTION_LENGTH_BIMODALITY_METRIC,
)
```

## 6. Testing Strategy

### 6.1 New fixture directory: `tests/fixtures/python/modules/`

| Fixture | Contents | Expected ratio / median / bimodality |
|---------|----------|--------------------------------------|
| `trivial_facade.py` | 6 fns; 5 trivial delegates covering all three DelegationKinds | 0.833 LOW / tiny / LOW (n<30) |
| `real_work.py` | 5 fns, zero delegates, varied lengths (3, 7, 10, 15, 20) | 0.0 LOW / 10 HIGH / LOW (n<30) |
| `bimodal.py` | 8 fns: 5× 2-stmt + 3× 30-stmt | 0.0 LOW / 2 or 30 LOW / >0.555 LOW |
| `uniform.py` | 10 fns × 10 stmts each | 0.0 LOW / 10 HIGH / 0.0 LOW (degenerate) |
| `empty.py` | 0 fns, module docstring only | sentinel LOW × 3 |
| `single.py` | 1 fn, 5 stmts, NONE delegation | 0.0 LOW / 5 LOW / 0.0 LOW (n<4) |
| `at_threshold.py` | exactly 20 fns (10 trivial, 10 real) | 0.5 MEDIUM / 1 HIGH / LOW (n<30) |
| `large_sample.py` | ≥30 fns exercising n≥30 HIGH tier | <computed> / <computed> HIGH / <computed> HIGH |

Each fixture file's module docstring documents hand-verified expected values — same discipline as Slice 3's `metric_fixtures.py`. Any BC expected value comes from running `_bimodality_coefficient` on the documented sample and recording the output.

### 6.2 Test file manifest

| Path | Scope |
|------|-------|
| `tests/test_parse_delegation_kind.py` | Parse-layer detection — one test per DelegationKind + edge cases (docstring+body, async, super(), self.x=x, decorated) |
| `tests/test_analyze_metric_trivial_delegation_ratio.py` | Metric unit tests, parametrized over fixtures |
| `tests/test_analyze_metric_median_function_length.py` | Metric unit tests |
| `tests/test_analyze_metric_function_length_bimodality.py` | Metric unit tests + direct `_bimodality_coefficient` tests (uniform→0; bimodal→>0.555; near-normal→~0.33) |
| `tests/test_analyze_module_artifact_emission.py` | Pipeline emits exactly one MODULE artifact per `.py` with correct `ast_hash`, `name`, `source_range` |
| `tests/test_analyze_metric_applies_to_filter.py` | Pipeline honors `applies_to`; startup assertion catches empty `applies_to` |
| `tests/integration/test_slice4b_pipeline.py` | End-to-end: `instinct run tests/fixtures/python/modules/` emits correct (N × 3) module rows + (total_fns × 6) function rows |

### 6.3 Existing tests to update

| File | Change |
|------|--------|
| `tests/cli/test_cli_run.py` | Row count: parametrized off `METRICS_REGISTRY` |
| `tests/test_analyze_pipeline.py` | Row count: parametrized |
| `tests/integration/test_slice3_pipeline.py` | Row count: parametrized |
| `tests/integration/test_slice4a_metrics.py` | Row count: parametrized |

## 7. Task Ordering (for plan doc)

Each step commits independently; each commit builds + tests green.

1. **Registry collapse.** `pipeline.py` imports `METRICS_REGISTRY`. `_METRICS` deleted. Pure refactor.
2. **Pipeline MODULE dispatch scaffold.** Emit MODULE artifact per file; apply `applies_to` filter. No metrics-of-kind-MODULE yet — module artifacts yield zero rows. New tests for artifact emission + `applies_to` filtering.
3. **Row-count parametrization.** Update the four existing tests to derive expected rows from `METRICS_REGISTRY`.
4. **Parse-layer `delegation_kind`.** Enum + field + `_classify_delegation` + `test_parse_delegation_kind.py`.
5. **Fixture directory.** Create all 8 module fixtures with hand-verified docstring expected values.
6. **`trivial_delegation_ratio` metric.**
7. **`median_function_length` metric.**
8. **`function_length_bimodality` metric.**
9. **End-to-end integration test** (`test_slice4b_pipeline.py`).
10. **Self-dogfood** — run `instinct run src/` and eyeball outputs.

## 8. File Manifest

| Path | Change type |
|------|-------------|
| `src/savviety_instinct/parse/types.py` | Modify — add `DelegationKind`, `delegation_kind` field; `ParseResult.line_count` field |
| `src/savviety_instinct/parse/python.py` | Modify — `_classify_delegation` helper wired into `_collect_functions`; populate `line_count` from root node |
| `src/savviety_instinct/analyze/metrics/trivial_delegation_ratio.py` | New |
| `src/savviety_instinct/analyze/metrics/median_function_length.py` | New |
| `src/savviety_instinct/analyze/metrics/function_length_bimodality.py` | New |
| `src/savviety_instinct/analyze/metrics/__init__.py` | Modify — re-export three new metrics |
| `src/savviety_instinct/analyze/__init__.py` | Modify — register three new metrics + empty-`applies_to` guard |
| `src/savviety_instinct/analyze/pipeline.py` | Modify — import `METRICS_REGISTRY`; MODULE artifact emission; `applies_to` filter |
| `tests/fixtures/python/modules/trivial_facade.py` | New |
| `tests/fixtures/python/modules/real_work.py` | New |
| `tests/fixtures/python/modules/bimodal.py` | New |
| `tests/fixtures/python/modules/uniform.py` | New |
| `tests/fixtures/python/modules/empty.py` | New |
| `tests/fixtures/python/modules/single.py` | New |
| `tests/fixtures/python/modules/at_threshold.py` | New |
| `tests/fixtures/python/modules/large_sample.py` | New |
| `tests/test_parse_delegation_kind.py` | New |
| `tests/test_analyze_metric_trivial_delegation_ratio.py` | New |
| `tests/test_analyze_metric_median_function_length.py` | New |
| `tests/test_analyze_metric_function_length_bimodality.py` | New |
| `tests/test_analyze_module_artifact_emission.py` | New |
| `tests/test_analyze_metric_applies_to_filter.py` | New |
| `tests/integration/test_slice4b_pipeline.py` | New |
| `tests/cli/test_cli_run.py` | Modify — parametrize row count |
| `tests/test_analyze_pipeline.py` | Modify — parametrize row count |
| `tests/integration/test_slice3_pipeline.py` | Modify — parametrize row count |
| `tests/integration/test_slice4a_metrics.py` | Modify — parametrize row count |

## 9. Decisions Locked During Brainstorm

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Bimodality ships as a separate metric, not a composite `MetricValue`. | `MetricValue.value` is `float \| int \| str`; composite struct would touch Slice 1 core types. |
| 2 | `DelegationKind` as enum (not bool, not struct). | Preserves per-kind signal for R2 metrics; matches `ControlFlowNodeKind` pattern. |
| 3 | Pipeline uses single loop + `applies_to` filter (not partitioned registry). | `applies_to` was designed for this in Slice 1; keeps pipeline extensible for future CLASS-kind metrics. |
| 4 | One `Artifact(kind=MODULE)` per `.py` file regardless of function count. | Empty modules handled via sentinel return in metric; no special-casing in pipeline. |
| 5 | Methods count as module functions. | Catalog definitions don't distinguish; keeps module metrics simple. |
| 6 | `__init__.py` treated as a regular module. | No special-casing — its contents (if any) contribute to module metrics the same way any other `.py` file does. Empty `__init__.py` files emit the n=0 sentinel. |
| 7 | `trivial_delegation_ratio` at top tier = MEDIUM confidence. | Matches catalog §2.1 literally. |
| 8 | `median_function_length` at top tier = HIGH confidence. | Matches catalog §2.2 literally. |
| 9 | `function_length_bimodality` at top tier = HIGH confidence. | User override of default-MEDIUM vote; matches catalog literal. |
| 10 | Hand-rolled Pearson's BC; no scipy. | Avoids ~100MB dep for one formula. |
| 11 | Row-count assertions parametrized off `METRICS_REGISTRY`. | Stable across future metric slices; hard-coded would break on every slice. |
| 12 | R1 triviality definition strict (exact passthrough only). | Minimizes false positives; widening tracked as Known Gaps for later `metric_version` bump. |
| 13 | Async functions excluded from triviality R1. | Conservative; easy extension for `metric_version=1.1.0`. |

## 10. Non-Goals Explicitly Deferred

- Class-level metrics (LCOM-HS, class-level abstractness) — Slice 4c.
- Cross-file / package-level aggregation — graph-infrastructure slice.
- Storage writes — Slice 5.
- Calibration-threshold enforcement in the metric layer — belongs in report/rendering layer (future).
- LLM-augmented delegation detection — R2.
