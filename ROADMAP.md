# EchoFlow roadmap 🗺️✨

EchoFlow is becoming a **private local workspace for recorded evidence**. Its job is not to out-engine every speech-recognition runtime. Its job is to make local transcription dependable, resumable, inspectable, searchable, navigable, annotatable, portable, and safe on ordinary computers while keeping source evidence and human-authored knowledge under clear custody.

Modern EchoFlow restarted on August 2, 2026. The project has moved from “can we transcribe a file?” through a substantial backend foundation into a native desktop that can import, process, search, verify, annotate, inspect speakers/provenance, publish derived transcript views, and play exact verified source evidence. This roadmap is a productization map, not a class inventory.

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

Text fallback: EchoFlow already spans local media, reliable transcription, canonical evidence, lexical/semantic/hybrid retrieval, verified navigation, durable research, lifecycle contracts, incremental refresh, remembered locations, native import, Processing, Library, Research, transcript/speaker tools, verified native playback, and an accessible multi-theme shell. The next first-release work is lifecycle UI, architecture cleanup, packaging, portability, packaged semantic custody, and real-device qualification.

# First-release foundation now

“Foundation” means the authority exists in code and is protected by tests. It does not mean installers and representative-device qualification are finished.

## Local processing and model custody

EchoFlow inspects effective CPU/memory and accelerator topology before admitting a local strategy. FFprobe owns deterministic media inspection and stream selection; FFmpeg owns canonical normalization and optional deterministic enhancement. Managed model revisions are explicit, verified, and pinned before transcription.

The Processing Center presents readiness, model state, preflight, supervised start/cancel, durable job status, checkpoint resume, fresh retry, and private execution-state discard. Python remains authoritative for planning, admission, model custody, resume compatibility, and transcript correctness. Tauri owns allowlisted long-running child-process lifetime. React submits intent and presents state.

## Canonical evidence and transcript tools

Canonical JSON is authoritative transcript evidence. It retains source/execution provenance, source-relative segment and word timing, language evidence, optional anonymous speaker evidence, and enhancement provenance. TXT, SRT, and WebVTT are deterministic publications, not transcript authority.

The desktop transcript-tools tranche is now implemented. Library results can open generation-bound tools for:

- transcript/source availability and provenance details;
- selected audio-stream inspection;
- human display-name editing while anonymous speaker refs remain visible;
- speaker-aware reading with explicit overlap/mixed/unattributed states; and
- post-hoc TXT/SRT/WebVTT publication to a native-selected destination.

Every transcript-tool operation carries `(document_id, canonical_sha256)`. Python refuses stale generations rather than letting a long-lived UI silently mutate newer speaker numbering. Tauri exposes a fixed transcript-tools command and Python bridge allowlist; React never parses canonical JSON or receives canonical/source paths.

See **[Transcript and speaker tools](docs/transcript-tools.md)** and **[Speaker display names](docs/speaker-names.md)**.

## Verified native playback

The desktop can now play the original local audio/video from the same verified source-relative cursor used by evidence navigation.

Playback is generation-bound rather than path-driven. React submits `(document_id, canonical_sha256, seek_seconds)`. Python verifies canonical bytes, source identity, current source SHA-256/size, duration bounds, and audio-stream identity. Rust opens only the approved source, narrows the verification/open race with metadata checks, stores the opened file behind an opaque active-session ID, and serves bounded `GET`/`HEAD` byte ranges through a dedicated `echoflow-media` protocol.

The webview never receives the source/canonical path and cannot call the private Python playback bridge. Multi-audio sources fail closed until native track selection can prove that the rendered track matches the one canonical evidence says was transcribed. Decoder availability remains an OS/WebView qualification issue, not evidence authority.

See **[Verified native playback](docs/native-playback.md)**.

## Retrieval and durable research

