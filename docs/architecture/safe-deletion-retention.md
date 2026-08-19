# Safe deletion and retention controls

EchoFlow treats deletion as a custody decision, not a filesystem shortcut.

The deletion surface therefore starts with a typed plan. A plan identifies the exact
canonical generation, every mutation EchoFlow intends to make, durable research objects
that will be preserved, saved searches whose results may change, and a confirmation token
bound to that exact plan. No deletion occurs until the same request is repeated with the
matching token.

This design protects the central library invariant:

> **Removing evidence from search must never silently erase canonical transcript evidence,
> user-authored research knowledge, or an original recording.**

## CLI

Plan an operation:

```bash
echoflow library delete TRANSCRIPT_ID --scope library-view
```

The command is a dry run unless `--confirm` is supplied. The human and JSON forms both
include the plan-bound confirmation token.

Apply exactly the reviewed plan:

```bash
echoflow library delete TRANSCRIPT_ID \
  --scope library-view \
  --confirm 'delete:...'
```

Scopes can be repeated:

```bash
echoflow library delete TRANSCRIPT_ID \
  --scope research-notes \
  --scope source-recording \
  --allow-source
```

Source deletion has a second safety gate: `--allow-source` is required and EchoFlow refuses
to delete the recording unless the current source bytes still match the source SHA-256
recorded when the transcript was created.

Private execution-state retention uses the same plan/apply contract:

```bash
echoflow library retention --execution-days 30
echoflow library retention --execution-days 30 --confirm 'retention:...'
```

By default only completed job workspaces are eligible. Failed and interrupted workspaces
are included only with `--include-incomplete`, because deleting those workspaces removes
resume capability. Running jobs are never eligible.

## Typed deletion scopes

`DeletionScope` deliberately separates meanings that a generic "delete transcript" button
would otherwise collapse.

| Scope | Effect | Does not do |
|---|---|---|
| `library-view` | removes the document from the lexical index and clears a built semantic corpus whose fingerprint would otherwise reference it | does not delete canonical JSON, exports, notes, lifecycle metadata, or source media |
| `derived-artifacts` | deletes sibling TXT/SRT/VTT publications that can be regenerated from canonical JSON | does not touch canonical JSON |
| `execution-state` | deletes the exact private job workspace containing checkpoints/intermediates | preserves the lightweight lifecycle manifest and all public evidence |
| `canonical-transcript` | deletes canonical JSON and automatically expands to `library-view`, `derived-artifacts`, and `execution-state` | does not delete notes or the source recording |
| `research-notes` | deletes notes anchored to the exact current canonical generation | does not delete tags/collections globally and is never implied by canonical deletion |
| `saved-searches` | deletes saved searches that explicitly constrain `document_ids` to this transcript | does not delete global saved searches and is never implied by canonical deletion |
| `source-recording` | deletes the original recording only after the explicit source gate and provenance check | is never implied by any other scope |

`canonical-transcript` is cumulative only across disposable descendants. The unique human/source custody classes, `research-notes`, `saved-searches`, and
`source-recording`, always require their own explicit scopes.

## Why notes survive canonical deletion

Notes are user-authored knowledge. Their evidence anchor contains:

```text
document_id
canonical_sha256
segment_id(s)
source-relative time coordinates
```

If canonical JSON is explicitly deleted without the `research-notes` scope, those
notes remain in authoritative SQLite. They become historical/stale anchors because their
exact canonical generation is no longer present in the active transcript index.

That is intentional. EchoFlow prefers:

```text
note survives + evidence is reported unavailable
```

over:

```text
canonical deletion cascades into silent loss of human work
```

A later UI can present this as an "evidence unavailable" note while still showing the
recorded document/generation identity.

## Saved searches are preserved unless their own scope is selected

Saved searches persist typed intent rather than result snapshots. A saved search that
explicitly constrains `document_ids` to a transcript being removed is listed in the
deletion plan as affected. By default it is preserved, so replay later re-resolves the
current library and may return fewer or no results.

If the user also selects `saved-searches`, only those document-scoped saved searches are
deleted. Global saved searches are not guessed to be dependent merely because they might
currently return the transcript. This keeps deletion explicit rather than semantic-by-guess.

## Semantic deletion is corpus-wide today

The current semantic index is generation-bound to one corpus fingerprint and exposes
atomic rebuild/clear operations rather than per-document mutation.

Therefore removing one transcript from the active library:

1. removes that document from the lexical index; and
2. clears a built semantic index.

That is intentionally conservative. Keeping vectors whose state fingerprint still claims
the removed generation would create stale derived state. Semantic search can be rebuilt
later from the remaining canonical corpus.

