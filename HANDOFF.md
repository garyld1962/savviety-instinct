# Instinct — Session Handoff

**Purpose:** enable a fresh Claude Code session (or a returning Gary) to resume without reconstructing context from git log + memory.

**Last updated:** 2026-04-21
**State at handoff:** Slices 1–4b merged to master. Cross-cutting test hardening initiative shipped as PR #6 (open, awaiting review/merge). Three parser bugs (B1–B3) surfaced by the hardening layer and logged for follow-up.

---

## Read these first (in order)

All design docs live in `docs/`:

1. `docs/03-executive-summary.md` — what Instinct is and why
2. `docs/01-locked-decisions.md` — D1–D10, frozen
3. `docs/02-prd.md` — MVP requirements
4. `docs/04-architecture-spec.md` — module layout, schema, slice plan (§15)
5. `docs/05-metric-catalog.md` — metric formulas (reference)

Then:

6. `docs/plans/2026-04-19-slice-4b-module-metrics.md` — most recent shipped slice plan; template for module-level metric work
7. `docs/plans/2026-04-20-test-hardening-algorithmic-rigor.md` — cross-cutting test rigor initiative (PR #6); template for non-slice initiatives and bug appendices
8. `docs/testing.md` — three-layer test strategy (unit / differential / property-based); adversarial fixture convention
9. Prior plans under `docs/plans/` for Slices 1, 2, 3, 4a — how things got here
10. `.claude/SESSION.md` (if present; per-machine, gitignored) — in-flight state

---

## Quick-start: "I just sat down, what do I do?"

1. `/whereami` — branch state, open PRs, last session context
2. Check https://github.com/garyld1962/savviety-instinct/pulls — is PR #6 still open?
3. If yes, review/merge it, then pick next-step from §"Next work" below
4. If no, refresh this doc from `git log` + check PR list for anything newer

---

## Project state

- **6 source modules populated** per arch §2 layout: `core/`, `storage/`, `config/`, `cli/`, `parse/`, `graph/`, `analyze/`. Reserved skeletons (`llm/`, `curate/`, `patterns/`, `suggest/`, `mcp/`, `report/`) are empty `__init__.py` stubs.
- **386 passed + 2 xfail** on the hardening branch (pre-PR-6 merge: 296 passed). Coverage ≥93% with hardening layer; `parse/python.py` at 91% line coverage but now stress-tested by adversarial fixtures.
- **PR cadence:** one PR per slice from arch §15. Merge-commit style (not squash). Branches live after merge — not deleted. Non-slice initiatives (test hardening, bug sweeps) get their own plan doc under `docs/plans/` and follow the same merge-commit flow.
- **Python 3.12+**, `uv`-managed (no pip/poetry/pyenv). Typer CLI. Pydantic v2 config. SQLAlchemy 2 + Alembic for the (unwritten-to) SQLite schema.

### Slices shipped (commits on master)

| Slice | Scope | Merge commit |
|-------|-------|--------------|
| 1 | Bootstrap: `core/` types, `storage/` interfaces + schema migration, `config/`, `cli/` (version + init + R2 stubs), pre-commit hooks, NFR-1 no-network test | `ebd23a8` (PR #1) |
| 2 | `parse/` (Python via tree-sitter), `graph/` (intra-file call graph), `ast_hash` via blake3/xxhash, `AnalysisContext.call_graph` | `25b41a9` (PR #2) |
| — | CLAUDE.md scaffold standalone commit | `63efd7c` |
| 3 | Three metrics (`statement_count`, `cyclomatic`, `cognitive`), `ControlFlowNode`, `analyze/pipeline.py`, `instinct run <path>`, cognitive rules YAML | `c20e97c` (PR #3) |
| 4a | Three function-level metrics (`max_nesting_depth`, `npath`, `identifier_quality`); `FunctionDefNode.identifier_names` field | PR #4 (merged) |
| 4b | Three module-level metrics (`trivial_delegation_ratio`, `median_function_length`, `function_length_bimodality`); first `ArtifactKind.MODULE` pipeline dispatch; `DelegationKind` enum; registry-duplication collapse (deleted `_METRICS`); row-count tests parametrized via `tests/_helpers.py` | `2a40ae7` (PR #5) |

### Test hardening (current state — branch `test-hardening-algorithmic-rigor`, PR #6 open)

Cross-cutting test rigor initiative (not a slice). Adds three layers atop existing unit tests: 26 adversarial parse fixtures under `tests/fixtures/python/adversarial/`, 9 hypothesis-based invariant tests, 57 differential tests (cyclomatic vs `radon`, cognitive vs `cognitive_complexity` package). `docs/testing.md` onboards future contributors. Three parser bugs surfaced, logged, **not fixed** — see §"Bugs awaiting fix" below. Plan: `docs/plans/2026-04-20-test-hardening-algorithmic-rigor.md`.

### Bugs awaiting fix (surfaced by PR #6's adversarial layer)

Logged in the hardening plan's "Bugs Surfaced" appendix. All three are silent-undercount bugs — tests still pass on existing fixtures; the hardening layer is what exposed them.

| # | Severity | Summary |
|---|----------|---------|
| **B1** | High | `match_statement` / `case_clause` absent from `_STATEMENT_NODE_TYPES` and `_TS_TO_CFN_KIND`. Match-only bodies report `statement_count=0`, `cyclomatic=1`, `cognitive=0`. Breaks `median_function_length`, `function_length_bimodality`, `trivial_delegation_ratio`, `cyclomatic_complexity`, `cognitive_complexity` for any 3.10+ module using pattern matching. |
| **B2** | Medium | `qualified_name` uniqueness violated — `@property` getter and `@setter` share `"Thing.name"`. Consumers keyed by qualified_name (test helpers, future SQL storage) silently collapse them. |
| **B3** | Medium | `except_group` (PEP 654 `except*`) absent from `_TS_TO_CFN_KIND`. Not counted as a decision. Asymmetric vs the `cognitive_complexity` reference package, which correctly counts `except*` clauses — confirms this is an undercount, not a shared blind spot. |

B1 and B2 are pinned via `xfail(strict=True)` in `tests/test_parse_adversarial.py` — they flip to unexpected-pass (and strict-fail) if fixed without removing the marker. B3 is documented in the differential cognitive test only (no xfail; reference tool reveals the asymmetry).

---

## Working agreement (frozen — Gary's rules)

- **`uv` only.** No `pip`, `poetry`, `pyenv`.
- **Decisions in `docs/01-locked-decisions.md` are frozen.** If you think one is wrong, raise it explicitly — do not silently work around.
- **Layer boundaries from arch spec §2 are absolute.** `core` is at the bottom; `analyze/` and `curate/` never import each other; all DB access goes through `storage/`. Use `TYPE_CHECKING` + quoted annotations to preserve layering when a lower-layer type needs to reference an upper-layer type.
- **Every PR maps to one slice from §15.** No combining slices. One plan per slice under `docs/plans/`.
- **Tests required per metric before that metric merges.** Ground-truth fixtures are authoritative; iterate code to match the fixture, not the other way around.
- **One commit per logical change.** Task-level commits within a slice; slice-level merge commit on master.
- **When in doubt about scope, default to "not in MVP."**

---

## Key design decisions carried forward

These are encoded in code; listed here so a fresh agent doesn't reinvent them:

### Layering (arch §2)
`core` → `config / storage / parse / graph / analyze / cli` hierarchy is absolute. `core.types.AnalysisContext` references `CallGraph` and `ParseResult` via `TYPE_CHECKING` + quoted string annotations — no runtime import. Verified by a `sys.modules` assertion in tests.

### Storage model (D10)
SQLite per-repo at `.instinct/instinct.db` is canonical. Postgres warehouse is reserved as a one-way derived view (R2+). `repo_fingerprint` column carries repo identity for warehouse aggregation. **Slice 4a still doesn't write to storage** — that's Slice 5.

### `ast_hash` (arch §4.2, D6)
`blake3` preferred, `xxhash` fallback at import time. `HASH_ALGORITHM` constant records backend. Normalization is **whitespace-only** — tree-sitter's `str(node)` natively omits identifier text and literal values (discovered empirically during Slice 2 code review). The hash is shape-invariant across identifier/literal changes without any normalizer work.

### Intra-file call graph (Slice 2)
`networkx.DiGraph` wrapped by `CallGraph`. Unresolved callees are silently DROPPED (no `ExternalCallee` placeholders — Scope Decision #2 from Slice 2 plan). Cross-file resolution is post-MVP.

### ControlFlowNode tree (Slice 3)
Domain-neutral nodes (IF/ELIF/ELSE/FOR/WHILE/TRY/EXCEPT/TERNARY/BOOLEAN_SEQUENCE/COMPREHENSION) pre-computed on `FunctionDefNode.control_flow` during parse. elif/else/except emitted as SIBLINGS at parent's depth (Sonar semantics), not children. Boolean_operator in if-condition also a sibling. Fourteen empirically-verified test cases in `test_parse_control_flow.py`.

### Cognitive rules YAML (Slice 3)
`src/savviety_instinct/core/cognitive_rules/python.yaml` — per-language increment table. Cognitive metric tracks cumulative nesting via `rule.increments_nesting` (NOT parse-level `ControlFlowNode.nesting_depth`), keeping parser rule-agnostic. Loader fails fast if any `ControlFlowNodeKind` has no rule — forces coordinated enum + YAML updates.

### Metric pattern
Each metric class lives in `src/savviety_instinct/analyze/metrics/<name>.py` exporting a module-level singleton `<NAME>_METRIC`. Metrics conform to `core.types.Metric` Protocol (Slice 1). `Metric.compute(artifact, context)` looks up the `FunctionDefNode` in `context.parse_result.functions` by `ast_hash` — O(N) per metric per artifact. All 6 Slice 3+4a metrics follow this pattern.

### Registry (single source)
`METRICS_REGISTRY` lives in `src/savviety_instinct/analyze/__init__.py` and is the single source of truth. Slice 4b deleted the duplicate `_METRICS` tuple from `pipeline.py`. Adding a new metric now requires one registry update. Module-load-time `assert` guards against a metric with an empty `applies_to` (which the pipeline filter would silently drop).

---

## Patterns that have paid off (apply to future slices)

### Empirical-first before algorithm design
When an algorithm depends on tree-sitter or CFN-tree structure, **run a REPL inspection before writing code.** Each time this discipline was followed, it surfaced a reality the plan didn't anticipate:
- Slice 2 Task 5: `str(tree_sitter.Node)` omits literals and identifiers natively
- Slice 3 Task 8: boolean_operator in if-condition emits as sibling, not child — led to a real parse-layer fix
- Slice 4a Task 4: BOOLEAN_SEQUENCE emits as sibling AFTER the IF — drove npath chain-consumption design

### Ground-truth fixtures as correctness net
`tests/fixtures/python/metric_fixtures.py` has 10 hand-crafted functions with expected values for all 6 metrics documented in each function's docstring. **Do not adjust fixture values to match code output — iterate code to match the documented ground truth.** This pattern caught three real parse-layer bugs in Slice 3:
1. Docstring-as-statement inflation
2. Missing `except_clause` in statement count
3. Condition-expression CFN nesting (boolean inside if counted with wrong depth)

Slice 4a ran against the same fixtures and produced correct values first-try — the parse layer has stabilized.

### Subagent-driven task execution
Per-task subagent dispatch (from `superpowers:subagent-driven-development`) with two-stage review (spec compliance → code quality) catches bugs that unit tests miss. Slice 2 Task 5 had 3 Critical correctness bugs caught only by code review (cross-class method-name collision, bare-name false positive, dead branch). Fresh-context per subagent also preserves the main thread's context budget.

---

## Gotchas & invariants

- **`FunctionDefNode.is_method` is a `@property`**, not a field. Never pass `is_method=...` as kwarg.
- **`ParseResult.language: Language`** — enum, not `.value` string. Construct with `language=Language.PYTHON`.
- **Parameters referenced in body DO appear in `identifier_names`.** The field collects body USAGES; parameter DECLARATIONS live on `parameter_names`.
- **elif/else/except are siblings at parent's depth.** Cognitive/cyclomatic/max_nesting/npath all depend on this invariant.
- **RTK proxy filters merge commits from `git log` output.** Use `rtk proxy git log ...` for merge archaeology. Burned time on Slice 2 merge diagnosis when a merge commit was hidden from default output.
- **Default config `suppress: [...]` includes `**/tests/**`.** Tests that operate on `tests/fixtures/` must override with `suppress: []` in their test config.
- **Row-count tests are parametrized via `tests/_helpers.py::expected_row_count`** against `METRICS_REGISTRY`. Slice 4b did this refactor — do not re-introduce hard-coded counts in new tests. `test_cli_run.py`, `test_analyze_pipeline.py`, `tests/integration/test_slice3_pipeline.py`, `tests/integration/test_slice4a_metrics.py`, `tests/integration/test_slice4b_pipeline.py` all use the helper.
- **Cognitive rules YAML must be complete.** Loader raises if any `ControlFlowNodeKind` has no rule. Adding a new kind requires updating every language's YAML.
- **Parse-layer helpers in `parse/python.py`** have grown substantial (~600 lines). `_collect_functions`, `_collect_control_flow`, `_count_statements`, `_collect_identifiers` all traverse the function body. Eventually worth refactoring to a single-pass tree visitor; not urgent.

---

## Next work

### Immediate: merge PR #6

```bash
gh pr merge 6 --merge
git checkout master && git pull
```

Matches Slices 1–4b merge-commit pattern.

### After merge: four options

**1. Slice 4c — LCOM-HS (class-level cohesion; recommended next per roadmap).**
Deferred from Slice 4b per its Scope Decision #1. Needs method ↔ attribute-read graph extraction in the parse layer. Non-trivial; plan should flag empirical CFN/AST probe as an early task.

**2. Parser bug-fix mini-slice (B1 / B2 / B3).**
Tight scope, each bug has a clear fix path:
- B1: add `match_statement` + `case_clause` + `except_group` (see also B3) to `_STATEMENT_NODE_TYPES` and `_TS_TO_CFN_KIND`; update `src/savviety_instinct/core/cognitive_rules/python.yaml`; bump metric_versions for every metric whose output changes on match-using code.
- B2: disambiguate `qualified_name` for `@property`/`@setter` pairs in `_collect_functions` (e.g., `"Thing.name[getter]"` / `"Thing.name[setter]"`, or append line number).
- B3: covered by B1's parse-layer fix if done together.
When fixed, flip `xfail(strict=True)` → real assertion in `tests/test_parse_adversarial.py` (strict mode will auto-enforce this).

**3. Graph infrastructure detour.**
- Cross-file call resolution
- Module dependency graph
- Unlocks arch §3.x coupling metrics (afferent, efferent, instability, abstractness, D, Henry-Kafura)

**4. Temporal infrastructure detour.**
- pydriller or gix integration for git history
- Unlocks arch §5.x (change_frequency, bug_fix_density, author_count, stability_tier)

### Deferred housekeeping (not urgent)

- Fix Slice 4a `metric_version = 1.0.0` documented approximations (NPATH condition, comprehension, ternary, lambda attribution, context-blind stopwords). Coordinated parse-layer + metric-version bump — natural co-travel with option 2 above.
- Mutation-testing baseline: previously attempted via `mutmut` 3.x, shelved due to src-layout friction. Alternatives documented in the hardening plan's mutation appendix (`mutatest`, `cosmic-ray`, `mutmut 2.x`).
- `.claude.bak-*/` backup directories accumulate untracked on every session start. Sweep occasionally.

---

## Process reminders for the next session

1. **Start with `/whereami`** in the new session.
2. **Confirm scope with Gary before writing code** for a new slice — he expects this. HANDOFF.md's "Next work" section is my proposal; his decision overrides.
3. **Follow the most recent slice plan's style** (Slice 4b for feature slices; test-hardening plan for cross-cutting initiatives): file-structure table, scope-decisions section, per-task TDD steps with verbatim code, self-review, execution handoff.
4. **Ground-truth fixtures before metrics.** Add expected values to `metric_fixtures.py` or a new fixture file (module-level metrics live under `tests/fixtures/python/modules/`; adversarial parser cases live under `tests/fixtures/python/adversarial/`) BEFORE implementing.
5. **Empirical CFN inspection** when writing any metric that reads `ControlFlowNode` structure. REPL commands included in prior plan docs.
6. **Subagent-driven execution** has worked cleanly for 4 slices. Use `superpowers:subagent-driven-development` skill for feature slices. Cross-cutting initiatives (test hardening, bug sweeps) don't need it — run tasks inline.
7. **Merge-commit style** for slice and initiative PRs (matches Slices 1–4b). Don't squash.
8. **When a test surfaces a real bug mid-plan, pin it with `xfail(strict=True)` rather than expanding plan scope to fix it.** Log in the plan's "Bugs Surfaced" appendix for a follow-up slice. The strict-xfail pattern auto-fails when the bug is fixed, forcing marker removal.
9. **Feedback memory to honor:** raise locked-decision concerns, give opinion before decisions, one commit per logical change, default to "not in MVP."

---

## How to resume

1. Read this file.
2. Read `docs/01-locked-decisions.md` and `docs/04-architecture-spec.md` §2/§5/§15 if unfamiliar.
3. Read `docs/plans/2026-04-19-slice-4b-module-metrics.md` for the most recent executed feature-slice plan (template for feature slices) and `docs/plans/2026-04-20-test-hardening-algorithmic-rigor.md` for the most recent cross-cutting initiative.
4. Read `docs/testing.md` for the three-layer test strategy before adding any new tests.
5. Check PR #6 state. Merge if ready.
6. Confirm next work scope with Gary before coding (see §"Next work").
7. Start with `/whereami` in any new session.

---

## Contact / pointers

- Shared skills installed via `savviety-skills` — see `CLAUDE.md` in repo root.
- Per-developer overrides live in `CLAUDE.local.md` (gitignored).
- Per-machine session state lives in `.claude/SESSION.md` (gitignored).
- PRs: https://github.com/garyld1962/savviety-instinct/pulls
