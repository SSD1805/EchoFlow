# Semantic search, without the mystery box ✨

EchoFlow can search transcripts in three different ways.

**Lexical search** looks for the words you typed. Search for `rent increase`, and it is
very good at finding passages containing those words.

**Semantic search** looks for passages with a related meaning. Search for:

```text
people struggling to afford housing
```

and it may help find:

```text
I was spending almost seventy percent of my pay on the apartment.
```

The vocabulary differs, but the idea is related.

**Hybrid search** lets exact terminology and conceptual similarity support each other.

```mermaid
flowchart LR
    A[Your query] --> B[Lexical BM25]
    A --> C[Semantic embeddings]
    B --> D[Hybrid rank fusion]
    C --> D
    B --> E[Transcript passages]
    C --> E
    D --> E
    E --> F[Verified canonical evidence]
```

Semantic search is optional. Lexical search remains the default and requires no semantic
model runtime.

## What is an embedding?

An embedding is a numeric representation of text used for comparison.

EchoFlow turns a search phrase and deterministic transcript passages into vectors, then
compares those vectors to find passages that sit near the query in the model's learned
semantic space.

An embedding is **not**:

- a replacement transcript;
- a generated summary;
- a hosted database requirement; or
- the only place your transcript exists.

It is derived search data.

```mermaid
flowchart TD
    A[Canonical transcript passage] --> B[Local embedding model]
    C[Search phrase] --> B
    B --> D[Numeric vectors]
    D --> E[Local similarity comparison]
    E --> F[Original canonical passage coordinates]
```

EchoFlow's current profile produces 384-number vectors. Those numbers are for the
computer. You are not expected to inspect them manually.

## What happens when semantic search is enabled?

EchoFlow builds a private, rebuildable semantic projection from canonical transcripts.

1. Adjacent canonical ASR segments are combined into deterministic search windows.
2. A local embedding model converts each window into a vector.
3. EchoFlow stores vectors in a private DuckDB semantic index.
4. Search queries are embedded locally with the same profile.
5. Hard constraints are applied before similarity ranking where possible.
6. Results point back to the canonical transcript segments that produced them.
7. `EvidenceLocator` re-verifies canonical bytes before exposing precise evidence.

Your original recording is not modified. Canonical transcript JSON remains authoritative
transcript evidence.

## Does transcript text leave my computer?

Not during semantic indexing or search in the current implementation.

EchoFlow's semantic provider loads from a **local model snapshot**. Model loading uses
local-only resolution with remote model code disabled.

Separate three questions:

### Searching or indexing transcripts

Local. Transcript passages are not sent to a hosted embedding API by this implementation.

### Obtaining a model

Potentially network-bearing. Downloading model weights from a provider uses the network.

### Using a model already present locally

Offline. EchoFlow accepts the local immutable snapshot and does not resolve a remote
repository while indexing/searching.

## Why Multilingual E5 Small?

The first qualified semantic profile is:

```text
intfloat/multilingual-e5-small
```

It offers multilingual retrieval, compact 384-dimensional vectors,
retrieval-specific query/passage instructions, and practical local inference compared
with much larger embedding families.

The important product decision is **not** that this exact model is sacred. One semantic
index generation must use one explicit reproducible profile.

> **The model is not sacred. The profile is.**

EchoFlow records model identity, immutable revision, dimensions, normalization, pooling,
distance metric, query/passage transforms, embedding schema, and chunking profile.

If the profile changes, the semantic projection is rebuilt rather than mixing incompatible
vector spaces.

## What can be rebuilt? 🦝

| Data | Role | Rebuildable? |
|---|---|---|
| Original recording | source evidence | **No** |
| Canonical transcript JSON | authoritative transcript evidence | **No** |
| Speaker labels, notes, tags, collections | user-authored knowledge | **No** |
| Future saved searches / curated result sets | user-authored knowledge | **No** |
| Lexical term statistics | search projection | Yes |
| Semantic chunks | derived retrieval windows | Yes |
| Embedding vectors | derived search projection | Yes |
| Research query projection | derived research acceleration | Yes |

If the semantic database disappears, rebuild it from canonical transcripts.

If a durable note disappears, that is data loss.

