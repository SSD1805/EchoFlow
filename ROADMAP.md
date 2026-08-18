# EchoFlow roadmap 🗺️✨

EchoFlow is becoming a **private local workspace for recorded evidence**.

Its job is not to out-engine speech-recognition runtimes. Its job is to make local
transcription dependable, resumable, inspectable, searchable, and useful on ordinary
computers while keeping source evidence and user-authored knowledge under clear custody.

Modern EchoFlow restarted on August 2, 2026. The project has already moved from “can we
transcribe a file?” to “can we preserve, search, and navigate a local corpus of recorded
evidence without giving the corpus away?”

That is now the useful product boundary.

```mermaid
flowchart LR
    A[Local media] --> B[Reliable local transcription]
    B --> C[Evidence-preserving corpus]
    C --> D[Lexical + semantic retrieval]
    D --> E[Aligned evidence navigation]
    E --> F[Durable research workspace]
    F --> G[Beginner-friendly product shell]

    classDef done fill:#DDF5E3,stroke:#347A46,stroke-width:2px,color:#142719
    classDef now fill:#FFF0B8,stroke:#8A6B18,stroke-width:2px,color:#2C260F
    classDef next fill:#E8D9FF,stroke:#68469B,stroke-width:2px,color:#1F1630

    class A,B,C,D,E done
    class F now
    class G next
```

# Current foundation: yes, we have been busy 💃

The backend is broad enough that the next work is increasingly about **research workflow,
qualification, packaging, and interface quality**, not inventing another transcription
pipeline.

## Local execution and media processing

EchoFlow currently provides:

- process-visible CPU and memory inspection, including relevant affinity/cgroup limits;
- physical accelerator topology kept separate from actual engine/runtime capability;
- resource-admitted faster-whisper CPU/int8 and CUDA-capable strategies;
- explicit refusal instead of silent substitution for infeasible user-selected
  strategies;
- dedicated/shared/unified accelerator-memory accounting;
- FFprobe inspection with file-only protocol access and complete source SHA-256;
- deterministic audio-stream selection;
- FFmpeg canonicalization to mono 16 kHz PCM16 WAV when required;
- exact integer-frame work windows;
- optional deterministic FFmpeg noise suppression with provenance and timeline checks;
  and
- bounded one-segment CPU preparation overlap during accelerated inference while
  preserving ordered checkpoints.

Performance ranks and memory estimates remain conservative heuristics pending
representative-device qualification.

## Reliability, model custody, and timeline evidence

The current execution contract includes:

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
- preservation of source-declared `timecode` and `creation_time` metadata at format and
  stream scope when FFprobe reports it.

Numeric source-relative seconds remain authoritative navigation coordinates. Human clock
strings are presentation. Source-declared camera/container metadata is parallel
provenance, not a replacement timeline and not automatically trusted.

## Language and speaker evidence

EchoFlow supports:

- multilingual faster-whisper decoding;
- conservative local text-language attribution that may leave ambiguous text unlabeled;
- optional recording-scoped anonymous speaker diarization;
- deterministic anonymous speaker refs;
- word-level speaker projection when timing evidence supports it;
- conservative null/mixed behavior instead of forcing one speaker across a handoff;
- durable user-authored display labels such as `speaker-02 → Dr. Chen`, stored separately
  from canonical evidence and rebuildable indexes; and
- a derived overlap-aware speaker transcript that distinguishes `single-speaker`,
  `overlap`, `mixed-unresolved`, and `unattributed` presentation states.

Speaker display names are bound to the exact canonical transcript generation. EchoFlow
does not perform biometric identity inference or silently link anonymous speakers across
recordings.

The pyannote execution path remains **security-held** while its locked Lightning
dependency is affected by the compensated CVE-2026-58659/PYSEC-2026-3624 advisory.
EchoFlow fails closed before that provider executes or acquires model state while the
security gate is active.

## Canonical transcript and publications

Canonical JSON is authoritative transcript evidence.

It carries source/execution provenance, source-relative segment and word timestamps,
source-declared temporal tags when present, language evidence, optional enhancement
provenance, and optional speaker-turn/word speaker evidence.

