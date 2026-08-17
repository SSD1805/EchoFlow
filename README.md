# EchoFlow

EchoFlow is a local-first Python application for audio processing, transcription, and
analysis. It is designed to keep private, potentially large recordings on the user's
machine.

The product target is a privacy-by-default, resource-aware, reproducible, and resumable
workflow for sensitive recordings rather than a model-specific transcription GUI.
EchoFlow derives execution plans from CPU, system memory, and execution-capable
accelerators actually available to the current process, keeps source media authoritative,
makes local model and preprocessing provenance explicit, and provides evidence-first
local search across completed transcripts.

EchoFlow does not require a hosted transcription account. Durability, reliability,
performance on ordinary hardware, local storage awareness, and portable user-owned
artifacts are first-class constraints. See [`ROADMAP.md`](ROADMAP.md) for current work
and research candidates.

## Project status

EchoFlow is pre-production. Its current tested foundation includes:

- a Typer/Rich CLI with deterministic JSON output;
- `echoflow doctor`, first-run initialization, and platform-aware private state;
- process-visible CPU, affinity, cgroup, memory, accelerator, and runtime capability
  inspection;
- resource-admitted faster-whisper CPU/int8 and CUDA execution strategies with no
  silent fallback for explicit selections;
- FFprobe media inspection and deterministic audio-stream selection;
- FFmpeg canonicalization to mono 16 kHz PCM16 WAV where needed;
- exact source-relative frame segmentation and one job-scoped faster-whisper session;
- bounded one-segment CPU preparation overlap for accelerated inference;
- durable private checkpoints and validated resume;
- multilingual faster-whisper decoding plus conservative local language attribution;
- optional anonymous local speaker diarization, currently security-held when its
  locked dependency graph is unsafe;
- canonical JSON with deterministic TXT, SRT, and WebVTT derived exports;
- explicit faster-whisper model inventory, recommendation, installation, local
  verification, immutable revision pinning, and exact-revision removal;
- mandatory managed-model custody for ASR planning and execution;
- optional deterministic local FFmpeg speech noise suppression with private derived
  audio, timeline-preservation checks, and transcript provenance;
- a database-neutral transcript-index port with a private rebuildable DuckDB backend,
  deterministic offline BM25-style lexical ranking, and typed evidence search;
- human-readable transcript evidence receipts with canonical/source locations,
  recorded source SHA-256, and current source-integrity verification;
- storage preflight for normalization, enhancement, segment materialization, model
  acquisition, and published artifacts;
- cross-platform private-storage enforcement and Linux/macOS/Windows CI.

Accelerator memory estimates and performance ranks remain conservative heuristics until
representative-device qualification is complete. Standalone end-user installers and a
graphical UI are not implemented yet.

## Requirements and installation

EchoFlow does not publish end-user installers or Releases yet. The supported path is a
source/developer install with Python 3.12 and `uv`:

```bash
git clone https://github.com/SSD1805/EchoFlow.git
cd EchoFlow
uv sync --locked --extra transcription
```

Run the CLI and initialize local directories:

```bash
uv run echoflow
uv run echoflow init
uv run echoflow doctor
uv run echoflow runner
uv run echoflow strategies
```

CUDA is not assumed merely because a GPU is visible. EchoFlow selects CUDA only when
physical topology, the CTranslate2 runtime, compute type, system-memory budget, and
device-memory budget all agree. CPU/int8 remains the reference fallback strategy.

## Install a transcription model first

ASR model acquisition is an explicit model-management action. Transcription itself does
not download faster-whisper models and does not treat arbitrary Hugging Face cache
entries as managed state.

Inspect the local catalog and current recommendation:

```bash
uv run echoflow models
uv run echoflow models recommend
```

Install the model required by the strategy/profile you intend to use:

```bash
uv run echoflow models install small
```

The install is disk-admitted, downloaded into EchoFlow's private model cache, structurally
verified, and recorded with provider/repository/resolved-revision provenance. New
transcription plans require a verified managed revision. If the selected model is not
managed, planning fails with an install-first message.

Inventory and recommendation are offline. `models install` is the explicit network-
bearing ASR model operation.

See
[`docs/architecture/model-management.md`](docs/architecture/model-management.md) for
the custody contract and current verification boundary.

## Plan and transcribe

Dry-run is side-effect free with respect to job/output reservation and model acquisition:

```bash
uv run echoflow transcribe /path/to/recording.wav --dry-run
uv run echoflow transcribe /path/to/recording.wav --dry-run --profile screening --json
uv run echoflow transcribe /path/to/recording.wav --strategy small-cpu-int8 --dry-run
```

Execute locally:

```bash
uv run echoflow transcribe /path/to/interview.mp4
uv run echoflow transcribe /path/to/interview.mp4 --export txt
uv run echoflow transcribe /path/to/interview.mp4 --export srt --export vtt
```

The faster-whisper adapter is local-only at execution time and loads the exact managed
revision already recorded in the plan.

TXT, SRT, and WebVTT are derived views of completed canonical JSON. Selecting an export
does not invoke recognition again. Canonical JSON remains authoritative; derived files
can be removed or regenerated without becoming checkpoint or recognition state.

## Optional local noise suppression

EchoFlow can apply deterministic local FFmpeg noise suppression before ASR:

```bash
uv run echoflow transcribe /path/to/noisy-interview.wav --enhance
```

Enhancement is off by default. The first provider uses the application-owned FFmpeg
`afftdn=nf=-50:nr=12` contract. Enhanced audio is private derived execution material,
not a replacement for the source recording and not published by default.

