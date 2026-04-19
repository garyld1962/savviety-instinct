# CLAUDE.md

@CLAUDE.local.md

Project-specific instructions for Claude Code in this repository.

This file is the top-level source of truth for *shared* conventions.
Personal overrides live in `CLAUDE.local.md` (gitignored) and are loaded
via the `@CLAUDE.local.md` reference above.
Per-skill project config lives under `.claude/skills/_project/`.

<!-- Replace the comments below with real content. Delete sections that don't apply. -->

## Stack

<!--
- Language(s) and version(s)
- Build / test / lint commands
- Package manager
- Runtime / target environments
-->

## Conventions

<!--
- Code style and formatting rules
- File and folder layout
- Naming conventions (files, types, tests)
- Error handling, logging, async patterns
-->

## Workflow

<!--
- Branch / PR conventions
- How to ship (deploy, release, hotfix paths)
- Where issues live (GitHub, Linear, ADO)
- Quality gates before merge
-->

## Domain notes

<!--
- Domain vocabulary that isn't self-evident from code
- External systems this repo integrates with
- Constraints worth knowing on day one
-->

## Pointers

- Personal overrides: `CLAUDE.local.md`
- Project skill config: `.claude/skills/_project/`
- Shared skills installed via [savviety-skills](https://github.com/garyld1962/savviety-skills) — refresh with `repo-skills --claude --update`.
