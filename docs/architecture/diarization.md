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

## Temporary upstream security gate

As of August 2026, pyannote 4.0.7 requires Lightning and the current lock resolves
Lightning 2.6.5. Lightning 2.6.5 is affected by CVE-2026-58659 /
PYSEC-2026-3624, a checkpoint-loading remote-code-execution vulnerability. Pyannote
subclasses `lightning.LightningModule` and loads pretrained model checkpoints through
Lightning, so this advisory intersects EchoFlow's actual diarization path rather than
being an unrelated transitive dependency.

Upstream merged the fix in July 2026, but no patched normal 2.x Lightning release is
available yet. EchoFlow therefore fails closed: before importing pyannote or resolving
or downloading any diarization model, it inspects the installed Lightning release.
Known-affected releases and versions whose safety cannot be established are rejected.
The current locked 2.6.5 runtime is consequently **not executable for diarization**.

Dependency auditing carries a single documented exception for PYSEC-2026-3624 while
that compensating control is in place. All other advisories still fail the audit.
The exception and runtime gate should be removed once a compatible upstream release
containing the merged fix is available and qualified.

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

While the temporary Lightning security gate above is active, these diarization
commands fail before pyannote import or model acquisition rather than executing the
known-vulnerable checkpoint-loading path.

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

## Evidence ladder and deliberate limits

The adapter, cache-only/download policy, telemetry-disable behavior, deterministic
label normalization, canonical schema, executor integration, conservative fusion,
derived exports, and fail-closed Lightning security gate are covered by deterministic
tests.

The locked diarization dependency graph is included in normal and scheduled
vulnerability auditing. A separate distribution lane installs `echoflow[diarization]`
from the built wheel outside the source checkout and imports the real pyannote and
PyTorch runtimes. This proves packaging/runtime compatibility without authorizing
model execution.

A dedicated real-model acceptance workflow exists but remains intentionally blocked
by the Lightning security gate until a patched compatible release is available. Once
unblocked, that lane is manual and credential-gated: it generates a non-sensitive
local speech fixture, runs real Community-1 inference, and then reopens the same cache
with model downloads disabled. Ordinary pull-request CI remains free of gated
credentials and model downloads.

Until both the upstream security gate is cleared and the real-model lane has
completed successfully on representative hardware, EchoFlow should describe
Community-1 diarization as integrated but not operationally qualified.

This capability does not provide:

- biometric speaker identification;
- cross-recording speaker linking;
- guaranteed word-level speaker attribution;
- a claim that speaker labels are correct when temporal evidence is ambiguous;
- a lightweight dependency footprint on low-memory devices.
