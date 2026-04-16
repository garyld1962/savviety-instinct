# Instinct — Session Handoff

**Purpose:** enable a fresh Claude Code session to resume without re-reading the prior conversation.

---

## Read these first (in order)

All design docs live in `docs/` (not repo root):

1. `docs/03-executive-summary.md` — what this is and why
2. `docs/01-locked-decisions.md` — D1–D10, frozen
3. `docs/02-prd.md` — MVP requirements
4. `docs/04-architecture-spec.md` — module layout, schema, slice plan (§15)
5. `docs/05-metric-catalog.md` — metric formulas (reference, not for memorization)

---

## Project state

- **No code written yet.** Docs only.
- **Git:** initialized. Two commits on `master`:
  - `734e6d7` — pre-Slice-1 doc cleanup (moved files into `docs/`, applied five schema/config fixes)
  - `fa81e09` — Option C storage model locked as D10
- **Working tree:** clean.

---

## Working agreement (from Gary, frozen)

- **`uv` only.** No `pip`, `poetry`, or `pyenv`.
- Decisions in `docs/01-locked-decisions.md` are **frozen**. If you think one is wrong, raise it explicitly — do not silently work around.
- Layer boundaries from arch spec §2 are **absolute**. `analyze/` and `curate/` never import each other. All DB access goes through `storage/`. `core/` is pure.
- Every PR maps to one slice from §15. **No combining slices.**
- Tests required per metric before that metric merges.
- When in doubt about scope, default to **"not in MVP."**

---

## What's already resolved (don't redo)

### Five items applied pre-Slice-1 (commit `734e6d7`)

1. **Doc paths.** All docs live in `docs/`. CLAUDE.md seed in arch §14 references `docs/02-prd.md` etc. — those paths are now correct.
2. **`context_hash` dedicated column.** `run_observations.context_hash TEXT NOT NULL` in the initial migration. Do **NOT** overload `enclosing_scope`. MVP computes and stores; no consumer until R2.
3. **Empty `patterns` + `pattern_evidence` tables** in the initial migration (see §4.1). Required for the forward-compat promise in §11 / §12. Minimal columns, FKs to existing MVP tables only.
4. **TTL enforcement.** Opportunistic cleanup at start of every `instinct run` (cheap indexed delete) + forced cleanup via `instinct vacuum`. Documented in arch §8.4.
5. **`assist_level: observe`** in the config model. Only `observe` is valid in MVP; any other value raises a config validation error (R4 hook).

### Storage model (commit `fa81e09`, D10 in locked decisions)

**Option C: SQLite canonical + reserved Postgres warehouse.**

- SQLite per-repo at `.instinct/instinct.db` is the **canonical** store. `instinct run` **never reads from the warehouse**.
- Postgres warehouse is reserved as a one-way derived view, populated by `instinct sync` (R2+).
- MVP schema includes `repo_fingerprint TEXT NOT NULL` on `runs` and `observation_artifacts` so warehouse aggregation can use `(repo_fingerprint, local_id)` composite keys without identity collisions.
- `repo_fingerprint` derivation: first-commit SHA → origin URL → synthetic `hostname+path` fallback. `repo_fingerprint_source` column on `runs` records which tier was used.
- `sync_allowed` config flag, default `false`; **hard-false for `scope: corporate`** (separate from `remote_apis_allowed` so pushing observations and calling remote LLMs can't accidentally unlock each other).
- `instinct sync` listed in arch §7 reserved commands (R2).

---

## Next work: Slice 1

**From arch spec §15:**

> Slice 1: `core/` types + `storage/` minimal schema + migrations + `cli/ version` + `instinct init`. Proves tooling and layering.

### Concrete scope

- `pyproject.toml` as single source of truth; `uv`-managed deps.
- `.python-version` pinned to 3.12+.
- Package layout per arch §2: `src/savviety_instinct/{core,storage,parse,graph,analyze,report,config,cli,llm,curate,patterns,suggest,mcp}/` — reserved modules empty but present.
- `core/types.py` with `Artifact`, `MetricValue`, `Metric` Protocol, `Confidence` enum, `AnalysisContext` (see arch §5.1).
- `storage/interfaces.py` with `ObservationStore` and `ObservationQuery` Protocols (arch §5.2).
- **Alembic migration — initial schema from arch §4.1, including:**
  - `runs` with `repo_fingerprint` + `repo_fingerprint_source`
  - `observation_artifacts` with `repo_fingerprint`
  - `run_observations` with `context_hash NOT NULL`
  - `rankings`, `run_profiles`
  - `llm_verdicts` (empty, R2)
  - `patterns`, `pattern_evidence` (empty, R3)
  - All indexes shown in §4.1
- `cli/` built on Typer:
  - `instinct version` — prints tool + metric versions
  - `instinct init` — scaffolds `.instinct/config.yaml` with required `scope` field and the full optional block (`sync_allowed`, `assist_level`, etc.); adds `.instinct/instinct.db` and `.instinct/reports/` to `.gitignore`
- `tests/` with pytest + pytest-cov; dev/test groups per arch §3.1.
- Pre-commit hooks: `ruff check`, `ruff format`, `mypy` on `core/` + `storage/`.
- Repo `CLAUDE.md` at root — copy from arch §14 seed (paths already reference `docs/`).

### Non-goals for Slice 1

No parsing, no metrics, no reports, no git integration, no non-`core`/`storage` functionality. That's Slice 2+.

---

## Gotchas

- **Docs are in `docs/`, not repo root.** `ls` at root shows only `.git/`, `docs/`, `HANDOFF.md`.
- **`context_hash`** has a dedicated column. Don't overload `enclosing_scope`.
- **`patterns` / `pattern_evidence`** tables must exist in the initial migration even though they're empty in MVP.
- **`repo_fingerprint`** has three derivation tiers; record which one was used in `repo_fingerprint_source`.
- **`sync_allowed`** is separate from `remote_apis_allowed`. Both default to false. Corporate scope forces both to false.
- **Config validation:** missing `scope` is an error (FR-25, D8). `assist_level != observe` in MVP is an error.
- **No network calls** in default config — there's a test for this (NFR-1, AC-7).
- **Reserved CLI commands** (`sync`, `curate`, `suggest`, `apply`, `serve`) should return "not available in this release" rather than a crash or a 404.

---

## Open implementation questions (not blockers)

Expected to resolve during Slice 1–2:

- `pydriller` vs `gix` for git history → deferred to Slice 4.
- `blake3` vs `xxhash` → evaluate during Slice 1; fall back to `xxhash` if `blake3` arm64 bindings are flaky.
- HTML report CSS approach → Slice 6.
- Default suppression patterns per language → validate against Baker Street (C#), Resolve (TS), BuildFlow (TS).

---

## How to resume

1. Read this file, then `docs/01-locked-decisions.md` and `docs/04-architecture-spec.md` §2, §4, §5, §15.
2. Confirm Slice 1 scope with Gary before writing code (he'll expect this).
3. Start with `pyproject.toml` + package skeleton + Alembic init. Commit each sub-step individually; one PR per slice.
