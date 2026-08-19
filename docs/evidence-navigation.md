# 🔎 From search result to the exact evidence

Search is useful when it finds something. Research gets easier when the result can also
answer **“where, exactly, did this come from?”**

EchoFlow has a navigation layer between retrieval and presentation. BM25, semantic search,
and hybrid retrieval decide *which passage ranks*. Then EchoFlow goes back to the
authoritative canonical transcript, verifies that it is still the exact transcript that
was indexed, and resolves the result onto canonical segments and word timing.

That distinction is important. A search database may point at evidence. It does not get
to become the evidence.

```mermaid
flowchart LR
    A[Your query] --> B[Lexical semantic hybrid ranking]
    B --> C[Ranked passage]
    C --> D[Verify canonical transcript]
    D --> E[Canonical segments and words]
    E --> F[Context highlights and seek]
    E --> G[Durable EvidenceAnchor]
    G --> H[Notes tags collections]

    classDef source fill:#F9D5E5,stroke:#7B2E52,stroke-width:2px,color:#22151B
    classDef process fill:#E8D9FF,stroke:#68469B,stroke-width:2px,color:#1F1630
    classDef evidence fill:#FFF0B8,stroke:#8A6B18,stroke-width:2px,color:#2C260F
    classDef view fill:#DDF5E3,stroke:#347A46,stroke-width:2px,color:#142719

    class A source
    class B,C process
    class D,E,G evidence
    class F,H view
```

Text fallback: retrieval ranks a passage, canonical navigation verifies it, and the same
verified evidence coordinates can be used by the desktop reader and durable research
notes.

🦝 Search may know the neighborhood. The canonical transcript still owns the street
address.

## What changes when I search?

The command-line contract remains ordinary library search:

```bash
echoflow library search "housing affordability"
```

The desktop Library screen now consumes the same application seam through grouped
workspace discovery. Neither interface changes which object is authoritative.

EchoFlow returns retrieval provenance: source and canonical hashes, segment/chunk
identities, numeric source-relative time, languages, anonymous speaker refs, and
lexical/semantic/fused ranks.

A result can also carry a verified **evidence location**:

- exact canonical transcript generation;
- result segment IDs;
- source-relative result interval;
- deterministic seek coordinate;
- canonical word matches when lexical evidence justifies them;
- current user-assigned speaker display names without replacing anonymous refs; and
- optional neighboring canonical context.

Machine-readable JSON and desktop DTOs keep those layers separate rather than flattening
them into one mystery object. The desktop bridge deliberately omits canonical/source
filesystem paths from evidence presentation DTOs.

## Exact highlighting is allowed to say “I don't know”

Lexical search knows which canonical segment matched the terms you asked for. When that
segment has aligned word timing, EchoFlow can resolve the same lexical token semantics
onto canonical words and highlight the words that actually matched.

For an exact phrase:

```bash
echoflow library search "housing affordability" --phrase
```

EchoFlow requires phrase tokens to be contiguous before marking canonical words as the
exact match.

Semantic retrieval is different. An embedding may decide this passage:

```text
I was spending almost seventy percent of my pay on the apartment.
```

is relevant to:

```text
people struggling to afford housing
```

There may be no single word in the passage that means “this is the semantic match.” A
semantic-only result therefore gets a verified passage and seek coordinate, but no fake
exact-word highlight.

Hybrid retrieval may contain both kinds of evidence. When lexical evidence contributed,
exact lexical highlights can be shown alongside fused ranking provenance.

## Give me a little more context

```bash
echoflow library search \
  "housing affordability" \
  --context-segments 1
```

`--context-segments` accepts `0` through `10`. Context expansion happens **after ranking**.
EchoFlow does not feed neighboring text back into BM25 or semantic scoring and then
pretend the original ranks still mean the same thing.

The returned context distinguishes actual result evidence from neighboring segments shown
only for reading. The desktop Evidence reader renders that verified context directly.

## What about speaker names?

If you previously assigned:

```text
speaker-02 → Dr. Chen
```

ordinary presentation can show:

```text
Dr. Chen (speaker-02)
```

The anonymous `speaker-02` remains machine-readable evidence. The friendly label comes
from separate durable user state and applies only to the exact canonical transcript
generation it was created for.

