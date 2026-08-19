# Library lifecycle, custody, refresh, and deletion

EchoFlow's library contains several kinds of local data with deliberately different
retention and recovery rules. A transcript is not a search index, a note is not a cache,
and an operational log is not evidence.

The central rule is:

> **Canonical transcript JSON is durable user-visible evidence. Library indexes are
> disposable views over that evidence.**

A second rule now governs destructive operations:

> **Removing evidence from search must never silently erase canonical evidence,
> user-authored research knowledge, or an original recording.**

These distinctions explain why EchoFlow can rescan or rebuild a library without
re-transcribing a recording, and why deletion is exposed as a typed plan instead of a
generic filesystem command.

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

EchoFlow stores typed search intent in authoritative SQLite:

- transcript query text;
- phrase / ANY / ALL semantics;
- speaker, language, and transcript constraints;
- sort and result limit;
- lexical / semantic / hybrid retrieval mode;
- research tag/collection/note constraints; and
- canonical context width.

Saved searches explicitly refuse a derived `evidence_scope`.

When a saved search runs later, `ResearchWorkspaceService` resolves current research
relationships and current canonical evidence again. If qualifying evidence has been added
since the search was saved, the saved query can find it.

If a transcript is later removed or deleted, a saved search constrained to that
`document_id` is reported as affected by the deletion plan but is not itself deleted.

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
| Authoritative source evidence | original recording | user-owned; EchoFlow treats input read-only except an explicit provenance-checked source-deletion request |
| Authoritative transcript evidence | canonical JSON | durable user-visible artifact; explicit deletion only |
| Authoritative human work | notes, tags, collections, speaker labels, saved searches | durable; explicit deletion only |
| Derived publications | TXT, SRT, VTT | regenerable; may be deleted explicitly |
| Rebuildable analytical state | lexical DuckDB, semantic DuckDB, research DuckDB | may be removed/rebuilt |
| Private execution state | checkpoints, normalized/enhanced intermediates, work segments | lifecycle-managed; age-based retention is allowed only through a reviewed plan |
| Lifecycle metadata | compact job manifests | retained by execution-workspace cleanup because they can preserve discovery pointers |
| Operational logs | structured process log stream | diagnostic only; not transcript evidence |

EchoFlow's structured application logger currently writes to the process stream (`stderr`)
rather than creating a durable transcript-log archive. Routine local filesystem paths are
redacted unless path disclosure is explicitly enabled.

## Safe deletion is now a typed product operation

The detailed design is in
[`safe-deletion-retention.md`](safe-deletion-retention.md).

The user-facing surface is plan-first:

```bash
echoflow library delete TRANSCRIPT_ID --scope library-view
```

Without `--confirm`, no mutation occurs. The plan shows exact actions, affected durable
objects, preserved notes, and a token bound to the current canonical generation and action
set.

Applying the plan requires the same request plus that exact token:

```bash
echoflow library delete TRANSCRIPT_ID \
  --scope library-view \
  --confirm 'delete:...'
```

The typed scopes are:

- `library-view`;
- `derived-artifacts`;
- `execution-state`;
- `canonical-transcript`;
- `research-notes`;
- `saved-searches`; and
- `source-recording`.

`canonical-transcript` automatically expands to removal from the active library,
regenerable derived publications, and private execution state. It does **not** imply `research-notes`, `saved-searches`, or `source-recording`.

That means deleting canonical JSON without the research scope leaves notes in authoritative
SQLite. Their exact `(document_id, canonical_sha256, segment_id)` anchors remain, but the
evidence becomes unavailable/current=false once that generation is no longer in the active
library.

Source deletion is even narrower: it requires both the explicit `source-recording` scope
and `--allow-source`, and EchoFlow refuses if current source bytes no longer match the
recorded source provenance.

## Why the semantic index is cleared when one transcript leaves the library

The current semantic index is bound to a corpus fingerprint and exposes whole-corpus
rebuild/clear semantics.

Removing one lexical document while retaining semantic vectors from the old corpus would
leave derived state whose fingerprint still claims deleted evidence. EchoFlow therefore
clears the semantic corpus when a transcript is removed from the active library.

