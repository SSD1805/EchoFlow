# Local speech enhancement and noise suppression 🎚️✨

## The human version

Some recordings are just noisy.

Air conditioners hum. Rooms echo. Microphones sit too far away. Someone decides to move
a coffee mug directly on top of the only useful sentence in the interview.

EchoFlow can optionally apply deterministic local noise suppression **before speech
recognition** while preserving the original recording as the authoritative evidence.

The first implementation is intentionally modest. It is not an audio-restoration oracle.
It asks a narrower question:

> Can a conservative, reproducible local transform improve downstream transcription
> without changing source custody, timeline semantics, or resume behavior?

```mermaid
graph LR;
    A[Original recording] --> B[Canonical decode]
    B --> C{Enhancement requested?}
    C -->|no| D[ASR]
    C -->|yes| E[Private noise-suppressed derivative]
    E --> F[Timeline identity checks]
    F --> D
    D --> G[Canonical transcript + provenance]
```

## User surface

Enhancement is off by default.

Enable it explicitly:

```bash
uv run echoflow transcribe recording.m4a --enhance
```

There is no automatic “this sounds noisy, so I turned something on” behavior yet.

That is deliberate. EchoFlow should first collect representative evidence showing when
enhancement improves end-to-end ASR enough to justify extra compute and disk use.

## Source custody

The source recording remains authoritative.

Canonical decoded audio and enhanced audio are private execution material. They are not
published merely because preprocessing happened.

The canonical transcript records which preprocessing affected ASR input, but the
derived WAV does not become a new archival source of truth.

🦝 Derived audio can live under the floorboards. The original recording keeps the deed.

## First provider

The current provider uses FFmpeg's local `afftdn` frequency-domain noise-reduction
filter with one application-owned parameter contract:

```text
afftdn=nf=-50:nr=12
```

Canonical provenance is:

- provider: `ffmpeg-afftdn`;
- operation: `noise_suppression`;
- noise floor: `-50 dB`;
- noise reduction: `12 dB`; and
- provider version: locally verified first line of `ffmpeg -version`.

This provider has no model weights.

EchoFlow does not create a pretend model manifest merely to make the architecture look
uniform.

If a future neural enhancement provider introduces weights, those weights must enter
through the same family of explicit model custody, disk admission, verification, and
immutable revision rules used by other model-backed capabilities.

## Timeline preservation is load-bearing

Enhancement may change **sample values**.

It may not silently change the **shape of the timeline** that transcript timestamps rely
on.

Before accepting the derived WAV, EchoFlow compares input/output:

- channel count;
- sample width;
- sample rate; and
- frame count.

Any mismatch fails closed and the derived output is removed where possible.

The FFmpeg provider is also instructed to emit the same mono 16 kHz PCM16 working format
as canonical decode. That is defense in depth, not permission to resample and then hope
nobody notices.

## Why diarization still sees the unmodified canonical decode

In enhancement v1:

- **ASR** consumes the enhanced derivative when enhancement succeeds;
- **anonymous diarization** continues to consume the unmodified canonical decoded audio.

EchoFlow has not established that denoising improves speaker-boundary evidence.

Preprocessing the diarization input merely because preprocessing helps ASR would be an
unearned assumption.

Future empirical evidence may justify a different provider path, but the change should
be explicit and provenance-bearing.

## Immutable plan and resume behavior

The transcription plan records enhancement mode, provider, parameters, and any future
model identity.

The checkpoint contract records the same structure even when enhancement is off.

Resume therefore cannot switch enhancement on/off, swap provider, or alter parameters
halfway through a recording.

A resumed transcript should not quietly contain two different acoustic preprocessing
regimes.

## Storage admission

Enhancement materializes one additional full-recording canonical-rate WAV in the private
job workspace.

For mono 16 kHz PCM16 audio, the incremental estimate is approximately:

```text
duration_seconds * 16,000 * 1 channel * 2 bytes
```

That cost participates in the same storage admission policy as normalization, segment
materialization, checkpoints, and published artifacts.

EchoFlow should refuse a job before creating a large derivative when available disk
space is below the safe budget.

## Canonical provenance

When enhancement is used, canonical transcript JSON records an
`EnhancementProvenance` object containing:

- provider;
- provider version;
- operation;
- parameters; and
- any future model identity/revision.

This explains which transform affected ASR input.

It does **not** claim that:

- the enhanced audio is authoritative;
- the enhanced audio was published;
- the enhanced audio necessarily sounds better; or
- enhancement necessarily improved ASR for this recording.

When enhancement is off, no enhancement provenance is recorded.

## Failure semantics 🔐

Enhancement fails closed when the user explicitly requested it.

EchoFlow does not silently fall back to raw audio after an enhancement failure and then
pretend the requested plan executed.

Failure cases include:

- FFmpeg unavailable;
- FFmpeg runtime version cannot be verified;
- provider/parameter contract differs from the plan;
- filtering timeout/non-zero exit;
- missing or empty output; or
- output violating canonical timeline identity.

Partial derived output is removed where possible.

Cleanup failure after another primary error is logged and must not replace the primary
exception.

## Mutation-oriented test contract

Tests should kill plausible bad decisions such as:

- `off` accidentally invoking enhancement;
- `on` silently falling back to raw audio;
- ASR reading the raw path after enhancement succeeded;
- diarization unexpectedly reading enhanced audio in v1;
- provider/parameters changing without checkpoint incompatibility;
- enhanced audio disappearing from storage admission;
- frame/sample-rate/channel validation being weakened or inverted;
- partial output surviving a failed transform;
- cleanup masking the primary failure;
- missing canonical enhancement provenance; and
- a future model-backed provider bypassing managed model custody.

Poodle remains targeted qualification for this decision-heavy code rather than a routine
per-commit gate.

## What qualification actually has to measure

The product question is not “does the denoised file sound nicer to a human?”

Qualification should compare **raw ASR** with **enhancement + ASR** on representative
recordings using measures such as:

- WER/CER where reference text exists;
- end-to-end execution time and real-time factor;
- CPU/RAM/accelerator pressure;
- private disk overhead; and
- failure behavior across silence, music, clipping, stationary noise, and non-stationary
  noise.

Only after evidence shows a reliable relationship between input conditions and benefit
should EchoFlow consider an `auto` mode.

## Where source separation belongs later 🧜‍♀️

Noise suppression and source separation are not the same problem.

The current provider tries to suppress background noise while preserving one acoustic
timeline.

**Speech/source separation for overlapping speakers** would attempt to decompose a mixed
recording into estimated speaker/source signals. That introduces substantially more
model/compute cost and harder provenance questions:

- which separated source produced which recognized words;
- how separation uncertainty is represented;
- whether separated outputs remain aligned to the original timeline;
- which model/revision produced them;
- whether source separation actually improves recognition on the target corpus; and
- how derived sources should be retained or discarded.

That is a later capability, after word alignment and overlap representation are strong
enough to show where separation is actually needed.

## Current deliberate limits

The current feature does not provide:

- simultaneous-speaker separation;
- arbitrary music/source isolation;
- generative restoration;
- automatic provider/model selection;
- opaque automatic denoising based on a quality score; or
- automatic publication of enhanced audio.

The stable rule is:

> **Preprocessing may help recognition. The source recording remains truth, and every
> transform that affects ASR must remain explicit, reproducible, private by default,
> and safe to resume.**

That is enough glamour for one filter. 💃
