# EchoFlow architecture

EchoFlow is organized around small capability boundaries rather than one inheritance
hierarchy or generic plugin framework. The composition root lives in
`src/echoflow/app/app_container.py` and uses Dependency Injector to wire concrete
local implementations.

## Start here

- [Processing capabilities](processing-capabilities.md) describes the current
  execution pipeline, capability ownership, recovery semantics, multilingual
  behavior, and deliberate product boundaries.
- [Media normalization and transcript timeline](media-and-timeline.md) explains what
  FFprobe inspection does, how audio streams are selected, how FFmpeg canonicalizes
  media, and exactly what transcript timestamps mean.
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
| `transcription` | Planning, normalization, segmentation, ASR, checkpoints, language attribution, assembly, exports |
| `workspace` | Private job paths and public artifact allocation |
| `benchmarking` | Privacy-minimized local execution measurement |
| `library` | Database-neutral port for rebuildable transcript indexing/search |

`runner` refers to the local compute environment available to the process; it is not
an orchestration/task runner. `media.probe` performs inspection, not transcoding.
Canonical audio normalization lives under the transcription execution boundary.

## Dependency conventions

- External/configuration/durable-data boundaries may use Pydantic where schema
  parsing and serialization are valuable.
- Small internal immutable domain values generally use frozen/slotted dataclasses.
- Services depend on narrow `Protocol` capabilities when substitution is real and
  useful for testing or multiple implementations.
- Structlog is isolated behind `core.observability.ILogger`; application services do
  not need to import Structlog directly.
- Canonical transcript/checkpoint files are authoritative. Search databases are
  derived and rebuildable.
- New frameworks, adapters, and abstraction layers require a concrete capability or
  invariant they protect; file count alone is not a reason to add a manager.