The library has a database-neutral retrieval contract, DuckDB lexical projection, BM25-style ranking, optional semantic chunks/embeddings, hybrid reciprocal-rank fusion, and exact-generation evidence identity.

Search ranking and evidence navigation remain separate. A ranked passage becomes precise evidence only after EchoFlow verifies canonical generation and resolves exact segment/word coordinates.

Authoritative SQLite owns notes, tags, collections, anchor history, and saved-search intent. DuckDB research/search state is rebuildable. The desktop supports note create/edit/delete, tag/collection navigation, saved-search lifecycle, typed Research search, exact-generation return, and explicit stale-anchor review/re-anchor.

## Safe lifecycle and locations

Deletion is dry-run-first and plan-bound. Source-recording deletion requires its own explicit guard and provenance verification. Retention is intentionally narrower and may remove old private execution work without silently deleting canonical transcripts, source media, or human research.

Remembered recording/transcript locations are durable permissions. Recording discovery itself does not hash, probe, copy, or transcribe candidate media. Automatic processing remains a separate explicit policy.

## Desktop presentation and accessibility

The desktop architecture remains:

```text
EchoFlow Desktop
├── React + TypeScript + Vite     presentation
├── Tauri / Rust                  narrow native capability host
└── Python EchoFlow               application and evidence rules
```

The shell now has eight skins: **Archive, Midnight, Paper, Moss, Plum, Ember, Pride, and Monochrome**. All use one semantic token contract for surfaces, text, controls, focus, errors, selection, and accent foregrounds. Pride's rainbow is decorative-only; Monochrome is deliberately grayscale. Theme preference is local presentation state and never evidence/research state.

Playwright iterates every registered skin through WCAG-oriented contrast pairs, real native-style controls, browser `color-scheme`, and axe. See **[Desktop themes and accessibility](docs/development/desktop-accessibility.md)**.

# Capability → desktop audit

| Capability | Authority | Desktop status | Remaining first-release work |
|---|---|---|---|
| Machine/resource policy | Python runner/admission | implemented | representative-device calibration |
| Model custody | verified pinned managed revisions | implemented | progress/offline/package polish |
| Import/locations | durable permissions/discovery | implemented | settings/forget polish |
| Processing | plan, execute, checkpoint, resume/retry | implemented | packaging/device qualification |
| Enhancement/diarization intent | Python plan/execution | implemented | result polish continues through transcript view |
| Canonical JSON | authoritative evidence | implemented consumer views | packaging/backup |
| Speaker labels | generation-bound human state | **implemented desktop management** | optional dedicated organization polish |
| Speaker transcript | backend derived presentation | **implemented** | playback-linked reading available through evidence view |
| Provenance/details | canonical verified inspection | **implemented** | richer troubleshooting optional |
| TXT/SRT/WebVTT | deterministic derived publication | **implemented post-hoc desktop flow** | optional export organization |
| Lexical/semantic/hybrid search | private retrieval | implemented | packaged semantic custody |
| Verified evidence navigation | exact generation + timing/seek | implemented | representative-device playback qualification |
| Notes/tags/collections | SQLite authority | implemented | optional management polish |
| Saved searches | durable typed intent | implemented | optional organization polish |
| Safe deletion/retention | typed plan-bound backend | backend ready | **desktop lifecycle UI next** |
| Native source playback | generation/source authorization + Rust session | **implemented** | decoder/device qualification; future proven multi-track selection |
| Themes/accessibility | semantic palette + browser/native controls | **8 skins qualified** | representative OS/forced-colors checks |
| Frontend tests | strict TS/build + Playwright/axe | primary surfaces + playback covered | grow with features, avoid duplicated backend policy |
| Packaging | Python wheel + source Tauri | development only | managed runtime/installers/update/uninstall |
| Backup/restore | authority boundaries known | none | manifest/reconcile/restore UI |
| Representative hardware | policy contracts + platform CI | partial | real 8/16 GB, Apple/dGPU/high-DPI qualification |

