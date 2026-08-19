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
    C --> H[Next Desktop Research workspace]

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
next desktop Research workspace will consume the same authority rather than inventing a
browser-owned notebook.

You do not need to operate either database. `ResearchWorkspaceService` presents one
research workspace over the two storage roles.

## Add and edit notes today

The current CLI anchors to real canonical segment IDs rather than a disposable search row
or formatted timestamp:

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

List or filter notes:

```bash
echoflow library notes
echoflow library notes --text "survey methodology" --tag housing
```

Edit authoritative research state explicitly:

```bash
echoflow library notes edit NOTE_ID --body "Revised note text"
echoflow library notes set-tags NOTE_ID --tag housing --tag methodology
echoflow library notes set-collections NOTE_ID --collection "Chapter 3"
echoflow library notes delete NOTE_ID
```

Those commands mutate authoritative SQLite user state. The DuckDB query projection catches
up from the monotonic journal.

The desktop Evidence reader already works with the same verified segment/word coordinate
system. The next Research UI tranche should turn verified selections into the exact same
`EvidenceAnchor` instead of creating a graphical-only annotation model.

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

Unified workspace discovery is implemented and powers the desktop Library search. Search
results can show associated note count, tags, and collections alongside original
evidence/ranking data without inventing one cross-type relevance score.

## What if the transcript changes?

A note belongs to the **exact canonical transcript generation** it was written against.
If a regenerated transcript reuses the same friendly `segment-000042` under a different
canonical SHA-256, EchoFlow does **not** silently move the old note.

The old note remains durable historical user state. The projected evidence key includes
canonical generation identity so stale annotations cannot accidentally attach to new
evidence.

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

## Saved searches and navigation are foundation

Saved searches persist typed query intent and re-resolve current evidence rather than
freezing result snapshots. Frequent/recent tag and collection navigation is derived from
current relationships instead of persisted popularity counters.

The tag is durable user state. “Used 147 times” is disposable navigation metadata.

## What comes next for the notebook?

The storage, evidence-address, unified-discovery, saved-search, and derived-navigation
contracts are built. The next tranche is the dedicated desktop Research workspace:

- browse current and older-generation notes;
- create a note directly from verified desktop evidence;
- edit/delete notes and assign/remove tags/collections;
- create, run, rename, and delete saved searches;
- navigate research objects back to current verified evidence when possible;
- stale-anchor review/re-anchor UX with explicit user confirmation; and
- later, selected/citable result sets and portable evidence-bearing research export.

The product does not currently provide rich-text/WYSIWYG editing, semantic embeddings over
note prose, automatic cross-generation re-anchoring, or collaborative sync.

> **Your research state is durable. Its fast query representation is disposable. The two
> can always meet again through exact evidence identities.**
