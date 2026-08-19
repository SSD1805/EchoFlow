# EchoFlow roadmap 🗺️✨

EchoFlow is becoming a **private local workspace for recorded evidence**.

Its job is not to out-engine every speech-recognition runtime. Its job is to make local
transcription dependable, resumable, inspectable, searchable, navigable, annotatable, and
portable on ordinary computers while keeping source evidence and human-authored knowledge
under clear custody.

Modern EchoFlow restarted on August 2, 2026. The project has moved from “can we transcribe
a file?” to “can a person build, research, and safely maintain a private evidence library
without giving the corpus away?”

![EchoFlow product roadmap](docs/diagrams/product-roadmap.svg)

<details>
<summary>Mermaid source</summary>

```mermaid
graph LR;
    A[Local media] --> B[Reliable local transcription]
    B --> C[Canonical evidence]
    C --> D[Lexical semantic hybrid retrieval]
    D --> E[Verified evidence navigation]
    E --> F[Durable research workspace]
    D --> G[Unified discovery]
    F --> G
    G --> H[Saved searches and derived navigation]
    H --> I[Safe deletion and retention]
    I --> J[Incremental refresh]
    J --> K[Durable library locations]
    K --> L[Tauri React desktop foundation]
    L --> M[Import search evidence research UI]
    M --> N[Desktop packaging and first-run]
    N --> O[Backup restore and portability]
    O --> P[Release qualification]
```

</details>

Text fallback: EchoFlow progresses from local media through reliable local transcription, canonical evidence, retrieval, verified navigation, durable research, discovery, safe lifecycle controls, incremental refresh, desktop workflows, packaging, portability, and release qualification.

# Current foundation

The backend is broad enough that near-term work should improve **human workflow,
qualification, delivery, and ordinary-library ergonomics**, not reopen solved custody or
search contracts.

## Local execution and media processing

EchoFlow currently provides process-visible CPU/memory inspection, physical accelerator
topology, resource-admitted faster-whisper strategies, deterministic FFprobe inspection,
audio-stream selection, canonical mono 16 kHz PCM16 normalization when needed, exact work
windows, optional deterministic noise suppression with provenance, and bounded preparation
overlap while preserving checkpoint order.

Performance ranks and memory estimates remain conservative heuristics pending broader
representative-device qualification.

## Reliability, model custody, and timeline evidence

The execution contract includes explicit model inventory/recommendation/installation,
immutable resolved model revisions, no silent ASR model download during transcription,
private checkpoints and validated resume, source/model/stream/preprocessing/execution
binding, source-relative word timestamps, deterministic elapsed-time presentation, and
source-declared temporal metadata when FFprobe reports it.

Numeric source-relative seconds remain authoritative navigation coordinates. Human clock
strings are presentation.

## Language and speaker evidence

EchoFlow supports multilingual decoding, conservative local language attribution, optional
recording-scoped anonymous diarization, deterministic speaker refs, word-level speaker
projection where timing supports it, overlap-aware presentation, and durable human display
labels without biometric identity inference or silent cross-recording linkage.

The pyannote execution path remains security-held while its locked Lightning dependency is
affected by the compensated advisory documented in `SECURITY.md`.

## Canonical transcript and publications

Canonical JSON is authoritative transcript evidence with source/execution provenance,
source-relative timestamps, language evidence, optional enhancement provenance, and
optional speaker evidence.

By default, public artifacts live under the platform Downloads `EchoFlow/` directory. A
transcription can choose `--output-dir`, and an explicit EchoFlow configuration may define
`ECHOFLOW_OUTPUT_DIR`.

TXT, SRT, and WebVTT are deterministic derived publications. They are not transcript
authority.

## Transcript library, retrieval, and evidence navigation

The local library includes a database-neutral lexical contract, DuckDB document/segment/
term projections, deterministic BM25-style ranking, phrase/ANY/ALL and typed filters,
canonical/source SHA-256 identity, deterministic semantic chunks, strict-local E5
embeddings, reciprocal-rank hybrid retrieval, stale-vector refusal, verified canonical
navigation, aligned-word highlighting where justified, neighboring context, and stable
source seek coordinates.

Search ranking and evidence navigation remain separate. An index ranks a passage;
navigation verifies the canonical evidence before presenting precision.

`echoflow library rebuild` reads existing canonical JSON and rebuilds discovery/index
projections. It never re-runs ASR.

## Durable research workspace

Authoritative SQLite owns notes, tags, collections, evidence anchors, and saved-search
intent. Exact canonical generation identity is retained in anchors. A monotonic
transactional journal drives a rebuildable DuckDB research projection with bounded,
idempotent replay and fail-closed convergence rules.

`ResearchWorkspaceService` is the shared application seam for CLI and future GUI adapters.
Research filters apply before transcript ranking when they define eligible evidence.

