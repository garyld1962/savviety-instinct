# Instinct — Architecture and Design Specification

**Product:** Instinct (`savviety-instinct`)
**Status:** MVP (Release 1) architecture with forward-compatible hooks for R2–R5
**Audience:** implementation — Claude Code CLI and any human collaborators
**Companion documents:** `01-locked-decisions.md`, `02-prd.md`, `03-executive-summary.md`, `05-metric-catalog.md`

---

## 1. Scope of This Document

This document specifies *how* the MVP is built. What it builds and why are specified in the PRD. Metric formulas are specified in the catalog.

Where this document references forward-looking releases (R2–R5), those references exist only to explain why MVP-era interfaces and schemas are shaped the way they are. Nothing in R2–R5 is required for MVP correctness.

## 2. Top-Level Architecture

Single Python package, installed once via `uv`, with multiple CLI subcommands exposing distinct internal layers.

```
src/savviety_instinct/
  core/          # domain types; pure, no I/O
  storage/       # the ONLY module that talks to SQLite
  parse/         # tree-sitter parsing and AST normalization
  graph/         # call graph and module dependency graph construction
  analyze/       # metric computation; reads source, writes observations
  report/        # JSON, terminal, HTML rendering
  config/        # per-repo config loading and validation
  cli/           # Typer-based, thin; parses args, dispatches to layers

  # reserved skeletons (empty in MVP, contracts defined):
  llm/           # Release 2: LLM backend abstraction
  curate/        # Release 3: curator tasks
  patterns/      # Release 3: pattern store
  suggest/       # Release 4: suggestion generation
  mcp/           # Release 5: MCP server
```

**Layering rule:** `analyze/` and `curate/` never import each other. They communicate only through `storage/`. `storage/` is the single writer to the observation database.

**Import hierarchy (bottom is most dependent):**

```
core
 ├── config
 ├── storage
 │   └── parse
 │       └── graph
 │           └── analyze
 │               └── report
 │                   └── cli
```

Tests are layered mirror: each module has its own unit tests; integration tests live in `tests/integration/` and cross layers.

## 3. Tooling

### 3.1 `uv` as the only Python workflow tool

- Python 3.12+, version pinned in `.python-version`, auto-fetched by `uv`.
- `pyproject.toml` is the single source of truth.
- `uv sync` bootstraps dependencies and the virtualenv.
- `uv run instinct ...` executes the CLI.
- `uv tool install .` installs globally for daily use.
- Dev dependencies in `[dependency-groups]`: `dev` (ruff, mypy), `test` (pytest, pytest-cov), `llm` (MLX, optional, R2+).
- `uv lock` pinned for reproducible installs; lockfile committed.

### 3.2 Quality tooling

- **Ruff** for lint and format (replaces black, isort, flake8).
- **Mypy** in strict mode on `core/`, `storage/`, and contract surfaces. Relaxed on `parse/` where tree-sitter typing is approximate.
- **Pytest** with `pytest-cov`; coverage floor TBD but aim ≥ 80% on `core/` and `analyze/`.
- **Pre-commit hooks** for ruff and mypy. Keep the set minimal.

### 3.3 Dependencies

MVP dependencies, expected:

- `tree-sitter` + per-language grammars (rust, c-sharp, typescript, python)
- `networkx` — graph algorithms (call graph, dependency graph, connected components for LCOM-HS)
- `pydriller` OR `gix` via bindings — git history access (evaluate; pydriller is simpler, gix is faster)
- `sqlalchemy` + `alembic` — DB access and migrations
- `typer` — CLI
- `rich` — terminal output
- `jinja2` — HTML report rendering
- `pydantic` — config validation
- `xxhash` or `blake3` — fast hashing for artifact keys

Avoid until needed: Pandas (use raw Python/dict statistics), Celery/Dramatiq (MVP is synchronous), FastAPI (MCP is R5).

## 4. Data Model

### 4.1 Observation store schema (MVP)

SQLite, one database per project at `.instinct/instinct.db`, is the **canonical** store for all observations, rankings, and profiles. Alembic-managed migrations.

