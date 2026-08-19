# EchoFlow architecture 🔧

Welcome to the maintenance hatch.

The user-facing docs explain what EchoFlow does. These pages explain **why the boundaries
exist, what each capability owns, what it refuses to own, and which invariants must
survive refactors**.

If you are trying to transcribe a file rather than maintain the system, use
**[Getting started](../getting-started.md)**.

## The shape of the system

EchoFlow is composed from narrow local capabilities in
`src/echoflow/app/app_container.py`. The through-line is custody: source evidence,
canonical transcript truth, private execution state, rebuildable projections, and durable
human knowledge deliberately do not share deletion or recovery semantics.

![EchoFlow system architecture](../diagrams/system-architecture.svg)

<details>
<summary>Mermaid source</summary>

```mermaid
flowchart LR
    A[Source media] --> B[Media and resource inspection]
    B --> C[Immutable local plan]
    C --> D[Transcription and checkpoints]
    D --> E[Canonical transcript JSON]
    E --> F[Derived exports]
    E --> G[DuckDB lexical and semantic projections]
    G --> H[Ranked passages]
    E --> I[Verified evidence navigation]
    H --> I
    I --> J[SQLite research authority]
    J --> K[Deterministic projector]
    K --> L[DuckDB research projection]
    L --> H
    J --> M[Saved searches]
    J --> N[ResearchWorkspaceService]
    I --> N
    M --> N
    N --> O[Unified discovery and navigation]
    E --> P[LibraryCustodyService]
    G --> P
    J --> P
    D --> P
    P --> Q[Plan-bound deletion and retention]
```

</details>

Text fallback: canonical JSON is evidence; DuckDB ranks rebuildable views; canonical
navigation verifies evidence; SQLite owns human research; `ResearchWorkspaceService`
composes research interactions; `LibraryCustodyService` plans and applies deletion or
private-state retention without merging those ownership classes.

## Where to look

| Page | What question it answers |
|---|---|
| [Processing capabilities](processing-capabilities.md) | How does the local transcription/research system fit together? |
| [Adaptive heterogeneous execution](adaptive-heterogeneous-execution.md) | How does EchoFlow decide what this machine can safely run? |
| [Media and timeline](media-and-timeline.md) | Which source/stream did we use, and what do timestamps mean? |
| [Word-level timestamp alignment](word-alignment.md) | How do engine timings become source-relative evidence? |
| [Local model management](model-management.md) | Which model revision is allowed to execute, and how did it get here? |
| [Speech enhancement](speech-enhancement.md) | How can preprocessing affect ASR without becoming source truth? |
| [Anonymous speaker diarization](diarization.md) | How are speaker turns represented without pretending anonymous labels are identities? |
| [Corpus search](corpus-search.md) | How do lexical/semantic/hybrid ranking and verified navigation stay separate? |
| [Durable research state](research-state.md) | Why does SQLite own human research while DuckDB owns rebuildable acceleration? |
| [Library lifecycle](library-lifecycle.md) | Where does canonical JSON live, what does rebuild rescan, and which state is durable? |
| [Safe deletion and retention](safe-deletion-retention.md) | What exactly can be deleted, what is preserved, and how is destructive intent confirmed? |
| [ROADMAP](../../ROADMAP.md) | What is implemented, what is next, and what remains research? |
| [SECURITY](../../SECURITY.md) | What does the security boundary actually claim? |

## Package map

| Package | Responsibility |
|---|---|
| `app` | Dependency-injection composition root |
| `core` | Configuration, errors, observability, health, measurements |
| `interfaces` | Local filesystem/storage adapters and private-storage policy |
| `media` | Read-only source inspection and deterministic audio-stream selection |
| `runner` | Process-visible CPU/memory inspection and execution-budget policy |
| `model_management` | Model inventory, acquisition, verification, provenance, removal |
| `transcription` | Planning, normalization, enhancement, segmentation, ASR, checkpoints, language, alignment, diarization, assembly, exports |
| `workspace` | Private job paths and public artifact allocation |
| `benchmarking` | Privacy-minimized local execution measurement |
| `library` | Retrieval, evidence navigation, research authority/projections, saved searches, discovery, and typed custody/deletion/retention policy |

## Capability boundaries

EchoFlow prefers a small object with one clear job over a universal manager.

The search/research/custody area deliberately separates responsibilities:

