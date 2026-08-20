# Processing Center

The Processing Center is EchoFlow's desktop control surface for local transcription work. It is intentionally a productization layer over existing backend authorities, not a second scheduler or transcription implementation.

## Authority boundaries

### Python application services own decisions

Python remains authoritative for:

- health and machine-resource inspection;
- processing-profile policy;
- strategy feasibility and recommendation;
- model inventory, verification, installation provenance, and removal safety;
- media probing and audio-stream selection;
- transcription preflight and resource admission;
- checkpoint compatibility and resume contracts;
- transcription execution correctness;
- diarization requests and explicit model-download consent;
- canonical transcript publication and derived exports;
- durable private job lifecycle state.

The desktop bridge exposes bounded typed operations only. It does not expose arbitrary shell, filesystem, SQL, database, or model-provider access.

### Tauri owns long-running child-process lifetime

The existing `desktop_request` bridge is deliberately short-lived: it starts Python, sends one bounded request, waits for one response, and exits. Long transcription or model-management work must not turn that RPC into an hour-long request.

Tauri therefore supervises a small allowlist of long-running task kinds:

- new transcription;
- checkpoint resume;
- fresh retry;
- model installation;
- model removal.

The native host does not decide which strategy is safe or whether a model is valid. It receives already-shaped intent, starts only allowlisted Python worker commands, owns the child handle, exposes status/cancel, rejects duplicate task identities, and terminates supervised children during desktop shutdown.

A cancelled or externally terminated transcription is recovered through Python's durable lifecycle/checkpoint rules. Tauri does not maintain a competing job database.

### React owns presentation and explicit user intent

The normal Processing Center UI leads with outcome-oriented profiles:

- **Quick draft** for provisional screening;
- **Balanced** for the ordinary default;
- **Best locally safe** for the highest-quality feasible local strategy.

Ordinary users are not required to choose Whisper model sizes, thread counts, compute types, or memory limits. Expert strategy/audio controls remain explicit advanced options and are still revalidated by Python before execution.

Model acquisition is never silently inferred from selecting a profile. The UI shows the recommended model and whether a verified EchoFlow-managed snapshot is already installed. Installing or removing a model is an explicit long-running action.

Optional diarization keeps its network-consent boundary separate from transcription-model custody. Derived TXT/SRT/VTT files remain disposable views; canonical transcript JSON remains evidence.

## Start flow

1. User selects a recording and processing intent.
2. React asks Python for preflight.
3. Python probes the recording, inspects current resources, assesses strategies, verifies managed model custody, and returns a minimized preflight DTO.
4. The user reviews the resulting profile/strategy/resource plan.
5. React asks Tauri to start an allowlisted transcription worker for the exact preflight job identity.
6. Python owns lifecycle state and checkpoints while the native host owns child-process lifetime.
7. The Processing Center polls bounded task status and durable job lifecycle state.
8. Successful execution publishes canonical transcript evidence and any explicitly requested derived exports.

Private source/output/model-cache paths are not part of the general Processing Center overview DTOs. Path-bearing execution intent is kept to the narrow operation that actually needs it.

## Resume, retry, cancel, and discard

These operations are deliberately distinct:

- **Resume** restores the interrupted job's checkpointed execution contract and re-admits it against current hardware. It does not silently change profile, strategy, audio stream, or enhancement settings.
- **Retry** creates a new plan from the source recording. It is allowed to use current defaults or newly selected expert options.
- **Cancel** terminates the supervised child. Valid checkpoints remain subject to the normal resumability rules.
- **Discard private job state** removes disposable lifecycle/checkpoint state only. It never deletes original recordings, published canonical transcript evidence, or human research state. The request is bound to the job's current `updated_at` value so stale UI state cannot delete a newer lifecycle generation.

A job reported as `running` whose recorded process identity is no longer active is reconciled by the Python lifecycle store to `interrupted`. This makes recovery durable across application restarts without treating native in-memory task state as authoritative.

## Failure and privacy semantics

Processing Center errors crossing into the desktop are public, bounded messages. Backend exceptions, raw provider errors, and private filesystem detail are not rendered directly into the UI.

Readiness and job overview responses expose only what is necessary to explain local execution state, such as platform, effective CPU count, available-memory budget, profile, model identity, progress, resumability, and safe failure categories.

The design preserves EchoFlow's central custody rule: recordings, canonical transcript evidence, and human research remain authoritative user-owned material; execution indexes, checkpoints, derived exports, and native task handles are supporting machinery and may be rebuilt or discarded according to their contracts.
