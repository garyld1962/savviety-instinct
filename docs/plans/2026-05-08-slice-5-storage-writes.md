# Slice 5 — Observation Store Writes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.
>
> **Gary's chosen flow:** `/plan` → `/execute-plan`. One commit per task. Branch `slice-5-storage-writes`, off master at `424c55e` (PR #7 merged).

**Goal:** Persist `instinct run` outputs to per-repo SQLite per D10. Establish the dormant-artifact shortcut (the substrate for the NFR-7 ≤15s re-run target) and the `repo_fingerprint` derivation that keeps the R2 Postgres-warehouse path cheap. After Slice 5, repeat runs are observable as accumulated history; before, every run was amnesiac.

**Architecture:** A new `SQLAlchemyObservationStore` (concrete `ObservationStore` Protocol from `storage/interfaces.py`) writes into the three core tables already defined by migration `001_initial_schema.py`: `runs`, `observation_artifacts`, `run_observations`. Alembic upgrades to head on store construction. The CLI's `run_cmd` opens a store at `<cwd>/.instinct/instinct.db`, wraps `analyze/pipeline.py` in a new persistence layer that decides per-artifact whether to recompute metrics or shortcut to a cheap `record_observation` call. `analyze/pipeline.py` itself is unchanged — the wrapper does the dispatch.

**Tech Stack:** Python 3.12+, SQLAlchemy 2 + Alembic (already wired), no new deps.

---

## Scope Decisions (locked)

