# Processing capabilities 🎛️

EchoFlow is not one giant transcription function. It composes small local capabilities
into a reproducible workflow whose source, execution choices, recovery state, transcript,
search projections, navigation views, and research state remain explainable afterward.

This page is the **family portrait** for maintainers.

For narrower contracts, see:

- [adaptive heterogeneous execution](adaptive-heterogeneous-execution.md);
- [media and timeline](media-and-timeline.md);
- [word-level timestamp alignment](word-alignment.md);
- [model management](model-management.md);
- [speech enhancement](speech-enhancement.md);
- [diarization](diarization.md);
- [corpus search](corpus-search.md); and
- [durable research state](research-state.md).

## What the user experiences

The intended experience is simpler than the machinery:

1. give EchoFlow a recording;
2. let it inspect the source and current machine;
3. install a recommended model explicitly if needed;
4. transcribe locally;
5. resume if interrupted;
6. publish useful transcript views;
7. search completed transcripts;
8. follow a result back to verified canonical evidence; and
9. keep durable notes/tags/collections attached to that evidence.

The next product work is making those existing capabilities easier to discover and use
through one library surface and eventually a thin GUI.

```mermaid
graph LR;
    A[Local recording] --> B[Inspect source and runtime]
    B --> C[Immutable plan]
    C --> D[Normalize enhance segment ASR]
    D --> E[Word timing and checkpoints]
    E --> F[Language and speaker evidence]
    F --> G[Canonical transcript JSON]
    G --> H[Derived exports]
    G --> I[Lexical semantic hybrid search]
    I --> J[Verified evidence navigation]
    J --> K[SQLite notes tags collections]
    K --> L[DuckDB research projection]
    L --> I
```

Text fallback: local execution produces canonical transcript evidence; rebuildable search
ranks it; verified navigation resolves results; durable research state attaches to exact
canonical evidence and can constrain later retrieval.

## 1. Media inspection: what is this file?

`FfprobeMediaProbe` owns source facts, not transcoding. It reads bounded FFprobe metadata
with file-only protocol access, fingerprints the complete source, and refuses a file whose
observed identity changes during inspection.

`AudioStreamSelector` chooses one deterministic audio stream. The choice becomes
provenance and resume restores it instead of silently choosing another track.

Source-declared `timecode` and `creation_time` tags are preserved with format/stream scope
when available. They remain provenance, not canonical elapsed-time authority.

## 2. Resource/runtime inspection: what can this computer really do?

`RunnerInspector` observes CPU and system memory actually visible to the process, including
relevant affinity/cgroup limits.

`HardwareTopologyInspector` adds physical accelerator evidence.
`EngineCapabilityRegistry` separately asks the installed engine/runtime which concrete
device/compute targets are executable. `StrategyEvaluator` admits/ranks safe strategies
against RAM, device memory, runtime capability, and profile intent.

A visible GPU is not assumed usable. Shared/unified accelerator memory is not counted as
bonus physical RAM. Explicit impossible strategies fail instead of being silently
replaced.

## 3. Model custody: which exact dependency may execute?

A strategy is not executable until its selected faster-whisper model has a verified
managed immutable revision.

`ModelManager` owns explicit acquisition/custody. Planning asks it for the locally
revalidated revision. At execution, faster-whisper uses local-only model resolution and
the exact revision already recorded in the plan.

No transcription-time ASR download fallback exists.

## 4. Canonical audio and optional enhancement

The current canonical processing format is:

```text
WAV
pcm_s16le
16 kHz
mono
```

Already-canonical WAV may use `DIRECT`; other supported audio-bearing media uses
`FFMPEG_NORMALIZE`.

Normalization changes representation, not the public transcript timeline. Exact PCM frame
intervals define durable work windows.

When `--enhance` is enabled, `FfmpegAfftdnEnhancer` creates private enhanced audio from
canonical audio using the fixed current filter contract. The original recording remains
authoritative, and EchoFlow verifies the derivative did not change the timeline shape.

