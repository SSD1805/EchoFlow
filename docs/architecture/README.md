# EchoFlow architecture 🔧

Welcome to the maintenance hatch.

The user-facing docs explain what EchoFlow does. These pages explain **why the boundaries
exist, what each capability owns, what it refuses to own, and which invariants must survive
refactors**.

If you are trying to transcribe a file rather than maintain the system, use
**[Getting started](../getting-started.md)**.

## The shape of the system

EchoFlow is composed from narrow local capabilities in
`src/echoflow/app/app_container.py`. The through-line is custody: source evidence,
canonical transcript truth, private execution state, rebuildable projections, durable human
knowledge, native process/media lifetime, and desktop presentation deliberately do not share
authority semantics.

```mermaid
flowchart LR
    A[Source media] --> B[Media and resource inspection]
    B --> C[Immutable local plan]
    C --> D[Transcription and checkpoints]
    D --> E[Canonical transcript JSON]
    E --> F[Derived exports]
    E --> G[DuckDB lexical and semantic projections]
    G --> H[Ranked passages]
    E --> I[Verified evidence navigation]
    H --> I
    I --> J[SQLite research authority]
    J --> K[Deterministic projector]
    K --> L[DuckDB research projection]
    L --> H
    J --> M[Saved searches]
    J --> N[ResearchWorkspaceService]
    I --> N
    M --> N
    N --> O[Unified discovery]
    E --> P[LibraryCustodyService]
    G --> P
    J --> P
    D --> P
    P --> Q[Plan-bound deletion]
    O --> R[Versioned desktop bridge]
    I --> R
    N --> R
    C --> U[ProcessingCenterService]
    D --> U
    U --> R
    R --> S[React Library Research Processing]

    classDef source fill:#F9D5E5,stroke:#7B2E52,stroke-width:2px,color:#22151B
    classDef process fill:#E8D9FF,stroke:#68469B,stroke-width:2px,color:#1F1630
    classDef evidence fill:#FFF0B8,stroke:#8A6B18,stroke-width:2px,color:#2C260F
    classDef view fill:#DDF5E3,stroke:#347A46,stroke-width:2px,color:#142719
    classDef inspect fill:#D8EEFF,stroke:#2E617B,stroke-width:2px,color:#12222A
    classDef stop fill:#FFD6D6,stroke:#9E3434,stroke-width:2px,color:#351616

    class A source
    class B,C,D,U process
    class E,I,J evidence
    class F,G,H,K,L,M,O view
    class N,R,S inspect
    class P,Q stop
```

<details>
<summary>Static diagram fallback if rich rendering is unavailable</summary>

![EchoFlow system-architecture static diagram](../diagrams/system-architecture.svg)

</details>

Text fallback: canonical JSON is evidence; DuckDB ranks rebuildable views; canonical
navigation verifies evidence; SQLite owns human research; `ResearchWorkspaceService`
composes research interactions; `ProcessingCenterService` composes machine/model/job,
preflight, and explicit embedded-track confirmation authority; the versioned desktop bridge
feeds current Library, Research, and Processing presentation; `LibraryCustodyService` keeps
destructive policy separate. Verified playback and lifecycle Storage each use separate fixed
Python-to-Rust paths rather than widening the general bridge.

## Where to look

