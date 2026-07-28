# Instinct — Executive Summary

**Product:** Instinct (`savviety-instinct`)
**Audience:** decision-making, sharing with collaborators, future-Gary skimming
**Companion documents:** `01-locked-decisions.md`, `02-prd.md`, `04-architecture-spec.md`, `05-metric-catalog.md`

---

## The Problem

Existing static analysis tools measure what's easy to count: cyclomatic complexity, lines of code, fan-in/fan-out. These catch real problems but miss the two that matter most in practice:

1. **Cognitive opacity** — code that's metric-clean but unreadable. The fear case is thousands of lines of production code that only a frontier LLM can decipher.
2. **Ravioli fragmentation** — 240 trivial functions that are individually fine and collectively incomprehensible. Per-unit metrics reward this structure.

Separately, a solo maintainer has no team to ask "is this codebase getting better or worse?" Without accumulated measurement over time, every concern is anecdotal.

Later releases also address a third problem: LLM code generation over-deliberates on patterns a senior developer handles by reflex, because it has no grounded sense of "the right shape for this team." That's the payoff of the full vision — but the MVP stands on its own without it.

## Primary User (MVP)

**A solo developer or lead maintainer working across multiple personal repositories** who wants a ranked list of high-signal code to inspect, a profile showing the shape of trouble, and a trend view over time.

Not a team. Not a CI system. Not an AI coding agent. Those users arrive in later releases.

## MVP Boundary

Release 1 ships:

- CLI tool, local-first, per-project SQLite
- Tree-sitter parsing for Rust, C#, TypeScript, Python
- Phase 1 metric suite: control-flow, ravioli, coupling, temporal, composite ranking
- Observation store with artifact deduplication and stability tiering
- Reports in JSON, terminal, and HTML
- Trend view across runs

Release 1 does NOT ship: any LLM functionality, pattern mining, suggestions, patches, MCP, remote APIs, CI integration, or cross-project analysis. Every one of those is valuable; none is required to prove the core hypothesis that measurement plus accumulation produces a useful trend view.

## The Hypothesis

A single tool can address all three problems (two now, one later) by treating analysis as a closed loop:

> **Measure → Accumulate → Curate → Apply → Measure again.**

Release 1 delivers the first two steps. Each subsequent release adds a step without retrofitting:

- **R1 (MVP):** Measure and Accumulate.
- **R2:** Add LLM-backed triage and deep-read stages. Comprehensibility axis becomes measurable.
- **R3:** Add Curate — a scheduled agent turns observations into a pattern library. Patterns are files (canonical) indexed in the DB (derived).
- **R4:** Add Apply — suggest → patch-assist → apply ladder, with override-tracking feedback.
- **R5:** Integrate with Claude Code for generation-time pattern retrieval.

The compounding is the point. A single run is a linter. A system that learns what *this* codebase actually looks like over time is something different.

## The Architecture in One Picture

```
                       ┌──────────────────┐
   source code ───────▶│    Analyzer      │  ◀──── MVP
                       │  (multi-axis)    │       tree-sitter, metric suite
                       └────────┬─────────┘
                                │ writes
                                ▼
                       ┌──────────────────┐
                       │ Observation Store│  ◀──── MVP
                       │  (raw, append)   │       deduped via artifact table
                       └────────┬─────────┘       stable code is cheap
                                │ reads
                                ▼
                       ┌──────────────────┐
                       │     Curator      │  ◀──── Release 3
                       │ (LLM-backed)     │       runs on the inference node, MLX
                       └────────┬─────────┘
                                │ proposes changes to
                                ▼
                       ┌──────────────────┐
                       │  Pattern Store   │  ◀──── Release 3
                       │  files+DB index  │       scopes: project/personal/global
                       └────────┬─────────┘
                                │ reads
                                ▼
            ┌───────────────────┴────────────────────┐
            ▼                                        ▼
   ┌────────────────┐                       ┌────────────────┐
   │  Assist Ladder │  ◀── Release 4        │  Claude Code   │  ◀── Release 5
   │ Obs→Sug→Patch  │                       │   (MCP/RAG)    │
   │   →Apply       │                       └────────────────┘
   └────────────────┘
```

## Five Distinguishing Decisions

1. **Multi-axis profile + single-ranked target list.** Composite scores hide failure modes; a profile shows shape, a ranked list shows where to start.
2. **Three Analysis Stages (Metric, Triage, Deep Read).** Math flags, a small local model triages, a larger model deep-reads only the highest-signal candidates. LLM cost stays proportional to value. (Deferred to R2.)
3. **Three Pattern Scopes (Project, Personal, Global).** Abstraction increases per scope. Patterns are promoted bottom-up from evidence, never authored top-down. Canonical form is YAML files in version control; DB is a derived index. (Deferred to R3.)
4. **Actively Managed observation and pattern stores.** Per-run amnesia destroys the value proposition. The curator turns accumulating observations into knowledge. (MVP does the accumulation; curation arrives in R3.)
5. **Assist Ladder, not a flag.** Observe → Suggest → Patch-Assist → Apply. Each level requires more trust and earns its way up. MVP ships at Observe only. (Deferred to R4.)

