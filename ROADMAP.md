# EchoFlow roadmap 🗺️✨

EchoFlow is becoming a **private local workspace for recorded evidence**.

Its job is not to out-engine every speech-recognition runtime. Its job is to make local
transcription dependable, resumable, inspectable, searchable, navigable, annotatable, and
portable on ordinary computers while keeping source evidence and user-authored knowledge
under clear custody.

Modern EchoFlow restarted on August 2, 2026. The project has already moved from “can we
transcribe a file?” to “can a person build and use a private local evidence library without
giving the corpus away?”

That is now the useful product boundary.

```mermaid
flowchart LR
    A[Local media] --> B[Reliable local transcription]
    B --> C[Canonical evidence]
    C --> D[Lexical semantic hybrid retrieval]
    D --> E[Verified evidence navigation]
    E --> F[Durable research workspace]
    D --> G[Unified library discovery]
    F --> G
    G --> H[Saved views and derived navigation]
    H --> I[Thin graphical shell]
```

Text fallback: transcription, evidence preservation, retrieval, navigation, durable
research state, and unified discovery are foundation. Saved views and derived navigation
are next; the first GUI should sit on those same services rather than inventing another
application.

# Current foundation

The backend is broad enough that the next work is increasingly about **human workflow,
qualification, packaging, and interface quality**, not inventing another transcription
pipeline.

## Local execution and media processing

EchoFlow currently provides:

- process-visible CPU and memory inspection, including relevant affinity/cgroup limits;
- physical accelerator topology kept separate from actual engine/runtime capability;
- resource-admitted faster-whisper CPU/int8 and CUDA-capable strategies;
- explicit refusal instead of silent substitution for infeasible user-selected strategies;
- dedicated/shared/unified accelerator-memory accounting;
- FFprobe inspection with file-only protocol access and complete source SHA-256;
- deterministic audio-stream selection;
- FFmpeg canonicalization to mono 16 kHz PCM16 WAV when required;
- exact integer-frame work windows;
- optional deterministic FFmpeg noise suppression with provenance and timeline checks; and
- bounded one-segment CPU preparation overlap during accelerated inference while preserving
  ordered checkpoints.

Performance ranks and memory estimates remain conservative heuristics pending
representative-device qualification.

## Reliability, model custody, and timeline evidence

The execution contract includes:

- explicit faster-whisper model inventory/recommendation/installation;
- immutable resolved model revisions and local revalidation;
- no silent ASR model download during transcription;
- private per-work-unit checkpoints and validated resume;
- source/model/stream/preprocessing/execution/alignment contract binding;
- contiguous-prefix checkpoint semantics;
- native faster-whisper word timestamps rebased onto one source-relative canonical
  timeline;
- aligned word evidence persisted through checkpoint/resume;
- deterministic `HH:MM:SS.mmm` human elapsed presentation without 24-hour wrapping; and
- preservation of source-declared `timecode` and `creation_time` metadata when FFprobe
  reports it.

Numeric source-relative seconds remain authoritative navigation coordinates. Human clock
strings are presentation. Source-declared media clocks are parallel provenance unless a
future media qualification proves a trustworthy mapping.

## Language and speaker evidence

EchoFlow supports:

- multilingual faster-whisper decoding;
- conservative local text-language attribution that may leave ambiguous text unlabeled;
- optional recording-scoped anonymous speaker diarization;
- deterministic anonymous speaker refs;
- word-level speaker projection when timing evidence supports it;
- conservative null/mixed behavior instead of forcing one speaker across a handoff;
- durable user-authored display labels such as `speaker-02 → Dr. Chen`; and
- derived overlap-aware presentation distinguishing `single-speaker`, `overlap`,
  `mixed-unresolved`, and `unattributed` states.

Speaker display names are bound to the exact canonical transcript generation. EchoFlow
does not perform biometric identity inference or silently link anonymous speakers across
recordings.

The pyannote execution path remains **security-held** while its locked Lightning
dependency is affected by the compensated advisory described in `SECURITY.md`.

## Canonical transcript and publications

Canonical JSON is authoritative transcript evidence. It carries source/execution
provenance, source-relative segment and word timestamps, source-declared temporal tags
when present, language evidence, optional enhancement provenance, and optional speaker
turn/word speaker evidence.

TXT, SRT, and WebVTT are deterministic derived publication views. They can be deleted and
regenerated without rerunning recognition.

## Transcript library, search, and aligned navigation

The local library now includes:

