# Testing and regression bisection

## Colocation rule

Every capability keeps tests in a `tests/` directory directly beneath the package it
protects:

```text
src/echoflow/core/health_check.py
src/echoflow/core/tests/test_health_check.py

src/echoflow/interfaces/local_file_manager.py
src/echoflow/interfaces/tests/test_local_file_manager.py
```

Repository-wide pytest configuration belongs in root `conftest.py`. Shared fixtures
remain local to the narrowest package that needs them. Test packages are excluded from
built distributions.

## Feedback ladder

Use the smallest trustworthy oracle first, then widen it:

1. One test node: `uv run pytest path/to/test.py::test_name`
2. One capability suite: `uv run pytest path/to/test.py`
3. One package suite: `uv run pytest src/echoflow/PACKAGE/tests`
4. Most recent failures: `uv run pytest --last-failed`
5. Full behavioral suite: `uv run pytest`
6. Full branch coverage:
   `uv run pytest --cov=echoflow --cov-branch --cov-report=term-missing`
7. Static/metric gates: Ruff check/format, strict mypy, Vulture, and Radon.
8. Targeted mutation scope for changed decision logic, followed by build, clean-wheel,
   and lock verification.

## Mutation anticipation rule

Mutation testing should not be the first place EchoFlow discovers weak test contracts.
For load-bearing decision logic, define plausible bad edits while designing ordinary
tests and identify the exact test expected to kill each one.

At minimum, review changed decision logic for:

- boundary/operator changes such as `<` vs `<=`, `>` vs `>=`, `==` vs `!=`;
- Boolean changes such as `and` vs `or`, removed `not`, or inverted predicates;
- threshold/constant perturbations around zero, one, counts, sizes, durations,
  percentages, schema versions, and resource limits;
- arithmetic/accounting changes such as `+` vs `-`, omitted/double-counted terms,
  integer rounding, or multipliers;
- fallback mutations that silently downgrade/upgrade or choose another
  provider/device/model;
- fail-open mutations where exceptions, missing capability, malformed probes, or
  uncertain security state become success;
- ordering mutations around checkpoint, persistence, publish, cleanup, cancellation,
  model-manifest commits, and provenance writes;
- ownership/lifecycle mutations such as skipped cleanup, double cleanup, leaked
  prefetched/derived work, or stale-state reuse;
- resume/idempotence mutations that accept mismatched source, model, revision,
  preprocessing, engine, version, or execution contract;
- provenance/serialization mutations that omit or alter evidence needed to explain an
  artifact; and
- concurrency mutations such as increased prefetch depth, oversubscription, changed
  worker counts, or out-of-order commits.

The preferred shape is explicit positive, negative, boundary, and failure-path coverage
where the contract warrants it. Hypothesis is useful for invariants spanning many
values, but named boundary cases remain valuable for safety decisions.

The review question is:

**if this comparator, Boolean, threshold, fallback, or ordering decision were subtly
wrong, which exact test would fail?**

If there is no clear answer, strengthen ordinary tests before asking Poodle to find the
blind spot.

Run Poodle only after deterministic tests are green and over the smallest relevant
module set. Inspect survivors as evidence about test strength. Routine CI does not gate
on mutation sweeps; use an available local/sandbox checkout or the manual workflow for
deliberate qualification.

## Model-custody mutation hypotheses

For model-management and the ASR planning/execution boundary, tests should kill at
least these plausible bad edits when the related logic changes:

- failed structural verification is treated as managed;
- a manifest points outside EchoFlow's model cache;
- repository identity can be substituted while required files still look valid;
- recorded revision and snapshot directory disagree;
- requested revision is silently replaced by another provider revision;
- insufficient disk is admitted before acquisition;
- manifest commit happens before provider verification completes;
- removal deletes the manifest before provider deletion succeeds;
- external deletion leaves a stale manifest reported as usable;
- a transcription plan accepts an unmanaged/ambient cache entry;
- a managed revision is replaced by a configuration override;
- faster-whisper execution changes `local_files_only=True` to a network-capable path;
  or
- model/repository/revision/verification provenance is omitted.

The pre-production current contract has **no ASR transcription-time download fallback**.
A test expecting that old compatibility behavior should be rewritten or removed rather
than forcing production code to preserve it.

## Enhancement mutation hypotheses

For optional speech noise suppression, tests should kill:

- `off` invokes the enhancer;
- `on` skips enhancement or silently falls back to raw audio after a provider failure;
- ASR consumes raw audio after enhancement succeeded;
- diarization consumes enhanced audio in the current v1 contract;
- provider or parameters can change without checkpoint incompatibility;
- enhanced full-recording storage is omitted or double-counted;
- channel/sample-width/sample-rate/frame-count validation is weakened or inverted;
- partial enhanced output survives a failed transform;
- cleanup is skipped, duplicated unsafely, or masks the primary error;
- provider/version/operation/parameters disappear from transcript provenance;
- enhancement modifies the original recording;
- enhanced audio becomes a public artifact without an explicit export contract; or
- a future model-backed enhancer bypasses model-management custody.

Tests should compare paths and ownership explicitly. “Enhancer was called” is not enough
to prove ASR used its output or that diarization retained the raw canonical decode.

## Pre-production schema rule

EchoFlow currently has no released/dogfooded durable-schema compatibility obligation.
Tests protect **one current job-plan, checkpoint, and canonical-transcript contract**.
Do not retain old schema branches solely because an earlier PR once emitted them during
development.

When a real compatibility boundary exists, migration tests should be added against
actual persisted fixtures from that boundary. Until then, deleting obsolete
pre-production branches is preferable to multiplying migration paths nobody uses.

## Sandbox readiness

A sandbox can run repository-local tools only when it actually has an EchoFlow
checkout. The repository cannot force an external execution environment to mount that
checkout, so every coding session verifies workspace availability before claiming local
mutation capability.

When a checkout exists, prepare it with:

```bash
python scripts/prepare_dev_environment.py
```

This performs a locked development sync and verifies Poodle is runnable. If the
checkout is absent, use the connected GitHub repository for inspection and the manual
mutation workflow for qualification rather than making per-commit mutation CI a
substitute for a local workspace.

## Git bisect

A bisect oracle must be deterministic, noninteractive, and narrow enough to run
repeatedly. Start from a known bad revision and a known good revision, then let Git
invoke the smallest test proving the regression:

```bash
git bisect start BAD GOOD
git bisect run uv run pytest src/echoflow/core/tests/test_health_check.py -q
git bisect reset
```

Use a package/full-suite oracle only when a smaller contract cannot reproduce the
failure. A test depending on network access, mutable model cache, wall-clock timing, or
mutable user state is not a valid bisect oracle until those inputs are controlled.

Model acquisition tests should fake the provider boundary. Enhancement-provider tests
should fake subprocess behavior or use intentionally generated local audio when the
native-media boundary itself is under test.

## Source-to-test navigation

The path convention is the primary index: changed production files and their tests
share a package. `rg`, `pytest --collect-only`, coverage, and Git's changed-file list
cover current navigation needs. Static test-to-symbol mapping can use Python `ast`
later if repository scale justifies it. Tree-sitter would not improve Git bisect,
pytest collection, or Python-only symbol parsing today.
