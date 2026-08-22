"""Durable saved searches and disposable workspace navigation views.

Saved searches are human-authored research state and therefore live in the same
private SQLite authority as notes, tags, and collections. Navigation rankings are
derived from current relationships and timestamps; they are never authoritative
counters.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast, runtime_checkable
from uuid import uuid4

from scholion.core.file_manager_facade import FileManagerFacade
from scholion.library.errors import ResearchStateError
from scholion.library.index import SearchOperator, SearchQuery, SearchSort
from scholion.library.retrieval import RetrievalMode

_METADATA_SCHEMA_VERSION = 1
_MAX_ID_CHARS = 200
_MAX_NAME_CHARS = 200
_MAX_DESCRIPTION_CHARS = 4_000
_MAX_LIST_RESULTS = 10_000
_MAX_NAVIGATION_RESULTS = 100


@dataclass(frozen=True, slots=True)
class SavedSearchIntent:
    """Typed workspace-search intent safe to persist and replay later."""

    query: SearchQuery
    mode: RetrievalMode = RetrievalMode.LEXICAL
    context_segments: int = 0
    tags: tuple[str, ...] = ()
    collections: tuple[str, ...] = ()
    note_text: str | None = None
    with_notes: bool = False

    def __post_init__(self) -> None:
        if self.query.evidence_scope is not None:
            raise ValueError("saved searches cannot persist a derived evidence scope")
        if self.context_segments < 0 or self.context_segments > 10:
            raise ValueError("context_segments must be between 0 and 10")
        for name, values in (("tags", self.tags), ("collections", self.collections)):
            if any(not value.strip() for value in values):
                raise ValueError(f"{name} cannot contain blank values")
            normalized = tuple(value.strip().casefold() for value in values)
            if len(normalized) != len(set(normalized)):
                raise ValueError(f"{name} cannot contain duplicates")
        if self.note_text is not None and not self.note_text.strip():
            raise ValueError("note_text cannot be blank")


@dataclass(frozen=True, slots=True)
class SavedSearch:
    """One durable named query authored by the user."""

    saved_search_id: str
    name: str
    description: str | None
    intent: SavedSearchIntent
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        if not self.saved_search_id.strip():
            raise ValueError("saved_search_id cannot be empty")
        if not self.name.strip():
            raise ValueError("saved search name cannot be empty")
        if self.description is not None and not self.description.strip():
            raise ValueError("saved search description cannot be blank")
        if not self.created_at.strip() or not self.updated_at.strip():
            raise ValueError("saved search timestamps cannot be empty")


@dataclass(frozen=True, slots=True)
class NavigationItem:
    """Disposable usage/recency view over one durable tag or collection."""

    object_id: str
    name: str
    usage_count: int
    last_used_at: str

    def __post_init__(self) -> None:
        if not self.object_id.strip() or not self.name.strip():
            raise ValueError("navigation item identity and name cannot be empty")
        if self.usage_count < 1:
            raise ValueError("navigation usage_count must be positive")
        if not self.last_used_at.strip():
            raise ValueError("navigation last_used_at cannot be empty")


@dataclass(frozen=True, slots=True)
class WorkspaceNavigation:
    """Useful derived navigation without creating new authoritative counters."""

    frequent_tags: tuple[NavigationItem, ...]
    recent_tags: tuple[NavigationItem, ...]
    frequent_collections: tuple[NavigationItem, ...]
    recent_collections: tuple[NavigationItem, ...]


@runtime_checkable
class WorkspaceMetadataStore(Protocol):
    """Port for durable saved searches plus rebuildable/derived navigation views."""

    def create_saved_search(
        self,
        name: str,
        intent: SavedSearchIntent,
        *,
        description: str | None = None,
        saved_search_id: str | None = None,
    ) -> SavedSearch: ...

    def update_saved_search(
        self,
        saved_search_id: str,
        *,
        name: str,
        description: str | None,
        intent: SavedSearchIntent,
        expected_updated_at: str | None = None,
    ) -> SavedSearch: ...

    def delete_saved_search(
        self,
        saved_search_id: str,
        *,
        expected_updated_at: str | None = None,
    ) -> None: ...

    def saved_search(self, identifier: str) -> SavedSearch | None: ...

    def saved_searches(self, *, limit: int = 1_000) -> tuple[SavedSearch, ...]: ...

    def navigation(self, *, limit: int = 10) -> WorkspaceNavigation: ...


class SqliteWorkspaceMetadataStore:
    """SQLite adapter sharing the authoritative research-state database file."""

    def __init__(self, database_path: Path, file_manager: FileManagerFacade) -> None:
        self.database_path = database_path.expanduser().resolve(strict=False)
        self.file_manager = file_manager
        self.file_manager.ensure_directory_exists(
            self.database_path.parent,
            private=True,
        )
        self._initialize()

    def create_saved_search(
        self,
        name: str,
        intent: SavedSearchIntent,
        *,
        description: str | None = None,
        saved_search_id: str | None = None,
    ) -> SavedSearch:
        resolved_id = self._validate_identifier(
            saved_search_id or f"search-{uuid4().hex}",
            "saved_search_id",
        )
        resolved_name = self._validate_name(name)
        resolved_description = self._normalize_description(description)
        now = self._now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_unique_name(connection, resolved_name, excluding_id=None)
            connection.execute(
                """
                INSERT INTO saved_searches (
                    saved_search_id, name, normalized_name, description,
                    query_text, phrase, operator, speaker_refs_json,
                    languages_json, document_ids_json, sort, result_limit,
                    retrieval_mode, context_segments, tags_json,
                    collections_json, note_text, with_notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._row_values(
                    resolved_id,
                    resolved_name,
                    resolved_description,
                    intent,
                    created_at=now,
                    updated_at=now,
                ),
            )
            saved = self._saved_search_by_id(connection, resolved_id)
            connection.commit()
        if saved is None:
            raise ResearchStateError("Saved search could not be read back")
        return saved

    def update_saved_search(
        self,
        saved_search_id: str,
        *,
        name: str,
        description: str | None,
        intent: SavedSearchIntent,
        expected_updated_at: str | None = None,
    ) -> SavedSearch:
        resolved_id = self._validate_identifier(saved_search_id, "saved_search_id")
        resolved_name = self._validate_name(name)
        resolved_description = self._normalize_description(description)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._saved_search_by_id(connection, resolved_id)
            if current is None:
                raise ResearchStateError("Saved search does not exist")
            self._require_current_version(current, expected_updated_at)
            self._require_unique_name(
                connection,
                resolved_name,
                excluding_id=resolved_id,
            )
            values = self._row_values(
                resolved_id,
                resolved_name,
                resolved_description,
                intent,
                created_at=current.created_at,
                updated_at=self._now(),
            )
            changed = connection.execute(
                """
                UPDATE saved_searches SET
                    name = ?, normalized_name = ?, description = ?,
                    query_text = ?, phrase = ?, operator = ?,
                    speaker_refs_json = ?, languages_json = ?, document_ids_json = ?,
                    sort = ?, result_limit = ?, retrieval_mode = ?,
                    context_segments = ?, tags_json = ?, collections_json = ?,
                    note_text = ?, with_notes = ?, created_at = ?, updated_at = ?
                WHERE saved_search_id = ?
                """,
                values[1:] + (resolved_id,),
            ).rowcount
            if changed != 1:
                raise ResearchStateError("Saved search does not exist")
            saved = self._saved_search_by_id(connection, resolved_id)
            connection.commit()
        if saved is None:
            raise ResearchStateError("Updated saved search could not be read back")
        return saved

    def delete_saved_search(
        self,
        saved_search_id: str,
        *,
        expected_updated_at: str | None = None,
    ) -> None:
        resolved_id = self._validate_identifier(saved_search_id, "saved_search_id")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._saved_search_by_id(connection, resolved_id)
            if current is None:
                raise ResearchStateError("Saved search does not exist")
            self._require_current_version(current, expected_updated_at)
            changed = connection.execute(
                "DELETE FROM saved_searches WHERE saved_search_id = ?",
                (resolved_id,),
            ).rowcount
            if changed != 1:
                raise ResearchStateError("Saved search does not exist")
            connection.commit()

    def saved_search(self, identifier: str) -> SavedSearch | None:
        resolved = self._validate_identifier(identifier, "saved search identifier")
        with self._connection() as connection:
            exact = self._saved_search_by_id(connection, resolved)
            if exact is not None:
                return exact
            row = connection.execute(
                """
                SELECT saved_search_id FROM saved_searches
                WHERE normalized_name = ?
                """,
                (resolved.strip().casefold(),),
            ).fetchone()
            if row is None:
                return None
            return self._saved_search_by_id(connection, str(row[0]))

    def saved_searches(self, *, limit: int = 1_000) -> tuple[SavedSearch, ...]:
        if limit < 1 or limit > _MAX_LIST_RESULTS:
            raise ValueError("saved search list limit must be between 1 and 10000")
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT saved_search_id FROM saved_searches
                ORDER BY updated_at DESC, normalized_name, saved_search_id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return tuple(
                saved
                for row in rows
                if (saved := self._saved_search_by_id(connection, str(row[0])))
                is not None
            )

    def navigation(self, *, limit: int = 10) -> WorkspaceNavigation:
        if limit < 1 or limit > _MAX_NAVIGATION_RESULTS:
            raise ValueError("navigation limit must be between 1 and 100")
        with self._connection() as connection:
            frequent_tags = self._navigation_rows(
                connection,
                kind="tag",
                order="usage",
                limit=limit,
            )
            recent_tags = self._navigation_rows(
                connection,
                kind="tag",
                order="recent",
                limit=limit,
            )
            frequent_collections = self._navigation_rows(
                connection,
                kind="collection",
                order="usage",
                limit=limit,
            )
            recent_collections = self._navigation_rows(
                connection,
                kind="collection",
                order="recent",
                limit=limit,
            )
        return WorkspaceNavigation(
            frequent_tags=frequent_tags,
            recent_tags=recent_tags,
            frequent_collections=frequent_collections,
            recent_collections=recent_collections,
        )

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS workspace_metadata (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    schema_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS saved_searches (
                    saved_search_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    query_text TEXT NOT NULL,
                    phrase INTEGER NOT NULL CHECK (phrase IN (0, 1)),
                    operator TEXT NOT NULL,
                    speaker_refs_json TEXT NOT NULL,
                    languages_json TEXT NOT NULL,
                    document_ids_json TEXT NOT NULL,
                    sort TEXT NOT NULL,
                    result_limit INTEGER NOT NULL,
                    retrieval_mode TEXT NOT NULL,
                    context_segments INTEGER NOT NULL,
                    tags_json TEXT NOT NULL,
                    collections_json TEXT NOT NULL,
                    note_text TEXT,
                    with_notes INTEGER NOT NULL CHECK (with_notes IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS saved_searches_updated_idx
                    ON saved_searches(updated_at DESC, saved_search_id);
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO workspace_metadata (singleton, schema_version)
                VALUES (1, ?)
                """,
                (_METADATA_SCHEMA_VERSION,),
            )
            row = connection.execute(
                "SELECT schema_version FROM workspace_metadata WHERE singleton = 1"
            ).fetchone()
            if row is None or int(row[0]) != _METADATA_SCHEMA_VERSION:
                raise ResearchStateError(
                    "Workspace metadata schema is unsupported by this Scholion build"
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
                "Workspace metadata database operation failed",
                cause=exc,
            ) from exc
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _row_values(
        saved_search_id: str,
        name: str,
        description: str | None,
        intent: SavedSearchIntent,
        *,
        created_at: str,
        updated_at: str,
    ) -> tuple[object, ...]:
        query = intent.query
        return (
            saved_search_id,
            name,
            name.casefold(),
            description,
            query.text,
            int(query.phrase),
            query.operator.value,
            SqliteWorkspaceMetadataStore._encode_tuple(query.speaker_refs),
            SqliteWorkspaceMetadataStore._encode_tuple(query.languages),
            SqliteWorkspaceMetadataStore._encode_tuple(query.document_ids),
            query.sort.value,
            query.limit,
            intent.mode.value,
            intent.context_segments,
            SqliteWorkspaceMetadataStore._encode_tuple(intent.tags),
            SqliteWorkspaceMetadataStore._encode_tuple(intent.collections),
            intent.note_text,
            int(intent.with_notes),
            created_at,
            updated_at,
        )

    def _saved_search_by_id(
        self,
        connection: sqlite3.Connection,
        saved_search_id: str,
    ) -> SavedSearch | None:
        row = connection.execute(
            """
            SELECT saved_search_id, name, description, query_text, phrase, operator,
                   speaker_refs_json, languages_json, document_ids_json, sort,
                   result_limit, retrieval_mode, context_segments, tags_json,
                   collections_json, note_text, with_notes, created_at, updated_at
            FROM saved_searches
            WHERE saved_search_id = ?
            """,
            (saved_search_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            query = SearchQuery(
                text=str(row[3]),
                phrase=bool(row[4]),
                operator=SearchOperator(str(row[5])),
                speaker_refs=self._decode_tuple(row[6], "speaker_refs"),
                languages=self._decode_tuple(row[7], "languages"),
                document_ids=self._decode_tuple(row[8], "document_ids"),
                sort=SearchSort(str(row[9])),
                limit=int(row[10]),
            )
            intent = SavedSearchIntent(
                query=query,
                mode=RetrievalMode(str(row[11])),
                context_segments=int(row[12]),
                tags=self._decode_tuple(row[13], "tags"),
                collections=self._decode_tuple(row[14], "collections"),
                note_text=None if row[15] is None else str(row[15]),
                with_notes=bool(row[16]),
            )
            return SavedSearch(
                saved_search_id=str(row[0]),
                name=str(row[1]),
                description=None if row[2] is None else str(row[2]),
                intent=intent,
                created_at=str(row[17]),
                updated_at=str(row[18]),
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ResearchStateError(
                "Saved search state is corrupt", cause=exc
            ) from exc

    @staticmethod
    def _require_current_version(
        saved: SavedSearch,
        expected_updated_at: str | None,
    ) -> None:
        if expected_updated_at is None:
            return
        if saved.updated_at != expected_updated_at:
            raise ResearchStateError(
                "Saved search changed since it was opened; refresh before saving"
            )

    @staticmethod
    def _encode_tuple(values: tuple[str, ...]) -> str:
        return json.dumps(list(values), ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _decode_tuple(value: object, name: str) -> tuple[str, ...]:
        decoded = json.loads(str(value))
        if not isinstance(decoded, list) or any(
            not isinstance(item, str) for item in decoded
        ):
            raise ValueError(f"saved search {name} state is invalid")
        return tuple(decoded)

    @staticmethod
    def _require_unique_name(
        connection: sqlite3.Connection,
        name: str,
        *,
        excluding_id: str | None,
    ) -> None:
        row = connection.execute(
            """
            SELECT saved_search_id FROM saved_searches
            WHERE normalized_name = ?
            """,
            (name.casefold(),),
        ).fetchone()
        if row is not None and str(row[0]) != excluding_id:
            raise ResearchStateError("A saved search with that name already exists")

    @staticmethod
    def _navigation_rows(
        connection: sqlite3.Connection,
        *,
        kind: str,
        order: str,
        limit: int,
    ) -> tuple[NavigationItem, ...]:
        if kind == "tag":
            id_column = "t.tag_id"
            name_column = "t.name"
            normalized_column = "t.normalized_name"
            from_clause = (
                "tags t JOIN note_tags rel ON rel.tag_id = t.tag_id "
                "JOIN notes n ON n.note_id = rel.note_id"
            )
        elif kind == "collection":
            id_column = "c.collection_id"
            name_column = "c.name"
            normalized_column = "c.normalized_name"
            from_clause = (
                "collections c "
                "JOIN collection_notes rel ON rel.collection_id = c.collection_id "
                "JOIN notes n ON n.note_id = rel.note_id"
            )
        else:
            raise ValueError("unsupported workspace navigation kind")

        if order == "usage":
            order_clause = (
                "usage_count DESC, last_used_at DESC, normalized_name, object_id"
            )
        elif order == "recent":
            order_clause = (
                "last_used_at DESC, usage_count DESC, normalized_name, object_id"
            )
        else:
            raise ValueError("unsupported workspace navigation order")

        rows = connection.execute(
            f"""
            SELECT {id_column} AS object_id,
                   {name_column} AS name,
                   {normalized_column} AS normalized_name,
                   COUNT(rel.note_id) AS usage_count,
                   MAX(n.updated_at) AS last_used_at
            FROM {from_clause}
            GROUP BY object_id, name, normalized_name
            ORDER BY {order_clause}
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return tuple(
            NavigationItem(
                object_id=str(row[0]),
                name=str(row[1]),
                usage_count=int(cast("int", row[3])),
                last_used_at=str(row[4]),
            )
            for row in rows
        )

    @staticmethod
    def _validate_identifier(value: str, name: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{name} cannot be blank")
        if len(stripped) > _MAX_ID_CHARS:
            raise ValueError(f"{name} is too long")
        if any(character in stripped for character in ("\r", "\n", "\x00")):
            raise ValueError(f"{name} contains unsupported control characters")
        return stripped

    @staticmethod
    def _validate_name(value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("saved search name cannot be blank")
        if len(stripped) > _MAX_NAME_CHARS:
            raise ValueError("saved search name is too long")
        if any(character in stripped for character in ("\r", "\n", "\x00")):
            raise ValueError(
                "saved search name contains unsupported control characters"
            )
        return stripped

    @staticmethod
    def _normalize_description(value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        if len(stripped) > _MAX_DESCRIPTION_CHARS:
            raise ValueError("saved search description is too long")
        if "\x00" in stripped:
            raise ValueError("saved search description cannot contain NUL characters")
        return stripped

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat(timespec="microseconds")