The custody hierarchy is:

| Class | Examples | Rule |
|---|---|---|
| Authoritative evidence | original recording, canonical JSON | never treat as cache; destructive deletion must be explicit |
| Authoritative human knowledge | speaker labels, notes, tags, collections, saved searches | must survive index rebuilds and unrelated deletion |
| Durable app preference | remembered library/recording locations and processing policy | private user-state; forgetting permission never deletes user files |
| Rebuildable projection | lexical/semantic/research DuckDB, derived exports | may be regenerated |
| Private execution state | checkpoints, normalization/enhancement intermediates | lifecycle-managed; not source truth |
| Lightweight lifecycle metadata | job manifests/discovery pointers | retained when heavyweight execution state is cleaned |

## Unified discovery, saved searches, and navigation

`echoflow library find QUERY` returns typed transcript, note, tag, and collection groups
without fabricating one cross-type relevance score.

Saved searches are durable **questions**, not result snapshots. They preserve typed query
semantics and explicitly refuse derived `evidence_scope`; replay re-resolves current
research relationships and current canonical evidence.

Frequent/recent tag and collection navigation is derived from current relationships. It
does not create authoritative popularity counters.

## Safe deletion and retention controls

This is now **foundation**.

`LibraryCustodyService` provides a plan-first typed deletion system. The CLI is a dry run
unless the exact plan token is returned with `--confirm`:

```bash
echoflow library delete TRANSCRIPT_ID --scope library-view
echoflow library delete TRANSCRIPT_ID --scope canonical-transcript
echoflow library delete TRANSCRIPT_ID --scope research-notes
echoflow library delete TRANSCRIPT_ID --scope saved-searches
echoflow library delete TRANSCRIPT_ID --scope source-recording --allow-source
echoflow library retention --execution-days 30
```

Deletion scopes separate:

- active-library membership/rebuildable retrieval state;
- regenerable TXT/SRT/VTT publications;
- private checkpoints/intermediates;
- canonical transcript evidence;
- notes attached to the exact canonical generation;
- saved searches explicitly constrained to the transcript; and
- the original recording.

`canonical-transcript` expands only across disposable descendants: library view, derived
publications, and private execution state. It does **not** imply note, saved-search, or
source deletion.

A confirmation token binds the exact canonical generation, requested/effective scopes,
mutation set, and relevant preserved note/saved-search dependency list. Canonical bytes are
re-hashed before mutation. Source deletion requires a second explicit switch and current
source bytes must still match transcription provenance.

Age-based retention is intentionally narrower. It deletes only old private job workspaces;
completed jobs are eligible by default, failed/interrupted jobs require
`--include-incomplete`, and running jobs are never eligible. Canonical evidence, human
research, source media, and lightweight lifecycle manifests survive retention cleanup.

EchoFlow does not claim secure erasure on storage where SSD wear levelling, snapshots,
copy-on-write history, backups, or sync/versioning make that guarantee unverifiable.

See `docs/architecture/safe-deletion-retention.md` and
`docs/architecture/library-lifecycle.md` for exact semantics.

## Incremental library refresh

This is now **foundation**.

`echoflow library refresh` reconciles the currently discoverable canonical corpus against
the rebuildable lexical index without rewriting unchanged transcript generations.
Generation identity remains `(document_id, canonical_sha256)`.

Normal refresh uses stored canonical size and modification time only as a cheap change
detector. If the signature and tracked source path are unchanged, the canonical JSON is
not opened. If a candidate changed, EchoFlow re-reads and re-hashes that canonical before
planning the lexical delta. `--verify` deliberately bypasses the metadata fast path and
re-hashes/schema-validates every tracked canonical transcript.

The lexical delta is applied atomically:

```text
new generation       -> upsert
changed generation   -> replace/upsert
removed transcript   -> remove
unchanged transcript -> skip
```

Tracked external imports remain discoverable while their indexed path exists, moved
canonicals can be reconciled when the old path is gone, and duplicate live paths for one
document identity fail closed. Corrupt tracked canonical state also fails closed before
lexical mutation.

The current semantic index remains whole-corpus/fingerprint bound. A refresh that changes
semantic-relevant corpus identity invalidates the semantic projection rather than leaving
stale vectors behind. Timestamp-only metadata churn with identical canonical bytes does
not discard valid embeddings.

The regression contract is deterministic rather than timing-based:

```text
100 unchanged tracked transcripts -> 0 canonical reads
1 changed transcript               -> 1 canonical read
```

Full `library rebuild` remains the explicit repair/recovery lever. A normal user should not
need to rebuild a database merely because one new transcript appeared.

See `docs/architecture/incremental-library-refresh.md` for the exact reconciliation and
verification contract.

## Durable library locations and recording discovery

