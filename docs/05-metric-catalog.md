# Instinct — Metric Catalog

**Companion to:** `02-prd.md`, `04-architecture-spec.md`
**Purpose:** authoritative reference for every metric Instinct computes — formulas, inputs, outputs, thresholds, operational behavior, and known pitfalls.
**Status:** MVP (Release 1) metrics marked `R1`; later-release metrics marked `R2` etc.

---

## Reading the Catalog

Each metric entry uses a fixed shape. The operational fields added per review feedback are in bold:

- **Identifier** — canonical name used in code, config, and reports.
- **Family** — control-flow, size, ravioli, coupling, cohesion, comprehensibility, temporal, composite, or pattern.
- **Unit** — function, class, module, package, or system.
- **Formula** — mathematical definition.
- **Inputs** — what the metric needs (AST, CFG, call graph, git history, LLM, etc.).
- **Output** — type and range.
- **Calibration** — absolute thresholds and distribution-relative thresholds (the default mode).
- **Confidence / reliability** — expected confidence level and what reduces it.
- **Reporting surface** — `Front page` | `Detail view` | `Ranking only` | `Curator only` | `Experimental`.
- **Graceful degradation** — behavior when inputs are partial or unavailable.
- **Minimum sample size** — smallest number of artifacts needed for distribution-relative calibration to be meaningful.
- **Default suppressions** — standard exclusions (tests, generated, vendor, etc.).
- **Pitfalls** — known false positives/negatives.
- **Release** — R1 (MVP), R2, R3+.

**Calibration philosophy:** absolute thresholds are brittle across codebases. Default is to compute distributions per analyzed codebase and flag p90/p95 outliers. Absolute thresholds are documented as overrides and sanity checks. Per-language calibration applies where syntax materially affects magnitude.

**Terminology note (D9):** what was previously called "LLM Tier" is now **Analysis Stage** (Metric, Triage, Deep Read). "Pattern Tier" is now **Pattern Scope** (Project, Personal, Global). "Suggest Level" is now **Assist Level** (Observe, Suggest, Patch-Assist, Apply).

---

## 1. Control-Flow Metrics (R1)

### 1.1 Cyclomatic Complexity (McCabe)

- **Identifier:** `cyclomatic_complexity`
- **Family:** control-flow
- **Unit:** function
- **Formula:** `M = E − N + 2P` over the CFG; for a single connected function: `M = decisions + 1` where decisions count `if`, `else if`, `case`, `for`, `while`, `&&`, `||`, `?:`, `catch`.
- **Inputs:** AST → CFG.
- **Output:** integer ≥ 1.
- **Calibration:** absolute ≤ 10 healthy, 11–20 review, > 20 high-risk. Distribution: flag p95.
- **Confidence / reliability:** high. Degrades to medium if language-specific AST mappings are incomplete for an unusual construct.
- **Reporting surface:** Detail view. (Cognitive complexity is the front-page primary signal.)
- **Graceful degradation:** computable from AST alone; no degradation path needed.
- **Minimum sample size:** 50 functions for meaningful p95.
- **Default suppressions:** tests, generated, migrations.
- **Pitfalls:** lookup-table `switch` statements inflate without inflating cognitive load. Boolean-operator branches each count, potentially misleading on guard-clause-heavy code.
- **Release:** R1.
- **Notes:** Computed but de-emphasized in favor of cognitive complexity. Retained for cross-tool compatibility.

### 1.2 Cognitive Complexity (Campbell / Sonar)

- **Identifier:** `cognitive_complexity`
- **Family:** control-flow
- **Unit:** function
- **Formula:** sum of weighted increments traversing AST:
  - **+1** for break in linear flow: `if`, `else if`, `else`, ternary, `switch`, `for`, `while`, `do`, `catch`, `goto`, recursion entry, sequence of boolean operators (per group, not per operator).
  - **+nesting_depth** additional penalty when above is inside another control structure.
  - **+0** for shorthand that doesn't increase reading load (early return, null-coalescing, single-branch `?.`).
- **Inputs:** AST.
- **Output:** integer ≥ 0.
- **Calibration:** absolute ≤ 15 healthy, 16–25 review, > 25 high-risk. Distribution: flag p90. **Primary per-function complexity signal.**
- **Confidence / reliability:** high when the per-language increment table is complete; medium otherwise.
- **Reporting surface:** Front page.
- **Graceful degradation:** if increment table is incomplete for a construct, the metric counts it as `+1` with `confidence = medium` and a note.
- **Minimum sample size:** 50 functions.
- **Default suppressions:** tests, generated, migrations.
- **Pitfalls:** language-specific shorthand requires per-language rules. Rust `?` operator should not increment; Python list comprehensions count once per generator clause, not per operation.
- **Release:** R1.
- **Notes:** Reference implementation is Sonar's; reproduce its semantics. Per-language increment tables in `core/cognitive_rules/<lang>.yaml`.

