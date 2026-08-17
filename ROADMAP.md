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
state, intentional recovery, adaptive use of local hardware, corpus search, and
eventually a graphical shell that does not redefine the application underneath it.

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
- accelerator topology discovery separated from engine capability negotiation;
- engine-neutral strategy admission across system RAM and dedicated/shared/unified
  accelerator memory;
- bounded one-segment CPU preparation overlap for accelerated inference while
  preserving ordered checkpoints and resumability;
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
- hardware selection should happen through typed application services rather than
  CLI-specific GPU switches;
- a future desktop or web UI should be a presentation adapter over the same
  application services, lifecycle state, and search service, not a second
  implementation of the transcription pipeline.

A graphical UI and polished non-developer installer are therefore intentionally
deferred until the backend contracts are mature enough that the UI can stay thin.

## Near-term direction

The next development sequence should improve user value without front-loading
speculative infrastructure:

1. **Finish adaptive-execution qualification and lifecycle dogfooding.** Exercise
   interruption, resume, stale-process reconciliation, progress rendering, accelerator
   re-admission, bounded prefetch cleanup, and long recordings. Keep published
   artifacts separate from private execution state.
2. **Model management.** Add local model inventory, recommendation, explicit download,
   verification/provenance, and removal. Integrate model-storage requirements with
   disk admission once inventory is authoritative.
3. **Representative-device qualification.** Collect repeated benchmark evidence from
   8 GB Windows, 16 GB commodity machines, Apple Silicon, discrete-GPU laptops, and
   larger workstations. Measure cold/warm cache behavior, sustained real-time factor,
   thermal effects, CPU/RAM pressure, and accelerator memory/utilization where the
   backend exposes reliable counters. Calibrate strategy heuristics from measurements
   rather than hardware-name guesses.
4. **Corpus library and evidence-first search.** Implement the existing
   `TranscriptIndex` port with a rebuildable local backend, initially DuckDB or an
   equivalently replaceable embedded analytical store. The user experience should be
   a search surface, not a database surface: plain text and exact phrase search,
   BM25-style lexical ranking, filters, facets, timestamped snippets, cross-recording
   results, saved searches/collections, tags and notes, and exportable result sets.
   Search results must preserve the evidence trail back to the source recording and
   exact transcript passage.
5. **Typed search grammar and query builder.** Keep SQL below the application boundary.
   Introduce a stable `SearchQuery`-style intermediate representation for text,
   phrase, speaker, language, date, recording, tag, duration, diarization, and sort
   constraints. CLI syntax, future query chips/dropdowns, and any later local natural-
   language parser should compile into that same typed query contract. DuckDB remains
   a replaceable derived-state adapter rather than user-facing homework.
6. **Word/timestamp alignment.** Add alignment as a separate enrichment capability so
   speaker projection and result jumping can become more precise without rewriting raw
   ASR or diarization evidence.
7. **Bounded failure recovery.** Add deterministic audio bisection/retry policy only
   if real long-recording failures justify it.
8. **Release/install and graphical UI.** Revisit these after the backend, lifecycle,
   model-management, and search contracts have survived representative dogfooding.
   The eventual interface should remain replaceable and thin.

## Corpus-search product principles

The database should be power, not homework. A researcher should be able to search for
`housing insecurity` and receive ranked passages across recordings with source,
speaker, language, and timestamp context without knowing that an embedded database is
involved.

The preferred progression is:

1. plain text and exact phrase search;
2. deterministic filters and facets;
3. saved searches and collections;
4. structured query chips or a visual query builder;
5. optional constrained local natural-language-to-`SearchQuery` translation; and
6. only later, optional local summarization over an explicitly selected evidence set.

Lexical retrieval is the default because it is fast, local, auditable, and useful for
research. BM25 or an equivalent lexical relevance model should rank actual matching
passages before semantic retrieval is considered.

EchoFlow should not begin with “chat with your transcripts.” A polished generated
answer can hide omissions, disagreement, and provenance. The primary retrieval result
should remain inspectable evidence: matching passages, source recordings, speakers,
and timestamps. Any future summary should sit above an explicit result set rather than
replace it.

Natural-language convenience must not require sending the corpus to a hosted LLM. A
small deterministic grammar can cover common requests first. A later optional local
model may translate a user sentence into the typed query representation, but it should
not need the transcript corpus itself and EchoFlow should show the interpreted query
back to the user before or alongside retrieval.

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
  acceptance lane. Its current Lightning 2.6.5 dependency is affected by
  CVE-2026-58659, so EchoFlow blocks diarization before pyannote import or model
  acquisition until a compatible patched Lightning release is available. The audit
  exception is limited to that advisory and exact locked version so dependency drift
  forces re-evaluation.
- Real Community-1 inference remains credential-gated and must clear the Lightning
  security hold plus representative-device qualification before EchoFlow makes
  operational or low-memory performance claims.
- Lifecycle state improves discoverability and recovery, but EchoFlow is still a
  synchronous local application rather than a background job daemon or distributed
  task system.
- Adaptive execution currently has a real CPU/int8 fallback and a CUDA-capable
  faster-whisper strategy path. CUDA is admitted only when physical topology,
  CTranslate2 runtime support, compute type, system-memory budget, and free device
  memory all agree. Other accelerator backends remain future adapters rather than
  implied support.
- Accelerator memory estimates and performance ranks are conservative heuristics
  pending representative-device qualification. EchoFlow does not yet claim that a
  detected GPU is faster on every workload.
- The transcript index/search backend is not implemented yet. Canonical transcript
  files remain authoritative and any future DuckDB index must be rebuildable derived
  state.
- Alternate ASR engines, distributed execution, semantic embeddings, polished
  installers, and a desktop GUI remain later work.

## Research candidates

These are directions to investigate, not committed release promises:

- finer-grained language attribution for intra-clause and romanized code switching;
- better overlap handling and optional user-assigned display labels for anonymous
  speaker references;
- alignment/word timestamps as a separate enrichment capability;
- original media timecode/capture-time provenance beyond source-relative seconds;
- local lexical and metadata search across transcript collections;
- corpus-statistical related terms before embedding-based relatedness;
- a constrained deterministic natural-language query grammar;
- an optional tiny local model whose only role is natural-language-to-typed-search
  translation, with the interpreted query visible to the user;
- optional local summarization only over explicitly selected/citable search evidence;
- optional semantic embeddings and hybrid lexical/semantic retrieval after lexical
  search is proven insufficient;
- multiple local ASR engine adapters when they provide a meaningful hardware,
  accuracy, packaging, or deployment advantage;
- additional accelerator backends when a real engine adapter can consume them and
  representative measurements justify the dependency/resource surface;
- multiple simultaneous inference workers only if measurements show that they beat a
  single model session plus bounded pipeline overlap without unacceptable memory or
  recovery cost.

The order can change when benchmarks, security review, implementation complexity, or
actual dogfooding contradicts an assumption. The stable direction is narrower:
**make sensitive local transcription boringly dependable, use local hardware well,
then make the evidence easy to find and use.**
