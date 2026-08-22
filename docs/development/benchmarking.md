# Empirical benchmarking and calibration 📏

Scholion's resource estimates and relative strategy ranks are intentionally conservative
heuristics until real machines prove them right or wrong.

The benchmarking subsystem collects transcription evidence **without creating a second
transcription implementation**. The same measurement philosophy now extends to incremental
library refresh, unified discovery, research projection behavior, and desktop interaction.

> **Benchmarks describe what happened. A later reviewed policy change decides whether
> those observations justify different application behavior.**

## Quick start: transcription benchmark

ASR models must already be installed through normal model management. Benchmarking never
authorizes a hidden faster-whisper download.

```bash
uv run python -m scholion.benchmarking /path/to/recording.wav
uv run python -m scholion.benchmarking /path/to/recording.wav --json
uv run python -m scholion.benchmarking /path/to/recording.wav --resume JOB_ID
```

The harness is experimental. Once its schema and behavior survive representative-device
use, it may graduate into the primary `scholion` command surface.

## What are we measuring now?

There are three performance questions.

**Execution performance:** does a chosen transcription strategy fit the machine and
complete at acceptable cost?

**Workspace performance:** does a growing evidence library remain interactive while it is
incrementally refreshed, searched, research-filtered, and projected?

**Desktop performance:** do native import, Library discovery, and verified evidence reading
remain responsive without bypassing the same application services used in production?

Neither should be tuned from one heroic laptop run.

```mermaid
flowchart LR
    A[Conservative prediction] --> B[Representative workload]
    B --> C[Measured result]
    C --> D[Compare expected and observed]
    D --> E[Reviewed calibration or optimization]
    E --> A

    classDef inspect fill:#D8EEFF,stroke:#2E617B,stroke-width:2px,color:#12222A
    classDef process fill:#E8D9FF,stroke:#68469B,stroke-width:2px,color:#1F1630
    classDef evidence fill:#FFF0B8,stroke:#8A6B18,stroke-width:2px,color:#2C260F
    classDef view fill:#DDF5E3,stroke:#347A46,stroke-width:2px,color:#142719

    class A inspect
    class B,C evidence
    class D process
    class E view
```

Text fallback: conservative policy is exercised on representative workloads; observed
results are compared with prediction; only reviewed evidence changes policy.

## What one transcription benchmark records

A current report describes one execution attempt and includes:

- Scholion and Python versions;
- path-minimized source provenance;
- process-visible resources and selected execution policy;
- path-free managed engine/model/revision and execution target;
- decoder, enhancement, segmentation, and resource-estimate contracts;
- planning, execution, and total wall-clock duration;
- whole-run and execution-only real-time factors;
- sampled process-tree RSS and CPU use;
- aggregate named execution-stage durations/failure counts;
- work totals/restored/completed counts when available;
- canonical transcript artifact size after publication; and
- observed peak memory relative to the planner estimate.

Repeated stages are named aggregates rather than fixed columns. Future capabilities can
add stages without redesigning the report schema.

## Privacy boundary 🔐

Benchmarking does not transmit reports. Scholion has no benchmark telemetry.

Reports are user-owned JSON files in the selected output directory. They intentionally
omit source paths/filenames, model-cache paths, transcript text, research-note text, and
exception messages unless a future benchmark explicitly requires and documents such
content.

A retained source digest can still be linkable if another party has the same recording,
so a report from sensitive media is not automatically anonymous.

## Interruption and resume

Ctrl+C and ordinary Python-level failures persist a partial benchmark report when
finalization can run. The transcription checkpoint contract remains authoritative for
recovery.

Hard kills, power loss, kernel termination, or machine crashes cannot run benchmark
finalization code, so a final benchmark report is not promised for those cases.

## Qualification layers

### Deterministic tests

Protect measurement semantics, privacy minimization, failure preservation, path/capability
boundaries, and invalid-value rejection.