Anonymous diarization deliberately continues to read the unmodified canonical decode in
enhancement v1.

## 5. Segmentation, word timing, and checkpointing

EchoFlow owns deterministic segmentation:

- exact integer PCM frame boundaries;
- stable zero-based work IDs;
- 600-second maximum work windows;
- no work-window overlap;
- one job-scoped ASR session; and
- strictly ordered checkpoint commits.

The faster-whisper session requests native word timestamps. Engine-produced words are
validated and rebased from work-window time onto the same source-relative timeline as
canonical segments.

Per-window checkpoints persist aligned word evidence. Resume restores the
source/model/device/decode/enhancement/segmentation/alignment contract and re-admits current
resources.

Accelerated execution may materialize at most one future segment while the current one is
inferred. Completed checkpoints remain a contiguous prefix of the deterministic work plan.

## 6. Recognition, language, and speaker evidence

The faster-whisper backend performs managed local ASR plus native word timing. EchoFlow
does not currently run a separate forced-alignment model.

With no explicit language, multilingual behavior can reconsider language within durable
work units rather than latching one job-wide prompt forever. Published text-language
labels come from local deterministic attribution, which may leave ambiguous text
unlabeled.

Diarization is recording-scoped enrichment, not identity. When speaker evidence exists,
word timing provides a finer projection coordinate than a whole ASR segment. A word
receives a speaker only when exactly one diarized speaker overlaps that word interval.

The enclosing segment keeps a convenience `speaker_ref` only when aligned words support
one uniform speaker. Mixed handoffs and ambiguous overlap stay explicit.

The library adds human-facing display labels such as `speaker-02 → Dr. Chen` without
rewriting anonymous canonical evidence. No biometric or cross-recording person inference
occurs.

The current pyannote path remains security-gated while the locked Lightning dependency is
affected by the compensated advisory described in `SECURITY.md`.

## 7. Canonical transcript and derived exports

Canonical JSON is authoritative transcript evidence.

It records source/stream provenance, execution-plan identity, managed model revision,
source-relative segment and word timing, language evidence, optional enhancement
provenance, source-declared temporal tags, and optional diarization evidence.

TXT, SRT, and WebVTT remain deterministic segment-oriented publication views. They are
useful. They are not recognition truth.

## 8. Transcript library and retrieval 🦝

Canonical transcript JSON can be projected into private rebuildable search state.

Lexical retrieval uses the database-neutral `TranscriptIndex` application port and DuckDB
BM25 adapter. Semantic retrieval adds deterministic segment-anchored chunks,
`EmbeddingProvider`/`EmbeddingProfile`, strict-local Multilingual E5 Small, private
numeric vectors, exact dense similarity, and stale-corpus refusal.

`TranscriptSearch` can combine lexical and semantic ranks with RRF while preserving
lexical, semantic, and fused provenance in one `SearchResponse`.

Nested word evidence remains outside ranking storage. Search indexes canonical segment
text once.

## 9. Canonical evidence navigation

Retrieval and navigation are separate capabilities.

`EvidenceLocator` takes ranked passages and re-verifies the exact canonical transcript
SHA/source identity before exposing precise coordinates. It can then:

- resolve result segment IDs;
- expose exact aligned words for lexical matches;
- preserve phrase contiguity for exact phrase highlighting;
- avoid exact-word claims for semantic-only results;
- add bounded neighboring canonical context; and
- choose a deterministic source-relative seek coordinate.

`ResearchNavigationService` composes that canonical location with current user-assigned
speaker display labels. Ranking/filtering still uses anonymous refs; presentation may
show `Dr. Chen (speaker-02)`.

## 10. Durable research workspace

Notes, tags, and collections are now implemented durable library-side state.

`ResearchWorkspaceService` is the application-facing facade over:

- transcript retrieval;
- verified `EvidenceAnchor` creation;
- authoritative SQLite research state;
- the monotonic change journal;
- `ResearchStateProjector` convergence;
- rebuildable DuckDB research relationships/terms; and
- transcript search constrained by research metadata.

A note anchor includes document identity, source SHA-256, canonical transcript SHA-256,
canonical segment IDs, and numeric source-relative time. Multi-segment anchors must be
contiguous.

If the canonical transcript generation changes, the note survives as durable historical
user state but does not silently attach to the new generation.

Research tag/collection/note-text constraints are resolved to canonical evidence scope
**before** BM25 ranking or semantic vector scoring.

SQLite user state is not rebuildable. The DuckDB research projection is.

## 11. Private storage and observability

Structured logging uses Structlog behind `ILogger`. Routine logs redact local paths by
default.

Private job/checkpoint state, model caches, normalized/enhanced audio, segment
materializations, search databases, SQLite research authority, and rebuildable research
projection remain distinct from user-visible transcript artifacts.

POSIX private state uses owner-only mode policy; Windows uses current-user DACL policy.
These are filesystem access controls, not application-level encryption or secure erasure.

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
| `DuckDbTranscriptIndex` | private BM25 projection | canonical truth |
| `EmbeddingProvider` | query/passage embedding semantics | corpus custody |
| `DuckDbSemanticIndex` | rebuildable vectors + exact similarity | canonical evidence |
| `TranscriptSearch` | retrieval composition + RRF | storage implementation |
| `TranscriptLibraryService` | discovery/rebuild/stale-state/retrieval/integrity receipts | durable research authority |
| `SpeakerLabelService` | durable human display names | diarization evidence |
| `EvidenceLocator` | verified canonical result/anchor coordinates | ranking |
| `ResearchNavigationService` | retrieval + location + speaker-display composition | canonical mutation |
| `ResearchStateStore` | durable notes/tags/collections + evidence anchors | search ranking |
| `ResearchStateProjector` | deterministic projection convergence | user truth |
| `ResearchProjectionIndex` | fast research filtering/summaries | authoritative note content |
| `ResearchWorkspaceService` | one application seam over research + evidence + retrieval | database topology leakage |
| `WorkspaceService` | private/public path allocation | audio semantics |

Protocols exist around real substitutable behavior, not because every class deserves a
ceremonial interface.

## Current deliberate limits

EchoFlow does not currently claim:

- calibrated performance across representative consumer hardware;
- every visible accelerator is useful/faster;
- alternate ASR engines;
- arbitrary word-level code-switch attribution;
- independent forced alignment or phoneme-level timing;
- biometric or cross-recording speaker identity;
- speech/source separation;
- generative restoration;
- automatic enhancement selection;
- trusted deterministic SMPTE/PTS mapping beyond preserved source declarations;
- malicious same-user TOCTOU resistance;
- secure erasure;
- a qualified locked semantic dependency extra;
- ANN/HNSW, learned reranking, or generated corpus answers;
- saved-search objects or curated/citable result sets;
- automatic cross-generation note re-anchoring; or
- a polished installer/desktop GUI.

## What is the next product layer?

The backend research workspace is now foundation.

The next sequence is:

1. **unified library discovery** across transcript evidence, notes, tags, collections, and
   later saved searches;
2. **saved searches and useful derived navigation**, such as most-used/recent tags and
   facets computed from authoritative relationships rather than stored counters;
3. **a thin GUI** over the same application services, evidence anchors, and seek contract;
4. **research export + incremental library refresh + realistic corpus benchmarks**; and
5. **semantic-install, representative-device, and installer qualification**.

Source separation remains later and evidence-driven. EchoFlow can already represent
overlap honestly; another model should earn its compute/custody/provenance burden with
measured benefit.

> **Source evidence stays authoritative. Derived machinery stays explainable. User
> knowledge does not get mistaken for cache.**
