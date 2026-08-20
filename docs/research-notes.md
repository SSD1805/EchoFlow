# Your notes should survive the machinery 📝🦝

EchoFlow keeps **your research notes, tags, collections, and saved searches** beside
recorded evidence without pretending they are part of the transcript itself.

The recording and canonical transcript describe evidence. A note such as “compare this
with the 2024 survey” is something **you know, suspect, or want to remember**. EchoFlow
keeps those kinds of truth separate while still letting them meet through exact evidence
coordinates.

## The short version

When you attach a note to transcript evidence, EchoFlow stores the note durably and keeps
its exact evidence address:

- document/transcript identity;
- original source SHA-256;
- canonical transcript SHA-256;
- canonical segment IDs; and
- source-relative start/end seconds.

The note survives search-index and research-projection rebuilds.

```mermaid
flowchart LR
    A[Canonical transcript evidence] --> B[Verified EvidenceAnchor]
    B --> C[SQLite durable research state]
    C --> D[Monotonic change journal]
    D --> E[Deterministic projector]
    E --> F[DuckDB research projection]
    F --> G[Fast research-aware search]
    G --> A
    C --> H[Desktop Research workspace]

    classDef evidence fill:#FFF0B8,stroke:#8A6B18,stroke-width:2px,color:#2C260F
    classDef source fill:#F9D5E5,stroke:#7B2E52,stroke-width:2px,color:#22151B
    classDef process fill:#E8D9FF,stroke:#68469B,stroke-width:2px,color:#1F1630
    classDef view fill:#DDF5E3,stroke:#347A46,stroke-width:2px,color:#142719

    class A,B evidence
    class C source
    class D,E,H process
    class F,G view
```

Text fallback: verified canonical evidence anchors durable SQLite research state; a
transactional journal projects that authority into rebuildable DuckDB query state; the
desktop Research workspace consumes the same authority rather than inventing a
browser-owned notebook.

You do not need to operate either database. `ResearchWorkspaceService` presents one
research workspace over the two storage roles.

## Add, edit, organize, delete, and reopen notes

The CLI anchors to real canonical segment IDs rather than a disposable search row or
formatted timestamp:

```bash
echoflow library notes add TRANSCRIPT_ID segment-000042 \
  --body "Check this against the 2024 survey." \
  --tag methodology \
  --tag housing \
  --collection "Chapter 3"
```

A note may span several **contiguous canonical segments**. EchoFlow verifies the current
canonical transcript bytes and refuses missing, reordered, or non-contiguous selections.
Optional `--start-seconds` and `--end-seconds` may narrow an anchor inside that verified
span.

The desktop uses that same rule when a note is created from the verified Evidence reader.
It sends document/generation identity and canonical coordinates through one narrow bridge
method. If the library moved to a newer canonical generation before Save, the write is
refused instead of silently attaching the note to different evidence.

Existing notes can be edited in the Research workspace. A desktop edit replaces note body,
tag assignments, and collection assignments **atomically in authoritative SQLite** and
emits one projection-journal event. The note’s evidence anchor is not rewritten.

Desktop edit/delete carries the note’s authoritative `updated_at` version. If a CLI or
another local surface changed that note after it was displayed, EchoFlow refuses the stale
write and asks the user to refresh. Local-first does not mean lost-update-safe by accident.

A note can now reopen the exact canonical generation it cites. The backend reuses the same
canonical verifier as search navigation: it hashes the stored canonical bytes, checks the
stored source and document identities, validates the stored segments and timing, expands
context, and resolves speaker display labels for that exact generation. React does not
choose a replacement generation.

That means an older note has three honest outcomes:

1. the older canonical generation is still present and verifies, so EchoFlow opens it and
   labels it as older evidence;
2. the stored canonical bytes, identity, segments, or timing no longer verify, so EchoFlow
   refuses to present them as evidence; or
3. the old evidence is unavailable, so the durable note remains but its cited evidence
   cannot currently be reopened.

There is deliberately no “close enough, use the current transcript” fallback. New note
creation is not offered from an older-generation evidence view because that would blur the
boundary between reviewing old evidence and authoring against current evidence.

Deletion remains explicit and narrow: deleting a note deletes that human-authored note. It
does not delete the canonical transcript or original recording.

The equivalent CLI operations remain available:

```bash
echoflow library notes edit NOTE_ID --body "Revised note text"
echoflow library notes set-tags NOTE_ID --tag housing --tag methodology
echoflow library notes set-collections NOTE_ID --collection "Chapter 3"
echoflow library notes delete NOTE_ID
```

## Navigate by tags and collections

