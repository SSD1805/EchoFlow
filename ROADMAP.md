# EchoFlow roadmap 🗺️✨

EchoFlow is becoming a **private local workspace for recorded evidence**.

Its job is not to out-engine speech-recognition runtimes. Its job is to make local
transcription dependable, resumable, inspectable, searchable, and usable on ordinary
computers while keeping source evidence and user-owned artifacts under clear custody.

Modern EchoFlow restarted on August 2, 2026. Since then, the project has moved very
quickly from “can we transcribe a file?” to “can we preserve and navigate a local corpus
of recorded evidence without giving the corpus away?”

That is a substantially different product.

## Where we are now

The backend foundation is broad enough that the next work is increasingly about
**evidence navigation, qualification, packaging, and interface quality**, not inventing
another transcription pipeline.

```mermaid
flowchart LR
    A[Local media] --> B[Reliable local transcription]
    B --> C[Evidence-preserving canonical corpus]
    C --> D[Lexical + semantic retrieval]
    D --> E[Finer evidence navigation]
    E --> F[Beginner-friendly product shell]

    classDef done fill:#DDF5E3,stroke:#347A46,stroke-width:2px,color:#142719
    classDef now fill:#FFF0B8,stroke:#8A6B18,stroke-width:2px,color:#2C260F
    classDef next fill:#E8D9FF,stroke:#68469B,stroke-width:2px,color:#1F1630

    class A,B,C,D done
    class E now
    class F next
```

## The current foundation: yes, we have been busy 💃

### Local execution and hardware awareness

EchoFlow currently has:

- process-visible CPU and memory inspection, including relevant affinity/cgroup limits;
- physical accelerator topology kept separate from engine/runtime capability;
- resource-admitted faster-whisper CPU/int8 and CUDA-capable strategies;
- explicit refusal instead of silent substitution for infeasible user-selected
  strategies;
- dedicated/shared/unified accelerator-memory accounting; and
- bounded one-segment CPU preparation overlap during accelerated inference while
  preserving ordered checkpoints.

Performance ranks and memory estimates remain conservative heuristics pending
representative-device qualification.

### Media, timeline, and local preprocessing

The current media foundation includes:

- FFprobe inspection with file-only protocol access and complete source SHA-256;
- deterministic audio-stream selection;
- FFmpeg canonicalization to mono 16 kHz PCM16 WAV when required;
- exact integer-frame work windows and source-relative transcript timestamps;
- optional deterministic FFmpeg noise suppression;
- timeline-preservation checks around enhanced audio; and
- provenance recording for preprocessing that affected ASR input.

The original recording remains read-only evidence. Normalized/enhanced WAV files remain
private derived processing material.

### Model custody

Faster-whisper model management currently provides:

- offline inventory and recommendation;
- explicit disk-admitted installation;
- provider/repository provenance;
- immutable resolved revisions;
- local structural revalidation;
- exact-revision removal; and
- mandatory managed-model identity for ASR planning/execution.

Transcription itself does not silently download ASR weights.

### Reliability and recovery

EchoFlow has:

- durable private per-work-unit checkpoints;
- validated resume;
- source/model/stream/preprocessing/execution contract binding;
- contiguous-prefix checkpoint semantics;
- cleanup of speculative/derived work without masking primary failures; and
- durable lifecycle evidence around long-running work.

The goal is that an interrupted long recording is an inconvenience, not a fresh start.

### Language and speaker evidence

The system currently supports:

- multilingual faster-whisper decoding;
- conservative local text-language attribution that may leave ambiguous text unlabeled;
- optional recording-scoped anonymous speaker diarization;
- deterministic speaker-label normalization; and
- conservative speaker projection that refuses ambiguous multi-speaker ASR segments.

The diarization path is **integrated but security-held** while its locked Lightning
dependency is affected by the compensated CVE-2026-58659/PYSEC-2026-3624 advisory.
EchoFlow fails closed before pyannote execution/acquisition while that gate is active.

### Canonical transcript and exports

Canonical JSON is authoritative transcript evidence.

It carries source and execution provenance, source-relative timestamps, language
evidence, optional enhancement provenance, and optional speaker-turn evidence.

TXT, SRT, and WebVTT are deterministic publication views that can be regenerated without
rerunning recognition.

### Transcript library and retrieval

The local library now includes:

