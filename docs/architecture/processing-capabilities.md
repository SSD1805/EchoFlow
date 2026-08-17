# Processing capabilities

EchoFlow composes small local capabilities into one reproducible transcription job.
It deliberately avoids a generic pipeline/plugin framework until multiple real
implementations require one.

For the detailed media normalization and timestamp contract, see
[media-and-timeline.md](media-and-timeline.md).

## Current transcription path

```text
local recording
    ↓
FFprobe inspection + source fingerprint
    ↓
deterministic audio-stream selection
    ↓
process-visible CPU/memory inspection
    ↓
resource policy + faster-whisper strategy selection
    ↓
canonical-audio plan
    ↓
DIRECT or FFmpeg normalization
    ↓
exact PCM frame windows
    ↓
job-scoped faster-whisper CPU/int8 session
    ↓
private per-window checkpoint
    ↓
source-relative transcript assembly
    ↓
local language attribution
    ↓
canonical JSON
    ↓
TXT / SRT / WebVTT derived views
```

The current implementation has executed through real FFmpeg/FFprobe on Linux,
macOS, and Windows CI and through real faster-whisper/CTranslate2 known-speech
acceptance. Hosted CI proves contracts and portability; it is not representative
performance calibration.

## Media inspection

`FfprobeMediaProbe` owns source facts, not transcoding. It resolves one local input,
reads container/stream metadata with a file-only FFprobe protocol, fingerprints the
source, and refuses a file that changes during inspection. `AudioStreamSelector`
then chooses one discovered audio stream, using the first audio stream by default or
an explicit `--audio-stream INDEX`.

The selected stream index is part of source/checkpoint provenance. Resume re-probes
the original source and restores the checkpointed stream choice rather than silently
selecting a different track.

## Canonical audio

The planner records one immutable `DecodeConfiguration`. The current canonical
segmentation format is:

- WAV container;
- `pcm_s16le` audio;
- 16,000 Hz sample rate;
- mono.

Already-canonical WAV may use `DIRECT`. Other supported audio-bearing media uses
`FFMPEG_NORMALIZE`. FFmpeg maps exactly the selected audio stream and discards video,
subtitle, attachment, and data streams. Temporary normalized audio stays inside the
private job workspace.

Normalization is representation conversion, not a new public timeline. Exact PCM
frame offsets define application work windows; assembly rebases engine-local
recognition timestamps onto one continuous source-relative timeline.

## Compute and strategy policy

The `runner` package means the process-visible execution environment, not a workflow
runner. `RunnerInspector` observes effective CPU and memory, including relevant
process/container limits. `RunnerPolicyPlanner` converts those facts and a processing
profile into a CPU-thread and memory budget. The faster-whisper strategy evaluator
then chooses a concrete CPU/int8 model strategy that fits that budget.

Current strategies remain conservative heuristics pending representative-device
calibration. EchoFlow does not interpret hosted-runner timing as physical-device
performance truth.

## Segmentation and checkpointing

EchoFlow owns durable application segmentation so an interrupted job can prove what
work completed. Segmentation schema v1 is intentionally sequential and
non-overlapping:

- exact integer PCM frame boundaries;
- stable zero-based `audio-XXXXXX` work IDs;
- 600-second maximum durable work windows;
- concurrency one;
- overlap zero;
- one materialized private segment at a time;
- one loaded faster-whisper model session reused across the job.

Each completed work result is atomically checkpointed beneath the private job state
before the executor advances. Resume validates source identity, stream choice,
engine/model/revision, decoder, segmentation, resource requirements, and checkpoint
integrity before reusing completed work.

Schema-1 checkpoint plans retain their legacy job-latched automatic language
semantics. New schema-2 plans use faster-whisper native multilingual decoding and do
not silently rewrite old interrupted jobs under new language behavior.

## Multilingual behavior

