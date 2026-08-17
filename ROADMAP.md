# EchoFlow roadmap

EchoFlow is a local-first, privacy-conscious, resource-aware audio transcription and
analysis application. It does not try to out-engine speech-recognition runtimes. Its job
is to make sensitive local transcription dependable, resumable, inspectable, portable,
and usable on ordinary computers.

## Current phase

Modern EchoFlow effectively restarted on August 2, 2026. The foundation now includes a
real local transcription vertical slice, deterministic media handling, segmentation,
private checkpoints, resource admission, durable lifecycle state, multilingual
semantics, anonymous speaker diarization, adaptive CPU/CUDA execution, explicit local
ASR model custody, optional provenance-bearing noise suppression, and an evidence-first
transcript library with lexical, semantic, and hybrid retrieval contracts.

The project is moving from **engine trust** to **product legibility and empirical
qualification**. Backend contracts should remain strict while ordinary users gain clear
progress, intentional recovery, predictable local model management, useful
preprocessing for difficult recordings, evidence-first corpus search, and eventually a
thin graphical shell.

Current foundation:

- real faster-whisper CPU/int8 transcription;
- deterministic FFprobe inspection and audio-stream selection;
- FFmpeg extraction/normalization to mono 16 kHz PCM16 WAV where needed;
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
  selection, private derived audio, timeline-preservation validation, storage
  admission, checkpoint identity, and canonical transcript provenance;
- cross-platform private-storage enforcement;
- empirical benchmarking instrumentation;
- native-media, abrupt-process, clean-wheel, known-speech, and diarization evidence
  lanes;
- multilingual faster-whisper decoding plus conservative local language attribution;
- anonymous recording-scoped speaker diarization with conservative text projection;
- a database-neutral `TranscriptIndex` lexical port with a private rebuildable DuckDB
  backend;
- deterministic offline BM25-style lexical ranking with phrase, ANY/ALL term, speaker,
  language, transcript, and sort constraints;
- canonical transcript SHA-256 projection in addition to source-media SHA-256;
- deterministic `search-chunk-v1` semantic windows anchored to exact canonical segment
  IDs and timestamps;
- an `EmbeddingProvider` contract with separate query/passages semantics;
- a strict-local `SentenceTransformersE5Provider` targeting
  `intfloat/multilingual-e5-small`;
- explicit semantic profile provenance: immutable revision, dimensions,
  normalization, pooling, distance metric, query/passage transforms, chunk profile,
  and embedding schema;
- a separate private `DuckDbSemanticIndex` storing numeric `FLOAT[]` vectors;
- exact local dense similarity with hard metadata constraints before top-K ranking;
- hybrid BM25+dense retrieval with inspectable reciprocal rank fusion;
- a unified `SearchResponse` carrying evidence coordinates and lexical, semantic, and
  fused ranks;
- a semantic corpus fingerprint over exact canonical JSON digests so stale vectors
  fail closed; and
- human-readable transcript evidence receipts exposing canonical/source locations,
  source/canonical SHA-256 evidence, and current source-integrity status.

Canonical transcript JSON and checkpoint files remain authoritative execution evidence.
Lifecycle metadata describes job state. Managed ASR model manifests describe local
execution dependencies. Enhanced audio is private derived processing material. Lexical
and semantic search databases are rebuildable derived state and contain no unique
user-authored information.

The current semantic adapter is implemented without adding an unresolved package to the
locked dependency graph. A compatible Sentence Transformers runtime and immutable local
multilingual-E5 snapshot are therefore an optional environment capability for this
tranche. Locking, auditing, and integrating semantic model acquisition into EchoFlow's
managed-model custody are separate qualification work.

## Pre-production contract policy

EchoFlow has not been released or meaningfully dogfooded yet. Internal durable
contracts therefore use one current canonical shape instead of accumulating migration
branches for hypothetical historical users.

Current code deliberately removes obsolete pre-production compatibility paths when a
better invariant replaces them. In particular:

- ASR planning requires a verified managed model revision;
- transcription does not download faster-whisper models;
- an arbitrary configuration revision cannot bypass managed ASR model custody;
- one current multilingual execution behavior replaces the earlier language-mode
  compatibility split;
- one current job-plan/transcript/checkpoint contract represents optional capabilities
  with typed fields instead of feature-version schema proliferation; and