- a database-neutral lexical search application port;
- private DuckDB document/segment/term projections;
- deterministic offline BM25-style ranking;
- phrase, ANY/ALL, speaker, language, document, and timeline constraints;
- canonical transcript SHA-256 in addition to source-media SHA-256;
- deterministic `search-chunk-v1` retrieval windows anchored to exact canonical segment
  IDs/timestamps;
- an `EmbeddingProvider` + immutable `EmbeddingProfile` contract;
- a strict-local Multilingual E5 Small provider;
- private numeric semantic vectors;
- exact local dense similarity with hard filters before top-K;
- reciprocal-rank hybrid BM25 + dense retrieval;
- one evidence-bearing `SearchResponse` with lexical/semantic/fused ranks; and
- corpus-fingerprint stale-vector refusal when canonical transcript bytes change.

Semantic search is currently an advanced optional capability because the locked project
dependency graph does not yet include Sentence Transformers. Lexical search remains the
normal dependency-light default.

### Security, privacy, and quality foundation

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
claim that the entire host operating system or every native dependency is trusted.

## The product principle that should survive every feature

EchoFlow now has several kinds of data with deliberately different deletion semantics.

| Class | Examples | Rule |
|---|---|---|
| Authoritative evidence | original recording, canonical transcript | never treat as cache |
| User-authored knowledge | future notes, speaker display labels, tags, annotations, collections | must survive index rebuilds |
| Rebuildable projection | lexical index, semantic chunks/vectors, derived exports | may be regenerated from durable evidence |
| Private execution state | normalization, enhancement, checkpoints, temporary segments | lifecycle-managed, not source truth |

This distinction becomes more important as EchoFlow evolves from a transcription tool
into a research library.

🦝 The raccoon may rebuild an index. The raccoon may not eat your annotations.

# Near-term product sequence

The next features should make evidence **finer, easier to navigate, and easier to name**
before EchoFlow adds heavier generative/audio-processing machinery.

## 1. Word/timestamp alignment

**Likely next feature.**

Current canonical ASR segments are durable evidence coordinates, but they are often too
coarse for precise highlighting, speaker handoffs, annotations, and jump-to-audio.

Alignment should add finer timestamp evidence without rewriting raw ASR truth.

Primary uses:

- word/phrase highlighting in search results;
- precise jump-to-audio;
- finer speaker attribution near handoffs;
- better handling of partially overlapping turns;
- durable annotation anchors smaller than an entire ASR segment; and
- improved subtitle/transcript interaction in a future GUI.

### Architectural direction

Alignment should be an **enrichment capability** over canonical transcript/audio
evidence.

Its output must record provider/model/version/revision as applicable and remain traceable
to canonical segments and source-relative time.

A neural model-backed aligner must reuse the model-custody family rather than inventing
a hidden download path.

## 2. Original-media timecode and capture-time provenance

EchoFlow currently exposes one clear canonical clock: elapsed source-relative seconds
from the selected audio origin.

That should remain stable.

The next provenance layer should preserve additional clocks when the input actually
contains them:

- non-zero container/stream presentation origins;
- SMPTE timecode;
- stream start-time offsets;
- camera/device capture timestamps;
- timezone/offset metadata when trustworthy; and
- explicit synchronization relationships between sources when known.

These should be typed parallel provenance, not collapsed into an ambiguous `timestamp`
field.

The design should distinguish “metadata exists” from “metadata is trustworthy enough to
map onto the transcript.”

## 3. Better speaker UX: overlap + user-assigned display labels

Anonymous diarization evidence should remain anonymous-by-default and recording-scoped.

But users should eventually be able to map stable anonymous refs to meaningful display
labels such as:

```text
speaker-01 → Dr. Chen
speaker-02 → Interviewer
```

Those labels are **user-authored state**. They must not be disposable search/index
metadata and should not rewrite the underlying anonymous speaker-turn evidence.

Overlap handling should also improve in presentation:

- preserve multiple active speaker refs where evidence supports overlap;
- use word/fine alignment where available;
- avoid forcing one speaker label onto genuinely ambiguous text; and
- render overlap clearly in human/GUI views.

## 4. Search/research workspace UX

The retrieval engine now supports lexical, semantic, and hybrid ranking. Real corpus use
should drive the next interface layer:

- better snippets/highlighting;
- result-context expansion;
- facets;
- exportable result sets;
- precise jump-to-audio;
- saved searches/collections; and
- durable tags, notes, and annotations.

The ownership rule is non-negotiable: user-authored state does not share deletion
semantics with rebuildable indexes.

## 5. Qualify semantic dependency and managed embedding custody

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

Do not bypass `uv.lock` coherence to make the feature look more finished.

