# EchoFlow roadmap 🗺️✨

EchoFlow is becoming a **private local workspace for recorded evidence**.

Its job is not to out-engine every speech-recognition runtime. Its job is to make local
transcription dependable, resumable, inspectable, searchable, navigable, annotatable, and
portable on ordinary computers while keeping source evidence and human-authored knowledge
under clear custody.

Modern EchoFlow restarted on August 2, 2026. The project has moved from “can we transcribe
a file?” through a substantial backend foundation into a native desktop that can import,
process, search, verify, and annotate local evidence. This roadmap is a productization map,
not a list of every class or CLI command.

```mermaid
flowchart LR
    A[Local media] --> B[Reliable local transcription]
    B --> C[Canonical evidence]
    C --> D[Lexical semantic hybrid retrieval]
    D --> E[Verified evidence navigation]
    E --> F[Durable research authority]
    D --> G[Unified discovery]
    F --> G
    G --> H[Saved searches]
    H --> I[Safe lifecycle]
    I --> J[Incremental refresh]
    J --> K[Durable library locations]
    K --> L[Tauri React desktop]
    L --> M[Import and Library UI]
    M --> N[Verified evidence reader]
    N --> O[Research evidence loop]
    O --> P[Processing center]
    P --> Q[Local media playback]
    Q --> R[Desktop packaging]
    R --> S[Backup restore portability]
    S --> T[Release qualification]

    classDef source fill:#F9D5E5,stroke:#7B2E52,stroke-width:2px,color:#22151B
    classDef process fill:#E8D9FF,stroke:#68469B,stroke-width:2px,color:#1F1630
    classDef evidence fill:#FFF0B8,stroke:#8A6B18,stroke-width:2px,color:#2C260F
    classDef view fill:#DDF5E3,stroke:#347A46,stroke-width:2px,color:#142719
    classDef inspect fill:#D8EEFF,stroke:#2E617B,stroke-width:2px,color:#12222A

    class A source
    class B process
    class C,E,F evidence
    class D,G,H,I,J,K view
    class L,M,N inspect
    class O,P,Q,R,S,T process
```

<details>
<summary>Static diagram fallback if rich rendering is unavailable</summary>

![EchoFlow product-roadmap static diagram](docs/diagrams/product-roadmap.svg)

</details>

Text fallback: EchoFlow already spans local media, reliable transcription, canonical
evidence, retrieval, verified navigation, durable research, lifecycle contracts,
incremental refresh, remembered locations, native import, Library discovery, the verified
evidence reader, the Research evidence loop, and the desktop Processing Center. Remaining
first-release work is primarily transcript/speaker polish, playback, lifecycle UI,
architecture cleanup, packaging, portability, semantic packaging, and real-device
qualification.

# What is foundation now

The word **foundation** below means the contract exists in code and is protected by tests.
It does not mean every capability has finished UX polish or packaged-product qualification.

## Local execution, media, model custody, and Processing Center

EchoFlow inspects process-visible CPU/memory, physical accelerator topology, and engine
capabilities before admitting a concrete local strategy. FFprobe provides deterministic
media inspection and stream selection; FFmpeg provides canonical local normalization and
optional deterministic enhancement. Work windows, checkpoint ordering, and resume remain
source-relative and provenance-bound.

Model acquisition is explicit and network-bearing. Managed model revisions are verified
and pinned before transcription; EchoFlow does not hide model download inside ASR.

The desktop Processing Center now productizes those authorities. A user can inspect machine
and model readiness, preflight a selected recording, choose outcome-oriented processing
intent, start supervised local work, follow durable job state, cancel a native child,
distinguish resume from fresh retry, and discard private execution state without deleting
published evidence or research. Python remains authoritative for planning, admission,
checkpoint compatibility, transcript correctness, model custody, and durable lifecycle;
Tauri owns allowlisted long-running child-process lifetime; React owns presentation and
explicit user intent.

## Canonical evidence and publication

Canonical JSON is authoritative transcript evidence. It retains source/execution
provenance, source-relative segment and word timing, language evidence, optional speaker
evidence, and optional enhancement provenance.

TXT, SRT, and WebVTT are deterministic publications. They are useful views, not transcript
authority. The original recording remains read-only during normal processing.

## Retrieval and verified navigation

The library has a database-neutral retrieval contract, DuckDB lexical projection,
BM25-style ranking, optional semantic chunks/embeddings, hybrid reciprocal-rank fusion,
and exact generation identity through `(document_id, canonical_sha256)`.

Search ranking and evidence navigation remain separate. A ranked passage becomes precise
evidence only after EchoFlow reopens the canonical transcript, verifies generation
identity, resolves exact segment/word coordinates, and returns a source-relative seek
coordinate.

## Durable research workspace

Authoritative SQLite owns notes, tags, collections, current evidence anchors, superseded
anchor history, and saved-search intent. A monotonic journal drives a rebuildable DuckDB
research projection. `ResearchWorkspaceService` composes those stores with verified
transcript retrieval.

The desktop supports note create/edit/delete, tag/collection navigation, exact-generation
note return, saved-search create/run/update/delete, stale/unavailable anchor review,
provenance-preserving same-source re-anchor, and the full typed Research search contract.
Saved questions persist intent, not result snapshots.

