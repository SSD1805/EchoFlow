# Library lifecycle, custody, and refresh

EchoFlow's library contains several kinds of local data that deliberately have different
retention and recovery rules. A transcript is not a search index, a note is not a cache,
and an operational log is not evidence.

The central rule is:

> **Canonical transcript JSON is durable user-visible evidence. Library indexes are
> disposable views over that evidence.**

This distinction explains why EchoFlow can safely rescan or rebuild a library without
re-transcribing the recording.

## Where canonical transcripts live

By default, EchoFlow publishes user-visible artifacts under the operating system's normal
Downloads directory:

```text
Downloads/
└── EchoFlow/
    ├── interview.json
    ├── interview.txt
    ├── interview.srt
    └── interview.vtt
```

The exact platform path is resolved with `platformdirs`; EchoFlow does not assume a
hard-coded Unix or Windows home layout.

Canonical JSON is the authoritative transcript artifact. TXT, SRT, and VTT are derived
publication formats and may be regenerated from canonical JSON without rerunning ASR.

A user may choose another output directory for a transcription:

```bash
echoflow transcribe recording.m4a --output-dir /path/to/research/project
```

The configured default is `ECHOFLOW_OUTPUT_DIR`. An explicitly selected EchoFlow dotenv
configuration file can therefore make another location the normal destination across
commands:

```text
ECHOFLOW_OUTPUT_DIR=/path/to/research/project
```

```bash
echoflow --config /path/to/echoflow.env transcribe recording.m4a
```

`echoflow init --output-dir ...` initializes a selected public output directory for that
invocation; it does not silently rewrite a persistent configuration file.

Public transcript output is intentionally kept separate from EchoFlow's private state and
cache directories. `WorkspacePaths` rejects layouts where the public output tree overlaps
private state/cache.

Artifact allocation is collision-safe. EchoFlow does not silently overwrite an existing
canonical transcript with the same friendly filename.

## What `library rebuild` actually means

A library rebuild is a **discovery and indexing operation**.

It does not:

- decode audio;
- run faster-whisper;
- perform diarization;
- rewrite canonical JSON; or
- replace the original recording.

It reads existing canonical transcript JSON and rebuilds the private analytical structures
used for search.

Conceptually:

```text
original recording
       |
       | one transcription run
       v
canonical transcript JSON       durable evidence
       |
       | scan / project
       v
DuckDB lexical index             disposable
DuckDB semantic index            disposable
DuckDB research projection       disposable
```

The transcript library discovers canonical JSON from three sources:

1. completed EchoFlow lifecycle records that point to an existing canonical artifact;
2. the configured EchoFlow output directory; and
3. file or directory paths explicitly supplied to `echoflow library rebuild`.

An explicit file is treated strictly: if it is claimed as a canonical transcript but
cannot be loaded, rebuild fails rather than pretending it was harmless noise. Directory
scans may skip unrelated JSON files that are not EchoFlow canonical transcripts.

## Why would a user ever rescan the transcripts?

Not because transcripts are supposed to disappear. Rescanning exists because **the corpus
and its derived indexes can drift apart**.

Normal reasons include:

### A new transcript exists

A user transcribes another interview, imports an older EchoFlow canonical JSON, or copies a
canonical transcript into a research directory. The evidence exists on disk, but an older
index cannot know about it until the library is refreshed.

### A transcript generation changed

A recording may be deliberately retranscribed after changing the engine/model,
preprocessing policy, language handling, or another transcription contract. The resulting
canonical bytes have a different SHA-256 and represent a different evidence generation.

The lexical index should then reflect the new canonical generation. Existing semantic
vectors are not silently trusted: EchoFlow compares corpus fingerprints and refuses stale
semantic search until embeddings are rebuilt for the current corpus.

### A transcript was removed or moved

A rebuild re-derives the indexed corpus from what EchoFlow can currently discover. That
lets a removed transcript disappear from a disposable index without requiring the index
to become a second authority about whether the evidence still exists.

Moving a canonical transcript outside the configured output directory may require adding
its new directory explicitly when rebuilding unless EchoFlow already knows the artifact
through durable job lifecycle state.

### A rebuildable database was deleted, damaged, or became incompatible

Lexical, semantic, and research DuckDB files are not unique user knowledge. If one is
missing or cannot be trusted, EchoFlow can rebuild it from authoritative evidence/state
instead of attempting heroic in-place repair.

This is an intentional recovery feature. The rebuildability of the index is what makes it
safe to treat the index as disposable.

### Search/index implementation changed

A later EchoFlow release may change projection schema, tokenization, chunk mapping, or
another derived representation. Rebuilding lets the new release regenerate those views
from canonical evidence rather than migrating every historical cache representation.

## Full rebuild versus incremental refresh

Today, `echoflow library rebuild` is the explicit whole-corpus repair/discovery path.

That is correct but eventually inefficient for a large library when only one transcript
changed. The planned incremental refresh contract uses stable transcript-generation
identity such as:

```text
(document_id, canonical_sha256)
```

