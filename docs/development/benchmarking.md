# Empirical benchmarking and calibration

EchoFlow's resource estimates and relative strategy ranks are intentionally
conservative heuristics until they can be compared with measured execution. The
benchmarking subsystem is a local-only harness for collecting that evidence without
creating a second transcription implementation.

ASR models must already be installed through model management before a benchmark can
plan or execute. Benchmarking never authorizes a hidden faster-whisper download.

The current development interface is:

```bash
uv run python -m echoflow.benchmarking /path/to/recording.wav
uv run python -m echoflow.benchmarking /path/to/recording.wav --json
```

An interrupted job can be measured as a separate resumed attempt:

```bash
uv run python -m echoflow.benchmarking /path/to/recording.wav --resume JOB_ID
```

The harness is experimental. Once its schema and behavior have been validated on real
devices it may be promoted into the primary `echoflow` command surface.

## What is measured

A benchmark report describes one execution attempt and currently includes:

- EchoFlow and Python versions;
- path-minimized source provenance: SHA-256, size, modification timestamp, container,
  duration, and audio stream index;
- process-visible runner resources and selected execution policy;
- path-free managed engine/model/revision, execution target, decoder, enhancement,
  segmentation, and resource-estimate contracts;
- planning, execution, and total wall-clock duration;
- whole-run and execution-only real-time factors;
- sampled RSS and CPU use for EchoFlow and current descendant processes;
- aggregate named execution-stage durations and failure counts;
- segment totals, restored counts, and completed counts where available;
- canonical transcript artifact size after successful publication; and
- the ratio between observed peak process-tree RSS and the planner's peak-memory
  estimate.

Repeated stages are named aggregates rather than fixed columns. Additional capabilities
can therefore add measurements such as `enhancement.apply`, `speaker.diarize`,
`alignment`, `embedding.index`, `search.index`, or `gpu.transfer` without a new
benchmark architecture.

CPU percentages sum sampled process-tree CPU and may exceed 100% on multi-core systems.
RSS is summed across the process tree and may conservatively double-count shared pages.
These are comparative measurements, not exact operating-system accounting.

## Privacy boundary

Benchmarking does not transmit results and EchoFlow has no benchmark telemetry.
Reports are user-owned JSON files in the selected output directory.

Reports intentionally omit source paths/filenames, model-cache paths, transcript text,
and exception messages. They retain source digest and other provenance needed to
compare equivalent runs. A source digest can still be linkable when another party has
the same recording, so a report for sensitive media is not automatically anonymous.

Public sharing should use a redistributable/synthetic corpus or a future intentionally
shareable report format with reduced provenance.

## Interruption and resume

Ctrl+C and ordinary Python-level failures persist a partial benchmark report before the
benchmark command exits. It identifies the attempt as interrupted/failed, includes only
the exception type, and preserves measurements already recorded.

The transcription checkpoint contract remains authoritative for recovery. Completed
segments are checkpointed before they count as complete, so a later resume benchmark
measures the resumed attempt without redefining recovery semantics. The checkpoint also
binds managed model revision and enhancement state, preventing a resumed benchmark from
quietly changing preprocessing or weights.

A hard process kill, power loss, kernel termination, or machine crash cannot execute
benchmark-finalization code, so no final report is promised for those failures. Durable
transcription checkpoints and lifecycle state remain recovery evidence.

## Qualification layers

Calibration needs three evidence layers that answer different questions.

### 1. Deterministic unit and contract tests

These validate the measurement system itself:

- ordinary transcription uses a no-op observer without changing semantics;
- repeated stage measurements aggregate correctly;
- failed stages are recorded without swallowing the original error;
- reports omit sensitive paths and transcript content;
- interruption/failure produce partial reports;
- process-tree sampling tolerates disappearing children;
- resume uses the checkpointed current contract; and
- report/schema validation fails closed on invalid values.

These remain deterministic and fast.

### 2. Cross-platform CI

Linux, macOS, and Windows GitHub Actions runners execute tests, build distributions,
and exercise clean-wheel behavior. CI proves psutil sampling, packaging, observer
injection, file handling, native media tools, and CLI behavior on supported operating
systems.

Hosted-runner timing is **not calibration truth**. Runner generations, neighboring
workloads, virtualization, CPU frequency policy, caches, and infrastructure change
outside EchoFlow's control. CI can reveal catastrophic regressions, but planner
heuristics should not be fitted to one hosted-runner measurement.

### 3. Representative real-device runs

The initial physical matrix should include:

- an 8 GB Windows consumer machine;
- a 16 GB commodity Windows/Linux machine;
- Apple Silicon;
- a discrete-GPU laptop; and
- a larger 32/64 GB workstation.

For comparisons, keep input bytes, EchoFlow version, managed model revision,
profile/strategy, enhancement condition, and relevant configuration identical. Record
whether caches are cold/warm. Run repeated trials and compare medians/spread rather
than one fastest result.

Thermal throttling, battery/power mode, other applications, storage speed, and OS
updates are legitimate consumer conditions. Record them as experimental context when
known rather than silently inferring/uploading them.

## Raw ASR versus enhancement-plus-ASR

Noise suppression is qualified by **transcription outcome and total cost**, not by
whether processed audio sounds nicer.

Use representative noisy recordings and run matched conditions:

1. managed-model raw ASR with enhancement off;
2. the same model/revision/strategy with `--enhance`; and
3. repeated runs when variance matters.

Where reference transcripts exist, compare at least WER and, where useful, CER. Also
compare:

- total and stage-specific wall-clock time;
- real-time factor;
- CPU/RAM pressure;
- accelerator impact when applicable;
- private disk overhead;
- checkpoint/resume behavior; and
- failures on silence, clipping, stationary/non-stationary noise, music, and mixed
  acoustic conditions.

The first FFmpeg `afftdn` provider is a fixed deterministic condition. Its presence in
the product does not imply it improves every recording.

An automatic enhancement mode should not exist until measurements show a sufficiently
reliable relationship between observable input conditions and end-to-end ASR benefit.
If enhancement worsens transcription or adds unjustified cost for a class of inputs,
that is evidence against automatic activation for that class.

## How evidence changes policy

The harness exists first for **measurement, not self-tuning**. A single benchmark must
not rewrite conservative planner constants or enhancement policy.

After a sufficient matrix exists, compare predicted and observed:

- peak memory and device memory;
- real-time factor;
- model initialization;
- decode and enhancement cost;
- segment materialization/inference/checkpoint cost;
- cold/warm behavior; and
- raw-ASR versus enhanced-ASR accuracy.

Only then should a separate reviewed change propose calibrated constants, safety
margins, hardware classes, or an evidence-driven enhancement heuristic.

The separation keeps evidence auditable: benchmark reports say what happened; policy
changes explain why those observations justify different admission or selection.
