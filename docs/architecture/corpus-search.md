# Evidence-first corpus search

Status: planned capability, not implemented  
Last updated: August 17, 2026

## Product intent

EchoFlow should make a local transcript corpus searchable without exposing its storage
engine as the user experience. A researcher should not need to know that DuckDB,
FTS/BM25, or another embedded index exists.

The default interaction should be ordinary search:

```text
housing insecurity
```

EchoFlow should return matching passages with enough provenance to inspect and cite
them: recording, timestamp, speaker reference when available, language evidence,
matching snippet, and any relevant tags or metadata. A result should be able to jump
back to the transcript and eventually to the corresponding audio position.

The database is infrastructure. The product is evidence retrieval.

## Retrieval order

The first retrieval primitive should be lexical search, using BM25 or an equivalent
local relevance model. For research, journalism, and archival work, matching the words
people actually used is often a strength rather than a limitation.

The initial search surface should progressively support:

1. plain text search;
2. exact phrases;
3. AND/OR and exclusions where useful;
4. fielded filters for recording, speaker, language, date, tags, duration, and
   enrichment state;
5. fuzzy or prefix behavior only where its semantics can be made explicit;
6. facets and result counts;
7. saved searches and user collections; and
8. export of the result set to portable formats such as CSV, JSON, or Markdown.

Semantic retrieval and embeddings are later optional capabilities, not prerequisites
for useful corpus search.

## Typed query boundary

The UI, CLI, and storage backend should not exchange handwritten SQL. They should
exchange a stable application-level query representation, conceptually:

```text
SearchQuery
  text = "housing"
  phrase = false
  speaker_refs = ["speaker-02"]
  languages = ["en"]
  date_range = ...
  tags = ...
  sort = relevance
```

A search adapter compiles this representation into the embedded backend's query
language. This keeps DuckDB or any later index replaceable and lets several interfaces
share exactly the same search semantics.

A future visual query builder can therefore express:

```text
text contains housing
AND speaker is speaker-02
AND recording date is after 2025-01-01
```

without ever presenting SQL to the user.

## Three layers

The intended architecture has three primary layers:

1. **Corpus index**: rebuildable derived state containing transcript passages and
   searchable metadata. DuckDB with lexical/FTS support is the leading initial
   candidate, not an authoritative artifact store.
2. **Search service**: owns typed query semantics, ranking behavior, filters, facets,
   result snippets, and provenance back to canonical transcript evidence.
3. **Presentation adapters**: CLI now and a later desktop/web UI. Search boxes,
   checkboxes, query chips, saved searches, and result navigation live here rather
   than in the storage adapter.

Canonical transcript JSON remains authoritative. The complete index must be
rebuildable from user-owned canonical artifacts plus separately owned user annotations.

## Natural language without giving away the corpus

Natural-language convenience must not require sending transcripts to a hosted model.
Two local-first paths are acceptable.

The first is a constrained deterministic parser for common requests such as:

- “interviews with Alice from March”;
- “mentions of housing after 2024”; or
- “French passages spoken by speaker 2”.

The second, later option is a small local model whose only task is user sentence to
typed `SearchQuery`. It should not need the transcript corpus to translate the query.
The deterministic search service still executes retrieval.

When probabilistic query translation is used, EchoFlow should display the interpreted
query back to the user, for example:

```text
Searching for: rent increases
Across: all recordings
Sort: relevance
```

The probabilistic component must not silently control corpus retrieval.

## Why chat is not the default

“Chat with your transcripts” is not the primary research interface. A generated answer
can conceal omitted interviews, disagreement, minority evidence, and the distinction
between source language and model interpretation.

The default response to a question such as “what did people say about rent?” should
therefore be inspectable retrieval evidence, such as 37 matching passages across 12
recordings, rather than a polished paragraph with uncertain coverage.

Optional local summarization may later operate over an explicitly selected result set.
The evidence must remain visible underneath the interpretation.

## Useful non-generative UX

A modern search experience does not require an LLM. High-value local features include:

- search-as-you-type;
- highlighted snippets;
- facets by recording, speaker, language, date, and tags;
- timeline clustering within long recordings;
- cross-recording retrieval;
- saved collections for research themes or chapters;
- user tags and notes attached to evidence;
- direct jump-to-timestamp behavior; and
- corpus-statistical related terms before embedding-based similarity.

These capabilities are deterministic, fast, testable, and compatible with EchoFlow's
privacy model.

## Privacy and custody

Search is local by default. Building or querying the corpus index must not upload
recordings, transcripts, snippets, tags, or queries to hosted services.

The index is derived state, not transcript custody. Deleting or rebuilding an index
must not delete canonical transcripts. User-created notes, tags, saved searches, and
collections are separate owned state and need an explicit backup/export story before
they can be treated as disposable.

The stable rule is:

> local evidence first, typed queries in the middle, replaceable database underneath,
> optional interpretation only above a visible result set.