TXT, SRT, and WebVTT remain deterministic derived publication views. They can be deleted
and regenerated without rerunning recognition.

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
- human elapsed result coordinates while JSON retains numeric seconds;
- verified canonical evidence lookup after ranking;
- exact aligned-word highlighting when lexical evidence justifies it;
- semantic-only passage navigation without fabricated exact-word matches;
- bounded neighboring canonical context expansion;
- deterministic seek coordinates for future local media playback; and
- current speaker display labels layered onto search presentation while raw anonymous
  refs remain visible evidence.

Search ranking and evidence navigation are separate operations. A rebuildable index ranks
a passage; the navigation layer verifies the canonical transcript before presenting a
precise location.

Semantic search remains an advanced optional capability because the locked base project
dependency graph does not yet include Sentence Transformers. Lexical search remains the
normal dependency-light default.

## Security, privacy, and quality foundation

The project currently has:

- path-redacted routine logs;
- platform-specific private storage enforcement;
- explicit network-bearing model acquisition boundaries;
- no hosted transcription integration or application telemetry;
- Linux/macOS/Windows CI;
- strict mypy, Ruff lint/format/security rules, Vulture, Radon, and branch coverage;
- locked dependency auditing and clean-wheel/package checks;
- Hypothesis property tests around load-bearing invariants; and
- targeted Poodle mutation qualification for decision-heavy code.

See [SECURITY.md](SECURITY.md) for the exact threat boundary. “Local-first” is not a
claim that the host operating system or every native dependency is trusted.

# The custody rule that should survive every feature

EchoFlow has several classes of data with deliberately different deletion semantics.

| Class | Examples | Rule |
|---|---|---|
| Authoritative evidence | original recording, canonical transcript | never treat as cache |
| User-authored knowledge | speaker labels, future notes/tags/annotations/collections | must survive index rebuilds |
| Rebuildable projection | lexical index, semantic chunks/vectors, derived exports | may be regenerated from durable evidence |
| Private execution state | normalization, enhancement, checkpoints, temporary segments | lifecycle-managed, not source truth |

🦝 The raccoon may rebuild an index. The raccoon may not eat your annotations.

# Near-term product sequence

Word timing, source time provenance, speaker naming, overlap presentation, and aligned
search navigation are now foundation. The next work should build on those contracts
rather than repeatedly reopening them.

## 1. Durable research workspace state

The next major product layer is user-authored research state over verified evidence
locations.

Target direction:

- notes anchored to source/canonical identity plus durable segment/word/time coordinates;
- tags;
- saved searches;
- collections;
- annotation update/history semantics where useful;
- exportable selected result sets; and
- a transactional private user-state store appropriate for mutable/queryable knowledge.

Speaker labels proved the custody model in miniature. Notes and collections are higher
volume and more queryable, so they should not simply accumulate forever in one giant JSON
file. A small transactional store such as SQLite is a likely application adapter, behind
ports that keep user knowledge separate from search implementation details.

A note must never be anchored only to a formatted timestamp or disposable semantic chunk
ID. If canonical evidence changes, EchoFlow should retain the note and report that its
old anchor needs review rather than silently teleporting the annotation.

## 2. Search/research workspace ergonomics

Use real corpora to decide which navigation conveniences earn permanence:

- result-context expansion beyond simple neighboring segments;
- facets and typed constraints;
- exportable/citable result sets;
- saved-search and collection workflows;
- local media playback over the existing seek contract; and
- cross-feature presentation of speaker names, tags, and annotation state.

The GUI should eventually consume these same services. It should not invent a second
search engine or a second definition of where transcript evidence lives.

## 3. Qualify semantic dependency and managed embedding custody

Before semantic search is advertised as a normal source install, qualify a locked
optional semantic dependency set.

Target direction:

- one explicit semantic extra;
- managed acquisition of the exact qualified E5 snapshot;
- immutable revision custody;
- private cache placement;
- disk/resource admission;
- no silent model download during search/indexing;
- offline execution after installation; and
- clean-wheel/platform qualification.

Do not bypass `uv.lock` coherence merely to make the feature look more finished.

## 4. Representative-device qualification and dogfooding

