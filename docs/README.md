# Welcome to EchoFlow 🦝✨

EchoFlow is a **local-first workspace for recorded evidence**.

It can inspect a recording, choose a safe way to run on the computer you actually have,
transcribe locally, survive interruptions, preserve provenance, enrich the transcript,
and help you find the important bit again later.

You do **not** need to understand CUDA, DuckDB, BM25, vector spaces, immutable model
revisions, or why a raccoon has been granted library privileges to use the product.
Those details exist because somebody has to care about them. EchoFlow would like that
somebody to be EchoFlow.

> **The short version:** your recording stays yours, the canonical transcript remains
> inspectable evidence, and most of the machinery EchoFlow builds around it can be
> thrown away and rebuilt.

🧜‍♀️

## What can EchoFlow do today?

EchoFlow is still pre-production, but the backend is no longer a toy transcription
script. The current foundation already covers the full local journey from media to a
searchable evidence corpus.

| You want to… | EchoFlow currently… |
|---|---|
| Transcribe a recording privately | runs faster-whisper locally from a verified managed model |
| Avoid melting a smaller laptop | inspects process-visible CPU, RAM, and compatible acceleration before choosing a strategy |
| Use a GPU when it is *actually* usable | separates physical hardware discovery from engine/runtime capability instead of assuming “GPU visible = GPU works” |
| Survive an interruption | checkpoints completed work and validates the original contract on resume |
| Keep the original recording intact | treats source media as read-only evidence and writes processing artifacts separately |
| Handle video files | deterministically selects an audio stream and transcribes the audio-bearing source |
| Clean up a noisy recording | optionally applies deterministic local noise suppression with provenance and timeline checks |
| Work with multiple languages | supports multilingual decoding plus conservative local language attribution |
| Distinguish speakers | has optional anonymous recording-scoped diarization, currently held behind a dependency security gate |
| Publish useful transcript formats | produces canonical JSON plus rebuildable TXT, SRT, and WebVTT views |
| Find an exact phrase later | builds a private local lexical/BM25 transcript library |
| Find an idea even when the wording changed | supports optional local semantic retrieval |
| Get the best of both search styles | combines lexical and semantic results with inspectable reciprocal-rank fusion |
| Verify where a result came from | carries timestamps, speakers/languages, hashes, canonical coordinates, and retrieval provenance |

That is a lot of machinery. The point is not to make you operate the machinery. The
point is to make sensitive local transcription feel boringly dependable.

## Pick your doorway

### 💃 I just want to use the thing

Start with **[Getting started](getting-started.md)**.

It walks through installation, model setup, transcription, resume, exports, and search
without requiring an architecture degree.

### 🔎 I want to search my transcripts

Read **[Semantic search, without the mystery box](semantic-search.md)** for the
plain-language explanation of lexical, semantic, and hybrid search, including what an
embedding is and what stays local.

### 🔐 I care about privacy and security boundaries

Read **[SECURITY.md](../SECURITY.md)**. That document intentionally uses less glitter.
Security claims should be boring enough to audit.

### 🔧 I am maintaining or extending EchoFlow

Open the **[architecture maintenance hatch](architecture/README.md)**.

Those documents contain the exact contracts for media handling, execution strategy,
model custody, checkpoints, diarization, enhancement, and transcript retrieval.

### 🧪 I am here to break things professionally

The [development docs](development/) cover benchmarking, test design, bisect strategy,
and targeted mutation qualification.

---

## The EchoFlow family portrait

The product makes more sense when its capabilities are grouped by the job they perform.

```mermaid
flowchart LR
    U[Your recording] --> C[Custodian\nsource + provenance]
    C --> H[Hardware sommelier\nfit work to this machine]
    H --> T[Transcription engine room\nASR + checkpoints + enrichment]
    T --> A[Archivist\ncanonical transcript + exports]
    A --> L[Librarian\nlexical + semantic + hybrid search]
    L --> E[Evidence you can inspect again]

    classDef source fill:#F9D5E5,stroke:#7B2E52,stroke-width:2px,color:#22151B
    classDef compute fill:#D8EEFF,stroke:#2E617B,stroke-width:2px,color:#12222A
    classDef process fill:#E8D9FF,stroke:#68469B,stroke-width:2px,color:#1F1630
    classDef evidence fill:#FFF0B8,stroke:#8A6B18,stroke-width:2px,color:#2C260F
    classDef result fill:#DDF5E3,stroke:#347A46,stroke-width:2px,color:#142719

    class U,C source
    class H compute
    class T process
    class A evidence
    class L,E result
```

The shared rule across the whole family is simple:

**Do complicated work locally. Keep the evidence understandable, portable, and owned by
the user.**

## What belongs to you, and what can the raccoon rebuild? 🦝

EchoFlow uses different custody rules for different kinds of data.

| Data | What it is | Rebuildable? |
|---|---|---|
| Original recording | source evidence | **No** |
| Canonical transcript JSON | authoritative transcript artifact | **No** |
| Future notes, tags, labels, annotations | user-authored knowledge | **No** |
| TXT / SRT / WebVTT | publication views | Yes |
| Normalized/enhanced working audio | private processing material | Yes |
| Checkpoint machinery after successful publication | execution/recovery state | Usually disposable after completion |
| Lexical search database | derived search projection | Yes |
| Semantic chunks and vectors | derived search projection | Yes |

If deleting a search index destroys unique user-authored information, something has gone
very wrong.

## Why the docs have different personalities

Not every reader needs the same depth.

- **Welcome/onboarding docs** explain the product in ordinary language and may contain
  raccoons, mermaids, dancing women, and other signs of life.
- **Feature guides** explain *why* a capability exists before exposing implementation
  detail.
- **Architecture docs** keep exact contracts, but each should still provide a
  plain-English doorway and useful diagrams.
- **Security, audit, schema, and command contracts** prioritize unambiguous language over
  jokes.

The detailed editorial rules live in **[documentation-style.md](documentation-style.md)**.

## What is next?

The backend is now broad enough that the next work is less about inventing a
transcription engine and more about making evidence easier to navigate and the product
easier to enter.

The likely evidence-navigation sequence is:

1. **word/timestamp alignment**, so highlighting, speaker attribution, annotations, and
   jump-to-audio can use finer coordinates;
2. **original-media timecode and capture-time provenance**, so source-relative seconds
   can coexist with container/SMPTE/device time when the source provides it;
3. **better speaker UX**, including user-assigned display labels for anonymous speakers
   and better presentation of overlap; and
4. **later, source separation for overlapping speech**, only after the simpler temporal
   evidence model is strong enough to justify the additional compute and uncertainty.

Packaging, installers, and a thin graphical interface remain important for ordinary
non-developer use. The architecture is already intentionally arranged so those can sit
on top of the same services rather than creating a second pipeline.

For the fuller sequencing and research boundary, see **[ROADMAP.md](../ROADMAP.md)**.

💃 **You are now allowed to leave the documentation lobby.**