ASR consumes the enhanced derivative when enabled. Anonymous diarization continues to
inspect the unmodified canonical decode in this first version because EchoFlow has not
yet established that denoising improves speaker evidence.

The provider must preserve channel count, sample width, sample rate, and frame count.
A timeline mismatch fails closed. Canonical transcript JSON records provider version,
operation, and parameters when enhancement affected ASR input.

There is no automatic enhancement mode yet. Representative benchmarks must show an
end-to-end ASR benefit before EchoFlow invents heuristics for when to turn it on.

See
[`docs/architecture/speech-enhancement.md`](docs/architecture/speech-enhancement.md).

## Search the local transcript library

Completed canonical transcripts can be projected into a private rebuildable local
library. Canonical JSON remains authoritative; the DuckDB search database is disposable
derived state and contains no unique user information.

Build or rebuild the library from EchoFlow's known completed transcripts:

```bash
uv run echoflow library rebuild
uv run echoflow library
```

Additional canonical transcript files or directories can be included explicitly:

```bash
uv run echoflow library rebuild /path/to/transcripts
```

Search uses deterministic local BM25-style lexical ranking. DuckDB is an implementation
detail below the application boundary; users do not provide SQL, and the first search
tranche does not install or load a network-fetched DuckDB FTS extension.

```bash
uv run echoflow library search "housing insecurity"
uv run echoflow library search "housing insecurity" --phrase
uv run echoflow library search "rent increase" --all-terms --speaker speaker-02 --language en
```

Results preserve evidence context including the canonical transcript, source recording
path when known, source SHA-256, source-relative timestamps, speaker/language evidence,
and the matching passage.

Inspect one transcript's custody and source-integrity evidence:

```bash
uv run echoflow library show JOB_ID
```

The evidence receipt distinguishes the original recording, canonical transcript, and
private search index. It reports the SHA-256 recorded for transcription and can re-hash
the file currently at the recorded source path to show whether those bytes still match.
A match proves current byte identity with the recorded fingerprint; it does not claim
that no external process ever modified and later restored the file.

EchoFlow treats the supplied source recording as read-only input. Canonicalization,
segmentation, enhancement, checkpoints, exports, and search data are written separately
rather than overwriting that source.

See
[`docs/architecture/corpus-search.md`](docs/architecture/corpus-search.md).

## Resume interrupted work

An interrupted job retains completed segment results in private local state. Resume
requires the original input and the job ID printed when execution began:

```bash
uv run echoflow transcribe /path/to/interview.mp4 --resume JOB_ID
```

The current checkpoint contract binds source identity, selected audio stream,
profile/provisional state, managed engine/model/revision, CPU/device/compute type,
decode settings, enhancement off/on/provider/parameters, segmentation settings,
resource requirements, and exact PCM frame windows.

Resume restores that contract rather than accepting overrides. The input is
fingerprinted again and the restored strategy must still satisfy current CPU, memory,
and, where applicable, accelerator admission before work continues. Completed segment
checkpoints must form a validated contiguous prefix and use one engine version.

Successful publication removes checkpoint payloads on a best-effort basis. Checkpoint
deletion is not secure erasure.

## Optional speaker diarization

Diarization is a separate optional enrichment:

```bash
uv run echoflow transcribe interview.wav --diarize
```

The current pyannote capability remains fail-closed while its locked Lightning
dependency is affected by the compensated security advisory documented in
[`SECURITY.md`](SECURITY.md). If model acquisition is explicitly needed for this
optional capability, authorization is narrowly scoped to
`--allow-diarization-model-download`; that flag does not authorize ASR model downloads.

Diarization produces anonymous recording-scoped labels such as `speaker-01`; it does
not perform biometric identity or cross-recording speaker linking.

## Configuration

Configuration uses namespaced `ECHOFLOW_*` environment variables, including:

- `ECHOFLOW_STATE_DIR`
- `ECHOFLOW_CACHE_DIR`
- `ECHOFLOW_MODEL_DIR`
- `ECHOFLOW_OUTPUT_DIR`
- `ECHOFLOW_PROCESSING_PROFILE`
- resource ceilings and FFmpeg/FFprobe timeouts

EchoFlow ignores generic variables such as `OUTPUT_DIR` and never loads an ambient
`.env` from the current directory. Select an explicit dotenv file before the command:

```bash
uv run echoflow --config /private/path/echoflow.env runner --json
```

There is no faster-whisper revision override. ASR revisions come from verified managed
model state.

See [`.env.example`](.env.example) for supported settings.

## Development

Production code uses a standard `src/` layout. Tests are colocated under a `tests/`
directory beneath the package whose contract they protect and are excluded from built
distributions.

Install hooks once:

```bash
uv run pre-commit install
```

Run normal repository gates:

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

Normal CI also audits locked dependencies, builds distributions, verifies clean-wheel
installs, and runs platform smoke coverage on Linux, macOS, and Windows. The enforced
quality budgets include Ruff complexity <= 10, branch coverage >= 90%, strict mypy,
100%-confidence Vulture findings, and Ruff security rules.

Mutation testing is deliberate qualification, not a per-commit gate. For load-bearing
decision code, tests should first anticipate comparator, Boolean, threshold, fallback,
fail-open, ordering, cleanup, resume, provenance, and concurrency mutations. Targeted
Poodle runs are then used locally/sandboxed or through the manual workflow after normal
tests are green.

See
[`docs/development/testing-and-bisect.md`](docs/development/testing-and-bisect.md).
