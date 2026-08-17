# Processing capabilities

EchoFlow composes small local capabilities into one reproducible transcription job. It
avoids a generic pipeline/plugin framework until multiple real implementations require
one.

For detailed media/timestamp semantics, see
[media-and-timeline.md](media-and-timeline.md). For model custody, see
[model-management.md](model-management.md). For preprocessing, see
[speech-enhancement.md](speech-enhancement.md). For corpus retrieval, see
[corpus-search.md](corpus-search.md).

## Current transcription path

```text
local recording
    ↓
FFprobe inspection + complete source fingerprint
    ↓
deterministic audio-stream selection
    ↓
process-visible CPU/RAM + accelerator topology
    ↓
engine capability negotiation + safe strategy selection
    ↓
verified managed faster-whisper revision
    ↓
canonical audio plan
    ↓
DIRECT or FFmpeg normalization
    ↓
optional private FFmpeg noise suppression
    ↓
exact PCM frame windows
    ↓
job-scoped managed local faster-whisper session
    ↓
ordered private per-window checkpoints
    ↓
source-relative transcript assembly
    ↓
local language attribution + optional anonymous diarization
    ↓
canonical JSON
    ↓
TXT / SRT / WebVTT derived views
```

The implementation exercises real FFprobe/FFmpeg on Linux, macOS, and Windows CI and
has a faster-whisper/CTranslate2 known-speech acceptance path. Hosted CI proves
contracts and portability, not representative machine performance.

## Media inspection and canonical audio

`FfprobeMediaProbe` owns source facts, not transcoding. It reads container/stream
metadata with file-only protocol access, fingerprints the complete source, and refuses
a file that changes during inspection. `AudioStreamSelector` chooses one discovered
audio stream, using the first audio stream by default or explicit
`--audio-stream INDEX`.

The selected stream is part of checkpoint provenance. Resume re-probes the source and
restores the original stream choice rather than silently selecting another track.

The current canonical processing format is WAV, `pcm_s16le`, 16 kHz, mono. An
already-canonical WAV may use `DIRECT`; other supported audio-bearing media uses
`FFMPEG_NORMALIZE`. FFmpeg maps exactly the selected audio stream and discards video,
subtitle, attachment, and data streams.

Normalization changes representation, not the public timeline. Exact PCM frame offsets
define work windows and assembly rebases engine-local timestamps onto one continuous
source-relative timeline.

## Optional local noise suppression

When the immutable plan enables enhancement, `FfmpegAfftdnEnhancer` consumes the
canonical decoded audio and creates a private `enhanced.wav` using the fixed current
`afftdn=nf=-50:nr=12` contract.

The provider validates that channel count, sample width, sample rate, and frame count
are unchanged. A mismatch fails closed because preprocessing must not shift EchoFlow's
source-relative timeline.

ASR segmentation consumes the enhanced derivative. Anonymous diarization continues to
consume the unmodified canonical decode in the first version. The transcript records
enhancement provider/version/operation/parameters when ASR input was transformed.

The extra full-recording derivative is included in private storage admission.
Enhancement is explicit with `--enhance`; there is no automatic selector yet.

## Compute and strategy policy

`RunnerInspector` observes CPU and memory actually visible to the process, including
relevant container limits. `HardwareTopologyInspector` adds physical accelerator
evidence without claiming the ASR runtime can use it. Engine capability probes then
report the concrete device/compute targets the installed runtime can execute.

`RunnerPolicyPlanner` derives a CPU-thread and system-memory budget from the processing
profile. `StrategyEvaluator` admits concrete faster-whisper CPU/int8 and CUDA
candidates against system RAM, device memory, runtime capabilities, and profile intent.
An explicit infeasible strategy is refused instead of silently downgraded.

Shared/unified accelerator memory is charged to system RAM rather than counted as extra
capacity. Unknown accelerator memory is not guessed safe.

Current performance ranks and memory estimates remain conservative heuristics until
representative-device qualification.

## Managed ASR model custody

A safe strategy is not executable until its selected faster-whisper model has a verified
managed revision.

`ModelManager` is the only ASR acquisition/custody path. A plan asks the manager for the
locally revalidated immutable revision. If none exists, planning fails with an
install-first error.

