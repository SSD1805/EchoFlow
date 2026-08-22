# Architecture and redundancy audit

This audit removes duplicated **meaning and ownership**, not merely repeated lines. EchoFlow deliberately keeps several narrow adapters because playback, custody, transcript tools, processing, research, and ordinary desktop operations do not carry the same authority.

## Status: complete

The pre-identity audit is complete in three bounded cleanup tranches:

1. trusted-host transport and composition consolidation;
2. Research saved-question and evidence-contract consolidation; and
3. broad desktop transport/composition closure.

The exit criterion is now met: remaining similarity is intentional authority separation, explicit compatibility, readable boundary validation, or ordinary interaction-local state rather than unresolved evolutionary residue.

This is the architectural freeze point before product identity migration and packaging. A future refactor still needs a concrete invariant or demonstrated drift risk; resemblance alone is no longer sufficient reason to consolidate code.

## Reconsolidation rules

### Capability-blind shared plumbing

Share mechanics that cannot grant new authority. `echoflow.desktop.host_protocol` owns bounded JSON stdin/stdout transport and the versioned response envelope. It knows nothing about methods, services, paths, databases, or Tauri commands.

The general desktop bridge now uses this same helper alongside playback, transcript-tools, and custody bridges. Each bridge still owns its closed request schema, dispatcher, public error policy, and application capability.

### Authority-preserving adapters

A shared transport does not imply a shared capability. `desktop_request`, `transcript_tools_request`, `lifecycle_request`, and the private playback path remain separate because their authority differs. A universal method/module dispatcher would save lines while weakening the threat model.

### Composition-root centralization

Application services are assembled by `AppContainer`, not quietly recreated in adapters. The container now owns:

- `PlaybackAuthorizationService`;
- `SpeakerPresentationService`;
- `TranscriptToolsService`;
- `ResearchSearchControlService`; and
- `ProcessingCenterService`.

The broad desktop bridge receives those composed authorities. Its job is request validation, presentation serialization, and dispatch, not dependency-graph construction.

Tests verify the shared dependency identities inside these composed services, rather than merely asserting that a provider returns the class registered with it.

### Fixed-command frontend transport

`frontend/src/api/nativeProtocol.ts` owns the shared versioned request envelope, response validation, request IDs, fixed Tauri invocation, and public-error unwrapping used by ordinary desktop, Processing bounded requests, transcript tools, Research anchor maintenance, and lifecycle calls.

Its command type remains closed to:

- `desktop_request`;
- `transcript_tools_request`; and
- `lifecycle_request`.

`api/desktop.ts` and the bounded request side of `api/processing.ts` now use that helper rather than maintaining private copies of the protocol.

Processing task launch/status/cancellation intentionally remain separate. They use dedicated Rust commands for supervised long-running child-process lifetime and return a different task-status contract, not the Python request/response envelope.

Playback also remains separate because Rust returns opaque media-session state rather than a normal desktop protocol response.

### Shared Research contract, not shared policy

`echoflow.desktop.research_serialization` maps already-authorized evidence into one frontend shape. It does not choose generations, resolve evidence, query storage, or expose canonical/source paths.

`echoflow.desktop.research_validation` owns the stable label invariant shared by Research adapters: trim, reject invalid values, de-duplicate case-insensitively, and preserve display spelling.

Search policy and durable saved-question lifecycle remain application/library authority.

### One saved-question desktop authority

The earlier Research UI exposed two management surfaces and two desktop API families over the same SQLite `SavedSearch` / `SavedSearchIntent` objects. The richer typed Research search surface now owns list, create, inspect, replace, run, and optimistic-concurrency delete.

The older desktop ingress and duplicate browser mock store are gone. CLI/internal domain capability remains available. No authoritative research data migration was required.

### Facade completion before adapter retirement

A richer facade must express the full lifecycle before an older ingress disappears. That rule was used for saved questions and is the default for later compatibility retirement.

## Intentionally retained boundaries

### Fixed Rust Python-module wrappers

`frontend/src-tauri/src/backend.rs` has one private request runner and tiny wrappers bound to hard-coded Python modules. The webview cannot select a module name. Keep that shape.

### Short requests versus supervised processing tasks

`backend.rs` and `processing.rs` both launch Python, but they do different jobs. The former performs bounded request/response IPC; the latter owns long-lived child-process supervision, task identity, cancellation, and process cleanup. Combining them would erase a useful lifetime and authority boundary.

### Explicit Pydantic request models

Repeated `ConfigDict(extra="forbid")` is a visible security property. A generic validation hierarchy would make unexpected-field refusal harder to inspect for little practical gain.

### Domain-visible E2E fixtures

Browser mocks deliberately repeat some DTO shape. They are executable examples of what the webview can see, and they keep path-disclosure and human-copy assertions legible. Centralizing every fixture would reduce textual repetition while obscuring the boundary being tested.

### Interaction-local React state

Loading, error, confirmation, and editing state often look alike but belong to different user lifecycles. There is no evidence of policy drift that justifies a generic interaction-state framework.

## Pre-release compatibility cleanup

The audit initially retained the deprecated runner `ModelTier` marker conservatively because `ExecutionPolicy.to_dict()` exposed `recommended_model_tier` through the development CLI wire shape. A follow-up review before packaging established that the marker was not part of canonical evidence, authoritative research, checkpoint identity, or a released integration contract.

It was therefore removed before distribution could turn historical residue into compatibility debt. `ExecutionPolicy` now owns only processing intent and resource/admission limits. Concrete transcription strategy ranking remains the sole engine/model-selection authority, including when a resumed job is re-admitted on the current machine.

This is the intended pre-release rule: preserve real user-owned and released contracts aggressively; do not manufacture permanence for an obsolete internal shape merely because tests once serialized it.

## Test policy

The audit does not add source-text, existence-only, or self-fulfilling tests.

Qualification relies on observable contracts:

- shared host transport tests bound input size, malformed JSON, response versioning, dispatch suppression, and stdout isolation;
- application-container tests verify real dependency identity across composed services;
- desktop bridge tests exercise closed allowlists, strict request validation, public error masking, path non-disclosure, and delegation;
- Research tests preserve optimistic concurrency and exact-generation evidence behavior;
- the frontend parser contract test checks compatible and incompatible envelopes;
- feature-level Playwright/axe flows continue to exercise the user-visible paths using the same conceptual authority graph as production.

Mutation testing remains targeted at decision-heavy policy. This consolidation does not change playback authorization decisions and does not justify a blanket frontend mutation tax.

## Audit exit criterion

The audit is closed when all of the following are true:

- capability-blind trusted-host transport has one implementation;
- application-service construction has one composition root;
- the frontend's bounded native protocol has one fixed-command implementation;
- Research saved-question and evidence presentation contracts no longer have duplicate desktop authorities;
- no stale compatibility layer is mistaken for current policy; and
- remaining repetition has an explicit readability, security, compatibility, authority, or lifecycle reason.

Those conditions are now satisfied. The next first-release arc is product identity migration, followed by packaging and release engineering.