Tags and collections are first-class desktop navigation affordances, not decorative pills.
Clicking a label asks the backend for authoritative filtered notes through the existing
`ResearchWorkspaceService` filter contract. React does not filter a capped overview
snapshot or recreate projection rules in the browser.

Multiple selected labels use **AND semantics**: every selected tag and every selected
collection must match the same note. The Research surface keeps active filters visible,
lets the user remove them individually or clear them all, and preserves the existing
note → verified-evidence path from filtered results.

## Use research state to search the transcript corpus

Research metadata can constrain transcript retrieval before scoring:

```bash
echoflow library search "housing affordability" \
  --tag methodology \
  --with-notes
```

Or require terms in attached notes while searching transcript evidence:

```bash
echoflow library search "housing affordability" \
  --note-text "2024 survey" \
  --collection "Chapter 3"
```

EchoFlow resolves human names to durable IDs, obtains a canonical evidence scope from the
research projection, and ranks lexical/semantic candidates **inside that scope**. It does
not retrieve the whole corpus and throw away results afterward.

Unified workspace discovery powers the desktop Library search. Search results can show
associated note count, tags, and collections alongside original evidence/ranking data
without inventing one cross-type relevance score.

## What if the transcript changes?

A note belongs to the **exact canonical transcript generation** it was written against.
If a regenerated transcript reuses the same friendly `segment-000042` under a different
canonical SHA-256, EchoFlow does **not** silently move the old note.

The old note remains durable historical user state. The projected evidence key includes
canonical generation identity so stale annotations cannot accidentally attach to new
evidence. Editing the prose or labels on that old note still leaves its original anchor
unchanged. The desktop can now inspect the older generation when those exact canonical
bytes remain available and valid.

A later re-anchor workflow must be an explicit user decision that shows both generations;
it must never be an incidental side effect of opening or editing a note.

## Why two databases?

| Store | Job | Rebuildable? |
|---|---|---|
| SQLite research state | authoritative notes/tags/collections/saved searches and evidence anchors | **No** |
| DuckDB research projection | fast derived relationships and lexical note terms | Yes |
| DuckDB transcript index | transcript terms/segments for lexical ranking | Yes |
| DuckDB semantic index | chunks/vectors for semantic retrieval | Yes |

SQLite fits frequently mutated transactional user state. DuckDB fits local analytical
query workloads. EchoFlow deliberately does **not** make both authoritative.

```text
SQLite authority
      |
      | monotonic transactional journal
      v
Deterministic projector
      |
      v
DuckDB projection
```

If the stores disagree, SQLite wins. If DuckDB disappears, rebuild it.

## Saved searches are durable questions, not screenshots

Saved searches persist typed query intent and re-resolve current evidence rather than
freezing result snapshots. Frequent/recent tag and collection navigation is derived from
current relationships instead of persisted popularity counters.

The desktop now supports saved-search create, run, rename, and delete. Creation sends only
human intent across the desktop bridge; Python constructs and validates the typed
`SearchQuery` and owns desktop defaults. Running the search replays that typed intent
through current research-aware retrieval, so new qualifying evidence can appear.

Rename edits display metadata while preserving the typed search intent server-side.
Rename/delete carry the saved search’s `updated_at` version, and authoritative SQLite checks
that version inside the same immediate transaction as the mutation. A stale desktop view
cannot silently overwrite a newer CLI/local change.

The tag is durable user state. “Used 147 times” is disposable navigation metadata.

## Operational logs are not a shadow research archive

Research operations use the normal structured application logger for operational evidence:
operation names, durable object IDs, canonical generation identity where relevant,
retrieval mode, counts, current/older state, and success/failure outcome.

The logger does **not** receive note bodies, saved-query text, saved-search names or
descriptions, or raw canonical/source paths from these Research operations. The durable
research stores remain the authority for human-authored content; logs do not become a
second notebook.

## What comes next for the notebook?

The storage, evidence-address, unified-discovery, Research overview, verified note
creation, note edit/delete/label mutation, first-class tag/collection navigation,
exact-generation note return, and saved-search create/run/rename/delete contracts are
built.

The remaining first-release Research tranche is narrower:

- expose advanced typed search/research controls without hidden interpretation; and
- stale/unavailable-anchor review and any explicit re-anchor UX with user confirmation.

Selected evidence packets, REFI-QDA interoperability, saved-question snapshots/diffs,
comparison workspaces, evidence-linked writing/script boards, portable research bundles,
and live provisional capture are deliberately post-MVP work. See
**[Post-MVP research roadmap](post-mvp-roadmap.md)**.

The product does not currently provide rich-text/WYSIWYG editing, semantic embeddings over
note prose, automatic cross-generation re-anchoring, or collaborative sync.

> **Your research state is durable. Its fast query representation is disposable. The two
> can always meet again through exact evidence identities.**