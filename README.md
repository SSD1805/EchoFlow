# EchoFlow

EchoFlow is a local-first Python application for audio processing,
transcription, and analysis. It is intended to keep private, potentially large
recordings on the user's machine.

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
- Dependency Injector composition for the implemented services.

Audio ingestion and transcription are not implemented yet. The first planned
product slice is a local `transcribe --dry-run` command, followed by one working
CPU transcription path.

## Requirements and installation

- Python 3.12
- [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/SSD1805/EchoFlow.git
cd EchoFlow
uv sync --locked
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
```

Configuration can be supplied through environment variables or an optional
`.env` file. `STATE_DIR`, `CACHE_DIR`, `MODEL_DIR`, and `OUTPUT_DIR` override
the platform-aware defaults. EchoFlow does not require a `.env` file.

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
```

The enforced budgets are:

- Ruff cyclomatic complexity of at most 10.
- Branch-aware test coverage of at least 90%.
- Vulture findings reported only at 100% confidence.
- Strict mypy checks over production code.

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

The proposed processing boundaries, resumability model, and bounded audio
bisection policy are documented in
[`docs/architecture/processing-capabilities.md`](docs/architecture/processing-capabilities.md).

## License

EchoFlow is licensed under the [Apache License 2.0](LICENSE).
