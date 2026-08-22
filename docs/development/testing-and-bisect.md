# Testing and regression bisection 🧪🦝

Scholion has enough failure-sensitive logic that “the happy path passed” is not a
satisfying definition of tested.

The testing strategy therefore prefers **small deterministic oracles, explicit boundary
cases, property invariants, and targeted mutation hypotheses** before expensive broad
qualification.

The question to keep asking is:

> **If this comparator, Boolean, threshold, fallback, ordering decision, or cleanup path
> were subtly wrong, which exact test would fail?**

If the answer is “probably something somewhere,” strengthen the test contract.

## Colocation rule

Every capability keeps tests in a `tests/` directory directly beneath the package it
protects:

```text
src/scholion/core/health_check.py
src/scholion/core/tests/test_health_check.py

src/scholion/interfaces/local_file_manager.py
src/scholion/interfaces/tests/test_local_file_manager.py
```

Repository-wide pytest configuration belongs in root `conftest.py`.

Shared fixtures stay at the narrowest package that needs them. Test packages are
excluded from built distributions.

This makes source-to-test navigation predictable without needing a test metadata system.

## Feedback ladder

Use the smallest trustworthy oracle first, then widen:

```text
one test node
    ↓
one capability file
    ↓
one package suite
    ↓
last failures
    ↓
full behavioral suite
    ↓
full branch coverage
    ↓
static / complexity / dead-code gates
    ↓
targeted mutation qualification
    ↓
build + clean-wheel + lock verification
```

Typical commands:

```bash
uv run pytest path/to/test.py::test_name
uv run pytest path/to/test.py
uv run pytest src/scholion/PACKAGE/tests
uv run pytest --last-failed
uv run pytest
uv run pytest --cov=scholion --cov-branch --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run vulture
uv run radon cc src/scholion --total-average
uv run radon mi src/scholion
```

The narrow test should answer the local question. The wide suite should answer whether
the change broke a contract you did not realize was adjacent.

## Mutation anticipation: think like a tiny malicious editor

Mutation testing should not be the first place Scholion discovers that tests are vague.

When changing load-bearing decision logic, enumerate plausible bad edits during test
design.

### Comparator and boundary mutations

Examples:

- `<` ↔ `<=`;
- `>` ↔ `>=`;
- `==` ↔ `!=`;
- zero/one/count/size/duration thresholds shifting by one; and
- percentages or schema versions drifting across a boundary.

Named tests should exist when the exact threshold is meaningful.

### Boolean and fallback mutations

Examples:

- `and` ↔ `or`;
- removed/inverted `not`;
- missing capability becoming success;
- an explicit strategy silently falling back;
- a security uncertainty becoming fail-open; and
- a provider/model/device being substituted without authorization.

### Arithmetic/accounting mutations

Examples:

- `+` ↔ `-`;
- double-counted or omitted memory/disk terms;
- rounding changes; and
- altered multipliers.

These matter especially in resource/storage admission.

### Ordering and lifecycle mutations

Examples:

- manifest committed before provider verification;
- checkpoint committed after work is exposed as resumable;
- publish/cleanup ordering reversed;
- speculative prefetched work leaked;
- derived audio not removed after failure; and
- cleanup error masking the primary exception.

### Resume/provenance mutations

Examples:

- mismatched source accepted;
- model revision changed;
- preprocessing changed halfway through a job;
- engine/runtime version mismatch ignored;
- execution target changed silently; and
- evidence/provenance fields omitted from durable artifacts.

### Concurrency mutations

Examples:

- prefetch depth increased beyond the admitted bound;
- worker count oversubscribed;
- future work committed out of order; and
- cleanup races leave unowned files behind.

💃 Mutation testing is not chaos testing. It is asking whether the test suite notices
plausible wrong code decisions.

## Hypothesis where the invariant spans many values

Property tests are particularly useful when the contract is easier to state than to
cover with examples.

Current semantic chunking is a good example: every generated source segment must appear
exactly once and in order regardless of word-count/profile combinations.

Named boundary cases remain valuable even when Hypothesis could generate them. A reader
should be able to see why a specific threshold is invalid without waiting for a
property-based failure seed.

## Model-custody mutation hypotheses

When model-management or ASR custody changes, tests should kill bad edits such as:

- failed structural verification treated as managed;
- manifest path escaping Scholion's model cache;
- provider repository identity substituted;
- recorded revision/snapshot path disagreeing;
- requested revision silently replaced;
- insufficient disk admitted before acquisition;
- manifest committed before verification;
- removal deleting the manifest before provider deletion succeeds;
- external model deletion leaving a stale manifest reported usable;
- transcription planning accepting an unmanaged ambient cache entry;
- configuration overriding managed revision identity;
- faster-whisper changing from `local_files_only=True` to network-capable resolution; or
- model/repository/revision/verification provenance disappearing.

There is no ASR transcription-time download fallback in the current pre-production
contract. Tests should not preserve obsolete behavior merely because an earlier branch
once had it.

## Enhancement mutation hypotheses

When optional speech enhancement changes, tests should kill:

- `off` invoking enhancement;
- `on` skipping enhancement;
- explicit enhancement failure silently falling back to raw audio;
- ASR reading raw audio after enhancement succeeded;
- diarization reading enhanced audio in the current v1 contract;
- provider/parameters changing without checkpoint incompatibility;
- enhanced full-recording storage omitted or double-counted;
- channel/sample-width/sample-rate/frame validation weakened;
- partial enhanced output surviving failure;
- cleanup skipped/duplicated/masking the primary error;
- provenance disappearing;
- original recording modified; or
- a future model-backed enhancer bypassing model custody.

“Enhancer was called” is not enough. Tests should prove **which path ASR actually
consumed** and which path diarization retained.

## Semantic/search mutation hypotheses

When transcript-library retrieval changes, ask whether tests would notice:

- stale semantic generations being accepted;
- canonical hashes disappearing from the corpus fingerprint;
- filters moving after top-K;
- chunk boundaries dropping/duplicating canonical segments;
- vector dimensions/normalization being accepted incorrectly;
- query/passage transforms being swapped;
- failed rebuild replacing valid semantic state;
- RRF arithmetic changing;
- timeline presentation overwriting relevance provenance; or
- local-only embedding restoration becoming network-capable.

See [semantic-retrieval-testing.md](semantic-retrieval-testing.md) for the focused matrix.

## Pre-production schema rule

Scholion currently has no released/dogfooded durable-schema compatibility obligation.

Tests protect **one current job-plan, checkpoint, and canonical-transcript contract**.

Do not retain obsolete pre-production branches solely because an earlier PR once emitted
them.

When a real compatibility boundary exists, add migration tests against actual persisted
fixtures from that boundary.

Until then, deleting unused compatibility scaffolding is usually safer than maintaining
fictional history.

## Sandbox readiness

A sandbox can run repository-local tools only when an Scholion checkout is actually
mounted.

When a checkout exists:

```bash
python scripts/prepare_dev_environment.py
```

This performs a locked development sync and verifies Poodle availability.

If the checkout is absent, inspect through the connected repository and use the manual
mutation workflow instead of pretending a local mutation run happened.

The environment is allowed to have boundaries. The documentation must tell the truth
about them. 🧜‍♀️

## Git bisect

A bisect oracle must be deterministic, noninteractive, and narrow enough to run many
times.

Start from known bad/good revisions and use the smallest test proving the regression:

```bash
git bisect start BAD GOOD
git bisect run uv run pytest src/scholion/core/tests/test_health_check.py -q
git bisect reset
```

Use a package/full-suite oracle only when a smaller contract cannot reproduce the
failure.

A test that depends on network access, mutable model cache, wall-clock timing, or mutable
user state is not a trustworthy bisect oracle until those inputs are controlled.

Model acquisition tests should fake the provider boundary. Enhancement-provider tests
should fake subprocess behavior or use generated local audio only when the native media
boundary itself is the subject.

## Source-to-test navigation

The path convention is the primary index: changed production files and their tests share
a package.

`rg`, `pytest --collect-only`, coverage, and Git's changed-file list cover current
navigation needs.

Static test-to-symbol mapping can use Python `ast` later if repository scale justifies
it. Tree-sitter would not improve Git bisect, pytest collection, or Python-only symbol
parsing today.

## The stable testing rule

**Make the smallest important wrong decision fail loudly. Then widen the evidence.**

That is much more useful than admiring a large green test count while one load-bearing
branch quietly has no witness. 🦝
