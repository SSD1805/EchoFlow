import re
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

_TOKEN_PATTERN = re.compile(r"\w+(?:['’]\w+)*", re.UNICODE)
_BM25_K1 = 1.2
_BM25_B = 0.75


def lexical_tokens(text: str) -> tuple[str, ...]:
    """Return deterministic, Unicode-aware lexical tokens for local ranking."""
    return tuple(match.group(0).casefold() for match in _TOKEN_PATTERN.finditer(text))


class DuckDbTranscriptIndex:
    """Rebuildable DuckDB transcript index with offline BM25 ranking.

    BM25 is calculated from term statistics stored in ordinary DuckDB tables. EchoFlow
    deliberately does not INSTALL/LOAD DuckDB's FTS extension because extension
    acquisition may require network access on a new machine.
    """

    def __init__(self, database_path: Path, file_manager: FileManagerFacade) -> None:
        self.database_path = database_path.expanduser().resolve(strict=False)
        self.file_manager = file_manager
        self.file_manager.ensure_directory_exists(self.database_path.parent, private=True)
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
            "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                transcript.document_id,
                transcript.source_sha256,
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
                "INSERT INTO segments VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    transcript.document_id,
                    segment.segment_id,
                    segment.start_seconds,
                    segment.end_seconds,
                    segment.text,
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
        self._connection.execute("DELETE FROM terms WHERE document_id = ?", [document_id])
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
            SELECT d.document_id, d.source_sha256, d.detected_language,
                   d.canonical_path, d.source_path, COUNT(s.segment_id)
            FROM documents d
            LEFT JOIN segments s USING (document_id)
            GROUP BY d.document_id, d.source_sha256, d.detected_language,
                     d.canonical_path, d.source_path
            ORDER BY d.document_id
            """
        ).fetchall()
        return tuple(
            IndexedDocument(
                document_id=str(row[0]),
                source_sha256=str(row[1]),
                detected_language=None if row[2] is None else str(row[2]),
                canonical_path=str(row[3]),
                source_path=None if row[4] is None else str(row[4]),
                segment_count=int(row[5]),
            )
            for row in rows
        )

    def search(self, query: SearchQuery) -> tuple[TranscriptMatch, ...]:
        self._require_open()
        tokens = tuple(dict.fromkeys(lexical_tokens(query.text)))
        if not tokens:
            raise ValueError("query text must contain at least one searchable token")
        values = ", ".join("(?)" for _ in tokens)
        filters, parameters = self._filters(query)
        required_terms = len(tokens) if query.operator is SearchOperator.ALL else 1
        order = (
            "s.document_id, s.start_seconds, s.segment_id"
            if query.sort is SearchSort.TIMELINE
            else "score DESC, s.document_id, s.start_seconds, s.segment_id"
        )
        sql = f"""  # noqa: S608
            WITH query_terms(term) AS (VALUES {values}),
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
                               (t.term_frequency * ({_BM25_K1} + 1.0)) /
                               (t.term_frequency + {_BM25_K1} * (
                                   1.0 - {_BM25_B} + {_BM25_B} *
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
            WHERE scores.matched_terms >= ?{filters}
            ORDER BY {order}
            LIMIT ?
        """
        rows = self._connection.execute(
            sql,
            [*tokens, required_terms, *parameters, query.limit],
        ).fetchall()
        return tuple(self._match(row) for row in rows)

    @staticmethod
    def _filters(query: SearchQuery) -> tuple[str, list[object]]:
        clauses: list[str] = []
        parameters: list[object] = []
        if query.phrase:
            clauses.append("strpos(lower(s.text), lower(?)) > 0")
            parameters.append(query.text.strip())
        for column, values in (
            ("s.speaker_ref", query.speaker_refs),
            ("s.language", query.languages),
            ("s.document_id", query.document_ids),
        ):
            if values:
                placeholders = ", ".join("?" for _ in values)
                clauses.append(f"{column} IN ({placeholders})")
                parameters.extend(values)
        if not clauses:
            return "", parameters
        return " AND " + " AND ".join(clauses), parameters

    @staticmethod
    def _match(row: tuple[object, ...]) -> TranscriptMatch:
        return TranscriptMatch(
            document_id=str(row[0]),
            source_sha256=str(row[1]),
            canonical_path=str(row[2]),
            source_path=None if row[3] is None else str(row[3]),
            segment_id=str(row[4]),
            start_seconds=float(row[5]),
            end_seconds=float(row[6]),
            text=str(row[7]),
            language=None if row[8] is None else str(row[8]),
            speaker_ref=None if row[9] is None else str(row[9]),
            score=float(row[10]),
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
