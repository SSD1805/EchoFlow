# Processing capabilities 🎛️

EchoFlow is not one giant transcription function. It composes small local capabilities
into a reproducible job whose source, execution choices, recovery state, transcript, and
search projections remain explainable afterward.

This page is the **family portrait** for maintainers.

For the narrower contracts, see:

- [adaptive heterogeneous execution](adaptive-heterogeneous-execution.md);
- [media and timeline](media-and-timeline.md);
- [word-level timestamp alignment](word-alignment.md);
- [model management](model-management.md);
- [speech enhancement](speech-enhancement.md);
- [diarization](diarization.md); and
- [corpus search](corpus-search.md).

## What the user experiences

The intended experience is much simpler than the machinery:

1. give EchoFlow a recording;
2. let it inspect the source and current machine;
3. install a recommended model explicitly if needed;
4. transcribe locally;
5. resume if interrupted;
6. export useful views; and
7. search completed transcripts later.

Underneath that, EchoFlow is preserving enough evidence to explain how each result was
produced.

```mermaid
flowchart LR
    A[Local recording] --> B[Inspect source]
    B --> C[Inspect machine + runtime]
    C --> D[Build immutable plan]
    D --> E[Normalize / enhance if needed]
    E --> F[Segment + local ASR]
    F --> G[Word timing + ordered checkpoints]
    G --> H[Language + optional speaker evidence]
    H --> I[Canonical transcript]
    I --> J[Derived exports]
    I --> K[Lexical / semantic search]

    classDef evidence fill:#F9D5E5,stroke:#7B2E52,stroke-width:2px,color:#22151B
    classDef inspect fill:#D8EEFF,stroke:#2E617B,stroke-width:2px,color:#12222A
    classDef process fill:#E8D9FF,stroke:#68469B,stroke-width:2px,color:#1F1630
    classDef publish fill:#FFF0B8,stroke:#8A6B18,stroke-width:2px,color:#2C260F
    classDef result fill:#DDF5E3,stroke:#347A46,stroke-width:2px,color:#142719

    class A,I evidence
    class B,C,D inspect
    class E,F,G,H process
    class J publish
    class K result
```

That diagram is the product shape in one picture.

## 1. Media inspection: what is this file?

`FfprobeMediaProbe` owns source facts, not transcoding.

It reads bounded FFprobe metadata with file-only protocol access, fingerprints the
complete source, and refuses a file whose observed identity changes during inspection.

`AudioStreamSelector` then chooses one deterministic audio stream, using the first audio
stream by default or an explicit `--audio-stream INDEX`.

The stream choice becomes provenance. Resume restores it rather than silently selecting
a different track.

## 2. Resource/runtime inspection: what can this computer really do?

`RunnerInspector` observes CPU and system memory actually visible to the process,
including relevant affinity/cgroup limits.

`HardwareTopologyInspector` adds physical accelerator evidence.

`EngineCapabilityRegistry` separately asks the installed engine/runtime which concrete
device/compute targets are actually executable.

`StrategyEvaluator` admits and ranks safe strategies against system RAM, device memory,
runtime capability, and profile intent.

A visible GPU is not assumed usable. Shared/unified accelerator memory is not counted as
bonus physical RAM. Explicit impossible strategies fail instead of being silently
replaced.

See [adaptive heterogeneous execution](adaptive-heterogeneous-execution.md) for the
whole hardware cabaret. 💃

## 3. Model custody: which exact dependency is allowed to execute?

A safe strategy is not executable until its selected faster-whisper model has a verified
managed immutable revision.

`ModelManager` owns explicit ASR acquisition/custody. Planning asks it for the locally
revalidated resolved revision.

If the model is not managed, planning fails with an install-first message.

At execution time, faster-whisper runs with `local_files_only=True` and the exact
revision already recorded in the plan.

No transcription-time ASR download fallback exists.

## 4. Canonical audio: one deterministic working representation

The current canonical processing format is:

```text
WAV
pcm_s16le
16 kHz
mono
```

Already-canonical WAV may use `DIRECT`; other supported audio-bearing media uses
`FFMPEG_NORMALIZE`.

