# Evidence-first corpus search

Status: first lexical library tranche implemented  
Last updated: August 17, 2026

## Product intent

EchoFlow makes a local transcript corpus searchable without exposing its storage engine
as the user experience. A researcher should not need to know that DuckDB or BM25 exists.
The database is infrastructure. The product is evidence retrieval.

The first implemented interaction is ordinary lexical search:

```text
echoflow library rebuild
echoflow library search "housing insecurity"
```

Results carry the evidence needed to inspect the hit rather than only returning text:
recording path when EchoFlow still knows it, canonical transcript path, source SHA-256,
segment identity, source-relative timestamps, speaker reference when available,
language evidence, passage text, and relevance score.

Canonical transcript JSON remains authoritative. The DuckDB database is private,
disposable derived state and can be rebuilt from canonical artifacts.

## Current architecture

The current path is:

```text
canonical transcript JSON
  -> validated searchable projection
  -> database-neutral TranscriptIndex port
  -> private DuckDB tables
  -> deterministic local BM25 ranking
  -> evidence-bearing TranscriptMatch
  -> CLI now / future UI later
```

The implementation has three primary layers:

1. **Corpus index**: `DuckDbTranscriptIndex` stores rebuildable document, segment, and
   lexical term statistics. It owns no authoritative transcript state.
2. **Library/search service**: `TranscriptLibraryService` discovers canonical artifacts,
   validates projections, performs transactional rebuilds, exposes search, and produces
   source-integrity evidence receipts.
3. **Presentation adapters**: `echoflow library` is the current adapter. A later GUI can
   consume the same service and query contract rather than implementing another search
   pipeline.

The DuckDB file lives under EchoFlow private state at
`STATE_DIR/library/transcripts.duckdb`. Removing that file must never destroy unique
user information.

## Offline BM25

The first ranking strategy is BM25-style lexical ranking over deterministic local token
statistics. EchoFlow stores per-segment token counts and term frequencies in ordinary
DuckDB tables and computes ranking from those statistics.

EchoFlow deliberately does **not** `INSTALL` or `LOAD` DuckDB's FTS extension in this
tranche. Extension installation can introduce an unexpected network dependency on a
fresh machine. Search must remain available offline once EchoFlow itself is installed.

This also makes ranking behavior explicit and replaceable. DuckDB is an adapter, not
the query API.

## Typed query boundary

The CLI, future UI, and storage backend exchange a stable application-level query
representation instead of handwritten SQL:

```text
SearchQuery
  text = "housing"
  phrase = false
  operator = any | all
  speaker_refs = ["speaker-02"]
  languages = ["en"]
  document_ids = ["job-123"]
  sort = relevance | timeline
  limit = 100
```

The DuckDB adapter compiles this representation using bounded application-owned SQL
structure and parameterized user values. Users never provide SQL fragments.

The initial query contract supports:

- ordinary lexical search;
- exact phrase requirements;
- ANY or ALL lexical-term semantics;
- speaker filters;
- language filters;
- transcript/document filters;
- relevance or source-timeline ordering; and
- bounded result limits.

Date/tag/duration/enrichment filters, facets, exclusions, saved searches, and
collections remain later extensions of the typed contract.

## Rebuild semantics

`echoflow library rebuild` discovers completed canonical artifacts from EchoFlow job
lifecycle metadata and the normal EchoFlow output directory. Additional canonical files
or directories may be supplied explicitly.

A rebuild validates the complete searchable projection before replacing index state.
The DuckDB replacement itself is transactional. If a known canonical transcript is
malformed, a duplicate canonical job identity is found, or the database replacement
fails, EchoFlow does not silently publish a partial new library.

Directory discovery may encounter unrelated JSON files. Those are skipped only when
they were found opportunistically during directory scanning. A lifecycle-known or
explicitly requested canonical artifact is strict and fails closed if it cannot be
validated.

## Source-integrity evidence

The library also exposes a human-readable evidence receipt:

```text
echoflow library show TRANSCRIPT_ID
```

The receipt separates several facts that should not be collapsed into one vague
"trusted" badge:

- **Original recording path**: where the input was located when EchoFlow recorded the
  lifecycle relationship, if that relationship is still available.
- **Recorded source SHA-256**: the digest stored in canonical transcript provenance when
  the recording was inspected for transcription.
- **Current source integrity**: whether the bytes currently at that source path hash to
  the same digest.
- **Canonical transcript path**: the user-visible authoritative transcript artifact.
- **Search-index custody**: explicitly described as private, rebuildable derived state.

Integrity states are explicit:

- `matches-recorded-source`
- `changed-since-transcription`
- `source-file-missing`
- `source-path-unavailable`

EchoFlow re-hashes the source only when integrity inspection is requested. It snapshots
file identity before and after hashing and fails closed if the file changes during the
verification pass.

This proves whether the current source bytes match the bytes EchoFlow fingerprinted for
the transcript. It is not a claim that software can prove the file was never touched by
any process at any point in history.

EchoFlow's transcription pipeline treats the supplied source as read-only input. Decode,
normalization, segmentation, enhancement, checkpoints, and search-index data are written
as separate derived material rather than overwriting the supplied recording.

## CLI surface

Current commands are:

```text
# Inspect the existing local library
echoflow library

# Rebuild from known/default canonical artifacts
echoflow library rebuild

# Include an additional canonical file or directory
echoflow library rebuild ~/Research/Transcripts

# Lexical BM25-style evidence search
echoflow library search "housing insecurity"

# Require the literal phrase
echoflow library search "housing insecurity" --phrase

# Require every lexical term and filter evidence
echoflow library search "rent increase" \
  --all-terms \
  --speaker speaker-02 \
  --language en

# Inspect source/canonical/index custody for one transcript
echoflow library show JOB_ID
```

Every command supports or preserves a deterministic machine-readable path through
`--json` where appropriate.

## Alignment boundary

Current search results are segment-level evidence. Their timestamps are the canonical
source-relative segment timestamps already produced by transcription. This makes the
result contract ready for later word/timestamp alignment without pretending word-level
precision exists today.

Alignment should remain a separate enrichment capability. When implemented, it may
make result highlighting, speaker projection, and jump-to-audio behavior more precise
without changing the authoritative raw ASR or diarization evidence.

## Natural language without giving away the corpus

Natural-language convenience must not require sending transcripts to a hosted model.
A later deterministic grammar may compile common sentences into `SearchQuery`. A small
optional local model may eventually translate a user sentence into the same typed
contract, but should not need the transcript corpus to perform that translation and
should show the interpreted query back to the user.

The probabilistic component must never silently control corpus retrieval.

## Why chat is not the default

"Chat with your transcripts" is not the primary research interface. A generated answer
can conceal omitted interviews, disagreement, minority evidence, and the distinction
between source language and model interpretation.

The default response to a question such as "what did people say about rent?" should
therefore be inspectable passages across recordings rather than a polished paragraph
with uncertain coverage. Optional local summarization may later operate over an
explicitly selected evidence set, with the underlying passages still visible.

## Later retrieval layers

High-value deterministic additions include facets, highlighted snippets, saved searches,
collections, user tags/notes, exportable result sets, and direct jump-to-timestamp UX.
Semantic retrieval remains optional and later.

If embeddings are introduced, embedding state is also disposable derived state and
must record model/revision, chunking, dimensions, normalization, metric, and index
schema. Exact similarity should precede ANN. HNSW or another approximate structure is
an execution strategy only when measured corpus scale demonstrates that exact search
misses an interactive latency target.

The stable rule remains:

> local evidence first, typed queries in the middle, replaceable database underneath,
> optional interpretation only above a visible result set.
