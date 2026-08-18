from collections import Counter
from pathlib import Path

import duckdb

from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.library.index import (
    IndexedDocument,
    IndexedTranscript,
    SearchOperator,
    SearchQuery,
    SearchSort,
    TranscriptMatch,
)
from echoflow.library.text import lexical_tokens

_SEARCH_SQL_PREFIX = """
    WITH query_terms AS (
        SELECT UNNEST(?::VARCHAR[]) AS term
    ),
    corpus AS (
        SELECT COUNT(*)::DOUBLE AS segment_count,
               COALESCE(AVG(token_count), 0)::DOUBLE AS average_length
        FROM segments
    ),
    document_frequency AS (
        SELECT t.term, COUNT(*)::DOUBLE AS frequency
        FROM terms t
        JOIN query_terms q USING (term)
        GROUP BY t.term
    ),
    scores AS (
        SELECT t.document_id, t.segment_id,
               COUNT(DISTINCT t.term) AS matched_terms,
               SUM(
                   ln(1.0 + (
                       (c.segment_count - df.frequency + 0.5) /
                       (df.frequency + 0.5)
                   )) * (
                       (t.term_frequency * 2.2) /
                       (t.term_frequency + 1.2 * (
                           0.25 + 0.75 *
                           s.token_count / NULLIF(c.average_length, 0)
                       ))
                   )
               ) AS score
        FROM terms t
        JOIN query_terms q USING (term)
        JOIN document_frequency df USING (term)
        JOIN segments s USING (document_id, segment_id)
        CROSS JOIN corpus c
        GROUP BY t.document_id, t.segment_id
    )
    SELECT s.document_id, d.source_sha256, d.canonical_path, d.source_path,
           s.segment_id, s.start_seconds, s.end_seconds, s.text,
           s.language, s.speaker_ref, scores.score
    FROM scores
    JOIN segments s USING (document_id, segment_id)
    JOIN documents d USING (document_id)
    WHERE scores.matched_terms >= ?
      AND (? = FALSE OR strpos(s.normalized_text, ?) > 0)
      AND (? = FALSE OR list_contains(?::VARCHAR[], s.speaker_ref))
      AND (? = FALSE OR list_contains(?::VARCHAR[], s.language))
      AND (? = FALSE OR list_contains(?::VARCHAR[], s.document_id))
"""
_RELEVANCE_SEARCH_SQL = (
    _SEARCH_SQL_PREFIX
    + "ORDER BY score DESC, s.document_id, s.start_seconds, s.segment_id LIMIT ?"
)
_TIMELINE_SEARCH_SQL = (
    _SEARCH_SQL_PREFIX + "ORDER BY s.document_id, s.start_seconds, s.segment_id LIMIT ?"
)


def _numeric_cell(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"DuckDB returned an invalid numeric {field}")
    return float(value)