## Why are transcript passages grouped into chunks?

ASR segments are evidence coordinates, but some are tiny:

```text
Yeah.
```

Embedding each tiny segment independently can discard useful context. EchoFlow therefore
combines adjacent canonical segments into deterministic retrieval windows.

Those chunks carry the IDs/timestamps of their source segments and can be recreated later.
EchoFlow does not split one canonical ASR segment into invented evidence coordinates merely
to hit a preferred chunk size.

## What does hybrid search combine?

BM25 lexical scores and semantic similarity scores are different mathematical things.
EchoFlow does not pretend they share one universal “relevance percentage.”

Hybrid mode combines **rank positions** with reciprocal rank fusion (RRF). The deeper
contract lives in **[architecture/corpus-search.md](architecture/corpus-search.md)**.

## Research-aware semantic search

Durable research state can constrain semantic retrieval before vector scoring.

For example:

```bash
uv run echoflow library search \
  "people struggling to make rent" \
  --mode semantic \
  --tag methodology \
  --collection "Chapter 3"
```

`ResearchWorkspaceService` resolves human tag/collection names to durable IDs. The
rebuildable research projection maps those IDs to canonical evidence scope. Semantic
candidate selection then happens **inside that scope**.

The semantic adapter also keeps a derived relational `chunk_segments` mapping so it can
map canonical segment scope to eligible semantic chunks without scanning every chunk's
JSON metadata.

This is an important boundary: notes/tags/collections do not become embedding truth. They
are durable user-authored constraints over evidence.

## Using semantic search

Lexical search works without semantic support:

```bash
uv run echoflow library rebuild
uv run echoflow library search "housing insecurity"
```

The current semantic foundation expects a compatible Sentence Transformers runtime and a
local immutable Multilingual E5 Small snapshot.

Build semantic state:

```bash
uv run echoflow library embeddings build \
  /path/to/models--intfloat--multilingual-e5-small/snapshots/<revision> \
  --revision <revision>
```

Inspect the indexed profile:

```bash
uv run echoflow library embeddings
uv run echoflow library embeddings --json
```

Search by conceptual similarity:

```bash
uv run echoflow library search \
  "people struggling to make rent" \
  --mode semantic
```

Or combine lexical and semantic retrieval:

```bash
uv run echoflow library search \
  "people struggling to make rent" \
  --mode hybrid
```

## Why is semantic setup still an advanced path?

The locked project dependency graph does not yet include Sentence Transformers.

The current implementation proves the architecture and strict-local retrieval contract
without pretending dependency/model acquisition is already a qualified normal install.

A productization tranche still needs:

- an audited/locked semantic dependency extra;
- managed acquisition of the qualified embedding snapshot;
- disk/resource admission;
- private model-cache placement; and
- clean-wheel/platform qualification.

Lexical search stays available regardless.

## Provider interoperability without model roulette

The retrieval core is provider-agnostic through `EmbeddingProvider` and
`EmbeddingProfile` contracts.

Another local provider can be implemented without changing canonical transcripts, chunk
custody, semantic storage, hybrid ranking, research evidence scope, or public search
results.

EchoFlow does **not** expose “paste any model repository ID and pray” as ordinary CLI
configuration. Different models can disagree about dimensions, normalization, pooling,
query/passage instructions, and distance semantics.

Future interoperability should therefore be **qualified interoperability**: another
provider declares and validates its complete profile, then builds a fresh semantic
generation.

## What if a better model appears later?

Nothing about canonical transcript evidence or durable research state has to migrate.

```mermaid
flowchart LR
    A[Canonical transcripts] --> B[Embedding profile v1]
    A --> C[Embedding profile v2]
    B --> D[Old rebuildable vectors]
    C --> E[New rebuildable vectors]
```

Vectors are derived state. Rebuild them. Keep the evidence.

## What if I never turn semantic search on?

Then EchoFlow continues to use lexical search. Your transcripts remain canonical, your
research state remains durable, and BM25 remains local.

Semantic retrieval is an enhancement, not a tax every user must pay.

For exact implementation details, stale-state detection, vector storage, research
pre-filtering, provider validation, and RRF provenance, descend into
**[Evidence-first corpus search](architecture/corpus-search.md)**.