1. `TranscriptLibraryService` discovers and ranks rebuildable transcript passages.
2. `EvidenceLocator` verifies ranked passages against canonical evidence.
3. `SpeakerLabelService` owns durable recording-scoped human display names without
   rewriting diarization evidence.
4. `ResearchStateStore` owns durable notes, tags, collections, and exact evidence anchors.
5. `ResearchStateProjector` converges authoritative SQLite state into a disposable DuckDB
   research projection.
6. `ResearchProjectionIndex` owns fast derived research constraints and summaries.
7. `WorkspaceMetadataStore` owns durable saved-search intent and computes disposable
   navigation views.
8. `ResearchWorkspaceService` composes those capabilities for CLI and future GUI adapters.
9. `LibraryCustodyService` owns typed deletion planning/execution and age-based private
   execution-state retention. It does not become a second research or transcript authority.

That split should survive the GUI. Presentation convenience is not permission to merge
custody boundaries.

## Why SQLite and DuckDB both exist

SQLite is authoritative for irreplaceable, frequently mutated user research. DuckDB is
used for rebuildable analytical/query projections. There is one authority, not two
masters.

```text
SQLite authority
      |
      | monotonic transactional change journal
      v
ResearchStateProjector
      |
      v
DuckDB research projection
```

If a research projection disappears, rebuild it. If SQLite user state disappears, unique
human work is lost. That asymmetry is intentional.

Saved searches live in authoritative SQLite because they are authored intent. Their
runtime evidence scope does not. Replaying a saved search re-resolves the current corpus
and current research relationships.

## The custody rules 🦝

These rules are load-bearing:

1. **Original media is source evidence and read-only during normal processing.** Explicit
   source deletion is a separate provenance-checked operation, never an implied cleanup.
2. **Canonical transcript JSON is authoritative transcript evidence.** It is deleted only
   through an explicit plan-bound canonical scope.
3. **Managed model manifests describe verified local execution dependencies.**
4. **Lexical, semantic, and research DuckDB databases are rebuildable projections.**
5. **Speaker labels, notes, tags, collections, and saved searches are human-authored
   authority and do not inherit index deletion semantics.**
6. **Research joins include canonical generation identity, not a friendly segment ID
   alone.**
7. **Precise navigation resolves to verified canonical evidence rather than trusting a
   stale search projection.**
8. **Research filters apply before ranking/scoring when they define eligible evidence.**
9. **Saved searches persist typed query intent, not a frozen derived evidence scope.**
10. **Canonical deletion preserves attached notes and document-scoped saved searches unless
    their own destructive scopes are explicitly selected.**
11. **Age-based retention can delete only private job workspaces.** It preserves canonical
    evidence, human research, and lightweight lifecycle manifests.
12. **EchoFlow does not claim secure erasure it cannot prove.**

Search infrastructure may disappear. User-authored knowledge may not disappear by
accident.

## Current application seams

Unified discovery, saved searches, frequent/recent navigation, and research interactions
compose through `ResearchWorkspaceService`.

Custody-sensitive operations compose separately through `LibraryCustodyService`:

```bash
echoflow library delete TRANSCRIPT_ID --scope library-view
echoflow library delete TRANSCRIPT_ID --scope canonical-transcript
echoflow library retention --execution-days 30
```

Deletion and retention are dry-run by default. Applying a reviewed operation requires the
plan-bound token returned by the dry run. The token binds the canonical generation,
effective scopes, concrete actions, and relevant preserved note/saved-search dependencies,
so a changed plan cannot reuse an old confirmation.

The next backend seam is **incremental library refresh**. Normal corpus growth should
upsert/remove changed transcript generations automatically; full `library rebuild` should
remain the repair lever. The first thin GUI should then consume the same search, evidence,
research, saved-search, custody, and refresh services instead of inventing parallel rules.

## New abstraction test

Before adding a manager, framework, registry, adapter hierarchy, generalized plugin
system, or database wrapper, ask which concrete capability or invariant it protects.

File count is not an architectural problem. Repeated policy, unclear ownership, and
unprovable invariants are.

## Documentation contract

Architecture pages should provide a plain-English doorway, a structural model when useful,
the exact implementation contract, ownership/failure semantics, and explicit current
limits or future seams.

See **[documentation-style.md](../documentation-style.md)** for the editorial contract.
