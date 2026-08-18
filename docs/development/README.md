# EchoFlow development docs 🧪🔧

This is where the project stops saying “EchoFlow tries very hard not to melt your
laptop” and starts showing **how we prove that claim is not merely aspirational prose**.

The development docs are for maintainers, contributors, and anyone who enjoys turning
subtle bad decisions into failing tests.

## Start here

| Page | What it is for |
|---|---|
| [Testing and regression bisection](testing-and-bisect.md) | the general test strategy, colocation rules, mutation anticipation, and deterministic bisect oracles |
| [Semantic retrieval qualification](semantic-retrieval-testing.md) | property, negative, boundary, integration, and mutation coverage for the transcript-library V2 search decisions |
| [Empirical benchmarking and calibration](benchmarking.md) | how EchoFlow measures real execution without turning hosted CI timing into folklore |

## The quality philosophy

EchoFlow has a lot of decision-heavy code: resource admission, model custody, stale-state
rejection, resume, cleanup ordering, search filtering, rank composition, and privacy
boundaries.

Line coverage alone cannot prove those decisions are correct.

The preferred ladder is:

```mermaid
flowchart LR
    A[Named unit tests] --> B[Negative + boundary cases]
    B --> C[Property tests]
    C --> D[Package / integration tests]
    D --> E[Branch coverage + static gates]
    E --> F[Targeted mutation qualification]
    F --> G[Cross-platform / package evidence]
    G --> H[Representative real-device evidence]

    classDef fast fill:#D8EEFF,stroke:#2E617B,stroke-width:2px,color:#12222A
    classDef deep fill:#E8D9FF,stroke:#68469B,stroke-width:2px,color:#1F1630
    classDef evidence fill:#DDF5E3,stroke:#347A46,stroke-width:2px,color:#142719

    class A,B,C,D fast
    class E,F,G deep
    class H evidence
```

Each layer answers a different question. Mutation testing does not replace ordinary
boundary tests. Hosted CI does not replace physical-device calibration. Benchmarks do
not silently rewrite planner policy.

🦝 **If a comparator changes from `<` to `<=`, we would like a test to notice before the
raccoon notices in production.**

## Colocation

Tests live with the capability whose contract they protect. Shared fixtures stay at the
narrowest useful scope. Built distributions exclude test packages.

That convention makes source-to-test navigation boring, which is exactly what we want.

## Documentation voice

Development docs use the medium-personality register from
[documentation-style.md](../documentation-style.md): exact commands and contracts, but
with enough explanation that a new contributor can understand why a test exists before
reading the mutant it is trying to kill.

💃 Happy breaking.