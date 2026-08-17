# Anonymous speaker diarization

EchoFlow treats speaker diarization as an optional enrichment capability, separate
from speech recognition and separate from human identity.

## Privacy boundary

Diarization answers **who spoke when within this recording** using anonymous,
recording-scoped labels such as `speaker-01` and `speaker-02`. EchoFlow does not use
those labels as biometric identities and does not infer that a speaker in one
recording is the same person in another recording.

The first adapter targets the open-source pyannote `community-1` pipeline. Upstream
currently requires accepting the model conditions and authenticating with Hugging
Face for initial model acquisition. EchoFlow does not store an HF token in its own
configuration. Model acquisition uses the standard Hugging Face credential flow and
the same explicit `--allow-model-download` authorization used for ASR model
retrieval.

Pyannote telemetry is disabled by EchoFlow before the pyannote package is imported.
The adapter records `telemetry_enabled: false` in diarization provenance. Recording
audio remains local during inference.

## Installation

Diarization is deliberately not part of the ordinary transcription dependency set.
Pyannote brings a large PyTorch-based dependency graph and must be installed
explicitly:

```bash
uv sync --locked --extra transcription --extra diarization
```

The first model acquisition also requires that the user has accepted the upstream
Community-1 model conditions and authenticated through Hugging Face's supported
credential mechanism. EchoFlow does not put access tokens in `.env` or canonical
artifacts.

## CLI contract

Diarization is opt-in:

```bash
uv run echoflow transcribe interview.wav --diarize --allow-model-download
```

If the speaker count is known, the user can provide an exact count:

```bash
uv run echoflow transcribe focus-group.wav --diarize --speakers 4
```

Or a bounded range:

```bash
uv run echoflow transcribe meeting.wav --diarize --min-speakers 2 --max-speakers 6
```

Exact and bounded speaker-count options are mutually exclusive. Speaker-count
options are invalid without `--diarize`.

## Evidence model

The primary diarization evidence is a source-relative speaker-turn timeline:

```text
00:00.0 ─ 00:12.4  speaker-01
00:12.4 ─ 00:18.8  speaker-02
00:18.1 ─ 00:20.0  speaker-01   # overlap can exist
```

Raw backend labels are not stable API. EchoFlow sorts turns deterministically and
maps backend labels to `speaker-01`, `speaker-02`, and so on in first-seen timeline
order.

Canonical transcript schema version 3 stores both the exact `speaker_turns` and the
diarization provenance. Non-diarized transcripts remain schema version 2 and retain
their existing wire shape.

## Conservative text projection

ASR segments and diarization turns are produced independently. Without word-level
alignment, an ASR segment can cross a speaker handoff or overlap two speakers.
EchoFlow therefore only assigns `RecognizedSegment.speaker_ref` when exactly one
unique diarized speaker overlaps that segment.

```text
ASR segment overlaps speaker-01 only
    → speaker_ref = speaker-01

ASR segment crosses speaker-01 → speaker-02
    → speaker_ref = null

ASR segment overlaps speaker-01 + speaker-02
    → speaker_ref = null
```

The exact turn evidence is still preserved even when text projection is ambiguous.
This avoids converting uncertain temporal reconciliation into false speaker
precision. A later alignment capability can split or associate words more finely.

Derived TXT, SRT, and WebVTT views prefix an unambiguous segment with its anonymous
speaker label. Ambiguous segments remain unlabeled. Export rendering never changes
timestamps or becomes canonical custody.

## Model and dependency boundary

The adapter resolves the configured pyannote snapshot into EchoFlow's private model
cache. With `--allow-model-download` absent, snapshot resolution is cache-only. Once
resolved, pyannote receives the local snapshot path for inference.

The `diarization` extra is intentionally separate because the current pyannote 4.x
stack resolves a substantial PyTorch dependency graph. Representative CPU-only
Windows/Linux/macOS installation size, peak RAM, and real-time factor still require
physical-device qualification before EchoFlow should advertise diarization as
appropriate for an 8 GB machine.

## Current evidence and deliberate limits

The adapter, cache-only/download policy, telemetry-disable behavior, deterministic
label normalization, canonical schema, executor integration, conservative fusion,
and derived exports are covered by deterministic tests.

A real pyannote Community-1 model inference acceptance is **not yet automated**
because the model is gated by upstream conditions/authentication. Until that lane is
qualified, EchoFlow should not claim that real pyannote inference has been proven in
CI.

This capability does not provide:

- biometric speaker identification;
- cross-recording speaker linking;
- guaranteed word-level speaker attribution;
- a claim that speaker labels are correct when temporal evidence is ambiguous;
- a lightweight dependency footprint on low-memory devices.
