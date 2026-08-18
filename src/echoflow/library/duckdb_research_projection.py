"""DuckDB query projection derived from authoritative SQLite research state."""

from __future__ import annotations

from pathlib import Path

import duckdb

from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.library.errors import ResearchProjectionError
from echoflow.library.index import EvidenceScopeKey
from echoflow.library.research_projection import (
    ProjectedEvidenceSummary,
    ResearchProjectionFilter,
)
from echoflow.library.research_state import ResearchProjectionRecord
from echoflow.library.text import lexical_tokens

_SCHEMA_VERSION = 1


class DuckDbResearchProjection:
    """Disposable note/tag/collection projection for fast corpus filtering."""

    def __init__(self, database_path: Path, file_manager: FileManagerFacade) -> None:
        self.database_path = database_path.expanduser().resolve(strict=False)
        self.file_manager = file_manager
        self.file_manager.ensure_directory_exists(self.database_path.parent, private=True)
        try:
            self._connection = duckdb.connect(str(self.database_path))
            self._closed = False
            self._initialize()
        except duckdb.Error as exc:
            raise ResearchProjectionError(
                "Research query projection could not be opened", cause=exc
            ) from exc

    @property
    def backend_id(self) -> str:
        return "duckdb-research-projection-v1"

    def projected_through_sequence(self) -> int:
        self._require_open()
        try:
            row = self._connection.execute(
                "SELECT projected_through_sequence FROM projection_metadata WHERE singleton = 1"
            ).fetchone()
        except duckdb.Error as exc:
            raise ResearchProjectionError(
                "Research projection watermark could not be read", cause=exc
            ) from exc
        if row is None:
            raise ResearchProjectionError("Research projection metadata is missing")
        return int(row[0])

    def rebuild(
        self,
        records: tuple[ResearchProjectionRecord, ...],
        *,
        through_sequence: int,
    ) -> None:
        self._require_open()
        if through_sequence < 0:
            raise ValueError("projection sequence cannot be negative")
        self._connection.execute("BEGIN TRANSACTION")
        try:
            self._clear_rows()
            for record in records:
                self._insert_record(record)
            self._set_watermark(through_sequence)
            self._connection.execute("COMMIT")
        except Exception as exc:
            self._connection.execute("ROLLBACK")
            if isinstance(exc, (KeyboardInterrupt, SystemExit, ValueError)):
                raise
            raise ResearchProjectionError(
                "Research query projection could not be rebuilt safely", cause=exc
            ) from exc

    def apply(
        self,
        records: tuple[ResearchProjectionRecord, ...],
        *,
        deleted_note_ids: tuple[str, ...],
        through_sequence: int,
    ) -> None:
        self._require_open()
        current = self.projected_through_sequence()
        if through_sequence < current:
            raise ResearchProjectionError(
                "Research projection cannot move its watermark backwards"
            )
        touched = tuple(record.note_id for record in records) + deleted_note_ids
        if len(touched) != len(set(touched)):
            raise ValueError("projection batch contains duplicate note identities")
        self._connection.execute("BEGIN TRANSACTION")
        try:
            for note_id in touched:
                self._delete_note(note_id)
            for record in records:
                self._insert_record(record)
            self._set_watermark(through_sequence)
            self._connection.execute("COMMIT")
        except Exception as exc:
            self._connection.execute("ROLLBACK")
            if isinstance(exc, (KeyboardInterrupt, SystemExit, ValueError)):
                raise
            raise ResearchProjectionError(
                "Research query projection could not apply a change batch safely",
                cause=exc,
            ) from exc

    def matching_evidence(
        self, filters: ResearchProjectionFilter
    ) -> tuple[EvidenceScopeKey, ...]:
        self._require_open()
        terms = tuple(dict.fromkeys(lexical_tokens(filters.note_text or "")))
        if filters.note_text is not None and not terms:
            return ()
        try:
            rows = self._connection.execute(
                """
                WITH requested_tags AS (
                    SELECT UNNEST(?::VARCHAR[]) AS tag_id
                ),
                requested_collections AS (
                    SELECT UNNEST(?::VARCHAR[]) AS collection_id
                ),
                requested_terms AS (
                    SELECT UNNEST(?::VARCHAR[]) AS term
                )
                SELECT DISTINCT n.document_id, n.canonical_sha256, s.segment_id
                FROM projected_notes n
                JOIN projected_note_segments s USING (note_id)
                WHERE (
                    ? = FALSE OR (
                        SELECT COUNT(DISTINCT nt.tag_id)
                        FROM projected_note_tags nt
                        JOIN requested_tags rt USING (tag_id)
                        WHERE nt.note_id = n.note_id
                    ) = ?
                )
                AND (
                    ? = FALSE OR (
                        SELECT COUNT(DISTINCT nc.collection_id)
                        FROM projected_note_collections nc
                        JOIN requested_collections rc USING (collection_id)
                        WHERE nc.note_id = n.note_id
                    ) = ?
                )
                AND (
                    ? = FALSE OR (
                        SELECT COUNT(DISTINCT nt.term)
                        FROM projected_note_terms nt
                        JOIN requested_terms rt USING (term)
                        WHERE nt.note_id = n.note_id
                    ) = ?
                )
                ORDER BY n.document_id, n.canonical_sha256, s.segment_id
                """,
                [
                    list(filters.tag_ids),
                    list(filters.collection_ids),
                    list(terms),
                    bool(filters.tag_ids),
                    len(filters.tag_ids),
                    bool(filters.collection_ids),
                    len(filters.collection_ids),
                    filters.note_text is not None,
                    len(terms),
                ],
            ).fetchall()
        except duckdb.Error as exc:
            raise ResearchProjectionError(
                "Research evidence filter could not be evaluated", cause=exc
            ) from exc
        return tuple((str(row[0]), str(row[1]), str(row[2])) for row in rows)

    def summaries(
        self, keys: tuple[EvidenceScopeKey, ...]
    ) -> dict[EvidenceScopeKey, ProjectedEvidenceSummary]:
        self._require_open()
        if not keys:
            return {}
        if len(keys) != len(set(keys)):
            keys = tuple(dict.fromkeys(keys))
        documents = [key[0] for key in keys]
        canonical_hashes = [key[1] for key in keys]
        segments = [key[2] for key in keys]
        try:
            rows = self._connection.execute(
                """
                WITH scope AS (
                    SELECT UNNEST(?::VARCHAR[]) AS document_id,
                           UNNEST(?::VARCHAR[]) AS canonical_sha256,
                           UNNEST(?::VARCHAR[]) AS segment_id
                )
                SELECT n.note_id, n.document_id, n.canonical_sha256, s.segment_id,
                       nt.tag_id, nc.collection_id
                FROM projected_notes n
                JOIN projected_note_segments s USING (note_id)
                JOIN scope requested
                  ON requested.document_id = n.document_id
                 AND requested.canonical_sha256 = n.canonical_sha256
                 AND requested.segment_id = s.segment_id
                LEFT JOIN projected_note_tags nt USING (note_id)
                LEFT JOIN projected_note_collections nc USING (note_id)
                ORDER BY n.document_id, n.canonical_sha256, s.segment_id, n.note_id
                """,
                [documents, canonical_hashes, segments],
            ).fetchall()
        except duckdb.Error as exc:
            raise ResearchProjectionError(
                "Research evidence summaries could not be read", cause=exc
            ) from exc

        notes: dict[EvidenceScopeKey, set[str]] = {}
        tags: dict[EvidenceScopeKey, set[str]] = {}
        collections: dict[EvidenceScopeKey, set[str]] = {}
        for row in rows:
            key = (str(row[1]), str(row[2]), str(row[3]))
            notes.setdefault(key, set()).add(str(row[0]))
            if row[4] is not None:
                tags.setdefault(key, set()).add(str(row[4]))
            if row[5] is not None:
                collections.setdefault(key, set()).add(str(row[5]))
        return {
            key: ProjectedEvidenceSummary(
                note_ids=tuple(sorted(notes.get(key, set()))),
                tag_ids=tuple(sorted(tags.get(key, set()))),
                collection_ids=tuple(sorted(collections.get(key, set()))),
            )
            for key in notes
        }

    def clear(self) -> None:
        self._require_open()
        self._connection.execute("BEGIN TRANSACTION")
        try:
            self._clear_rows()
            self._set_watermark(0)
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise

    def close(self) -> None:
        if self._closed:
            return
        self._connection.close()
        self._closed = True

    def _initialize(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS projection_metadata (
                singleton INTEGER PRIMARY KEY,
                schema_version INTEGER NOT NULL,
                projected_through_sequence BIGINT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS projected_notes (
                note_id VARCHAR PRIMARY KEY,
                document_id VARCHAR NOT NULL,
                canonical_sha256 VARCHAR NOT NULL,
                source_sha256 VARCHAR NOT NULL,
                start_seconds DOUBLE NOT NULL,
                end_seconds DOUBLE NOT NULL,
                normalized_body VARCHAR NOT NULL
            );
            CREATE TABLE IF NOT EXISTS projected_note_segments (
                note_id VARCHAR NOT NULL,
                segment_id VARCHAR NOT NULL,
                PRIMARY KEY (note_id, segment_id)
            );
            CREATE TABLE IF NOT EXISTS projected_note_tags (
                note_id VARCHAR NOT NULL,
                tag_id VARCHAR NOT NULL,
                PRIMARY KEY (note_id, tag_id)
            );
            CREATE TABLE IF NOT EXISTS projected_note_collections (
                note_id VARCHAR NOT NULL,
                collection_id VARCHAR NOT NULL,
                PRIMARY KEY (note_id, collection_id)
            );
            CREATE TABLE IF NOT EXISTS projected_note_terms (
                note_id VARCHAR NOT NULL,
                term VARCHAR NOT NULL,
                PRIMARY KEY (note_id, term)
            );
            CREATE INDEX IF NOT EXISTS projected_note_generation_idx
                ON projected_notes(document_id, canonical_sha256);
            CREATE INDEX IF NOT EXISTS projected_note_segment_idx
                ON projected_note_segments(segment_id, note_id);
            CREATE INDEX IF NOT EXISTS projected_note_tag_idx
                ON projected_note_tags(tag_id, note_id);
            CREATE INDEX IF NOT EXISTS projected_note_collection_idx
                ON projected_note_collections(collection_id, note_id);
            CREATE INDEX IF NOT EXISTS projected_note_term_idx
                ON projected_note_terms(term, note_id);
            """
        )
        self._connection.execute(
            """
            INSERT INTO projection_metadata
                (singleton, schema_version, projected_through_sequence)
            SELECT 1, ?, 0
            WHERE NOT EXISTS (
                SELECT 1 FROM projection_metadata WHERE singleton = 1
            )
            """,
            [_SCHEMA_VERSION],
        )
        row = self._connection.execute(
            "SELECT schema_version FROM projection_metadata WHERE singleton = 1"
        ).fetchone()
        if row is None or int(row[0]) != _SCHEMA_VERSION:
            raise ResearchProjectionError(
                "Research projection schema is unsupported by this EchoFlow build"
            )

    def _insert_record(self, record: ResearchProjectionRecord) -> None:
        self._connection.execute(
            "INSERT INTO projected_notes VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                record.note_id,
                record.anchor.document_id,
                record.anchor.canonical_sha256,
                record.anchor.source_sha256,
                record.anchor.start_seconds,
                record.anchor.end_seconds,
                record.body.casefold(),
            ],
        )
        segment_rows = [
            (record.note_id, segment_id) for segment_id in record.anchor.segment_ids
        ]
        tag_rows = [(record.note_id, tag_id) for tag_id in record.tag_ids]
        collection_rows = [
            (record.note_id, collection_id) for collection_id in record.collection_ids
        ]
        term_rows = [
            (record.note_id, term)
            for term in tuple(sorted(set(lexical_tokens(record.body))))
        ]
        if segment_rows:
            self._connection.executemany(
                "INSERT INTO projected_note_segments VALUES (?, ?)", segment_rows
            )
        if tag_rows:
            self._connection.executemany(
                "INSERT INTO projected_note_tags VALUES (?, ?)", tag_rows
            )
        if collection_rows:
            self._connection.executemany(
                "INSERT INTO projected_note_collections VALUES (?, ?)", collection_rows
            )
        if term_rows:
            self._connection.executemany(
                "INSERT INTO projected_note_terms VALUES (?, ?)", term_rows
            )

    def _delete_note(self, note_id: str) -> None:
        self._connection.execute(
            "DELETE FROM projected_note_terms WHERE note_id = ?", [note_id]
        )
        self._connection.execute(
            "DELETE FROM projected_note_collections WHERE note_id = ?", [note_id]
        )
        self._connection.execute(
            "DELETE FROM projected_note_tags WHERE note_id = ?", [note_id]
        )
        self._connection.execute(
            "DELETE FROM projected_note_segments WHERE note_id = ?", [note_id]
        )
        self._connection.execute(
            "DELETE FROM projected_notes WHERE note_id = ?", [note_id]
        )

    def _clear_rows(self) -> None:
        self._connection.execute("DELETE FROM projected_note_terms")
        self._connection.execute("DELETE FROM projected_note_collections")
        self._connection.execute("DELETE FROM projected_note_tags")
        self._connection.execute("DELETE FROM projected_note_segments")
        self._connection.execute("DELETE FROM projected_notes")

    def _set_watermark(self, sequence_id: int) -> None:
        self._connection.execute(
            """
            UPDATE projection_metadata
            SET projected_through_sequence = ?
            WHERE singleton = 1
            """,
            [sequence_id],
        )

    def _require_open(self) -> None:
        if self._closed:
            raise ResearchProjectionError("Research query projection is closed")
