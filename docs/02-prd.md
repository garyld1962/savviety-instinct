# Instinct — Product Requirements Document

**Product:** Instinct
**Package:** `savviety-instinct`
**Status:** MVP (Release 1) scope
**Owner:** Gary / Savviety
**Companion documents:** `01-locked-decisions.md`, `03-executive-summary.md`, `04-architecture-spec.md`, `05-metric-catalog.md`

---

## 1. Product Summary

Instinct is a static analysis tool that measures code complexity and comprehensibility across multiple axes, accumulates observations over time, and produces a ranked list of investigation targets plus a multi-axis profile of codebase health.

**One-line value proposition:** *For solo maintainers who run multiple repositories, Instinct answers "where should I look first?" and "is this getting better or worse?" with numbers that can be trusted and trends that compound over time.*

The MVP is a complete, useful tool on its own. Future releases add LLM adjudication (Release 2), pattern mining (Release 3), suggestions (Release 4), and generation integration (Release 5). Each builds on the MVP's observation store without requiring retrofits.

## 2. Problem Statement

Existing static analysis tools measure what's easy to count: cyclomatic complexity, lines of code, fan-in/fan-out. These catch some real problems but miss the two that matter most for a solo maintainer working across multiple personal projects:

1. **Cognitive opacity.** Code that's metric-clean and unreadable. The fear case is production code thousands of lines long that only a frontier LLM can decipher. Classical metrics don't measure readability.

2. **Ravioli fragmentation.** 240 trivial functions that are individually fine and collectively incomprehensible. Per-unit metrics reward this structure because they score each unit in isolation.

Additionally, a solo maintainer has no team to ask "is this codebase getting better or worse?" Without accumulated measurement over time, every concern is anecdotal.

## 3. Primary User (MVP)

**A solo developer or lead maintainer working across multiple personal repositories** who wants:

- A ranked list of high-signal code to inspect, not a firehose of warnings
- A profile showing the shape of trouble, not a single opaque score
- A trend view over repeated runs so "it feels worse than last month" can be tested

**User's situation:**
- Runs multiple repos in different languages and stacks
- Has limited time to spend on tooling; the tool must earn its attention
- Doesn't have a team to discuss architecture with; the tool substitutes for some of that conversation
- Cares about keeping corporate and personal code analysis strictly separated

**User's current workarounds (and their failure modes):**
- SonarQube / Sonar CLI — too heavyweight, too many false positives, weak at trend views, poor at fragmentation
- `lizard`, `radon`, `scc` — narrow; measure one thing
- Manual code review — doesn't scale across repos, no memory, no trend
- Eyeballing git diffs — misses accumulated decay

## 4. MVP Scope

### 4.1 In scope

- CLI tool (`instinct run`, `instinct report`)
- Tree-sitter-based parsing for Rust, C#, TypeScript, Python
- Phase 1 metric suite: control-flow, ravioli, coupling, temporal, composite ranking (no LLM)
- Per-project SQLite observation store with artifact deduplication and stability tiering
- Git history integration for temporal metrics (change frequency, bug-fix density, author count)
- Reports in JSON (machine), terminal (rich), and HTML (single-page, self-contained)
- Trend view across runs over time (requires ≥2 runs in window)
- Configuration via `.instinct/config.yaml` per repo
- Explicit scope declaration (`personal | corporate | open-source`) required per repo

### 4.2 Out of scope for MVP

- LLM adjudication (Release 2)
- Pattern mining and pattern store (Release 3)
- Suggestions of any level (Release 4)
- Patches or code modification
- MCP server / Claude Desktop integration
- Claude Code integration / generation context injection
- Remote model dependencies
- Cross-project analysis
- Shared / synced pattern libraries
- Postgres backend
- CI integration / enforcement / gating
- Monthly rollups or retention compression

## 5. Success Metrics

Concrete, measurable targets. The MVP is not successful unless these are met.

### 5.1 Performance targets