| Page | What question it answers |
|---|---|
| [Processing capabilities](processing-capabilities.md) | How does the local transcription/research system fit together? |
| [Processing Center](processing-center.md) | How does the desktop expose readiness, preflight, embedded-track choice, jobs, and long-running native work without becoming the scheduler? |
| [Audio tracks](../audio-tracks.md) | How does EchoFlow choose among several embedded audio streams without guessing or confusing transcription with playback? |
| [Verified native playback](../native-playback.md) | How does exact-generation evidence become a local media capability without exposing paths to React? |
| [Storage and lifecycle controls](../storage-lifecycle.md) | How does the desktop expose plan-bound custody and retention without giving React filesystem authority? |
| [Adaptive heterogeneous execution](adaptive-heterogeneous-execution.md) | How does EchoFlow decide what this machine can safely run? |
| [Media and timeline](media-and-timeline.md) | Which source/stream did we use, and what do timestamps mean? |
| [Word-level timestamp alignment](word-alignment.md) | How do engine timings become source-relative evidence? |
| [Local model management](model-management.md) | Which model revision is allowed to execute, and how did it get here? |
| [Speech enhancement](speech-enhancement.md) | How can preprocessing affect ASR without becoming source truth? |
| [Anonymous speaker diarization](diarization.md) | How are speaker turns represented without pretending anonymous labels are identities? |
| [Corpus search](corpus-search.md) | How do lexical/semantic/hybrid ranking and verified navigation stay separate? |
| [Durable research state](research-state.md) | Why does SQLite own human research while DuckDB owns rebuildable acceleration? |
| [Library lifecycle](library-lifecycle.md) | Where does canonical JSON live, what does rebuild/refresh scan, and which state is durable? |
| [Library locations](library-locations.md) | What does “remember this folder” persist, and what does discovery refuse to do? |
| [Incremental library refresh](incremental-library-refresh.md) | How does the corpus reconcile without a full rebuild? |
| [Safe deletion and retention](safe-deletion-retention.md) | What exactly can be deleted, what is preserved, and how is destructive intent confirmed? |
| [Desktop themes/accessibility](../development/desktop-accessibility.md) | How do all skins share one semantic token and contrast contract? |
| [ROADMAP](../../ROADMAP.md) | What is implemented, what is next, and what remains later? |
| [SECURITY](../../SECURITY.md) | What does the security boundary actually claim? |

## Package map

| Package / surface | Responsibility |
|---|---|
| `app` | Dependency-injection composition root and application-facing processing composition |
| `core` | Configuration, errors, observability, health, measurements |
| `interfaces` | Local filesystem/storage adapters and private-storage policy |
| `media` | Read-only source inspection, bounded embedded-track display metadata, and deterministic audio-stream selection |
| `runner` | Process-visible CPU/memory inspection and execution-budget policy |
| `model_management` | Model inventory, acquisition, verification, provenance, removal |
| `transcription` | Planning, normalization, enhancement, segmentation, ASR, checkpoints, language, alignment, diarization, assembly, exports |
| `workspace` | Private job paths and public artifact allocation |
| `benchmarking` | Privacy-minimized local execution measurement |
| `library` | Retrieval, evidence navigation, playback authorization, research authority/projections, saved searches, discovery, refresh, locations, typed custody policy |
| `desktop` | Versioned allowlisted Python bridges plus fixed private playback and lifecycle custody bridges |
| `frontend` | React/TypeScript presentation over typed desktop operations; no direct DB/filesystem/media-probe/custody authority |
| `src-tauri` | Thin native host/capability boundary for dialogs, allowlisted long-running child processes, fixed Python bridge commands, opened playback sessions, and bounded local media transport |

## Capability boundaries

EchoFlow prefers a small object with one clear job over a universal manager.

The search/research/custody/processing/desktop area deliberately separates responsibilities:

1. `TranscriptLibraryService` discovers and ranks rebuildable transcript passages.
2. `EvidenceLocator` verifies ranked passages against canonical evidence.
3. `SpeakerLabelService` owns durable recording-scoped human display names without rewriting diarization evidence.
4. `ResearchStateStore` owns durable evidence notes, tags, collections, and exact evidence anchors.
5. `ResearchStateProjector` converges authoritative SQLite state into a disposable DuckDB research projection.
6. `ResearchProjectionIndex` owns fast derived research constraints and summaries.
7. `WorkspaceMetadataStore` owns durable saved-search intent and computes disposable navigation views.
8. `ResearchWorkspaceService` composes those capabilities for CLI and presentation adapters.
9. `LibraryLocationService` owns remembered directory permissions and cheap recording discovery without becoming a media processor.
10. `LibraryCustodyService` owns typed deletion planning/execution and age-based private execution-state retention.
11. `ProcessingCenterService` composes health/resource/model/job/preflight authority, including whether multi-track preflight requires explicit user confirmation, without reimplementing lower-level media policy.
12. `PlaybackAuthorizationService` verifies exact canonical generation, current source bytes, coordinate bounds, and stream identity before native media can open.
13. `echoflow.desktop.bridge` exposes the ordinary allowlisted versioned IPC surface for Library/Research/Processing.
14. The playback bridge is private to a fixed Rust host path and cannot be redirected to an arbitrary Python module.
15. `echoflow.desktop.custody_bridge` exposes only document listing, deletion plan/apply, and retention plan/apply through a dedicated fixed Tauri command; it strips action/workspace paths before serialization.
16. Tauri supervises allowlisted long-running native child processes, owns opaque opened playback sessions, and invokes fixed Python modules. It owns process/file lifetime, not strategy selection, stream selection, model validity, transcript correctness, or custody policy.
17. React owns interaction and presentation only. It does not issue SQL, mutate DuckDB/SQLite directly, select canonical generations, inspect media, choose a preferred audio track by policy, or decide effective deletion/retention policy.

That split must survive future UI convenience work. Presentation convenience is not
permission to merge custody boundaries.

## Why SQLite and DuckDB both exist

SQLite is authoritative for irreplaceable, frequently mutated user research. DuckDB is
used for rebuildable analytical/query projections. There is one authority, not two masters.

```text
SQLite authority
      |
      | monotonic transactional change journal
      v
ResearchStateProjector
      |
      v
DuckDB research projection
```

If a research projection disappears, rebuild it. If SQLite user state disappears, unique
human work is lost. That asymmetry is intentional.

Saved searches live in authoritative SQLite because they are authored intent. Their runtime
evidence scope does not. Replaying a saved search re-resolves the current corpus and current
research relationships.

A future freeform research memo/notebook should also be authoritative SQLite state, but as a
separate research-document class rather than an evidence note with a nullable anchor. That
keeps “this is my synthesis” distinct from “this prose is attached to these exact canonical
coordinates.”

## Desktop presentation does not rename authority

The desktop intentionally translates internal vocabulary into ordinary product language.
For example, Research presents one **Match** choice while the backend keeps separate
phrase/operator properties, and it calls lexical/semantic/hybrid **Wording / Meaning /
Wording + meaning**.

That translation is presentation only. Python still validates/canonicalizes the typed
request, derives research evidence scope, chooses retrieval behavior, and verifies evidence.
Similarly, all eight UI skins share semantic CSS tokens; theme selection cannot alter
backend requests, evidence identity, or research state.

Embedded-track presentation follows the same rule. Python decides whether explicit stream
confirmation is required and validates the requested stream. React can display bounded
source-declared title/language/default metadata and collect a radio-button choice, but it
cannot turn those labels into a recommendation or skip backend re-preflight.

Storage follows the same principle. React offers understandable custody scope labels and a
second source acknowledgment, but `LibraryCustodyService` computes scope expansion, action
sets, note preservation, saved-search effects, source provenance checks, retention
eligibility, resume-loss flags, and the plan-bound confirmation token.

## The custody rules 🦝