## Privacy and Scope Discipline

Instinct performs zero outbound network calls by default. Remote APIs are opt-in per repo.

Repos declare their scope explicitly (`personal | corporate | open-source`) in `.instinct/config.yaml`. Corporate-scoped repos are hard-isolated: their observations never leave the repo, they never participate in cross-project analysis, and they never contribute to personal pattern learning. Missing scope declaration is an error, not a default.

This is a product requirement, not operational hygiene. Client work and personal work share a machine; they don't share a knowledge base.

## Measurable Success for MVP

The MVP is not successful unless these targets are met. Self-assessed on three real repos (Baker Street, Resolve, a Python reference).

| Target | Threshold |
|---|---|
| Install-to-first-report time | ≤ 5 minutes |
| First-run analysis on 100k LOC | ≤ 60 seconds |
| Re-run on same repo (≥70% dormant) | ≤ 15 seconds |
| Top-10 relevance (maintainer judgment) | ≥ 7 of 10 worth investigating |
| Repeat-run frequency over 6 weeks | ≥ 1 run per active repo per week |
| Reproducibility | Identical inputs → identical outputs across 10 runs |

Full success criteria and acceptance tests in the PRD.

## What the First Report Looks Like

```
Instinct Report — baker-street
Run: 2025-11-15 14:32:17 (first run)
Scope: personal | Remote APIs: disabled
Files: 347 C# | Functions: 2,184 | Modules: 47

PROFILE
  Per-unit cognitive load ....... Watch      (p90 = 14, p95 = 23)
  System fragmentation .......... Elevated   (p95 ratio = 0.58)
  Coupling health ............... Watch      (D p95 = 0.71)
  Temporal pressure ............. Normal     (3.2 commits/wk p95)

TOP 10 ATTENTION TARGETS
#1  MessageRouter.cs:142  RouteMessage
    Priority 9.4 (p99) — cognitive 34, npath 1842, 23 callers, 2.1/wk
    → Deep nesting in hot dispatch path with frequent churn

#2  Agents/Coordinator (module)
    Priority 8.7 (p98) — 71% trivial delegation, 38 functions, locality 0.31
    → Ravioli pattern: high delegation, low locality

... 8 more ...

Explain any target: instinct explain <file>:<function>
Full report: .instinct/reports/2025-11-15T14-32-17.html
```

Every number traces to a formula in the metric catalog. Every target has a rationale. No magic.

## Why Now

Several investments converge on this tool:

- **Multi-project workload** (a mix of .NET, TypeScript, and cloud client engagements) is the substrate where cross-project pattern synthesis becomes possible in later releases.
- **Postgres + pgvector + Voyage stack** is already running on Resolve and is the right substrate when R2+ needs embedding search.
- An **Apple Silicon inference node (M4 Pro, 64GB, MLX)** is set up for local LLM inference and is the natural curator host in R3+.
- **Existing Actively Managed Knowledge Base pattern** from the inbox system maps directly onto observation/pattern-store separation. Same metabolism, different content.
- **Claude Code skills and handoff workflow** is the distribution channel for R5 generation integration.

The MVP doesn't need any of this. But the architecture reserves the right shape so those investments pay out when their releases arrive.

## Honest Risks

- **Review cost.** A tool that flags 20 things per repo only helps if the maintainer actually reads them. The Top-10 relevance target (≥ 7 of 10 worth investigating) is the guardrail; if it's not met, the tool is noise.
- **Pattern calcification in later releases.** Once a pattern is canonical, the tool will pressure code toward it. If the canonical was wrong, the tool entrenches the wrong thing. Lifecycle states and override-tracking feedback loop mitigate this, but not in MVP — it's an R3+ concern.
- **Scope creep.** The full vision covers analyzer, observation store, curator, pattern store, assist ladder, MCP, generation integration. The MVP boundary is the discipline that prevents this from becoming a perpetually-planned system. Each release has its own scope; each stands alone.

## The Through-Line

One tool, one loop:

> **Measure what matters. Reason about what the math can't see. Learn what the team does well. Feed that learning back into how the team writes code.**

R1 does the measuring. R2 adds the reasoning. R3 adds the learning. R4-5 feed it back. Each release is independently valuable. The compounding is what makes this worth building rather than configuring an existing tool harder.

## Next Step

Begin implementation of Release 1 (MVP) from the PRD. Reference corpus and fixture repos first, then metric core, then observation store, then report generator. The metric catalog is the authoritative technical reference; the architecture spec describes the module layout and contracts.
