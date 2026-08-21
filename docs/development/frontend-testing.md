# Frontend testing strategy

EchoFlow tests the desktop according to its architecture: React proves presentation and human interaction; Python proves application, evidence, custody, and resource decisions; Rust proves narrow native capability wiring and process lifetime.

The goal is not equal tool counts in every language. The goal is to place each behavioral oracle beside the authority it can actually judge.

## Frontend layers

### TypeScript and production build

Strict TypeScript, `noUncheckedIndexedAccess`, and `exactOptionalPropertyTypes` catch DTO drift and unsafe optional-state assumptions. The production Vite build catches bundling/import errors that a type-only pass can miss.

### Pure presentation contracts

`frontend/tests/frontend-contracts.spec.ts` uses the Playwright test runner without a page fixture for deterministic presentation helpers and registries. Current examples cover:

- unique/stable theme IDs and labels;
- registered light/dark scheme metadata;
- rejection of theme lookalikes; and
- evidence-time formatting at negative, minute, and hour boundaries.

These tests are deliberately small. A pure frontend helper belongs here only when it is genuinely presentation logic.

### Browser interaction

Playwright exercises every primary desktop surface:

- Intake and remembered locations;
- Processing readiness, preflight, supervised start, resume, and fresh retry;
- Library search and verified evidence navigation;
- Transcript and speaker tools;
- Research notes, filtering, saved searches, typed search, and anchor maintenance; and
- development-mode behavior.

Tests use semantic roles and accessible names where possible. A selector that depends on implementation-only class names should have a specific reason.

### Accessibility and themes

Axe runs on representative rendered workflows. Theme qualification iterates the registry so every skin receives the same text/control/focus/selection contrast checks and browser `color-scheme` assertion.

Pride has a dedicated assertion that its rainbow remains decorative. Monochrome has a dedicated assertion that its semantic palette is actually grayscale. Neither special test replaces the shared contrast matrix.

### Security-oriented browser assertions

Frontend tests explicitly check that:

- transcript/research strings containing HTML remain inert text;
- evidence and transcript-tool views do not expose canonical/source filesystem paths;
- speaker display labels do not erase anonymous evidence refs; and
- post-hoc publication reports safe filenames instead of rendering the selected destination path.

## Why there is no Stryker gate today

Stryker is useful when JavaScript/TypeScript contains decision-heavy pure logic whose tests should kill semantic mutations. EchoFlow deliberately keeps those decisions out of React.

The important mutants in the current transcript-tools tranche are questions such as:

- does a stale canonical digest get accepted?;
- can a label cross transcript generations?;
- can an unknown speaker ref be named?;
- does publication skip canonical verification?;
- can collision policy overwrite a file?; and
- can an unallowlisted desktop method execute?

Those decisions live in Python, so Poodle is the meaningful mutation tool for them. Installing Stryker solely to mutate JSX branches would increase dependency/runtime surface without improving evidence-policy assurance.

This is not a permanent ban. Add a frontend mutation layer when all of the following are true:

1. decision-heavy pure frontend modules actually exist;
2. those decisions are correctly presentation-owned rather than leaked backend policy;
3. ordinary tests give the mutant runner stable deterministic oracles; and
4. mutation runtime is targeted rather than turning every pull request into a full-tree search.

## Backend mutation qualification

Poodle workflows are manual/targeted by design. Routine PR CI already runs static analysis, branch coverage, package checks, browser tests, native compilation, dependency audit, and platform smoke. Full mutation runs are qualification jobs for changed decision-heavy surfaces, not a mandatory tax on every typo.

Transcript tools have a dedicated mutation workflow covering generation, speaker, and publication decisions. The broader transcript-library mutation workflow continues to cover retrieval/semantic decisions.

## Adding a desktop feature

A new interactive slice should normally ship with:

- typed frontend request/response contracts;
- positive interaction coverage;
- at least one meaningful negative/boundary case;
- keyboard/semantic-role coverage where interactive;
- axe on the rendered slice;
- explicit path/capability assertions if sensitive local state is involved; and
- backend property/mutation tests when the feature changes decision-heavy application policy.

If writing the browser test requires recreating a backend rule in the mock or component, inspect the architecture first. The better fix may be moving that rule back behind the Python service boundary.
