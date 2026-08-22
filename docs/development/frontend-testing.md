# Frontend testing strategy

Scholion tests the desktop according to its architecture: React proves presentation and human interaction; Python proves application, evidence, custody, resource, media-selection, and playback-authorization decisions; Rust proves narrow native capability wiring, process lifetime, and local media transport.

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
- Processing readiness, preflight, explicit embedded-track confirmation, supervised start, resume, and fresh retry;
- Library search and verified evidence navigation;
- verified local playback from current and preserved older evidence generations;
- Transcript and speaker tools;
- Research notes, filtering, saved searches, typed search, and anchor maintenance;
- Storage custody planning/application and private-retention previews;
- persistent and contextual in-app guidance; and
- development-mode behavior.

Playback browser qualification covers exact ranked and word-level coordinates, missing and changed sources, deliberate multi-audio refusal, audio/video presentation, keyboard preparation, and path non-disclosure. The browser mock does not reimplement source verification; it exposes already-decided backend outcomes so React tests can verify presentation of success/refusal states.

Processing has a separate multi-track presentation contract. Under the E2E multitrack fixture, Python-shaped mock data reports two embedded audio streams plus `audio_stream_selection_required=true`. The browser test proves that:

- both tracks and their bounded source-declared metadata are visible;
- neither track is silently treated as confirmed;
- **Start local transcription** remains disabled;
- selecting a track causes a new preflight request with that exact integer stream index;
- the resulting backend-bound plan becomes startable; and
- axe remains clean in the multi-track state.

The mock deliberately does not score microphones or choose a preferred track. That decision does not belong in React.

`frontend/tests/lifecycle.spec.ts` treats Storage as a presentation surface over the existing Python custody service. It proves that:

- canonical transcript removal is previewed before application and backend scope expansion is visible;
- source recording removal cannot even be previewed until the second user guard is enabled;
- source/canonical/private workspace paths do not enter the DOM;
- default retention shows only completed old work while optional incomplete retention exposes resumable interrupted state and a backend-provided resume-loss warning;
- applying a reviewed mock plan produces the expected presentation result; and
- Storage guidance plus an open destructive plan remain axe-clean.

The lifecycle mock may mirror DTO shape and deterministic backend outcomes for browser interaction. It must not become a second implementation of `LibraryCustodyService` policy. Scope expansion/provenance/retention/stale-token correctness are Python-test responsibilities.

`frontend/tests/in-app-help.spec.ts` treats guidance as an interaction/accessibility feature, not as backend policy. It proves that screen help follows the active workspace, overall help remains reachable, Escape closes a panel and restores focus, contextual Evidence/Playback/Transcript guidance is discoverable, sensitive paths do not appear, and axe stays clean while help is open. Lifecycle-specific help is additionally exercised from `lifecycle.spec.ts`.

Tests use semantic roles and accessible names where possible. A selector that depends on implementation-only class names should have a specific reason.

### Accessibility and themes

Axe runs on representative rendered workflows. Theme qualification iterates the registry so every skin receives the same text/control/focus/selection contrast checks and browser `color-scheme` assertion.

Pride has a dedicated assertion that its rainbow remains decorative. Monochrome has a dedicated assertion that its semantic palette is actually grayscale. Neither special test replaces the shared contrast matrix.

Native playback does not autoplay. Its prepare/re-verify action is keyboard reachable, the system media controls remain native semantic controls, and the surrounding presentation honors reduced-motion preferences.

In-app guidance is never hover-only. Triggers are ordinary buttons usable by keyboard, pointer, and touch. Expanded state is programmatic, Escape closes the panel, focus returns to the trigger, and every panel has an explicit close control. The responsive layout keeps the explanation reachable on narrow/touch viewports.

The multi-track chooser is a semantic fieldset with radio inputs, a visible legend, and inline explanatory text. It remains usable by keyboard and touch and uses the same semantic theme tokens as the rest of Processing Center.

Storage uses native checkboxes/select/number controls and plan-first buttons. Danger is conveyed through wording, structure, and semantic tokens rather than color alone. The second source guard is an ordinary labeled checkbox, not a hover affordance or modal-only trap.

### Security-oriented browser assertions

Frontend tests explicitly check that:

- transcript/research strings containing HTML remain inert text;
- evidence, transcript-tool, playback, lifecycle, and help views do not expose canonical/source/private-workspace filesystem paths;
- playback failure does not create a media element/session in the view;
- multi-track preflight receives only bounded display metadata and stream indices rather than a new path/media-inspection capability;
- lifecycle DTOs expose backend descriptions/counts/typed targets rather than destructive action paths;
- speaker display labels do not erase anonymous evidence refs; and
- post-hoc publication reports safe filenames instead of rendering the selected destination path.