Per D10, a central Postgres warehouse is reserved as a one-way derived aggregation layer (`instinct sync`, R2+) to enable cross-project queries. `instinct run` **never reads from the warehouse**; the warehouse is populated by explicit push and is always reconstructable from the per-repo SQLite files. To keep the R2 warehouse path cheap, MVP tables include a `repo_fingerprint` column so observations from different repos can be merged into a single Postgres schema using `(repo_fingerprint, local_id)` composite keys without identity collisions.

`repo_fingerprint` is derived at run start: the SHA-256 of the repo's first-commit SHA where available, falling back to a hash of the origin URL, and finally to a machine-local synthetic fingerprint (`hostname + absolute path`) for non-git workspaces. Fingerprint stability across clones of the same repo is the design goal; fallbacks are labelled so the warehouse can reject or de-duplicate as needed.

```sql
-- Run-level metadata
CREATE TABLE runs (
    id                      INTEGER PRIMARY KEY,
    repo_fingerprint        TEXT NOT NULL,      -- D10: stable repo identity for
                                                -- warehouse aggregation
    repo_fingerprint_source TEXT NOT NULL,      -- 'first_commit' | 'origin_url' | 'synthetic'
    started_at              TIMESTAMP NOT NULL,
    completed_at            TIMESTAMP,
    commit_sha              TEXT,
    branch                  TEXT,
    config_hash             TEXT NOT NULL,
    tool_version            TEXT NOT NULL,
    metric_version          TEXT NOT NULL,
    status                  TEXT NOT NULL,      -- 'running' | 'completed' | 'failed'
    notes                   TEXT
);

CREATE INDEX idx_runs_fingerprint ON runs (repo_fingerprint);

-- Unique code artifacts, deduplicated by ast_hash
CREATE TABLE observation_artifacts (
    id                  INTEGER PRIMARY KEY,
    repo_fingerprint    TEXT NOT NULL,   -- D10: repo identity for warehouse aggregation
    ast_hash            TEXT NOT NULL,
    language            TEXT NOT NULL,
    artifact_kind       TEXT NOT NULL,   -- 'function' | 'class' | 'module'
    ast_serialized      BLOB,            -- compressed; may be pruned for old dormant artifacts
    metrics_json        TEXT NOT NULL,
    metric_version      TEXT NOT NULL,
    first_seen_run_id   INTEGER NOT NULL REFERENCES runs(id),
    last_seen_run_id    INTEGER NOT NULL REFERENCES runs(id),
    occurrence_count    INTEGER NOT NULL DEFAULT 1,
    stability_tier      TEXT NOT NULL,   -- 'volatile' | 'settled' | 'dormant'
    UNIQUE (ast_hash, language, metric_version)
);

CREATE INDEX idx_artifacts_ast_hash ON observation_artifacts (ast_hash);
CREATE INDEX idx_artifacts_stability ON observation_artifacts (stability_tier);
CREATE INDEX idx_artifacts_fingerprint ON observation_artifacts (repo_fingerprint);

-- Per-run sightings; this is what the TTL applies to
CREATE TABLE run_observations (
    id              INTEGER PRIMARY KEY,
    run_id          INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    artifact_id     INTEGER NOT NULL REFERENCES observation_artifacts(id),
    file_path       TEXT NOT NULL,
    line_start      INTEGER NOT NULL,
    line_end        INTEGER NOT NULL,
    symbol_name     TEXT NOT NULL,
    enclosing_scope TEXT,           -- class name or module name
    context_hash    TEXT NOT NULL   -- R2 forward-compat per D6: hash of
                                    -- (language, enclosing signature, import set,
                                    --  framework indicators, caller/callee signatures).
                                    -- MVP computes and stores; no consumer yet.
);

CREATE INDEX idx_run_obs_run ON run_observations (run_id);
CREATE INDEX idx_run_obs_artifact ON run_observations (artifact_id);
CREATE INDEX idx_run_obs_file ON run_observations (file_path);
CREATE INDEX idx_run_obs_context ON run_observations (context_hash);

-- Composite rankings per run
CREATE TABLE rankings (
    id                  INTEGER PRIMARY KEY,
    run_id              INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    run_observation_id  INTEGER NOT NULL REFERENCES run_observations(id) ON DELETE CASCADE,
    attention_priority  REAL NOT NULL,
    rank               INTEGER NOT NULL,
    contributing_metrics_json TEXT NOT NULL  -- which metrics fired, at which percentiles
);

CREATE INDEX idx_rankings_run ON rankings (run_id, rank);

-- Profile axes per run (aggregate)
CREATE TABLE run_profiles (
    id          INTEGER PRIMARY KEY,
    run_id      INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    axis        TEXT NOT NULL,
    p50         REAL,
    p90         REAL,
    p95         REAL,
    p99         REAL,
    status      TEXT NOT NULL,  -- 'normal' | 'watch' | 'elevated'
    sample_size INTEGER NOT NULL
);

-- Reserved for R2+
CREATE TABLE llm_verdicts (
    id              INTEGER PRIMARY KEY,
    artifact_id     INTEGER NOT NULL REFERENCES observation_artifacts(id),
    context_hash    TEXT NOT NULL,
    model_id        TEXT NOT NULL,
    prompt_hash     TEXT NOT NULL,
    stage           TEXT NOT NULL,  -- 'triage' | 'deep_read'
    verdict         TEXT NOT NULL,
    category        TEXT,
    reasoning       TEXT,
    created_at      TIMESTAMP NOT NULL,
    UNIQUE (artifact_id, context_hash, model_id, prompt_hash)
);

-- Reserved for R3+ (empty in MVP; defined so the initial migration
-- preserves the forward-compat promise from §11 and §12).
CREATE TABLE patterns (
    id                  INTEGER PRIMARY KEY,
    pattern_id          TEXT NOT NULL UNIQUE,   -- canonical ID from YAML file
    scope               TEXT NOT NULL,          -- 'project' | 'personal' | 'global'
    file_path           TEXT NOT NULL,          -- path to canonical YAML (D4)
    structural_sig      TEXT,
    lifecycle_state     TEXT NOT NULL DEFAULT 'proposed',
    created_at          TIMESTAMP NOT NULL,
    updated_at          TIMESTAMP NOT NULL
);

CREATE TABLE pattern_evidence (
    id                  INTEGER PRIMARY KEY,
    pattern_id          INTEGER NOT NULL REFERENCES patterns(id),
    artifact_id         INTEGER NOT NULL REFERENCES observation_artifacts(id),
    run_id              INTEGER REFERENCES runs(id),
    relation            TEXT NOT NULL,          -- 'example' | 'counter_example' | 'deviation'
    created_at          TIMESTAMP NOT NULL
);

CREATE INDEX idx_pattern_evidence_pattern ON pattern_evidence (pattern_id);
CREATE INDEX idx_pattern_evidence_artifact ON pattern_evidence (artifact_id);
```

