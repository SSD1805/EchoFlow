# EchoFlow

EchoFlow is a local-first Python application for audio processing,
transcription, and analysis. It is intended to keep private, potentially large
recordings on the user's machine.

The product target is a privacy-by-default, resource-aware, reproducible and
resumable workflow for sensitive recordings rather than a model-specific
transcription GUI. EchoFlow keeps the orchestration core small, treats engines
and model payloads as optional capabilities, and derives plans from the CPU,
system memory, and execution-capable accelerators actually available to a laptop,
workstation, container, or CI runner.

EchoFlow is intended to remain useful without mandatory hosted transcription
fees or a cloud account. Durability, reliability, performance on ordinary
hardware, storage/resource awareness, and portable user-owned artifacts are
first-class design constraints. The current direction and research candidates
are documented in [`ROADMAP.md`](ROADMAP.md).

## Project status

EchoFlow currently provides a tested application foundation:

- A Typer command boundary with side-effect-free help.
- `echoflow doctor` diagnostics for workspace, disk, FFmpeg, CPU, and memory.
- Platform-aware private state and model-cache directories.
- An idempotent `echoflow init` first-run command.
- A consumer output directory defaulting to `Downloads/EchoFlow`.
- Typed local jobs and exclusive, collision-safe artifact-path reservations.
- Human-readable Rich tables and stable JSON diagnostic output.
- Atomic local file operations with typed errors.
- Structured logging and monotonic operation timing.
- Path-redacted routine logs and platform-specific private-storage enforcement.
- Namespaced, explicit configuration that does not consume ambient `.env` files.
- CPU-, affinity-, cgroup-, and memory-aware runner policy inspection.
- Separate accelerator-topology discovery and engine capability negotiation so a
  physically visible GPU is not mistaken for a runtime-supported execution target.
- A deterministic local strategy evaluator that admits faster-whisper CPU/int8 and
  CUDA candidates against system-memory, device-memory, runtime-capability, and
  processing-profile constraints, and refuses unsafe explicit selections rather
  than silently replacing them.
- Conservative handling of dedicated, shared, unified, and unknown accelerator
  memory so shared capacity is not double-counted as extra RAM.
- Local FFprobe inspection with protocol restriction, bounded output, timeout,
  full input fingerprinting, and typed media metadata.
- An immutable `transcribe INPUT --dry-run` plan covering paths, streams, codec,
  duration, selected local strategy, decoding strategy, deterministic segmentation,
  and resource estimates.
- Local faster-whisper execution that rechecks resource admission, claims its
  workspace and output atomically, and writes canonical transcript JSON.
- Bounded accelerated pipeline overlap: while an accelerator transcribes the current
  segment, one CPU worker may prepare the next segment, while checkpoint commits
  remain strictly ordered and resumable.
- Audio extraction from audio-bearing containers, including video files, by mapping
  only the selected audio stream into a private canonical WAV.
- Deterministic source-relative PCM frame segmentation with bounded temporary
  materialization and one job-scoped faster-whisper model session reused across
  every segment.
- Deterministic source-relative transcript assembly with contiguous segment and
  engine-version validation.
- Durable private per-segment checkpoints and `transcribe INPUT --resume JOB_ID`
  recovery that restores the original execution contract and skips only validated
  completed work.
- Deterministic opt-in TXT, SRT, and WebVTT views derived from the completed
  canonical transcript without rerunning speech recognition.
- Native-media acceptance coverage that exercises real FFprobe, FFmpeg audio
  extraction/normalization, canonical WAV validation, segmentation, and cleanup on
  Linux, macOS, and Windows CI.
- Explicit model-download authorization; execution is local-only by default.
- Dependency Injector composition for the implemented services.
- A distribution contract that builds the wheel and verifies a clean install of
  the packaged CLI and transcription extra outside the source checkout on Linux,
  macOS, and Windows CI.

Accelerator memory estimates and relative performance ranks are conservative
heuristics until representative-device qualification is complete. EchoFlow does not
claim that every detected GPU is supported or faster. Standalone end-user installers
are not implemented yet.

## Requirements and installation

EchoFlow does not publish end-user installers or GitHub Releases yet. The current
supported path is a source/developer installation using:

- Python 3.12
- [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/SSD1805/EchoFlow.git
cd EchoFlow
uv sync --locked
```

The small default installation can inspect and plan recordings. Install the
optional transcription engine for local transcription execution:

```bash
uv sync --locked --extra transcription
```

CUDA acceleration is not a separate cloud service or account. EchoFlow only selects a
CUDA strategy when a physical CUDA device is visible, CTranslate2 reports support for
the exact device and compute type, and current system/VRAM budgets are safe. Otherwise
the normal CPU/int8 path remains available.

Run the CLI and diagnostics:

```bash
uv run echoflow
uv run echoflow init
uv run echoflow init --json
uv run echoflow init --output-dir /path/to/output
uv run echoflow doctor
uv run echoflow doctor --json
uv run echoflow doctor --workspace /path/to/workspace
uv run echoflow runner
uv run echoflow runner --profile screening --json
uv run echoflow strategies
uv run echoflow strategies --profile accuracy --json
uv run echoflow transcribe /path/to/recording.wav --dry-run
uv run echoflow transcribe /path/to/recording.wav --dry-run --profile screening --json
uv run echoflow transcribe /path/to/recording.wav --strategy small-cpu-int8 --dry-run
uv run echoflow transcribe /path/to/interview.mp4
uv run echoflow transcribe /path/to/interview.mp4 --allow-model-download
uv run echoflow transcribe /path/to/interview.mp4 --export txt
uv run echoflow transcribe /path/to/interview.mp4 --export srt --export vtt
uv run echoflow transcribe /path/to/interview.mp4 --resume JOB_ID --export txt
```

TXT, SRT, and WebVTT are derived views of the completed canonical transcript.
Selecting an export does not invoke the recognition engine again. Canonical JSON
remains the authoritative artifact with execution provenance; derived files can be
removed or regenerated without becoming part of checkpoint or recognition state.
Derived exports are opt-in for now.

Without `--allow-model-download`, EchoFlow asks faster-whisper to use only model
files already present in EchoFlow's private model cache. The flag authorizes the
selected model retrieval for that invocation; it does not authorize uploading the
recording.

An interrupted job retains completed transcript segments in EchoFlow's private
local job state. Resume requires the original input plus the job ID shown when the
job started. EchoFlow restores the original profile, model, revision, execution
device/compute type, CPU thread count, decode settings, and segmentation contract
automatically; `--profile` and `--strategy` cannot override them during resume. The
input is fingerprinted again, and the restored contract must still fit current CPU,
system-memory, and, when applicable, accelerator runtime/VRAM limits before work
continues. Successfully published jobs remove checkpoint payloads on a best-effort
basis. Checkpoint deletion is not secure erasure.

Configuration uses `ECHOFLOW_*` environment variables, including
`ECHOFLOW_STATE_DIR`, `ECHOFLOW_CACHE_DIR`, `ECHOFLOW_MODEL_DIR`, and
`ECHOFLOW_OUTPUT_DIR`. EchoFlow ignores generic variables such as `OUTPUT_DIR`
and never reads an ambient `.env` from the current directory. An explicit
dotenv file can be selected before the command:

```bash
uv run echoflow --config /private/path/echoflow.env runner --json
```

See [`.env.example`](.env.example) for the supported resource and privacy
settings.

## Development

Production code uses a standard src layout under `src/echoflow`. Tests are
colocated in a `tests/` directory beneath the package whose contract they
protect, and those test packages are excluded from built distributions.

Install the Git hooks once:

```bash
uv run pre-commit install
```

Run the repository gates:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run vulture
uv run radon cc src/echoflow --total-average
uv run radon mi src/echoflow
uv run pytest --cov=echoflow --cov-branch --cov-report=term-missing
uv lock --check
uv build
uv run python scripts/verify_distribution.py dist
```

The distribution verifier inspects the built wheel for its console entry point,
transcription extra, license metadata, packaged license file, and accidental test
leakage. It then creates a temporary virtual environment outside the repository,
disables user-site and source-path imports, installs `echoflow[transcription]` from
that wheel, and exercises the installed CLI. CI runs that contract on Linux,
macOS, and Windows. CI also provisions FFmpeg/FFprobe explicitly and exercises a
small generated MP4 through the production probe, decode, WAV, segmentation, and
cleanup path on all three operating systems; this is a functional media-boundary
check, not a performance benchmark or real-model accuracy test.

The enforced budgets are:

- Ruff cyclomatic complexity of at most 10.
- Branch-aware test coverage of at least 90%.
- Vulture findings reported only at 100% confidence.
- Strict mypy checks over production code.
- Ruff security rules over production code.
- A locked runtime dependency audit in CI.

Radon reports complexity and maintainability trends; Ruff provides the hard
complexity gate. Targeted Poodle mutation runs are used for changed decision
logic because its broad runner currently has a process-timeout cleanup defect.
Topology, capability negotiation, heterogeneous strategy admission, adaptive
execution, and bounded prefetch are included in the targeted mutation scope along
with the existing transcription decision modules.

The full feedback ladder and Git bisect procedure are documented in
[`docs/development/testing-and-bisect.md`](docs/development/testing-and-bisect.md).

## Architecture direction

EchoFlow keeps user artifacts as normal files in a user-selected output
directory. Private state and model caches are separate internal concerns.
Artifact names are reserved atomically and collisions are renamed rather than
overwritten by default. Durable checkpoint state is stored as private per-job
files; a future local job index, if added, should contain metadata rather than
audio or transcript blobs.

`echoflow runner` derives an engine-neutral CPU and system-memory budget from
resources actually visible to the process, including common container limits and
explicit user ceilings. Accelerator topology is discovered separately so a broken or
unsupported GPU runtime cannot make ordinary CPU execution unusable. Engine-specific
capability providers then advertise only execution targets their installed runtimes
can actually consume.

Transcription evaluates concrete faster-whisper strategies against that evidence.
`echoflow strategies` exposes current CPU/int8 and feasible CUDA candidates with their
estimated model-cache, system-memory, and device-memory costs, marks infeasible choices
with typed reasons, and recommends a feasible strategy according to `screening`,
`balanced`, or `accuracy` intent. An explicit `transcribe --strategy` choice is honored
when feasible and refused otherwise; it is never silently replaced. Screening remains
explicitly provisional.

Dedicated device memory is budgeted separately from system RAM. Shared and unified
accelerator memory is also charged against the system-memory budget so EchoFlow never
counts the same physical bytes twice. Unknown device-memory capacity is not guessed for
an accelerated strategy.

Execution consumes the selected plan rather than allowing the engine to make a second,
unrelated placement decision. It checks process-visible CPU and system-memory capacity
before claiming paths and again before model initialization. Accelerated execution also
rechecks physical accelerator visibility, current safe device memory, and exact runtime
support before loading the model. A video is not treated as visual input: FFmpeg
discards video, subtitle, and data streams and emits only the selected audio stream to
the private job workspace.

After decode, EchoFlow owns segmentation. Segment windows remain exact source-relative
PCM frame ranges. The CPU path preserves the original strictly sequential
materialize/transcribe/checkpoint loop. Accelerated execution may pre-materialize at
most one future segment on a CPU worker while the current segment is being transcribed.
There is still one job-scoped faster-whisper session and one ordered checkpoint writer.
A result becomes resumable only after its checkpoint is written, so completed work
remains a contiguous prefix even when preparation overlaps inference.

EchoFlow intentionally uses pipeline overlap before attempting model/tensor sharding.
The application owns decode, materialization, checkpoints, assembly, and publication,
but it does not own every speech engine's tensor graph or host/device transfer policy.
That keeps heterogeneous scheduling portable across future engine adapters and avoids
binding recovery semantics to one backend's partitioning implementation.

TXT, SRT, and WebVTT publication occurs only after canonical transcript completion.
The renderers consume canonical source-relative segment times; application-owned
segmentation therefore does not reset subtitle clocks. Derived files are rendered
before path reservation and published through the same atomic local-file boundary.
If derived publication fails, EchoFlow rolls back that derived set while preserving
the already-completed canonical JSON artifact.

Resource estimates and accelerator performance ranks are deliberately conservative
heuristics until representative-machine benchmarks and privacy-safe local calibration
exist. Dry-run workspace and artifact paths are candidates, not reservations;
execution must claim them atomically before writing.

Checkpoint schema version 1 persists a manifest plus one atomic JSON result for
each completed segment under the private local job directory. The manifest omits
the input path, source filename, and model-cache path while binding source content,
media identity, engine/model/revision, resource requirements, decode settings,
segmentation settings, and exact PCM frame windows. Resume accepts only a
contiguous validated prefix, restores detected language and the original execution
contract, and refuses corruption, identity mismatches, engine-version changes, or
resource contraction that makes the interrupted strategy unsafe. Transcript
fragments are intentionally not masked because exact recovery requires exact text;
they are sensitive local plaintext state and are never routine log fields or public
artifacts.

Adaptive placement and bounded overlap are documented in
[`docs/architecture/adaptive-heterogeneous-execution.md`](docs/architecture/adaptive-heterogeneous-execution.md).
The planned evidence-first corpus-search architecture is documented in
[`docs/architecture/corpus-search.md`](docs/architecture/corpus-search.md).
The broader processing boundaries and resumability model are documented in
[`docs/architecture/processing-capabilities.md`](docs/architecture/processing-capabilities.md).

Security boundaries, residual risks, and disclosure instructions are in
[`SECURITY.md`](SECURITY.md). The current review record is
[`docs/security/audit-2026-08-02.md`](docs/security/audit-2026-08-02.md).

## License

EchoFlow is licensed under the [GNU Affero General Public License v3.0 only](LICENSE).
See [`LICENSING.md`](LICENSING.md) for the transition from earlier Apache-2.0
versions.
