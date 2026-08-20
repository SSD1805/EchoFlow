# EchoFlow development docs 🧪🔧

This is where the project stops saying “EchoFlow tries very hard not to melt your laptop”
and starts showing **how we prove that claim is not merely aspirational prose**.

The development docs are for maintainers, contributors, and anyone who enjoys turning
subtle bad decisions into failing tests.

## Start here

| Page | What it is for |
|---|---|
| [Desktop development prerequisites](desktop-development.md) | Node/npm locality, Rust/Cargo, native Tauri prerequisites, real-host versus browser development, and cleanup |
| [Testing and regression bisection](testing-and-bisect.md) | general test strategy, colocation rules, mutation anticipation, and deterministic bisect oracles |
| [Semantic retrieval qualification](semantic-retrieval-testing.md) | property, negative, boundary, integration, and mutation coverage for lexical/semantic/hybrid search decisions |
| [Empirical benchmarking and calibration](benchmarking.md) | measuring real execution without turning hosted CI timing into folklore |
| [Documentation style](../documentation-style.md) | current-truth rules, Mermaid palette, accessibility, and editorial voice |

## The current quality gate

Normal pull-request qualification is staged so cheap failures stop expensive native/media
jobs. It includes:

- locked Python dependency verification and audit;
- Mermaid visibility/syntax/palette verification before expensive runners;
- Ruff lint/format/security rules;
- strict mypy;
- Vulture dead-code checks;
- Radon complexity/maintainability reporting;
- pytest with branch coverage and a **90% aggregate gate**;
- locked frontend dependency installation and audit;
- TypeScript checking plus a production Vite build;
- rejection of raw-HTML rendering escape hatches in the frontend;
- a native Tauri/Rust compile smoke so browser-only builds cannot hide missing native assets or host errors;
- Playwright interaction tests plus axe accessibility checks;
- package build verification and clean-wheel installation; and
- Linux, macOS, and Windows CI/platform smoke.

Do not memorialize the current total test count as a project-health metric. It becomes
stale with the next useful test and says less than the behavioral gates above. Dated PR or
audit records may preserve historical counts when they are evidence about that event.

## The quality philosophy

EchoFlow has decision-heavy code: resource admission, model custody, stale-state
rejection, resume, cleanup ordering, search filtering, rank composition, evidence
anchoring, transactional user state, projection recovery, desktop capability boundaries,
and privacy rules.

Line/branch coverage alone cannot prove those decisions are correct.

```mermaid
flowchart LR
    A[Named behavioral tests] --> B[Negative and boundary cases]
    B --> C[Property tests]
    C --> D[Integration and package tests]
    D --> E[Branch coverage and static gates]
    E --> F[Targeted mutation qualification]
    F --> G[Frontend interaction and a11y]
    G --> H[Cross-platform package evidence]
    H --> I[Representative real-device evidence]

    classDef inspect fill:#D8EEFF,stroke:#2E617B,stroke-width:2px,color:#12222A
    classDef process fill:#E8D9FF,stroke:#68469B,stroke-width:2px,color:#1F1630
    classDef success fill:#DDF5E3,stroke:#347A46,stroke-width:2px,color:#142719
    classDef evidence fill:#FFF0B8,stroke:#8A6B18,stroke-width:2px,color:#2C260F

    class A,B,C inspect
    class D,E,F process
    class G success
    class H,I evidence
```

Text fallback: named behavior, negative/boundary/property coverage, integration/static
gates, targeted mutation testing, frontend accessibility, cross-platform packages, and
representative-device evidence protect different classes of failure.

## No tautologies

A test should prove an observable contract, not restate the implementation.

Useful tests include:

- a failed SQLite mutation leaves neither the user row nor journal event committed;
- replaying projection changes converges to the same DuckDB state;
- an old canonical generation does not match a new segment that reuses the same friendly
  segment ID;
- an empty research evidence scope returns zero transcript results rather than widening
  to the corpus;
- a desktop evidence DTO never exposes canonical/source filesystem paths even though the
  backend authority knows them; and
- an unexpected internal CLI/bridge error is masked while a known public error preserves
  its intended message/code.

Avoid tests that simply assign X and assert X equals X, mock-only call counting where no
behavioral contract depends on the call, or assertions that duplicate a constant from the
same function under test.

## Colocation

Tests live with the capability whose contract they protect. Shared fixtures stay at the
narrowest useful scope. Built distributions exclude test packages.

Hypothesis is preferred for invariants and generated sequences. Explicit fixtures/builders
are preferred where IDs, hashes, sequences, and evidence relationships are load-bearing.

Frontend tests live beside the frontend harness. A new interactive desktop slice should
normally include keyboard behavior, semantic-role assertions, path/capability boundary
checks where relevant, and an axe pass in the same tranche.

## Performance qualification from here

Current performance work should target product workloads:

- incremental transcript-library refresh versus full rebuild;
- warm/cold unified discovery;
- tag/collection/note-text constrained lexical and semantic search;
- one-edit and large-batch research projection catch-up;
- full research projection rebuild;
- realistic multi-recording corpus startup and disk cost;
- desktop Library responsiveness;
- desktop Research filtering, mutation, and evidence-return responsiveness; and
- local media seek/playback responsiveness once the Tauri media capability lands.

Representative 8/16 GB consumer machines, Apple Silicon, discrete-GPU laptops, and larger
workstations should calibrate policy. Hosted runner timing remains supporting evidence,
not a substitute for hardware qualification.

## Mermaid regression discipline

GitHub's own documentation accepts Mermaid inside an exact `mermaid` fence and uses the
classic `graph TD;` form. EchoFlow also uses `flowchart`. **Do not encode a false rule that
one spelling is required.**

The August 2026 regression had two concrete presentation failures:

1. a one-shot normalizer stripped `classDef`/class assignments and removed EchoFlow's
   established palette; and
2. a later fallback experiment made hand-maintained SVGs the primary visible diagrams and
   hid Mermaid inside collapsed `<details>`. Those SVGs used `currentColor`, which is a bad
   dependency for an externally loaded image expected to remain legible across GitHub
   themes.

The verifier therefore protects direct visible Mermaid fences, simple GitHub-supported
`graph`/`flowchart` syntax, approved colors when `classDef` is used, and the absence of the
old primary-SVG/hide-Mermaid pattern.

A separately maintained static SVG fallback is acceptable only as a **secondary fallback**
for rich-rendering outages, with deliberate fixed light/dark-safe colors and accessible
text. It must never replace or hide the Mermaid source.

## Documentation voice

Development docs use the medium-personality register from
[documentation-style.md](../documentation-style.md): exact commands and contracts, but
enough explanation that a new contributor can understand why a test exists before reading
the mutant it is trying to kill.

💃 Happy breaking.
