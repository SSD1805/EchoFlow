# EchoFlow roadmap

EchoFlow is a local-first, privacy-conscious, resource-aware audio transcription and
analysis application. It does not try to out-engine speech-recognition runtimes. Its
job is to make sensitive local transcription dependable, resumable, inspectable,
portable, and usable on ordinary computers.

## Current phase

Modern EchoFlow effectively restarted on August 2, 2026. The foundation now includes a
real local transcription vertical slice, deterministic media handling, segmentation,
private checkpoints, resource admission, durable lifecycle state, multilingual
semantics, anonymous speaker diarization, adaptive CPU/CUDA execution, explicit local
model custody, and optional provenance-bearing noise suppression.

The project is moving from **engine trust** to **product legibility and empirical
qualification**. Backend contracts should remain strict while ordinary users gain
clear progress, intentional recovery, predictable local model management, useful
preprocessing for difficult recordings, evidence-first corpus search, and eventually a
thin graphical shell.

Current foundation:

- real faster-whisper CPU/int8 transcription;
- deterministic FFprobe inspection and audio-stream selection;
- FFmpeg extraction/normalization to mono 16 kHz PCM16 WAV when needed;
- exact frame-based segmentation with one job-scoped ASR session;
- private durable checkpoints and validated resume;
- durable job lifecycle metadata plus discoverable status and cleanup;
- Rich interactive progress over the execution-observer seam;
- source-relative canonical timestamps with TXT/SRT/WebVTT derived exports;
- process-visible CPU/memory and storage admission;
- accelerator topology separated from engine capability negotiation;
- engine-neutral strategy admission across system RAM and dedicated/shared/unified
  accelerator memory;
- bounded one-segment CPU preparation overlap for accelerated inference while
  preserving ordered checkpoints and resumability;
- explicit faster-whisper model inventory, disk-admitted installation,
  provider/revision provenance, local revalidation, exact-revision removal, and
  mandatory immutable managed-revision pinning for ASR plans;
- local-only ASR execution with no transcription-time model download fallback;
- optional deterministic FFmpeg noise suppression before ASR, with explicit off/on
  selection, private derived audio, timeline-preservation validation, storage admission,
  checkpoint identity, and canonical transcript provenance;
- cross-platform private-storage enforcement;
- empirical benchmarking instrumentation;
- native-media, abrupt-process, clean-wheel, known-speech, and diarization evidence
  lanes;
- multilingual faster-whisper decoding plus conservative local language attribution;
- anonymous recording-scoped speaker diarization with conservative text projection;
  and
- a database-neutral `TranscriptIndex` port for a future rebuildable transcript
  library.

Canonical transcript JSON and checkpoint files remain authoritative execution evidence.
Lifecycle metadata describes job state. Managed model manifests describe local
execution dependencies. Enhanced audio is private derived processing material. Future
search/index databases remain rebuildable derived state.

## Pre-production contract policy

EchoFlow has not been released or meaningfully dogfooded yet. Internal durable
contracts therefore use one current canonical shape instead of accumulating migration
branches for hypothetical historical users.

That means current code deliberately removes obsolete pre-production compatibility
paths when a better invariant replaces them. In particular:

- ASR planning requires a verified managed model revision;
- transcription does not download faster-whisper models;
- an arbitrary configuration revision cannot bypass managed model custody;
- one current multilingual execution behavior replaces the earlier language-mode
  compatibility split; and
- one current job-plan/transcript/checkpoint contract represents optional capabilities
  with typed fields instead of encoding feature combinations into schema versions.

When EchoFlow has a real released/dogfooded compatibility boundary, schema migrations
should be introduced deliberately from that evidence rather than pre-built in advance.

## Product and interface direction

EchoFlow remains CLI-first while backend contracts mature:

- interactive terminals may use Rich progress, tables, stage names, and safe prompts;
- `--json` remains deterministic and presentation-noise free;
- long-running work has durable job IDs, progress, resume evidence, and explicit
  private-state cleanup;
- hardware selection happens through typed application services rather than CLI GPU
  switches;
- ASR model acquisition/removal happens through model-management actions, never hidden
  inside transcription;
- enhancement is explicit until evidence justifies automation; and
- a future desktop/web UI remains a presentation adapter over the same application
  services rather than a second pipeline implementation.

A polished installer and graphical UI remain deferred until the backend, model,
enhancement, and search contracts have survived representative dogfooding.

## Engineering qualification policy

