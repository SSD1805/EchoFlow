# Architecture and redundancy audit

This audit exists to remove duplicated **meaning and ownership**, not to minimize file count.
EchoFlow deliberately has several narrow adapters because playback, custody, transcript tools,
processing, research, and ordinary desktop operations do not share the same authority.
Similar-looking code is only a problem when it can drift into different behavior or makes the
real composition root unclear.

## Status

Two cleanup tranches are now implemented:

1. trusted-host transport/composition consolidation; and
2. Research saved-question/evidence-contract consolidation.

The Research tranche removes the largest product-level redundancy found by the audit without
migrating or rewriting authoritative research data. Saved questions remain the same SQLite
`SavedSearch` / `SavedSearchIntent` objects; only their duplicate desktop ingress and UI are
collapsed.

## Reconsolidation patterns

The audit uses a small set of patterns rather than a generic abstraction framework.

### Capability-blind shared plumbing

Share mechanics that cannot grant new authority. `echoflow.desktop.host_protocol` knows how
to bound/read JSON and emit a versioned response, but it does not know which service, method,
path, or database capability a bridge owns.

### Authority-preserving adapters

A shared transport helper does not imply a shared capability. Playback, custody, transcript
tools, lifecycle, and ordinary desktop operations keep separate closed schemas, dispatchers,
and public error policies when their authority differs.

### Composition-root centralization

Application services are assembled by `AppContainer` rather than quietly rebuilt inside
adapters. Bridges translate contracts; they do not become second dependency graphs.

### Fixed-command transport

Frontend protocol helpers accept a closed set of native commands. Consolidation must never
turn a hard-coded native seam into `invokeAnything(command: string)` or allow the webview to
choose a Python module.

### Shared contract, not shared policy

`echoflow.desktop.research_serialization` serializes already-authorized Research evidence into
one frontend shape. It does not choose generations, resolve evidence, query storage, or expose
paths. Search policy stays in application/library services.

### Facade completion before adapter retirement

Before deleting an older ingress, complete the richer application facade so it can express the
whole user lifecycle. The typed Research search service gained list/inspect/replace/run/delete
operations before the older `workspace.research.saved_search.*` desktop family was retired.

### Remove duplicate ingress, preserve domain capability

Retiring a duplicate desktop API does not mean deleting the underlying capability. CLI and
internal callers still use `ResearchWorkspaceService` saved-search operations. One redundant
front door disappeared; the room did not.

### Test-double isomorphism

Mocks should reflect the same conceptual authority graph as production. The browser mock now
keeps one typed saved-question store instead of mirroring the same saved search into separate
"simple" and "typed" arrays.

### Extract stable invariants, not utility grab-bags

Research label normalization is one stable boundary invariant: trim, reject blank/oversized or
control-character values, de-duplicate case-insensitively, preserve display spelling. That rule
is appropriate to share. Unrelated one-field validators remain next to their request models.

## First tranche: trusted-host and composition cleanup

### Trusted-host Python protocol mechanics

Playback, transcript tools, and lifecycle custody each had their own copy of the same bounded
stdin/stdout JSON loop, protocol response envelope, request-size cap, and stdout redirection.
They now share `echoflow.desktop.host_protocol` for **transport mechanics only**.

The helper does not know:

- which methods a bridge accepts;
- which application service is being called;
- which Tauri command invokes it;
- any filesystem path or SQL/database capability; or
- how domain errors are classified for the caller.

Each bridge therefore keeps its closed Pydantic request schema, domain dispatcher, service,
and public error policy. This is intentionally not a universal desktop bridge.

### Application composition ownership

`PlaybackAuthorizationService`, `SpeakerPresentationService`, and `TranscriptToolsService`
are now composed by `AppContainer` instead of being manually assembled inside desktop bridge
modules. The bridge is an adapter; the application container is the composition root.

This matters because otherwise a future dependency change could be applied to the application
container while the native desktop silently continued constructing an older graph.

### Processing preflight DTOs

First-run preflight and retry preflight genuinely share profile, strategy, audio-stream, and
enhancement options. Those fields now live in one strict `_PlanningOptionsParams` base while
the two request types keep their distinct identity field (`input_path` versus
`source_job_id`). The refactor removes duplicated validation without pretending the two
operations are the same command.

### Frontend native protocol transport

Lifecycle, transcript tools, and research-anchor maintenance repeated the same versioned
request envelope, response validation, Tauri invocation, and public-error unwrapping. They
now use `frontend/src/api/nativeProtocol.ts`.

The helper accepts only the fixed native protocol commands currently intended for this
contract:

- `desktop_request`;
- `transcript_tools_request`; and
- `lifecycle_request`.

It does not accept an arbitrary command string. Playback remains separate because its Rust
API returns opaque media-session state rather than the Python desktop protocol envelope.

## Second tranche: Research contract consolidation

### One saved-question authority in the desktop product

`ResearchWorkspace` and `ResearchSearchControlsPanel` previously rendered two saved-search
management surfaces on the same screen. Both operated on the same authoritative SQLite
objects, but one used the older query-only `workspace.research.saved_search.*` desktop family
and the other used the richer typed `workspace.research.search.saved.*` family.

The typed Research search surface now owns the complete lifecycle:

- list;
- create;
- inspect/load;
- replace full typed intent;
- run against current evidence/research; and
- explicitly confirmed delete with optimistic concurrency.

`ResearchWorkspace` now owns notes, labels, and anchored evidence only. The older desktop
saved-search methods, DTOs, client methods, result block, and duplicate browser mock state are
removed. The underlying workspace/domain API remains available to the CLI and internal code.

### One Research evidence presentation contract

Ordinary workspace discovery and typed Research search previously serialized
`EvidenceWord`, `EvidenceContextSegment`, speaker presentation, exact canonical generation,
timing, research labels, and `WorkspaceSearchPassage` independently.

They now depend on `echoflow.desktop.research_serialization`. The module is intentionally
pure presentation mapping. Private `canonical_path` / `source_path` fields remain absent from
the frontend contract, and evidence resolution remains owned by library/application services.

### Research label validation

Typed search and note/filter requests apply the same Research label invariant. The invariant
lives in `echoflow.desktop.research_validation` rather than being independently reimplemented
by adapters.

## Patterns intentionally retained

### Fixed Rust module wrappers

`frontend/src-tauri/src/backend.rs` already has the right shape. One private Rust function
owns process spawning, request-size enforcement, and Python stdout parsing, while tiny wrapper
functions bind each capability to a hard-coded Python module. Do not replace those wrappers
with a webview-supplied module name.

### Separate bridge authorities

`desktop_request`, `transcript_tools_request`, `lifecycle_request`, and the private playback
path are separate because their authority differs. A generic dispatcher would save lines and
weaken the threat model.

### Explicit Pydantic request models

`ConfigDict(extra="forbid")` appears often because rejecting unexpected fields is part of the
boundary contract. A global inheritance hierarchy merely to remove those lines would hide a
security property rather than simplify it.

### Domain-visible E2E fixtures

Mocks repeat some DTO shape intentionally. They are executable product examples and make it
obvious what the browser can see. Centralizing every fixture into a factory would reduce
literal duplication while making path-disclosure and human-copy tests harder to inspect.

## Remaining high-value cleanup

### 1. Finish frontend protocol migration

The fixed-command native protocol helper should also replace equivalent transport boilerplate
inside the broader `api/desktop.ts` and `api/processing.ts` clients. Do this in a focused
change with their interaction tests; do not widen the helper to arbitrary commands.

### 2. Move Processing Center composition into `AppContainer`

The ordinary desktop bridge still manually assembles `ProcessingCenterService`. Its
dependencies are already container-owned. Move that composition after the general bridge is
made smaller so the change does not combine dependency wiring with unrelated dispatch work.

## Lower-value repetition not worth a framework

- repeated `new URLSearchParams(...).get("e2e")` checks can become one helper if test-mode
  wiring changes, but they do not currently threaten authority or correctness;
- small one-field Pydantic validators are clearer beside their request than behind a generic
  validation DSL;
- React loading/error state often looks similar but belongs to different interaction
  lifecycles; and
- separate semantic CSS classes are not redundant merely because they share token values.

## Test policy

The shared Python host transport has direct unit tests for bounded JSON input, response
versioning, dispatch suppression on malformed input, and stdout isolation. The frontend
response parser has a pure contract test in the Playwright test runner in addition to feature
flows.

The Research tranche migrates, rather than deletes, lifecycle coverage: browser tests now
qualify the one typed saved-question surface, backend tests qualify the typed list/inspect/
replace/run/delete contract, and exact-generation note evidence safety tests remain separate.
Because this tranche does not alter playback authorization decisions, the Playback Mutation
workflow should not be selected merely because Research adapters changed.

## Exit criterion for the audit

The product-level Research redundancy and evidence-contract drift identified by the audit are
resolved. The remaining two high-value items are transport/composition cleanup in the broad
desktop path. Once those are complete and qualified, remaining similarity should be
intentional authority separation rather than evolutionary residue.
