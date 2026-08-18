# Getting started with EchoFlow

EchoFlow keeps recording, transcription, and search work on your computer. The original
recording is treated as read-only input. The main transcript is portable canonical JSON;
TXT/SRT/VTT and search databases are derived views that can be regenerated.

## 1. Install the source build

EchoFlow is pre-production and does not publish end-user installers yet.

```bash
git clone https://github.com/SSD1805/EchoFlow.git
cd EchoFlow
uv sync --locked --extra transcription
```

Initialize private application directories and inspect the machine:

```bash
uv run echoflow init
uv run echoflow doctor
uv run echoflow runner
```

## 2. See which transcription model fits

```bash
uv run echoflow models recommend
```

Install the recommended managed model before transcription:

```bash
uv run echoflow models install small
```

Model installation is explicit because it is a network-bearing action. Transcription
itself does not silently download ASR weights.

## 3. Transcribe a recording

Inspect the plan without starting recognition:

```bash
uv run echoflow transcribe interview.m4a --dry-run
```

Then transcribe:

```bash
uv run echoflow transcribe interview.m4a
```

Optional derived exports:

```bash
uv run echoflow transcribe interview.m4a --export txt --export srt
```

## 4. Search completed transcripts

Build the private lexical library:

```bash
uv run echoflow library rebuild
```

Search it:

```bash
uv run echoflow library search "housing insecurity"
```

Filter by available transcript evidence:

```bash
uv run echoflow library search \
  "rent increase" \
  --speaker speaker-02 \
  --language en
```

Inspect where one transcript came from:

```bash
uv run echoflow library show JOB_ID
```

## What EchoFlow stores

```mermaid
flowchart LR
    A[🎙️ Your recording] -->|read only| B[EchoFlow processing]
    B --> C[Private temporary state]
    B --> D[📜 Canonical transcript JSON]
    D --> E[TXT / SRT / VTT]
    D --> F[Private lexical index]
    D --> G[✨ Optional private semantic index]
    A -. never overwritten .-> A
```

The important distinction is ownership:

- **Your recording**: source evidence, never overwritten by EchoFlow.
- **Canonical transcript JSON**: authoritative transcript artifact.
- **TXT/SRT/VTT**: derived publication formats.
- **DuckDB indexes**: private rebuildable search state.

Deleting a search index should not delete transcript evidence.

## 5. Optional semantic and hybrid search

Lexical search finds the words you typed. Semantic search can also find passages with a
similar meaning, even when they use different wording.

For example, a search for:

```text
people struggling to afford housing
```

may help surface a transcript passage such as:

```text
I was spending almost seventy percent of my pay on the apartment.
```

The words differ, but the idea is related.

EchoFlow does this with a **local sentence-embedding model**. The model converts your
query and transcript passages into small numeric vectors that can be compared for
similarity. EchoFlow still returns the original transcript passage with timestamps,
speaker/language evidence, and canonical-source provenance.

```mermaid
flowchart LR
    Q[🔎 Search phrase] --> L[Exact words<br/>BM25]
    Q --> S[Related meaning<br/>local embeddings]
    L --> H[💃 Hybrid ranking]
    S --> H
    H --> E[📜 Evidence-bearing passages]
```

Semantic search is **optional**. Lexical search remains the default and has no semantic
model requirement.

### Privacy boundary

Semantic indexing and search run locally. EchoFlow loads the embedding model from a
local immutable snapshot and does not send transcript passages to a hosted embedding
API.

Obtaining a model is a separate concern. Downloading a model from a provider such as
Hugging Face may require network access, but building/searching the semantic index from
a model already present locally does not.

The repository does not bundle model weights.

### Why Multilingual E5 Small?

EchoFlow's first qualified semantic profile is
`intfloat/multilingual-e5-small`.

It is a conservative local default because it gives EchoFlow multilingual retrieval,
compact 384-dimensional vectors, explicit retrieval-oriented query/passage semantics,
and a comparatively lightweight local execution profile.

The model is not treated as permanent product truth. EchoFlow records an immutable
embedding profile so a future model can rebuild the derived semantic projection without
changing canonical transcripts.

The locked project dependency graph does not yet include Sentence Transformers. Until a
semantic dependency tranche is resolved and audited, this capability requires an
environment that already supplies a compatible `sentence_transformers` runtime and a
local immutable Multilingual E5 Small snapshot.

Build the private semantic index:

```bash
uv run echoflow library embeddings build \
  /path/to/models--intfloat--multilingual-e5-small/snapshots/<revision> \
  --revision <revision>
```

Inspect what was indexed:

```bash
uv run echoflow library embeddings
```

Semantic retrieval:

```bash
uv run echoflow library search \
  "people struggling to make rent" \
  --mode semantic
```

Hybrid lexical + semantic retrieval:

```bash
uv run echoflow library search \
  "people struggling to make rent" \
  --mode hybrid
```

For the plain-language explanation of embeddings, privacy, model custody, and future
provider interoperability, see [`semantic-search.md`](semantic-search.md).

## How search results stay tied to evidence

```mermaid
flowchart TD
    Q[SearchQuery] --> L[BM25]
    Q --> S[Optional multilingual E5]
    L --> R[Ranked lexical evidence]
    S --> V[Ranked semantic chunks]
    R --> H[Optional RRF hybrid rank]
    V --> H
    H --> E[Segments + timestamps + speaker/language + canonical source]
```

Semantic chunks are retrieval windows, not replacement transcript text. Each window
points to the exact canonical segment IDs and source-relative time range from which it
was built.

For the full architecture, see
[`architecture/corpus-search.md`](architecture/corpus-search.md).
