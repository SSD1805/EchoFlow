# Processing capabilities

EchoFlow should prove one local transcription path before it grows a generic
pipeline framework. The first implementation should expose small capability
contracts that can be composed into a job without requiring every engine to
inherit from a common pipeline base class.

## Product target

EchoFlow aims to be a privacy-by-default, resource-aware, reproducible and
resumable system for sensitive recordings. Its core should remain small enough
for ordinary local installation while optional engines and model weights carry
the unavoidable machine-learning payload. The same planner must behave
coherently on a constrained laptop, a larger workstation, and a container whose
effective limits are smaller than its host.

This target does not imply distributed execution across several machines. It
means one plan respects the resources exposed to the process and records the
decisions required to reproduce that work elsewhere.

The implemented path now covers input validation, SHA-256 fingerprinting,
FFprobe metadata, side-effect-free path resolution, adaptive local CPU strategy
selection, decode strategy, resource estimates, immutable JSON/Rich dry-run
output, local FFmpeg audio normalization, deterministic application-owned PCM
segmentation, one job-scoped CPU/int8 faster-whisper model session, private
per-segment checkpoints, validated resume, source-relative transcript assembly,
resource readmission, and canonical transcript JSON. Model download is disabled
unless the invocation explicitly authorizes it; after completed checkpoints exist,
resume does not authorize a fresh model retrieval.

Video is not a downstream capability. An audio-bearing video container is accepted
at the media boundary, its selected audio stream is extracted, and all video,
subtitle, attachment, and data streams are discarded. Everything after decode sees
the same canonical audio input used for other noncanonical recordings.

## First vertical slice

1. **Probe input**
   - Resolve a local input path without copying the original media.
   - Record size, media type, duration, streams, codec, and a content
     fingerprint.
   - Decide whether the selected input can be decoded directly or requires
     FFmpeg.
2. **Plan the job**
   - Select the transcription engine, model, device, language, and output
     directory.
   - Estimate temporary disk and memory requirements before processing.
   - Produce an immutable plan that can be logged, tested, and persisted.
3. **Decode and normalize**
   - Decode only when the engine cannot consume the original media in EchoFlow's
     canonical segmentation format.
   - Normalize to mono 16 kHz PCM16 WAV for deterministic frame segmentation.
   - Keep temporary media in the private workspace, never in the user's output
     directory.
4. **Segment**
   - Use deterministic source-relative PCM frame windows with stable segment
     identifiers.
   - Segmentation schema version 1 uses sequential, non-overlapping windows and
     a single worker. This deliberately avoids claiming overlap or concurrency
     semantics before they can be reconciled deterministically.
   - Materialize only one segment at a time with bounded reads so large inputs do
     not need to be loaded into memory or duplicated in full.
5. **Transcribe**
   - Hide engine-specific behavior behind a narrow job-scoped session boundary.
   - Load the faster-whisper model once per job and reuse it across every app-level
     segment.
   - Return timestamped segment results rather than writing final files.
6. **Checkpoint**
   - Atomically persist each completed segment result under the private local job
     directory before considering that segment complete.
   - Bind resumable state to the source fingerprint, engine/model/revision,
     decoder, segmentation schema, exact frame windows, and engine package version.
   - Never treat unknown, reordered, corrupt, or incompatible state as completed
     work.
7. **Assemble**
   - Rebase engine-local timestamps onto the source-relative timeline and
     reindex them deterministically.
   - Reject gaps, inconsistent segment order, mixed engine versions, or timestamps
     outside the segment contract.
   - Preserve confidence and engine metadata in the canonical result.
8. **Render artifacts**
   - Write canonical transcript JSON atomically.
   - Derive TXT, SRT, and VTT from that canonical result in future work.
   - Put user-facing artifacts in an explicit output directory, with
     `Downloads/EchoFlow` resolved at the application-configuration boundary.
9. **Retire recovery payloads**
   - Retain checkpoints after interruption so a later process can resume.
   - Remove checkpoint payloads after successful canonical publication on a
     best-effort basis.
   - Treat ordinary deletion as cleanup, not secure erasure.

## Segmentation contract

EchoFlow owns segmentation rather than delegating segment boundaries to the speech
engine. That ownership lets a resumed job prove that it is completing the same work
rather than merely retrying an approximate chunk.

The current contract is intentionally narrow:

- canonical input is uncompressed PCM16 WAV at the planned sample rate and channel
  count;
- boundaries are integer PCM frame offsets, not accumulated floating-point times;
- segment IDs derive from deterministic zero-based ordinals;
- windows exactly cover the decoded source without gaps or overlap;
- default segment duration is 600 seconds;
- concurrency is one;
- overlap is zero;
- only the current segment is materialized as a private temporary WAV;
- the selected model is loaded once for the job, not once per segment;
- assembled timestamps are source-relative and global recognized-segment indices
  are regenerated deterministically.

These restrictions are not performance claims. They establish the stable unit of
completed work required for checkpointing. Bounded parallelism or overlap may be
added only when their reconciliation rules and resource behavior are measured and
testable.

## Screening and resource policy

Fast screening is a separate, provisional product contract rather than a
synonym for a low-quality final transcript.

- `screening` prioritizes time to first useful text and recommends a compact
  model tier.
- Screening results must carry `provisional=true` in their eventual job plan
  and canonical metadata.