The UI no longer asks ordinary users to operate backend vocabulary directly. One **Match**
choice compiles Any words / All words / Exact phrase into the same typed search intent;
retrieval, ordering, filters, result count, and context are grouped under **Search options**.
Technical provenance remains inspectable without being the default interface.

## Safe deletion, refresh, and locations

`LibraryCustodyService` provides dry-run-first typed deletion. Confirmation is bound to the
exact canonical generation, requested/effective scopes, mutation set, and relevant
preserved dependencies. Source deletion requires explicit `source-recording`, a second
`--allow-source` switch, and current provenance verification.

Normal library refresh reconciles changed canonical generations without reopening every
unchanged transcript. Remembered transcript and recording locations persist explicit user
permission. Missing removable roots stay remembered but unavailable.

The default recording policy is manual. Discovery does not itself open, hash, probe, copy,
or transcribe candidate media.

## Desktop presentation and accessibility

The desktop architecture remains:

```text
EchoFlow Desktop
├── React + TypeScript + Vite     presentation
├── Tauri / Rust                  narrow native capability host
└── Python EchoFlow               application and evidence rules
```

The shell now has six skins: Archive, Midnight, Paper, Moss, Plum, and Ember. They share one
semantic token contract for surfaces, text, controls, focus, errors, selection, and accent
foregrounds. Theme selection is a compact persisted dropdown and remains presentation-only
state.

Every skin declares its browser light/dark `color-scheme`. Playwright checks the same
WCAG-oriented text and control contrast pairs across all themes and runs axe against real
Research controls. Components should not add theme-specific colors or assume that accent
buttons always use white text.

React still does not receive arbitrary shell, SQL/database, model-provider, or raw
evidence-path capability. Presentation convenience is not permission to move application
or custody policy into the webview.

# Capability → desktop productization audit

“Backend ready” means a tested application/CLI contract already exists. “Implemented” means
the first-release desktop workflow exists; it may still have polish or packaging work.

| Capability | Authority available today | Desktop today | Remaining product work | Planned slice |
|---|---|---|---|---|
| First-run initialization | private workspace/output allocation and config validation | source-build startup | storage-location onboarding, repair UX | Packaging / first run |
| Health diagnostics | doctor/system/resource checks | **implemented** in Processing readiness | richer repair guidance | Processing polish |
| Hardware/resource policy | effective CPU/RAM/accelerator inspection, profiles, admission | **implemented** in readiness + preflight | representative-device calibration | Device qualification |
| Managed model custody | inventory, recommendation, install, verification/revalidation/removal | **implemented** through Processing/native tasks | download-progress and offline polish | Processing polish |
| Native import and remembered locations | durable transcript/recording roots and discovery permissions | **implemented** | location management/forget polish | Settings / library polish |
| Recording discovery | side-effect-free candidate discovery | **implemented** | source availability polish | Library polish |
| Job lifecycle | durable status/progress/failure/resumability/discard | **implemented** in Processing | history/detail polish | Processing polish |
| Transcription planning | probe, stream, strategy, resource and disk admission | **implemented** preflight | presentation refinement | Processing complete |
| Transcription execution | local execution with checkpoints/resume | **implemented** through Tauri-supervised worker | packaged-runtime qualification | Packaging |
| Difficult-audio enhancement | deterministic FFmpeg suppression with provenance checks | **implemented** as explicit processing intent | explanation/result presentation | Transcript tools |
| Anonymous diarization | recording-scoped speaker evidence | **implemented** as explicit processing intent | speaker result presentation/management | Speaker tools |
| Speaker display labels | durable human names without biometric claims | labels appear in evidence | rename/manage speakers | Speaker tools |
| Canonical JSON authority | reproducible transcript + provenance | consumed by evidence views | provenance/details inspector | Transcript tools |
| TXT/SRT/WebVTT publication | deterministic derived exports | publication intent available in processing | destination/export management polish | Transcript tools |
| Lexical BM25 retrieval | private corpus ranking | **implemented** | ordinary-language polish complete in current tranche | Research/search complete |
| Semantic + hybrid retrieval | local semantic index + RRF | **implemented** in typed desktop controls when qualified | packaged dependency/model custody | Semantic qualification |
| Verified evidence navigation | generation verification, context, exact timing, seek | **implemented** | media playback | Playback |
| Unified discovery | transcript/note/tag/collection groups | **implemented** | optional object actions | Research/search complete |
| Research notes | exact-generation durable anchors/history | **implemented** | optional editing polish | Research/search complete |
| Tags and collections | durable relationships + rebuildable projection | **implemented** navigation/filter/assignment | dedicated management optional | Research polish |
| Saved searches | durable typed intent + current re-resolution | **implemented** whole-intent lifecycle | optional organization polish | Research/search complete |
| Safe deletion | typed dry-run plans + exact confirmation binding | none | custody review UI | Lifecycle UI |
| Retention | execution-state-only age policies | none | preview/settings/results | Lifecycle UI |
| Local source playback | verified source-relative coordinate exists | none | Tauri media capability and transport | Native playback |
| Themes/accessibility | semantic palette + browser presentation | **implemented** six-skin picker + contrast/axe matrix | representative OS native-control qualification | Desktop comprehension complete |
| Desktop packaging | Python wheel + source build | development Tauri shell | managed runtime, FFmpeg/native deps, installers | Packaging |
| Updates/uninstall | custody semantics defined | none | signed updates; uninstall never implies evidence deletion | Packaging |
| Backup/restore | authority boundaries identify irreplaceable state | none | manifest, restore/reconcile UX | Portability |
| Research export | stable evidence identities/coordinates exist | none | CSV/JSONL/Markdown selected export | Portability |
| Packaged semantic custody | dependency/model rules designed | advanced source-build capability | locked stack, immutable model, offline behavior | Semantic qualification |
| Representative hardware | resource-planning contracts exist | CI smoke | 8/16 GB, Apple Silicon, dGPU, 32/64 GB real-device qualification | Release qualification |

