import json
import math
from pathlib import Path

import duckdb

from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.library.duckdb_index import lexical_tokens
from echoflow.library.index import SearchOperator, SearchQuery
from echoflow.library.semantic import (
    EmbeddingProfile,
    EmbeddingVector,
    EvidenceKey,
    SearchChunk,
    SemanticCandidate,
    SemanticState,
)


class DuckDbSemanticIndex:
    """Exact local vector retrieval over rebuildable DuckDB numeric arrays."""

    def __init__(self, database_path: Path, file_manager: FileManagerFacade) -> None:
        self.database_path = database_path.expanduser().resolve(strict=False)
        self.file_manager = file_manager
        self.file_manager.ensure_directory_exists(
            self.database_path.parent, private=True
        )
        self._connection = duckdb.connect(str(self.database_path))
        self._closed = False
        self._initialize()

    @property
    def backend_id(self) -> str:
        return "duckdb-exact-vector-v1"

    def _initialize(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS embedding_profiles (
                profile_id VARCHAR PRIMARY KEY,
                provider VARCHAR NOT NULL,
                model_id VARCHAR NOT NULL,
                resolved_revision VARCHAR NOT NULL,
                dimensions INTEGER NOT NULL,
                normalization VARCHAR NOT NULL,
                pooling VARCHAR NOT NULL,
                distance_metric VARCHAR NOT NULL,
                query_prefix VARCHAR NOT NULL,
                passage_prefix VARCHAR NOT NULL,
                chunking_profile_id VARCHAR NOT NULL,
                snapshot_path VARCHAR NOT NULL,
                embedding_schema_version INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS semantic_state (
                singleton INTEGER PRIMARY KEY,
                profile_id VARCHAR NOT NULL,
                corpus_fingerprint VARCHAR NOT NULL,
                chunk_count INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id VARCHAR PRIMARY KEY,
                document_id VARCHAR NOT NULL,
                source_sha256 VARCHAR NOT NULL,
                canonical_sha256 VARCHAR NOT NULL,
                canonical_path VARCHAR NOT NULL,
                source_path VARCHAR,
                segment_ids_json VARCHAR NOT NULL,
                first_segment_id VARCHAR NOT NULL,
                last_segment_id VARCHAR NOT NULL,
                start_seconds DOUBLE NOT NULL,
                end_seconds DOUBLE NOT NULL,
                text VARCHAR NOT NULL,
                normalized_text VARCHAR NOT NULL,
                content_sha256 VARCHAR NOT NULL,
                chunking_profile_id VARCHAR NOT NULL,
                languages_json VARCHAR NOT NULL,
                speaker_refs_json VARCHAR NOT NULL
            );
            CREATE TABLE IF NOT EXISTS embeddings (
                chunk_id VARCHAR NOT NULL,
                profile_id VARCHAR NOT NULL,
                vector FLOAT[] NOT NULL,
                PRIMARY KEY (chunk_id, profile_id)
            );
            """
        )

    def rebuild(
        self,
        *,
        state: SemanticState,
        chunks: tuple[SearchChunk, ...],
        vectors: tuple[EmbeddingVector, ...],
    ) -> None:
        self._require_open()
        if len(chunks) != len(vectors):
            raise ValueError("semantic chunk and vector counts must match")
        if state.chunk_count != len(chunks):
            raise ValueError("semantic state chunk count does not match chunks")
        if any(
            chunk.chunking_profile_id != state.profile.chunking_profile_id
            for chunk in chunks
        ):
            raise ValueError("chunking profile does not match embedding profile")
        for vector in vectors:
            self._validate_vector(vector, state.profile.dimensions)

        self._connection.execute("BEGIN TRANSACTION")
        try:
            self._clear_tables()
            self._insert_profile(state.profile)
            self._connection.execute(
                "INSERT INTO semantic_state VALUES (1, ?, ?, ?)",
                [
                    state.profile.profile_id,
                    state.corpus_fingerprint,
                    state.chunk_count,
                ],
            )
            for chunk, vector in zip(chunks, vectors, strict=True):
                self._insert_chunk(chunk)
                self._connection.execute(
                    "INSERT INTO embeddings VALUES (?, ?, ?)",
                    [chunk.chunk_id, state.profile.profile_id, list(vector)],
                )
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise

    def _insert_profile(self, profile: EmbeddingProfile) -> None:
        self._connection.execute(
            "INSERT INTO embedding_profiles VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            list(profile.identity_tuple()),
        )

    def _insert_chunk(self, chunk: SearchChunk) -> None:
        self._connection.execute(
            "INSERT INTO chunks VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                chunk.chunk_id,
                chunk.document_id,
                chunk.source_sha256,
                chunk.canonical_sha256,
                chunk.canonical_path,
                chunk.source_path,
                json.dumps(chunk.segment_ids),
                chunk.first_segment_id,
                chunk.last_segment_id,
                chunk.start_seconds,
                chunk.end_seconds,
                chunk.text,
                chunk.text.casefold(),
                chunk.content_sha256,
                chunk.chunking_profile_id,
                json.dumps(chunk.languages),
                json.dumps(chunk.speaker_refs),
            ],
        )

    def state(self) -> SemanticState | None:
        self._require_open()
        row = self._connection.execute(
            """
            SELECT p.profile_id, p.provider, p.model_id, p.resolved_revision,
                   p.dimensions, p.normalization, p.pooling, p.distance_metric,
                   p.query_prefix, p.passage_prefix, p.chunking_profile_id,
                   p.snapshot_path, p.embedding_schema_version,
                   s.corpus_fingerprint, s.chunk_count
            FROM semantic_state s
            JOIN embedding_profiles p USING (profile_id)
            WHERE s.singleton = 1
            """
        ).fetchone()
        if row is None:
            return None
        return SemanticState(
            profile=EmbeddingProfile(
                profile_id=str(row[0]),
                provider=str(row[1]),
                model_id=str(row[2]),
                resolved_revision=str(row[3]),
                dimensions=int(row[4]),
                normalization=str(row[5]),
                pooling=str(row[6]),
                distance_metric=str(row[7]),
                query_prefix=str(row[8]),
                passage_prefix=str(row[9]),
                chunking_profile_id=str(row[10]),
                snapshot_path=str(row[11]),
                embedding_schema_version=int(row[12]),
            ),
            corpus_fingerprint=str(row[13]),
            chunk_count=int(row[14]),
        )

    def search(
        self, query: SearchQuery, query_vector: EmbeddingVector
    ) -> tuple[SemanticCandidate, ...]:
        self._require_open()
        state = self.state()
        if state is None:
            return ()
        self._validate_vector(query_vector, state.profile.dimensions)
        rows = self._connection.execute(
            """
            SELECT c.chunk_id, c.document_id, c.source_sha256, c.canonical_sha256,
                   c.canonical_path, c.source_path, c.segment_ids_json,
                   c.first_segment_id, c.last_segment_id, c.start_seconds,
                   c.end_seconds, c.text, c.content_sha256,
                   c.chunking_profile_id, c.languages_json, c.speaker_refs_json,
                   e.vector
            FROM chunks c
            JOIN embeddings e USING (chunk_id)
            WHERE e.profile_id = ?
            """,
            [state.profile.profile_id],
        ).fetchall()

        candidates: list[SemanticCandidate] = []
        for row in rows:
            chunk = self._chunk(row)
            if not self._matches_filters(chunk, query):
                continue
            vector = self._vector_cell(row[16], state.profile.dimensions)
            score = sum(
                query_value * passage_value
                for query_value, passage_value in zip(
                    query_vector, vector, strict=True
                )
            )
            candidates.append(SemanticCandidate(chunk=chunk, score=score))
        candidates.sort(
            key=lambda candidate: (
                -candidate.score,
                candidate.chunk.document_id,
                candidate.chunk.start_seconds,
                candidate.chunk.chunk_id,
            )
        )
        return tuple(candidates[: query.limit])

    def chunks_for_segments(
        self, keys: tuple[EvidenceKey, ...]
    ) -> dict[EvidenceKey, SearchChunk]:
        self._require_open()
        if not keys:
            return {}
        wanted = set(keys)
        rows = self._connection.execute(
            """
            SELECT chunk_id, document_id, source_sha256, canonical_sha256,
                   canonical_path, source_path, segment_ids_json,
                   first_segment_id, last_segment_id, start_seconds,
                   end_seconds, text, content_sha256, chunking_profile_id,
                   languages_json, speaker_refs_json
            FROM chunks
            """
        ).fetchall()
        result: dict[EvidenceKey, SearchChunk] = {}
        for row in rows:
            chunk = self._chunk(row)
            for segment_id in chunk.segment_ids:
                key = (chunk.document_id, segment_id)
                if key in wanted:
                    result[key] = chunk
        return result

    @staticmethod
    def _matches_filters(chunk: SearchChunk, query: SearchQuery) -> bool:
        if query.document_ids and chunk.document_id not in query.document_ids:
            return False
        if query.languages and not set(chunk.languages).intersection(query.languages):
            return False
        if query.speaker_refs and not set(chunk.speaker_refs).intersection(
            query.speaker_refs
        ):
            return False
        normalized = chunk.text.casefold()
        if query.phrase and query.text.strip().casefold() not in normalized:
            return False
        if query.operator is SearchOperator.ALL:
            terms = tuple(dict.fromkeys(lexical_tokens(query.text)))
            present_terms = set(lexical_tokens(chunk.text))
            if terms and any(term not in present_terms for term in terms):
                return False
        return True

    @staticmethod
    def _chunk(row: tuple[object, ...]) -> SearchChunk:
        segment_ids = DuckDbSemanticIndex._string_tuple(row[6], "segment_ids")
        languages = DuckDbSemanticIndex._string_tuple(row[14], "languages")
        speaker_refs = DuckDbSemanticIndex._string_tuple(row[15], "speaker_refs")
        return SearchChunk(
            chunk_id=str(row[0]),
            document_id=str(row[1]),
            source_sha256=str(row[2]),
            canonical_sha256=str(row[3]),
            canonical_path=str(row[4]),
            source_path=None if row[5] is None else str(row[5]),
            segment_ids=segment_ids,
            first_segment_id=str(row[7]),
            last_segment_id=str(row[8]),
            start_seconds=DuckDbSemanticIndex._numeric_cell(row[9], "start_seconds"),
            end_seconds=DuckDbSemanticIndex._numeric_cell(row[10], "end_seconds"),
            text=str(row[11]),
            content_sha256=str(row[12]),
            chunking_profile_id=str(row[13]),
            languages=languages,
            speaker_refs=speaker_refs,
        )

    @staticmethod
    def _string_tuple(value: object, field: str) -> tuple[str, ...]:
        if not isinstance(value, str):
            raise RuntimeError(f"DuckDB returned invalid {field}")
        parsed = json.loads(value)
        if not isinstance(parsed, list) or any(
            not isinstance(item, str) for item in parsed
        ):
            raise RuntimeError(f"DuckDB returned invalid {field}")
        return tuple(parsed)

    @staticmethod
    def _numeric_cell(value: object, field: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RuntimeError(f"DuckDB returned invalid numeric {field}")
        return float(value)

    @staticmethod
    def _vector_cell(value: object, dimensions: int) -> EmbeddingVector:
        if not isinstance(value, (list, tuple)):
            raise RuntimeError("DuckDB returned an invalid embedding vector")
        try:
            vector = tuple(float(item) for item in value)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("DuckDB returned an invalid embedding vector") from exc
        DuckDbSemanticIndex._validate_vector(vector, dimensions)
        return vector

    @staticmethod
    def _validate_vector(vector: EmbeddingVector, dimensions: int) -> None:
        if len(vector) != dimensions:
            raise ValueError("embedding vector has unexpected dimensions")
        if any(not math.isfinite(value) for value in vector):
            raise ValueError("embedding vector contains non-finite values")
        norm = math.sqrt(sum(value * value for value in vector))
        if not math.isclose(norm, 1.0, rel_tol=1e-4, abs_tol=1e-4):
            raise ValueError("embedding vector must be l2-normalized")

    def clear(self) -> None:
        self._require_open()
        self._clear_tables()

    def _clear_tables(self) -> None:
        self._connection.execute("DELETE FROM embeddings")
        self._connection.execute("DELETE FROM chunks")
        self._connection.execute("DELETE FROM semantic_state")
        self._connection.execute("DELETE FROM embedding_profiles")

    def close(self) -> None:
        if self._closed:
            return
        self._connection.close()
        self._closed = True

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("semantic index is closed")