| Metric | Target | How measured |
|---|---|---|
| Install-to-first-report time | ≤ 5 minutes on a fresh machine with `uv` installed | Manual timed test on macOS and Linux |
| Runtime on representative repo | ≤ 60 seconds for a 100k-LOC repo, first run | Benchmark on Baker Street (.NET), Resolve (TS), and a Python reference repo |
| Runtime on representative repo, subsequent run | ≤ 15 seconds for the same repo with ≥ 70% dormant artifacts | Same benchmark after first run settles |
| Memory ceiling | ≤ 1 GB resident during analysis of a 500k-LOC repo | Observed during benchmark |

### 5.2 Quality targets

| Metric | Target | How measured |
|---|---|---|
| Top-10 relevance | ≥ 7 of top-10 ranked targets judged "worth investigating" by the maintainer | Self-assessment on 3 real repos after first run |
| False-positive rate on generated code | 0% — generated code is suppressed by default patterns and does not appear in rankings | Fixture test with generated code present |
| Reproducibility | Identical inputs produce identical outputs across 10 consecutive runs | Automated test |
| Cross-language consistency | Same type of complexity issue gets comparable rankings in Rust, C#, TS, Python | Fixture test with parallel examples |

### 5.3 Adoption targets (self-assessed)

| Metric | Target | How measured |
|---|---|---|
| Repeat-run frequency | ≥ 1 run per week per active repo over a 6-week window | Observation store log |
| Trend usefulness | At least 2 instances where the trend view changed a maintenance decision | Self-assessment journal |
| Time-to-first-action | ≤ 30 seconds from opening a report to identifying a first action item | Self-timed on 3 repos |

## 6. User Workflows (MVP)

Four workflows define the MVP experience. Each specifies trigger, inputs, system behavior, outputs, and failure handling.

### 6.1 Workflow W1: First analysis of a repo

**Trigger:** user runs `instinct run` in a repo for the first time.

**Inputs:**
- Repo source tree
- (Required) `.instinct/config.yaml` with at minimum `scope: personal | corporate | open-source`
- Git history

**System behavior:**
1. Validate config exists and declares scope. If missing, emit a clear error with remediation ("run `instinct init` to create a default config").
2. Create `.instinct/instinct.db` (SQLite).
3. Parse source files using tree-sitter for the detected languages. Skip binaries, vendored dirs (per suppression rules), generated files (per suppression rules), and files over size limit.
4. Compute Phase 1 metrics. Write to observation store with dedup via `ast_hash`.
5. Compute composite ranking (`attention_priority`).
6. Emit report.

**Outputs:**
- JSON report at `.instinct/reports/<timestamp>.json`
- Terminal summary: top-10 attention targets, profile axes with p50/p90/p95, counts (files analyzed, artifacts, dormant)
- HTML report at `.instinct/reports/<timestamp>.html`

**Failure handling:**
- Parser error on a file: log warning, skip the file, continue. Surface skipped-file count in the report.
- Git history unavailable (no `.git`): skip temporal metrics, emit warning, proceed with other metrics.
- Unsupported language: file is counted as "skipped — unsupported language" in the report summary.
- No files parseable: exit non-zero with a clear message.

**Acceptance criteria:**
- Running `instinct run` on Baker Street, Resolve, and a reference Python repo produces reports within time targets.
- Top-10 list contains ≥ 7 items the maintainer considers worth investigating (self-assessed).
- Report clearly distinguishes scope (personal/corporate/open-source) in its header.
- Corporate-scoped runs never write to `~/.instinct/` paths.

### 6.2 Workflow W2: Review the ranked list

**Trigger:** user opens a report after W1 or W3.

**Inputs:** report JSON or HTML.

**System behavior:**
- Report presents the top-N (default 20) attention targets.
- For each target: file path and line number, function or module name, attention priority score, and the specific metrics that flagged it.
- Each flagged metric includes: value, codebase percentile, threshold crossed, and one-line rationale.
- Profile axes visible: per-unit cognitive load, system fragmentation, coupling health, temporal pressure.
- Each axis shows p50, p90, p95 within codebase and (where available) language norm comparison.

**Outputs:** same report, navigable.

**Failure handling:**
- Stale report (underlying files deleted): mark targets as "source missing" but preserve the entry.
- Missing git data for temporal column: show "—" rather than 0; never fabricate.

**Acceptance criteria:**
- Any entry in the top-10 can be traced to specific metric values in under 30 seconds.
- No metric value appears without a rationale explaining why it was flagged.
- Reports older than the observation TTL still render (from cached report data), but with a "some source may have moved" note.

