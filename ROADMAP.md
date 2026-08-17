# EchoFlow roadmap

EchoFlow is a local-first, privacy-conscious, resource-aware audio transcription and
analysis application. The project does not try to out-engine speech-recognition
runtimes. Its job is to make sensitive local transcription dependable, resumable,
inspectable, portable, and usable on ordinary computers.

The current foundation already includes:

- real faster-whisper CPU/int8 transcription;
- deterministic FFprobe inspection and audio-stream selection;
- FFmpeg extraction/normalization to canonical mono 16 kHz PCM16 WAV when needed;
- exact frame-based segmentation with one job-scoped model session;
- private durable checkpoints and validated resume;
- source-relative canonical timestamps with TXT/SRT/WebVTT derived exports;
- process-visible CPU/memory admission and storage preflight;
- cross-platform private-storage enforcement for Windows and POSIX systems;
- empirical benchmarking instrumentation;
- real native-media, abrupt-process, clean-wheel, and known-speech acceptance lanes;
- multilingual faster-whisper decoding plus conservative local language attribution;
- a database-neutral `TranscriptIndex` application port for a future rebuildable
  transcript library.

Canonical transcript JSON and checkpoint files remain authoritative. Any future
search/index database is derived state and must be rebuildable from canonical
artifacts.

## Near-term direction

The next development sequence should improve user value rather than continuing to
front-load speculative infrastructure:

1. **Job lifecycle and progress UX.** Add discoverable job status, progress, resume,
   discard/cleanup, and graceful interruption so normal users can understand what a
   long transcription is doing and recover it intentionally.
2. **Model management.** Add local model inventory, recommendation, explicit download,
   verification/provenance, and removal. Integrate model-storage requirements with
   disk admission once inventory is authoritative.
3. **Release/install experience.** Establish a supported non-developer installation
   path before a desktop UI grows around a source-checkout workflow.
4. **Canonical enrichment semantics.** Evolve the transcript contract for additional
   timestamped enrichments while keeping recognition text/provenance separate from
   enrichment provenance.
5. **Anonymous speaker diarization.** Evaluate and integrate a local diarization
   capability that produces recording-scoped speaker references such as
   `speaker-01`, not biometric identity.
6. **Representative-device qualification.** Continue collecting benchmark evidence
   from 8 GB Windows, 16 GB commodity machines, Apple Silicon, and larger
   workstations. Use repeated measurements to calibrate heuristics rather than one
   hosted-CI timing sample.
7. **Transcript library/search implementation.** When the user-facing library is
   scheduled, implement the existing `TranscriptIndex` port with a rebuildable local
   backend. DuckDB remains the leading default candidate; SQLite/PostgreSQL or other
   adapters may implement the same behavioral port when there is a real use case.
8. **Bounded failure recovery.** Add deterministic audio bisection/retry policy if
   real long-recording failures justify it.

## Current capability boundaries

- Multilingual decoding can reconsider acoustic language within a durable work unit;
  language attribution is conservative and may intentionally leave ambiguous text
  unlabeled.
- Clause/utterance-level code switching is supported better than arbitrary word-level
  or romanized Hinglish attribution. Fine-grained language ID remains a research
  direction rather than a solved claim.
- Transcript timestamps are elapsed source-relative seconds from the selected audio
  origin. EchoFlow does not yet expose arbitrary container PTS origins, SMPTE
  timecode, or wall-clock capture timestamps as separate provenance.
- Speaker diarization is not yet implemented. The canonical model has nullable
  `speaker_ref` space so diarization can enrich recognition without redefining ASR
  text.
- GPU strategies, alternate ASR engines, distributed execution, semantic embeddings,
  and a desktop GUI remain later work.

## Research candidates

These are directions to investigate, not committed release promises:

- finer-grained language attribution for intra-clause and romanized code switching;
- anonymous speaker diarization, overlap handling, and optional user-assigned labels;
- alignment/word timestamps as a separate enrichment capability;
- original media timecode/capture-time provenance beyond source-relative seconds;
- local lexical and metadata search across transcript collections;
- optional semantic embeddings and hybrid lexical/semantic retrieval;
- multiple local ASR engine adapters when they provide a meaningful hardware,
  accuracy, packaging, or deployment advantage;
- GPU execution only after representative measurements justify the additional
  dependency/resource surface.

The order can change when benchmarks, security review, implementation complexity, or
actual dogfooding contradicts an assumption. The stable direction is narrower:
**make sensitive local transcription boringly dependable.**