Then normal refresh can behave as:

```text
new generation       -> upsert
changed generation   -> replace/upsert
removed transcript   -> remove
unchanged transcript -> skip
```

A full rebuild remains valuable as an explicit recovery operation even after incremental
refresh exists.

## Saved searches do not save result snapshots

Saved searches are durable **questions**, not frozen answers.

PR #67 stores typed search intent in authoritative SQLite:

- transcript query text;
- phrase / ANY / ALL semantics;
- speaker, language, and transcript constraints;
- sort and result limit;
- lexical / semantic / hybrid retrieval mode;
- research tag/collection/note constraints; and
- canonical context width.

It explicitly refuses to persist a derived `evidence_scope`.

When a saved search runs later, `ResearchWorkspaceService` resolves the current research
relationships and current canonical evidence again. If qualifying evidence has been added
since the search was saved, the saved query can find it.

This is why saved searches survive library growth without becoming stale snapshots.

## Frequent and recent navigation is disposable

Frequent/recent tags and collections are computed from current note relationships and note
update timestamps.

EchoFlow does **not** store authoritative `usage_count` or `last_used_at` counters on tag
and collection records. Those values are views.

If the derived navigation calculation changes tomorrow, no user-authored state needs to
be migrated or repaired.

## Retention classes

| Class | Examples | Retention rule |
|---|---|---|
| Authoritative source evidence | original recording | user-owned; EchoFlow treats input read-only |
| Authoritative transcript evidence | canonical JSON | durable user-visible artifact; never an index cache |
| Authoritative human work | notes, tags, collections, speaker labels, saved searches | durable; losing it loses user work |
| Derived publications | TXT, SRT, VTT | deletable and regenerable from canonical JSON |
| Rebuildable analytical state | lexical DuckDB, semantic DuckDB, research DuckDB | may be deleted/rebuilt |
| Private execution state | checkpoints, normalized/enhanced intermediates, work segments | lifecycle-managed for execution/resume, not evidence authority |
| Operational logs | structured process log stream | diagnostic only; not transcript evidence |

EchoFlow's structured application logger currently writes to the process stream (`stderr`)
rather than creating a durable transcript-log archive. Routine local filesystem paths are
redacted unless path disclosure is explicitly enabled.

That logging policy is independent of canonical transcript retention.

## Safe deletion is a separate product operation

EchoFlow does not yet provide one unified safe-delete command for transcript evidence and
all dependent state. That should not be faked by teaching users to manually delete random
SQLite/DuckDB rows.

A future deletion surface needs to distinguish at least:

- **delete a derived index/cache**: safe to rebuild; no unique work should disappear;
- **delete a publication export**: safe to regenerate from canonical JSON;
- **delete private execution/checkpoint state**: may remove resume capability but not
  canonical evidence;
- **delete a saved search/note/tag relationship**: explicit deletion of human-authored
  state;
- **remove a transcript from the active library**: an indexing/membership decision, not
  necessarily deletion of canonical evidence; and
- **delete canonical transcript evidence**: destructive user-data deletion that must make
  dependent notes/anchors and projections explicit before committing.

Secure deletion of arbitrary files on modern SSDs, copy-on-write filesystems, snapshots,
backups, sync clients, and wear-levelled storage cannot be honestly guaranteed by simply
overwriting bytes. EchoFlow should therefore use precise language about deletion and
retention rather than claiming cryptographic shredding it cannot prove.

The safe-delete design should preserve one core invariant: **a command that means “remove
this from search” must never accidentally mean “erase my only canonical transcript and my
annotations.”**

## Test contract for this lifecycle

PR #67 exercises the following invariants at multiple layers:

- saved-search typed intent round-trips through SQLite;
- saved-search names are case-insensitive unique identities without accidental overwrite;
- derived evidence scopes cannot be persisted as saved-search state;
- replay re-resolves current research relationships rather than freezing old segment IDs;
- frequent/recent navigation is derived from current relationships;
- authoritative tag/collection rows do not grow usage/recency counters;
- unsupported/corrupt durable metadata fails closed;
- CLI flags compile to the same typed `SearchQuery` and research-filter contracts;
- CLI save/list/show/run/delete and navigation surfaces preserve JSON/human behavior; and
- CLI public errors remain useful while unexpected internal details are masked.

The normal repository Quality workflow then runs Ruff, formatting, strict mypy, Vulture,
Radon, branch-coverage pytest, distribution build/install verification, and full tests on
Windows and macOS.

## Load-bearing invariants

1. Canonical JSON is evidence, not cache.
2. Rescanning/rebuilding indexes never means re-transcribing audio.
3. Saved searches persist typed intent, never a frozen derived evidence scope.
4. Frequent/recent navigation remains derived rather than authoritative counters.
5. Deleting a rebuildable database must not delete canonical evidence or human-authored
   research state.
6. Output directories remain user-visible and separate from private state/cache.
7. Destructive canonical-evidence deletion must be explicit and dependency-aware when that
   capability is implemented.
