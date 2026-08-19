# Welcome to EchoFlow 🦝✨

EchoFlow is a **private, local-first workspace for recorded evidence**.

It can inspect a recording, choose a safe way to run on the computer you actually have,
transcribe locally, survive interruptions, preserve provenance, search a private corpus,
navigate results back to verified canonical evidence, keep research notes attached to that
evidence, save reusable research questions, and expose the first import/search/evidence
workflows through a native desktop shell.

You do **not** need to understand CUDA, DuckDB, SQLite, BM25, vector spaces, immutable
model revisions, or why a raccoon has been granted library privileges. EchoFlow owns that
machinery so the user can concentrate on recordings and evidence.

> **The short version:** your recording stays yours, canonical JSON remains inspectable
> evidence, your notes and saved searches remain your knowledge, and most machinery built
> around those things can be thrown away and rebuilt.

## What can EchoFlow do today?

| You want to… | EchoFlow currently… |
|---|---|
| Transcribe privately | runs faster-whisper locally from a verified managed model |
| Avoid melting a smaller laptop | inspects process-visible CPU, RAM, and compatible acceleration before choosing a strategy |
| Survive interruption | checkpoints completed work and validates the original contract on resume |
| Keep the original recording intact | treats source media as read-only during normal processing and writes artifacts separately |
| Handle audio/video | selects one audio stream deterministically and canonicalizes locally |
| Clean noisy audio | optionally applies deterministic local suppression with provenance/timeline checks |
| Work across languages | supports multilingual decoding plus conservative local language attribution |
| Distinguish speakers | preserves optional anonymous recording-scoped speaker evidence without claiming identity |
| Publish useful formats | produces canonical JSON plus rebuildable TXT/SRT/WebVTT |
| Search a private corpus | supports lexical BM25, optional semantic retrieval, and hybrid RRF |
| Follow a result to evidence | verifies canonical generation and returns justified segment/word/context/seek coordinates |
| Keep durable research | stores notes/tags/collections in authoritative private SQLite anchored to exact evidence |
| Reuse research questions | stores saved typed query intent and re-resolves current evidence |
| Remember libraries | persists explicit transcript/recording location permissions without copying user media |
| Refresh an evolving corpus | incrementally reconciles changed canonical generations and can verify tracked evidence |
| Remove something safely | plans typed deletion scopes before mutation and binds confirmation to the exact plan |
| Use a desktop shell | provides Tauri + React import, Library search, verified evidence reading/cursor, and Archive/Midnight themes |

The point is not to make users operate the machinery. The point is to make sensitive local
transcription and research boringly dependable.

## Pick your doorway

- **[Getting started](getting-started.md)** for the source-build path and first transcript.
- **[Find things across the whole local library](library-discovery.md)** for grouped Library
  discovery, which now powers the desktop Library surface.
- **[Your notes should survive the machinery](research-notes.md)** for authoritative notes,
  tags, collections, and saved research intent. A dedicated desktop Research workspace is
  the next UI tranche.
- **[From search result to the exact evidence](evidence-navigation.md)** for verified
  canonical navigation and the current desktop evidence reader/cursor.
- **[Transcript time without calculator gymnastics](time-navigation.md)** for timeline and
  source-relative coordinate semantics.
- **[Give the anonymous speakers names](speaker-names.md)** for user-authored speaker labels.
- **[Semantic search, without the mystery box](semantic-search.md)** for local semantic/hybrid
  retrieval.
- **[Safe deletion and retention](architecture/safe-deletion-retention.md)** for custody-aware
  deletion.
- **[SECURITY.md](../SECURITY.md)** for the security boundary.
- **[Architecture](architecture/README.md)** for maintainers.
- **[Development docs](development/)** for testing, benchmarking, mutation qualification,
  frontend accessibility, and quality gates.

## The EchoFlow family portrait

```mermaid
flowchart LR
    A[Your recording] --> B[Local transcription]
    B --> C[Canonical transcript]
    C --> D[Lexical semantic hybrid search]
    D --> E[Verified evidence navigation]
    E --> F[Research authority]
    F --> D
    D --> G[Unified discovery]
    F --> G
    G --> H[Saved searches]
    C --> I[Typed custody planning]
    F --> I
    B --> I
    H --> J[Incremental refresh]
    J --> K[Desktop Library]
    E --> K
    F --> L[Next Desktop Research]

    classDef source fill:#F9D5E5,stroke:#7B2E52,stroke-width:2px,color:#22151B
    classDef process fill:#E8D9FF,stroke:#68469B,stroke-width:2px,color:#1F1630
    classDef evidence fill:#FFF0B8,stroke:#8A6B18,stroke-width:2px,color:#2C260F
    classDef view fill:#DDF5E3,stroke:#347A46,stroke-width:2px,color:#142719
    classDef inspect fill:#D8EEFF,stroke:#2E617B,stroke-width:2px,color:#12222A
    classDef stop fill:#FFD6D6,stroke:#9E3434,stroke-width:2px,color:#351616

    class A source
    class B process
    class C,E,F evidence
    class D,G,H,J view
    class I stop
    class K inspect
    class L process
```

Text fallback: canonical evidence feeds rebuildable search; search resolves back to verified
evidence; durable notes/tags/collections and saved searches remain authoritative human
knowledge; lifecycle and refresh reuse those identities; the current desktop Library uses
the same application contracts, and a dedicated Research surface is next.

## What belongs to you, and what can the raccoon rebuild? 🦝

| Data | What it is | Rebuildable? |
|---|---|---|
| Original recording | source evidence | **No** |
| Canonical transcript JSON | authoritative transcript evidence | **No** |
| Speaker display labels | user-authored knowledge | **No** |
| Research notes, tags, collections, anchors | user-authored knowledge | **No** |
| Saved searches | user-authored query intent | **No** |
| Remembered library/recording locations | machine-local app preference | **No, but reconcile on another machine** |
| TXT / SRT / WebVTT | publication views | Yes |
| Normalized/enhanced working audio | private processing material | Yes |
| Checkpoint workspace after publication | execution/recovery state | Usually disposable |
| Lexical/semantic search databases | derived search projections | Yes |
| Research query projection | derived view over durable research state | Yes |

If deleting a search projection destroys unique human-authored information, something has
gone very wrong.

## What comes next

Incremental refresh, durable locations, the Tauri/React shell, native import, grouped
Library discovery, and verified evidence reading/cursor are foundation.

The next sequence is:

1. **Research workspace UI** over existing authoritative notes/tags/collections/saved-search
   services.
2. **Tauri-owned local media playback** driven by verified source-relative coordinates.
3. **Desktop packaging and first run** for Windows, signed/notarized macOS, and deliberate
   Linux delivery.
4. **Backup, restore, and portable research export** while rebuilding disposable indexes.
5. **Semantic dependency/model qualification and representative-device release testing**.

See **[ROADMAP.md](../ROADMAP.md)** for detailed sequencing.

The editorial and Mermaid visual rules live in
**[documentation-style.md](documentation-style.md)**.

💃 **You are now allowed to leave the documentation lobby.**