The faster-whisper backend then executes with `local_files_only=True` and that exact
revision. It never downloads ASR weights as a transcription side effect and never falls
back to an arbitrary ambient Hugging Face cache entry or configuration revision.

## Segmentation and checkpointing

EchoFlow owns durable segmentation so interrupted work has deterministic identity:

- exact integer PCM frame boundaries;
- stable zero-based `audio-XXXXXX` work IDs;
- 600-second maximum work windows;
- no overlap;
- one job-scoped model session;
- strictly ordered checkpoint commits; and
- at most one future CPU materialization while accelerated inference handles the
  current segment.

Every completed result is atomically checkpointed before it becomes resumable. The
completed set must remain a contiguous prefix.

The current pre-production checkpoint contract binds source identity, stream choice,
profile, engine/model/revision, execution target, decode settings, enhancement state,
segmentation, resource requirements, and exact frame windows. Resume restores that one
current contract and re-admits current CPU/RAM/accelerator capacity.

EchoFlow does not carry legacy job-plan or language-mode migration branches for
unreleased behavior. A real migration layer should be introduced when a released or
dogfooded contract creates an actual compatibility obligation.

## Multilingual behavior

Automatic faster-whisper decoding uses the current native multilingual behavior for
each durable work unit. With no explicit language, the backend uses an 8-second
multilingual window and disables previous-text conditioning so a prior work unit does
not force a language prompt across a detected change.

Published text-language labels come from the local `LinguaLanguageAttributor`, not from
fabricated per-word acoustic labels. Attribution uses deterministic text units and an
uncertainty floor. Ambiguous short text may remain unlabeled.

This supports language changes better than a job-latched language but is not a claim of
perfect arbitrary word-level or romanized Hinglish attribution.

## Anonymous speaker diarization

Diarization is optional local enrichment with recording-scoped anonymous speaker refs.
It does not perform biometric identity or cross-recording linking.

Its pyannote dependency path is security-gated. The current locked Lightning dependency
is affected by CVE-2026-58659, so EchoFlow blocks diarization before pyannote import or
model acquisition until a compatible patched dependency is available.

Diarization model download authorization remains narrowly separate from ASR model
management for now. This does not reopen a general transcription-time ASR download
path.

## Canonical transcript and exports

Canonical JSON is authoritative. The one current transcript contract records:

- source provenance and selected stream;
- profile/provisional state;
- managed engine/model/revision and execution target;
- language evidence;
- optional enhancement provenance;
- optional diarization provenance/speaker turns; and
- timestamped recognized segments.

TXT, SRT, and WebVTT are deterministic derived views. They can be deleted and
regenerated without changing recognition/checkpoint truth.

## Privacy and observability

Structured logging uses Structlog behind `ILogger`. Routine logs redact local paths by
default. Private job/checkpoint state, model caches, normalized audio, enhanced audio,
and segment materializations are distinct from user-visible transcript artifacts.

POSIX systems enforce owner-only mode bits; Windows uses current-user DACL policy.
These are filesystem access controls, not application-level encryption or secure
erasure.

## Transcript library and retrieval boundary

Canonical transcript JSON remains authoritative. The lexical and semantic databases are
private rebuildable projections and must not contain the only copy of user-authored
information.

`TranscriptIndex` remains the database-neutral lexical port. The current
`DuckDbTranscriptIndex` adapter stores document, segment, and term statistics under
`STATE_DIR/library/transcripts.duckdb` and implements deterministic offline BM25-style
ranking.

Canonical projection now records both the source recording SHA-256 and the SHA-256 of
the exact canonical JSON artifact. The latter is used to detect stale semantic state.

Semantic retrieval is split across narrower capabilities rather than expanding
`TranscriptIndex` into a universal search manager:

- `ChunkingProfile` and `build_search_chunks()` create deterministic derived windows
  anchored to exact canonical segment IDs and timestamps.
- `EmbeddingProvider` separates query-side and passage-side encoding.
- `SentenceTransformersE5Provider` implements strict-local
  `intfloat/multilingual-e5-small` semantics with immutable revision provenance.
- `DuckDbSemanticIndex` stores numeric `FLOAT[]` vectors and performs exact local
  similarity after hard metadata filtering.