Routine commit and pull-request gates should remain fast enough for iterative work:
deterministic tests, Hypothesis, branch coverage, Ruff, formatting, strict mypy,
Vulture, Radon, locked dependency/security audit, package builds, clean-wheel checks,
and cross-platform smoke tests.

Mutation testing serves a different purpose. Poodle is targeted development and
qualification for asking whether tests detect plausible bad decisions, not a routine
per-commit gate. For load-bearing logic, anticipate boundary, Boolean, threshold,
fallback, fail-open, ordering, cleanup, resume, provenance, and concurrency mutations
while designing ordinary tests. Run focused mutation scopes locally/sandboxed when
possible or through the manual workflow after deterministic tests are green. Inspect
survivors and rerun only affected scopes.

## Near-term direction

### 1. Adaptive execution, lifecycle, model, and enhancement dogfooding

Exercise interruption/resume, stale-process reconciliation, progress rendering,
accelerator re-admission, bounded prefetch cleanup, managed-model removal/reinstall,
and enhancement on long/noisy recordings. Keep published artifacts separate from
private execution state.

### 2. Representative-device qualification

Collect repeated benchmark evidence from:

- 8 GB Windows machines;
- 16 GB commodity machines;
- Apple Silicon;
- discrete-GPU laptops; and
- larger workstations.

Measure cold/warm model behavior, sustained real-time factor, thermal effects, CPU/RAM
pressure, accelerator memory/utilization where reliable counters exist, private disk
cost, and raw-ASR versus enhancement-plus-ASR accuracy/cost on representative noisy
recordings. Calibrate strategies and any future enhancement heuristic from measurements,
not hardware names or aesthetic audio-quality judgments.

### 3. Corpus library and evidence-first search

Implement the existing `TranscriptIndex` port with a rebuildable local backend, likely
DuckDB or an equivalently replaceable embedded analytical store.

The user experience is a search surface, not a database surface:

- plain text and exact phrase search;
- BM25-style lexical ranking;
- filters and facets;
- timestamped snippets;
- cross-recording results;
- saved searches/collections;
- tags and notes; and
- exportable result sets.

Results must preserve the evidence trail to the source recording and exact transcript
passage. Canonical transcript files remain truth; the index is disposable derived state.

### 4. Typed search grammar and query builder

Keep SQL below the application boundary. Introduce a stable `SearchQuery`-style IR for
text, phrase, speaker, language, date, recording, tag, duration, diarization, and sort
constraints. CLI syntax, future query chips/dropdowns, and any local natural-language
parser should compile to the same typed contract.

### 5. Word/timestamp alignment

Add alignment as a separate enrichment capability so speaker projection and result
jumping can become more precise without rewriting raw ASR or diarization evidence.

### 6. Bounded failure recovery

Add deterministic audio bisection/retry only if real long-recording failures justify
it. Do not front-load recovery machinery for failures that representative use has not
shown.

### 7. Release/install and graphical UI

Revisit these after the backend, lifecycle, model-management, enhancement, and search
contracts have survived representative dogfooding. The eventual interface should stay
thin and replaceable.

## Corpus-search product principles

The database should be power, not homework. A researcher should be able to search for
`housing insecurity` and receive ranked passages across recordings with source,
speaker, language, and timestamp context without knowing an embedded database exists.

Preferred progression:

1. plain text and exact phrase search;
2. deterministic filters and facets;
3. saved searches and collections;
4. structured query chips or a visual query builder;
5. optional constrained local natural-language-to-`SearchQuery` translation; and
6. only later, optional local summarization over an explicitly selected evidence set.

Lexical retrieval comes first because it is fast, local, auditable, and useful for
research. EchoFlow should not begin with “chat with your transcripts.” Generated
answers can hide omissions and provenance. Primary results should remain inspectable
passages, source recordings, speakers, and timestamps.

Natural-language convenience must not require sending the corpus to a hosted LLM. A
deterministic grammar can cover common queries first. A later optional local model may
translate a sentence into the typed query representation, but should not need the
transcript corpus and should show the interpreted query back to the user.

## Later semantic and hybrid retrieval

Semantic retrieval is a later layer over proven lexical search, not a replacement.
The intended architecture is:

```text
canonical transcripts
  -> deterministic chunks
  -> lexical index + optional local embeddings
  -> optional exact/vector index
  -> inspectable hybrid ranking
  -> deterministic metadata filters
  -> evidence-bearing results
```

