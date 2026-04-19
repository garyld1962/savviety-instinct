# Instinct — Session Handoff

**Purpose:** enable a fresh Claude Code session (or a returning Gary) to resume without reconstructing context from git log + memory.

**Last updated:** 2026-04-19
**State at handoff:** Slices 1–3 merged to master. Slice 4a shipped as PR #4 (open, awaiting review/merge). Slice 4b not yet started.

---

## Read these first (in order)

All design docs live in `docs/`:

1. `docs/03-executive-summary.md` — what Instinct is and why
2. `docs/01-locked-decisions.md` — D1–D10, frozen
3. `docs/02-prd.md` — MVP requirements
4. `docs/04-architecture-spec.md` — module layout, schema, slice plan (§15)
5. `docs/05-metric-catalog.md` — metric formulas (reference)

Then:

6. `docs/plans/2026-04-19-slice-4a-function-metrics.md` — the most recent executed plan, useful as template
7. Prior plans under `docs/plans/` for Slices 1, 2, 3 — how things got here
8. `.claude/SESSION.md` (if present; per-machine, gitignored) — in-flight state

---

## Quick-start: "I just sat down, what do I do?"

1. `/whereami` — branch state, open PRs, last session context
2. Check https://github.com/garyld1962/savviety-instinct/pulls — is PR #4 still open?
3. If yes, review/merge it, then pick next-step from §"Next work" below
4. If no, refresh this doc from `git log` + check PR list for anything newer

---

## Project state

- **6 source modules populated** per arch §2 layout: `core/`, `storage/`, `config/`, `cli/`, `parse/`, `graph/`, `analyze/`. Reserved skeletons (`llm/`, `curate/`, `patterns/`, `suggest/`, `mcp/`, `report/`) are empty `__init__.py` stubs.
- **236 passing tests** (post-Slice-4a), 94% coverage, mypy strict clean on 27 source files.
- **PR cadence:** one PR per slice from arch §15. Merge-commit style (not squash). Branches live after merge — not deleted.
- **Python 3.12+**, `uv`-managed (no pip/poetry/pyenv). Typer CLI. Pydantic v2 config. SQLAlchemy 2 + Alembic for the (unwritten-to) SQLite schema.

### Slices shipped (commits on master)

