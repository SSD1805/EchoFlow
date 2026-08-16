# EchoFlow

EchoFlow is a local-first Python application for audio processing,
transcription, and analysis. It is intended to keep private, potentially large
recordings on the user's machine.

The product target is a privacy-by-default, resource-aware, reproducible and
resumable workflow for sensitive recordings rather than a model-specific
transcription GUI. EchoFlow keeps the orchestration core small, treats engines
and model payloads as optional capabilities, and derives plans from the CPU and
memory actually available to a laptop, workstation, container, or CI runner.

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
- Path-redacted routine logs and owner-only private directories on POSIX.
- Namespaced, explicit configuration that does not consume ambient `.env` files.
- CPU-, affinity-, cgroup-, and memory-aware runner policy inspection.
- A deterministic local strategy evaluator that lists feasible faster-whisper
  CPU/int8 choices, recommends one by processing profile, and refuses unsafe
  explicit selections rather than silently downgrading them.
- Local FFprobe inspection with protocol restriction, bounded output, timeout,
  full input fingerprinting, and typed media metadata.
- An immutable `transcribe INPUT --dry-run` plan covering paths, streams, codec,
  duration, selected local strategy, decoding strategy, and resource estimates.
- One executable CPU/int8 faster-whisper path that rechecks resource admission,
  claims its workspace and output atomically, and writes canonical transcript JSON.
- Audio extraction from audio-bearing containers, including video files, by mapping
  only the selected audio stream into a private canonical WAV.
- Explicit model-download authorization; execution is local-only by default.
- Dependency Injector composition for the implemented services.
- A distribution contract that builds the wheel and verifies a clean install of
  the packaged CLI and transcription extra outside the source checkout on Linux,
  macOS, and Windows CI.

Deterministic application-owned segmentation, checkpointing, resume, calibrated
performance estimates, GPU strategies, derived TXT/SRT/VTT artifacts, and
standalone end-user installers are not implemented yet.

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
optional CPU engine for transcription execution:

```bash
uv sync --locked --extra transcription
```

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
```

Without `--allow-model-download`, EchoFlow asks faster-whisper to use only model
files already present in EchoFlow's private model cache. The flag authorizes the
selected model retrieval for that invocation; it does not authorize uploading the
recording.

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
transcription extra, and accidental test leakage. It then creates a temporary
virtual environment outside the repository, disables user-site and source-path
imports, installs `echoflow[transcription]` from that wheel, and exercises the
installed CLI. CI runs that contract on Linux, macOS, and Windows.

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

The full feedback ladder and Git bisect procedure are documented in
[`docs/development/testing-and-bisect.md`](docs/development/testing-and-bisect.md).

## Architecture direction

EchoFlow keeps user artifacts as normal files in a user-selected output
directory. Private state and model caches are separate internal concerns.
Artifact names are reserved atomically and collisions are renamed rather than
overwritten by default. Future SQLite job state will contain paths and metadata;
audio and transcript documents will not be stored as database blobs.

`echoflow runner` derives an engine-neutral CPU and memory budget from resources
actually visible to the process, including common container limits and explicit
user ceilings. It does not select a model. Transcription evaluates concrete
faster-whisper strategies against that budget. `echoflow strategies` exposes all
current CPU/int8 choices with their estimated model-cache and peak-memory costs,
marks infeasible choices with typed reasons, and recommends a feasible strategy
according to `screening`, `balanced`, or `accuracy` intent. An explicit
`transcribe --strategy` choice is honored when feasible and refused otherwise;
it is never silently replaced. Screening remains explicitly provisional.

Execution consumes the selected plan rather than detecting a second, unrelated
machine configuration inside the engine. It checks process-visible memory and CPU
capacity before claiming paths and again after any FFmpeg normalization,
immediately before model initialization. A video is not treated as visual input:
FFmpeg discards video, subtitle, and data streams and emits only the selected audio
stream to the private job workspace.

Resource estimates are deliberately conservative heuristics until real engine
benchmarks and privacy-safe local calibration are added. Dry-run workspace and
artifact paths are candidates, not reservations; execution must claim them
atomically before writing.

Checkpoint resume is intentionally not represented as implemented yet. The current
backend transcribes a complete decoded recording in one call. Truthful resume first
requires deterministic, source-relative segment boundaries and a job-scoped model
session; persisted per-segment state can then retain completed work across a crash
without changing the model contract.

The proposed processing boundaries, resumability model, and bounded audio
bisection policy are documented in
[`docs/architecture/processing-capabilities.md`](docs/architecture/processing-capabilities.md).

Security boundaries, residual risks, and disclosure instructions are in
[`SECURITY.md`](SECURITY.md). The current review record is
[`docs/security/audit-2026-08-02.md`](docs/security/audit-2026-08-02.md).

## License

EchoFlow is licensed under the [Apache License 2.0](LICENSE).