- semantic generations bind to exact canonical artifact hashes rather than assuming a
  source-media hash proves the search projection is current.

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
- enhancement is explicit until evidence justifies automation;
- corpus search compiles through one typed `SearchQuery` contract rather than exposing
  SQL or DuckDB;
- lexical/semantic/hybrid results use one evidence-bearing response shape; and
- a future desktop/web UI remains a presentation adapter over the same services rather
  than a second pipeline implementation.

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
fallback, fail-open, ordering, cleanup, resume, provenance, stale-state, filtering, and
concurrency mutations while designing ordinary tests.

## Near-term direction

### 1. Dogfood the complete local workflow

Exercise interruption/resume, stale-process reconciliation, progress rendering,
accelerator re-admission, bounded prefetch cleanup, managed ASR model
removal/reinstall, enhancement on long/noisy recordings, transcript-library rebuilds,
source-integrity receipts, and lexical/semantic/hybrid search over real multi-recording
corpora.

Particular retrieval questions:

- Are 220-word target / 300-word maximum chunks good enough across interviews,
  lectures, meetings, and oral histories?
- Does exact vector scan remain interactive at realistic personal/research corpus
  sizes?
- Does RRF improve conceptual recall without burying exact identifiers, names, and
  acronyms that BM25 handles well?
- Do speaker/language/document constraints behave as users expect on mixed chunks?
- Which retrieval metadata actually belongs in the normal interface versus an
  inspector/details surface?

### 2. Qualify the semantic dependency and model custody

Resolve and audit a locked optional semantic dependency set before advertising semantic
search as a normal source install.

The target direction is:

- one explicit semantic extra;
- no silent model download during search;
- managed acquisition of the exact multilingual-E5 snapshot;
- immutable resolved revision in model custody;
- private cache placement;
- disk/resource admission;
- offline query execution after installation; and
- clean-wheel/platform qualification.

Do not bypass `uv.lock` consistency merely to make the optional capability look more
finished.

### 3. Representative-device qualification

Collect repeated benchmark evidence from:

- 8 GB Windows machines;
- 16 GB commodity machines;
- Apple Silicon;
- discrete-GPU laptops; and
- larger workstations.

Measure cold/warm model behavior, sustained real-time factor, thermal effects, CPU/RAM
pressure, accelerator memory/utilization where reliable counters exist, private disk
cost, raw-ASR versus enhancement-plus-ASR accuracy/cost, embedding build cost, and
semantic-query latency.

Calibrate strategy and semantic defaults from measurements, not hardware names.

### 4. Corpus library retrieval UX

The retrieval engine now supports lexical, exact dense, and hybrid ranking. The next
library work should be driven by real search use and may add:

- richer snippets and highlights;
- result-context expansion;
- facets;
- exportable result sets;
- direct jump-to-audio;
- saved searches and collections; and
- tags, notes, and annotations.

The ownership boundary is non-negotiable: user-authored state may not share the deletion
semantics of the rebuildable index. Notes/annotations must anchor to durable canonical
segment coordinates, not only to disposable chunk IDs.

### 5. Typed search grammar and query builder

The current `SearchQuery` supports text, phrase, ANY/ALL lexical semantics, speaker,
language, transcript/document, sorting, and bounded limits.

Extend only as product evidence requires date, tag, duration, enrichment, exclusion,
facet, or collection constraints. CLI syntax, future query chips/dropdowns, and any
local natural-language parser should compile to the same typed contract.

### 6. Word/timestamp alignment

Add alignment as a separate enrichment capability so speaker projection,
search-result highlighting, jump-to-audio behavior, and future durable annotations can
become more precise without rewriting raw ASR or diarization evidence.

### 7. Bounded failure recovery

Add deterministic audio bisection/retry only if real long-recording failures justify
it. Do not front-load recovery machinery for failures representative use has not shown.

### 8. Release/install and graphical UI

Revisit after backend, lifecycle, model-management, enhancement, and retrieval contracts
have survived representative dogfooding. The eventual interface should stay thin and
replaceable.

## Corpus-search product principles

The database should be power, not homework. A researcher should be able to search for
`housing insecurity` and receive ranked passages across recordings with source,
speaker, language, timestamp, and canonical-evidence context without knowing DuckDB
exists.