### Cross-platform CI

Linux, macOS, and Windows CI exercise static gates, Python tests, frontend build/type/audit,
Playwright/axe, packaging, clean-wheel behavior, file handling, native media tools, and CLI
contracts.

Hosted-runner timing is **not calibration truth**. Runner generations, virtualization,
caches, and neighboring workloads can change independently of Scholion.

### Representative real devices

The physical matrix should include at least:

- an 8 GB Windows consumer machine;
- a 16 GB commodity Windows/Linux machine;
- Apple Silicon;
- a discrete-GPU laptop; and
- a larger 32/64 GB workstation.

Hold relevant source bytes, model revision, strategy/profile, corpus generation, and query
set constant for comparisons. Record cold/warm state and prefer repeated trials plus
medians/spread over one fastest result.

## Enhancement qualification

Noise suppression should be qualified by **transcription outcome and total cost**, not by
whether the derivative sounds nicer.

Compare enhancement off/on under the same source/model/revision/strategy. Where reference
transcripts exist, compare WER/CER alongside wall-clock time, real-time factor, CPU/RAM,
accelerator pressure, private disk overhead, checkpoint behavior, and failures.

The current FFmpeg `afftdn` provider is a deterministic condition, not a claim of universal
benefit.

## Incremental corpus refresh

Incremental refresh is implemented. Full `library rebuild` remains the repair/recovery
comparison baseline.

Measure:

- no-op refresh;
- one new transcript;
- one changed canonical generation;
- one removed transcript;
- batches of additions/changes/removals;
- `--verify` versus cheap refresh; and
- full rebuild of the same corpus.

The goal is to prove normal corpus growth avoids unnecessary work while preserving
canonical generation identity and deterministic recovery.

## Search and unified discovery

Unified discovery is implemented across transcript evidence, notes, tags, and collections.
Use fixed query sets over representative corpora and measure cold/warm behavior for:

- lexical BM25;
- semantic exact-scan;
- hybrid RRF;
- document/language/speaker constraints;
- tag/collection/note-text/with-notes research constraints;
- notebook-only note queries; and
- grouped unified discovery.

Measure latency distributions, not only the best run. The first goal is interactive local
use, not a marketing benchmark.

## Research projection

Measure one-note mutation plus catch-up, edit/tag/collection/delete sequences, bounded
batches, idempotent replay, restart catch-up, journal-gap rebuild, and projection size
relative to authoritative SQLite state.

SQLite remains authoritative and DuckDB rebuildable. A faster benchmark is not permission
to bypass the custody model.

## Desktop responsiveness

The thin desktop exists now. Current end-to-end measurements should include:

- opening the app/library;
- import selection and remembered-location refresh;
- search submission to stable grouped results;
- opening verified evidence context; and
- moving the evidence cursor among canonical words.

After the next tranche lands, add Research-workspace browse/edit/save-search timings. Once
Tauri media playback exists, add source seek/playback responsiveness.

The UI should be measured through the same Python application services and native
capability boundaries it uses in production. Do not create benchmark-only fast paths.

## Suggested corpus shapes

Synthetic corpora are useful for repeatability and should be paired with real dogfood where
privacy permits:

```text
small      10 transcripts / 1,000 segments / 100 notes
medium    100 transcripts / 10,000 segments / 3,000 notes
large   1,000 transcripts / 100,000 segments / 30,000 notes
```

Those are **qualification shapes, not supported-limit claims**.

## How measurements become policy

The harness is for **measurement first, self-tuning never by accident**.

Only a separate reviewed change should alter safety margins, hardware classes, indexing
strategies, automatic preprocessing heuristics, or approximate retrieval structures based
on collected evidence.

Benchmark reports say what happened. Policy changes explain why that evidence justifies a
different decision.

That separation keeps calibration auditable and prevents the planner from becoming a
self-modifying raccoon with a stopwatch. 🦝
