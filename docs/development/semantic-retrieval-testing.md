# Semantic retrieval qualification

Transcript Library V2 is decision-heavy code. Its tests protect evidence custody,
chunking, vector-space coherence, filter ordering, stale-index rejection, and hybrid
ranking. A high line count by itself is not enough.

## Qualification matrix

The semantic tranche uses several complementary test styles.

| Test style | What it protects | Current examples |
|---|---|---|
| Positive | intended retrieval behavior | deterministic chunks, exact vector ranking, RRF fusion |
| Negative | fail-closed behavior | stale corpus, missing model, malformed vectors, embedding failure |
| Boundary | thresholds and invalid contracts | chunk target/max sizes, indivisible oversize source segments |
| Property-based | invariants over many generated cases | every source segment appears exactly once in deterministic chunks |
| Integration | cross-component behavior | canonical JSON → projection → vectors → DuckDB → hybrid search |
| Mutation | strength of decision tests | targeted Poodle workflow for semantic/retrieval/service modules |

Factory Boy is intentionally not introduced for this capability. The tested objects are
small immutable domain values rather than ORM graphs. Narrow builders and Hypothesis
strategies provide the useful construction behavior without another dependency.

## Hypothesis invariants

`src/echoflow/library/tests/test_semantic.py` generates varied segment word counts and
chunking thresholds and checks these invariants:

- the same input/profile produces the same chunks and IDs;
- every canonical segment appears exactly once in the flattened chunk sequence;
- no chunk invents or drops an evidence coordinate;
- chunk timestamps are inherited from the first/last canonical segments;
- exceeding `max_words` is allowed only when one indivisible source segment is itself
  larger than the maximum.

Keep named examples for important boundaries even when a property test could generate
them. A future maintainer should be able to see why `target_words=0` and
`max_words < target_words` are invalid without reverse-engineering a strategy.

## Embedding-provider failure cases

The E5 adapter tests should reject at least:

- unavailable snapshot directory;
- snapshot/revision mismatch;
- blank input text;
- wrong number of output vectors;
- wrong vector dimensions;
- non-finite values;
- vectors that violate the declared L2-normalized contract.

The model runtime is faked for these tests. Qualification must not require downloading a
model or sending text to an external service.

## Projection and service failure cases

The service/index tests protect:

- hard metadata/phrase constraints before semantic top-K;
- invalid semantic replacement leaving previous state intact;
- embedding failure leaving the previous semantic generation intact;
- canonical transcript changes invalidating stale semantic vectors;
- lexical search remaining available without semantic capability;
- a non-E5 fake provider satisfying the application-level `EmbeddingProvider` contract.

The last case matters for architecture: the library core is provider-agnostic even
though the normal CLI currently qualifies one concrete local E5 profile.

## Mutation testing

Run the dedicated manual workflow:

```text
.github/workflows/mutation-library.yml
```

It establishes a focused semantic-library baseline and asks Poodle to mutate:

```text
src/echoflow/library/semantic.py
src/echoflow/library/duckdb_semantic.py
src/echoflow/library/retrieval.py
src/echoflow/library/service.py
```

The mutations we care about include:

- changing chunk boundary comparisons;
- accepting stale corpus fingerprints;
- weakening vector dimension/normalization checks;
- applying filters after top-K;
- changing RRF rank arithmetic;
- claiming lexical/semantic/fused ranks when that retrieval path did not run;
- replacing semantic state after a failed build;
- mixing incompatible embedding profiles;
- turning a local-only model path into a network-capable resolution path.

Mutation testing remains a deliberate qualification tool, not a routine PR gate. Run it
when these decisions change and inspect surviving mutations as evidence of a missing test
contract.

## Feedback ladder for this capability

```bash
# Focused semantic/domain tests
uv run pytest src/echoflow/library/tests/test_semantic.py

# Full library package
uv run pytest src/echoflow/library/tests

# CLI boundary
uv run pytest src/echoflow/tests/test_cli_library.py

# Full branch coverage
uv run pytest --cov=echoflow --cov-branch --cov-report=term-missing

# Static gates
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run vulture
```

The repository-wide branch-coverage gate remains 90%. A semantic change is not considered
qualified merely because its focused tests pass if the full quality workflow is red.