- `TranscriptSearch` composes lexical and semantic ranks and implements hybrid RRF.
- `SearchResponse` exposes evidence coordinates plus lexical, semantic, and fused
  ranks for presentation adapters.

`SearchQuery` remains above both storage adapters. User values do not become SQL
fragments.

The first semantic generation records model ID, immutable revision, 384 dimensions,
L2 normalization, mean pooling, dot-product metric, E5 query/passage transforms,
embedding schema, chunking profile, and a corpus fingerprint over canonical JSON
digests. A mismatch between that fingerprint and the current lexical corpus fails
semantic/hybrid retrieval closed.

The Sentence Transformers runtime is lazy and optional. This tranche does not add an
unresolved dependency to `pyproject.toml`; the repository's existing locked dependency
contract remains intact. Lexical retrieval therefore remains available on the base
install even when the optional semantic runtime is absent.

See [corpus-search.md](corpus-search.md) for the full retrieval and data-ownership
contract.

## Capability ownership

| Capability | Owns | Does not own |
|---|---|---|
| `FfprobeMediaProbe` | Source identity and stream metadata | Transcoding |
| `AudioStreamSelector` | Deterministic selected audio stream | FFprobe discovery |
| `RunnerInspector` | Process-visible CPU/RAM facts | Model choice |
| `HardwareTopologyInspector` | Physical accelerator evidence | Runtime support claims |
| `EngineCapabilityRegistry` | Engine/device/compute support | Strategy ranking |
| `StrategyEvaluator` | Safe strategy admission/ranking | Model acquisition |
| `ModelManager` | Managed ASR model custody and revision identity | ASR execution |
| `TranscriptionJobPlanner` | Immutable combined execution plan | Performing work |
| `FfmpegAudioDecoder` | Selected-stream canonicalization | Acoustic enhancement |
| `FfmpegAfftdnEnhancer` | Optional deterministic noise suppression | Source authority |
| `WaveAudioSegmenter` | Exact work windows/materialization | Speech recognition |
| `FasterWhisperSession` | Managed local ASR recognition | Model download |
| `LocalCheckpointStore` | Private resumable evidence | Public artifacts |
| `TranscriptAssembler` | Source-relative assembly | Filesystem policy |
| `LinguaLanguageAttributor` | Conservative text-language labels | Acoustic decoding |
| `SpeakerDiarizer` | Anonymous speaker evidence | Biometric identity |
| `TranscriptExporter` | TXT/SRT/VTT derived publication | Recognition truth |
| `TranscriptIndex` | Database-neutral lexical search contract | Semantic model execution |
| `DuckDbTranscriptIndex` | Private lexical index and BM25 execution | Authoritative transcript state |
| `EmbeddingProvider` | Query/passage embedding semantics | Corpus custody |
| `DuckDbSemanticIndex` | Rebuildable chunks/vector state and exact similarity | Canonical transcript truth |
| `TranscriptSearch` | Lexical/semantic composition and RRF | Storage implementation |
| `TranscriptLibraryService` | Discovery, rebuild, stale-state checks, retrieval, integrity receipts | SQL or canonical transcript ownership |
| `WorkspaceService` | Private/public path allocation | Audio semantics |

Protocols are introduced around real substitutable behavior, not pre-emptively for
every class.

## Current deliberate boundaries

EchoFlow does not currently claim:

- calibrated speed/memory/thermal performance across representative devices;
- that every detected accelerator is usable or faster;
- alternate ASR engines;
- arbitrary word-level code-switch attribution;
- biometric speaker identity;
- simultaneous-speaker/source separation;
- generative audio restoration;
- automatic enhancement selection;
- original SMPTE/container/capture-time provenance beyond source-relative seconds;
- storage durability across sudden power loss;
- malicious same-user TOCTOU resistance;
- secure erasure;
- word-level alignment;
- a qualified/locked Sentence Transformers semantic dependency extra;
- ANN/HNSW, learned reranking, generated corpus answers, or user tags/notes/collections;
  or
- a polished installer or desktop GUI.

The next product work is dogfooding the current execution/retrieval contracts,
representative-device and enhancement qualification, semantic dependency/model-custody
qualification, retrieval UX, and word/timestamp alignment where real use shows the need
for finer evidence coordinates.
