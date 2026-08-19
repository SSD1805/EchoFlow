# EchoFlow roadmap 🗺️✨

EchoFlow is becoming a **private local workspace for recorded evidence**.

Its job is not to out-engine every speech-recognition runtime. Its job is to make local
transcription dependable, resumable, inspectable, searchable, navigable, annotatable, and
portable on ordinary computers while keeping source evidence and human-authored knowledge
under clear custody.

Modern EchoFlow restarted on August 2, 2026. The project has moved from “can we transcribe
a file?” through a substantial backend foundation and into the first real desktop evidence
workflows.

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
    N --> O[Research workspace UI]
    O --> P[Local media playback]
    P --> Q[Desktop packaging]
    Q --> R[Backup restore portability]
    R --> S[Release qualification]

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
    class O,P,Q,R,S process
```

Text fallback: EchoFlow already spans local media, reliable transcription, canonical
evidence, retrieval, verified navigation, durable research, lifecycle controls, incremental
refresh, remembered locations, and the first desktop import/search/evidence-reader
surfaces. The next work turns the existing research authority into a real desktop
workspace, then adds local playback, packaging, portability, and release qualification.

# What is foundation now

The word **foundation** below means the contract exists in code and is protected by tests.
It does not mean the feature is fully productized for a non-technical end user.

## Local execution, media, and model custody

EchoFlow inspects process-visible CPU/memory, physical accelerator topology, and engine
capabilities before admitting a concrete local strategy. FFprobe provides deterministic
media inspection and stream selection; FFmpeg provides canonical local normalization and
optional deterministic enhancement. Work windows, checkpoint ordering, and resume remain
source-relative and provenance-bound.

Model acquisition is explicit and network-bearing. Managed model revisions are verified
and pinned before transcription; EchoFlow does not hide model download inside ASR.

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

Authoritative SQLite owns notes, tags, collections, evidence anchors, and saved-search
intent. A monotonic journal drives a rebuildable DuckDB research projection.
`ResearchWorkspaceService` composes those stores with verified transcript retrieval.

Saved searches are durable questions, not result snapshots. Tags/collections and note text
can constrain eligible evidence before transcript ranking.

The custody hierarchy is:

| Class | Examples | Rule |
|---|---|---|
| Authoritative evidence | original recording, canonical JSON | never treat as cache; destructive deletion must be explicit |
| Authoritative human knowledge | speaker labels, notes, tags, collections, saved searches | must survive index rebuilds and unrelated deletion |
| Durable app preference | remembered library/recording locations and processing policy | private user-state; forgetting permission never deletes user files |
| Rebuildable projection | lexical/semantic/research DuckDB, derived exports | may be regenerated |
| Private execution state | checkpoints, normalization/enhancement intermediates | lifecycle-managed; not source truth |
| Lightweight lifecycle metadata | job manifests/discovery pointers | retained when heavyweight execution state is cleaned |

## Safe deletion and retention

`LibraryCustodyService` provides dry-run-first typed deletion. Confirmation is bound to the
exact canonical generation, requested/effective scopes, mutation set, and relevant
preserved dependencies. Source deletion requires explicit `source-recording`, a second
`--allow-source` switch, and current provenance verification.

`canonical-transcript` expands only through disposable descendants. It does **not** imply
notes, saved searches, or source deletion. Age-based retention is narrower still and can
remove only eligible private execution workspaces.

EchoFlow does not claim secure erasure where SSD wear levelling, snapshots, backups,
copy-on-write history, or sync/versioning make that guarantee unverifiable.

## Incremental refresh and durable locations

Normal library refresh reconciles changed canonical generations without reopening every
unchanged transcript. Metadata is a cheap change detector; canonical SHA-256 remains the
generation authority. `--verify` deliberately reopens and rehashes tracked canonicals.

Remembered locations have one explicit purpose: transcript-library reconciliation or
recording-source candidate discovery. Missing removable roots stay remembered but are
reported unavailable. Recording discovery does not itself hash, FFprobe, copy, transcribe,
or modify media.

The default recording policy is manual. `automatic` is durable permission metadata only;
no background daemon silently processes recordings today.

## Desktop foundation and import

The desktop architecture is:

```text
EchoFlow Desktop
├── React + TypeScript + Vite     presentation
├── Tauri / Rust                  narrow native capability host
└── Python EchoFlow               application and evidence rules
```

The current shell provides Archive/Midnight themes, keyboard-visible navigation, native
file/folder selection, one-time versus remembered import choices, recording discovery,
and transcript refresh. React does not receive arbitrary shell, database, or filesystem
mutation capability.

## Library discovery and evidence reader

The Library surface now has grouped discovery across transcript evidence, notes, tags, and
collections. It does not fabricate one relevance score across unlike object types.

A search result can open a verified canonical context window. Backend-justified matched
words retain exact source-relative timing; selecting a canonical word moves an evidence
cursor, and “Return to match” restores the backend-verified seek coordinate. Raw source
and canonical filesystem paths stay out of the webview.

# Current quality contract

Current CI is staged so cheap failures stop expensive runners. The repository protects:

- locked Python and frontend dependency graphs;
- Mermaid syntax and the approved EchoFlow diagram palette;
- Ruff lint/format/security, strict mypy, Vulture, and Radon;
- compensated dependency-advisory scope checks and dependency audit;
- repository-wide branch coverage at the unchanged 90% gate;
- frontend type checking, production build, dependency audit, and raw-HTML guard;
- Playwright interaction and axe accessibility tests;
- full macOS and Windows platform smoke;
- distribution builds and clean-wheel installation.

Historical PR-specific test counts belong in historical records. The roadmap tracks
behavioral gates rather than a number that becomes stale with the next test.

# Near-term product sequence

## 1. Research workspace UI

The research authority already exists in Python. The next tranche should make it usable
from the desktop without creating a second frontend data model.

The first Research slice should:

- enable the Research navigation door;
- browse authoritative notes, tags, collections, and saved searches;
- distinguish current evidence anchors from older canonical generations;
- create a note from a verified evidence window;
- edit/delete notes and assign/remove tags and collections;
- create, run, rename, and delete saved searches;
- navigate a research object back to verified current evidence when possible; and
- keep every operation inside narrow versioned desktop bridge methods with no frontend SQL
  or direct SQLite access.

Advanced typed search controls for phrase/ANY/ALL, speaker, language, transcript,
research filters, retrieval mode, and sort belong in this same Library/Research journey.

## 2. Local media playback behind Tauri capability

The evidence reader already has a verified source-relative cursor. The next native media
step should let that coordinate drive audio/video playback without handing an arbitrary raw
path to React.

Rust should own file capability and media lifecycle. Python should continue to own source
identity/evidence rules. The webview should receive playback state and safe coordinates,
not general filesystem authority.

Qualification includes unavailable/moved sources, source-generation mismatch, keyboard
transport, reduced motion, long media, and seeking around word boundaries.

## 3. Desktop packaging, first run, updates, and uninstall

A Python wheel proves EchoFlow is distributable to Python. It does not make EchoFlow a
consumer desktop application.

Produce deliberate delivery paths for:

- a normal Windows installer/application entry point;
- a signed/notarized macOS application bundle and installer/disk-image flow; and
- an intentional Linux desktop package.

Packaging must account for the Tauri host, managed Python runtime/sidecar, FFmpeg/FFprobe,
native transcription dependencies, model custody, migrations, updates, and uninstall.

**Uninstalling EchoFlow must not silently delete canonical transcripts or authoritative
human research state.** Program removal and user-data destruction are different operations.

## 4. Backup, restore, and research portability

Back up what is irreplaceable: canonical evidence, research SQLite state, saved searches,
speaker labels, and other durable human state. Rebuildable DuckDB projections should be
regenerated rather than promoted to backup authority.

Remembered absolute paths are machine-local preferences. Export them as reviewable metadata
and require explicit reconciliation/reapproval on another machine.

Selected research export should target CSV, JSON/JSONL, and Markdown while retaining
document/generation identity, segment IDs, and numeric evidence coordinates.

## 5. Semantic dependency and embedding custody qualification

Before semantic retrieval is advertised as a normal packaged capability, qualify one
locked optional dependency set with managed immutable embedding-model acquisition, private
cache placement, disk/resource admission, no silent search-time download, offline use after
installation, and packaged-platform qualification.

## 6. Representative-device release qualification

Exercise real corpora and the packaged app on 8 GB Windows, 16 GB commodity hardware,
Apple Silicon, a discrete-GPU laptop, and 32/64 GB workstations. Measure real-time factor,
cold/warm model behavior, thermal/memory pressure, private disk cost, enhancement benefit,
embedding build cost, refresh cost, query latency, and GUI responsiveness.

Also cover Unicode/space-heavy paths, external drives, permission failures, low disk,
interrupted downloads, crash/resume, upgrade migrations, uninstall/reinstall, offline
operation, keyboard/accessibility use, corruption/recovery, location disappearance and
reappearance, and one-time versus remembered import.

# Conditional later capabilities

## Deeper original-media clock qualification

Only add production/media-clock mapping when real recordings require it: non-zero stream
origins, rational frame/timecode rates, drop-frame semantics, PTS/DTS mapping, and explicit
synchronization across independent sources.

## Speech/source separation for overlapping speakers

Source separation remains later than honest overlap representation. It adds substantial
compute/model custody, uncertainty, derived-audio provenance, and failure modes. It should
demonstrate measurable recognition benefit before entering the normal path.

## Typed query evolution

Natural-language query assistance may eventually compile into the stable typed
`SearchQuery`/research-filter contract, but it must remain inspectable and must not turn an
LLM interpretation into hidden retrieval authority.

# Pre-1.0 meaning

The pre-1.0 milestone is not “the tests pass from a checkout.” It is:

> A normal person can install EchoFlow, understand first run, process sensitive recordings,
> search and annotate their evidence, recover from common failure, move or back up durable
> work, update the app safely, and remove the program without losing evidence.

That is the finish line the roadmap is walking toward.