### 4.2 Artifact identity (D6)

**MVP cache key (for artifact deduplication):**

```
artifact_key = hash(ast_hash, language, metric_version)
```

**Reserved R2+ cache key (for LLM verdicts):**

```
verdict_key = hash(
    artifact_ast_hash,
    context_hash,      # includes enclosing signature, import set, framework markers
    model_id,
    prompt_hash,
    metric_version
)
```

`context_hash` is defined in `01-locked-decisions.md` (D6). MVP computes and stores `context_hash` on every `run_observations` row (dedicated column, see §4.1) even though no LLM consumes it yet. This guarantees R2 can key verdicts correctly without a schema migration.

### 4.3 Provenance invariant

Every row in the database traces back to specific inputs. When a metric value changes in a later run, it's always possible to answer "did the code change, did the metric formula change, or did the analysis pipeline change?" by consulting `metric_version`, `tool_version`, and the artifact's `ast_hash`.

## 5. Module Contracts

### 5.1 `core/`

Pure domain types. Must not import from any other internal module.

```python
# core/types.py
@dataclass(frozen=True)
class Artifact:
    ast_hash: str
    language: Language
    kind: ArtifactKind  # function | class | module
    name: str
    enclosing_scope: str | None
    source_range: SourceRange

@dataclass(frozen=True)
class MetricValue:
    metric_id: str
    value: float | int | str
    metric_version: str
    confidence: Confidence  # high | medium | low
    notes: str | None = None

class Metric(Protocol):
    id: str
    version: str
    applies_to: set[ArtifactKind]
    required_inputs: set[InputKind]

    def compute(self, artifact: Artifact, context: AnalysisContext) -> MetricValue: ...
```

