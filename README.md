# instinct

[![CI](https://github.com/garyld1962/savviety-instinct/actions/workflows/ci.yml/badge.svg)](https://github.com/garyld1962/savviety-instinct/actions/workflows/ci.yml)

A local-first static-analysis CLI that measures the code-health problems conventional linters miss:
**cognitive opacity** (code that passes every metric and is still unreadable) and **ravioli
fragmentation** (hundreds of trivial functions that each do nothing). It parses with tree-sitter,
stores observations in a per-project SQLite store so trends accumulate across runs, and ranks what to
look at first.

This repo is also the strongest example in my work of testing designed to catch its own author's
confirmation bias — see below.

## Proof

- **461 tests, 91% branch coverage** — `uv run pytest` (coverage is on by default; CI runs the same
  command)
- **Four test layers**, documented in [`docs/testing.md`](docs/testing.md):
  1. *Unit* — hand-authored expectations
  2. *Differential* — every complexity metric checked against an independent external implementation
     (`radon` for cyclomatic, the `cognitive_complexity` package for cognitive)
  3. *Property-based* — Hypothesis invariants pinning value ranges for all nine metrics
  4. *Adversarial parser fixtures* — `match`, walrus, async generators, decorator stacks, PEP 695
     generics, PEP 654 exception groups
- **The layering found three real bugs** (documented with impact in
  [`docs/plans/2026-04-20-test-hardening-algorithmic-rigor.md`](docs/plans/2026-04-20-test-hardening-algorithmic-rigor.md)):
  **B1** `match`/`case` missing from the statement and control-flow node maps, so match-only function
  bodies scored `statement_count=0, cyclomatic=1` regardless of case count · **B2** `@property`
  getter and setter colliding on the same qualified name, breaking uniqueness for any consumer keyed
  by it · **B3** PEP 654 `except*` not counted as a decision point.

B3 is the one worth dwelling on: `radon` has the *same* blind spot on cyclomatic complexity, so a
single differential oracle would have agreed with the bug. The second oracle disagreed, and that
disagreement is what exposed it. Layer 1 alone would have missed all three — the expectations were
written by the same person who wrote the parser.

## Scope, honestly

Python only today (tree-sitter-python is the sole grammar). Nine metrics are implemented: cyclomatic,
cognitive, npath, statement count, max nesting depth, median function length, function-length
bimodality, trivial-delegation ratio, and identifier quality. Working commands are `version`, `init`,
and `run`; `sync`, `curate`, `suggest`, `apply`, and `serve` are registered but reserved and raise on
invocation. There is no LLM adjudication, no MCP server, and no mutation-testing baseline — those are
designed (see `docs/`) and not built.

## Run it

```bash
uv sync
uv run pytest              # 461 tests
uv run instinct init       # create the per-project observation store
uv run instinct run        # analyze the current repo and report
```

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/). Everything runs locally — no network, no
API keys.

## Design docs

`docs/01-locked-decisions.md` (closed decisions and rationale) · `docs/02-prd.md` ·
`docs/03-executive-summary.md` · `docs/04-architecture-spec.md` · `docs/05-metric-catalog.md` ·
`docs/testing.md`

## License

MIT