Exercise real multi-recording corpora and collect repeated evidence from at least:

- 8 GB Windows consumer hardware;
- 16 GB commodity hardware;
- Apple Silicon;
- a discrete-GPU laptop; and
- larger 32/64 GB workstations.

Measure cold/warm model behavior, real-time factor, thermal effects, CPU/RAM pressure,
device memory/utilization where reliable, private disk cost, enhancement benefit/cost,
embedding build cost, and semantic-query/navigation latency.

Dogfood interruption/resume, noisy media, stale-process reconciliation, model
remove/reinstall, source-integrity receipts, speaker naming/overlap, lexical/semantic/
hybrid search, and aligned navigation using real interviews, lectures, meetings, and oral
histories.

Calibrate from measurements, not hardware marketing names.

## 5. Beginner delivery surface

EchoFlow's backend increasingly makes beginner-friendly decisions automatically. Its
current source-install/terminal delivery still assumes a developer.

A reasonable pre-1.0 usability milestone includes:

1. durable notes/tags/collections over aligned evidence;
2. semantic setup that no longer requires advanced manual environment preparation;
3. representative qualification on ordinary hardware;
4. polished error/recovery language;
5. an installer/package path that does not require a developer environment; and
6. a thin graphical shell over the existing application services.

The GUI should be a presentation adapter, not a second implementation of transcription,
search, time mapping, speaker policy, or model custody.

## 6. Deeper original-media clock qualification only when real media requires it

The current implementation preserves source-declared format/stream `timecode` and
`creation_time` tags while keeping them distinct from canonical elapsed seconds.

If real recordings require deterministic production/media-clock mapping, qualify the
necessary semantics rather than guessing. Candidate work includes non-zero stream
origins, rational frame/timecode rates, drop-frame/non-drop-frame semantics, PTS/DTS
mapping, timezone normalization only when actually encoded, and explicit synchronization
relationships across independent sources.

“Metadata exists” and “metadata is trustworthy enough to map onto transcript evidence”
remain different states.

# Later capability: speech/source separation for overlapping speakers

Source separation is valuable, but it remains intentionally later than honest overlap
representation.

Separating mixed speech into estimated source signals adds substantial compute/model
cost, new dependency/model custody, uncertainty about source-to-human identity, derived
audio provenance, and new failure modes. It should also demonstrate an actual end-to-end
recognition benefit on representative overlap cases.

EchoFlow can now represent simultaneous speaker evidence without choosing a fake winner.
That is enough foundation to **measure** whether separation is worth the additional
complexity.

🧜‍♀️ We enter the deep water after learning to swim.

# Other engineering work, when evidence asks for it

## Typed query evolution

`SearchQuery` already owns text, phrase, ANY/ALL semantics, speaker, language,
document/transcript, sorting, and bounded limits.

Add date/tag/duration/facet/collection constraints when real product use requires them.
CLI syntax, future query chips, and any local natural-language convenience layer should
compile to the same typed contract instead of growing separate search semantics.

## Bounded failure recovery

Audio bisection/retry should be added only if representative long-recording failures show
it is needed. Do not front-load a recovery labyrinth for hypothetical failures.

## Pre-production contract policy

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
- source separation when measured overlap failures justify it;
- richer PTS/SMPTE synchronization only when real media requires it;
- alternative qualified multilingual embedding models;
- character n-gram/fuzzy retrieval for ASR names/acronyms/misspellings;
- a small local cross-encoder reranker if measured benefit justifies it;
- resource-admitted HNSW only when exact-search latency justifies approximation;
- constrained deterministic natural-language query grammar;
- optional local query translation that shows the interpreted typed query;
- optional summarization only over an explicitly selected/citable evidence set;
- explicit user-authored cross-recording person relationships, without biometric
  identity inference;
- additional ASR engines when they provide a concrete advantage; and
- additional accelerator backends when a real engine can consume them.

The order can change when security review, dogfooding, hardware evidence, or complexity
contradicts an assumption.

The stable direction is narrower:

> **Make sensitive local transcription boringly dependable. Make its evidence easy to
> navigate and annotate. Do not give the corpus away.** 💃
