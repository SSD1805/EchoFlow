# Empirical benchmarking and calibration

EchoFlow's resource estimates are intentionally conservative heuristics until they
can be compared with measured execution. The benchmarking subsystem is a local-only
measurement harness for collecting that evidence without turning normal
transcription into a separate benchmark implementation.

The current development interface is:

```bash
uv run python -m echoflow.benchmarking /path/to/recording.wav
uv run python -m echoflow.benchmarking /path/to/recording.wav --allow-model-download
uv run python -m echoflow.benchmarking /path/to/recording.wav --json
```

An interrupted job can be measured as a separate resumed attempt:

```bash
uv run python -m echoflow.benchmarking /path/to/recording.wav --resume JOB_ID
```

The harness is deliberately experimental. Once its schema and behavior have been
validated on real devices it can be promoted into the primary `echoflow` command
surface.

## What is measured

A benchmark report records one execution attempt. It currently contains:

- EchoFlow and Python versions;
- path-minimized source provenance: SHA-256, size, modification timestamp,
  container, duration, and audio stream index;
- the process-visible runner resources and selected execution policy;
- the path-free engine/model, decoder, segmentation, and resource-estimate
  contract;
- planning, execution, and total wall-clock duration;
- whole-run and execution-only real-time factors;
- sampled RSS and CPU use for the EchoFlow process and its current descendants;
- aggregate named execution-stage durations and failure counts;
- segment totals, restored counts, and completed counts where available;
- the canonical transcript artifact size after successful publication; and
- the ratio between observed peak process-tree RSS and the planner's current
  peak-memory estimate.

Repeated stages are represented as named aggregates rather than fixed benchmark
columns. A future capability can therefore add measurements such as
`diarization`, `alignment`, `language.identification`, `embedding.index`,
`search.index`, `gpu.transfer`, or `pause.checkpoint` without requiring a new
benchmark architecture.

CPU percentages are the sum of sampled process-tree CPU percentages and can exceed
100% on multi-core machines. RSS is summed across the process tree and can
conservatively double-count shared pages. These measurements are useful comparative
evidence, not operating-system accounting.

## Privacy boundary

Benchmarking does not transmit results and EchoFlow has no benchmark telemetry.
Reports are ordinary user-owned JSON files in the selected public output directory.

The report intentionally omits the source filesystem path, source filename, model
cache path, transcript text, and exception messages. It still contains the source
SHA-256 and other provenance needed to compare equivalent runs. A source digest can
itself be linkable when another party possesses the same recording, so a benchmark
report for a sensitive recording should not be treated as anonymous or published
casually.

Public benchmark sharing should use a known redistributable or synthetic benchmark
corpus, or a future explicitly shareable report format with an appropriately
reduced provenance contract.

## Interruption and resume

Ctrl+C and ordinary Python-level failures persist a partial benchmark report before
the benchmark command exits. The report identifies the attempt as `interrupted` or
`failed`, includes only the exception type, and preserves any measurements recorded
before the failure.

The transcription checkpoint contract remains authoritative for recovery. Completed
segments are checkpointed before they are considered complete, so a later
`--resume JOB_ID` benchmark measures the resumed attempt without redefining resume
semantics.

A hard process kill, power loss, kernel termination, or machine crash cannot execute
benchmark-finalization code, so no final benchmark report is promised for those
failures. Durable transcription checkpoints remain the recovery mechanism. A future
job-lifecycle layer can persist progress observations incrementally if real-world
evidence justifies that additional write path.

## How calibration should be tested

Calibration needs three different evidence layers. They answer different questions
and should not be collapsed into one CI number.

### 1. Deterministic unit and contract tests

These validate the measurement system itself:

- ordinary transcription uses a no-op observer and retains its existing semantics;
- repeated stage measurements aggregate correctly;
- failed stages are recorded without swallowing the original error;
- benchmark reports omit sensitive paths and transcript content;
- interruption and failure produce partial reports;
- process-tree sampling tolerates disappearing child processes;
- resume continues to use the checkpointed execution contract; and
- report/schema validation fails closed on invalid values.

These tests should remain deterministic and fast.

### 2. Cross-platform CI

Linux, macOS, and Windows GitHub Actions runners should execute source tests, build
the distribution, and exercise the clean-wheel contract. CI is useful for proving
that psutil sampling, packaging, observer injection, file handling, and CLI behavior
work on each supported operating system.

Hosted-runner timing is **not calibration truth**. Runner generations, neighboring
workloads, virtualization, CPU frequency policy, caches, and GitHub infrastructure
change outside EchoFlow's control. CI timing can detect catastrophic regressions,
but product resource heuristics should not be fitted to a single hosted-runner
measurement.

### 3. Representative real-device runs

The planner should eventually be calibrated from repeated runs on hardware people
actually own. A useful initial matrix is:

- an 8 GB Windows consumer machine;
- a 16 GB commodity Windows or Linux machine;
- an Apple Silicon Mac; and
- a larger 32/64 GB workstation for comparison.

For comparisons, keep the input bytes, EchoFlow version, engine/model revision,
profile/strategy, and relevant configuration identical. Record whether the model was
already cached. Run each condition multiple times and compare medians and spread,
not a single fastest result. Cold-cache/model-download behavior should be measured
separately from warm local inference.

Thermal throttling, battery/power mode, other active applications, storage speed,
and operating-system updates are legitimate parts of real consumer behavior. They
should be recorded as experimental context when intentionally contributed, not
silently inferred or uploaded by EchoFlow.

## How the evidence should change the planner

The first purpose of this harness is **measurement, not self-tuning**. Do not make a
single benchmark overwrite the planner's conservative resource constants.

Once a sufficient matrix exists, compare predicted and observed peak memory,
real-time factor, model initialization, decode cost, checkpoint cost, and segment
processing across hardware classes. Only then should a separate change propose
calibrated constants, safety margins, hardware classes, or privacy-safe local
calibration behavior.

This separation keeps the evidence auditable: the benchmark says what happened; a
later policy change explains how those observations alter admission and strategy
selection.