## 6. Representative-device and enhancement qualification

Collect repeated benchmark evidence from at least:

- 8 GB Windows consumer hardware;
- 16 GB commodity hardware;
- Apple Silicon;
- a discrete-GPU laptop; and
- larger 32/64 GB workstations.

Measure cold/warm model behavior, real-time factor, thermal effects, CPU/RAM pressure,
device memory/utilization where reliable, private disk cost, enhancement benefit/cost,
embedding build cost, and semantic-query latency.

Calibrate from measurements, not hardware marketing names.

# Beginner-ready milestone

The backend is already beginner-oriented in many internal decisions: resource discovery,
model custody, recovery, provenance, and search are designed so the user does **not**
need to manually operate those systems.

But a beginner-friendly product also needs a beginner-friendly delivery surface.

A reasonable pre-1.0 usability milestone is:

1. word/fine alignment for precise evidence navigation;
2. richer media time provenance;
3. clearer speaker labels/overlap behavior;
4. semantic dependency/model setup that no longer requires advanced manual environment
   preparation;
5. representative qualification on ordinary hardware;
6. polished error/recovery language;
7. an installer/package path that does not require a developer environment; and
8. a thin graphical shell over the existing application services.

The GUI should be a presentation adapter, not a second implementation of transcription,
search, or model policy.

# Later capability: speech/source separation for overlapping speakers

Source separation is valuable, but it is intentionally **later** than better alignment
and overlap representation.

Separating mixed speech into estimated source signals adds:

- substantial compute/model cost;
- new model custody/dependency concerns;
- uncertainty about which separated signal corresponds to which human speaker;
- timeline/provenance requirements for derived sources;
- new failure modes; and
- a need to prove end-to-end recognition benefit on representative overlap cases.

EchoFlow should first become excellent at representing overlap honestly.

Then, if real recordings demonstrate that overlap remains a major recognition failure,
source separation can be evaluated as a targeted capability rather than an impressive
but unqualified checkbox.

🧜‍♀️ We enter the deep water after learning to swim.

# Other near-term engineering work

## Dogfood the complete workflow

Use real multi-recording corpora to exercise:

- interruption/resume;
- stale-process reconciliation;
- progress rendering;
- accelerator re-admission;
- managed model removal/reinstall;
- enhancement on noisy/long recordings;
- transcript-library rebuilds;
- source-integrity receipts; and
- lexical/semantic/hybrid search.

Retrieval questions worth measuring include whether current 220/300-word chunks behave
well across interviews, lectures, meetings, and oral histories; whether exact vector scan
remains interactive at realistic corpus sizes; and whether RRF improves conceptual
recall without burying exact names/acronyms.

## Typed query evolution

`SearchQuery` already owns text, phrase, ANY/ALL semantics, speaker, language,
document/transcript, sorting, and bounded limits.

Add date/tag/duration/facet/collection constraints only when real product use requires
them.

CLI syntax, future query chips, and any local natural-language convenience layer should
compile to the same typed contract instead of growing separate search semantics.

## Bounded failure recovery

Audio bisection/retry should be added only if representative long-recording failures show
it is needed.

Do not front-load a recovery labyrinth for hypothetical failures.

# Pre-production contract policy

EchoFlow has not had a released/dogfooded durable compatibility boundary yet.

Internal durable contracts therefore use one current canonical shape rather than
accumulating migration branches for every unreleased intermediate state.

Unsupported schema versions still fail closed.

When a real compatibility obligation exists, migrations should be introduced against
actual persisted fixtures from that boundary.

# Research candidates, not promises

Interesting later investigations include:

- finer intra-clause/romanized language attribution;
- richer original-media capture/timecode provenance;
- improved overlap rendering and source separation;
- alternative qualified multilingual embedding models;
- character n-gram/fuzzy retrieval for ASR names/acronyms/misspellings;
- a small local cross-encoder reranker if measured benefit justifies it;
- resource-admitted HNSW only when exact-search latency justifies it;
- constrained deterministic natural-language query grammar;
- optional local query translation that shows the interpreted typed query to the user;
- optional summarization only over an explicitly selected/citable evidence set;
- additional ASR engines when they provide a concrete advantage; and
- additional accelerator backends when a real engine can consume them.

The order can change when security review, dogfooding, hardware evidence, or complexity
contradicts an assumption.

The stable direction is much narrower:

> **Make sensitive local transcription boringly dependable. Make its evidence easy to
> navigate. Do not give the corpus away.** 💃