# Product critical path

## 1. Research/search complete

The first-release Research circuit is coherent: find evidence → verify → annotate → organize → save/replay a question → return to exact evidence → deliberately maintain an anchor when necessary.

## 2. Processing Center complete

The first Processing control loop exists over readiness, model state, durable jobs, preflight, launch, native supervision, cancel, resume versus retry, and private-state discard.

## 3. Desktop comprehension + theme system complete

Ordinary users see human search language rather than Python/database vocabulary. The theme system has one registry, semantic tokens, local persistence, explicit browser schemes, native-control theming, and eight-skin contrast/a11y qualification.

## 4. Transcript and speaker tools complete

The first desktop transcript-inspection loop now exists. Generation-bound backend services own speaker names, overlap-aware presentation, provenance/details, and deterministic post-hoc publication. The React layer submits intent and never becomes canonical authority.

Frontend coverage explicitly spans Intake, Processing, Library/evidence, transcript tools, Research/search/anchor maintenance, themes, development mode, hostile text rendering, path non-disclosure, and accessibility. Backend decision-heavy transcript tools also have property tests and a dedicated targeted Poodle workflow. See **[Frontend testing strategy](docs/development/frontend-testing.md)**.

## 5. Native playback complete

Verified source-relative evidence coordinates now drive local audio/video without giving React arbitrary path authority. Python owns generation/source/stream authorization. Rust owns the opened file handle, opaque session lifetime, and bounded local-media transport. React receives only safe playback state and coordinates.

Qualification covers stale/missing/changed sources, exact word coordinates, preserved older generations, keyboard preparation, path non-disclosure, audio/video presentation, multi-audio refusal, native range parsing, session-token allowlisting, and bounded streaming. A targeted playback Poodle workflow challenges the Python authorization decisions.

## 6. Lifecycle + retention UI ← next

Productize the existing custody contracts before a packaged app invites large local corpora: dry-run plan review, plan-bound confirmation, explicit scopes, source-recording second guard, and retention preview/result state.

The UI must not invent deletion semantics. Python already owns scope expansion, provenance checks, confirmation tokens, source-recording protection, and retention exclusions. The desktop tranche should expose those decisions clearly while keeping filesystem mutation out of React.

## 7. Architecture/redundancy audit

Do this before packaging freezes seams. Audit bridge DTOs, Pydantic models, React client glue, serializers, service composition, fixtures, Tauri supervisor/media patterns, stale compatibility paths, and duplicated documentation. Refactor policy duplication or unclear ownership, not merely similar-looking files.

## 8. Packaging + first run + update/uninstall

Ship a managed Python runtime/sidecar, FFmpeg/native dependencies, Windows/macOS/Linux delivery, storage onboarding/repair, signed updates, and evidence-safe uninstall semantics.

## 9. Backup/restore + research portability

Back up canonical evidence and authoritative research, rebuild projections on restore, reconcile machine-local paths, and export selected research with stable evidence identity.

## 10. Packaged semantic custody

Lock/qualify embedding dependencies, immutable model acquisition, private cache/offline behavior, corpus compatibility, and upgrade semantics as an ordinary product feature.

## 11. Representative-device qualification

Qualify 8 GB Windows, 16 GB commodity systems, Apple Silicon, dGPU laptops, 32/64 GB systems, Unicode/long paths, external disks, low disk, crashes, interrupted downloads, offline use, upgrades/reinstall, scaling, native controls, media codecs, keyboard use, forced colors, and accessibility.

# Later research-native work

Snapshots/diffs, REFI-QDA interoperability, evidence packets, comparison workspaces, evidence-linked writing/script boards, portable research bundles, and live provisional capture remain intentionally separate from the first-release path.

The sequencing rule remains simple: do not build a larger research superstructure while the ordinary desktop still lacks lifecycle UI, packaging, portability, and real-device qualification.
