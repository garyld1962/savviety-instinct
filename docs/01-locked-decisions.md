# Locked Decisions — Code Intelligence Tool

**Status:** Committed. These decisions are inputs to the PRD, Architecture Spec, and Metric Catalog rewrites. Changing any of them requires revisiting the documents downstream.

**Date locked:** [fill in on adoption]

---

## D1. Name

**Product name:** Instinct
**Package name:** `savviety-instinct`
**CLI name:** `instinct` (with `savviety-instinct` as a fully-qualified alias for environments where short names collide)
**Repository name:** `savviety-instinct`

**Rationale:** names the core hypothesis (team-specific code instinct), reads well in sentences ("run instinct on this repo"), brand-aligned with Savviety, leaves Holmes naming for homelab machines and Baker Street subsystems where it's already working.

**One-line tagline:** *Measure what matters. Learn what your team does well. Apply it.*

---

## D2. MVP Boundary

**In scope for MVP (Release 1):**

- CLI only (`instinct run`, `instinct report`)
- Local-first execution on a single developer workstation
- Per-project SQLite observation store
- Tree-sitter-based parser for Rust, C# (.NET), TypeScript, Python
- Phase 1 metric suite (control-flow, ravioli, coupling, temporal, composite ranking) — no LLM-backed metrics
- Observation store with artifact deduplication and stability tiering
- Reports: JSON, terminal (rich), HTML single-page
- Git history integration for temporal metrics
- Trend view across runs over time

**Explicitly out of scope for MVP:**

- LLM adjudication of any kind (deferred to Release 2)
- Pattern mining and pattern store (deferred to Release 3)
- Suggestions of any level (deferred to Release 4)
- Patches or code modification
- MCP server
- Claude Code integration
- Remote model dependencies
- Cross-project analysis
- Rollups or retention compression
- Postgres backend (SQLite only in MVP)
- Pattern enforcement or CI gating
- Shared pattern libraries

**Rationale:** the MVP is a useful standalone analyzer. It produces a ranked list and a profile today, accumulates observations that future releases will curate, and has zero external dependencies. Every deferred item is valuable; none is required to prove the core hypothesis that measurement plus accumulation produces a useful trend view for a solo maintainer.

---

## D3. Primary User for MVP

**Primary user:** a solo developer or lead maintainer working across multiple personal repositories who wants:

1. A ranked list of high-signal code to inspect
2. A profile showing the shape of trouble (per-unit complexity vs. fragmentation vs. coupling vs. temporal pressure)
3. A trend view over repeated runs

**Explicit non-users in MVP:**
- Teams with shared responsibilities (deferred — shared pattern libraries come in later releases)
- CI systems (deferred — the MVP is interactive)
- AI coding tools consuming patterns (deferred — Release 4+)
- Enterprise compliance auditors (deferred — reporting format for this is out of scope)

**The MVP user role is "consumer of analysis on their own repos," not "curator of shared knowledge."** The curator role belongs to Release 3 when the pattern store exists.

---

## D4. Pattern Store Source of Truth

**Canonical form:** YAML/Markdown files, version-controlled.

- Project (Tier 1) patterns live in `<repo>/.instinct/patterns/*.yaml`, committed with the code.
- Personal (Tier 2) patterns live in `~/.instinct/patterns/*.yaml`, git-managed separately.
- Global (Tier 3) patterns live in a dedicated `savviety-patterns` repository.

**Derived form:** database rows in the pattern store, indexed for retrieval (structural signatures, embeddings, lifecycle state cache).

**Rebuild rule:** the database representation is fully reconstructable from the files. `instinct rebuild-patterns` is a supported operation.

**Edit rule:** humans edit files; the curator proposes file changes (as PRs or patches) rather than writing directly to the database.

**Deferred to Release 3.** Locked here so the architecture reserves the right shape from day one.

**Rationale:** preserves git-based auditability and human editing ergonomics; the database exists for query performance, not authority.

---

## D5. Privacy and Network Policy

**Default mode:** local-only. Instinct performs zero outbound network calls by default.

**Opt-in for remote APIs:** per-repo configuration in `.instinct/config.yaml` with an explicit `remote_apis_allowed: true` flag. Absent or false = no outbound traffic.

**Corporate-repo guarantees:**
- Cross-project promotion (Release 4+) is disabled by default when a repo is marked `scope: corporate`.
- Tier 2 personal pattern mining excludes corporate repos unless explicitly enabled.
- A corporate repo's observation data never appears in cross-project analyses without explicit `include_in_cross_project: true`.

