# Architecture and redundancy audit

This audit exists to remove duplicated **meaning and ownership**, not to minimize file count.
EchoFlow deliberately has several narrow adapters because playback, custody, transcript tools,
processing, research, and ordinary desktop operations do not share the same authority.
Similar-looking code is only a problem when it can drift into different behavior or makes the
real composition root unclear.

## Status

The first cleanup tranche is implemented on the architecture-audit branch. It removes shared
transport/composition boilerplate without widening any native capability. A second Research
cleanup remains before the product-identity/packaging checkpoint because saved-search
management is currently duplicated on the same screen.

## Changes made in this tranche

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

### 1. Consolidate saved-search management

This is the largest real product redundancy found by the audit.

`ResearchWorkspace` and `ResearchSearchControlsPanel` currently render two saved-search
management surfaces on the same Research screen. Both operate on the same authoritative
SQLite `SavedSearch` / `SavedSearchIntent` objects, but one surface uses the older simple
`workspace.research.saved_search.*` bridge family while the typed search panel uses
`workspace.research.search.saved.*`.

The older create operation is not a different research primitive. It simply compiles a
query-only request into default lexical typed intent. The typed panel can express the full
saved question and should become the single creation/edit/run/delete surface.

The cleanup should:

1. add typed saved-search run and delete operations under the Research search control
   service/bridge;
2. keep optimistic concurrency on destructive/update operations;
3. move run/delete presentation into the typed saved-search panel;
4. remove the duplicate saved-search editor/results block from `ResearchWorkspace`;
5. remove the older simple desktop methods and client calls once no UI uses them; and
6. migrate the existing backend/browser lifecycle tests instead of deleting coverage.

No SQLite data migration is required because both endpoint families already use the same
saved-search authority.

### 2. Share Research evidence serialization

`echoflow.desktop.bridge` and `research_search_bridge` independently serialize the same
`EvidenceWord`, `EvidenceContextSegment`, speaker labels, exact canonical generation, timing,
research labels, and `WorkspaceSearchPassage` fields. That can eventually make ordinary
Library discovery and typed Research search disagree about what an evidence DTO means.

Extract one presentation serializer module and have both adapters depend on it. This is a
contract-drift fix, not an attempt to move search semantics into serialization.

### 3. Finish frontend protocol migration

The new fixed-command helper should also replace the equivalent transport boilerplate inside
`api/desktop.ts` and `api/processing.ts`. Those files are broader clients, so migrate them in
a focused change with their existing interaction tests rather than coupling the change to the
smaller adapter cleanup above.

### 4. Move Processing Center composition into `AppContainer`

The ordinary desktop bridge still manually assembles `ProcessingCenterService`. Its
dependencies are already container-owned. Move that composition after the general bridge is
made smaller so the edit does not combine a composition change with unrelated dispatch
rewrites.

### 5. Share Research label normalization

The generic research bridge and typed search bridge enforce the same trim/length/control-
character/case-fold de-duplication rules. Move that exact rule to one small Research desktop
validation helper when the saved-search/Research adapter cleanup touches both files.

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
response parser has a pure contract test in the Playwright test runner in addition to the
existing feature-flow tests.

Because this tranche changes `playback_bridge.py`, the targeted Playback Mutation workflow is
expected to run. That is appropriate: mutation testing remains path-targeted to a changed
security-sensitive seam rather than becoming a universal CI tax.

## Exit criterion for the audit

Before the product-identity checkpoint, finish the saved-search consolidation and shared
Research evidence serialization, then re-run the ordinary quality matrix plus only the
mutation workflows selected by touched decision-heavy files. At that point the remaining
similarity should be intentional authority separation, not evolutionary residue.