New jobs use faster-whisper's native multilingual mode with the versioned
`native_multilingual_v1` policy. The currently qualified contract uses an 8-second
internal multilingual window and disables previous-text conditioning so a prior
language prompt is not carried across a detected language change.

Published text-language labels come from the local `LinguaLanguageAttributor`, not
from a fabricated per-ASR-segment acoustic label. Attribution uses deterministic
clause/utterance-sized text units plus an uncertainty floor. Ambiguous short text may
remain unlabeled rather than receive false precision.

This is useful for language changes such as English/French. It is not a claim of
perfect arbitrary word-level or romanized Hinglish attribution.

## Canonical transcript and exports

Canonical JSON is authoritative. It records source provenance, execution profile,
engine provenance, language evidence, timestamped recognized segments, and optional
language spans. `speaker_ref` is currently nullable semantic space for future
anonymous diarization.

TXT, SRT, and WebVTT are deterministic derived views. They can be deleted and
regenerated without changing recognition/checkpoint truth. Subtitle timestamps come
from the canonical source-relative segment timeline.

## Privacy and observability

Structured logging is implemented with Structlog behind the narrow `ILogger`
capability. `echoflow.core.observability` is the canonical home for logging setup and
path-disclosure policy. Routine logs omit local paths unless the user explicitly
selects full path disclosure.

Private job/checkpoint state is distinct from public transcript artifacts. POSIX
systems enforce owner-only mode bits; Windows uses a current-user DACL policy. These
controls are filesystem access restrictions, not application-level encryption or
secure erasure.

## Transcript library boundary

`TranscriptIndex` is a database-neutral application port for **derived, rebuildable**
transcript search state. It deliberately exposes transcript-library behavior instead
of generic SQL. Future DuckDB, SQLite, PostgreSQL, or other adapters can implement the
same port when there is a real product need.

The database is never canonical custody of research recordings or transcripts.
Deleting the index must not delete canonical JSON or checkpoint truth.

## Capability ownership

| Capability | Owns | Does not own |
|---|---|---|
| `FfprobeMediaProbe` | Source identity, container/stream metadata | Transcoding |
| `AudioStreamSelector` | Deterministic chosen audio stream | FFprobe discovery |
| `RunnerInspector` | Process-visible CPU/memory facts | Model choice |
| `RunnerPolicyPlanner` | CPU/memory job budget | ASR execution |
| `TranscriptionJobPlanner` | Immutable combined execution plan | Performing work |
| `FfmpegAudioDecoder` | Selected-stream extraction and canonical normalization | Segmentation policy |
| `WaveAudioSegmenter` | Exact frame windows/materialization | Speech recognition |
| `FasterWhisperSession` | Loaded ASR engine/model and recognition | Final file formats |
| `CheckpointStore` | Private durable resumable state | Public artifacts |
| `TranscriptAssembler` | Source-relative timestamp assembly | Filesystem policy |
| `LinguaLanguageAttributor` | Conservative local text-language labels | Acoustic decoding |
| `TranscriptExporter` | TXT/SRT/VTT derived publication | Recognition truth |
| `TranscriptIndex` | Rebuildable transcript-search behavior | Canonical custody |
| `WorkspaceService` | Private/public path allocation | Audio semantics |

Protocols are introduced around real substitutable behavior, not pre-emptively for
every class.

## Current deliberate boundaries

EchoFlow does not currently claim:

- calibrated speed/memory performance across representative physical devices;
- GPU strategy support;
- alternate ASR engines;
- anonymous speaker diarization;
- arbitrary word-level code-switch attribution;
- original SMPTE/container/capture-time provenance beyond source-relative seconds;
- storage durability across sudden power loss;
- malicious same-user TOCTOU resistance;
- biometric speaker identity;
- a production transcript-library database backend;
- a desktop GUI or consumer installer.

The next roadmap priority is product-facing lifecycle/progress UX, followed by model
management, installation/release ergonomics, canonical enrichment semantics, and
anonymous diarization.