### 5.2 `storage/`

Repository pattern interfaces. Only module that imports SQLAlchemy.

```python
# storage/interfaces.py
class ObservationStore(Protocol):
    def begin_run(self, meta: RunMeta) -> RunId: ...
    def complete_run(self, run_id: RunId, status: RunStatus) -> None: ...
    def upsert_artifact(self, artifact: Artifact, metrics: list[MetricValue]) -> ArtifactId: ...
    def record_observation(self, run_id: RunId, artifact_id: ArtifactId, location: FileLocation) -> None: ...
    def write_ranking(self, run_id: RunId, ranking: Ranking) -> None: ...
    def write_profile(self, run_id: RunId, profile: Profile) -> None: ...

class ObservationQuery(Protocol):
    def get_run(self, run_id: RunId) -> Run: ...
    def get_rankings(self, run_id: RunId, limit: int) -> list[RankedObservation]: ...
    def get_profile(self, run_id: RunId) -> Profile: ...
    def get_trend(self, window_days: int) -> Trend: ...
    def get_artifact_history(self, ast_hash: str) -> list[Observation]: ...
```

### 5.3 `analyze/`

Orchestrates parsing, graph construction, metric computation, ranking, profile.

```python
# analyze/pipeline.py
class AnalysisPipeline:
    def __init__(self, parser: Parser, graph_builder: GraphBuilder,
                 metrics: list[Metric], store: ObservationStore): ...

    def run(self, repo: Repo, config: InstinctConfig) -> RunId: ...
```

Pipeline stages, executed in order:

1. **Discovery** — enumerate source files honoring suppression patterns.
2. **Parsing** — parse each file concurrently to AST.
3. **Graph construction** — build call graph and module dependency graph.
4. **Artifact extraction** — produce `Artifact` objects (functions, classes, modules).
5. **Metric computation** — compute all applicable metrics per artifact.
6. **Storage** — upsert artifacts, record observations.
7. **Ranking** — compute composite scores and percentiles.
8. **Profile** — compute codebase-level axis values.
9. **Report generation** — hand off to `report/`.

### 5.4 `report/`

Consumes `ObservationQuery` only. Does not compute metrics.

```python
# report/rendering.py
class Reporter(Protocol):
    def render(self, run_id: RunId, query: ObservationQuery) -> Report: ...

class JsonReporter(Reporter): ...
class TerminalReporter(Reporter): ...
class HtmlReporter(Reporter): ...
```

HTML rendering via Jinja2 templates, output a single self-contained HTML file with inlined CSS and minimal JS for filtering/sorting.

### 5.5 `parse/` and `graph/`

- `parse/` wraps tree-sitter. Produces normalized ASTs; each language has a `LanguageAdapter` that maps language-specific AST nodes to domain-level node types (`ControlFlowNode`, `FunctionDefNode`, etc.).
- `graph/` consumes normalized ASTs to build call graphs and module dependency graphs using `networkx`.

Both produce data used by many metrics; each is computed once per run and passed via `AnalysisContext` to metric implementations.

### 5.6 `config/`

Pydantic-validated config loading from `.instinct/config.yaml`. Emits clear errors on missing `scope` (FR-25). Provides `instinct init` scaffolding.

## 6. Configuration

`.instinct/config.yaml` — single config file per repo.

