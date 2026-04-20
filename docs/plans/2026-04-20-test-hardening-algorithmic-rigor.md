# Test Hardening — Algorithmic Rigor Plan

**Date:** 2026-04-20
**Status:** LOCKED — approved 2026-04-20; branch `test-hardening-algorithmic-rigor`
**Trigger:** Coverage is 93%, 296 tests pass — but coverage ≠ correctness. Gap analysis in this session flagged that metric expected-values were authored by the metric author, creating confirmation-bias risk. Parser (`parse/python.py`, 91% line coverage, algorithmically complex) is the single highest-risk module and has no direct differential or adversarial tests.

**Scope:** Cross-cutting test hardening, not a new feature slice. Does not ship new metrics or new source modules. Adds fixtures, differential tests, property-based tests, and a baseline mutation-testing signal.

---

## Problem Statement

Current test suite (post-Slice-4b, 296 tests):

**What's load-bearing:**
- Metric tests use parametrized fixtures with hand-worked expected values — `npath` (10 cases), `cognitive` (10 cases), `identifier_quality` (fractional ratios), `bimodality` (uniform/bimodal/near-normal samples). These verify specific computed values.
- `test_parse_delegation_kind.py` is comprehensive for the R1 triviality rules.

**What's pro forma:**
- `test_core_types.py` — enum values, frozenness, Protocol conformance. Would pass even if every metric was broken.

**Gaps that raise correctness risk:**

| # | Gap | Risk |
|---|-----|------|
| G1 | Expected values for cyclomatic/cognitive derived by metric author only | Confirmation bias — if mental model is wrong, code and test are both wrong |
| G2 | Parser (`parse/python.py`, 376 statements) has no direct tests for modern Python constructs: `match` statements, walrus `:=`, async generators, decorator stacks, multi-clause comprehensions, PEP 695 generics | 91% line coverage masks edge-case blind spots in the most algorithmically complex module |
| G3 | No invariants enforced (`cyclomatic ≥ 1`, `cognitive ≥ 0`, `0 ≤ bimodality ≤ 1`) | Silent violations possible on inputs outside fixture set |
| G4 | Same ~10 toy fixtures (`metric_fixtures.py`) back almost every metric | One bad fixture = multiple blind spots |
| G5 | No mutation-testing signal | Can't prove tests detect algorithm breakage |
| G6 | Dogfood run is eyeballed, not asserted (`b1b0565`) | No regression guard |

---

## Scope Decisions (locked)

1. **MVP-in-scope (this plan):** G1, G2, G3, G4. These address correctness risk in code we've already shipped and are cheap enough to land in small commits.
2. **Post-MVP (defer):** G5 (mutation testing), G6 (golden-file dogfood assertions). G5 is slow (CI minutes) and G6 duplicates work that Slice 5+ reporting will enable naturally.
3. **`radon` as a dev-only dep** for differential testing of `cyclomatic` and `cognitive`. Added to `[dependency-groups].test`, never shipped. Non-negotiable for G1.
4. **`hypothesis` as a dev-only dep** for property-based invariant tests (G3). Added to `[dependency-groups].test`.
5. **No scope creep into new metrics.** LCOM-HS, class-level metrics, cross-file aggregation remain Slice 4c+ territory.
6. **One commit per logical change**, per Gary's working agreement. Expect ~6 commits.
7. **Calibration tolerance** for differential tests: exact match on `cyclomatic` (both should follow McCabe). Cognitive may legitimately differ from radon's cognitive — document the delta rather than forcing match.
8. **Adversarial parser fixtures** go under a new `tests/fixtures/python/adversarial/` directory — clear separation from existing toy fixtures. Each fixture is minimal: one construct per file.

---

## Resolved Questions (answered 2026-04-20)

1. **Deps:** `radon` and `hypothesis` added to `[dependency-groups].test`. Both pure-Python, small, stable.
2. **Cognitive-vs-radon:** document deltas in `# KNOWN DELTAS` comments; assert our own values with xfail-strict against radon where they diverge. No forced exact-match.
3. **Adversarial scope:** keep all 8 constructs. Cheap to write; `match`/walrus/PEP 695 are real Python 3.12 code.
4. **Mutation testing (G5):** one-off local run on `src/savviety_instinct/analyze/metrics/` after Task 5; appendix to this plan with the score. No CI wiring.
5. **Branch:** `test-hardening-algorithmic-rigor`, off master at `466525e`.

---

## File Structure