- Screening processes the complete source by default. Interval sampling or
  early termination requires a separate explicit user choice so relevant
  material is not silently omitted.
- A screening artifact cannot silently replace a balanced or accuracy-oriented
  canonical transcript.
- Every job plan records the selected profile, runner limits, CPU thread budget,
  memory budget, engine, concrete model, engine-specific parameters, and
  segmentation policy.

Runner inspection uses resources visible to the process, not merely host totals.
On supported systems this includes CPU affinity and cgroup v2 CPU/memory limits.
The runner produces an engine-neutral execution budget. The transcription strategy
evaluator then ranks concrete faster-whisper CPU/int8 strategies against that
budget. Resource figures remain conservative heuristics pending measurements from
the real engine.

## Capability boundaries

| Capability | Owns | Does not own |
|---|---|---|
| `MediaProbe` | Input metadata and decoder requirements | Transcoding |
| `JobPlanner` | Resource checks and immutable execution plan | Performing work |
| `AudioDecoder` | Decode and normalization | Segmentation policy |
| `Segmenter` | Stable segment boundaries and materialization | Speech recognition |
| `TranscriptionSession` | One loaded engine/model and segment recognition | Final file formats |
| `CheckpointStore` | Private resumable segment state and contract validation | Public artifacts |
| `TranscriptAssembler` | Source-relative assembly and result invariants | Filesystem policy |
| `ArtifactRenderer` | JSON/TXT/SRT/VTT rendering | Job state |
| `WorkspaceService` | Private job paths and atomic artifact paths | Audio semantics |

Protocols should be introduced with the first real implementation that needs
them. Empty interfaces, cloud variants, and speculative managers are not part
of the first slice.

## Checkpoint and resume boundary

A checkpoint is a durable assertion that one deterministic segment completed under
a particular transcription contract. EchoFlow stores a versioned manifest and one
JSON envelope per completed segment beneath the private local job directory. It does
not use the operating-system temporary directory for durable resume state because
that state must survive process restarts and reboots.

The manifest contains no source path, source filename, or model-cache path. It binds
the job to source content/media identity, processing profile, engine/model/revision,
decoder settings, segmentation settings, and exact PCM frame windows. Each segment
envelope repeats its window identity and carries a SHA-256 digest of the canonical
result document so accidental corruption is detected before work is skipped.
Unkeyed hashes are integrity checks, not authentication against a malicious process
running as the same user.

Only a contiguous prefix of completed segment checkpoints is resumable. Unknown
segment files, gaps, reordered windows, malformed JSON, oversized state, contract
mismatches, payload-digest failures, or a different installed engine package version
fail closed. The previously detected language is restored into the job-scoped model
session so recognition semantics do not change after restart.

`echoflow transcribe INPUT --resume JOB_ID` still requires the original input path.
The input is freshly probed and fingerprinted rather than trusting a stored path.
If the current plan does not match the persisted contract, resume is refused. This
keeps explicit profile/model choices from being silently changed across a restart.

Checkpoint transcript fragments are sensitive plaintext local state. They are not
masked because exact resume requires exact output. They are never public artifacts
or routine log fields. Successful final publication triggers best-effort checkpoint
cleanup; interruption retains them for recovery. Application-level encryption,
secure erasure, and OS-specific ACL hardening remain separate security work.

## Bounded audio bisection

Bisection is a recovery policy for an input-related segment failure, not the
default segmentation algorithm.

1. Retry a transient engine failure once without changing the segment.
2. Do not bisect configuration, dependency, capacity, cancellation, or
   permission failures.
3. If a deterministic input/decoder failure remains and the segment is longer
   than the minimum duration, split it at the midpoint.
4. Give both children stable lineage derived from the parent segment ID.
5. Process children independently and checkpoint each successful result.
6. Stop at a configured maximum depth or minimum duration and report the exact
   failed interval.

The limits belong in future processing configuration, with conservative initial
defaults such as a 15-second minimum segment and three bisection levels. They must
be validated against real audio before becoming compatibility guarantees.

## Sequence of implementation

1. Extend the implemented job/artifact path objects with input metadata,
   job-plan, segment, and transcript value objects as each capability arrives.
2. Implement media probing and a `transcribe --dry-run` planning command.
   **Implemented.**
3. Implement one CPU transcription engine for one supported input path.
   **Implemented for direct canonical audio and FFmpeg-normalized audio-bearing media.**
4. Add deterministic segmentation, one job-scoped model session, and assembly.
   **Implemented sequentially with segmentation schema version 1.**
5. Add durable per-segment checkpoints and resume validation.
   **Implemented with private local checkpoint schema version 1.**
6. Add JSON-derived TXT output, then SRT and VTT.
7. Add bounded audio bisection using recorded stage/segment attempts.
8. Add calibrated local performance measurements and only then evaluate bounded
   parallelism or additional execution strategies.
9. Add alternative engines or GPU execution only after the same contract suite
   can exercise both implementations.

## Tree-sitter decision

Tree-sitter is intentionally not a dependency. EchoFlow is a Python audio
application, and pytest already discovers its test files. Python's standard
`ast` module is sufficient if a later developer tool needs structural Python
inspection. Tree-sitter becomes justified only if EchoFlow itself must parse
multiple programming languages or incremental source edits as product data.