```yaml
# Required
scope: personal  # personal | corporate | open-source

# Optional (defaults shown)
remote_apis_allowed: false
include_in_cross_project: false
sync_allowed: false        # D10: opt-in push to Postgres warehouse via `instinct sync` (R2+).
                           # Hard-false when `scope: corporate`; any other value is a
                           # config validation error for corporate repos.
llm_backend: disabled      # MVP: always disabled; R2+ values: local | ollama | anthropic
assist_level: observe      # MVP: only 'observe' is valid. R4 values: suggest | patch_assist | apply.
                           # Any other value in MVP raises a config validation error.

# Languages
languages:
  # auto-detected; override here if needed
  include: [rust, csharp, typescript, python]
  exclude: []

# Suppression
suppress:
  paths:
    - "**/node_modules/**"
    - "**/target/**"
    - "**/dist/**"
    - "**/build/**"
    - "**/.venv/**"
    - "**/.next/**"
    - "**/migrations/**"
    - "**/*.generated.*"
  patterns:  # content-based
    - marker: "// <auto-generated>"
    - marker: "@generated"
  max_file_size_mb: 1

# Metric thresholds (optional; defaults from catalog)
thresholds:
  cognitive_complexity:
    healthy: 15
    review: 25
  # ... etc

# Retention
retention:
  run_observations_days: 180

# Performance
performance:
  max_concurrency: auto  # or integer
```

Config is hashed into `runs.config_hash` so differing configs across runs don't silently produce incomparable data.

## 7. CLI Surface (MVP)

```
instinct init                 # scaffold .instinct/config.yaml and .gitignore entries
instinct run                  # perform analysis; write to observation store
instinct report [RUN_ID]      # render latest or specified run as terminal + paths to JSON/HTML
instinct explain TARGET       # detailed view of one file:function across history
instinct trend [AXIS]         # show trend for a profile axis or metric over time
instinct vacuum               # force retention cleanup + compact DB
instinct rebuild-db           # rebuild DB from preserved artifact data on corruption
instinct version              # print tool and metric versions
```

Reserved for later releases (not implemented in MVP; commands return "not available in this release"):

```
instinct sync                 # R2 — one-way push of observations to Postgres warehouse (D10)
instinct curate               # R3
instinct suggest              # R4
instinct apply                # R4
instinct serve                # R5 (MCP)
```

## 8. Concurrency and Performance

### 8.1 Parallelism strategy

File-level parallelism via `concurrent.futures.ProcessPoolExecutor` for CPU-bound metric computation. Tree-sitter and networkx are not thread-safe in all cases; process isolation is safer. Default concurrency = `cpu_count() - 1`.

### 8.2 Dormant artifact shortcut

Artifacts classified as `dormant` (per metric catalog definition) skip full re-analysis on subsequent runs:

1. Compute `ast_hash` only.
2. If `(ast_hash, language, metric_version)` exists in `observation_artifacts`, insert `run_observations` row and update `last_seen_run_id` / `occurrence_count`. Do NOT recompute metrics.
3. Otherwise, treat as new and proceed to full metric computation.

This is the primary performance optimization enabling the NFR-7 (≤15s re-run) target on mature codebases.

### 8.3 SQLite tuning

- `PRAGMA journal_mode = WAL` for concurrent reads during writes.
- `PRAGMA synchronous = NORMAL` for write performance (acceptable durability tradeoff; lost data is at most the last run, which can be re-executed).
- Batch inserts within a run in single transactions per table.

### 8.4 Retention cleanup

The 180-day TTL on `run_observations` (D7, FR-15) is enforced in two places:

1. **Opportunistic cleanup** at the start of every `instinct run`: a single cheap query deletes any `run_observations` older than the retention window, plus orphaned `observation_artifacts` no longer referenced by any surviving `run_observations` or `pattern_evidence` row. This is the normal path — no user action required.
2. **Forced cleanup** via `instinct vacuum`: runs the same deletion and then issues SQLite `VACUUM` to reclaim disk space. Intended for explicit maintenance, not daily use.

Opportunistic cleanup runs inside a single short transaction before analysis starts so it never extends the wall-clock time on the hot path meaningfully; the delete is indexed on `run_id`/`started_at`. If the cleanup fails for any reason it is logged as a warning and the run continues — stale rows do not block analysis.

## 9. Graceful Degradation

Per NFR-20 through NFR-22, metrics indicate confidence and degrade rather than fabricate:

