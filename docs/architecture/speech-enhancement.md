# Local speech enhancement and noise suppression

## Purpose

EchoFlow can optionally preprocess difficult recordings before automatic speech
recognition while preserving the original recording as the authoritative evidence.
The first implementation is deliberately narrow: deterministic local background-noise
suppression, explicit user selection, private derived audio, and complete preprocessing
provenance.

The feature is not a restoration engine and does not claim that processed audio is a
better archival source. Its purpose is to test whether a conservative local transform
can improve downstream transcription on noisy recordings without weakening custody,
resumability, or timeline guarantees.

## Pipeline boundary

The current processing path is:

```text
source media
  -> selected audio stream
  -> canonical decode (mono, 16 kHz, PCM16 WAV)
  -> optional private noise suppression
  -> segmentation
  -> managed local ASR
  -> canonical transcript
```

The source media remains authoritative. Canonical decoded audio and enhanced audio are
private execution material. They are deleted when no longer required and are not
published merely because enhancement was enabled.

For the first version, anonymous speaker diarization deliberately reads the unmodified
canonical decoded audio while ASR reads the enhanced derivative. EchoFlow does not yet
claim that denoising improves speaker-boundary evidence, so it does not silently
preprocess the diarization input.

## Explicit off/on contract

Enhancement is off by default. A user enables it explicitly with:

```text
echoflow transcribe recording.m4a --enhance
```

There is no automatic enhancement selector in the first version. EchoFlow must first
collect representative evidence showing when enhancement improves end-to-end ASR
accuracy enough to justify its extra compute and storage cost.

The immutable plan records the enhancement mode, provider, parameters, and any future
model identity. The checkpoint contract records the same structure even when
preprocessing is off. Resume therefore cannot switch provider, parameters, or off/on
state halfway through a recording.

## First provider

The first provider is FFmpeg's local `afftdn` frequency-domain noise-reduction filter.
EchoFlow pins an application-owned parameter contract:

```text
afftdn=nf=-50:nr=12
```

The corresponding application provenance is:

- provider: `ffmpeg-afftdn`;
- operation: `noise_suppression`;
- noise floor: `-50 dB`;
- noise reduction: `12 dB`; and
- provider version: the locally verified first line of `ffmpeg -version`.

The provider is model-free. EchoFlow does not create a fake model manifest merely to
make the abstraction look uniform. If a future neural provider introduces model
weights, those weights must use the model-management custody, verification, disk
admission, explicit-install, and immutable-revision contracts.

## Timeline preservation

Enhancement must not change EchoFlow's source-relative transcript timeline.

Before accepting an enhanced WAV, EchoFlow compares the canonical input and derived
output for:

- channel count;
- sample width;
- sample rate; and
- frame count.

Any mismatch fails closed and the derived output is removed. This protects the
assumption that segment frame intervals and source-relative timestamps refer to the
same acoustic timeline before and after preprocessing.

The provider is also instructed to emit mono 16 kHz PCM16 WAV, matching the canonical
decode contract. This is defense in depth rather than permission for the provider to
resample arbitrarily.

## Storage admission

Enhancement materializes one additional full-recording canonical-rate WAV in the
private job workspace. Planning therefore adds that derivative to the private storage
estimate before job execution begins.

For mono 16 kHz PCM16 audio, the incremental storage estimate is approximately:

```text
duration_seconds * 16,000 * 1 channel * 2 bytes
```

The estimate participates in the same storage admission policy as normalization,
segment materialization, checkpoints, and published outputs. EchoFlow should refuse a
job before creating large private derivatives if local free space is below the safe
budget.

## Provenance

When enhancement is used, canonical transcript JSON records an
`EnhancementProvenance` object containing the provider, provider version, operation,
parameters, and any future model identity/revision.

The provenance describes the preprocessing that affected ASR input. It does not make
the enhanced WAV authoritative and it does not imply that the enhanced audio was
published.

When enhancement is off, the transcript records no enhancement provenance.

## Failure semantics

Enhancement fails closed. EchoFlow does not silently fall back to raw audio when the
user explicitly requested preprocessing.

Failure cases include:

- FFmpeg unavailable;
- FFmpeg runtime version cannot be verified;
- provider or parameter contract differs from the planned configuration;
- filtering times out or exits unsuccessfully;
- output is missing or contains no usable samples; or
- output violates the canonical timeline identity.

Partial derived output is removed where possible. Cleanup failure after another primary
failure is logged and must not replace the primary exception.

## Mutation-oriented test contract

Tests should be designed so the following plausible bad edits are killed before a
broad mutation run is needed:

- `off` accidentally invokes the enhancer;
- `on` silently falls back to raw audio after provider failure;
- ASR uses the raw path even though enhancement succeeded;
- diarization unexpectedly uses the enhanced path in v1;
- provider or parameter values can change without checkpoint incompatibility;
- enhanced audio is omitted from storage admission;
- frame-count/sample-rate/channel validation is weakened or inverted;
- partial output survives a failed transform;
- enhanced cleanup is skipped or masks a primary failure;
- provider/version/parameter provenance is omitted from the canonical transcript; and
- a future model-backed provider bypasses managed model custody.

Poodle remains a targeted manual qualification technique for this decision-heavy code,
not an automatic per-commit gate.

## Qualification criteria

The product question is not whether denoised audio sounds nicer. Qualification compares
raw ASR with enhancement-plus-ASR on representative noisy recordings and measures at
least:

- word error rate or another transcription-accuracy measure when reference text exists;
- character error rate where appropriate;
- end-to-end execution time and real-time factor;
- CPU/RAM pressure and accelerator impact when relevant;
- private disk overhead; and
- failure behavior on silence, music, clipping, stationary noise, and non-stationary
  noise.

Only after measurements show a reliable relationship between input conditions and
end-to-end benefit should EchoFlow consider an `auto` mode.

## Out of scope

The first version does not implement:

- simultaneous-speaker separation;
- arbitrary source separation or music isolation;
- generative audio restoration;
- automatic provider/model selection;
- automatic denoising based on an opaque quality score; or
- publishing enhanced audio by default.

The stable rule is evidence-first: preprocessing may help recognition, but the source
recording remains truth and every transform affecting ASR must remain inspectable,
reproducible, private by default, and safe to resume.
