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
MediaInfo
  source fingerprint
  container duration
  discovered streams
  codec/sample-rate/channel metadata
    ↓
AudioStreamSelector
  first audio stream by default
  or explicit --audio-stream INDEX
    ↓
TranscriptionJobPlanner
  runner/resource policy
  ASR strategy
  canonical-audio plan
    ↓
DIRECT if already canonical
or
FFmpeg extraction + normalization
    ↓
canonical PCM16 mono 16 kHz WAV
    ↓
exact integer-frame windows
    ↓
faster-whisper
    ↓
source-relative transcript assembly
    ↓
canonical JSON → TXT/SRT/VTT views
```

## What the media probe does

`FfprobeMediaProbe` is read-only inspection. It does not transcode media or choose a
transcription strategy. For one local file it:

- snapshots filesystem identity before inspection;
- runs FFprobe with a file-only protocol whitelist;
- reads container duration and stream metadata;
- validates that at least one audio stream exists;
- fingerprints the complete source with SHA-256;
- snapshots filesystem identity again and refuses the input if it changed while
  being inspected;
- returns immutable `MediaInfo` metadata.

The source path is required locally to perform work, but routine logs omit paths by
default.

## Stream selection

`AudioStreamSelector` makes one deterministic choice from the streams returned by the
probe. Without a user override, the first discovered audio stream is selected. With
`--audio-stream INDEX`, EchoFlow validates that the requested index is an audio
stream and records it in the job/source contract. Resume restores the same stream
index and refuses a changed source contract.

Selection does not mutate FFprobe's discovered stream metadata. It returns a new
`MediaInfo` value whose `primary_audio_stream_index` identifies the chosen stream.

## Canonical audio format

The current transcription planner uses one canonical segmentation representation:

| Property | Value |
|---|---|
| container | WAV |
| audio codec | signed 16-bit little-endian PCM (`pcm_s16le`) |
| sample rate | 16,000 Hz |
| channels | 1 (mono) |

If a source WAV already satisfies this contract, the planner chooses `DIRECT` and no
normalization copy is produced. All other supported audio-bearing media uses
`FFMPEG_NORMALIZE`.

The FFmpeg normalization command maps exactly the selected audio stream, drops
video/subtitle/data streams, sets the planned channel count/sample rate/codec, and
writes `normalized.wav` inside the private job workspace. The normalized WAV is an
execution artifact, not a public transcript artifact and not a second source of
truth.

## Timestamp basis

EchoFlow's current public transcript timestamps are **elapsed seconds from the start
of the selected recording audio**, with zero as the source-relative origin.

Normalization does not create a new public timeline. The canonical WAV exists so
segmentation can use exact PCM frame arithmetic. Each application-owned segment is
represented by integer `start_frame` and `end_frame` offsets. The corresponding
seconds are derived from those frames and the canonical sample rate.

faster-whisper returns timestamps local to the materialized work interval. During
assembly, EchoFlow adds the interval's source-relative offset and produces one
continuous transcript timeline. For example:

```text
work interval 0 starts at 0 s
engine timestamp 12.4 s   → canonical timestamp 12.4 s

work interval 7 starts at 4200 s
engine timestamp 21.7 s   → canonical timestamp 4221.7 s
```

SRT and WebVTT are rendered from those canonical timestamps, so application-owned
checkpoint/segmentation boundaries never reset subtitle time to zero.

## What is not currently preserved

The source-relative timeline is not the same thing as every possible media timebase.
EchoFlow does **not** currently claim to preserve or expose:

- arbitrary non-zero container/stream presentation timestamp origins;
- SMPTE timecode tracks;
- camera/device wall-clock capture time;
- synchronization offsets between independently recorded devices.

Those are legitimate future provenance capabilities. They should be represented by a
versioned timeline/timecode model rather than overloaded onto the existing
source-relative seconds.

## Why normalization remains separate from inspection

Inspection answers **what is this source?** Selection answers **which audio stream are
we using?** Normalization answers **what deterministic audio representation will the
engine and segmenter consume?** Keeping those responsibilities separate means
metadata discovery remains side-effect free while FFmpeg execution stays inside the
private transcription workspace.