| Slice | Scope | Merge commit |
|-------|-------|--------------|
| 1 | Bootstrap: `core/` types, `storage/` interfaces + schema migration, `config/`, `cli/` (version + init + R2 stubs), pre-commit hooks, NFR-1 no-network test | `ebd23a8` (PR #1) |
| 2 | `parse/` (Python via tree-sitter), `graph/` (intra-file call graph), `ast_hash` via blake3/xxhash, `AnalysisContext.call_graph` | `25b41a9` (PR #2) |
| — | CLAUDE.md scaffold standalone commit | `63efd7c` |
| 3 | Three metrics (`statement_count`, `cyclomatic`, `cognitive`), `ControlFlowNode`, `analyze/pipeline.py`, `instinct run <path>`, cognitive rules YAML | `c20e97c` (PR #3) |

### Slice 4a (current state — branch `slice-4a-function-metrics`, PR #4 open)

Three more function-level metrics: `max_nesting_depth`, `npath`, `identifier_quality` (heuristic). `FunctionDefNode.identifier_names` field added. 236 tests, 94% coverage. Awaiting Gary's review.

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

### Registry (smell: duplication)
`METRICS_REGISTRY` lives in `src/savviety_instinct/analyze/__init__.py`; pipeline.py has a separate `_METRICS` tuple. **Adding a new metric requires updating both.** Collapsing the two would remove this footgun — worth doing in a future small refactor.

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
- **Tests hard-code row counts encoding `len(METRICS_REGISTRY)`.** `test_cli_run.py`, `test_analyze_pipeline.py`, `tests/integration/test_slice3_pipeline.py`, `tests/integration/test_slice4a_metrics.py` all assume 60 rows (10 fns × 6 metrics). Slice 4b will change this — update expectations or parametrize.
- **Cognitive rules YAML must be complete.** Loader raises if any `ControlFlowNodeKind` has no rule. Adding a new kind requires updating every language's YAML.
- **Parse-layer helpers in `parse/python.py`** have grown substantial (~600 lines). `_collect_functions`, `_collect_control_flow`, `_count_statements`, `_collect_identifiers` all traverse the function body. Eventually worth refactoring to a single-pass tree visitor; not urgent.

---

## Next work

### Immediate: merge PR #4

```bash
gh pr merge 4 --merge
git checkout master && git pull
```

Matches Slices 1–3 merge-commit pattern.

### After merge: three options

**1. Slice 4b — module-level + class-level metrics (recommended next).**
- `trivial_delegation_ratio`, `median_function_length` (module-level — needs `ArtifactKind.MODULE` pipeline dispatch)
- `LCOM-HS` (class-level — needs method↔attribute-read graph extraction in parse layer; may justify splitting into Slice 4c if it's non-trivial)
- Registry duplication collapse (small refactor, natural fit here)

**2. Graph infrastructure detour.**
- Cross-file call resolution
- Module dependency graph
- Unlocks arch §3.x coupling metrics (afferent, efferent, instability, abstractness, D, Henry-Kafura)

**3. Temporal infrastructure detour.**
- pydriller or gix integration for git history
- Unlocks arch §5.x (change_frequency, bug_fix_density, author_count, stability_tier)

### Deferred housekeeping (not urgent)

- Fix Slice 4a `metric_version = 1.0.0` documented approximations (NPATH condition, comprehension, ternary, lambda attribution, context-blind stopwords). Coordinated parse-layer + metric-version bump.
- Delete `.claude.bak-20260419T094327Z/` backup directory (untracked, from session-start backup).
- Consider collapsing `_METRICS` in `analyze/pipeline.py` to import `METRICS_REGISTRY` from `analyze/__init__.py`.

---

## Process reminders for the next session

1. **Start with `/whereami`** in the new session.
2. **Confirm scope with Gary before writing code** for a new slice — he expects this. HANDOFF.md's "Next work" section is my proposal; his decision overrides.
3. **Follow the Slice 4a plan doc style** for future plan docs: file-structure table, scope-decisions section, per-task TDD steps with verbatim code, self-review, execution handoff.
4. **Ground-truth fixtures before metrics.** Add expected values to `metric_fixtures.py` (or a new fixture file if the new metrics are module/class-scoped) BEFORE implementing.
5. **Empirical CFN inspection** when writing any metric that reads `ControlFlowNode` structure. REPL commands included in prior plan docs.
6. **Subagent-driven execution** has worked cleanly for 3 slices. Use `superpowers:subagent-driven-development` skill for Slice 4b+.
7. **Merge-commit style** for slice PRs (matches Slices 1–3). Don't squash.
8. **Feedback memory to honor:** raise locked-decision concerns, give opinion before decisions, one commit per logical change, default to "not in MVP."

---

## How to resume

1. Read this file.
2. Read `docs/01-locked-decisions.md` and `docs/04-architecture-spec.md` §2/§5/§15 if unfamiliar.
3. Read `docs/plans/2026-04-19-slice-4a-function-metrics.md` for the most recent executed plan (template for future plans).
4. Check PR #4 state. Merge if ready.
5. Confirm next slice scope with Gary before coding.
6. Start with `/whereami` in any new session.

---

## Contact / pointers

- Shared skills installed via `savviety-skills` — see `CLAUDE.md` in repo root.
- Per-developer overrides live in `CLAUDE.local.md` (gitignored).
- Per-machine session state lives in `.claude/SESSION.md` (gitignored).
- PRs: https://github.com/garyld1962/savviety-instinct/pulls
