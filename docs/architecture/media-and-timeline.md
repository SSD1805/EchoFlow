# Media normalization and transcript timeline

EchoFlow treats every supported recording as an **audio-bearing local media source**.
Audio files and videos enter through the same inspection boundary. Video is not a
separate downstream pipeline: EchoFlow selects one audio stream and discards video,
subtitle, attachment, and data streams before transcription work begins.

## Pipeline

```text
local recording
    ↓
FFprobe media inspection
    ↓
MediaInfo + complete source fingerprint
    ↓
AudioStreamSelector
  first audio stream by default
  or explicit --audio-stream INDEX
    ↓
TranscriptionJobPlanner
  runner/resource policy
  managed ASR strategy + immutable model revision
  canonical-audio plan
  optional enhancement contract
    ↓
DIRECT if already canonical
or
FFmpeg extraction + normalization
    ↓
canonical PCM16 mono 16 kHz WAV
    ↓
optional private FFmpeg noise suppression
    ↓
exact integer-frame windows
    ↓
managed local faster-whisper ASR
    ↓
source-relative transcript assembly
    ↓
canonical JSON → TXT/SRT/VTT views
```

When enhancement is enabled, ASR reads the private enhanced derivative. Anonymous
speaker diarization deliberately continues to read the unmodified canonical decoded
audio in the first enhancement version.

## What the media probe does

`FfprobeMediaProbe` is read-only inspection. It does not transcode media, install
models, choose preprocessing, or choose a transcription strategy. For one local file
it:

- snapshots filesystem identity before inspection;
- runs FFprobe with a file-only protocol whitelist;
- reads container duration and stream metadata;
- validates that at least one audio stream exists;
- fingerprints the complete source with SHA-256;
- snapshots filesystem identity again and refuses the input if it changed during
  inspection; and
- returns immutable `MediaInfo` metadata.

The source path is required locally to perform work, but routine logs omit paths by
default.

## Stream selection

`AudioStreamSelector` makes one deterministic choice from streams returned by the
probe. Without an override, the first discovered audio stream is selected. With
`--audio-stream INDEX`, EchoFlow validates that the requested index is audio and records
it in the job/source contract. Resume restores the same stream index and refuses a
changed source contract.

Selection does not mutate FFprobe's discovered metadata. It returns a new `MediaInfo`
whose `primary_audio_stream_index` identifies the chosen stream.

## Canonical audio format

The current segmentation representation is:

| Property | Value |
|---|---|
| container | WAV |
| audio codec | signed 16-bit little-endian PCM (`pcm_s16le`) |
| sample rate | 16,000 Hz |
| channels | 1 (mono) |

If a source WAV already satisfies this contract, the planner chooses `DIRECT` and no
normalization copy is produced. Other supported audio-bearing media uses
`FFMPEG_NORMALIZE`.

Normalization maps exactly the selected audio stream, drops video/subtitle/data
streams, sets the planned channel count/sample rate/codec, and writes `normalized.wav`
inside the private job workspace. The canonical WAV is an execution artifact, not a
public artifact and not another source of truth.

## Optional enhanced derivative

With `--enhance`, EchoFlow applies its current deterministic FFmpeg noise-suppression
contract after canonical decode and before ASR segmentation. The output is
`enhanced.wav` inside the private job workspace.

The enhanced WAV is derived processing material only. It does not replace the original
recording, is not automatically exported, and does not change source custody.

Enhancement is permitted to alter sample values but not the canonical timeline shape.
Before accepting the derivative, EchoFlow compares input and output for:

- channel count;
- sample width;
- sample rate; and
- frame count.

Any mismatch fails closed and the derived file is removed. This protects downstream
frame-window and timestamp assumptions from a preprocessing provider that silently
resamples, trims, pads, or changes channel structure.

See [speech enhancement](speech-enhancement.md) for provider/provenance details.

## Timestamp basis

Public transcript timestamps are **elapsed seconds from the start of the selected
recording audio**, with zero as the source-relative origin.

Neither normalization nor enhancement creates a new public timeline. Canonical and
enhanced WAV files exist so deterministic local processing can operate on a known frame
representation. Each application-owned segment is represented by integer `start_frame`
and `end_frame` offsets; seconds are derived from those frames and the canonical sample
rate.

faster-whisper returns timestamps local to the materialized work interval. Assembly
adds the work interval's source-relative offset and produces one continuous timeline.
For example:

```text
work interval 0 starts at 0 s
engine timestamp 12.4 s   → canonical timestamp 12.4 s

work interval 7 starts at 4200 s
engine timestamp 21.7 s   → canonical timestamp 4221.7 s
```

SRT and WebVTT are rendered from canonical timestamps, so segmentation/checkpoint
boundaries never reset subtitle time to zero.

## Source authority and provenance

The original local media file remains authoritative. EchoFlow separately records:

- source fingerprint and media identity;
- selected audio stream;
- decode strategy;
- managed ASR engine/model/revision and execution target;
- enhancement provider/version/operation/parameters when used;
- language and optional diarization evidence; and
- source-relative segment timestamps.

Derived audio can therefore be discarded without losing the description of how the
canonical transcript was produced.

## What is not currently preserved

The source-relative timeline is not every possible media timebase. EchoFlow does not
currently claim to preserve or expose:

- arbitrary non-zero container/stream presentation timestamp origins;
- SMPTE timecode tracks;
- camera/device wall-clock capture time; or
- synchronization offsets between independently recorded devices.

Those are legitimate future provenance capabilities. They should be represented by a
dedicated timeline/timecode model rather than overloaded onto elapsed seconds.

## Why the stages remain separate

Inspection answers **what is this source?** Selection answers **which audio stream are
we using?** Normalization answers **what deterministic representation will local
processing consume?** Enhancement answers **did the user request a provenance-bearing
acoustic transform before ASR?**

Keeping those responsibilities separate leaves metadata discovery side-effect free,
keeps source authority explicit, and lets future preprocessing providers change without
rewriting media inspection or transcript timeline semantics.