Help content is static local presentation text. It must not become a remote-document embed, analytics surface, or a second executable copy of backend rules.

## Native Rust qualification

Rust owns the opened playback file handle, opaque session lifetime, and `scholion-media` byte-range transport. Those are not browser-policy questions, so they are covered beside the native implementation.

`cargo test --locked` runs in the normal `native-tauri` CI lane and covers:

- closed opaque session-token shape;
- rejection of path-like/unknown tokens;
- single-range parsing including open and suffix ranges;
- rejection of multipart/invalid ranges; and
- the 1 MiB response bound for local media transport.

`cargo check --locked` remains a separate compilation gate. The Storage tranche adds no new Rust policy object; native qualification compiles the fixed `lifecycle_request` command that maps to the fixed Python custody module.

## Why there is no Stryker gate today

Stryker is useful when JavaScript/TypeScript contains decision-heavy pure logic whose tests should kill semantic mutations. Scholion deliberately keeps those decisions out of React.

The important mutants in current desktop policy are questions such as:

- does a stale canonical digest get accepted?;
- can a label cross transcript generations?;
- can an unknown speaker ref be named?;
- does publication skip canonical verification?;
- can collision policy overwrite a file?;
- can playback proceed after the source bytes change?;
- can an ambiguous playback audio track be guessed?;
- does multi-track preflight require explicit user confirmation rather than treating a probe default as intent?;
- can a custody confirmation token authorize a changed plan?;
- can source deletion bypass its provenance/safety gate?; and
- can an unallowlisted desktop method execute?

Those decisions live in Python, so Poodle is the meaningful mutation tool for them. Installing Stryker solely to mutate JSX branches or static guidance copy would increase dependency/runtime surface without improving evidence-policy assurance.

This is not a permanent ban. Add a frontend mutation layer when all of the following are true:

1. decision-heavy pure frontend modules actually exist;
2. those decisions are correctly presentation-owned rather than leaked backend policy;
3. ordinary tests give the mutant runner stable deterministic oracles; and
4. mutation runtime is targeted rather than turning every pull request into a full-tree search.

## Backend mutation qualification

Poodle workflows are targeted by design. Routine PR CI already runs static analysis, branch coverage, package checks, browser tests, native compilation/tests, dependency audit, and platform smoke. Mutation should follow decision-heavy backend changes rather than becoming a mandatory tax on unrelated presentation or documentation edits.

Transcript tools retain a manually dispatchable mutation workflow covering generation, speaker, and publication decisions. Playback is stricter because it introduces a privileged evidence-to-native-media boundary: its workflow runs automatically on pull requests that change playback authorization, its trusted-host bridge, their dedicated tests, Poodle configuration, or the workflow itself. Its baseline also includes the hardened media-probe tests used by playback authorization, so an incompatible probe refactor fails before mutation begins. It remains manually dispatchable for explicit requalification. The broader transcript-library mutation workflow continues to cover retrieval/semantic decisions.

Multi-track display metadata and confirmation policy are qualified by the normal repository-wide Python coverage gate plus dedicated media/Processing tests. The Poodle target remains playback authorization/bridge policy rather than expanding mutation scope merely because playback shares the hardened probe.

The Storage/lifecycle UI tranche intentionally does **not** add a Poodle workflow because it does not modify `LibraryCustodyService` decision logic. The new `custody_bridge` is a closed serializer/adapter whose path stripping, validation, forwarding, and error masking are covered directly; the existing custody suite remains the oracle for scope expansion, stale confirmation, source verification, execution ordering, and retention eligibility. A future PR that materially changes custody policy should get a targeted mutation workflow/path filter for those decision-heavy files rather than forcing every Storage/CSS/docs PR to execute a long full-tree sweep.

## Adding a desktop feature

A new interactive slice should normally ship with:

- typed frontend request/response contracts;
- positive interaction coverage;
- at least one meaningful negative/boundary case;
- keyboard/semantic-role coverage where interactive;
- axe on the rendered slice;
- contextual guidance when the user must understand a non-obvious Scholion concept;
- explicit path/capability assertions if sensitive local state is involved;
- native tests when Rust gains a new privileged capability; and
- backend property/mutation tests when the feature changes decision-heavy application policy.

If writing the browser test or help copy requires recreating a backend rule in the component, inspect the architecture first. The better fix may be moving that rule back behind the Python service boundary and letting the frontend describe its outcome.