# Product critical path

## 1. Research/search complete

The first-release Research circuit is coherent: **find evidence → verify → annotate →
organize → save/replay a question → return to exact evidence → deliberately maintain an
anchor when necessary**. Phrase/ANY/ALL semantics, speaker/language/transcript constraints,
research filters, retrieval mode, sort, limits, context, saved whole-intent replacement,
and retrieval provenance all exist.

The current comprehension tranche changes presentation, not authority. Human choices are
compiled to the same typed request and Python continues to canonicalize, validate, derive
research scopes, execute retrieval, and select evidence generations.

## 2. Processing Center complete

The first Processing workflow now exists over readiness, model state, durable jobs,
preflight, explicit launch, native supervision, cancel, resume versus retry, and private
execution-state discard. See **[Processing Center](docs/architecture/processing-center.md)**.

“Complete” here means the first-release control loop exists. Packaging, representative
hardware, richer model-download presentation, and transcript/result tooling still remain.

## 3. Desktop comprehension + theme system complete

The desktop now uses ordinary search language, hides architecture-only labels from default
Research interactions, keeps advanced controls behind a clear disclosure, and places
retrieval provenance under Technical details.

The theme system has one registry, one semantic token contract, a compact six-skin picker,
local persistence, explicit browser light/dark schemes, centralized native form-control
theming, and automated contrast/accessibility qualification. See
**[Desktop themes and accessibility](docs/development/desktop-accessibility.md)**.

## 4. Transcript and speaker tools

Next, make produced evidence easier to inspect and manage without duplicating Processing
controls:

- speaker display-name editing while anonymous refs remain evidence identity;
- clearer language/speaker transcript presentation;
- selected audio-stream detail where multiple legitimate streams exist;
- publication/export destination workflow; and
- provenance/transcript details for troubleshooting and audit.

## 5. Native playback

Let the existing verified source-relative coordinate drive local audio/video without giving
React arbitrary path authority. Rust owns file/media capability; Python owns source identity
and evidence rules; the webview receives playback state and safe coordinates.

Qualification includes moved/unavailable sources, source mismatch, keyboard transport,
reduced motion, long media, and seeking around exact word boundaries.

## 6. Lifecycle + retention UI

Productize existing custody contracts before a packaged app invites large local corpora:

- dry-run deletion plan review;
- plan-bound confirmation;
- explicit source/canonical/research/export/execution scopes;
- source-recording second guard; and
- retention preview/result state.

## 7. Architecture/redundancy audit

Do this **before packaging freezes seams**. Audit bridge DTOs, Pydantic request models,
React client glue, serializers, service composition, fixtures, Tauri supervisor patterns,
stale compatibility paths, and duplicated documentation. Refactor where policy is repeated
or ownership is unclear, not merely where two files look similar.

## 8. Packaging + first run + update/uninstall

Ship a managed Python runtime/sidecar, FFmpeg/native dependencies, Windows/macOS/Linux
delivery, storage-location onboarding, signed updates, and evidence-safe uninstall
semantics.

## 9. Backup/restore + research portability

Back up canonical evidence and authoritative research, rebuild projections on restore,
reconcile machine-local paths, and export selected research with stable evidence identities.

## 10. Packaged semantic custody

Lock and qualify embedding dependencies, immutable model acquisition, private cache/offline
behavior, corpus compatibility, and upgrade semantics as an ordinary product feature.

## 11. Representative-device qualification

Qualify 8 GB Windows, 16 GB commodity systems, Apple Silicon, dGPU laptops, 32/64 GB
systems, Unicode/long paths, external disks, low disk, crashes, interrupted downloads,
offline use, upgrades/reinstall, display scaling, native controls, keyboard use, and
accessibility.

# Later research-native work

Snapshots/diffs, REFI-QDA interoperability, evidence packets, comparison workspaces,
evidence-linked writing/script boards, portable research bundles, and live provisional
capture remain intentionally separate from the first-release critical path. See
**[Post-MVP research roadmap](docs/post-mvp-roadmap.md)**.

The sequencing rule remains simple: do not add a larger research superstructure while the
ordinary desktop still lacks playback, lifecycle UI, packaging, portability, and real-device
qualification.
