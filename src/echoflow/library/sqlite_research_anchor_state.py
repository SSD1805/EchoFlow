"""Same-database durable history for deliberate research-note re-anchoring."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from echoflow.library.errors import ResearchStateError
from echoflow.library.evidence import EvidenceAnchor
from echoflow.library.research_state import ResearchAnchorHistoryEntry

_EXTENSION_SCHEMA_VERSION = 1
_MAX_ID_CHARS = 200


class SqliteResearchAnchorStateStore:
    """Maintain note anchors in the authoritative research SQLite transaction boundary.

    This adapter deliberately shares the existing research SQLite file. Re-anchoring one
    note, preserving its prior anchor, replacing current segment relationships, and
    advancing the projection journal therefore commit or roll back together.
    """

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.expanduser().resolve(strict=False)
        self._initialize_extension()

    def reanchor_note(
        self,
        note_id: str,
        anchor: EvidenceAnchor,
        *,
        expected_updated_at: str,
    ) -> None:
        resolved_id = self._validate_id(note_id, "note_id")
        expected_version = self._validate_id(
            expected_updated_at, "expected_updated_at"
        )
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT document_id, canonical_sha256, source_sha256, canonical_path,
                       source_path, start_seconds, end_seconds, updated_at
                FROM notes WHERE note_id = ?
                """,
                (resolved_id,),
            ).fetchone()
            if row is None:
                raise ResearchStateError("Research note does not exist")
            if str(row[7]) != expected_version:
                raise ResearchStateError(
                    "Research note changed since its evidence was reviewed; refresh before re-anchoring"
                )

            old_anchor = self._anchor_from_note_row(
                connection,
                resolved_id,
                row,
            )
            if anchor.document_id != old_anchor.document_id:
                raise ResearchStateError(
                    "Re-anchoring cannot move a note to a different transcript"
                )
            if anchor.source_sha256 != old_anchor.source_sha256:
                raise ResearchStateError(
                    "Re-anchoring cannot move a note to different source evidence"
                )
            if anchor == old_anchor:
                raise ResearchStateError("Research note already cites that evidence")

            revision_row = connection.execute(
                """
                SELECT COALESCE(MAX(revision), 0) + 1
                FROM note_anchor_history WHERE note_id = ?
                """,
                (resolved_id,),
            ).fetchone()
            if revision_row is None:
                raise ResearchStateError("Research anchor history could not be advanced")
            revision = int(revision_row[0])
            replaced_at = self._now()
            connection.execute(
                """
                INSERT INTO note_anchor_history (
                    note_id, revision, document_id, canonical_sha256, source_sha256,
                    canonical_path, source_path, start_seconds, end_seconds, replaced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resolved_id,
                    revision,
                    old_anchor.document_id,
                    old_anchor.canonical_sha256,
                    old_anchor.source_sha256,
                    old_anchor.canonical_path,
                    old_anchor.source_path,
                    old_anchor.start_seconds,
                    old_anchor.end_seconds,
                    replaced_at,
                ),
            )
            connection.executemany(
                """
                INSERT INTO note_anchor_history_segments (
                    note_id, revision, ordinal, segment_id
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    (resolved_id, revision, ordinal, segment_id)
                    for ordinal, segment_id in enumerate(old_anchor.segment_ids)
                ),
            )

            connection.execute(
                """
                UPDATE notes
                SET document_id = ?, canonical_sha256 = ?, source_sha256 = ?,
                    canonical_path = ?, source_path = ?, start_seconds = ?,
                    end_seconds = ?, updated_at = ?
                WHERE note_id = ?
                """,
                (
                    anchor.document_id,
                    anchor.canonical_sha256,
                    anchor.source_sha256,
                    anchor.canonical_path,
                    anchor.source_path,
                    anchor.start_seconds,
                    anchor.end_seconds,
                    replaced_at,
                    resolved_id,
                ),
            )
            connection.execute(
                "DELETE FROM note_segments WHERE note_id = ?", (resolved_id,)
            )
            connection.executemany(
                """
                INSERT INTO note_segments (note_id, ordinal, segment_id)
                VALUES (?, ?, ?)
                """,
                (
                    (resolved_id, ordinal, segment_id)
                    for ordinal, segment_id in enumerate(anchor.segment_ids)
                ),
            )
            self._journal(connection, resolved_id)
            connection.commit()

    def note_anchor_history(
        self, note_id: str
    ) -> tuple[ResearchAnchorHistoryEntry, ...]:
        resolved_id = self._validate_id(note_id, "note_id")
        with self._connection() as connection:
            exists = connection.execute(
                "SELECT 1 FROM notes WHERE note_id = ?", (resolved_id,)
            ).fetchone()
            if exists is None:
                raise ResearchStateError("Research note does not exist")
            rows = connection.execute(
                """
                SELECT revision, document_id, canonical_sha256, source_sha256,
                       canonical_path, source_path, start_seconds, end_seconds,
                       replaced_at
                FROM note_anchor_history
                WHERE note_id = ?
                ORDER BY revision DESC
                """,
                (resolved_id,),
            ).fetchall()
            entries: list[ResearchAnchorHistoryEntry] = []
            for row in rows:
                revision = int(row[0])
                segment_rows = connection.execute(
                    """
                    SELECT segment_id FROM note_anchor_history_segments
                    WHERE note_id = ? AND revision = ?
                    ORDER BY ordinal
                    """,
                    (resolved_id, revision),
                ).fetchall()
                anchor = EvidenceAnchor(
                    document_id=str(row[1]),
                    canonical_sha256=str(row[2]),
                    source_sha256=str(row[3]),
                    canonical_path=str(row[4]),
                    source_path=None if row[5] is None else str(row[5]),
                    segment_ids=tuple(str(item[0]) for item in segment_rows),
                    start_seconds=float(cast("float | int", row[6])),
                    end_seconds=float(cast("float | int", row[7])),
                )
                entries.append(
                    ResearchAnchorHistoryEntry(
                        note_id=resolved_id,
                        revision=revision,
                        anchor=anchor,
                        replaced_at=str(row[8]),
                    )
                )
            return tuple(entries)

    def _initialize_extension(self) -> None:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            core = connection.execute(
                "SELECT schema_version FROM metadata WHERE singleton = 1"
            ).fetchone()
            if core is None:
                raise ResearchStateError("Research state metadata is missing")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS anchor_history_metadata (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    schema_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS note_anchor_history (
                    note_id TEXT NOT NULL REFERENCES notes(note_id) ON DELETE CASCADE,
                    revision INTEGER NOT NULL,
                    document_id TEXT NOT NULL,
                    canonical_sha256 TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    canonical_path TEXT NOT NULL,
                    source_path TEXT,
                    start_seconds REAL NOT NULL,
                    end_seconds REAL NOT NULL,
                    replaced_at TEXT NOT NULL,
                    PRIMARY KEY (note_id, revision)
                );
                CREATE TABLE IF NOT EXISTS note_anchor_history_segments (
                    note_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    ordinal INTEGER NOT NULL,
                    segment_id TEXT NOT NULL,
                    PRIMARY KEY (note_id, revision, ordinal),
                    UNIQUE (note_id, revision, segment_id),
                    FOREIGN KEY (note_id, revision)
                        REFERENCES note_anchor_history(note_id, revision)
                        ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS note_anchor_history_generation_idx
                    ON note_anchor_history(note_id, canonical_sha256);
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO anchor_history_metadata
                    (singleton, schema_version)
                VALUES (1, ?)
                """,
                (_EXTENSION_SCHEMA_VERSION,),
            )
            row = connection.execute(
                """
                SELECT schema_version FROM anchor_history_metadata
                WHERE singleton = 1
                """
            ).fetchone()
            if row is None or int(row[0]) != _EXTENSION_SCHEMA_VERSION:
                raise ResearchStateError(
                    "Research anchor-history schema is unsupported by this EchoFlow build"
                )
            connection.commit()

    @staticmethod
    def _anchor_from_note_row(
        connection: sqlite3.Connection,
        note_id: str,
        row: tuple[object, ...],
    ) -> EvidenceAnchor:
        segment_rows = connection.execute(
            """
            SELECT segment_id FROM note_segments
            WHERE note_id = ? ORDER BY ordinal
            """,
            (note_id,),
        ).fetchall()
        return EvidenceAnchor(
            document_id=str(row[0]),
            canonical_sha256=str(row[1]),
            source_sha256=str(row[2]),
            canonical_path=str(row[3]),
            source_path=None if row[4] is None else str(row[4]),
            segment_ids=tuple(str(item[0]) for item in segment_rows),
            start_seconds=float(cast("float | int", row[5])),
            end_seconds=float(cast("float | int", row[6])),
        )

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
                "Research anchor database operation failed", cause=exc
            ) from exc
        finally:
            if connection is not None:
                connection.close()

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
    def _now() -> str:
        return datetime.now(UTC).isoformat(timespec="microseconds")