### 1.3 NPATH Complexity

- **Identifier:** `npath`
- **Family:** control-flow
- **Unit:** function
- **Formula:** product of path counts across statements. Recursive rules:
  - Sequence `S1; S2`: `NPATH(S1) × NPATH(S2)`
  - `if (c) S1`: `NPATH(c) + NPATH(S1) + 1`
  - `if (c) S1 else S2`: `NPATH(c) + NPATH(S1) + NPATH(S2)`
  - `while (c) S`: `NPATH(c) + NPATH(S) + 1`
  - `do S while (c)`: `NPATH(c) + NPATH(S) + 1`
  - `for (init; c; upd) S`: `NPATH(c) + NPATH(S) + 1`
  - `switch` with cases `C1..Cn` + default: `Σ NPATH(Ci) + NPATH(default)`
  - `try S catch C1..Cn`: `NPATH(S) + Σ NPATH(Ci)`
  - Boolean `&&` / `||` in expression: `+1` per operator.
- **Inputs:** AST.
- **Output:** integer ≥ 1. Values can grow exponentially.
- **Calibration:** absolute ≤ 200 healthy; > 10,000 high-risk. Distribution: flag p95 AND any function ≥ 10× p90 (combinatorial explosion signal).
- **Confidence / reliability:** high.
- **Reporting surface:** Detail view. Cited in front-page target entries when it dominates the ranking.
- **Graceful degradation:** overflow handling — store as `min(npath, MAX_NPATH)` with separate `npath_overflow` boolean. No data loss; ranking treats overflow as top-percentile.
- **Minimum sample size:** 50 functions.
- **Default suppressions:** tests, generated, migrations.
- **Pitfalls:** flat enum dispatch produces large NPATH but low cognitive cost — R2 Triage dismissal target.
- **Release:** R1.

### 1.4 Maximum Nesting Depth

- **Identifier:** `max_nesting_depth`
- **Family:** control-flow
- **Unit:** function
- **Formula:** maximum depth of nested control structures along any path. Lambdas and nested function definitions reset the count.
- **Inputs:** AST.
- **Output:** integer ≥ 0.
- **Calibration:** absolute ≤ 3 healthy, 4 review, ≥ 5 high-risk. Distribution: flag p95.
- **Confidence / reliability:** high.
- **Reporting surface:** Detail view.
- **Graceful degradation:** none needed.
- **Minimum sample size:** 50 functions.
- **Default suppressions:** tests, generated.
- **Pitfalls:** depth is easy to game by extracting helpers. Always read alongside `cognitive_complexity`.
- **Release:** R1.

### 1.5 Statement Count

- **Identifier:** `statement_count`
- **Family:** size
- **Unit:** function
- **Formula:** count of executable statements per language's AST grammar. Excludes blank lines, comments, pure declarations.
- **Inputs:** AST.
- **Output:** integer ≥ 0.
- **Calibration:** absolute ≤ 30 healthy, 31–60 review, > 60 high-risk. Distribution: flag p95.
- **Confidence / reliability:** high.
- **Reporting surface:** Detail view; used as input to multiple composite metrics.
- **Graceful degradation:** none needed.
- **Minimum sample size:** 50 functions.
- **Default suppressions:** tests, generated, migrations (fixtures and migrations are often large and linear).
- **Pitfalls:** sequential setup code (fixtures, migrations) looks big without genuine complexity — R2 Triage target.
- **Release:** R1.

---

## 2. Ravioli / Fragmentation Metrics (R1)

These target the "240 trivial functions" failure mode. Most operate at module or system level.

### 2.1 Trivial Delegation Ratio

- **Identifier:** `trivial_delegation_ratio`
- **Family:** ravioli
- **Unit:** module
- **Formula:**

  ```
  trivial = functions whose body is one of:
    - return f(args) with args passed through unchanged
    - single assignment delegating to another function
    - single-statement wrapper with no transformation
  ratio = |trivial| / |total_functions|
  ```

- **Inputs:** AST per function; module function inventory.
- **Output:** float in [0, 1].
- **Calibration:** absolute ≤ 0.15 healthy, 0.16–0.35 review, > 0.35 ravioli-suspect. Distribution: flag modules in p90.
- **Confidence / reliability:** medium — triviality detection is pattern-based and language-specific.
- **Reporting surface:** Front page (for module-level rankings).
- **Graceful degradation:** when language-specific triviality rules incomplete, `confidence = low` and the metric is shown with a caveat rather than ranking-dominant.
- **Minimum sample size:** 20 functions per module.
- **Default suppressions:** tests (test helpers legitimately delegate), generated, vendor.
- **Pitfalls:** legitimate hexagonal/ports-and-adapters has high delegation by design — R2 Triage dismissal target ("facade by design").
- **Release:** R1.

