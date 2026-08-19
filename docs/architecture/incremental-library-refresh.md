# Incremental library refresh

EchoFlow's canonical transcript JSON is durable evidence. The lexical and semantic
indexes are private, rebuildable views over that evidence.

Normal library maintenance should therefore be cheap when nothing changed and exact when
something did.

The user-facing operations are deliberately different:

| Operation | Input | What changes |
|---|---|---|
| `transcribe` | source media | creates a new canonical transcript generation |
| `library refresh` | existing canonical JSON | reconciles changed library membership and lexical projection |
| `library refresh --verify` | existing canonical JSON | re-hashes and validates every tracked canonical before reconciling |
| `library rebuild` | existing canonical JSON | replaces the complete lexical projection as a repair/recovery operation |

Refresh never runs ASR, rewrites canonical JSON, or changes the source recording.

## Generation identity and the fast path

The authoritative generation identity remains:

```text
(document_id, canonical_sha256)
```

A SHA-256 requires reading the file. Re-hashing every transcript on every normal refresh
would make the database writes incremental while leaving canonical I/O whole-corpus.
EchoFlow therefore stores two additional **derived change-detector fields** in the lexical
projection:

```text
canonical_size_bytes
canonical_modified_ns
```

On a normal refresh, a tracked canonical file can be skipped without opening it when:

1. its canonical path is unchanged;
2. its size is unchanged;
3. its filesystem modification time is unchanged; and
4. its known source-path metadata has not changed.

Those fields are an optimization, not evidence. They do not replace `canonical_sha256`.
An older index that predates the fields simply cannot take the fast path; the next refresh
reads the canonical once and stores the derived signature.

## Verified refresh

Filesystems do not make size and modification time cryptographic statements. A file can,
in principle, be replaced with different same-size bytes while retaining or restoring the
same modification time.

`--verify` exists for the case where the user wants an exact corpus check:

```bash
echoflow library refresh --verify
```

Verified refresh bypasses the metadata fast path, reads every tracked canonical, validates
its schema, and recomputes its SHA-256. A generation whose bytes are unchanged is still not
rewritten into DuckDB.

This is also why evidence navigation continues to verify canonical SHA-256 before
presenting precise source evidence. The refresh fast path is a performance optimization;
it is not promoted into an integrity guarantee.

## Reconciliation rules

After discovery and validation, refresh computes one typed corpus delta:

```text
new document            -> upsert
new canonical generation -> replace/upsert
moved tracked canonical  -> update canonical path
missing tracked canonical -> remove from rebuildable library view
unchanged generation      -> skip
```

`TranscriptIndex.apply_delta()` applies all lexical removals and upserts in one DuckDB
transaction. If any write fails, the previous lexical projection remains intact.

Tracked canonical files are strict. If a file that was already part of the library is
present but cannot be validated, refresh fails closed rather than silently dropping the
old indexed evidence. Untracked JSON encountered through a directory scan can still be
skipped as unrelated noise, matching full rebuild behavior.

If a tracked canonical changes availability during the refresh itself, EchoFlow refuses
the reconciliation and asks for a retry rather than guessing which filesystem state was
intended.

## Imported and moved transcripts

An explicit import should not require the user to remember the same path forever.

After a canonical transcript has entered the library, its indexed canonical path remains a
refresh discovery input while that path exists. A later normal refresh therefore keeps an
external import tracked even when its original `PATH` argument is not repeated.

If the old path no longer exists and a newly discovered canonical with the same document
identity appears elsewhere, refresh treats it as a move/update. If both the old and new
canonical paths still exist with the same document ID, refresh fails closed on duplicate
identity instead of choosing one arbitrarily.

## Semantic projection behavior

The current semantic index has a whole-corpus fingerprint and does not expose an atomic
per-document mutation contract.

When refresh changes semantic-relevant corpus identity, EchoFlow clears the semantic
projection before applying the lexical delta. Semantic or hybrid search then remains
unavailable until embeddings are rebuilt. This is preferable to retaining vectors whose
stored corpus fingerprint describes evidence that is no longer in the lexical corpus.

Semantic state is invalidated for:

- an added transcript;
- a removed transcript;
- changed canonical bytes;
- a moved canonical path; or
- changed source-path metadata carried by search chunks.

A filesystem timestamp-only change whose canonical SHA and semantic-relevant metadata are
unchanged updates the cheap lexical change detector without throwing away valid vectors.

Incremental vector mutation is intentionally not smuggled into this tranche. It can be
added later by extending the semantic index contract while preserving the same custody and
generation rules.

## Complexity and scale contract

For an unchanged tracked corpus, normal refresh may enumerate file metadata but must not
open canonical JSON merely to discover that nothing changed.

The regression suite exercises a 100-transcript corpus and requires:

```text
100 unchanged transcripts -> 0 canonical reads
1 changed transcript       -> 1 canonical read
```

This is a deterministic I/O contract rather than a wall-clock benchmark, so it remains
stable across CI hardware. Separate representative-corpus qualification should measure
cold/warm latency, database size, semantic rebuild cost, and interactive search behavior.

## Full rebuild remains the repair lever

Incremental refresh is the normal maintenance path. It does not make full rebuild obsolete.

Use `library rebuild` when the derived lexical database is absent, damaged, incompatible,
or deliberately being regenerated under a new projection/tokenization contract. Rebuild
re-reads the discoverable canonical corpus and replaces the disposable index atomically.

The custody hierarchy does not change:

- canonical JSON remains authoritative transcript evidence;
- notes/tags/collections/saved searches remain authoritative human state;
- lexical/semantic/research DuckDB state remains rebuildable;
- refresh never turns a projection into a second source of truth.
