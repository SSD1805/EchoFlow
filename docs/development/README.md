# EchoFlow development docs 🧪🔧

This is where the project stops saying “EchoFlow tries very hard not to melt your laptop”
and starts showing **how we prove that claim is not merely aspirational prose**.

The development docs are for maintainers, contributors, and anyone who enjoys turning
subtle bad decisions into failing tests.

## Start here

| Page | What it is for |
|---|---|
| [Testing and regression bisection](testing-and-bisect.md) | general test strategy, colocation rules, mutation anticipation, and deterministic bisect oracles |
| [Semantic retrieval qualification](semantic-retrieval-testing.md) | property, negative, boundary, integration, and mutation coverage for lexical/semantic/hybrid search decisions |
| [Empirical benchmarking and calibration](benchmarking.md) | measuring real execution without turning hosted CI timing into folklore |
| [Documentation style](../documentation-style.md) | current-truth rules, Mermaid dialect/palette, accessibility, and editorial voice |

## The current quality gate

Normal pull-request qualification is staged so cheap failures stop expensive native/media
jobs. It includes:

- locked Python dependency verification and audit;
- Mermaid syntax/palette verification before expensive runners;
- Ruff lint/format/security rules;
- strict mypy;
- Vulture dead-code checks;
- Radon complexity/maintainability reporting;
- pytest with branch coverage and a **90% aggregate gate**;
- locked frontend dependency installation and audit;
- TypeScript checking plus a production Vite build;
- rejection of raw-HTML rendering escape hatches in the frontend;
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

Each layer answers a different question. Mutation testing does not replace ordinary
boundary tests. Playwright does not prove platform assistive-technology behavior by
itself. Hosted CI does not replace physical-device calibration. Benchmarks do not silently
rewrite planner policy.

## No tautologies

A test should prove an observable contract, not restate the implementation.

Useful tests have a meaningful precondition, perform a real operation, and assert a
postcondition that could fail if the implementation were wrong. Examples include:

- a failed SQLite mutation leaves neither the user row nor its journal event committed;
- replaying the same projection changes converges to the same DuckDB state;
- an old canonical generation does not match a new segment that reuses the same friendly
  segment ID;
- an empty research evidence scope returns zero transcript results rather than widening
  to the whole corpus;
- a desktop research DTO never exposes canonical/source filesystem paths even though the
  backend authority knows them; and
- an unexpected internal CLI/bridge error is masked while a known public error preserves
  its intended message and error code.

Avoid tests of the form “assign X, assert X equals X,” mock-only call counting where no
behavioral contract depends on the call, or assertions that duplicate a constant from the
same function under test.

## Colocation

Tests live with the capability whose contract they protect. Shared fixtures stay at the
narrowest useful scope. Built distributions exclude test packages.

Hypothesis is preferred for invariants and generated sequences. Explicit fixtures/builders
are preferred where IDs, hashes, sequences, and evidence relationships are load-bearing.
Factory-style indirection should be introduced only if entity setup becomes genuinely
repetitive rather than because object factories are fashionable.

Frontend tests live beside the frontend test harness. A new interactive desktop slice
should normally include keyboard behavior, semantic-role assertions, path/capability
boundary checks where relevant, and an axe pass in the same tranche.

## Performance qualification from here

Current performance work should target product workloads rather than microbenchmarks for
their own sake:

- incremental transcript-library refresh versus full rebuild;
- warm/cold unified discovery;
- tag/collection/note-text constrained lexical and semantic search;
- one-edit and large-batch research projection catch-up;
- full research projection rebuild;
- realistic multi-recording corpus startup and disk cost;
- desktop Library/Research responsiveness on large local corpora; and
- local media seek/playback responsiveness once the Tauri media capability lands.

Representative 8/16 GB consumer machines, Apple Silicon, discrete-GPU laptops, and larger
workstations should calibrate policy. Hosted runner timing remains supporting evidence,
not a substitute for hardware qualification.

## Mermaid regression discipline

Documentation diagrams are part of the developer contract now because a repository-wide
“normalization” once changed working `flowchart` diagrams to `graph ...;` and stripped the
established class palette.

The permanent verifier protects the known-good direct `flowchart` dialect and approved
EchoFlow colors. If a diagram change fails that gate, fix the diagram or deliberately
update the documented contract. Do not add a second hand-maintained monochrome SVG merely
to make CI quiet.

## Documentation voice

Development docs use the medium-personality register from
[documentation-style.md](../documentation-style.md): exact commands and contracts, but
with enough explanation that a new contributor can understand why a test exists before
reading the mutant it is trying to kill.

💃 Happy breaking.
