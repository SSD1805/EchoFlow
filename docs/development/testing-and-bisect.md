# Testing and regression bisection

## Colocation rule

Every capability keeps tests in a `tests/` directory directly beneath the
package it protects:

```text
src/echoflow/core/health_check.py
src/echoflow/core/tests/test_health_check.py

src/echoflow/interfaces/local_file_manager.py
src/echoflow/interfaces/tests/test_local_file_manager.py
```

Repository-wide pytest configuration belongs in root `conftest.py`. Shared
fixtures should remain local to the narrowest package that needs them. Test
packages are excluded from built distributions.

## Feedback ladder

Use the smallest trustworthy oracle first, then widen it:

1. One test node:
   `uv run pytest src/echoflow/core/tests/test_health_check.py::test_name`
2. One capability suite:
   `uv run pytest src/echoflow/core/tests/test_health_check.py`
3. One package suite:
   `uv run pytest src/echoflow/core/tests`
4. Tests that failed most recently:
   `uv run pytest --last-failed`
5. Full behavioral suite:
   `uv run pytest`
6. Full branch coverage:
   `uv run pytest --cov=echoflow --cov-branch --cov-report=term-missing`
7. Static and metric gates:
   `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`,
   `uv run vulture`, and `uv run radon cc src/echoflow --total-average`
8. Targeted mutation scope for changed decision logic, followed by package
   build and lock verification.

## Mutation anticipation rule

Mutation testing is not the first place EchoFlow should discover weak test
contracts. For load-bearing decision logic, define the plausible bad edits while
designing the tests and identify which test is expected to kill each one.

At minimum, review changed decision logic for these mutation families:

- boundary/operator changes such as `<` vs `<=`, `>` vs `>=`, `==` vs `!=`;
- Boolean changes such as `and` vs `or`, removed `not`, or inverted predicates;
- threshold and constant perturbations around `0`, `1`, counts, sizes, durations,
  percentages, schema versions, and resource limits;
- arithmetic/accounting changes such as `+` vs `-`, omitted terms, double counting,
  integer rounding, or changed multipliers;
- fallback mutations that silently downgrade, upgrade, or select a different
  provider/device/model than requested;
- fail-open mutations where an exception, missing capability, malformed probe, or
  uncertain security condition is treated as success;
- ordering mutations around checkpoint, persistence, publish, cleanup, cancellation,
  and provenance writes;
- ownership/lifecycle mutations such as skipped cleanup, double cleanup, leaked
  prefetched work, or reuse of stale state;
- resume/idempotence mutations that accept mismatched identity, engine, source,
  version, or execution contracts;
- provenance/serialization mutations that omit or alter fields needed to explain how
  an artifact was produced;
- concurrency mutations such as increased prefetch depth, oversubscription, changed
  worker counts, or out-of-order commits.

The preferred test shape is explicit: positive case, negative case, boundary case,
and failure-path assertion where the contract warrants them. Property-based tests are
preferred for invariants spanning many values, but they do not replace named boundary
examples for safety-relevant decisions.

A useful review question is: **if this comparator, Boolean, threshold, fallback, or
ordering decision were subtly wrong, which exact test would fail?** If there is no
clear answer, strengthen the test plan before relying on Poodle to discover the gap.

Run Poodle only after ordinary tests are green and only over the smallest relevant
module set. Inspect survivors as evidence about test strength, not as a requirement to
mutate the entire repository on every commit. Routine CI does not gate on mutation
sweeps; use the manual GitHub workflow or an available local/sandbox checkout for
deliberate qualification.

## Sandbox readiness

A sandbox can only run repository-local tools when it actually has an EchoFlow
checkout. The repository cannot force an external execution environment to mount that
checkout, so every coding session must verify the workspace before claiming local
mutation capability.

When a checkout is available, prepare it with:

```bash
python scripts/prepare_dev_environment.py
```

That command performs a locked development sync and verifies that Poodle is runnable.
If the checkout is absent, use the connected GitHub repository for inspection and the
manual mutation workflow for qualification rather than asking a developer to wait on
per-commit mutation CI.

## Git bisect

A bisect command must be deterministic, noninteractive, and narrow enough to
run repeatedly. Start from a known bad revision and a known good revision, then
let Git invoke the smallest test that proves the regression:

```bash
git bisect start BAD GOOD
git bisect run uv run pytest src/echoflow/core/tests/test_health_check.py -q
git bisect reset
```

Use a package or full-suite oracle only when a single contract cannot reproduce
the failure. A test that depends on the network, local model cache, wall-clock
timing, or mutable user state is not a valid bisect oracle until those inputs
are controlled.

## Source-to-test navigation

The path convention is the primary index: a changed production file and its
tests share a package. `rg`, `pytest --collect-only`, coverage, and Git's changed
file list cover the present navigation needs. Static test-to-symbol mapping can
use Python `ast` later if the repository becomes large enough to justify it.
Tree-sitter would not improve Git bisect, pytest collection, or Python-only
symbol parsing today.