Current retrieval ladder:

1. deterministic BM25 lexical retrieval;
2. deterministic metadata constraints;
3. exact local dense retrieval over segment-anchored chunks;
4. inspectable RRF hybrid fusion.

Likely UX progression:

1. better snippets/highlighting and context navigation;
2. richer deterministic filters/facets;
3. saved searches and collections in durable user state;
4. structured query chips/visual builder;
5. optional constrained local natural-language-to-`SearchQuery` translation; and
6. only later, optional local summarization over an explicitly selected evidence set.

EchoFlow should not begin with “chat with your transcripts.” Generated answers can hide
omissions and provenance. Primary results remain inspectable passages, source
recordings, speakers, timestamps, and canonical transcript coordinates.

Natural-language convenience must not require sending the corpus to a hosted LLM. A
deterministic grammar can cover common queries first. A later optional local model may
translate a sentence into the typed query representation, but should not need the
transcript corpus and should show the interpreted query back to the user.

## Semantic and hybrid retrieval policy

Semantic retrieval is an optional layer over proven lexical search, not a replacement.

Current architecture:

```text
canonical transcripts
  -> deterministic segment-anchored chunks
  -> BM25 + optional local multilingual-E5 embeddings
  -> exact local dense scan
  -> hard metadata constraints before top-K
  -> optional RRF hybrid ranking
  -> evidence-bearing SearchResponse
```

Embedding state is disposable. One generation has one coherent embedding space.
EchoFlow does not dynamically mix embedding models by document language.

Exact similarity remains the reference execution strategy. Approximate structures such
as HNSW are optional only when measured corpus scale shows exact search misses an
interactive latency target. An 8 GB laptop should not pay an ANN tax because ANN is
fashionable.

RRF precedes learned reranking because it is simple, local, inspectable, and avoids
score-normalization fiction. A cross-encoder may later rerank a small explicit candidate
set if representative evaluation demonstrates worthwhile gains at acceptable resource
cost.

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
  identity or cross-recording linking.
- Pyannote's locked Lightning dependency is security-gated as documented in
  `SECURITY.md`.
- Lifecycle state improves discoverability and recovery, but EchoFlow is a synchronous
  local application rather than a background daemon or distributed task system.
- Adaptive execution has a real CPU/int8 path and a CUDA-capable faster-whisper path.
  Other accelerators remain future adapters.
- Performance ranks and accelerator-memory estimates are conservative heuristics
  pending representative-device qualification.
- ASR model management owns verified private manifests and immutable revisions.
- Noise suppression is explicit optional local preprocessing and does not replace
  source authority.
- Semantic retrieval code exists, but the Sentence Transformers runtime/model
  acquisition is not yet a qualified locked EchoFlow extra.
- Exact dense search exists; ANN/HNSW and learned reranking do not.
- Saved searches, collections, tags, notes, user annotations, word-level alignment,
  generated corpus answers, polished installers, and a desktop GUI remain later work.
- Source-integrity inspection proves whether current source bytes match the digest
  captured for transcription. It cannot prove no external process ever changed and
  restored the file.

## Research candidates

These are investigations, not release promises:

- finer-grained language attribution for intra-clause and romanized switching;
- better overlap handling and user-assigned display labels for anonymous speakers;
- alignment/word timestamps;
- original-media timecode/capture-time provenance;
- evidence-driven automatic enhancement after measured benefit;
- later speech/source separation for overlapping speakers;
- corpus-statistical related terms and richer facets;
- constrained deterministic natural-language query grammar;
- optional tiny local natural-language-to-typed-search translation;
- optional summarization only over selected/citable evidence;
- alternative multilingual embedding models;
- character n-gram/fuzzy retrieval for ASR names, acronyms, and misspellings;
- a small cross-encoder reranker only after measured benefit;
- resource-admitted HNSW only when exact-search latency justifies it;
- additional local ASR engines when they provide a concrete advantage;
- additional accelerator backends when a real engine can consume them; and
- multiple simultaneous inference workers only if measurements beat the current
  bounded-overlap design without unacceptable memory/recovery cost.

The order may change when benchmarks, security review, complexity, or dogfooding
contradicts an assumption. The stable direction is narrower:

**make sensitive local transcription boringly dependable, then make its evidence easy
to find without giving the corpus away.**
