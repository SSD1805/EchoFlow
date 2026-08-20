"""SQLite-backed authoritative storage for user-authored research state."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.library.errors import ResearchStateError
from echoflow.library.evidence import EvidenceAnchor
from echoflow.library.research_state import (
    ResearchCollection,
    ResearchNote,
    ResearchProjectionRecord,
    ResearchProjectionSnapshot,
    ResearchStateChange,
    ResearchTag,
)

_SCHEMA_VERSION = 1
_MAX_BODY_CHARS = 1_000_000
_MAX_NAME_CHARS = 200
_MAX_ID_CHARS = 200
_MAX_BATCH_NOTES = 10_000


class SqliteResearchStateStore:
    """Durable transactional research state with a monotonic projection outbox."""

    def __init__(self, database_path: Path, file_manager: FileManagerFacade) -> None:
        self.database_path = database_path.expanduser().resolve(strict=False)
        self.file_manager = file_manager
        self.file_manager.ensure_directory_exists(
            self.database_path.parent, private=True
        )
        self._initialize()

    def create_note(
        self,
        anchor: EvidenceAnchor,
        body: str,
        *,
        tags: tuple[str, ...] = (),
        collections: tuple[str, ...] = (),
        note_id: str | None = None,
    ) -> ResearchNote:
        resolved_id = self._validate_id(note_id or f"note-{uuid4().hex}", "note_id")
        self._validate_body(body)
        tag_names = self._normalized_names(tags)
        collection_names = self._normalized_names(collections)
        now = self._now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO notes (
                    note_id, body, document_id, canonical_sha256, source_sha256,
                    canonical_path, source_path, start_seconds, end_seconds,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resolved_id,
                    body,
                    anchor.document_id,
                    anchor.canonical_sha256,
                    anchor.source_sha256,
                    anchor.canonical_path,
                    anchor.source_path,
                    anchor.start_seconds,
                    anchor.end_seconds,
                    now,
                    now,
                ),
            )
            connection.executemany(
                "INSERT INTO note_segments (note_id, ordinal, segment_id) VALUES (?, ?, ?)",
                (
                    (resolved_id, ordinal, segment_id)
                    for ordinal, segment_id in enumerate(anchor.segment_ids)
                ),
            )
            for name in tag_names:
                tag_id = self._ensure_tag(connection, name)
                connection.execute(
                    "INSERT INTO note_tags (note_id, tag_id) VALUES (?, ?)",
                    (resolved_id, tag_id),
                )
            for name in collection_names:
                collection_id = self._ensure_collection(connection, name)
                connection.execute(
                    "INSERT INTO collection_notes (collection_id, note_id) VALUES (?, ?)",
                    (collection_id, resolved_id),
                )
            self._journal(connection, resolved_id)
            note = self._note(connection, resolved_id)
            connection.commit()
        if note is None:
            raise ResearchStateError("Saved research note could not be read back")
        return note

    def update_note(self, note_id: str, body: str) -> ResearchNote:
        resolved_id = self._validate_id(note_id, "note_id")
        self._validate_body(body)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            changed = connection.execute(
                "UPDATE notes SET body = ?, updated_at = ? WHERE note_id = ?",
                (body, self._now(), resolved_id),
            ).rowcount
            if changed != 1:
                raise ResearchStateError("Research note does not exist")
            self._journal(connection, resolved_id)
            note = self._note(connection, resolved_id)
            connection.commit()
        if note is None:
            raise ResearchStateError("Updated research note could not be read back")
        return note

    def replace_note(
        self,
        note_id: str,
        body: str,
        *,
        tags: tuple[str, ...],
        collections: tuple[str, ...],
        expected_updated_at: str | None = None,
    ) -> ResearchNote:
        """Atomically replace editable human state without rebinding evidence."""
        resolved_id = self._validate_id(note_id, "note_id")
        self._validate_body(body)
        tag_names = self._normalized_names(tags)
        collection_names = self._normalized_names(collections)
        if expected_updated_at is not None:
            self._validate_id(expected_updated_at, "expected_updated_at")

        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_note_version(
                connection,
                resolved_id,
                expected_updated_at=expected_updated_at,
            )
            connection.execute(
                "UPDATE notes SET body = ?, updated_at = ? WHERE note_id = ?",
                (body, self._now(), resolved_id),
            )
            connection.execute(
                "DELETE FROM note_tags WHERE note_id = ?", (resolved_id,)
            )
            for name in tag_names:
                tag_id = self._ensure_tag(connection, name)
                connection.execute(
                    "INSERT INTO note_tags (note_id, tag_id) VALUES (?, ?)",
                    (resolved_id, tag_id),
                )
            connection.execute(
                "DELETE FROM collection_notes WHERE note_id = ?", (resolved_id,)
            )
            for name in collection_names:
                collection_id = self._ensure_collection(connection, name)
                connection.execute(
                    "INSERT INTO collection_notes (collection_id, note_id) VALUES (?, ?)",
                    (collection_id, resolved_id),
                )
            self._journal(connection, resolved_id)
            note = self._note(connection, resolved_id)
            connection.commit()
        if note is None:
            raise ResearchStateError("Updated research note could not be read back")
        return note

    def delete_note(
        self, note_id: str, *, expected_updated_at: str | None = None
    ) -> None:
        resolved_id = self._validate_id(note_id, "note_id")
        if expected_updated_at is not None:
            self._validate_id(expected_updated_at, "expected_updated_at")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_note_version(
                connection,
                resolved_id,
                expected_updated_at=expected_updated_at,
            )
            connection.execute("DELETE FROM notes WHERE note_id = ?", (resolved_id,))
            self._journal(connection, resolved_id)
            connection.commit()

    def note(self, note_id: str) -> ResearchNote | None:
        resolved_id = self._validate_id(note_id, "note_id")
        with self._connection() as connection:
            return self._note(connection, resolved_id)

    def notes(
        self, *, document_id: str | None = None, limit: int = 1_000
    ) -> tuple[ResearchNote, ...]:
        if limit < 1 or limit > _MAX_BATCH_NOTES:
            raise ValueError("note list limit must be between 1 and 10000")
        if document_id is not None and not document_id.strip():
            raise ValueError("document_id cannot be blank")
        with self._connection() as connection:
            if document_id is None:
                rows = connection.execute(
                    "SELECT note_id FROM notes ORDER BY updated_at DESC, note_id LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT note_id FROM notes
                    WHERE document_id = ?
                    ORDER BY updated_at DESC, note_id
                    LIMIT ?
                    """,
                    (document_id, limit),
                ).fetchall()
            note_ids = tuple(str(row[0]) for row in rows)
            return self._notes_by_ids(connection, note_ids)

    def notes_by_ids(self, note_ids: tuple[str, ...]) -> tuple[ResearchNote, ...]:
        if len(note_ids) > _MAX_BATCH_NOTES:
            raise ValueError("note batch cannot contain more than 10000 IDs")
        if len(note_ids) != len(set(note_ids)):
            raise ValueError("note batch cannot contain duplicate IDs")
        for note_id in note_ids:
            self._validate_id(note_id, "note_id")
        with self._connection() as connection:
            return self._notes_by_ids(connection, note_ids)

    def set_note_tags(self, note_id: str, names: tuple[str, ...]) -> ResearchNote:
        resolved_id = self._validate_id(note_id, "note_id")
        normalized = self._normalized_names(names)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_note(connection, resolved_id)
            connection.execute(
                "DELETE FROM note_tags WHERE note_id = ?", (resolved_id,)
            )
            for name in normalized:
                tag_id = self._ensure_tag(connection, name)
                connection.execute(
                    "INSERT INTO note_tags (note_id, tag_id) VALUES (?, ?)",
                    (resolved_id, tag_id),
                )
            connection.execute(
                "UPDATE notes SET updated_at = ? WHERE note_id = ?",
                (self._now(), resolved_id),
            )
            self._journal(connection, resolved_id)
            note = self._note(connection, resolved_id)
            connection.commit()
        if note is None:
            raise ResearchStateError("Tagged research note could not be read back")
        return note

    def set_note_collections(
        self, note_id: str, names: tuple[str, ...]
    ) -> ResearchNote:
        resolved_id = self._validate_id(note_id, "note_id")
        normalized = self._normalized_names(names)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_note(connection, resolved_id)
            connection.execute(
                "DELETE FROM collection_notes WHERE note_id = ?", (resolved_id,)
            )
            for name in normalized:
                collection_id = self._ensure_collection(connection, name)
                connection.execute(
                    "INSERT INTO collection_notes (collection_id, note_id) VALUES (?, ?)",
                    (collection_id, resolved_id),
                )
            connection.execute(
                "UPDATE notes SET updated_at = ? WHERE note_id = ?",
                (self._now(), resolved_id),
            )
            self._journal(connection, resolved_id)
            note = self._note(connection, resolved_id)
            connection.commit()
        if note is None:
            raise ResearchStateError("Collected research note could not be read back")
        return note

    def tags(self) -> tuple[ResearchTag, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT tag_id, name FROM tags ORDER BY normalized_name, tag_id"
            ).fetchall()
        return tuple(ResearchTag(tag_id=str(row[0]), name=str(row[1])) for row in rows)

    def collections(self) -> tuple[ResearchCollection, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT collection_id, name FROM collections
                ORDER BY normalized_name, collection_id
                """
            ).fetchall()
        return tuple(
            ResearchCollection(collection_id=str(row[0]), name=str(row[1]))
            for row in rows
        )

    def resolve_tag_ids(self, names: tuple[str, ...]) -> tuple[str, ...] | None:
        normalized = self._normalized_names(names)
        if not normalized:
            return ()
        with self._connection() as connection:
            resolved: list[str] = []
            for name in normalized:
                row = connection.execute(
                    "SELECT tag_id FROM tags WHERE normalized_name = ?",
                    (name.casefold(),),
                ).fetchone()
                if row is None:
                    return None
                resolved.append(str(row[0]))
        return tuple(sorted(resolved))

    def resolve_collection_ids(self, names: tuple[str, ...]) -> tuple[str, ...] | None:
        normalized = self._normalized_names(names)
        if not normalized:
            return ()
        with self._connection() as connection:
            resolved: list[str] = []
            for name in normalized:
                row = connection.execute(
                    "SELECT collection_id FROM collections WHERE normalized_name = ?",
                    (name.casefold(),),
                ).fetchone()
                if row is None:
                    return None
                resolved.append(str(row[0]))
        return tuple(sorted(resolved))

    def current_sequence(self) -> int:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT current_sequence FROM metadata WHERE singleton = 1"
            ).fetchone()
        if row is None:
            raise ResearchStateError("Research state metadata is missing")
        return int(row[0])

    def oldest_change_sequence(self) -> int | None:
        with self._connection() as connection:
            row = connection.execute("SELECT MIN(sequence_id) FROM changes").fetchone()
        if row is None or row[0] is None:
            return None
        return int(row[0])

    def changes_after(
        self, sequence_id: int, *, limit: int
    ) -> tuple[ResearchStateChange, ...]:
        if sequence_id < 0:
            raise ValueError("sequence_id cannot be negative")
        if limit < 1 or limit > _MAX_BATCH_NOTES:
            raise ValueError("change batch limit must be between 1 and 10000")
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT sequence_id, note_id FROM changes
                WHERE sequence_id > ?
                ORDER BY sequence_id
                LIMIT ?
                """,
                (sequence_id, limit),
            ).fetchall()
        return tuple(
            ResearchStateChange(sequence_id=int(row[0]), note_id=str(row[1]))
            for row in rows
        )

    def projection_records(
        self, note_ids: tuple[str, ...]
    ) -> tuple[ResearchProjectionRecord, ...]:
        if not note_ids:
            return ()
        if len(note_ids) != len(set(note_ids)):
            raise ValueError("projection note IDs cannot contain duplicates")
        for note_id in note_ids:
            self._validate_id(note_id, "note_id")
        with self._connection() as connection:
            notes = self._notes_by_ids(connection, note_ids)
        return tuple(self._projection_record(note) for note in notes)

    def projection_snapshot(self) -> ResearchProjectionSnapshot:
        with self._connection() as connection:
            connection.execute("BEGIN")
            sequence_row = connection.execute(
                "SELECT current_sequence FROM metadata WHERE singleton = 1"
            ).fetchone()
            if sequence_row is None:
                raise ResearchStateError("Research state metadata is missing")
            rows = connection.execute(
                "SELECT note_id FROM notes ORDER BY note_id"
            ).fetchall()
            note_ids = tuple(str(row[0]) for row in rows)
            notes = self._notes_by_ids(connection, note_ids)
            connection.commit()
        return ResearchProjectionSnapshot(
            sequence_id=int(sequence_row[0]),
            records=tuple(self._projection_record(note) for note in notes),
        )

    def compact_changes(self, through_sequence: int, *, retain: int) -> None:
        if through_sequence < 0:
            raise ValueError("through_sequence cannot be negative")
        if retain < 0:
            raise ValueError("retain cannot be negative")
        threshold = max(0, through_sequence - retain)
        if threshold == 0:
            return
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current_row = connection.execute(
                "SELECT current_sequence FROM metadata WHERE singleton = 1"
            ).fetchone()
            if current_row is None:
                raise ResearchStateError("Research state metadata is missing")
            if through_sequence > int(current_row[0]):
                raise ResearchStateError(
                    "Cannot compact research changes beyond authoritative state"
                )
            connection.execute(
                "DELETE FROM changes WHERE sequence_id <= ?", (threshold,)
            )
            connection.commit()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    schema_version INTEGER NOT NULL,
                    current_sequence INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notes (
                    note_id TEXT PRIMARY KEY,
                    body TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    canonical_sha256 TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    canonical_path TEXT NOT NULL,
                    source_path TEXT,
                    start_seconds REAL NOT NULL,
                    end_seconds REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS note_segments (
                    note_id TEXT NOT NULL REFERENCES notes(note_id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL,
                    segment_id TEXT NOT NULL,
                    PRIMARY KEY (note_id, ordinal),
                    UNIQUE (note_id, segment_id)
                );
                CREATE TABLE IF NOT EXISTS tags (
                    tag_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS note_tags (
                    note_id TEXT NOT NULL REFERENCES notes(note_id) ON DELETE CASCADE,
                    tag_id TEXT NOT NULL REFERENCES tags(tag_id) ON DELETE CASCADE,
                    PRIMARY KEY (note_id, tag_id)
                );
                CREATE TABLE IF NOT EXISTS collections (
                    collection_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS collection_notes (
                    collection_id TEXT NOT NULL
                        REFERENCES collections(collection_id) ON DELETE CASCADE,
                    note_id TEXT NOT NULL REFERENCES notes(note_id) ON DELETE CASCADE,
                    PRIMARY KEY (collection_id, note_id)
                );
                CREATE TABLE IF NOT EXISTS changes (
                    sequence_id INTEGER PRIMARY KEY,
                    note_id TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS notes_document_generation_idx
                    ON notes(document_id, canonical_sha256);
                CREATE INDEX IF NOT EXISTS note_segments_segment_idx
                    ON note_segments(segment_id, note_id);
                CREATE INDEX IF NOT EXISTS note_tags_tag_idx
                    ON note_tags(tag_id, note_id);
                CREATE INDEX IF NOT EXISTS collection_notes_collection_idx
                    ON collection_notes(collection_id, note_id);
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO metadata
                    (singleton, schema_version, current_sequence)
                VALUES (1, ?, 0)
                """,
                (_SCHEMA_VERSION,),
            )
            row = connection.execute(
                "SELECT schema_version FROM metadata WHERE singleton = 1"
            ).fetchone()
            if row is None or int(row[0]) != _SCHEMA_VERSION:
                raise ResearchStateError(
                    "Research state schema is unsupported by this EchoFlow build"
                )
            connection.commit()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(self.database_path, timeout=5.0)
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA synchronous = FULL")
            yield connection
        except sqlite3.Error as exc:
            if connection is not None:
                connection.rollback()
            raise ResearchStateError(
                "Research state database operation failed", cause=exc
            ) from exc
        finally:
            if connection is not None:
                connection.close()

    def _note(
        self, connection: sqlite3.Connection, note_id: str
    ) -> ResearchNote | None:
        notes = self._notes_by_ids(connection, (note_id,))
        return None if not notes else notes[0]

    def _notes_by_ids(
        self, connection: sqlite3.Connection, note_ids: tuple[str, ...]
    ) -> tuple[ResearchNote, ...]:
        if not note_ids:
            return ()
        self._select_note_ids(connection, note_ids)
        base_rows = connection.execute(
            """
            SELECT n.note_id, n.body, n.document_id, n.canonical_sha256,
                   n.source_sha256, n.canonical_path, n.source_path,
                   n.start_seconds, n.end_seconds, n.created_at, n.updated_at
            FROM notes n
            JOIN selected_note_ids selected USING (note_id)
            ORDER BY selected.ordinal
            """
        ).fetchall()
        segment_rows = connection.execute(
            """
            SELECT s.note_id, s.segment_id
            FROM note_segments s
            JOIN selected_note_ids selected USING (note_id)
            ORDER BY selected.ordinal, s.ordinal
            """
        ).fetchall()
        tag_rows = connection.execute(
            """
            SELECT nt.note_id, nt.tag_id
            FROM note_tags nt
            JOIN selected_note_ids selected USING (note_id)
            ORDER BY selected.ordinal, nt.tag_id
            """
        ).fetchall()
        collection_rows = connection.execute(
            """
            SELECT cn.note_id, cn.collection_id
            FROM collection_notes cn
            JOIN selected_note_ids selected USING (note_id)
            ORDER BY selected.ordinal, cn.collection_id
            """
        ).fetchall()
        segments = self._group_values(segment_rows)
        tags = self._group_values(tag_rows)
        collections = self._group_values(collection_rows)
        return tuple(
            self._note_from_row(
                row,
                segment_ids=segments.get(str(row[0]), ()),
                tag_ids=tags.get(str(row[0]), ()),
                collection_ids=collections.get(str(row[0]), ()),
            )
            for row in base_rows
        )

    @staticmethod
    def _select_note_ids(
        connection: sqlite3.Connection, note_ids: tuple[str, ...]
    ) -> None:
        connection.execute(
            """
            CREATE TEMP TABLE IF NOT EXISTS selected_note_ids (
                note_id TEXT PRIMARY KEY,
                ordinal INTEGER NOT NULL
            )
            """
        )
        connection.execute("DELETE FROM selected_note_ids")
        connection.executemany(
            "INSERT INTO selected_note_ids (note_id, ordinal) VALUES (?, ?)",
            ((note_id, ordinal) for ordinal, note_id in enumerate(note_ids)),
        )

    @staticmethod
    def _group_values(rows: list[tuple[object, ...]]) -> dict[str, tuple[str, ...]]:
        grouped: dict[str, list[str]] = {}
        for note_id, value in rows:
            grouped.setdefault(str(note_id), []).append(str(value))
        return {key: tuple(values) for key, values in grouped.items()}

    @staticmethod
    def _note_from_row(
        row: tuple[object, ...],
        *,
        segment_ids: tuple[str, ...],
        tag_ids: tuple[str, ...],
        collection_ids: tuple[str, ...],
    ) -> ResearchNote:
        anchor = EvidenceAnchor(
            document_id=str(row[2]),
            canonical_sha256=str(row[3]),
            source_sha256=str(row[4]),
            canonical_path=str(row[5]),
            source_path=None if row[6] is None else str(row[6]),
            segment_ids=segment_ids,
            start_seconds=float(cast("float | int", row[7])),
            end_seconds=float(cast("float | int", row[8])),
        )
        return ResearchNote(
            note_id=str(row[0]),
            body=str(row[1]),
            anchor=anchor,
            tag_ids=tuple(sorted(tag_ids)),
            collection_ids=tuple(sorted(collection_ids)),
            created_at=str(row[9]),
            updated_at=str(row[10]),
        )

    @staticmethod
    def _projection_record(note: ResearchNote) -> ResearchProjectionRecord:
        return ResearchProjectionRecord(
            note_id=note.note_id,
            body=note.body,
            anchor=note.anchor,
            tag_ids=note.tag_ids,
            collection_ids=note.collection_ids,
        )

    @staticmethod
    def _require_note(connection: sqlite3.Connection, note_id: str) -> None:
        row = connection.execute(
            "SELECT 1 FROM notes WHERE note_id = ?", (note_id,)
        ).fetchone()
        if row is None:
            raise ResearchStateError("Research note does not exist")

    @staticmethod
    def _require_note_version(
        connection: sqlite3.Connection,
        note_id: str,
        *,
        expected_updated_at: str | None,
    ) -> None:
        row = connection.execute(
            "SELECT updated_at FROM notes WHERE note_id = ?", (note_id,)
        ).fetchone()
        if row is None:
            raise ResearchStateError("Research note does not exist")
        if expected_updated_at is not None and str(row[0]) != expected_updated_at:
            raise ResearchStateError(
                "Research note changed since it was opened; refresh before saving"
            )

    @staticmethod
    def _ensure_tag(connection: sqlite3.Connection, name: str) -> str:
        normalized = name.casefold()
        row = connection.execute(
            "SELECT tag_id FROM tags WHERE normalized_name = ?", (normalized,)
        ).fetchone()
        if row is not None:
            return str(row[0])
        tag_id = f"tag-{uuid4().hex}"
        connection.execute(
            "INSERT INTO tags (tag_id, name, normalized_name) VALUES (?, ?, ?)",
            (tag_id, name, normalized),
        )
        return tag_id

    @staticmethod
    def _ensure_collection(connection: sqlite3.Connection, name: str) -> str:
        normalized = name.casefold()
        row = connection.execute(
            "SELECT collection_id FROM collections WHERE normalized_name = ?",
            (normalized,),
        ).fetchone()
        if row is not None:
            return str(row[0])
        collection_id = f"collection-{uuid4().hex}"
        connection.execute(
            """
            INSERT INTO collections (collection_id, name, normalized_name)
            VALUES (?, ?, ?)
            """,
            (collection_id, name, normalized),
        )
        return collection_id

    @staticmethod
    def _journal(connection: sqlite3.Connection, note_id: str) -> int:
        connection.execute(
            "UPDATE metadata SET current_sequence = current_sequence + 1 WHERE singleton = 1"
        )
        row = connection.execute(
            "SELECT current_sequence FROM metadata WHERE singleton = 1"
        ).fetchone()
        if row is None:
            raise ResearchStateError("Research state metadata is missing")
        sequence_id = int(row[0])
        connection.execute(
            "INSERT INTO changes (sequence_id, note_id) VALUES (?, ?)",
            (sequence_id, note_id),
        )
        return sequence_id

    @staticmethod
    def _validate_body(body: str) -> None:
        if not body.strip():
            raise ValueError("note body cannot be blank")
        if len(body) > _MAX_BODY_CHARS:
            raise ValueError("note body is too large")
        if "\x00" in body:
            raise ValueError("note body cannot contain NUL characters")

    @staticmethod
    def _validate_id(value: str, name: str) -> str:
        if not value.strip():
            raise ValueError(f"{name} cannot be blank")
        if len(value) > _MAX_ID_CHARS:
            raise ValueError(f"{name} is too long")
        if any(character in value for character in ("\r", "\n", "\x00")):
            raise ValueError(f"{name} contains unsupported control characters")
        return value

    @staticmethod
    def _normalized_names(names: tuple[str, ...]) -> tuple[str, ...]:
        by_normalized: dict[str, str] = {}
        for raw in names:
            name = raw.strip()
            if not name:
                raise ValueError("research label names cannot be blank")
            if len(name) > _MAX_NAME_CHARS:
                raise ValueError("research label name is too long")
            if any(character in name for character in ("\r", "\n", "\x00")):
                raise ValueError(
                    "research label names contain unsupported control characters"
                )
            by_normalized.setdefault(name.casefold(), name)
        return tuple(by_normalized[key] for key in sorted(by_normalized))

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat(timespec="microseconds")