**Declared in `.instinct/config.yaml`:**

```yaml
scope: personal | corporate | open-source
remote_apis_allowed: false
include_in_cross_project: false
llm_backend: local | ollama | anthropic | disabled
```

**Rationale:** JMA work must never leak into the personal pattern library or out to remote APIs. This is a hard product requirement, not an operational preference.

---

## D6. LLM Verdict Cache Key

**Cache key composition:**

```
cache_key = hash(
  artifact_ast_hash,     # the function's AST shape
  context_hash,          # see below
  model_id,              # e.g., "qwen2.5-coder-7b-mlx-q4"
  prompt_hash,           # hash of the prompt template + parameters
  metric_version         # the metric formula version
)
```

**`context_hash` composition:**

```
context_hash = hash(
  language,
  enclosing_signature,           # e.g., class name + interfaces, module name
  import_set_normalized,         # sorted list of imports used in the artifact
  framework_indicators,          # detected framework: "aspnetcore", "nextjs", etc.
  caller_signature_set,          # signatures of immediate callers (not bodies)
  callee_signature_set           # signatures of immediate callees (not bodies)
)
```

**Rationale:** the same AST shape can behave very differently depending on surrounding context. Caching on AST alone produces fast wrong answers. Caching on AST + context produces fast right answers; cache hit rate drops somewhat but correctness is preserved.

**Deferred to Release 2.** Locked now so the MVP schema reserves the column.

---

## D7. Retention Defaults

**MVP retention:**

- `run_observations` (link rows): **180 days**, then deleted
- `observation_artifacts` (the unique-shape rows): **kept while referenced** by any `run_observations` or `pattern_evidence` row
- `llm_verdicts`: **kept while the artifact exists** (deferred — Release 2)
- `pattern_evidence`: **indefinite** (deferred — Release 3)

**Explicitly NOT in MVP:** monthly rollups, time-series compression, cold-storage tiers. All deferred to a later release. If long-term trends are needed before rollups exist, the raw 180-day window plus artifact history is sufficient for the first 6 months of use.

**Rationale:** rollups require their own task implementation and schema. Defer them rather than committing to a half-built version. 180 days covers repeat-run trend analysis across ~2 quarters, which meets the MVP success criteria.

---

## D8. Scope Defaults by Repo Type

Repos declare their scope explicitly. Default scoping rules:

| Scope value | Cross-project inclusion | Tier 2 promotion eligible | Remote APIs default | Notes |
|---|---|---|---|---|
| `personal` | opt-in (default: false) | yes (default: true) | false | Default for new personal repos |
| `corporate` | never (hard no) | never | false (hard no) | JMA repos land here |
| `open-source` | opt-in (default: false) | opt-in (default: false) | opt-in (default: false) | Potentially public analysis data |

**Repos must declare scope.** Missing `scope:` in config is an error, not a default. This forces the decision explicitly rather than letting corporate code silently flow into personal analyses.

**Rationale:** prevents the worst-case data leak by construction. Explicit is better than implicit here.

---

## D9. Terminology Disambiguation

Three concepts were previously all called "tiers." Rename permanently:

| Old | New | Applies to |
|---|---|---|
| LLM Tier 1 / 2 / 3 | **Analysis Stages:** Metric, Triage, Deep Read | How heavily the LLM is used on a given candidate |
| Pattern Tier 1 / 2 / 3 | **Pattern Scopes:** Project, Personal, Global | What breadth of code a pattern applies to |
| Suggest levels 0–3 | **Assist Levels:** Observe, Suggest, Patch-Assist, Apply | How actively the tool modifies code |

"Stages" reflect sequential processing. "Scopes" reflect breadth. "Levels" reflect increasing assertiveness. Each term now points at exactly one concept.

---

## Summary of locked commitments

1. **Name:** Instinct (`savviety-instinct`).
2. **MVP:** analyzer + observation store + ranking + reports. No LLM, no patterns, no suggestions.
3. **Primary user:** solo maintainer, personal repos, consumer of analysis.
4. **Pattern truth:** files canonical, DB derived.
5. **Privacy:** local-only default, opt-in remote, hard corporate guarantees.
6. **Cache key:** artifact + context + model + prompt + metric version.
7. **Retention:** 180 days for observations; artifacts while referenced; no rollups in MVP.
8. **Scope defaults:** explicit declaration required; corporate is hard-isolated.
9. **Terminology:** Analysis Stages, Pattern Scopes, Assist Levels.