Normalization changes representation, not the public transcript timeline.

Exact PCM frame intervals define durable work windows.

## 5. Optional enhancement: help ASR without rewriting the source

When `--enhance` is enabled, the current `FfmpegAfftdnEnhancer` creates a private
`enhanced.wav` from canonical audio using the fixed current filter contract.

ASR may consume the enhanced derivative. The original recording remains authoritative.

EchoFlow checks channel count, sample width, sample rate, and frame count before
accepting the derivative so preprocessing cannot quietly shift the transcript timeline.

Anonymous diarization deliberately continues to read the unmodified canonical decode in
enhancement v1.

## 6. Segmentation, word timing, and checkpointing: make interruption survivable

EchoFlow owns deterministic segmentation:

- exact integer PCM frame boundaries;
- stable zero-based `audio-XXXXXX` work IDs;
- 600-second maximum work windows;
- no work-window overlap;
- one job-scoped ASR session; and
- strictly ordered checkpoint commits.

The faster-whisper session requests native word timestamps. Each engine-produced word is
validated inside its ASR segment and later rebased from work-window time onto the same
source-relative timeline as the canonical segment.

Per-window checkpoints persist that word evidence. The checkpoint manifest records an
explicit alignment identity so a pre-alignment checkpoint cannot silently resume into a
partially aligned transcript.

Accelerated execution may materialize at most one future segment while the current one
is being inferred.

A completed checkpoint set must remain a contiguous prefix of the deterministic work
plan.

Resume restores the original source/model/device/decode/enhancement/segmentation and
alignment contract and re-admits current resources.

## 7. Recognition, word alignment, and multilingual attribution

The faster-whisper backend performs managed local ASR and preserves its native per-word
timing evidence. EchoFlow does not run a separate forced-alignment model in this tranche.

With no explicit language, the current multilingual behavior can reconsider language
within durable work units rather than latching one job-wide acoustic prompt forever.

Published text-language labels come from local deterministic language attribution,
which can leave ambiguous short text unlabeled rather than fabricating certainty.

This is better support for changing languages, not a claim of perfect arbitrary
word-level code-switch attribution.

## 8. Optional anonymous speaker evidence

Diarization is recording-scoped enrichment, not identity.

The current pyannote capability is security-gated because the locked Lightning
dependency is affected by a compensated advisory. EchoFlow refuses the vulnerable path
before pyannote import/model acquisition.

When operationally qualified, diarization contributes an exact speaker-turn timeline.
Word timing now gives projection a finer evidence coordinate than an entire ASR segment:
a word receives a speaker only when exactly one diarized speaker overlaps its interval.

The enclosing segment keeps a convenience `speaker_ref` only when every aligned word is
attributed to the same speaker. Mixed handoffs and ambiguous overlap therefore remain
explicit instead of being flattened into one guessed label.

## 9. Canonical transcript and derived exports

Canonical JSON is authoritative transcript evidence.

The current contract records source/stream provenance, execution plan identity,
managed model revision, source-relative segment timestamps, nested source-relative word
timing evidence, language evidence, optional enhancement provenance, and optional
diarization evidence.

TXT, SRT, and WebVTT remain deterministic segment-oriented publication views.

They are useful. They are not recognition truth. More expressive word/speaker rendering
belongs to later presentation work rather than quietly changing caption semantics in the
alignment tranche.

## 10. Transcript library and search 🦝

Canonical transcript JSON can be projected into private rebuildable search state.

Lexical retrieval uses the database-neutral `TranscriptIndex` application port and a
current DuckDB BM25 implementation.

Semantic retrieval adds deterministic segment-anchored chunks, an
`EmbeddingProvider`/`EmbeddingProfile` contract, strict-local Multilingual E5 Small,
private numeric vectors, exact dense similarity, and corpus-fingerprint stale-state
refusal.

`TranscriptSearch` can combine lexical and semantic ranks with RRF while preserving
lexical, semantic, and fused provenance in one evidence-bearing `SearchResponse`.

The current search projection deliberately ignores nested word evidence and indexes
canonical segment text once. Future highlighting/jump-to-audio UX may consume word
coordinates without changing the ranking contract.

