# EchoFlow development docs 🧪🔧

This area explains how EchoFlow turns architecture claims into failing tests instead of hoping the screenshots are persuasive.

## Start here

| Page | What it is for |
|---|---|
| [Desktop development prerequisites](desktop-development.md) | browser mock, native Tauri, real processing, Node/Rust/Python/native prerequisites |
| [Desktop source-build troubleshooting](troubleshooting.md) | symptom-first recovery for Tauri/Python/WebKitGTK/Wayland/port failures and safe cleanup |
| [Desktop themes and accessibility](desktop-accessibility.md) | semantic theme contract, eight skins, contrast/native-control rules, adding a skin safely |
| [Frontend testing strategy](frontend-testing.md) | frontend/backend test ownership, Processing/Library/Research/transcript-tools coverage, and why Stryker is not currently a routine tool |
| [Testing and regression bisection](testing-and-bisect.md) | repository-wide test strategy, colocation, mutation anticipation, deterministic bisect oracles |
| [Semantic retrieval qualification](semantic-retrieval-testing.md) | property, negative, boundary, integration, and mutation coverage for lexical/semantic/hybrid retrieval |
| [Empirical benchmarking and calibration](benchmarking.md) | measuring real execution without turning hosted CI timing into folklore |
| [Documentation style](../documentation-style.md) | current-truth rules, Mermaid portability/accessibility, editorial voice |

## Current PR quality gate

Cheap checks stop expensive jobs where possible. Normal pull-request qualification includes:

- locked Python dependency verification and runtime dependency audit;
- Mermaid documentation portability verification;
- Ruff lint/format/security;
- strict mypy;
- Vulture dead-code checks;
- Radon complexity/maintainability reporting;
- pytest branch coverage with a 90% aggregate gate;
- frontend locked dependency install and high-severity audit;
- Tauri JavaScript/Rust version-family consistency;
- strict TypeScript and production Vite build;
- rejection of `dangerouslySetInnerHTML` in the frontend;
- native `cargo check --locked`;
- Playwright interaction/negative/boundary tests across Intake, Processing, Library, transcript tools, and Research;
- axe accessibility coverage;
- an eight-skin WCAG-oriented contrast/native-control matrix;
- package build plus clean-wheel installation; and
- Linux/macOS/Windows platform smoke.

Do not turn a current test count into a health metric. Counts go stale; behavioral gates are the evidence.

## Quality philosophy

EchoFlow has decision-heavy application code: resource admission, model custody, canonical-generation verification, resume, cleanup ordering, search filtering/rank composition, evidence anchoring, transactional user state, projection recovery, speaker authority, derived publication, desktop allowlists, and privacy boundaries.

Branch coverage alone cannot prove those decisions are right. Use several independent oracles:

1. named behavioral examples;
2. negative and boundary cases;
3. Hypothesis/property tests for invariants;
4. integration/package tests;
5. static and coverage gates;
6. targeted mutation qualification;
7. browser interaction/accessibility; and
8. cross-platform plus representative-device evidence.

## Test the authority, not a copy of it

Useful examples include:

- a stale `(document_id, canonical_sha256)` cannot rename a speaker in a newer generation;
- a tampered canonical transcript is rejected before transcript details or publication are trusted;
- an unknown transcript-tools method cannot reach an application service;
- rebuilding DuckDB does not erase human speaker names or notes;
- an empty research evidence scope returns no transcript results rather than widening to the corpus;
- a desktop evidence/transcript-tools DTO omits canonical/source filesystem paths;
- every registered skin satisfies the same semantic-token contrast contract; and
- hostile transcript HTML remains inert text in the WebView.

Avoid tests that assign X and assert X equals X, or frontend mocks that independently reimplement the business rule supposedly being tested.

## Colocation and mutation

Tests live beside the capability whose contract they protect. Shared fixtures stay at the narrowest useful scope. Built distributions exclude test packages.

Hypothesis is preferred for generated invariants and sequences. Explicit fixtures/builders are preferred when hashes, identities, ordering, and evidence relationships are load-bearing.

Poodle mutation workflows are targeted/manual qualification. They are not routine PR gates because mutating the complete Python tree on every pull request would add substantial latency while weakening signal. Transcript retrieval/semantic behavior and transcript-tools generation/speaker/publication behavior have dedicated mutation workflows.

The frontend currently does not use Stryker. That is deliberate: decision-heavy product rules belong in Python, while React primarily owns presentation and interaction. See [Frontend testing strategy](frontend-testing.md) for the criteria that would justify adding a JavaScript mutation layer later.

## Frontend contract

A new interactive desktop slice should normally include semantic-role/keyboard assertions, an axe pass, positive behavior, at least one meaningful negative/boundary case, and path/capability assertions when sensitive local state is involved.

Theme-aware components inherit the shared registry-driven contrast matrix. Do not create a private palette test for every component.

## Performance qualification

Product measurements should focus on:

- incremental library refresh versus full rebuild;
- warm/cold unified discovery;
- constrained lexical/semantic/hybrid retrieval;
- research projection catch-up/rebuild;
- realistic multi-recording startup and disk cost;
- Library and Research responsiveness;
- Processing responsiveness while jobs are active;
- transcript-tools inspection/presentation on large canonical files; and
- local media seek/playback once native playback lands.

For transcript tools, canonical-byte verification is intentionally retained at the backend boundary. If profiling demonstrates material UI latency, optimize with a generation-keyed verified backend reader/cache and explicit invalidation, not a React cache that weakens custody.

Representative 8/16 GB consumer machines, Apple Silicon, dGPU laptops, and larger workstations should calibrate resource policy. Hosted runner timing is supporting evidence, not hardware qualification.

## Documentation regressions

Mermaid source remains directly visible and a static SVG may exist only as a secondary fallback. Do not hide Mermaid behind a fallback or strip the established palette. `scripts/verify_mermaid_docs.py` protects the portable source/fallback contract.

Development docs should explain enough of the rule that a new contributor understands why a test exists before reading the mutant it is meant to kill.