| Path | New/Modify | Purpose |
|------|------------|---------|
| `pyproject.toml` | Modify | Add `radon` + `hypothesis` to `[dependency-groups].test` |
| `tests/fixtures/python/adversarial/` | New dir | Adversarial parser fixtures |
| `tests/fixtures/python/adversarial/match_statement.py` | New | PEP 634 `match` / `case` patterns |
| `tests/fixtures/python/adversarial/walrus.py` | New | `(x := expr)` in conditions, comprehensions |
| `tests/fixtures/python/adversarial/async_generator.py` | New | `async def` + `yield`, `async for`, `async with` |
| `tests/fixtures/python/adversarial/decorator_stack.py` | New | 3+ stacked decorators, `@property` with `@setter` |
| `tests/fixtures/python/adversarial/multi_clause_comp.py` | New | Comprehensions with multiple `for`/`if` clauses |
| `tests/fixtures/python/adversarial/nested_functions.py` | New | Closures, nested def, nested class-in-function |
| `tests/fixtures/python/adversarial/generics_pep695.py` | New | `def f[T](x: T) -> T` syntax (3.12+) |
| `tests/fixtures/python/adversarial/exception_groups.py` | New | `try/except*` (PEP 654) |
| `tests/test_parse_adversarial.py` | New | Parse adversarial fixtures; assert no exceptions, function counts, delegation_kind where applicable |
| `tests/test_metric_differential_cyclomatic.py` | New | Parametrized over all `metric_fixtures.py` + adversarial fixtures; assert `cyclomatic == radon.complexity.cc_visit(...)` per function |
| `tests/test_metric_differential_cognitive.py` | New | Same shape; document deltas as `pytest.param(..., marks=pytest.mark.xfail(strict=True, reason="..."))` where our definition diverges |
| `tests/test_metric_invariants.py` | New | Hypothesis-based property tests: `cyclomatic ≥ 1`, `cognitive ≥ 0`, `0 ≤ bimodality ≤ 1`, `statement_count ≥ 0`, `npath ≥ 1`, `0 ≤ identifier_quality ≤ 1`, `0 ≤ trivial_delegation_ratio ≤ 1` |

---

## Task Ordering

Each task commits independently. Each commit green.

- [ ] **Task 1 — Dep addition.** Add `radon` + `hypothesis` to test deps. `uv sync`. Verify `uv run pytest` still 296 passed, 0 new failures. Commit: `chore(deps): add radon + hypothesis to test group for hardening plan`.
- [ ] **Task 2 — Adversarial parser fixtures + tests.** Add 8 adversarial fixtures + `test_parse_adversarial.py`. For each fixture: assert parse succeeds, assert expected function count, assert `delegation_kind` classification where it applies. Reveals parser bugs early. Commit: `test(parse): adversarial fixtures for modern Python constructs`.
- [ ] **Task 3 — Invariant tests (hypothesis).** Generate synthetic Python via hypothesis strategies (or sample from adversarial fixtures) and assert value-range invariants on each metric. Settings: `max_examples=50`, `deadline=None`. Commit: `test(analyze): property-based invariant tests for metric value ranges`.
- [ ] **Task 4 — Differential cyclomatic.** Parametrize over all existing `metric_fixtures.py` functions + adversarial fixtures; assert exact match against `radon.complexity.cc_visit`. If any delta, root-cause before skipping. Commit: `test(analyze): differential cyclomatic vs radon — ground-truth check`.
- [ ] **Task 5 — Differential cognitive.** Same parametrization; assert match where definitions agree, xfail-strict where we diverge, with inline `# reason: ...`. Commit: `test(analyze): differential cognitive vs radon with documented deltas`.
- [ ] **Task 6 — Documentation.** Add a short `docs/testing.md` noting the three rigor layers (unit + differential + property) and the `adversarial/` fixture convention. Commit: `docs: testing strategy — unit, differential, property-based`.

---

## Acceptance

- All 6 tasks merged; test count grows from 296 to ≥ 340 (rough est: +8 adversarial parse tests, +20 differential params, +7 invariant properties, +a few spots).
- Coverage holds at ≥ 93%; `parse/python.py` coverage rises (adversarial fixtures exercise more branches).
- Zero regressions in existing tests.
- If Task 4 uncovers a real cyclomatic discrepancy, fix the metric in a separate commit before landing the differential test.

---

## Non-Goals

- Not adding new metrics.
- Not refactoring existing metric code beyond bugs surfaced by differential tests.
- Not wiring mutation testing into CI (deferred; see §Scope Decisions #2).
- Not adding golden-file regression tests on the dogfood run (deferred).

---

## Bugs Surfaced by This Plan

Running log — populated as tasks execute. Each entry cites the fixture/test
that surfaced it. No commitment in this plan to fix; captured so they become
candidates for follow-up slices.

| # | Surfaced in | Summary | Severity |
|---|-------------|---------|----------|
| B1 | Task 2 — `match_statement.py` | `match_statement` / `case_clause` absent from `_STATEMENT_NODE_TYPES` and `_TS_TO_CFN_KIND`. Match-only bodies yield `statement_count=0`. Breaks `median_function_length`, `function_length_bimodality`, `trivial_delegation_ratio` for any 3.10+ module using match. | Medium — wrong-data silently |
| B2 | Task 2 — `decorator_stack.py` | `qualified_name` uniqueness violated — `@property` getter and `@setter` share `"Thing.name"`. Consumers keyed by qualified_name collapse them. | Medium — latent data-integrity |

---

## Risk

| Risk | Mitigation |
|------|------------|
| Differential cyclomatic reveals a real bug in our metric | Fix it — this is the point of the exercise. Separate commit, cite radon as ground truth |
| Hypothesis generates pathological programs that crash the parser | Narrow the strategy to syntactically-valid subsets; catch `SyntaxError` at parse boundary |
| `radon` output format changes | Pin version in `pyproject.toml`; version exists in `uv.lock` regardless |
| Scope creep ("while we're here, let's also...") | Per Gary's rule: default to "not in MVP". Log ideas in a follow-up issue |