class DuckDbTranscriptIndex:
    """Rebuildable DuckDB transcript index with offline BM25 ranking.

    BM25 is calculated from term statistics stored in ordinary DuckDB tables. EchoFlow
    deliberately does not INSTALL/LOAD DuckDB's FTS extension because extension
    acquisition may require network access on a new machine.
    """

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
        return "duckdb-bm25-v1"

    def _initialize(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                document_id VARCHAR PRIMARY KEY,
                source_sha256 VARCHAR NOT NULL,
                canonical_sha256 VARCHAR,
                transcript_schema_version INTEGER NOT NULL,
                detected_language VARCHAR,
                canonical_path VARCHAR NOT NULL,
                source_path VARCHAR,
                source_size_bytes BIGINT NOT NULL,
                source_modified_ns BIGINT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS segments (
                document_id VARCHAR NOT NULL,
                segment_id VARCHAR NOT NULL,
                start_seconds DOUBLE NOT NULL,
                end_seconds DOUBLE NOT NULL,
                text VARCHAR NOT NULL,
                normalized_text VARCHAR NOT NULL,
                language VARCHAR,
                speaker_ref VARCHAR,
                token_count INTEGER NOT NULL,
                PRIMARY KEY (document_id, segment_id)
            );
            CREATE TABLE IF NOT EXISTS terms (
                document_id VARCHAR NOT NULL,
                segment_id VARCHAR NOT NULL,
                term VARCHAR NOT NULL,
                term_frequency INTEGER NOT NULL,
                PRIMARY KEY (document_id, segment_id, term)
            );
            """
        )
        self._connection.execute(
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS canonical_sha256 VARCHAR"
        )

    def rebuild(self, transcripts: tuple[IndexedTranscript, ...]) -> None:
        self._require_open()
        self._connection.execute("BEGIN TRANSACTION")
        try:
            self._clear_tables()
            for transcript in transcripts:
                self._insert_transcript(transcript)
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise

    def upsert(self, transcript: IndexedTranscript) -> None:
        self._require_open()
        self._connection.execute("BEGIN TRANSACTION")
        try:
            self._delete_document(transcript.document_id)
            self._insert_transcript(transcript)
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise

    def _insert_transcript(self, transcript: IndexedTranscript) -> None:
        self._connection.execute(
            """
            INSERT INTO documents (
                document_id,
                source_sha256,
                canonical_sha256,
                transcript_schema_version,
                detected_language,
                canonical_path,
                source_path,
                source_size_bytes,
                source_modified_ns
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                transcript.document_id,
                transcript.source_sha256,
                transcript.canonical_sha256,
                transcript.transcript_schema_version,
                transcript.detected_language,
                transcript.canonical_path,
                transcript.source_path,
                transcript.source_size_bytes,
                transcript.source_modified_ns,
            ],
        )
        for segment in transcript.segments:
            tokens = lexical_tokens(segment.text)
            self._connection.execute(
                "INSERT INTO segments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    transcript.document_id,
                    segment.segment_id,
                    segment.start_seconds,
                    segment.end_seconds,
                    segment.text,
                    segment.text.casefold(),
                    segment.language,
                    segment.speaker_ref,
                    len(tokens),
                ],
            )
            for term, frequency in Counter(tokens).items():
                self._connection.execute(
                    "INSERT INTO terms VALUES (?, ?, ?, ?)",
                    [
                        transcript.document_id,
                        segment.segment_id,
                        term,
                        frequency,
                    ],
                )

    def remove(self, document_id: str) -> None:
        self._require_open()
        if not document_id.strip():
            raise ValueError("document_id cannot be empty")
        self._connection.execute("BEGIN TRANSACTION")
        try:
            self._delete_document(document_id)
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise

    def _delete_document(self, document_id: str) -> None:
        self._connection.execute(
            "DELETE FROM terms WHERE document_id = ?", [document_id]
        )
        self._connection.execute(
            "DELETE FROM segments WHERE document_id = ?", [document_id]
        )
        self._connection.execute(
            "DELETE FROM documents WHERE document_id = ?", [document_id]
        )

    def contains(self, document_id: str) -> bool:
        self._require_open()
        row = self._connection.execute(
            "SELECT 1 FROM documents WHERE document_id = ? LIMIT 1", [document_id]
        ).fetchone()
        return row is not None

    def documents(self) -> tuple[IndexedDocument, ...]:
        self._require_open()
        rows = self._connection.execute(
            """
            SELECT d.document_id, d.source_sha256, d.canonical_sha256,
                   d.detected_language, d.canonical_path, d.source_path,
                   COUNT(s.segment_id)
            FROM documents d
            LEFT JOIN segments s USING (document_id)
            GROUP BY d.document_id, d.source_sha256, d.canonical_sha256,
                     d.detected_language, d.canonical_path, d.source_path
            ORDER BY d.document_id
            """
        ).fetchall()
        return tuple(
            IndexedDocument(
                document_id=str(row[0]),
                source_sha256=str(row[1]),
                canonical_sha256=None if row[2] is None else str(row[2]),
                detected_language=None if row[3] is None else str(row[3]),
                canonical_path=str(row[4]),
                source_path=None if row[5] is None else str(row[5]),
                segment_count=int(row[6]),
            )
            for row in rows
        )

    def search(self, query: SearchQuery) -> tuple[TranscriptMatch, ...]:
        self._require_open()
        tokens = tuple(dict.fromkeys(lexical_tokens(query.text)))
        if not tokens:
            raise ValueError("query text must contain at least one searchable token")
        required_terms = len(tokens) if query.operator is SearchOperator.ALL else 1
        sql = (
            _TIMELINE_SEARCH_SQL
            if query.sort is SearchSort.TIMELINE
            else _RELEVANCE_SEARCH_SQL
        )
        rows = self._connection.execute(
            sql,
            [
                list(tokens),
                required_terms,
                query.phrase,
                query.text.strip().casefold(),
                bool(query.speaker_refs),
                list(query.speaker_refs),
                bool(query.languages),
                list(query.languages),
                bool(query.document_ids),
                list(query.document_ids),
                query.limit,
            ],
        ).fetchall()
        return tuple(self._match(row) for row in rows)

    @staticmethod
    def _match(row: tuple[object, ...]) -> TranscriptMatch:
        return TranscriptMatch(
            document_id=str(row[0]),
            source_sha256=str(row[1]),
            canonical_path=str(row[2]),
            source_path=None if row[3] is None else str(row[3]),
            segment_id=str(row[4]),
            start_seconds=_numeric_cell(row[5], "start_seconds"),
            end_seconds=_numeric_cell(row[6], "end_seconds"),
            text=str(row[7]),
            language=None if row[8] is None else str(row[8]),
            speaker_ref=None if row[9] is None else str(row[9]),
            score=_numeric_cell(row[10], "score"),
        )

    def clear(self) -> None:
        self._require_open()
        self._clear_tables()

    def _clear_tables(self) -> None:
        self._connection.execute("DELETE FROM terms")
        self._connection.execute("DELETE FROM segments")
        self._connection.execute("DELETE FROM documents")

    def close(self) -> None:
        if self._closed:
            return
        self._connection.close()
        self._closed = True

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("transcript index is closed")