A future incremental semantic index may support generation-scoped removal without changing
the deletion service contract.

## Canonical integrity is rechecked before mutation

The deletion plan binds to `canonical_sha256`. Immediately before executing any action,
EchoFlow re-reads the canonical JSON scheduled for deletion and recomputes SHA-256.

If the bytes changed after indexing, execution fails before any mutation. The user must
rebuild/review the current generation and obtain a new plan.

This prevents a stale confirmation token from authorizing deletion of different canonical
bytes that happen to occupy the same path.

The token is not an authentication secret. It is a change-detection/confirmation primitive
that binds the user's approval to the exact planned mutation set.

## Source deletion has an additional provenance boundary

Original recordings are treated read-only throughout normal EchoFlow processing.

A source recording can be deleted only when all of the following are true:

1. `source-recording` is an explicitly requested scope;
2. `--allow-source` is supplied;
3. a source path is available;
4. the source still exists; and
5. current source integrity is `matches-recorded-source`.

If a recording changed since transcription, EchoFlow refuses deletion. That prevents a
transcript's old provenance record from becoming authorization to delete new bytes at the
same path.

## Retention is restricted to private execution workspaces

Automatic age-based retention is intentionally narrower than explicit deletion.

`RetentionPolicy` currently governs only private job workspaces:

```text
state/
└── jobs/
    └── JOB_ID/
        ├── checkpoints/
        └── intermediates/
```

It never age-deletes:

- canonical JSON;
- TXT/SRT/VTT;
- source recordings;
- notes/tags/collections;
- speaker labels;
- saved searches;
- lexical/semantic research meaning; or
- lightweight job lifecycle manifests.

Keeping lifecycle manifests matters because they can retain the discovery pointer to a
canonical transcript written to a custom output directory. Deleting the heavy workspace
while preserving that small manifest frees resumable/intermediate state without making
valid evidence harder to rediscover.

## Retention defaults

The default CLI policy is:

```text
execution_days = 30
include_incomplete = false
```

A completed workspace older than the cutoff is eligible.

Failed/interrupted workspaces remain available for resume unless the user explicitly opts
into `--include-incomplete`. Running jobs are never eligible, regardless of age.

Retention plans are recalculated at execution time. If candidates changed, the old token
no longer matches and EchoFlow refuses to apply the stale plan.

## Filesystem and failure semantics

EchoFlow cannot make SQLite, DuckDB, arbitrary public files, private workspaces, and source
media participate in one cross-filesystem ACID transaction.

The executor therefore orders operations by custody risk:

1. rebuildable index state;
2. regenerable publication artifacts;
3. private execution workspace;
4. canonical transcript evidence;
5. explicitly requested source media;
6. explicitly requested document-scoped saved searches; and
7. explicitly requested research notes.

Unique human-authored state is ordered last. If an earlier filesystem mutation fails,
notes and saved searches remain intact rather than being sacrificed before a recoverable
cleanup step.

Before the first mutation, destructive canonical inputs are revalidated.

If a later filesystem operation fails, earlier disposable mutations may already have
occurred. Those can be rebuilt. EchoFlow deliberately avoids deleting unique evidence
first and hoping cleanup succeeds afterward.

## Secure erasure is not claimed

Deletion means EchoFlow asks the operating system/filesystem to remove the selected file
or directory.

It does **not** mean EchoFlow can prove the bytes are unrecoverable from:

- SSD wear-levelled blocks;
- copy-on-write filesystem history;
- snapshots;
- backups;
- cloud sync/version history;
- storage-controller caches; or
- forensic recovery outside the active filesystem namespace.

Both human and JSON CLI output therefore state that secure erasure is not guaranteed.

## Test contract

The custody tests cover:

- canonical scope expansion;
- preservation of notes by default;
- saved-search impact reporting and separate explicit deletion;
- exact confirmation-token matching;
- canonical SHA revalidation before any mutation;
- explicit research deletion;
- explicit source deletion and provenance refusal;
- library-view-only removal;
- semantic invalidation;
- derived-export cleanup;
- private execution-workspace cleanup;
- default completed-only retention;
- explicit incomplete-job retention;
- resume-capability impact reporting;
- stale retention-plan refusal;
- timezone/malformed lifecycle edge cases;
- human and JSON CLI behavior; and
- safe public/internal error presentation.

Additional saved-search tests added alongside this work cover value-object validation,
storage bounds, corrupt persisted JSON/enums, missing mutation targets, closed navigation
dispatch, and human rendering paths that were under-covered in the merged saved-search PR.