| Condition | Affected metrics | Behavior |
|---|---|---|
| No git history | change_frequency, bug_fix_density, author_count, stability_tier | Metric value = `unavailable`; `confidence = low`; reports show "—" |
| Ambiguous call graph | chain_depth_to_effect, henry_kafura, module_locality | `confidence = medium`; visually de-emphasized in reports |
| Partial type information (TS, Python dynamic) | lcom_hs, abstractness for classes | `confidence = medium`; note in tooltip |
| File too large | All metrics | File skipped; listed in report summary |
| Parse error | All metrics | File skipped; error logged; summary count |
| Unsupported construct within a parsed file | Language-specific metrics | Artifact skipped; note; summary count |

Every `MetricValue` carries a `confidence` enum (`high | medium | low`). Ranking uses confidence as a dampener: `attention_priority` is multiplied by `confidence_factor` (1.0 / 0.75 / 0.5).

## 10. Testing Strategy

### 10.1 Unit tests per metric

Hand-crafted AST fixtures with known correct values. Each metric in the catalog has at minimum:
- Happy path (straightforward example)
- Edge case identified in "Pitfalls"
- Language-specific variants where applicable

### 10.2 Reference corpus (`tests/corpus/`)

Three categories of fixture repos, per PRD §9:

- **Known-problematic fixtures** with intentional cognitive opacity, ravioli, and coupling issues. Assertion: these rank in top 10% of their fixture repo.
- **Known-good fixtures** with high metric counts that are legitimately fine. Assertion: reports produce explanatory context for these.
- **Parallel fixtures** — same complexity problem in Rust, C#, TypeScript, Python. Assertion: ranking parity within 1 standard deviation.

### 10.3 Snapshot tests

Full-pipeline runs on fixture repos produce JSON reports compared byte-for-byte against golden files. Changes require explicit golden-file updates during review.

### 10.4 Integration tests

- `tests/integration/test_first_run.py` — end-to-end first run on a small fixture repo
- `tests/integration/test_re_run.py` — two runs in sequence, verifying dormant-artifact shortcut and trend generation
- `tests/integration/test_scope_isolation.py` — confirms `scope: corporate` writes nothing outside repo

### 10.5 Performance tests

- `tests/perf/test_runtime.py` — benchmarks against NFR-6 and NFR-7 on Baker Street, Resolve, Python reference repos.
- Run in CI with warning thresholds, not hard failures, since CI hardware is inconsistent.

### 10.6 Property tests (selective)

Hypothesis-based tests for metric determinism: randomly generated AST variations should produce identical metric values across repeated invocations. Not exhaustive; targeted at metrics most prone to non-determinism.

## 11. Acceptance Criteria Per Phase

### MVP (Release 1)

Mapped to PRD §5 and §6:

- [ ] **AC-1:** Workflow W1 (first analysis) completes within NFR-6 on Baker Street, Resolve, and Python reference repo.
- [ ] **AC-2:** Workflow W4 (re-run) completes within NFR-7 after first run establishes dormant artifacts.
- [ ] **AC-3:** Top-10 relevance target (≥ 7 of 10) met on three real repos, self-assessed.
- [ ] **AC-4:** Workflow W3 (`instinct explain`) returns within 2 seconds and explains every flagged metric.
- [ ] **AC-5:** Reproducibility target: 10 consecutive runs on a fixture repo produce byte-identical JSON reports (modulo timestamps).
- [ ] **AC-6:** `scope: corporate` test: manual audit confirms no data written outside repo during a corporate-scoped run.
- [ ] **AC-7:** Default-mode network isolation: integration test confirms zero outbound sockets opened during a default-config run.
- [ ] **AC-8:** HTML report is a single self-contained file that renders in an offline browser.
- [ ] **AC-9:** Install-to-first-report on a fresh machine with `uv` installed: ≤ 5 minutes.
- [ ] **AC-10:** Graceful degradation: running on a non-git directory produces a valid report with temporal metrics marked unavailable, not zero.
- [ ] **AC-11:** Reference corpus assertions pass: problematic fixtures rank high, good fixtures don't dominate, parallel fixtures rank consistently.
- [ ] **AC-12:** Missing or invalid `scope` in config produces a clear error with remediation (not a silent default).

### R2 acceptance (for forward-compatibility checks only, not MVP work)