- a database-neutral lexical search contract;
- private DuckDB document/segment/term projections;
- deterministic offline BM25-style ranking;
- phrase, ANY/ALL, speaker, language, transcript, and timeline constraints;
- canonical transcript SHA-256 plus source-media SHA-256;
- deterministic segment-anchored semantic search chunks;
- a provider-neutral embedding contract and strict-local Multilingual E5 Small profile;
- private numeric semantic vectors and exact local dense similarity;
- reciprocal-rank hybrid BM25 + dense retrieval;
- stale-vector refusal when canonical transcript bytes change;
- verified canonical evidence lookup after ranking;
- exact aligned-word highlighting when lexical evidence justifies it;
- semantic-only passage navigation without fabricated exact-word matches;
- bounded neighboring canonical context expansion;
- deterministic seek coordinates for future local media playback; and
- current speaker display labels layered onto presentation while raw anonymous refs remain
  visible evidence.

Search ranking and evidence navigation remain separate operations. A rebuildable index
ranks a passage; navigation verifies canonical evidence before presenting precision.

## Durable research workspace

This is now **foundation**, not future work.

EchoFlow provides:

- authoritative private SQLite state for notes, tags, collections, and evidence anchors;
- exact source/canonical generation identity in durable note anchors;
- contiguous canonical segment-span validation before a note is accepted;
- optional sub-segment source-relative start/end coordinates;
- durable stale-generation retention rather than silent note teleportation;
- a monotonic transactional SQLite change journal;
- bounded idempotent projection replay;
- a rebuildable DuckDB research projection with an atomic convergence watermark;
- fail-closed handling when a projection claims to be ahead of authority;
- deterministic full rebuild when retained journal history cannot bridge a gap;
- note/tag/collection notebook filtering;
- tag/collection/note-text/with-notes constraints applied before transcript ranking or
  semantic scoring; and
- one `ResearchWorkspaceService` application boundary for CLI and future GUI adapters.

The custody hierarchy is now:

| Class | Examples | Rule |
|---|---|---|
| Authoritative evidence | original recording, canonical transcript JSON | never treat as cache |
| Authoritative user knowledge | speaker labels, notes, tags, collections, future saved searches/result sets | must survive index rebuilds |
| Rebuildable projection | lexical index, semantic chunks/vectors, research query projection, derived exports | may be regenerated |
| Private execution state | normalization, enhancement, checkpoints, temporary segments | lifecycle-managed, not source truth |

🦝 The raccoon may rebuild an index. The raccoon may not eat your annotations.

## Unified library discovery

This is now **foundation** too.

`ResearchWorkspaceService.discover()` and `echoflow library find QUERY` provide one human
query across four typed result groups:

- transcript evidence through existing lexical/semantic/hybrid retrieval and verified
  canonical navigation;
- note prose through the research projection followed by authoritative SQLite hydration;
- matching tag names; and
- matching collection names.

The discovery layer deliberately does not create a universal relevance score across
unlike objects. Transcript ranks remain transcript ranks. Notes, tags, and collections
remain their own object types.

Name matching for tags/collections is deterministic and group-local. Exact names sort
before prefix/substring matches, then token overlap. That ordering is a disposable view,
not authoritative state.

Per-group limits, canonical context, stale-note state, speaker presentation, evidence
identity, and source seek coordinates remain visible through the same application
contracts a future GUI can consume.

# Near-term product sequence

The next work should make the existing backend **pleasant to remember and navigate** rather
than reopening solved custody/search contracts.

## 1. Saved searches and useful derived navigation

This is the next feature tranche.

Saved searches are **durable user-authored workspace state** and belong in authoritative
SQLite. They should preserve typed query intent, not a blob of rendered CLI text.

Useful derived navigation should remain disposable. Candidate conveniences include:

- most-used tags, derived from current relationships rather than stored counters;
- recently used tags/collections;
- facets and counts where they reduce hunting;
- recent searches if they prove useful;
- saved search names/descriptions;
- selected/citable result sets; and
- stale-anchor review surfaces.

Do not make every convenience statistic another authoritative table. The durable object
is the user's tag/search/collection; popularity and recency rankings are views.

## 2. First thin GUI

The GUI has now earned its place because the backend is ahead of the human interface.

The first graphical vertical slice should remain deliberately small and beautiful rather
than becoming a second application implementation.

It should support:

- browse/open local transcripts;
- unified library search/discovery;
- readable transcript evidence with speaker/time context;
- click or select evidence and create/edit/delete a note;
- apply/create tags and collections, with frequent/recent suggestions;
- browse notes and saved searches; and
- jump to the existing source-relative seek coordinate in local media playback.

The GUI must consume existing application services and `EvidenceAnchor`. It must not own a
second search engine, second note schema, second speaker policy, or second definition of
where evidence lives.

Visual direction can be refined later, but the intended shell is light, calm, legible,
and evidence-first rather than dashboard-heavy.

## 3. Research portability and selected-result export

Portability is part of EchoFlow's ownership thesis, not decorative export polish.

Target first formats:

- CSV for ordinary tabular interoperability;
- JSON/JSONL for machine-readable structure;
- Markdown for human-readable research bundles; and
- a whole-workspace/user-state export manifest when the schema is ready.

Exports should retain evidence coordinates such as document ID, source/canonical SHA-256,
segment IDs, and numeric start/end seconds where applicable.

Native XLSX is optional later. CSV already opens in Excel, Numbers, LibreOffice, R,
pandas, and many research tools without adding a workbook dependency.

## 4. Incremental library refresh and corpus-scale qualification

`library rebuild` remains the correct repair path, but normal growth should not require
re-reading an entire large corpus because one transcript changed.

Add an incremental refresh path keyed by stable transcript generation identity, likely
`document_id + canonical_sha256`, using the existing lexical index `upsert/remove`
capabilities:

- new transcript → upsert;
- changed canonical generation → replace/upsert;
- removed transcript → remove;
- unchanged transcript → skip.

Keep full rebuild as explicit recovery.

Then measure realistic corpora rather than optimizing by instinct. Representative
qualification should include startup, warm/cold search, filtered lexical/semantic queries,
unified-discovery latency, notebook queries, one-edit projection catch-up, large-batch
projection catch-up, and full rebuild behavior.

## 5. Qualify semantic dependency and managed embedding custody

Before semantic search is advertised as a normal source install, qualify a locked
optional semantic dependency set with:

- one explicit semantic extra;
- managed acquisition of the exact qualified E5 snapshot;
- immutable revision custody;
- private cache placement;
- disk/resource admission;
- no silent model download during search/indexing;
- offline execution after installation; and
- clean-wheel/platform qualification.

Do not bypass `uv.lock` coherence merely to make the feature look finished.

## 6. Representative-device dogfooding and delivery

Exercise real multi-recording corpora on at least:

- 8 GB Windows consumer hardware;
- 16 GB commodity hardware;
- Apple Silicon;
- a discrete-GPU laptop; and
- larger 32/64 GB workstations.

Measure real-time factor, cold/warm model behavior, thermal effects, memory pressure,
private disk cost, enhancement cost/benefit, embedding build cost, library refresh cost,
and interactive query latency.

Use those measurements to calibrate strategy recommendations and installer defaults.

A pre-1.0 delivery milestone should include polished recovery/error language and an
installer/package path that does not require a developer environment.

# Conditional later capabilities

## Deeper original-media clock qualification

Only add production/media-clock mapping when real recordings require it. Candidate work
includes non-zero stream origins, rational frame/timecode rates, drop-frame semantics,
PTS/DTS mapping, and explicit synchronization relationships across independent sources.

“Metadata exists” and “metadata is trustworthy enough to map onto transcript evidence”
remain different states.

## Speech/source separation for overlapping speakers

Source separation remains later than honest overlap representation. It adds substantial
compute/model custody, uncertainty, derived-audio provenance, and failure modes.

It should demonstrate measurable end-to-end recognition benefit on representative overlap
cases before entering the normal product path.

# Other engineering work, when evidence asks for it

## Typed query evolution

The unified discovery/search surface compiles into typed query contracts. Do not let CLI
flags, GUI chips, saved searches, and a future natural-language convenience layer grow
separate semantics.

Add date/duration/fuzzy/facet constraints only when real use needs them.

## Bounded failure recovery

Audio bisection/retry should be added only if representative long-recording failures show
it is needed. Do not front-load a recovery labyrinth for hypothetical failures.

## Pre-production durable-contract policy

EchoFlow has not yet had a released/dogfooded durable compatibility boundary. Internal
durable contracts therefore use one current canonical shape rather than accumulating
migration branches for every unreleased intermediate state.

Unsupported schema versions still fail closed. When a real compatibility obligation
exists, migrations should be introduced against actual persisted fixtures from that
boundary.

# Research candidates, not promises

Interesting later investigations include:

- independent forced alignment or phoneme-level timing if native word timing proves
  insufficient;
- finer intra-clause/romanized language attribution;
- character n-gram/fuzzy retrieval for ASR names/acronyms/misspellings;
- a small local cross-encoder reranker if measured benefit justifies it;
- resource-admitted HNSW only when exact-search latency justifies approximation;
- constrained deterministic natural-language query grammar;
- optional local query translation that shows the interpreted typed query;
- optional summarization only over an explicitly selected/citable evidence set;
- explicit user-authored cross-recording person relationships, without biometric identity
  inference;
- additional ASR engines when they provide a concrete advantage; and
- additional accelerator backends when a real engine can consume them.

The order can change when security review, dogfooding, hardware evidence, or complexity
contradicts an assumption.

The stable direction is narrower:

> **Make sensitive local transcription boringly dependable. Make its evidence easy to
> navigate and annotate. Do not give the corpus away.** 💃
