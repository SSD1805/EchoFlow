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