### 6.3 Workflow W3: Inspect one target and understand why it surfaced

**Trigger:** user identifies a target in W2 and wants to understand it.

**Inputs:** target identifier (file:function or entry ID).

**System behavior:**
- `instinct explain <target>` produces a detailed view of a single target.
- Shows all computed metric values for that target, with per-metric explanation:
  - What the metric measures
  - Its value
  - Where that falls in the codebase distribution
  - Known pitfalls / caveats for that metric
  - Graceful-degradation notes if inputs were incomplete
- Shows the temporal view: how this target's metrics have moved across the last N runs.
- Shows related targets: functions in the same module with similar flags.

**Outputs:** terminal or HTML detail view.

**Failure handling:**
- Target not found in latest run: check history, surface most recent data with timestamp.
- Incomplete metric data (e.g., git history missing): note "temporal data not available" rather than hiding the field.

**Acceptance criteria:**
- `instinct explain` produces a response within 2 seconds.
- Every flagged metric has a human-readable explanation, not just a number.
- Temporal view requires ≥ 2 historical runs; with fewer, shows "insufficient history" rather than a misleading zero.

### 6.4 Workflow W4: Re-run and compare

**Trigger:** user re-runs `instinct run` on a repo that has been analyzed before.

**Inputs:** repo, observation store.

**System behavior:**
1. Perform full analysis as in W1, but:
2. For artifacts classified as `dormant` (unchanged for ≥ N runs AND no git activity for ≥ M days), skip full analysis; perform presence check only.
3. Compute metric deltas vs. previous run.
4. Produce a "changes since last run" section in the report:
   - New targets in top-20
   - Targets removed from top-20 (with reason: resolved, moved, or no longer relatively high)
   - Targets with significant metric changes (any axis shifting by ≥ 1 z-score)
5. Produce a trend view: codebase-level metrics (profile p50/p90/p95) across all runs in window.

**Outputs:** same as W1 plus a "changes since last run" section and a trend view.

**Failure handling:**
- If a previous run's data is unavailable (retention expired, DB corruption), emit warning and fall back to first-run behavior.
- If the git history suggests a merge or rebase (many files touched simultaneously), note this in the header so sudden metric shifts are contextualized.

**Acceptance criteria:**
- Re-runs complete within second-run time target (15s on 100k LOC with 70%+ dormant).
- Trend view is visible when ≥ 2 runs exist; hidden otherwise.
- Changes section explicitly names what moved and why, not just deltas.

## 7. Functional Requirements

### 7.1 Parsing and ingestion

- **FR-1.** MUST parse Rust, C#, TypeScript, and Python using tree-sitter.
- **FR-2.** MUST detect language from file extension with configurable overrides.
- **FR-3.** MUST skip files matching default suppression patterns (node_modules, target/, .venv, dist, build, .next, generated code markers, migrations unless explicitly included).
- **FR-4.** MUST allow per-repo extension of suppression patterns via config.
- **FR-5.** MUST handle parse errors gracefully: log, skip file, continue.
- **FR-6.** MUST enforce a configurable maximum file size (default 1 MB) to prevent runaway analysis on large generated files.

### 7.2 Metric computation

- **FR-7.** MUST compute all Phase 1 metrics listed in the metric catalog for every successfully parsed function, class, and module.
- **FR-8.** MUST record the `metric_version` for every computed value to support schema evolution across releases.
- **FR-9.** MUST be deterministic: identical inputs produce identical outputs.
- **FR-10.** MUST parallelize file-level analysis using available cores (configurable, default = `cpu_count - 1`).
- **FR-11.** MUST compute metrics in under 60 seconds on a 100k-LOC repo on baseline hardware.

### 7.3 Observation store

- **FR-12.** MUST store observations in a per-project SQLite database at `.instinct/instinct.db`.
- **FR-13.** MUST deduplicate artifacts via the cache key defined in `01-locked-decisions.md` (D6). MVP uses `ast_hash + language + metric_version` since LLM verdicts and model context do not apply yet.
- **FR-14.** MUST track artifact stability tiers (volatile, settled, dormant) and use them to skip full analysis of dormant artifacts on subsequent runs.
- **FR-15.** MUST retain `run_observations` rows for 180 days, then delete.
- **FR-16.** MUST retain `observation_artifacts` rows while any `run_observations` row references them.
- **FR-17.** MUST support `instinct vacuum` to manually compact the DB after retention cleanup.