## Can this jump to the original audio or video?

The application contract exposes the coordinate a player needs.

If an exact aligned lexical match begins at:

```text
4788.370 seconds
```

that renders as:

```text
01:19:48.370
```

and becomes the preferred seek point. If a result has no justified exact-word match, the
passage start remains the safe seek coordinate.

The desktop Evidence reader now exposes this as an interactive **evidence cursor**. Clicking
a canonical timed word moves the cursor to that verified source-relative coordinate;
“Return to match” restores the backend-selected match coordinate.

EchoFlow still does not ship local audio/video playback. Playback is planned behind a
Tauri-owned capability so React can consume safe playback state and verified coordinates
without receiving arbitrary raw source paths.

## Susan's notes use this exact coordinate system 📝

`ResearchWorkspaceService.add_note()` asks `EvidenceLocator` to resolve a verified
`EvidenceAnchor` before durable user state is written. The anchor preserves:

```text
document ID
source SHA-256
canonical transcript SHA-256
canonical segment IDs
numeric start/end seconds
```

A command-line note therefore attaches to canonical evidence, not a search row:

```bash
echoflow library notes add JOB_ID segment-000042 \
  --body "Compare this with the 2024 survey." \
  --tag methodology
```

A multi-segment note must select contiguous canonical segments. Optional narrower time
coordinates may refine the anchor inside that verified span.

The note body remains separate durable user knowledge. That means:

- changing timestamp formatting does not detach the note;
- rebuilding BM25 does not delete the note;
- rebuilding semantic vectors does not delete the note;
- rebuilding the DuckDB research projection does not delete the note;
- changing the canonical transcript is detected instead of silently teleporting the
  note; and
- CLI, desktop, export, and citation workflows share one anchoring contract.

```mermaid
flowchart TD
    A[Canonical transcript evidence] --> B[Verified evidence location]
    B --> C[CLI and desktop result view]
    B --> D[Durable EvidenceAnchor]
    D --> E[SQLite note]
    E --> F[Rebuildable DuckDB research projection]
    B --> G[Desktop evidence cursor]
    G --> H[Future Tauri media capability]

    classDef evidence fill:#FFF0B8,stroke:#8A6B18,stroke-width:2px,color:#2C260F
    classDef source fill:#F9D5E5,stroke:#7B2E52,stroke-width:2px,color:#22151B
    classDef view fill:#DDF5E3,stroke:#347A46,stroke-width:2px,color:#142719
    classDef inspect fill:#D8EEFF,stroke:#2E617B,stroke-width:2px,color:#12222A
    classDef process fill:#E8D9FF,stroke:#68469B,stroke-width:2px,color:#1F1630

    class A,B,D evidence
    class E source
    class C,F view
    class G inspect
    class H process
```

## Research metadata can constrain later retrieval

Once notes/tags/collections exist, they are not merely decorations on already-ranked
results. EchoFlow can resolve them into a canonical evidence scope before ranking:

```bash
echoflow library search \
  "housing affordability" \
  --tag methodology \
  --collection "Chapter 3" \
  --with-notes
```

Saved searches can persist that typed intent and re-resolve current evidence later. The
browse-first desktop Research screen now lists authoritative notes, tags, collections, and
saved searches; note/saved-search editing is the next UI slice.

This is important. The application does not retrieve a giant corpus and then throw away
results in Python after the fact.

## What this deliberately does not do

Evidence navigation still does not:

- change BM25, semantic similarity, or RRF ranking;
- claim an exact word match for semantic-only relevance;
- rewrite canonical JSON;
- bake speaker display names into diarization evidence;
- automatically re-anchor notes across changed canonical generations;
- expose arbitrary raw source/canonical paths to React; or
- ship graphical audio/video playback yet.

The next product layers reuse the same verified coordinate system rather than inventing a
new idea of “where this quote came from.”

For the retrieval internals, open **[Evidence-first corpus search](architecture/corpus-search.md)**.
For durable notebook custody, see **[Your notes should survive the machinery](research-notes.md)**.
For how the timeline works, see **[Transcript time without calculator gymnastics](time-navigation.md)**.