### 2.2 Median Function Length

- **Identifier:** `median_function_length`
- **Family:** ravioli
- **Unit:** module
- **Formula:** median of `statement_count` across module functions. Also compute bimodality coefficient (Pearson's) to detect "many 2-line functions + a few 200-line ones."
- **Inputs:** per-function `statement_count`.
- **Output:** integer (median) + float (bimodality).
- **Calibration:** absolute median < 5 ravioli-suspect, 5–15 healthy, > 30 review. Bimodality > 0.555 flags suspicious distribution.
- **Confidence / reliability:** high.
- **Reporting surface:** Detail view.
- **Graceful degradation:** none needed.
- **Minimum sample size:** 10 functions per module (median meaningful); 30 for bimodality.
- **Default suppressions:** tests (test files legitimately have many small functions); report test-file versions separately.
- **Pitfalls:** test files. Exclude by default; report separately.
- **Release:** R1.

### 2.3 Call Chain Depth to Effect

- **Identifier:** `chain_depth_to_effect`
- **Family:** ravioli
- **Unit:** function (entry points only)
- **Formula:** for each public entry point, BFS through call graph counting hops until reaching a function that performs an effect (I/O, state mutation, FFI, raise). Metric value = minimum such depth.
- **Inputs:** call graph + per-function effect classification.
- **Output:** integer ≥ 0 (or `∞` if no effect reachable — itself a signal).
- **Calibration:** absolute ≤ 3 healthy, 4–6 review, > 6 deep ravioli. Distribution: flag p90 across entry points.
- **Confidence / reliability:** medium — call graph resolution can be incomplete (dynamic dispatch, indirect calls); effect classification is heuristic.
- **Reporting surface:** Detail view.
- **Graceful degradation:** when call graph resolution is ambiguous, metric produces upper and lower bounds. Reports show the range with `confidence = medium`.
- **Minimum sample size:** 10 entry points.
- **Default suppressions:** tests.
- **Pitfalls:** framework code legitimately delegates many layers. Per-language effect-source lists in `core/effect_sources/<lang>.yaml`.
- **Release:** R1.

### 2.4 Name-to-Body Information Ratio

- **Identifier:** `name_body_info_ratio`
- **Family:** ravioli + comprehensibility
- **Unit:** function
- **Formula:**

  ```
  name_tokens = camelCase/snake_case split of function name minus stopwords
  name_information = |name_tokens|
  body_information = log2(1 + statement_count) + log2(1 + cyclomatic_complexity)
  ratio = name_information / max(body_information, 1)
  ```

- **Inputs:** function name + per-function metrics.
- **Output:** float ≥ 0.
- **Calibration:** absolute > 2.0 means name carries more meaning than body delivers. Distribution: flag p95.
- **Confidence / reliability:** low individually; medium as contributing signal alongside `trivial_delegation_ratio`.
- **Reporting surface:** Detail view; contributing signal only.
- **Graceful degradation:** none needed.
- **Minimum sample size:** 50 functions.
- **Default suppressions:** generated (generated code has systematic long names).
- **Pitfalls:** verbose names trigger this without genuine problem. Use only as contributing signal, never standalone rank driver.
- **Release:** R1.

### 2.5 Module Locality

- **Identifier:** `module_locality`
- **Family:** ravioli + coupling
- **Unit:** function
- **Formula:**

  ```
  callees = functions called by this function
  same_module = callees ∩ functions_in_same_module
  locality = |same_module| / max(|callees|, 1)
  ```

- **Inputs:** call graph + module membership.
- **Output:** float in [0, 1].
- **Calibration:** absolute < 0.3 smeared; > 0.7 self-contained. Distribution: flag p10 (lowest locality) — integration points warrant attention.
- **Confidence / reliability:** medium — depends on call graph resolution.
- **Reporting surface:** Detail view.
- **Graceful degradation:** when call graph resolution is ambiguous, `confidence = medium`; report de-emphasizes.
- **Minimum sample size:** 20 functions in scope.
- **Default suppressions:** tests, generated.
- **Pitfalls:** orchestrators legitimately have low locality — R2 Triage dismissal target.
- **Release:** R1.

---

## 3. Coupling and Cohesion Metrics (R1)

### 3.1 Afferent Coupling (Ca)

- **Identifier:** `afferent_coupling`
- **Family:** coupling
- **Unit:** module / package
- **Formula:** count of distinct outside modules that depend on this module.
- **Inputs:** module dependency graph.
- **Output:** integer ≥ 0.
- **Calibration:** distribution-only. High Ca = popular module = needs stability.
- **Confidence / reliability:** high for static imports; medium if dynamic imports / reflection are common.
- **Reporting surface:** Ranking only (contributes to composite).
- **Graceful degradation:** unresolved imports reduce confidence; metric reports what it can resolve with a note.
- **Minimum sample size:** 5 modules.
- **Default suppressions:** tests.
- **Release:** R1.

### 3.2 Efferent Coupling (Ce)

- **Identifier:** `efferent_coupling`
- **Family:** coupling
- **Unit:** module / package
- **Formula:** count of distinct outside modules this module depends on.
- **Inputs:** module dependency graph.
- **Output:** integer ≥ 0.
- **Calibration:** distribution-only. High Ce = fragile.
- **Confidence / reliability:** high for static imports.
- **Reporting surface:** Ranking only.
- **Graceful degradation:** same as Ca.
- **Minimum sample size:** 5 modules.
- **Default suppressions:** tests.
- **Release:** R1.

### 3.3 Instability (I)

- **Identifier:** `instability`
- **Family:** coupling (Martin)
- **Unit:** module / package
- **Formula:** `I = Ce / (Ca + Ce)`; returns 0 when both zero.
- **Inputs:** `afferent_coupling`, `efferent_coupling`.
- **Output:** float in [0, 1]. 0 = maximally stable, 1 = maximally unstable.
- **Calibration:** no standalone threshold; see `distance_from_main_sequence`.
- **Confidence / reliability:** derived; inherits from Ca/Ce.
- **Reporting surface:** Detail view.
- **Graceful degradation:** inherits from inputs.
- **Minimum sample size:** 5 modules.
- **Default suppressions:** tests.
- **Release:** R1.

### 3.4 Abstractness (A)

- **Identifier:** `abstractness`
- **Family:** coupling (Martin)
- **Unit:** module / package
- **Formula:** `A = abstract_types / total_types` where abstract = interfaces, abstract classes, traits, protocols.
- **Inputs:** AST + per-language abstract-type rules.
- **Output:** float in [0, 1].
- **Calibration:** see `distance_from_main_sequence`.
- **Confidence / reliability:** high for statically-typed OO languages (C#, Rust with traits); medium for TypeScript with structural types; low for Python (depends on convention).
- **Reporting surface:** Detail view.
- **Graceful degradation:** languages without clear abstract-type distinction return `unavailable` with `confidence = low`.
- **Minimum sample size:** 10 types per module.
- **Default suppressions:** tests.
- **Release:** R1.
- **Notes:** Per-language rules in `core/abstractness_rules/<lang>.yaml`.

### 3.5 Distance from Main Sequence (D)

- **Identifier:** `distance_from_main_sequence`
- **Family:** coupling (Martin)
- **Unit:** module / package
- **Formula:** `D = |A + I − 1|`.
- **Inputs:** `abstractness`, `instability`.
- **Output:** float in [0, 1]. 0 = on main sequence; 1 = zone of pain or uselessness.
- **Calibration:** absolute ≤ 0.3 healthy, 0.31–0.6 drift, > 0.6 smell. Distribution: flag p90.
- **Confidence / reliability:** derived; inherits from inputs.
- **Reporting surface:** Front page (for module-level analysis).
- **Graceful degradation:** inherits; reported as unavailable when `abstractness` is unavailable.
- **Minimum sample size:** 5 modules with ≥ 10 types each.
- **Default suppressions:** tests.
- **Pitfalls:** assumes Martin's worldview. Useful in OO and well-modularized codebases; less meaningful in scripts or single-file utilities.
- **Release:** R1.

### 3.6 Henry-Kafura Information Flow

- **Identifier:** `henry_kafura`
- **Family:** coupling (data flow)
- **Unit:** function
- **Formula:** `length × (fan_in × fan_out)²` where:
  - `length` = `statement_count`
  - `fan_in` = distinct functions that call this one
  - `fan_out` = distinct callees + distinct global/module variables read
- **Inputs:** call graph + variable reference analysis.
- **Output:** integer ≥ 0.
- **Calibration:** distribution only — flag p95. Absolute thresholds scale with codebase size.
- **Confidence / reliability:** medium — depends on call graph.
- **Reporting surface:** Ranking only (contributes to composite); log-scaled in dashboards.
- **Graceful degradation:** when fan-in or fan-out resolution is incomplete, `confidence = medium`.
- **Minimum sample size:** 50 functions.
- **Default suppressions:** tests.
- **Pitfalls:** squared term is extremely top-heavy. Hub-and-spoke coordinators dominate by design.
- **Release:** R1.

### 3.7 LCOM-HS (Hitz-Montazeri Lack of Cohesion)

- **Identifier:** `lcom_hs`
- **Family:** cohesion
- **Unit:** class
- **Formula:** treat class as graph (nodes = methods, edges = shared field access). Then:

  ```
  if |methods| ≤ 1: 0
  else:
    components = connected components of the graph
    lcom_hs = (components − 1) / (|methods| − 1)
  ```

- **Inputs:** AST per class; field-access analysis per method.
- **Output:** float in [0, 1]. 0 = cohesive, 1 = disjoint.
- **Calibration:** absolute ≤ 0.3 cohesive, > 0.6 split-candidate. Distribution: flag p90.
- **Confidence / reliability:** high for statically-typed OO; medium for TypeScript with `this`-implicit access; medium for Python.
- **Reporting surface:** Detail view; front-page when it dominates.
- **Graceful degradation:** inapplicable to non-class languages — return `not_applicable`.
- **Minimum sample size:** 10 classes with ≥ 3 methods each.
- **Default suppressions:** tests, generated.
- **Pitfalls:** earlier LCOM1–4 variants have pathologies. Use LCOM-HS specifically.
- **Release:** R1.

---

## 4. Comprehensibility Metrics (R2 — LLM-backed)

Deferred to Release 2; included here for catalog completeness. All values cache on verdict key per D6.

### 4.1 Identifier Quality (heuristic; R1)

- **Identifier:** `identifier_quality`
- **Family:** comprehensibility
- **Unit:** function
- **Formula:** heuristic only in R1:

  ```
  meaningful = identifiers with:
    - length ≥ 3
    - not in stopword list (i, j, k, x, tmp, foo, bar, ...)
    - not single-letter except loop counters in tight scope, math
  total = all identifiers
  quality = meaningful / max(total, 1)
  ```

- **Inputs:** AST.
- **Output:** float in [0, 1].
- **Calibration:** absolute ≤ 0.6 concern. Distribution: flag p10.
- **Confidence / reliability:** low individually — heuristic.
- **Reporting surface:** Detail view; contributing signal.
- **Graceful degradation:** none needed.
- **Minimum sample size:** 50 functions.
- **Default suppressions:** tests (test fixtures often use short names), generated.
- **Pitfalls:** idiomatic tight-loop code scores low without real problem.
- **Release:** R1 (heuristic) → R2 (LLM-augmented refinement).

### 4.2 LLM Perplexity Proxy

- **Identifier:** `lm_perplexity`
- **Family:** comprehensibility
- **Unit:** function
- **Formula:** average per-token log-probability of function body under a code-trained language model:

  ```
  perplexity = exp(- (1/N) × Σ log P(token_i | context))
  ```

- **Inputs:** function body + LLM with logprob access.
- **Output:** float ≥ 1.
- **Calibration:** distribution-only — flag p95 within codebase. Absolute values vary by model.
- **Confidence / reliability:** medium — strong research basis (Hindle et al., naturalness of software), but model-bias applies.
- **Reporting surface:** Detail view; front-page in comprehensibility axis.
- **Graceful degradation:** when LLM backend unavailable (R1 default, or R2+ with `llm_backend: disabled`), return `unavailable` with no value.
- **Minimum sample size:** 100 functions for meaningful distribution.
- **Default suppressions:** tests (boilerplate skews distribution), generated.
- **Pitfalls:** domain-specific code (DSP, low-level systems) shows high perplexity without genuine readability problem.
- **Release:** R2.

### 4.3 Name-Body Semantic Drift

- **Identifier:** `name_body_drift`
- **Family:** comprehensibility
- **Unit:** function
- **Formula:**

  ```
  generated_name = LLM("Suggest a name for this function: {body}")
  drift = 1 − cosine(embed(actual_name), embed(generated_name))
  ```

- **Inputs:** name + body + LLM + embedding model.
- **Output:** float in [0, 1].
- **Calibration:** absolute ≥ 0.5 = significant divergence. Distribution: flag p90.
- **Confidence / reliability:** medium — LLM may suggest stylistically different name without genuine semantic mismatch.
- **Reporting surface:** Detail view; escalation signal for R2 Triage.
- **Graceful degradation:** when LLM unavailable, `unavailable`.
- **Minimum sample size:** 100 functions.
- **Default suppressions:** tests, generated, trivial accessors (auto-generated getters/setters).
- **Pitfalls:** Triage stage should adjudicate rather than treating as confirmed.
- **Release:** R2.

### 4.4 Summary Difficulty

- **Identifier:** `summary_difficulty`
- **Family:** comprehensibility
- **Unit:** function
- **Formula:** R2 Triage LLM is prompted: "Write a one-sentence summary of this function. If you cannot, explain why." Output classified:

  ```
  - clear: confident, specific summary
  - vague: summary produced but generic
  - failed: declined or visibly hedged
  ```

- **Inputs:** function source + LLM.
- **Output:** enum + free-text reasoning.
- **Calibration:** `failed` is strong signal; `vague` accumulates as evidence; `clear` is baseline.
- **Confidence / reliability:** medium — prompt-dependent; classification must be itself model-judged with structured rubric.
- **Reporting surface:** Front page (comprehensibility axis) when `failed`. **Most direct "can a human read this?" signal in the catalog.**
- **Graceful degradation:** when LLM unavailable, `unavailable`.
- **Minimum sample size:** no minimum — per-function signal.
- **Default suppressions:** tests, generated.
- **Pitfalls:** prompt design matters a lot. Validate classification rubric during R2 development.
- **Release:** R2.

### 4.5 Context Required

- **Identifier:** `context_required`
- **Family:** comprehensibility
- **Unit:** function
- **Formula:**

  ```
  non_local_refs = identifiers referenced in body NOT defined in:
    - function's own scope
    - parameter list
    - immediate enclosing class
    - language builtins
  context_required = |non_local_refs|
  ```

- **Inputs:** AST + scope analysis.
- **Output:** integer ≥ 0.
- **Calibration:** absolute > 15 = high contextual load. Distribution: flag p90.
- **Confidence / reliability:** high for statically-typed languages; medium for dynamic (Python, JS without types).
- **Reporting surface:** Detail view.
- **Graceful degradation:** when scope analysis incomplete, `confidence = medium`.
- **Minimum sample size:** 50 functions.
- **Default suppressions:** tests.
- **Pitfalls:** import-heavy code inflates without real cognitive cost. Distinguish stdlib / framework refs from project-internal in reporting.
- **Release:** R1 (the structural version, no LLM needed).

---

## 5. Temporal Metrics (R1)

All require git history. Computed via `pydriller` or `gix` binding over a configurable window (default 90 days).

### 5.1 Change Frequency

- **Identifier:** `change_frequency`
- **Family:** temporal
- **Unit:** file
- **Formula:** `commits_touching_file_in_window / window_days`.
- **Inputs:** git log.
- **Output:** float ≥ 0 (commits per day).
- **Calibration:** distribution-only. Combined with complexity for `attention_priority`.
- **Confidence / reliability:** high when git history is available.
- **Reporting surface:** Detail view; composite input.
- **Graceful degradation:** no `.git` → `unavailable`, reports show "—".
- **Minimum sample size:** 30 days of history for meaningful rate.
- **Default suppressions:** tests (test-file churn is noisy), migrations, generated.
- **Release:** R1.

### 5.2 Bug-Fix Density

- **Identifier:** `bug_fix_density`
- **Family:** temporal
- **Unit:** file
- **Formula:**

  ```
  bug_fix_commits = commits matching:
    /\b(fix|bug|hotfix|patch|defect|issue|broken|regress|crash|wrong|incorrect)\b/i
    OR linking to a tracker issue tagged as bug
  density = bug_fix_commits / max(total_commits_in_window, 1)
  ```

- **Inputs:** git log + optional issue tracker integration.
- **Output:** float in [0, 1].
- **Calibration:** distribution-only. High density × high complexity = highest priority.
- **Confidence / reliability:** medium — commit-message heuristics imperfect. Higher with issue tracker integration.
- **Reporting surface:** Detail view; composite input.
- **Graceful degradation:** no `.git` → `unavailable`.
- **Minimum sample size:** 30 commits in window for meaningful density.
- **Default suppressions:** tests, migrations.
- **Pitfalls:** teams with disciplined trackers should use the integration path. Pattern configurable per-project.
- **Release:** R1.

### 5.3 Author Count (Bus Factor Proxy)

- **Identifier:** `author_count`
- **Family:** temporal
- **Unit:** file
- **Formula:** distinct authors with ≥ N commits in window. Default N = 2.
- **Inputs:** git log.
- **Output:** integer ≥ 0.
- **Calibration:** absolute = 1 with high complexity = bus-factor risk.
- **Confidence / reliability:** medium — same author under multiple emails produces false positives.
- **Reporting surface:** Detail view.
- **Graceful degradation:** no `.git` → `unavailable`.
- **Minimum sample size:** 20 commits per file.
- **Default suppressions:** tests, migrations, generated.
- **Release:** R1.

### 5.4 Stability Tier

- **Identifier:** `stability_tier`
- **Family:** temporal
- **Unit:** artifact (via `observation_artifacts`)
- **Formula:**

  ```
  if first_seen and last_seen are same run:
    'volatile'
  elif seen ≥ N runs unchanged AND last git modification > M days ago:
    'dormant'
  elif seen ≥ N runs unchanged:
    'settled'
  else:
    'volatile'
  ```

  Defaults: N = 3, M = 90 days.
- **Inputs:** artifact occurrence history + git mtime.
- **Output:** enum.
- **Use:** dormant artifacts skip full re-analysis — primary R1 perf optimization.
- **Confidence / reliability:** high when git history available; medium otherwise.
- **Reporting surface:** Detail view; not ranked.
- **Graceful degradation:** without git, tier is `settled` or `volatile` based purely on run history.
- **Minimum sample size:** no minimum.
- **Default suppressions:** none (applies to all artifacts).
- **Release:** R1.

---

## 6. Composite and Ranking Metrics (R1)

### 6.1 Attention Priority

- **Identifier:** `attention_priority`
- **Family:** composite
- **Unit:** function or file
- **Formula:**

  ```
  severity = z-score of unit's max metric across:
    cognitive_complexity, npath, henry_kafura,
    lcom_hs (if class), distance_from_main_sequence (if module)
  centrality = log(1 + afferent_coupling) for modules
                log(1 + fan_in) for functions
  volatility = log(1 + change_frequency) × (1 + bug_fix_density)
  attention_priority = severity × (1 + 0.5 × centrality) × (1 + volatility)
                       × confidence_factor
  ```

  Z-scores within codebase. `confidence_factor` = 1.0 | 0.75 | 0.5 for high/medium/low.
- **Inputs:** all of the above.
- **Output:** float, used only for ranking.
- **Confidence / reliability:** inherits from component metrics.
- **Reporting surface:** **Front page — the single sort order.**
- **Graceful degradation:** when component metrics unavailable, composite computes over whatever is available with note.
- **Minimum sample size:** 50 artifacts for meaningful z-scores.
- **Default suppressions:** inherits from components.
- **Pitfalls:** weights are configurable in `.instinct/config.yaml`. Tuned to: complex code matters; complex code with many callers matters more; complex code that changes often matters most.
- **Release:** R1.

### 6.2 Multi-Axis Profile

- **Identifier:** `profile`
- **Family:** composite
- **Unit:** codebase
- **Formula:** for each axis, p50/p90/p95/p99 of constituent metrics, normalized [0, 1] by language norms or absolute thresholds.

  Axes:
  - **Per-unit cognitive load** — cognitive_complexity, npath, max_nesting_depth, statement_count
  - **System fragmentation** — trivial_delegation_ratio, median_function_length, chain_depth_to_effect, module_locality
  - **Coupling health** — distance_from_main_sequence, henry_kafura, lcom_hs
  - **Comprehensibility** (R2+) — lm_perplexity, name_body_drift, summary_difficulty, context_required
  - **Architectural drift** — distance_from_main_sequence aggregated, A/I bivariate plot
  - **Temporal pressure** — change_frequency, bug_fix_density weighted against complexity
- **Output:** structured JSON; radar chart in HTML.
- **Confidence / reliability:** inherits.
- **Reporting surface:** **Front page.**
- **Graceful degradation:** axes with insufficient data report `insufficient_data` rather than zero.
- **Minimum sample size:** axis-dependent; min 50 artifacts for per-unit axes, 5 modules for module-level axes.
- **Default suppressions:** inherits.
- **Release:** R1.

---

## 7. Pattern Metrics (R3+)

Included for completeness. Emerge from curator and pattern store.

### 7.1 Pattern Match Confidence

- **Identifier:** `pattern_match_confidence`
- **Family:** pattern
- **Unit:** function
- **Formula:**

  ```
  structural_sim = MinHash Jaccard between artifact AST subtree fingerprints
                   and pattern signature
  semantic_sim = cosine(artifact_embedding, pattern_embedding)
  confidence = 0.6 × structural_sim + 0.4 × semantic_sim
  ```

  Weights tunable per scope: Project scope weights structural higher; Global scope weights semantic higher.
- **Inputs:** artifact + pattern from PatternStore.
- **Output:** float in [0, 1].
- **Reporting surface:** Detail view; escalation input to deviation vector.
- **Release:** R3.

### 7.2 Pattern Deviation Vector

- **Identifier:** `pattern_deviation`
- **Family:** pattern
- **Unit:** function (relative to matched pattern)
- **Formula:** structured diff between matched pattern's expected metric profile and actual artifact's metrics. Per-axis z-scores against pattern's exemplar distribution.
- **Output:** structured object.
- **Reporting surface:** Front page (R3+); drives mechanical and structural suggestions.
- **Release:** R3.

### 7.3 Cluster Cohesion

- **Identifier:** `cluster_cohesion`
- **Family:** pattern
- **Unit:** cluster
- **Formula:** Davies-Bouldin index over embedding clusters (HDBSCAN).
- **Reporting surface:** Curator only.
- **Release:** R3.

---

## 8. Per-Language Calibration

YAML tables under `core/` load at startup:

| File | Purpose |
|---|---|
| `core/cognitive_rules/<lang>.yaml` | Increment table for cognitive complexity per AST node type. |
| `core/triviality_rules/<lang>.yaml` | Patterns classifying a function body as trivial delegation. |
| `core/effect_sources/<lang>.yaml` | Known I/O, mutation, FFI patterns for chain-depth-to-effect. |
| `core/abstractness_rules/<lang>.yaml` | What counts as "abstract type" per language. |
| `core/stopwords/<lang>.yaml` | Identifier stopwords for `identifier_quality`. |
| `core/distribution_norms/<lang>.yaml` | (Optional) precomputed distributions from open-source corpora as fallback when codebase is too small. |

R1 ships rules for: Rust, C# (.NET), TypeScript, Python. Adding a language = YAML plus tree-sitter grammar; no metric core changes.

---

## 9. Implementation Notes

### 9.1 Compute once, read many

Metrics share inputs (AST, CFG, call graph). The `analyze/` pipeline computes shared inputs once per file and passes via `AnalysisContext`. No metric re-parses source.

### 9.2 Parallelism

File-level via `ProcessPoolExecutor`. Metrics within a file are sequential (cheap relative to parsing and graph construction).

### 9.3 Determinism

All metrics MUST be deterministic given the same inputs. LLM-backed metrics (R2+) achieve determinism via:
- Pinned model + prompt + temperature = 0
- Cache on full verdict key (D6)
- Cache hits treated as authoritative

### 9.4 Provenance

Every metric value stored with:
- `metric_id` — catalog identifier
- `metric_version` — incremented when formula changes
- `tool_version` — overall semver
- `confidence` — high/medium/low
- `inputs_hash` — hash of inputs used

Lets the system distinguish "metric value changed because code changed" from "metric value changed because formula changed."

### 9.5 Distribution calibration safety

Minimum sample sizes in each entry. When a codebase is below the minimum, distribution-relative thresholds are suppressed and only absolute thresholds apply, with a note in the report ("codebase too small for calibrated thresholds; absolute values shown").

### 9.6 Default suppression sets

Applied during file discovery before any metric computation:

| Pattern | Reason |
|---|---|
| `**/node_modules/**` | vendor |
| `**/target/**` | Rust build |
| `**/dist/**`, `**/build/**` | output |
| `**/.venv/**`, `**/venv/**` | Python venvs |
| `**/.next/**` | Next.js build |
| `**/migrations/**` | generated or linear |
| `**/*.generated.*` | generated code |
| `**/*.min.js` | minified |
| Files with `@generated` or `// <auto-generated>` markers | generated |
| Files > `max_file_size_mb` (default 1 MB) | likely generated |

Tests are NOT suppressed by default; they're analyzed but separately reported. Metrics that explicitly exclude tests are documented per-metric above.

### 9.7 Testing

Per metric:
- Unit tests with hand-crafted AST fixtures, expected values
- Snapshot tests against `tests/corpus/` reference repos
- Regression tests for historical bugs (e.g., "LCOM-HS returned NaN on single-method classes — never again")

---

## 10. Known Gaps (Future Consideration)

Metrics deliberately not included but worth revisiting:

- **Halstead suite** (volume, difficulty, effort) — classical but empirical validity weak. Skipping.
- **Maintainability Index** — composite that compresses information; multi-axis profile does the same job better.
- **Chidamber-Kemerer DIT, NOC, RFC** — valuable for deep OO codebases. Add in R2 if Baker Street's .NET surface justifies.
- **MOOD metrics** — system-level OO encapsulation/inheritance/polymorphism. Defer.
- **Semantic duplication (beyond textual clone detection)** — falls naturally out of R3 pattern clustering; not a separate metric.

---

## 11. Summary

R1 (MVP) ships a metric core covering control-flow, ravioli/fragmentation, coupling/cohesion, temporal, and composite ranking — producing profiles and target lists with no LLM dependency. R2 adds the comprehensibility axis. R3+ adds pattern-relative metrics.

Every metric in this catalog has a formula, inputs, calibration approach, confidence profile, reporting surface, graceful-degradation behavior, minimum sample size, default suppressions, and known pitfalls. New metrics added later follow the same shape.
