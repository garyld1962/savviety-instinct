# Testing Strategy

Instinct's tests operate in three rigor layers. Each targets a different
class of bug; together they catch what any one layer alone would miss.

When adding a metric, parser feature, or CLI path, check which layer(s)
should grow. Most new code earns at least layer 1 (unit); algorithmic
code earns layer 2 (property or differential) too.

---

## Layer 1 — Unit tests

**Location:** `tests/test_*.py` (excluding files named `test_metric_differential_*`
and `test_metric_invariants.py`)

**What they check:** specific expected values on hand-crafted inputs.
Parametrized fixtures with a small set of known-correct answers —
e.g., `nested_if → cyclomatic=3`, `single_if_with_boolean → cognitive=2`.

**When to add:** every new metric, parser field, CLI flag, config key.
Default vehicle; cheapest to write and run.

**Fixtures:** `tests/fixtures/python/metric_fixtures.py` is the canonical
ground-truth fixture for function-level metrics. `tests/fixtures/python/modules/`
holds module-level fixtures for Slice 4b metrics.

**Weakness:** expected values are authored by the same person who wrote the
code. Confirmation-bias risk. Layer 2 and 3 exist to check this.

---

## Layer 2 — Differential tests

**Location:** `tests/test_metric_differential_*.py`

**What they check:** our metric output against an independent implementation
of the same concept.

| Metric | Reference | Differential file |
|--------|-----------|-------------------|
| `cyclomatic_complexity` | `radon` (PyPI, stdlib-ast based) | `test_metric_differential_cyclomatic.py` |
| `cognitive_complexity` | `cognitive_complexity` PyPI package | `test_metric_differential_cognitive.py` |

**Structure:** each file has two parametrized tests:
1. `*_matches_reference` — cases where both tools agree. Exact match asserted.
2. `*_documented_deltas` — cases where they diverge. BOTH sides' values pinned
   with a `reason` string. Drift on either side surfaces for review.

**When to add:** any metric with a credible external reference implementation.
Not every metric has one (`identifier_quality`, `trivial_delegation_ratio`,
`function_length_bimodality` are instinct-specific; no reference exists).

**When to use xfail vs. dual-assertion:**
- Prefer dual-assertion: pins both values explicitly. Reader sees both
  numbers and the reason at once. Drift on either side surfaces.
- Reserve `pytest.mark.xfail(strict=True)` for known bugs we intend to
  fix — the strict mode flips to failure if someone fixes it, forcing
  the marker removal.

**Weakness:** deltas are labor-intensive to document. Keep the
`reason` field honest: "Known Gap #N in module X" or "Bug B#", not
vague hand-waving.

---

## Layer 3 — Property-based (invariant) tests

**Location:** `tests/test_metric_invariants.py`

**What they check:** value-range invariants on many generated inputs.
For each metric, hypothesis draws ~50 synthetic function or module
sources from a fixed vocabulary of single-line statements; every draw
must satisfy the metric's invariant.

**Invariants pinned today:**

| Metric | Invariant |
|--------|-----------|
| `statement_count` | `>= 0` |
| `cyclomatic_complexity` | `>= 1` |
| `cognitive_complexity` | `>= 0` |
| `max_nesting_depth` | `>= 0` |
| `npath` | `>= 1` |
| `identifier_quality` | `[0.0, 1.0]` |
| `trivial_delegation_ratio` | `[0.0, 1.0]` |
| `median_function_length` | `>= 0` |
| `function_length_bimodality` | `[0.0, 1.0]` |

**When to add:** new metric with a defined numeric range. Cheap one-shot
(one `@given` + one assertion). Catches silent overflows, sign errors,
division-by-zero paths.

**Weakness:** the source-generation vocabulary is limited; hypothesis
doesn't exercise every Python construct. Use alongside adversarial
fixtures.

---

## Adversarial parser fixtures

**Location:** `tests/fixtures/python/adversarial/*.py`

**Purpose:** stress the parser against modern Python constructs that
aren't exercised by the toy `metric_fixtures.py` — `match` statements,
walrus, async generators, decorator stacks, multi-clause comprehensions,
nested functions, PEP 695 generics, exception groups.

**Convention:** one construct per file. Each fixture's docstring lists
expected function count, expected classes, and any KNOWN BUGS the
fixture pins (via `xfail(strict=True)` on the relevant assertion).

**Testing entry point:** `tests/test_parse_adversarial.py`. Add to the
file when introducing a new construct.

**When to add:** whenever Python grammar evolves (new PEPs), or when a
bug surfaces that's specific to a construct not yet covered.

---

## Mutation testing

Not wired into CI. One-off local runs are documented in the plan
appendix at `docs/plans/2026-04-20-test-hardening-algorithmic-rigor.md`
§Mutation Baseline. Mutation score indicates how much the test suite
would catch if a line of logic changed; a drop over time signals tests
going stale.

Re-run occasionally, not per-PR — the run takes ~15 minutes.

---

## Pointers

- Adding a new metric? See `docs/plans/2026-04-19-slice-4b-module-metrics.md`
  for the current slice pattern: one fixture file, one test file,
  expected values pinned in docstrings.
- Adding a new parser field? Start with `test_parse_python.py` for the
  happy path, add adversarial fixtures for edge cases.
- Bug discovered via a fixture? Log it in the plan's "Bugs Surfaced"
  appendix (see `2026-04-20-test-hardening-algorithmic-rigor.md`).