This is the current backend foundation immediately before the desktop client.

`LibraryLocationService` owns private, schema-versioned remembered directory preferences
without making filesystem paths part of the search index or research database. A remembered
location has one explicit purpose:

- `transcript-library` means that the directory may be revisited for canonical transcript
  reconciliation through the existing incremental refresh service; or
- `recording-source` means that the directory may be revisited for cheap local recording
  candidate discovery.

The default recording policy is `manual`. An `automatic` policy is an explicit opt-in
permission marker for a future application lifecycle adapter; setting it does not itself
run ASR. Discovery never hashes, FFprobes, copies, transcribes, or modifies a recording.
Actual processing must continue through the existing transcription planner, resource
admission, model custody, checkpoint, and execution contracts.

Temporarily unavailable roots, such as unplugged external drives, are reported as offline
without deleting their durable permission record. Forgetting a location only removes the
permission record and never deletes user files. EchoFlow private state/cache/model paths
cannot be registered, and the configured output directory remains an implicit transcript
root rather than a redundant remembered location.

This tranche intentionally does not add a background daemon or filesystem watcher. Desktop
startup, explicit Refresh, and post-transcription lifecycle points are sufficient triggers
until real usage justifies always-on observation. See
`docs/architecture/library-locations.md`.

## Test/quality debt repaired after saved-search merge

The saved-search/navigation PR was merged while its Linux branch-coverage gate was still
below the repository threshold even though all 1,000 tests passed. The subsequent safe
lifecycle tranche added the missing edge/failure and human-rendering tests instead of
lowering the 90% requirement.

Coverage additions exercise invalid durable saved-search objects, storage bounds, corrupt
persisted state, missing mutation targets, closed navigation dispatch, human CLI rendering,
and safe missing-state behavior. The custody tranche adds its own positive, negative,
stale-plan, provenance, partial-state, and retention tests.

# Near-term product sequence

## 1. Tauri + React desktop foundation and import experience

The frontend should be a thin local desktop adapter over the application services already
built. The target stack is Tauri for the small native host, React + TypeScript + Vite for
the presentation layer, and Playwright plus accessibility automation from the first UI PR.

The first desktop slice should establish:

- the native Tauri application shell on Windows, macOS, and Linux;
- a React/TypeScript design system with semantic theme tokens;
- Archive and Midnight baseline skins, with richer optional skins remaining cheap to add;
- keyboard-first navigation, visible focus, reduced-motion support, accessible names and
  landmarks, and automated Playwright/axe coverage;
- a narrow versioned IPC boundary where Rust owns desktop/process capability and Python
  continues to own EchoFlow business logic; and
- no direct frontend access to DuckDB, SQLite, arbitrary shell execution, or arbitrary
  filesystem mutation.

Import is the first human workflow. The GUI should support both one-time and remembered
choices:

```text
Choose files…
Choose folder…

Use this location:
(•) Just this time
( ) Remember this folder

For remembered recording sources only:
[ ] Automatically process new recordings
```

The automatic option is advanced opt-in and defaults off. The UI consumes
`LibraryLocationService`; it does not persist paths or invent scan policy in TypeScript.

For raw recordings, import flows into the existing media probe/planner and may show file,
container, duration, audio-stream choices, resource estimates, and model requirements
before execution. For existing canonical transcripts, import/remembered transcript roots
flow into incremental library refresh. Neither path copies the user's original source merely
because it was selected.

No always-on watcher or background daemon is required for the first desktop release.
Application startup, explicit Refresh, and successful transcription are sufficient bounded
lifecycle triggers.

## 2. Search, evidence navigation, media, and research workspace UI

Once the desktop/import chassis is stable, expose the existing research engine rather than
building a second frontend search architecture.

The graphical slice should provide:

- Susan-style global search with no database knowledge required;
- advanced typed search over phrase/ANY/ALL, speaker, language, transcript, tag,
  collection, note, retrieval-mode, and sort constraints;
- grouped unified discovery across transcripts, notes, tags, and collections;
- verified result navigation back to canonical segment/word coordinates;
- click-to-seek source-relative audio/video playback with justified word highlighting;
- notes, tags, collections, speaker display labels, and saved searches;
- explicit refresh/verification state; and
- the same typed deletion/retention plans already enforced by the backend.

An expert SQL/data-lab surface, if added later, should be a hardened read-only projection
feature. Raw SQL is not the ordinary advanced-search contract and must never expose mutable
research authority directly.

## 3. Desktop packaging, first-run setup, updates, and uninstall

A Python wheel proves EchoFlow is distributable to Python. It does not make EchoFlow a
consumer desktop application.

Produce an intentional desktop delivery path for supported platforms:

- a normal Windows installer/application entry point;
- a signed/notarized macOS application bundle and normal installer/disk-image flow; and
- a deliberate Linux desktop package rather than requiring a repository clone.