Embedding/vector state remains disposable. Provenance should record embedding
engine/version, model/revision, dimensionality, chunking schema, normalization, metric,
and index schema so changes trigger explicit rebuilds.

Begin with exact vector similarity where corpus size permits. Approximate structures
such as HNSW are optional execution strategies only when measurement shows exact search
misses an interactive latency target. Apply the same resource-admission discipline as
transcription. An 8 GB laptop should not pay an HNSW tax because ANN happens to be
fashionable.

Simple inspectable fusion such as reciprocal-rank fusion should precede learned
reranking. Multilingual embeddings may later provide useful cross-language conceptual
retrieval, but remain optional local models with explicit custody and resource cost.

The product rule stays evidence-first: semantic retrieval returns passages and source
locations, not an uncited generated answer.

## Current capability boundaries

- Multilingual decoding can reconsider acoustic language within each durable work unit;
  conservative local language attribution may leave ambiguous text unlabeled.
- Clause/utterance-level code switching is supported better than arbitrary word-level
  or romanized Hinglish attribution.
- Timestamps are elapsed source-relative seconds from the selected audio origin.
  Arbitrary container PTS origins, SMPTE timecode, and wall-clock capture timestamps
  are not yet exposed as separate provenance.
- Anonymous diarization is optional local enrichment. It does not perform biometric
  identity or cross-recording linking. Ambiguous ASR segments may remain unlabeled
  without word alignment.
- Pyannote's locked Lightning 2.6.5 dependency is affected by CVE-2026-58659. EchoFlow
  blocks diarization before pyannote import or acquisition until a compatible patched
  Lightning release is available. The audit exception is exact-version/advisory scoped.
- Lifecycle state improves discoverability and recovery, but EchoFlow is a synchronous
  local application rather than a background daemon or distributed task system.
- Adaptive execution has a real CPU/int8 path and a CUDA-capable faster-whisper path.
  CUDA is admitted only when topology, runtime support, compute type, system RAM, and
  device memory agree. Other accelerators remain future adapters.
- Performance ranks and accelerator-memory estimates are conservative heuristics
  pending representative-device qualification.
- Faster-whisper model management owns private manifests over the Hugging Face cache.
  ASR plans require a locally revalidated managed revision, and execution is
  `local_files_only`; arbitrary cache entries and transcription-time downloads are not
  accepted.
- Model verification proves expected provider layout, repository/revision identity,
  and required non-empty files. It does not claim independent cryptographic
  attestation of upstream weights.
- Noise suppression is implemented as explicit optional local preprocessing. The
  source stays authoritative, enhanced audio is private derived state, ASR uses the
  derivative, and diarization still uses the unmodified canonical decode in v1.
- Enhancement v1 uses deterministic FFmpeg `afftdn`, not a neural model. Future
  model-backed enhancement must use model-management custody.
- There is no automatic enhancement selector yet; raw-ASR versus enhancement-plus-ASR
  evidence comes first.
- The transcript index/search backend is not implemented yet.
- Alternate ASR engines, distributed execution, semantic embeddings, polished
  installers, and a desktop GUI remain later work.

## Research candidates

These are investigations, not release promises:

- finer-grained language attribution for intra-clause and romanized switching;
- better overlap handling and user-assigned display labels for anonymous speakers;
- alignment/word timestamps;
- original-media timecode/capture-time provenance;
- evidence-driven automatic enhancement only after measured input conditions predict
  end-to-end ASR benefit reliably enough;
- later speech/source separation for overlapping speakers, kept distinct from ordinary
  denoising;
- local lexical/metadata search and corpus-statistical related terms;
- constrained deterministic natural-language query grammar;
- optional tiny local natural-language-to-typed-search translation;
- optional summarization only over selected/citable search evidence;
- optional semantic embeddings and hybrid lexical/semantic retrieval;
- exact vector similarity before ANN;
- resource-admitted HNSW only when measured scale/latency justifies it;
- explainable lexical/semantic fusion before learned reranking;
- optional multilingual embedding models;
- additional local ASR engines when they provide a concrete hardware, accuracy,
  packaging, or deployment advantage;
- additional accelerator backends when a real engine can consume them; and
- multiple simultaneous inference workers only if measurements beat a single session
  plus bounded pipeline overlap without unacceptable memory/recovery cost.

The order may change when benchmarks, security review, complexity, or dogfooding
contradicts an assumption. The stable direction is narrower:

**make sensitive local transcription boringly dependable, use local hardware well,
then make the evidence easy to find and use.**