### 7.4 Ranking and reports

- **FR-18.** MUST produce the composite `attention_priority` score for every function and module, ranked descending.
- **FR-19.** MUST produce the multi-axis profile with p50/p90/p95 values per axis.
- **FR-20.** MUST emit reports in JSON, terminal (rich), and HTML formats.
- **FR-21.** HTML reports MUST be single-file self-contained (no external CSS/JS dependencies at view time).
- **FR-22.** MUST produce a trend view when ≥ 2 historical runs exist.
- **FR-23.** MUST produce a "changes since last run" section on re-runs.

### 7.5 Configuration

- **FR-24.** MUST require `.instinct/config.yaml` with explicit `scope` declaration.
- **FR-25.** MUST emit a clear error (not a silent default) when `scope` is missing.
- **FR-26.** MUST provide `instinct init` to scaffold a default config.
- **FR-27.** MUST honor per-repo suppression patterns, language overrides, and metric threshold overrides.

## 8. Non-Functional Requirements

### 8.1 Privacy and security

- **NFR-1.** Default mode performs ZERO outbound network calls. Confirmed by unit test.
- **NFR-2.** Repos with `scope: corporate` MUST NOT write any data to `~/.instinct/` or any path outside the repo.
- **NFR-3.** Repos with `scope: corporate` MUST NOT participate in any cross-project analysis (N/A in MVP; reserved for later releases).
- **NFR-4.** No telemetry in MVP. Period.
- **NFR-5.** No authentication, no cloud accounts, no sign-in.

### 8.2 Performance

- **NFR-6.** First-run analysis on a 100k-LOC repo: ≤ 60 seconds.
- **NFR-7.** Subsequent-run analysis on the same repo with ≥ 70% dormant: ≤ 15 seconds.
- **NFR-8.** Memory usage: ≤ 1 GB resident on a 500k-LOC repo.
- **NFR-9.** Report generation: ≤ 2 seconds on a completed analysis.

### 8.3 Reliability

- **NFR-10.** Parsing errors on individual files MUST NOT crash the run.
- **NFR-11.** A corrupted observation store MUST surface a clear error and offer `instinct rebuild-db` for recovery.
- **NFR-12.** Reports MUST be renderable even when some underlying source files have been deleted.

### 8.4 Usability

- **NFR-13.** Install-to-first-report time on a fresh machine with `uv` pre-installed: ≤ 5 minutes.
- **NFR-14.** CLI commands MUST provide `--help` with examples.
- **NFR-15.** Errors MUST include remediation guidance, not just diagnosis.
- **NFR-16.** Terminal output MUST be readable without color (for logs and pipes) and benefit from color when a TTY is detected.

### 8.5 Portability

- **NFR-17.** MUST run on macOS (arm64), Linux (x86_64 and arm64), and Windows via WSL2.
- **NFR-18.** MUST require only `uv` as a system dependency (Python itself is `uv`-managed).
- **NFR-19.** SQLite databases MUST be portable across platforms.

### 8.6 Graceful degradation

- **NFR-20.** Missing git history: temporal metrics degrade to "unavailable" rather than zero. Tagged so downstream consumers can distinguish "zero" from "unknown."
- **NFR-21.** Ambiguous call graph resolution: metrics depending on the call graph report a `confidence` field. Low-confidence values are visually de-emphasized in reports.
- **NFR-22.** Language-specific metrics on an unsupported construct: skip and note, don't fabricate.

## 9. Reference Corpus and Testing Strategy

The MVP ships with a reference corpus that is the ground truth for regression testing:

- **Known-problematic fixtures** — functions with intentional cognitive opacity, ravioli fragmentation, coupling issues. The tool MUST rank these in the top 10% of their respective fixture repos.
- **Known-good fixtures** — functions with high metric counts that are actually fine (lookup tables, exhaustive switch on enums, setup-heavy test code). The tool MAY flag these but the reports MUST include context that explains what they are.
- **Parallel fixtures across languages** — same complexity problem expressed in Rust, C#, TypeScript, and Python. Ranking parity should be within 1 standard deviation across languages.

