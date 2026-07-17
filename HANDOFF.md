# Instinct — Session Handoff

**Purpose:** enable a fresh Claude Code session (or a returning Gary) to resume without reconstructing context from git log + memory.

**Last updated:** 2026-07-17
**State at handoff:** Slices 1–5 on master, plus test hardening (PR #6), parser-bug fixes (PR #7), and the ast_hash-identity fixes (PR #9 + PR #8's storage half). **Slice 5 merged as PR #8** — storage is the active write path. 461 tests passing on master. Next: Slice 6 (reports + ranking + profile), pending scope confirmation with Gary.

---

## Read these first (in order)

All design docs live in `docs/`:

1. `docs/03-executive-summary.md` — what Instinct is and why
2. `docs/01-locked-decisions.md` — D1–D10, frozen
3. `docs/02-prd.md` — MVP requirements
4. `docs/04-architecture-spec.md` — module layout, schema, slice plan (§15)
5. `docs/05-metric-catalog.md` — metric formulas (reference)

Then:

6. `docs/plans/2026-05-08-slice-5-storage-writes.md` — current open slice plan; template for slices that touch storage
7. `docs/plans/2026-04-19-slice-4b-module-metrics.md` — most recent shipped feature-slice plan; template for pure metric work
8. `docs/plans/2026-04-20-test-hardening-algorithmic-rigor.md` — cross-cutting initiative template (test rigor + bug appendix pattern)
9. `docs/testing.md` — three-layer test strategy (unit / differential / property-based); adversarial fixture convention
10. Prior plans under `docs/plans/` for Slices 1–4a — how things got here
11. `.claude/SESSION.md` (if present; per-machine, gitignored) — in-flight state

---

## Quick-start: "I just sat down, what do I do?"

1. `/whereami` — branch state, open PRs, last session context
2. Check https://github.com/garyld1962/savviety-instinct/pulls — anything open?
3. No open PRs at handoff time. Next work is Slice 6 (see §"Next work") — confirm scope with Gary before coding.
4. If this doc looks stale, refresh from `git log master --oneline -10` + `gh pr list --state all --limit 5`.

---

## Project state

- **8 source modules populated** per arch §2 layout: `core/`, `storage/`, `config/`, `cli/`, `parse/`, `graph/`, `analyze/`. Reserved skeletons (`llm/`, `curate/`, `patterns/`, `suggest/`, `mcp/`, `report/`) are empty `__init__.py` stubs.
- **Test count: 461 passed on master tip (`2f97c95`).** Coverage 91% (TOTAL). `parse/python.py` at 91% line coverage; storage modules between 87% and 100%.
- **PR cadence:** one PR per slice from arch §15. Merge-commit style (not squash). Branches live after merge — not deleted. Non-slice initiatives (test hardening, bug sweeps) get their own plan doc under `docs/plans/` and follow the same merge-commit flow.
- **Python 3.12+**, `uv`-managed (no pip/poetry/pyenv). Typer CLI. Pydantic v2 config. SQLAlchemy 2 + Alembic for the SQLite schema — **active writer in Slice 5** (PR #8).

### Shipped to master

| Slice / Initiative | Scope | Merge commit |
|---|---|---|
| Slice 1 | Bootstrap: `core/` types, `storage/` interfaces + schema migration, `config/`, `cli/` (version + init + R2 stubs), pre-commit hooks, NFR-1 no-network test | PR #1 (`ebd23a8`) |
| Slice 2 | `parse/` (Python via tree-sitter), `graph/` (intra-file call graph), `ast_hash` via blake3/xxhash, `AnalysisContext.call_graph` | PR #2 (`25b41a9`) |
| — | CLAUDE.md scaffold | `63efd7c` |
| Slice 3 | Three metrics (`statement_count`, `cyclomatic`, `cognitive`), `ControlFlowNode`, `analyze/pipeline.py`, `instinct run <path>`, cognitive rules YAML | PR #3 (`c20e97c`) |
| Slice 4a | Function metrics: `max_nesting_depth`, `npath`, `identifier_quality`; `FunctionDefNode.identifier_names` | PR #4 |
| Slice 4b | Module metrics: `trivial_delegation_ratio`, `median_function_length`, `function_length_bimodality`; first `ArtifactKind.MODULE` pipeline dispatch; `DelegationKind` enum; registry-duplication collapse | PR #5 (`2a40ae7`) |
| Test hardening | Cross-cutting: 26 adversarial parse fixtures, 9 hypothesis invariants, 57 differential tests (cyclomatic vs `radon`, cognitive vs `cognitive_complexity` pkg), `docs/testing.md`. Surfaced bugs B1/B2/B3. | PR #6 (`da8b4c4`) |
| Parser bug fixes | B1 (`match` / `case_clause`), B2 (`@property`/`@setter` qualified_name collision via `[getter]`/`[setter]`/`[deleter]` suffix), B3 (`except_group_clause`). Metric versions: `cyclomatic`, `cognitive`, `statement_count` → 1.2.0. | PR #7 (`424c55e`) |
| ast_hash identity fix | `ast_hash` is identifier-blind and was wrongly used as a per-occurrence identity. Metric lookup now via `_resolve.py::resolve_function_node()` keyed on `source_range`; `identifier_quality` → 1.1.0. | PR #9 (`8b8dfc1`) |
| Slice 5 | Observation store writes + dormant shortcut (see below); includes the storage half of the ast_hash fix (`Metric.shape_invariant`, commit `2f97c95`) | PR #8 |

### Slice 5 detail (merged)

Observation store writes. Closes the "Accumulate" half of the MVP per arch §4.1 / §8.2 / D10.

- **`storage/sqlite_store.py:SQLAlchemyObservationStore`** — concrete `ObservationStore` Protocol impl. Auto-upgrades schema to head on construction (programmatic Alembic Config, cached module-level). Per-engine WAL + synchronous=NORMAL pragmas via SQLAlchemy event listener.
- **`storage/fingerprint.py:derive_repo_fingerprint(cwd)`** — three-tier (first-commit SHA → origin URL → synthetic hostname:abspath). Source label written to `runs.repo_fingerprint_source`.
- **`storage/run_meta.py`** — `compute_config_hash`, `compute_combined_metric_version` (compact `mv_<sha12>` hash of sorted `id:version` pairs — Scope #2), `derive_git_commit_branch`.
- **`analyze/persistence.py:run_pipeline_with_persistence(path, config, store)`** — wraps `analyze.pipeline.run_pipeline`'s machinery with the store and adds the dormant-artifact shortcut. Bare `run_pipeline` stays storage-free so existing unit tests keep bypassing the DB.
- **Dormant shortcut**: `ObservationStore.try_dormant_shortcut(run_id, ast_hash, language)` returns `(artifact_id, cached_metrics) | None`. On hit, bumps `last_seen_run_id` / `occurrence_count` / `stability_tier` atomically and the wrapper yields cached metrics for **shape-invariant metrics only** (`Metric.shape_invariant`); `identifier_quality` and `trivial_delegation_ratio` are recomputed per occurrence and never enter `metrics_json` (they read identifier text, which ast_hash omits). Proven by a compute-call spy on `CYCLOMATIC_METRIC` in `tests/integration/test_re_run.py` plus `tests/integration/test_shape_invariant_metrics.py`.
- **`stability_tier` minimal** (Scope #3): `volatile` → `settled` at `occurrence_count >= 2`. `dormant` deferred to Slice 6.
- **`context_hash` partial** (Scope #5): `sha256(language|enclosing_class|caller_count|callee_count)`. R2 extends per D6.
- **CLI wired**: `instinct run` opens the store at `<cwd>/.instinct/instinct.db`, calls the persistence wrapper. Stdout output unchanged from Slice 3.
- **Out of scope** (deferred): `rankings`, `run_profiles` (Slice 6); 180-day TTL cleanup; `instinct vacuum`; read-side `ObservationQuery` impl; `dormant` tier transitions; `instinct sync` (R2).

---

## Working agreement (frozen — Gary's rules)

- **`uv` only.** No `pip`, `poetry`, `pyenv`.
- **Decisions in `docs/01-locked-decisions.md` are frozen.** If you think one is wrong, raise it explicitly — do not silently work around. (2026-05-08 example: I briefly considered centralized SQL Server storage; raising D10 / D5 / D8 conflicts reverted the direction — D10 stays as locked.)
- **Layer boundaries from arch spec §2 are absolute.** `core` is at the bottom; `analyze/` and `curate/` never import each other; all DB access goes through `storage/`. Use `TYPE_CHECKING` + quoted annotations to preserve layering when a lower-layer type needs to reference an upper-layer type.
- **Every PR maps to one slice from §15** (or a cross-cutting initiative with its own plan doc). No combining slices. One plan per slice under `docs/plans/`.
- **Tests required per metric before that metric merges.** Ground-truth fixtures are authoritative; iterate code to match the fixture, not the other way around.
- **One commit per logical change.** Task-level commits within a slice; slice-level merge commit on master.
- **When in doubt about scope, default to "not in MVP."**

---

## Key design decisions carried forward

These are encoded in code; listed here so a fresh agent doesn't reinvent them:

### Layering (arch §2)
`core` → `config / storage / parse / graph / analyze / cli` hierarchy is absolute. `core.types.AnalysisContext` references `CallGraph` and `ParseResult` via `TYPE_CHECKING` + quoted string annotations — no runtime import. Verified by a `sys.modules` assertion in tests.

### Storage model (D10 + Slice 5)
SQLite per-repo at `.instinct/instinct.db` is canonical. Postgres warehouse reserved as a one-way derived view (R2+). `repo_fingerprint` column on `runs` and `observation_artifacts` carries repo identity for warehouse aggregation. **Slice 5 (PR #8, merged) is the first writer:** `instinct run` persists `runs` + `observation_artifacts` + `run_observations` with full dormant-artifact dedup. `rankings` and `run_profiles` tables exist but stay empty until Slice 6.

### `ast_hash` (arch §4.2, D6)
`blake3` preferred, `xxhash` fallback at import time. `HASH_ALGORITHM` constant records backend. Normalization is **whitespace-only** — tree-sitter's `str(node)` natively omits identifier text and literal values (discovered empirically during Slice 2 code review). The hash is shape-invariant across identifier/literal changes without any normalizer work.

**Consequence (PR #9): ast_hash is NOT a per-occurrence identity.** Shape-identical functions (e.g. delegation wrappers) share a hash. Anything keyed on ast_hash may only carry shape-determined data; per-occurrence lookups go through `source_range`, and per-occurrence metric values (`Metric.shape_invariant is False`) are never served from shape-keyed caches.

### Combined `metric_version` (Slice 5 Scope #2)
The schema's single `metric_version` column on `runs` and `observation_artifacts` predates the multi-metric reality. Slice 5 computes a per-run `mv_<sha12>` hash of every registered metric's `id:version` pair (sorted, joined by `|`). Adding or bumping any metric changes the combined version, naturally invalidating dedup at the previous version — old rows stay inert. Refactor to per-metric versioning is out of MVP scope.

### Intra-file call graph (Slice 2)
`networkx.DiGraph` wrapped by `CallGraph`. Unresolved callees are silently DROPPED (no `ExternalCallee` placeholders — Scope Decision #2 from Slice 2 plan). Cross-file resolution is post-MVP.

### ControlFlowNode tree (Slice 3 + parser bug fixes)
Domain-neutral nodes (IF/ELIF/ELSE/FOR/WHILE/TRY/EXCEPT/MATCH/CASE/TERNARY/BOOLEAN_SEQUENCE/COMPREHENSION) pre-computed on `FunctionDefNode.control_flow` during parse. elif/else/except/case emitted as SIBLINGS at parent's depth (Sonar semantics), not children. MATCH itself is a marker (base=0); each CASE is a sibling like elif (base=1, increments_nesting=false). `except_group_clause` mapped to EXCEPT (PR #7's B3 fix).

### Cognitive rules YAML (Slice 3)
`src/savviety_instinct/core/cognitive_rules/python.yaml` — per-language increment table. Cognitive metric tracks cumulative nesting via `rule.increments_nesting` (NOT parse-level `ControlFlowNode.nesting_depth`), keeping parser rule-agnostic. Loader fails fast if any `ControlFlowNodeKind` has no rule — forces coordinated enum + YAML updates.

### Metric pattern
Each metric class lives in `src/savviety_instinct/analyze/metrics/<name>.py` exporting a module-level singleton `<NAME>_METRIC`. Metrics conform to `core.types.Metric` Protocol (Slice 1), including the `shape_invariant: bool` attribute (PR #8). Function metrics look up their `FunctionDefNode` via `metrics/_resolve.py::resolve_function_node()` keyed on `source_range` (PR #9 — never by `ast_hash`; shape collisions) — O(N) per metric per artifact.

### qualified_name disambiguator (PR #7 / B2)
`_collect_functions` inspects each function's `decorated_definition` parent. `@property` → `[getter]` suffix; `@<name>.setter` → `[setter]`; `@<name>.deleter` → `[deleter]`. Other duplicates fall back to `@L<line>`. Pinned by `test_decorator_stack_property_setter_disambiguated`.

### Persistence wrapper (Slice 5)
`analyze.persistence.run_pipeline_with_persistence(path, config, store)` is the only entry point that touches the DB. `analyze.pipeline.run_pipeline` stays a pure generator so metric unit tests keep bypassing storage. The dormant-shortcut path (`try_dormant_shortcut`) yields cached shape-invariant metrics straight from `metrics_json` and recomputes the non-shape-invariant ones per occurrence. Compute-call spy in `tests/integration/test_re_run.py` enforces the optimization.

### Registry (single source)
`METRICS_REGISTRY` lives in `src/savviety_instinct/analyze/__init__.py` and is the single source of truth. Slice 4b deleted the duplicate `_METRICS` tuple from `pipeline.py`. Adding a new metric now requires one registry update. Module-load-time `assert` guards against a metric with an empty `applies_to`.

---

## Patterns that have paid off (apply to future slices)

### Empirical-first before algorithm design
When an algorithm depends on tree-sitter or CFN-tree structure, **run a REPL inspection before writing code.** Each time this discipline was followed, it surfaced a reality the plan didn't anticipate:
- Slice 2 Task 5: `str(tree_sitter.Node)` omits literals and identifiers natively
- Slice 3 Task 8: boolean_operator in if-condition emits as sibling, not child
- Slice 4a Task 4: BOOLEAN_SEQUENCE emits as sibling AFTER the IF — drove npath chain-consumption design
- PR #7 B1: `case_clause` uses `consequence` field (not `body`) for its block — caught by the bare-metric REPL probe before the integration test would have surfaced statement_count=1 instead of 4
- PR #7 B3: tree-sitter parses `except*` as `except_group_clause`, not `except_group` as the fixture docstring originally guessed

### Ground-truth fixtures as correctness net
`tests/fixtures/python/metric_fixtures.py` has 10 hand-crafted functions with expected values for all 9 metrics documented in each function's docstring. **Do not adjust fixture values to match code output — iterate code to match the documented ground truth.** Adversarial fixtures under `tests/fixtures/python/adversarial/` add one-construct-per-file stress cases.

### Differential tests as drift-detector
`tests/test_metric_differential_*.py` pin both sides' values when we deliberately diverge from a reference tool — `radon` for cyclomatic, `cognitive_complexity` PyPI pkg for cognitive. Drift on either side surfaces for review. Don't move a delta back into AGREEMENT_CASES without verifying both tools.

### Strict-xfail for found bugs
When a test surfaces a real bug mid-plan, pin it with `xfail(strict=True)` rather than expanding plan scope to fix. The strict mode flips to failure when the bug is fixed, forcing marker removal. B1/B2 used this pattern from PR #6 through PR #7's fix.

### Subagent-driven task execution
Per-task subagent dispatch (from `superpowers:subagent-driven-development`) with two-stage review (spec compliance → code quality) catches bugs that unit tests miss. Fresh-context per subagent also preserves the main thread's context budget.

---

## Gotchas & invariants

- **`FunctionDefNode.is_method` is a `@property`**, not a field. Never pass `is_method=...` as kwarg.
- **`ParseResult.language: Language`** — enum, not `.value` string. Construct with `language=Language.PYTHON`.
- **Parameters referenced in body DO appear in `identifier_names`.** The field collects body USAGES; parameter DECLARATIONS live on `parameter_names`.
- **elif/else/except/case are siblings at parent's depth.** Cognitive/cyclomatic/max_nesting/npath all depend on this invariant. `match_statement` itself is a no-cost marker; the case_clauses do the counting.
- **`@property`/`@setter` methods now disambiguate via `[getter]`/`[setter]`/`[deleter]` suffix on `qualified_name`.** Don't normalize this away — downstream consumers and the test pin specific shapes.
- **`ObservationStore.upsert_artifact` takes `run_id` as first arg** (PR #8 amended the Protocol). Implicit-state coupling was rejected; thread it explicitly.
- **`try_dormant_shortcut` has a side effect** — on hit, it bumps `last_seen_run_id` / `occurrence_count` / `stability_tier` atomically with the lookup. Callers must not "check first, then bump" — that's two transactions and a race.
- **`metrics_json` carries shape-invariant metrics ONLY.** `identifier_quality` and `trivial_delegation_ratio` are per-occurrence (identifier-dependent) and are recomputed on every path — they are not persisted anywhere yet. Slice 6 ranking must not expect them in the store; persisting them properly needs the per-metric side table (see deferred housekeeping). Any new metric MUST declare `shape_invariant` honestly — a wrong `True` silently revives the stale-cache bug.
- **Never key per-occurrence data on `ast_hash`.** Shape-identical functions share a hash (delegation wrappers especially). Function lookup identity is `source_range`; residual corner: two lambdas on one line still collide (line-based ranges).
- **RTK proxy filters merge commits from `git log` output.** Use `rtk proxy git log ...` for merge archaeology.
- **Default config `suppress: [...]` includes `**/tests/**`.** Tests that operate on `tests/fixtures/` must override with `suppress: []` in their test config.
- **Row-count tests are parametrized via `tests/_helpers.py::expected_row_count`** against `METRICS_REGISTRY`. Slice 4b did this refactor — do not re-introduce hard-coded counts.
- **Cognitive rules YAML must be complete.** Loader raises if any `ControlFlowNodeKind` has no rule. Adding a new kind requires updating every language's YAML.
- **Parse-layer helpers in `parse/python.py`** have grown substantial (~900 lines after PR #7). `_collect_functions`, `_collect_control_flow`, `_count_statements`, `_collect_identifiers` all traverse the function body. Eventually worth refactoring to a single-pass tree visitor; not urgent.
- **stdlib `sqlite3` datetime-adapter `DeprecationWarning` is filtered in `pyproject.toml`** (Python 3.12 + SQLAlchemy interaction). Don't unsuppress without a real fix.

---

## Next work

PR #8 merged 2026-07-17; storage is the active write path. Four options, in recommended order:

**1. Slice 6 — Report generators + ranking + profile (recommended next per arch §15).**
The natural follow-on from Slice 5: with observations now persisted, surface them. Includes:
- `analyze/ranking.py` — `attention_priority` computation (arch §6) with confidence dampener
- `analyze/profile.py` — per-axis percentiles + status (`normal` / `watch` / `elevated`)
- `report/terminal.py`, `report/json.py`, `report/html.py` — the three Phase-1 renderers
- Wires `ObservationStore.write_ranking` / `write_profile` (currently raising `NotImplementedError`)
- Implements `ObservationQuery` read-side Protocol so renderers can pull historical context
- Adds `dormant` stability tier transition (now that there's a consumer reading tier)

**2. Slice 4c — LCOM-HS (class-level cohesion).**
Deferred from Slice 4b per its Scope Decision #1. Needs method ↔ attribute-read graph extraction in the parse layer. Non-trivial; plan should flag empirical CFN/AST probe as an early task.

**3. Graph infrastructure detour.**
- Cross-file call resolution
- Module dependency graph
- Unlocks arch §3.x coupling metrics (afferent, efferent, instability, abstractness, D, Henry-Kafura)

**4. Temporal infrastructure detour.**
- pydriller or gix integration for git history
- Unlocks arch §5.x (change_frequency, bug_fix_density, author_count, stability_tier as a real metric)

### Deferred housekeeping (not urgent)

- Fix Slice 4a `metric_version = 1.0.0` documented approximations (NPATH condition, comprehension, ternary, lambda attribution, context-blind stopwords). Coordinated parse-layer + metric-version bump.
- 180-day TTL cleanup on `run_observations` (arch §8.4). Defer until there's data old enough to need it.
- Per-metric versioning refactor — current schema has a single `metric_version` column; we work around with the combined hash. Real fix is a `metric_values` side table keyed by `(artifact_id, metric_id, metric_version)`. **Priority raised by the shape_invariant split:** non-shape-invariant metrics are currently not persisted at all, and R2's comprehensibility metrics (`name_body_drift` etc.) will all be non-shape-invariant — the side table (keyed per occurrence, not per shape) becomes load-bearing before R2.
- Mutation-testing baseline: previously attempted via `mutmut` 3.x, shelved due to src-layout friction. Alternatives documented in the hardening plan's mutation appendix.
- `read-side ObservationQuery` Protocol implementation — naturally lands with Slice 6.

---

## Process reminders for the next session

1. **Start with `/whereami`** in the new session.
2. **Confirm scope with Gary before writing code** for a new slice — he expects this. HANDOFF.md's "Next work" section is my proposal; his decision overrides.
3. **Follow the most recent slice plan's style.** Slice 5 (`docs/plans/2026-05-08-slice-5-storage-writes.md`) is the freshest example with a storage-layer touch; Slice 4b is the freshest pure-metric example; test-hardening plan is the freshest cross-cut.
4. **Ground-truth fixtures before metrics.** Add expected values to `metric_fixtures.py` or a new fixture file (module-level metrics live under `tests/fixtures/python/modules/`; adversarial parser cases live under `tests/fixtures/python/adversarial/`) BEFORE implementing.
5. **Empirical CFN inspection** when writing any metric that reads `ControlFlowNode` structure. REPL commands included in prior plan docs.
6. **Subagent-driven execution** has worked cleanly for 4 feature slices. Use `superpowers:subagent-driven-development` skill for feature slices. Cross-cutting initiatives and tight bug-fix branches can run tasks inline.
7. **Merge-commit style** for slice and initiative PRs. Don't squash.
8. **When a test surfaces a real bug mid-plan, pin it with `xfail(strict=True)`** rather than expanding plan scope. Log in the plan's "Bugs Surfaced" appendix.
9. **Tests should bypass the store by default.** Metric unit tests use `analyze.pipeline.run_pipeline`; only CLI-level and explicit storage tests use `analyze.persistence.run_pipeline_with_persistence`. Don't accidentally couple a metric test to SQLite — that's a contract violation.
10. **Feedback memory to honor:** raise locked-decision concerns, give opinion before decisions, one commit per logical change, default to "not in MVP."

---

## How to resume

1. Read this file.
2. Read `docs/01-locked-decisions.md` and `docs/04-architecture-spec.md` §2/§4/§5/§8/§15 if unfamiliar.
3. Read `docs/plans/2026-05-08-slice-5-storage-writes.md` for the freshest storage-touching slice plan; `docs/plans/2026-04-19-slice-4b-module-metrics.md` for the most recent feature-slice template; `docs/testing.md` for test-strategy.
4. Confirm next work scope with Gary before coding (see §"Next work").
5. Start with `/whereami` in any new session.

---

## Contact / pointers

- Shared skills installed via `savviety-skills` — see `CLAUDE.md` in repo root.
- Per-developer overrides live in `CLAUDE.local.md` (gitignored).
- Per-machine session state lives in `.claude/SESSION.md` (gitignored).
- PRs: https://github.com/garyld1962/savviety-instinct/pulls
