# Research search

EchoFlow has two complementary search surfaces.

**Library** is the quick doorway: type what you remember and search transcripts, notes,
tags, and collections. **Research** adds explicit choices when you need to narrow or save a
question. They do **not** implement separate search engines. Both end in the same Python
search and evidence-navigation authority.

The desktop deliberately uses ordinary product language even though the backend retains a
more exact typed model.

## What the user sees

The main Research search asks two things up front:

1. **What are you looking for?**
2. **Match:** Any of these words / All of these words / Exact phrase.

Everything else is behind **Search options**:

- **Search by:** Wording / Meaning / Wording + meaning;
- **Order results by:** Relevance / Time;
- maximum results;
- context around a result;
- speakers;
- languages;
- interviews/transcripts;
- tags;
- collections;
- text in attached notes; and
- only results that have notes.

Successful results can expose backend/model/fusion provenance under **Technical details**.
That information remains inspectable without being a vocabulary test for someone trying to
find an interview passage.

## How the simple Match control stays rigorous

The backend contract still carries separate `phrase` and `operator` properties because they
are useful, explicit search semantics. The GUI does not ask ordinary users to manipulate
both at once.

The presentation mapping is deterministic:

| Human choice | Typed request |
|---|---|
| Any of these words | `phrase=false`, `operator=any` |
| All of these words | `phrase=false`, `operator=all` |
| Exact phrase | `phrase=true`, `operator=all` |

Python still validates and canonicalizes the resulting request. React has not become the
search-semantic authority; it has simply stopped exposing two low-level knobs for one human
choice.

A saved legacy intent with `phrase=true` remains presented as **Exact phrase** regardless of
the stored operator because exact phrase is the stronger visible semantic. Saving that
question again canonicalizes the presentation choice to the table above.

## The typed intent underneath

The backend Research intent can contain:

- query text;
- exact-phrase flag and ANY/ALL term operator;
- anonymous speaker-reference filters;
- language filters;
- transcript/document filters;
- relevance or source-timeline ordering;
- result limit;
- lexical, semantic, or hybrid retrieval mode;
- surrounding context-segment count;
- required research tags;
- required research collections;
- required text in attached notes; and
- whether qualifying evidence must have an attached research note.

Those controls are represented in Python as one `ResearchSearchIntent`. The object contains
a normal `SearchQuery`, `ResearchQueryFilters`, `RetrievalMode`, and context count. It
rejects an `evidence_scope` supplied as user intent because evidence scope is derived state,
not something the desktop is allowed to author.

```mermaid
flowchart LR
    A[Human search choices] --> B[Strict desktop DTO]
    B --> C[ResearchSearchIntent]
    C --> D[ResearchQueryFilters]
    C --> E[SearchQuery]
    D --> F[Derived evidence scope]
    E --> G[Current transcript retrieval]
    F --> G
    G --> H[Canonical evidence verifier]
    H --> I[Desktop evidence result]

    classDef input fill:#E8D9FF,stroke:#68469B,stroke-width:2px,color:#1F1630
    classDef authority fill:#F9D5E5,stroke:#7B2E52,stroke-width:2px,color:#22151B
    classDef derived fill:#DDF5E3,stroke:#347A46,stroke-width:2px,color:#142719
    classDef evidence fill:#FFF0B8,stroke:#8A6B18,stroke-width:2px,color:#2C260F

    class A,B input
    class C,D,E authority
    class F,G derived
    class H,I evidence
```

Text fallback: React collects ordinary search choices and submits a strict desktop DTO.
Python constructs and validates search intent and research filters, derives any evidence
scope from authoritative research state, retrieves current transcript evidence, and
verifies canonical evidence before results return to the desktop.

## The browser does not interpret evidence policy

React is allowed to compile the documented Match presentation choice and collect/display
other values. It does not:

- derive evidence scope from visible notes or labels;
- filter a capped result set after retrieval;
- invent semantic/lexical scores;
- choose a canonical generation;
- query SQLite or DuckDB directly;
- turn saved searches into shell commands, SQL, or opaque strings; or
- silently fall back from an unavailable semantic mode to a different retrieval mode.

The backend validates the nested intent again even though browser controls constrain some
values. The desktop adapter uses `extra="forbid"`, so unexpected fields such as SQL, a
filesystem path, or a derived evidence scope are not silently accepted.

Speaker, language, and transcript filters are currently explicit identifiers. The desktop
does not fabricate authoritative dropdown options by scraping whichever results happen to
be visible. A future convenience picker should come from a backend facet/catalog service.

## Research filters happen before ranking

Tags, collections, note text, and `with_notes` are not browser-side result filters.
`ResearchWorkspaceService` synchronizes the research projection, resolves human-facing
labels to durable IDs, obtains the matching current evidence identities, and passes that
evidence scope into transcript retrieval.

Adding research constraints therefore narrows the candidate evidence **before** lexical or
semantic ranking. The GUI cannot reproduce or weaken that rule.

## Wording, meaning, and both

The user-facing labels map to the existing retrieval modes:

| Desktop | Backend |
|---|---|
| Wording | lexical |
| Meaning | semantic |
| Wording + meaning | hybrid |

Semantic and hybrid modes use the existing local semantic index and embedding profile.
Selecting them does not make that capability magically available: Python verifies that
semantic state exists, matches the current corpus, and can load the qualified local model.
If not, the operation fails with the normal safe application error rather than silently
changing retrieval mode.

A successful result returns retrieval provenance such as backend IDs, semantic profile, and
hybrid fusion profile. The desktop places those fields under **Technical details**; React
does not calculate them.

## Saved searches store the whole question

A saved search is durable intent, not a frozen result list. It can retain the same match,
transcript/speaker/language, research-filter, retrieval, ordering, limit, and context choices
used for an immediate search.

Creating a saved search converts `ResearchSearchIntent` into the existing durable
`SavedSearchIntent`. Runtime `evidence_scope` is deliberately omitted. Running the question
later re-derives qualifying evidence from whatever current transcript and research state
exists at that time.

Editing a saved search replaces **display metadata and the complete typed intent in one
authoritative SQLite transaction**. The mutation carries `expected_updated_at`; if another
local surface changed the saved search after it was opened, EchoFlow refuses the stale write
rather than losing the newer edit.

The UI calls these actions **Save search** and **Update saved search**. “Typed intent” remains
a maintainer concept and storage contract, not a label an ordinary user must decode.

## Desktop privacy boundary

The search bridge returns evidence text, IDs/hashes needed for evidence identity,
source-relative times, speaker display state, research labels, and retrieval provenance.
It does not return raw canonical or original-recording filesystem paths as part of the
search result DTO.

Operational logging for saved-intent replacement records durable object identity, retrieval
mode, context size, and filter counts. It does not log query text, note-text filters, saved
search names/descriptions, or raw media/canonical paths.

## First-release status

The complete typed Research search contract is implemented in the desktop. Remaining
Research work is optional polish, convenience catalogs/facets, or post-MVP workflows rather
than a blocker for playback, lifecycle UI, packaging, or portability.

The product rule remains: **simple by default, inspectable when needed, authoritative in
Python either way.**
