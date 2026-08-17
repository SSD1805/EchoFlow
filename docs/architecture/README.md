# EchoFlow architecture

EchoFlow is organized around small capability boundaries rather than one inheritance
hierarchy or generic plugin framework. The composition root lives in
`src/echoflow/app/app_container.py` and uses Dependency Injector to wire concrete
local implementations.

For a user-oriented path before opening the maintenance hatch, start with
[`docs/getting-started.md`](../getting-started.md).

## Start here

- [Processing capabilities](processing-capabilities.md) describes the current
  execution pipeline, capability ownership, recovery semantics, multilingual
  behavior, and deliberate product boundaries.
- [Media normalization and transcript timeline](media-and-timeline.md) explains what
  FFprobe inspection does, how audio streams are selected, how FFmpeg canonicalizes
  media, and exactly what transcript timestamps mean.
- [Local model management](model-management.md) defines explicit model acquisition,
  private manifest custody, local revalidation, immutable revision pinning, and the
  rule that ASR execution never downloads models implicitly.
- [Local speech enhancement](speech-enhancement.md) defines optional deterministic
  noise suppression, private derived audio, timeline preservation, provenance, and the
  raw-audio boundary retained for diarization.
- [Evidence-first corpus search](corpus-search.md) defines canonical-vs-derived
  ownership, BM25, deterministic chunks, exact dense retrieval, multilingual-E5
  provenance, stale-index detection, and hybrid RRF ranking.
- [`ROADMAP.md`](../../ROADMAP.md) separates implemented foundation from near-term
  product work and later research.
- [`SECURITY.md`](../../SECURITY.md) documents the supported security/privacy threat
  boundary and the claims EchoFlow intentionally does not make.

## Package map

| Package | Responsibility |
|---|---|
| `app` | Dependency-injection composition root |
| `core` | Configuration, errors, observability, health, measurements |
| `interfaces` | Local filesystem/storage adapters and private-storage policy |
| `media` | Read-only source inspection and deterministic audio-stream selection |
| `runner` | Process-visible CPU/memory inspection and execution-budget policy |
| `model_management` | Explicit local model inventory, acquisition, verification, provenance, and removal |
| `transcription` | Planning, normalization, optional enhancement, segmentation, ASR, checkpoints, language attribution, diarization, assembly, exports |
| `workspace` | Private job paths and public artifact allocation |
| `benchmarking` | Privacy-minimized local execution measurement |
| `library` | Evidence-first lexical/semantic retrieval over rebuildable transcript projections |

`runner` refers to the local compute environment available to the process; it is not
an orchestration/task runner. `media.probe` performs inspection, not transcoding.
Canonical audio normalization and optional noise suppression live under the
transcription execution boundary.

## Dependency conventions

- External/configuration/durable-data boundaries may use Pydantic where schema
  parsing and serialization are valuable.
- Small internal immutable domain values generally use frozen/slotted dataclasses.
- Services depend on narrow `Protocol` capabilities when substitution is real and
  useful for testing or multiple implementations.
- Structlog is isolated behind `core.observability.ILogger`; application services do
  not need to import Structlog directly.
- Canonical transcript/checkpoint files are authoritative. Model manifests describe
  execution dependencies. Search databases are derived and rebuildable.
- User-authored notes/tags/collections must not share the deletion semantics of
  rebuildable lexical or semantic indexes.
- New frameworks, adapters, and abstraction layers require a concrete capability or
  invariant they protect; file count alone is not a reason to add a manager.