Fixtures live in `tests/corpus/` and are the basis for:
- Unit tests per metric (expected value on hand-crafted AST)
- Snapshot tests per fixture repo (full-run output)
- Regression tests for historical bugs
- Cross-language consistency tests

Changes to metric formulas MUST update the snapshot and be reviewed before merge.

## 10. Release Roadmap Beyond MVP

These releases inform the MVP architecture (schema reserves columns; APIs are structured to accept new inputs) but are not in MVP scope.

- **Release 2 — LLM adjudication.** Triage and Deep Read stages on flagged candidates. Comprehensibility axis added. Local LLM via MLX on Irene or Ollama.
- **Release 3 — Pattern mining.** Curator agent. Project-scope pattern library. Reports flag deviations from canonical patterns. Files canonical, DB derived (per D4).
- **Release 4 — Assist levels.** Observe (always on) → Suggest → Patch-Assist → Apply ladder. Personal-scope and Global-scope patterns. Override tracking feedback loop.
- **Release 5 — Generation integration.** MCP server; Claude Code pattern retrieval.

## 11. Open Questions

Resolved before MVP ships:
- [ ] Exact default suppression patterns per language (currently best-guess; needs validation against Baker Street, Resolve, BuildFlow).
- [ ] HTML report CSS framework vs. hand-rolled. (Leaning: hand-rolled for zero-dependency single-file.)
- [ ] `instinct init` interactive vs. non-interactive default (leaning: interactive with `--yes` flag).

Deferred past MVP:
- Postgres backend (Release 2+ if needed)
- MCP surface (Release 5)
- Public pattern libraries (Release 4+)

## 12. Example: What the First Report Actually Looks Like

A concrete example for the Baker Street repo. The report has three regions: header, profile, targets.

### Header

```
Instinct Report — baker-street
Run: 2025-11-15 14:32:17 (first run)
Scope: personal | Remote APIs: disabled
Files analyzed: 347 (C#) | Skipped: 12 generated, 8 too large
Functions: 2,184 | Classes: 389 | Modules: 47
Metric version: 1.0.0 | Tool version: 0.1.0
```

### Profile (radar chart in HTML; table in terminal)

```
Axis                    | p50    | p90    | p95    | Status
------------------------+--------+--------+--------+----------
Per-unit cognitive load | 4      | 14     | 23     | Watch
System fragmentation    | 0.22   | 0.41   | 0.58   | Elevated
Coupling health         | 0.18   | 0.47   | 0.71   | Watch
Temporal pressure       | 0.3/wk | 1.8/wk | 3.2/wk | Normal

Elevated = p95 > healthy threshold
Watch = p90 > healthy threshold
Normal = within expected ranges
```

### Top-10 attention targets

```
#1  src/Brain/Dispatch/MessageRouter.cs:142  RouteMessage
    Priority: 9.4 (p99)
    cognitive: 34 (p99) | npath: 1,842 (p98) | nesting: 6 (p98)
    fan_in: 23 callers | change_frequency: 2.1/wk | bug_fix_density: 0.31
    → Deep nesting in hot dispatch path with frequent churn

#2  src/Agents/Coordinator  (module)
    Priority: 8.7 (p98)
    trivial_delegation_ratio: 0.71 (p99) | median_function_length: 3 stmts
    module_locality: 0.31 | 38 functions across 6 files
    → Ravioli pattern: high delegation ratio, low locality

#3  src/Persistence/AgentStore.cs:89  SaveWithRetry
    Priority: 7.9 (p96)
    cognitive: 22 (p95) | chain_depth_to_effect: 7 (p97)
    fan_in: 11 callers | change_frequency: 0.8/wk
    → Complex retry logic at depth; single author

... (7 more) ...
```

### Footer

```
Full report: .instinct/reports/2025-11-15T14-32-17.html
Explain any target: instinct explain <file>:<function>
Next run will show changes since this baseline.
```

This is what Release 1 delivers. Every number in the report traces to the metric catalog. Every target has a human-readable rationale. No magic.
