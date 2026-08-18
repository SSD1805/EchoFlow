# Empirical benchmarking and calibration 📏

EchoFlow's resource estimates and relative strategy ranks are intentionally conservative
heuristics until real machines prove them right or wrong.

The existing benchmarking subsystem collects transcription evidence **without creating a
second transcription implementation**. The next performance work extends the same
measurement philosophy to the library and research workspace rather than adding policy by
vibes.

> **Benchmarks describe what happened. A later reviewed policy change decides whether
> those observations justify different application behavior.**

## Quick start: transcription benchmark

ASR models must already be installed through normal model management. Benchmarking never
authorizes a hidden faster-whisper download.

```bash
uv run python -m echoflow.benchmarking /path/to/recording.wav
uv run python -m echoflow.benchmarking /path/to/recording.wav --json
```

Measure a resumed attempt separately:

```bash
uv run python -m echoflow.benchmarking /path/to/recording.wav --resume JOB_ID
```

The harness is experimental. Once its schema and behavior survive real-device use, it may
graduate into the primary `echoflow` command surface.

## What problem are we trying to solve?

There are now two performance questions.

**Execution performance:** does a chosen transcription strategy fit the machine and
complete at an acceptable cost?

**Workspace performance:** does a growing local evidence library remain interactive when
it is refreshed, searched, filtered through research state, projected, and eventually
used through a GUI?

Neither should be tuned from one heroic laptop run.

```mermaid
flowchart LR
    A[Conservative prediction] --> B[Representative workload]
    B --> C[Measured result]
    C --> D[Compare expected and observed]
    D --> E[Reviewed calibration or optimization]
    E --> A
```

## What one transcription benchmark records

A current report describes one execution attempt and includes:

- EchoFlow and Python versions;
- path-minimized source provenance: SHA-256, size, modification timestamp, container,
  duration, and selected audio stream;
- process-visible runner resources and selected execution policy;
- path-free managed engine/model/revision and execution target;
- decoder, enhancement, segmentation, and resource-estimate contracts;
- planning, execution, and total wall-clock duration;
- whole-run and execution-only real-time factors;
- sampled process-tree RSS and CPU use;
- aggregate named execution-stage durations/failure counts;
- segment totals/restored/completed counts when available;
- canonical transcript artifact size after successful publication; and
- the ratio between observed peak process-tree RSS and the planner's peak-memory estimate.

Repeated stages are named aggregates rather than fixed columns. Future capabilities can
add stages without redesigning the report schema.

CPU percentages may exceed 100% because sampled process-tree CPU is summed across cores.
RSS is also summed across the process tree and may conservatively double-count shared
pages. These are comparative measurements, not perfect OS accounting.

## Privacy boundary 🔐

Benchmarking does not transmit reports. EchoFlow has no benchmark telemetry.

Reports are user-owned JSON files in the selected output directory. They intentionally
omit source paths/filenames, model-cache paths, transcript text, research-note text, and
exception messages unless a future benchmark explicitly requires and documents such
content.

They retain source digest and enough provenance to compare equivalent runs. A source
digest can still be linkable if another party has the same recording, so a benchmark
report from sensitive media is not automatically anonymous.

Public sharing should use synthetic/redistributable media or a deliberately shareable
report format with reduced provenance.

## Interruption and resume

Ctrl+C and ordinary Python-level failures persist a partial transcription benchmark report
before exit when finalization can run.

The transcription checkpoint contract remains authoritative for recovery. A later
`--resume` benchmark measures the resumed attempt without redefining resume semantics.

Hard kills, power loss, kernel termination, or machine crashes cannot run benchmark
finalization code, so a final benchmark report is not promised for those cases. Durable
checkpoint/lifecycle state remains the recovery evidence.

## Three qualification layers

### 1. Deterministic unit and contract tests

These prove the measurement machinery itself behaves correctly: observers do not change
product semantics, repeated stages aggregate, failures do not swallow primary errors,
reports respect privacy minimization, and invalid report values fail closed.

### 2. Cross-platform CI

Linux, macOS, and Windows GitHub Actions exercise tests, packaging, clean-wheel behavior,
file handling, native media tools, and CLI contracts.

Hosted-runner timing is **not calibration truth**. Runner generations, virtualization,
neighboring workloads, caches, and infrastructure can change outside the project.

### 3. Representative real-device runs

The physical matrix should include at least:

- an 8 GB Windows consumer machine;
- a 16 GB commodity Windows/Linux machine;
- Apple Silicon;
- a discrete-GPU laptop; and
- a larger 32/64 GB workstation.

