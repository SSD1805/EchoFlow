# EchoFlow roadmap

EchoFlow is a local-first, privacy-conscious, resource-aware audio transcription and
analysis application. The project does not try to out-engine speech-recognition
runtimes. Its job is to make sensitive local transcription dependable, resumable,
inspectable, portable, and usable on ordinary computers.

## Current phase

Modern EchoFlow effectively restarted on August 2, 2026. The first phase repaired a
drifted prototype foundation and made the local-first boundary explicit. The second
phase proved real transcription and then hardened the engine around deterministic
segmentation, private checkpoints, resource admission, real acceptance evidence,
multilingual semantics, and anonymous speaker diarization.

The project is now moving from **engine trust** to **product legibility**: the backend
should remain strict and boring while ordinary users gain clear progress, durable job
state, intentional recovery, and eventually a graphical shell that does not redefine
the application underneath it.

The current foundation includes:

- real faster-whisper CPU/int8 transcription;
- deterministic FFprobe inspection and audio-stream selection;
- FFmpeg extraction/normalization to canonical mono 16 kHz PCM16 WAV when needed;
- exact frame-based segmentation with one job-scoped model session;
- private durable checkpoints and validated resume;
- durable private job lifecycle metadata plus discoverable job status and cleanup;
- Rich interactive progress over the same execution-observer seam used by benchmarks;
- source-relative canonical timestamps with TXT/SRT/WebVTT derived exports;
- process-visible CPU/memory admission and storage preflight;
- cross-platform private-storage enforcement for Windows and POSIX systems;
- empirical benchmarking instrumentation;
- native-media, abrupt-process, clean-wheel, known-speech, and diarization evidence
  lanes;
- multilingual faster-whisper decoding plus conservative local language attribution;
- anonymous recording-scoped speaker diarization with conservative text projection;
- a database-neutral `TranscriptIndex` application port for a future rebuildable
  transcript library.

Canonical transcript JSON and checkpoint files remain authoritative. Lifecycle
metadata describes execution state but does not become transcript custody. Any future
search/index database is derived state and must be rebuildable from canonical
artifacts.

## Product and interface direction

EchoFlow remains CLI-first while the backend is still maturing. The CLI should be
pleasant for humans without becoming ambiguous for automation:

- interactive terminals may use Rich progress, tables, clear stage names, and safe
  confirmation prompts;
- `--json` remains deterministic and free of presentation noise;
- long-running work has durable job IDs, status, progress, resume evidence, and
  explicit private-state cleanup;
- a future desktop or web UI should be a presentation adapter over the same
  application services and lifecycle state, not a second implementation of the
  transcription pipeline.

A graphical UI and polished non-developer installer are therefore intentionally
deferred until the backend contracts are mature enough that the UI can stay thin.

## Near-term direction

The next development sequence should improve user value without front-loading
speculative infrastructure:

1. **Finish job-lifecycle qualification and dogfooding.** Exercise interruption,
   resume, stale-process reconciliation, progress rendering, and cleanup on long real
   recordings. Keep lifecycle metadata private and keep published artifacts separate.
2. **Model management.** Add local model inventory, recommendation, explicit download,
   verification/provenance, and removal. Integrate model-storage requirements with
   disk admission once inventory is authoritative.
3. **Representative-device qualification.** Collect repeated benchmark evidence from
   8 GB Windows, 16 GB commodity machines, Apple Silicon, and larger workstations.
   Calibrate strategy heuristics from measurements rather than hosted-CI guesses.
4. **Word/timestamp alignment.** Add alignment as a separate enrichment capability so
   speaker projection can become more precise without rewriting raw ASR or diarization
   evidence.
5. **Transcript library/search implementation.** Implement the existing
   `TranscriptIndex` port with a rebuildable local backend when the user-facing
   library is scheduled. Start with lexical/metadata search before semantic
   embeddings.
6. **Bounded failure recovery.** Add deterministic audio bisection/retry policy only
   if real long-recording failures justify it.
7. **Release/install and graphical UI.** Revisit these after the backend and lifecycle
   contracts have survived representative dogfooding. The eventual interface should
   remain replaceable and thin.

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
- Anonymous speaker diarization is implemented as optional local enrichment. It does
  not perform biometric identity or cross-recording linking, and ambiguous ASR
  segments intentionally remain unlabeled without word-level alignment.
- The pyannote dependency graph is continuously audited and has a clean-install
  acceptance lane. Real Community-1 inference is credential-gated and still requires
  representative-device qualification before EchoFlow should make low-memory
  performance claims.
- Lifecycle state improves discoverability and recovery, but EchoFlow is still a
  synchronous local application rather than a background job daemon or distributed
  task system.
- GPU strategies, alternate ASR engines, distributed execution, semantic embeddings,
  polished installers, and a desktop GUI remain later work.

## Research candidates

These are directions to investigate, not committed release promises:

- finer-grained language attribution for intra-clause and romanized code switching;
- better overlap handling and optional user-assigned display labels for anonymous
  speaker references;
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
**make sensitive local transcription boringly dependable, then make that dependable
system easy to use.**