- Schema reserves `llm_verdicts` table (implemented in MVP, unused).
- `context_hash` computed and stored for every observation (implemented in MVP, no consumer yet).
- `llm/` skeleton exists with Protocol interfaces.

### R3 acceptance (for forward-compatibility checks only)

- Patterns directory shape (`.instinct/patterns/`) is reserved; `instinct` does not complain if files exist there.
- Observation schema supports `pattern_evidence` foreign keys via reserved `patterns/` skeleton.

## 12. Release 2–5 Forward Hooks

This section exists so MVP implementation doesn't paint itself into corners. Each hook is a schema element or interface that MVP implements or reserves even though nothing in MVP uses it.

**R2 hooks:**
- `llm_verdicts` table exists; no writes in MVP.
- `context_hash` stored in the dedicated `run_observations.context_hash` column (see §4.1). Computed and written on every observation; no MVP consumer.
- `llm/` module has Protocol definition for `LLMBackend`; no implementations.
- `repo_fingerprint` populated on every `runs` and `observation_artifacts` row (D10). Enables `instinct sync` in R2 to merge observations across repos into a Postgres warehouse without identity collisions.
- `sync_allowed` config flag exists; MVP validates it but never consumes it. Hard-false for `scope: corporate`.

**R3 hooks:**
- Reserved path `.instinct/patterns/` — not created by MVP, but not touched either.
- `patterns` and `pattern_evidence` tables defined in initial migration as empty (see §4.1).
- Curator task interface (`curate/tasks.py`) has Protocol defined; no implementations.

**R4 hooks:**
- `suggestion_outcomes` table defined; no writes in MVP.
- Assist level configuration field in config (`assist_level: observe` only valid value in MVP).

**R5 hooks:**
- MCP surface (`mcp/`) left empty but reserved.
- HTTP/MCP-compatible query interface design matches `ObservationQuery` Protocol.

## 13. Deployment and Distribution

### 13.1 MVP distribution

- `uv tool install git+https://github.com/savviety/savviety-instinct` (primary)
- `uv tool install .` from a local clone (development)
- No PyPI publication in MVP phase; revisit at R2.

### 13.2 Multi-machine context

Instinct runs on any developer workstation. For Gary's setup:

- **Sherlock** (primary development) — first target for bringup and daily use on Baker Street and Resolve.
- **Irene** (personal AI workstation) — runs the curator agent in R3+. No curator in MVP.
- **Lestrade** (laptop) — same daily-use target as Sherlock.
- **Mycroft** (server, 36TB ZFS) — candidate Postgres host when multi-project DB arrives in R2+; not in MVP.

The MVP works identically on all of these with no special configuration.

### 13.3 Database lifecycle

- `.instinct/instinct.db` lives per-repo.
- Gitignored by default (`instinct init` adds entries to `.gitignore`).
- Backups are the user's responsibility in MVP; `instinct export` / `instinct import` commands reserved but not implemented in MVP.

## 14. CLAUDE.md Seed

The following seeds the repo's `CLAUDE.md`:

````markdown
# CLAUDE.md — Instinct

## Project overview

Instinct measures code complexity and comprehensibility across multiple axes, accumulates
observations over time, and produces ranked investigation targets plus a multi-axis profile.

Current scope: Release 1 (MVP) — see `docs/02-prd.md`.
Architecture: `docs/04-architecture-spec.md`.
Metrics reference: `docs/05-metric-catalog.md`.

## Tooling

- Python 3.12+, managed by **`uv`**. No `pip`, no `poetry`, no `pyenv`.
- `uv sync` to install.
- `uv run instinct ...` to run the CLI.
- `uv run pytest` for tests.
- `uv run ruff check` and `uv run ruff format`.
- `uv run mypy src/savviety_instinct/core src/savviety_instinct/storage`
- Add deps with `uv add`; dev deps with `uv add --group dev`.

## Architecture rules (enforce in review)

1. **Layer boundaries are absolute.**
   - `analyze/` and `curate/` MUST NOT import each other.
   - All DB access goes through `storage/`. No SQL outside that module.
   - `core/` is pure — no I/O, no DB, no network.