This is conservative and rebuildable. A future incremental semantic index may support
generation-scoped removal while keeping the same custody service contract.

## Retention controls are intentionally narrower than deletion

Age-based retention currently applies only to private job workspaces:

```bash
echoflow library retention --execution-days 30
```

The command is also a dry run until the matching plan token is supplied with `--confirm`.

Default policy:

```text
execution_days = 30
include_incomplete = false
```

Completed private workspaces older than the cutoff are eligible. Failed/interrupted
workspaces require `--include-incomplete` because deleting them removes resume capability.
Running jobs are never eligible.

Retention cleanup preserves:

- canonical JSON;
- derived public exports;
- source recordings;
- notes/tags/collections;
- speaker labels;
- saved searches; and
- lightweight lifecycle manifests.

Preserving lifecycle manifests matters for canonical transcripts written to custom output
directories. A manifest can remain a discovery pointer even after heavyweight
checkpoints/intermediates are gone.

## Deletion ordering and partial-failure semantics

SQLite, DuckDB, public files, private workspaces, and arbitrary source media cannot
participate in one cross-filesystem ACID transaction.

EchoFlow therefore validates destructive inputs first and then orders mutations from most
recoverable to most unique:

1. rebuildable lexical/semantic state;
2. regenerable publication exports;
3. private execution workspace;
4. canonical transcript evidence;
5. explicitly requested source media;
6. explicitly requested document-scoped saved searches; and
7. explicitly requested research notes.

Immediately before a canonical deletion, EchoFlow re-hashes the canonical JSON and refuses
the operation if those bytes no longer match the indexed `canonical_sha256`.

The confirmation token is not an authentication secret. It is a change-detection primitive
that binds approval to one exact mutation set.

## Secure erasure is not claimed

Deleting a path through the operating system does not prove that bytes are unrecoverable
from SSD wear leveling, copy-on-write history, snapshots, backups, sync/version history,
controller caches, or forensic tooling.

EchoFlow therefore reports deletion precisely and sets
`secure_erasure_guaranteed = false` in machine-readable deletion output.

## Test contract

The merged saved-search implementation now has additional regression coverage for:

- invalid durable intent/value objects;
- list bounds and missing mutation targets;
- invalid identifiers/names/descriptions;
- corrupt persisted JSON and enum state;
- closed navigation dispatch;
- human list/show/save/run/delete rendering;
- every derived navigation group; and
- missing run/delete behavior without mutation.

The safe-deletion/retention tranche adds tests for:

- canonical scope expansion;
- note preservation by default;
- saved-search impact reporting and separate explicit deletion;
- exact confirmation-token matching;
- canonical SHA revalidation before mutation;
- explicit research/source deletion;
- source provenance refusal;
- library-view-only removal;
- semantic invalidation;
- derived-export cleanup;
- execution-workspace cleanup;
- completed-only retention defaults;
- explicit incomplete retention;
- resume-capability impact;
- stale retention-plan refusal;
- malformed/timezone lifecycle edge cases; and
- human/JSON CLI safety.

The repository Quality workflow runs Ruff, formatting, strict mypy, Vulture, Radon,
branch-coverage pytest, distribution build/install verification, and full platform tests.

## Load-bearing invariants

1. Canonical JSON is evidence, not cache.
2. Rescanning/rebuilding indexes never means re-transcribing audio.
3. Saved searches persist typed intent, never a frozen derived evidence scope.
4. Frequent/recent navigation remains derived rather than authoritative counters.
5. Deleting a rebuildable database must not delete canonical evidence or human-authored
   research state.
6. Output directories remain user-visible and separate from private state/cache.
7. Canonical deletion is plan-bound, exact-generation-aware, and does not cascade into
   human-authored notes.
8. Source media remains read-only unless a separate explicit, provenance-checked deletion
   scope is chosen.
9. Age-based retention cannot delete canonical evidence or research knowledge.
10. EchoFlow never claims secure erasure it cannot prove.