For comparisons, hold constant relevant input bytes, EchoFlow version, model revision,
strategy/profile, enhancement condition, corpus generation, and query set. Record
cold/warm state and prefer repeated trials plus medians/spread over one fastest result.

Thermal throttling, battery mode, background applications, storage speed, and OS updates
are legitimate consumer conditions. Record them when known rather than pretending they do
not exist.

## Raw ASR versus enhancement + ASR

Noise suppression should be qualified by **transcription outcome and total cost**, not
whether the processed file sounds nicer.

Use matched conditions with enhancement off/on under the same managed model/revision and
strategy. Where reference transcripts exist, compare WER and, where useful, CER.

Also compare total/stage wall-clock time, real-time factor, CPU/RAM pressure, accelerator
impact, private disk overhead, checkpoint/resume behavior, and failures across realistic
acoustic conditions.

The current FFmpeg `afftdn` provider is a fixed deterministic condition. Its existence is
not a claim that it improves every recording.

## Library and research-workspace qualification

The merged research workspace creates a second measurement surface. The important tests
are user-shaped workloads, not raw database microbenchmarks.

### Corpus refresh

Today `library rebuild` is an explicit full-repair path. The roadmap proposes incremental
refresh keyed by stable transcript generation identity such as
`(document_id, canonical_sha256)`.

Measure:

- no-op refresh when nothing changed;
- one new transcript;
- one changed canonical generation;
- one removed transcript;
- batches of new/changed/removed transcripts; and
- full rebuild of the same corpus as the comparison baseline.

The goal is to prove that normal corpus growth avoids unnecessary work while full rebuild
remains deterministic recovery.

### Search and unified discovery

Use fixed query sets over representative corpora and measure both cold and warm behavior:

- lexical BM25 queries;
- semantic exact-scan queries;
- hybrid RRF queries;
- transcript/document/language/speaker constraints;
- tag/collection/note-text/with-notes research constraints;
- notebook-only note queries; and
- future unified discovery across transcript evidence, notes, tags, collections, and saved
  searches.

Measure latency distribution, not only the best run. The first goal is interactive local
use, not a marketing benchmark.

### Research projection

Measure:

- one-note mutation plus projector catch-up;
- edit/tag/collection/delete mutations;
- bounded batches of 100/1,000/10,000 changes where practical;
- idempotent replay cost;
- projection catch-up after restart;
- journal-gap full rebuild; and
- projection size relative to authoritative SQLite state.

The benchmark must preserve the architecture: SQLite remains authoritative and DuckDB
remains rebuildable. A faster benchmark is not permission to bypass that custody model.

### GUI-facing responsiveness

Once the thin GUI exists, include end-to-end user-visible timings for:

- opening a library;
- typing/search debounce to first stable results;
- switching transcript/note/tag facets;
- opening a transcript result;
- creating/editing a note from selected evidence; and
- seeking local media to `seek_seconds`.

The GUI should be measured through the same application services it uses in production.
Do not create a benchmark-only fast path.

## Suggested corpus sizes

Synthetic corpora are useful for repeatability, but should be paired with real dogfood
where privacy permits.

A practical progression is:

```text
small      10 transcripts / 1,000 segments / 100 notes
medium    100 transcripts / 10,000 segments / 3,000 notes
large   1,000 transcripts / 100,000 segments / 30,000 notes
```

Those are **qualification shapes, not supported-limit claims**. Increase them only when
the application remains useful and measurements justify the next scale.

## Semantic and later capability measurements

Useful semantic dimensions include embedding-index build cost, query latency at increasing
corpus size, research-scope reduction effects, and exact-scan break-even points before
considering ANN/HNSW.

Later optional work can measure diarization after its security gate clears, source
separation on genuine overlap, or alternative embedding profiles. Each should be judged
on end-to-end product benefit, not whether a new model produces an impressive demo.

## How measurements become policy

The harness is for **measurement first, self-tuning never by accident**.

After a sufficient matrix exists, compare predicted and observed memory, real-time factor,
initialization, decode/enhancement/alignment cost, segmentation/inference/checkpoint cost,
cold/warm behavior, library/query latency, projection behavior, and accuracy where
reference data exists.

Only then should a separate reviewed change propose new constants, safety margins,
hardware classes, indexing strategies, automatic preprocessing heuristics, or approximate
search structures.

Benchmark reports say what happened. Policy changes explain why that evidence justifies a
different decision.

That separation keeps calibration auditable and prevents the planner from becoming a
self-modifying raccoon with a stopwatch. 🦝