1. **Original media is source evidence and read-only during normal processing.** Explicit source deletion is separate and provenance-checked.
2. **Canonical transcript JSON is authoritative transcript evidence.**
3. **The exact selected embedded audio-stream index is part of transcription provenance. Source-declared track labels are descriptive clues, not identity.**
4. **Managed model manifests describe verified local execution dependencies.**
5. **Lexical, semantic, and research DuckDB databases are rebuildable projections.**
6. **Speaker labels, notes, tags, collections, and saved searches are human-authored authority and do not inherit index deletion semantics.**
7. **Research joins include canonical generation identity, not a friendly segment ID alone.**
8. **Precise navigation resolves to verified canonical evidence rather than trusting a stale search projection.**
9. **Research filters apply before ranking/scoring when they define eligible evidence.**
10. **Saved searches persist typed query intent, not a frozen derived evidence scope.**
11. **Canonical deletion preserves attached notes and document-scoped saved searches unless their own destructive scopes are explicitly selected.**
12. **Age-based retention can delete only private job workspaces.**
13. **Remembered locations are permissions/pointers, not copies of user media.**
14. **The desktop webview receives typed presentation DTOs and opaque playback handles, not arbitrary filesystem paths or database handles.**
15. **Lifecycle plan DTOs omit deletion paths and private workspace paths.**
16. **Long-running native process supervision does not create a second job or checkpoint authority.**
17. **Verified playback authorization does not turn an opaque media session into source/evidence authority.**
18. **Theme/presentation state is machine-local preference, not evidence or research state.**
19. **EchoFlow does not claim secure erasure it cannot prove.**

Search infrastructure may disappear. User-authored knowledge may not disappear by accident.

## Current application seams

Unified discovery, saved searches, frequent/recent navigation, and research interactions
compose through `ResearchWorkspaceService`. The desktop exposes grouped Library discovery,
verified context/word coordinates, durable Research mutation, saved search/anchor flows, and
full Research search controls through narrow bridge methods.

Processing composes through `ProcessingCenterService`; Tauri owns only the native lifetime
of allowlisted long-running tasks. Multi-track confirmation is returned by Python preflight,
and a user choice is rebound through Python before execution. Resume/retry semantics remain
Python application policy.

Verified playback composes through `PlaybackAuthorizationService` plus the private fixed
playback bridge. Rust opens the approved file, retains it behind an opaque active session,
and serves bounded byte ranges through `echoflow-media`. React does not receive the path.
Multi-track playback deliberately fails closed until the native layer can prove the rendered
embedded stream.

Incremental corpus growth composes through `TranscriptLibraryService.refresh(...)` and
remembered roots through `LibraryLocationService`. Full `library rebuild` is an explicit
repair/recovery lever, not a normal “one file changed” workflow.

Custody-sensitive operations remain separate through `LibraryCustodyService`:

```bash
echoflow library delete TRANSCRIPT_ID --scope library-view
echoflow library delete TRANSCRIPT_ID --scope canonical-transcript
echoflow library retention --execution-days 30
```

The native Storage workspace exposes the same plan/apply contract through the dedicated
custody bridge. Deletion and retention remain preview-first. Applying a reviewed operation
requires the exact plan-bound token; execution recalculates the plan and refuses changed
state. React never receives the destructive filesystem paths.

The **next product seam is the architecture/redundancy audit**. It should remove duplicated
policy/glue and clarify ownership before packaging freezes bundle IDs, app-data locations,
sidecar contracts, and update/uninstall behavior. The product-name/identity decision belongs
before that packaging freeze as well.

## New abstraction test

Before adding a manager, framework, registry, adapter hierarchy, generalized plugin system,
or database wrapper, ask which concrete capability or invariant it protects.

File count is not an architectural problem. Repeated policy, unclear ownership, and
unprovable invariants are.

The same applies to frontend styling: eight skins do not justify eight component palettes.
One semantic role should have one meaning and eight token values.

## Documentation contract

Architecture pages should provide a plain-English doorway, a structural model when useful,
the exact implementation contract, ownership/failure semantics, and explicit current
limits or future seams.

Mermaid diagrams use direct GitHub-supported fenced syntax and the approved EchoFlow
palette; color helps hierarchy but never carries the only meaning. See
**[documentation-style.md](../documentation-style.md)** for the editorial and visual
contract.