Search infrastructure must never become the only home of future user-authored notes,
labels, tags, collections, or annotations.

## 11. Private storage and observability

Structured logging uses Structlog behind `ILogger`.

Routine logs redact local paths by default.

Private job/checkpoint state, model caches, normalized/enhanced audio, and segment
materializations remain distinct from user-visible transcript artifacts.

POSIX private state uses owner-only mode policy; Windows uses current-user DACL policy.
These are filesystem access controls, not application-level encryption or secure
erasure.

## Capability ownership map

| Capability | Owns | Does not own |
|---|---|---|
| `FfprobeMediaProbe` | source identity + stream metadata | transcoding |
| `AudioStreamSelector` | selected audio stream | media discovery |
| `RunnerInspector` | process-visible CPU/RAM | model choice |
| `HardwareTopologyInspector` | physical accelerator evidence | runtime-support claims |
| `EngineCapabilityRegistry` | engine/device/compute support | strategy ranking |
| `StrategyEvaluator` | safe strategy admission/ranking | model acquisition |
| `ModelManager` | managed model custody/revision | ASR execution |
| `TranscriptionJobPlanner` | immutable combined execution plan | performing work |
| `FfmpegAudioDecoder` | selected-stream canonicalization | enhancement |
| `FfmpegAfftdnEnhancer` | optional noise suppression | source authority |
| `WaveAudioSegmenter` | exact work windows/materialization | recognition |
| `FasterWhisperSession` | local ASR + native word timing | model download or forced alignment |
| `LocalCheckpointStore` | private resumable segment/word evidence | public artifacts |
| `TranscriptAssembler` | source-relative segment/word assembly | filesystem policy |
| `LinguaLanguageAttributor` | conservative text-language labels | acoustic decoding |
| `SpeakerDiarizer` | anonymous speaker-turn evidence | biometric identity |
| `TranscriptExporter` | derived TXT/SRT/VTT | recognition truth |
| `TranscriptIndex` | database-neutral lexical search contract | semantic execution |
| `DuckDbTranscriptIndex` | private BM25 projection | canonical transcript truth |
| `EmbeddingProvider` | query/passage embedding semantics | corpus custody |
| `DuckDbSemanticIndex` | rebuildable vector state + exact similarity | canonical evidence |
| `TranscriptSearch` | retrieval composition + RRF | storage implementation |
| `TranscriptLibraryService` | discovery/rebuild/stale-state/retrieval/integrity receipts | SQL ownership |
| `WorkspaceService` | private/public path allocation | audio semantics |

Protocols exist around real substitutable behavior, not because every class deserves a
ceremonial interface.

## Current deliberate limits

EchoFlow does not currently claim:

- calibrated performance across representative hardware;
- every visible accelerator is useful/faster;
- alternate ASR engines;
- arbitrary word-level code-switch attribution;
- independent forced alignment or phoneme-level timing;
- biometric speaker identity;
- user-assigned speaker display labels;
- polished overlap handling;
- simultaneous-speaker/source separation;
- generative restoration;
- automatic enhancement selection;
- original SMPTE/container/capture-time provenance beyond source-relative elapsed time;
- storage durability across sudden power loss;
- malicious same-user TOCTOU resistance;
- secure erasure;
- a qualified locked semantic dependency extra;
- ANN/HNSW, learned reranking, generated corpus answers, or durable user annotations;
  or
- a polished installer/desktop GUI.

## What is becoming the next product layer?

Word timing establishes the first finer-grained evidence coordinate below an ASR segment.
The next high-value work is increasingly about using and extending that evidence:

1. original-media timecode and capture-time provenance;
2. better speaker overlap presentation and user-assigned display labels;
3. search highlighting, precise jump-to-audio, and durable annotation UX over aligned
   coordinates; and
4. later, source separation for genuinely overlapping speech when evidence and measured
   benefit justify the additional model/compute complexity.

Those capabilities strengthen the user experience without changing the architecture's
central rule:

> **Source evidence stays authoritative. Derived machinery stays explainable. User
> knowledge does not get mistaken for cache.**