1. **Three tables only:** `runs`, `observation_artifacts`, `run_observations`. **Out of scope:** `rankings`, `run_profiles`, `llm_verdicts`, `patterns`, `pattern_evidence`. The first two are Slice 6 (no ranking algorithm exists yet); the rest are R2/R3 reservations.
2. **Combined `metric_version` strategy.** The schema's `UNIQUE (ast_hash, language, metric_version)` predates the multi-metric reality (we have 9 metrics at varying individual versions). Compute a single `combined_metric_version` per run as `"mv_" + first 12 hex of sha256(sorted `<metric_id>:<version>` pairs joined by `|`)`. Documented in code; refactor to per-metric versioning is out of MVP scope.
3. **Stability tier: minimal placeholder.** Slice 5 records `volatile` on first insert and transitions to `settled` once `occurrence_count >= 2`. Full stability semantics (`dormant` after N runs unseen) are deferred — they need a "runs since last seen" calculation that's cheaper to add once we have more than two runs in fixture data.
4. **Dormant-artifact shortcut IS in scope** (it's why the slice exists). On re-run, an artifact that already exists in `observation_artifacts` for the current `combined_metric_version` skips metric recomputation entirely; we just insert a `run_observations` row and bump `last_seen_run_id` / `occurrence_count`.
5. **`context_hash` populated, partially.** D6's full composition (language, enclosing_signature, import_set, framework_indicators, caller/callee signatures) requires R2 work. Slice 5 stores a partial: `sha256(language|enclosing_class_or_empty|caller_count|callee_count)`. Forward-compat: extending the formula in R2 will invalidate stored values, which is acceptable per D6 (cache-key bumps are deliberate events).
6. **`repo_fingerprint` derivation order:** (a) SHA-256 of first-commit SHA via `git log --reverse --format=%H | head -1`; (b) SHA-256 of `git config --get remote.origin.url`; (c) synthetic `sha256(hostname + abspath)`. Source label written to `repo_fingerprint_source`. The directory used for git lookup is **cwd**, not the analyzed path — fingerprint identifies the repo, not the analyzed subtree.
7. **180-day TTL cleanup is OUT of scope.** Arch §8.4 says cleanup runs at the start of every `instinct run`; defer that to a follow-up. Slice 5 just writes; cleanup arrives when we have data old enough to need it (also gives us a chance to validate the index strategy on real fixture data).
8. **`instinct vacuum` is OUT of scope.** Reserved-stub already exists; not needed for Slice 5's tests.
9. **Read-side `ObservationQuery` Protocol stays unimplemented.** Slice 5 is write-only. Reports (Slice 6) and trend queries (Slice 9) drive the read implementation.
10. **Schema migration on store construction.** Every `SQLAlchemyObservationStore.__init__` calls `command.upgrade(alembic_cfg, "head")` against the database file. Idempotent — no-op if already at head. Tests against tmp DBs always start clean.
11. **SQLite tuning per arch §8.3:** `PRAGMA journal_mode = WAL`, `PRAGMA synchronous = NORMAL`. Set on connection creation.
12. **MODULE artifacts ARE persisted** alongside FUNCTION artifacts. Slice 4b's pipeline already emits them; storage just writes them through with `artifact_kind = 'module'`. No new computation.
13. **Pipeline integration via wrapper, not edit.** Add `analyze/persistence.py` that wraps `run_pipeline`. The pipeline itself stays a pure generator + summary (preserved Slice 3 contract; existing tests bypass storage). The CLI calls the wrapper; unit tests of metrics call the bare pipeline.
14. **stdout output unchanged.** `instinct run` still prints the Slice 3 tab-separated rows. Storage is a side effect on top. Report layer (Slice 6) replaces stdout.
15. **`config_hash`:** SHA-256 of the loaded Pydantic config's `.model_dump_json(sort_keys=False)` — deterministic given the model field order, which is stable across Python sessions.
16. **`tool_version`:** `savviety_instinct.__version__`.
17. **`branch` and `commit_sha`:** from `cwd` git via subprocess. Both nullable on schema; if not in a git repo, store NULL.
18. **No NetworkX changes.** Call graph still intra-file only (Slice 2 scope decision). The `caller_count` / `callee_count` for `context_hash` come from the existing `CallGraph` per file.
19. **Test stability: store paths are `tmp_path`-based.** Real `.instinct/instinct.db` only touched by integration tests under `tests/integration/`.
20. **Acceptance test for re-run: behaviour, not timing.** Performance tests live in Slice 10 per arch §10.5. Slice 5 verifies `occurrence_count` increments and that `observation_artifacts` row count is stable across runs of unchanged source.

---

## Resolved Questions

1. **Q: When CFNs change but identifiers don't, does `ast_hash` change?** A: Yes — tree-sitter's `str(node)` includes structure. Verified empirically in Slice 2.
2. **Q: Where does the engine come from in tests?** A: `SQLAlchemyObservationStore(db_path=tmp_path / "instinct.db")` per test; auto-upgraded to head on init.
3. **Q: How are partial-write failures handled?** A: One transaction per `begin_run` → `complete_run` window. If `complete_run` raises before commit, the run is marked `failed` (or, on hard exception, the `runs` row stays in `running` status — observable as orphan but acceptable; arch §9 doesn't mandate auto-recovery in MVP).
4. **Q: Does the dormant shortcut require parsing files?** A: Yes — we still need each function's `ast_hash`, which only the parser produces. The shortcut skips **metric computation**, not parsing. Cheap because metric loops on the CFN tree dominate per-function CPU.
5. **Q: Module artifacts and re-run dedup?** A: `_module_ast_hash` is derived from joined function ast_hashes (see `pipeline.py`). If a module's function set is unchanged structurally, the module ast_hash stays stable, so module artifacts dedupe naturally on re-run.

---

## File Structure

| Path | New/Modify | Purpose |
|------|------------|---------|
| `src/savviety_instinct/storage/fingerprint.py` | New | `derive_repo_fingerprint(cwd) -> tuple[str, RepoFingerprintSource]` |
| `src/savviety_instinct/storage/run_meta.py` | New | `compute_config_hash`, `compute_combined_metric_version`, `derive_git_commit_branch` |
| `src/savviety_instinct/storage/sqlite_store.py` | New | `SQLAlchemyObservationStore` concrete `ObservationStore` impl |
| `src/savviety_instinct/storage/__init__.py` | Modify | Re-export `SQLAlchemyObservationStore` and helpers |
| `src/savviety_instinct/analyze/persistence.py` | New | `run_pipeline_with_persistence(path, config, store)` wrapper |
| `src/savviety_instinct/analyze/__init__.py` | Modify | Re-export `run_pipeline_with_persistence` |
| `src/savviety_instinct/cli/app.py` | Modify | Wire the store into `run_cmd` |
| `tests/test_storage_fingerprint.py` | New | Three derivation cases (first-commit, origin-url, synthetic) |
| `tests/test_storage_run_meta.py` | New | Stable hashes, sensitivity to relevant changes |
| `tests/test_storage_sqlite_store.py` | New | Begin/complete run, upsert dedup, record_observation, stability_tier transition |
| `tests/test_analyze_persistence.py` | New | Wrapper logic with a fake store (verifies dormant shortcut without touching SQLite) |
| `tests/integration/test_first_run.py` | New | End-to-end: fresh repo → CLI run → verify DB rows |
| `tests/integration/test_re_run.py` | New | Two runs in sequence → verify dedup behaviour |

---

## Task Ordering

Each task commits independently. Each commit green.

- [ ] **Task 1 — Fingerprint + run-meta helpers.** Add `storage/fingerprint.py` and `storage/run_meta.py`. Three derivation cases for fingerprint (git-with-commits, no-origin git, non-git). Helpers for `config_hash`, `combined_metric_version`, `derive_git_commit_branch(cwd) -> tuple[str | None, str | None]`. Pure functions, no I/O beyond subprocess for git. Commit: `feat(storage): repo_fingerprint + run-meta helpers (Slice 5 task 1)`.
- [ ] **Task 2 — SQLAlchemyObservationStore skeleton.** Add `storage/sqlite_store.py` with `__init__(db_path)` opening SQLAlchemy engine, applying WAL/synchronous pragmas, and running `command.upgrade(alembic_cfg, "head")`. Implement `begin_run` and `complete_run` only. `upsert_artifact`, `record_observation`, `write_ranking`, `write_profile` raise `NotImplementedError` for now to preserve Protocol shape. Tests: tmp_path DB, schema is at head, `begin_run` returns int, `complete_run` updates status + completed_at. Commit: `feat(storage): SQLAlchemyObservationStore + run lifecycle (Slice 5 task 2)`.
- [ ] **Task 3 — Upsert dedup + record_observation.** Implement `upsert_artifact(artifact, metrics)` (INSERT or UPDATE returning artifact_id) and `record_observation(run_id, artifact_id, location)`. `metrics_json` serialized as `{metric_id: {value, version, confidence}}`. Stability tier transition from `volatile` to `settled` on `occurrence_count >= 2`. Tests: same artifact across runs gets one row, occurrence_count increments, stability tier transitions, `metrics_json` round-trips. Commit: `feat(storage): artifact upsert with dedup + stability tier (Slice 5 task 3)`.
- [ ] **Task 4 — Persistence wrapper with dormant shortcut.** Add `analyze/persistence.py:run_pipeline_with_persistence(path, config, store)`. Per artifact: parse → compute ast_hash → query store for existing artifact at `(ast_hash, language, combined_metric_version)`; if present, skip metric computation and call only `record_observation`; if absent, run metrics and call `upsert_artifact` then `record_observation`. Yields the same `(Artifact, MetricValue)` tuples as `run_pipeline` so CLI stdout is unaffected (yields metrics from cache for shortcut path). Tests: a fake `ObservationStore` records calls; assert that on second invocation with same artifacts, `upsert_artifact` is NOT called, but `record_observation` is. Commit: `feat(analyze): persistence wrapper with dormant shortcut (Slice 5 task 4)`.
- [ ] **Task 5 — CLI wiring + first-run integration test.** Modify `cli/app.py:run_cmd` to construct `SQLAlchemyObservationStore` from `cwd/.instinct/instinct.db` and call `run_pipeline_with_persistence`. Add `tests/integration/test_first_run.py` that scaffolds a tiny fixture, runs CLI, and asserts the DB has 1 run row and the expected artifact/observation rows. stdout output assertions copied from existing `tests/test_cli_run.py`. Commit: `feat(cli): wire observation store into instinct run (Slice 5 task 5)`.
- [ ] **Task 6 — Re-run integration test.** Add `tests/integration/test_re_run.py` that runs the CLI twice on the same fixture and asserts: 2 rows in `runs`; `observation_artifacts` row count unchanged between runs (dedup); each artifact's `occurrence_count = 2` and `last_seen_run_id` matches the second run; corresponding `run_observations` count doubles. Plus an instrumented assertion that on the second run, the persistence wrapper short-circuits (use a spy/counter on metric `compute` calls, not perf timing). Commit: `test(integration): re-run dormant shortcut behaviour (Slice 5 task 6)`.

---

## Acceptance

- All 6 tasks merged; test count grows by ~25–35 (rough est: 3 fingerprint + 3 run-meta + 6 store + 4 persistence + 4 first-run + 5 re-run + a few smoke).
- Coverage holds at ≥ 89%; storage/ moves from ~0% to ≥ 85% (currently `storage/migrations/env.py` and `001_initial_schema.py` show 0% — Slice 5 doesn't fix those by design; they execute only via `alembic upgrade`, not via test imports).
- Re-running `instinct run` on the test fixture produces no new `observation_artifacts` rows and increments `occurrence_count` to 2 on every artifact.
- mypy strict clean on all new modules.
- `instinct run` stdout output for the Slice 3+4 tests is byte-identical to master (no regression in existing CLI tests).

---

## Non-Goals

- No ranking, profile, or report generation (Slice 6).
- No 180-day TTL cleanup (follow-up).
- No `instinct vacuum`, `instinct trend`, `instinct explain` commands.
- No read-side query implementation (`ObservationQuery` Protocol stays unimplemented).
- No `dormant` stability tier transition (only `volatile` → `settled`).
- No `instinct sync` work — the warehouse path stays an R2 reservation.
- No performance benchmarking against NFR-6 / NFR-7 (Slice 10).
- No cross-file or temporal metric work.

---

## Risks

| Risk | Mitigation |
|------|------------|
| Alembic `command.upgrade()` from inside the library has historically been awkward (cwd assumptions, ini-file path lookup) | Construct `Config` programmatically with `set_main_option("script_location", ...)` and `set_main_option("sqlalchemy.url", ...)`. Test it against a tmp DB before wiring into production. |
| Schema's single `metric_version` column doesn't fit our 9-metric reality | Combined-version hash (Scope #2). Document the limitation; defer per-metric versioning to a future refactor. |
| Tests using monkeypatched `METRICS_REGISTRY` may break the persistence wrapper if the wrapper hashes the registered metrics for the combined version | Compute combined version eagerly at start of run (one snapshot), not per-artifact. Tests that monkeypatch get a stable hash for that test's metrics. |
| `git` not on PATH on a CI runner | `derive_repo_fingerprint` falls through to synthetic; documented as the design intent. |
| `model_dump_json` field-order stability across SQLAlchemy version bumps | Pin via test that round-trips a known config and asserts the hash. |
| Large repo first-run write volume | Slice 5 doesn't optimize for it; arch §8.3 batch-insert tuning is a follow-up if first-run wall-clock fights NFR-6 in Slice 10. |
| The dormant shortcut accidentally skips when it shouldn't (e.g. a metric was added) | Combined `metric_version` includes every metric's version; adding/removing a metric changes the combined hash, invalidating all prior artifacts at the previous version. New version becomes the dedup key going forward. Old rows linger but are inert. |

---

## Resolved (2026-05-08)

These were open at plan-writing; Gary signed off on the recommendations.

1. **Combined-version hash format: compact `mv_<sha12>`.** Aligns with D6 cache_key precedent (also a hash). Column-width predictability matters as metrics multiply. Debug ergonomics solvable later via a separate `metric_versions` lookup table.
2. **`stability_tier`: minimal (volatile / settled only).** Dormant tier isn't load-bearing for the rerun shortcut (gate is existence, not tier). No data to calibrate a threshold yet; add when the first consumer (Slice 6 reports) needs it.
3. **Alembic: auto-upgrade on `SQLAlchemyObservationStore` construction.** Right ergonomics for the MVP user (D3: solo maintainer). Cache the `Config` at module level so the cost amortizes across tests. `--no-migrate` escape hatch can be added later if needed.