The package must account for the Tauri host, managed Python runtime/sidecar, FFmpeg/FFprobe,
native transcription runtime dependencies, application assets, and optional capabilities
without requiring the user to assemble a developer environment.

First run should initialize private/public paths, run health checks, inspect hardware, and
recommend an explicit model download with honest disk/resource requirements. Do not hide
network-bearing model acquisition inside transcription or search.

Application update and uninstall semantics are custody-sensitive. Updating EchoFlow must
preserve durable schemas/state or fail safely. Uninstalling the program must not silently
delete canonical transcripts, research SQLite state, speaker labels, saved searches,
remembered-location preferences, or other user-owned evidence/knowledge. Program removal
and user-data destruction are separate operations.

## 4. Backup, restore, research portability, and selected-result export

Portability is part of the ownership thesis. A user should be able to back up or move the
irreplaceable EchoFlow workspace without treating disposable indexes as authority.

Backup/restore should cover canonical transcript evidence and authoritative user state,
including research SQLite data, saved searches, and speaker display labels. Rebuildable
DuckDB lexical/semantic/research projections should be regenerated rather than becoming
backup authority.

Remembered absolute library locations are machine-local application preferences and should
not be blindly replayed on another computer during workspace restore. Portability should
export them as reviewable metadata, then require explicit path reconciliation/re-approval
on the destination machine.

For research export, target CSV, JSON/JSONL, and Markdown first, then a whole-workspace or
user-state export manifest when the durable schema is ready. Exports should retain document
ID, source/canonical SHA-256, segment IDs, and numeric evidence coordinates where
applicable.

## 5. Qualify semantic dependency and managed embedding custody

Before semantic search is advertised as a normal packaged capability, qualify one locked
optional semantic dependency set with managed immutable E5 snapshot acquisition, private
cache placement, disk/resource admission, no silent search-time download, offline
execution after installation, and packaged-platform qualification.

## 6. Representative-device release qualification

Exercise real corpora and the packaged application on 8 GB Windows, 16 GB commodity
hardware, Apple Silicon, a discrete-GPU laptop, and larger 32/64 GB workstations. Measure
real-time factor, cold/warm model behavior, thermal/memory pressure, private disk cost,
enhancement benefit, embedding build cost, refresh cost, interactive query latency, and GUI
responsiveness.

Release qualification should also cover Unicode/space-heavy paths, external drives,
permission failures, low-disk conditions, interrupted model downloads, crash/resume,
upgrade migrations, uninstall/reinstall, offline operation, accessibility/keyboard use,
corruption/recovery language, remembered-location disappearance/reappearance, and
one-time-vs-persistent import behavior.

The pre-1.0 milestone is not “the tests pass from a checkout.” It is “a normal person can
install EchoFlow, understand first run, process sensitive recordings, recover from common
failure, move or back up their durable work, update the app safely, and remove the program
without losing evidence.”

# Conditional later capabilities

## Deeper original-media clock qualification

Only add production/media-clock mapping when real recordings require it: non-zero stream
origins, rational frame/timecode rates, drop-frame semantics, PTS/DTS mapping, and explicit
synchronization across independent sources.

## Speech/source separation for overlapping speakers

Source separation remains later than honest overlap representation. It adds substantial
compute/model custody, uncertainty, derived-audio provenance, and failure modes. It should
demonstrate measurable end-to-end recognition benefit before entering the normal path.

## Typed query evolution

Do not let CLI flags, GUI chips, saved searches, and a future natural-language convenience
layer grow separate semantics. Add date/duration/fuzzy/facet constraints only when real
usage requires them.

## Bounded failure recovery

Audio bisection/retry should be added only if representative long-recording failures show
it is needed. Do not front-load a recovery labyrinth for hypothetical failures.

## Durable-contract policy

EchoFlow has not yet had a released/dogfooded compatibility boundary. Internal durable
contracts therefore use one current canonical shape rather than accumulating migrations
for unreleased intermediate states. Unsupported schema versions still fail closed.

# Research candidates, not promises

Interesting later investigations include independent forced alignment, finer language
attribution, character n-gram/fuzzy retrieval for ASR names, a small local reranker if
measured benefit justifies it, resource-admitted HNSW only when exact search latency
justifies approximation, deterministic natural-language query grammar, optional local
query translation that exposes the interpreted typed query, citation-bound local
summarization over explicit evidence sets, user-authored cross-recording person
relationships without biometric inference, additional ASR engines, and additional
accelerator backends when concrete advantage exists.

The order can change when security review, dogfooding, hardware evidence, or complexity
contradicts an assumption. The stable direction is narrower:

> **Make sensitive local transcription boringly dependable. Make its evidence easy to
> navigate and annotate. Do not give the corpus away.** 💃
