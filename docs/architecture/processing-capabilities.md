# Processing capabilities

EchoFlow should prove one local transcription path before it grows a generic
pipeline framework. The first implementation should expose small capability
contracts that can be composed into a job without requiring every engine to
inherit from a common pipeline base class.

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
   - Decode only when the engine cannot consume the original media.
   - Normalize to the engine's required channel count and sample rate.
   - Keep temporary media in the private workspace, never in the user's output
     directory.
4. **Segment**
   - Prefer deterministic time windows with explicit overlap and stable segment
     identifiers.
   - Preserve source-relative timestamps so a resumed job produces the same
     artifact boundaries.
5. **Transcribe**
   - Hide engine-specific behavior behind a narrow transcriber protocol.
   - Return timestamped segment results rather than writing final files.
6. **Assemble**
   - Reconcile overlapping words and segments deterministically.
   - Preserve confidence and engine metadata in the canonical result.
7. **Render artifacts**
   - Write canonical transcript JSON atomically.
   - Derive TXT, SRT, and VTT from that canonical result.
   - Put user-facing artifacts in an explicit output directory, defaulting to
     `Downloads/EchoFlow` only at the CLI boundary.
8. **Record progress**
   - Persist job, stage, segment, attempt, and artifact metadata in SQLite.
   - Store paths and metadata in SQLite, not audio blobs or transcript files.

## Capability boundaries

| Capability | Owns | Does not own |
|---|---|---|
| `MediaProbe` | Input metadata and decoder requirements | Transcoding |
| `JobPlanner` | Resource checks and immutable execution plan | Performing work |
| `AudioDecoder` | Decode and normalization | Segmentation policy |
| `Segmenter` | Stable segment boundaries and lineage | Speech recognition |
| `Transcriber` | Engine invocation and timestamped results | Final file formats |
| `TranscriptAssembler` | Overlap reconciliation and canonical result | Filesystem policy |
| `ArtifactRenderer` | JSON/TXT/SRT/VTT rendering | Job state |
| `JobRepository` | SQLite state and resumability | Artifact contents |
| `WorkspaceService` | Private temp paths and atomic artifact paths | Audio semantics |

Protocols should be introduced with the first real implementation that needs
them. Empty interfaces, cloud variants, and speculative managers are not part
of the first slice.

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

The limits belong in the future processing configuration, with conservative
initial defaults such as a 15-second minimum segment and three bisection levels.
They must be validated against real audio before becoming compatibility
guarantees.

## Sequence of implementation

1. Define input, output, job-plan, segment, transcript, and artifact value
   objects with colocated contract tests.
2. Implement media probing and a `transcribe --dry-run` planning command.
3. Implement one CPU transcription engine for one supported input path.
4. Add deterministic segmentation and assembly.
5. Add JSON and TXT output, then SRT and VTT.
6. Add SQLite checkpoints and resume.
7. Add bounded audio bisection using recorded stage/segment attempts.
8. Add alternative engines or GPU execution only after the same contract suite
   can exercise both implementations.

## Tree-sitter decision

Tree-sitter is intentionally not a dependency. EchoFlow is a Python audio
application, and pytest already discovers its test files. Python's standard
`ast` module is sufficient if a later developer tool needs structural Python
inspection. Tree-sitter becomes justified only if EchoFlow itself must parse
multiple programming languages or incremental source edits as product data.