2. **Metrics are pluggable via the `Metric` Protocol.**
3. **No outbound network calls in MVP.** A test enforces this.
4. **Schema changes via Alembic migrations.**
5. **Config requires explicit `scope`.** No defaults.

## Working style

- Decisions already locked live in `docs/01-locked-decisions.md`. Read them before proposing
  architectural changes.
- Reference corpus in `tests/corpus/` is ground truth for regression testing.
- Snapshot tests exist. If a metric change is intentional, update snapshots explicitly.
- Tests required per metric before that metric's PR can merge.

## MVP boundary reminders

Not in MVP:
- LLM features of any kind
- Pattern mining or pattern store
- Suggestions or patches
- MCP server or Claude Code integration
- Postgres backend
- Cross-project analysis

If a PR adds any of the above, it belongs in a later release.

## Deployment targets

- Primary: any developer workstation (macOS, Linux, Windows-via-WSL2).
- Runtime target: ≤ 60s first run on 100k LOC, ≤ 15s re-run.

## Privacy invariants

- Zero outbound network calls by default. Enforced by test.
- `scope: corporate` repos write nothing outside their own `.instinct/` directory.
- No telemetry. Ever.
````

## 15. Implementation Order

Suggested vertical-slice build order for Release 1:

1. **Slice 1:** `core/` types + `storage/` minimal schema + migrations + `cli/ version` + `instinct init`. Proves tooling and layering.
2. **Slice 2:** `parse/` for one language (Python, as self-dogfood target) + `graph/` call graph. Proves parsing pipeline.
3. **Slice 3:** First three metrics end-to-end: `cyclomatic_complexity`, `cognitive_complexity`, `statement_count`. Produces a minimal report.
4. **Slice 4:** Full Phase 1 metric suite for Python.
5. **Slice 5:** Observation store with dedup and stability tiering. Run 2+ times and confirm dormant shortcut.
6. **Slice 6:** Report generators — JSON, terminal (rich), HTML.
7. **Slice 7:** Add Rust language adapter. Confirm parity.
8. **Slice 8:** Add C# and TypeScript adapters.
9. **Slice 9:** `instinct explain` and `instinct trend`.
10. **Slice 10:** Reference corpus + snapshot tests + performance benchmarks against NFRs.
11. **Slice 11:** Hardening — graceful degradation, error messages, help text, docs.

Each slice is a PR. Acceptance criteria are checked against the PRD at each slice.

## 16. Known Technical Decisions

### 16.1 AST serialization format

Use tree-sitter's built-in serialization where possible; fall back to a compact JSON form. Compressed with zstd for storage. Pruned for dormant artifacts older than 30 days (keep the hash, drop the serialized tree) to control DB size.

### 16.2 Hash function

`blake3` preferred for speed; fall back to `xxhash` if blake3 bindings are problematic. SHA-256 is overkill for non-cryptographic deduplication.

### 16.3 Tree-sitter grammar version pinning

Pin specific grammar versions in `pyproject.toml`. Grammar upgrades invalidate `ast_hash` values and therefore invalidate caches; this is acceptable if rare, but should be a deliberate event (metric_version bump) rather than accidental.

### 16.4 Parallelism implementation

Start with `ProcessPoolExecutor`; evaluate `joblib` or `anyio` if process startup overhead dominates. MVP does not implement async; the analysis pipeline is synchronous per-process with process-level parallelism.

### 16.5 Config file format

YAML for human editability. Pydantic models validate on load; unknown keys are errors by default (strict mode).

## 17. Open Technical Questions

These are implementation-level questions expected to resolve during Slice 1–2:

- [ ] `pydriller` vs. `gix` Python binding for git history — evaluate speed on Baker Street repo (~5 years of history).
- [ ] `blake3` availability on all target platforms — if arm64 support is flaky, default to `xxhash`.
- [ ] Tree-sitter-c-sharp maturity — confirm Phase 1 metric computation works on Baker Street .NET code.
- [ ] HTML report CSS approach — hand-rolled vs. minimal Tailwind-like utility set inlined. Leaning hand-rolled.

These do NOT block MVP; they're decision points expected to surface early and resolve quickly.
