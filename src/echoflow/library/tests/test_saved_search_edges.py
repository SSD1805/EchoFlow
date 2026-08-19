import sqlite3
from pathlib import Path

import pytest

from echoflow.library.errors import ResearchStateError
from echoflow.library.index import SearchQuery
from echoflow.library.workspace_metadata import (
    NavigationItem,
    SavedSearch,
    SavedSearchIntent,
    SqliteWorkspaceMetadataStore,
)


class PrivateDirectoryStore:
    def ensure_directory_exists(
        self, directory_path: str | Path, *, private: bool = False
    ) -> None:
        assert private
        Path(directory_path).mkdir(parents=True, exist_ok=True)


def _store(tmp_path: Path) -> SqliteWorkspaceMetadataStore:
    return SqliteWorkspaceMetadataStore(
        tmp_path / "state" / "research.sqlite3",
        PrivateDirectoryStore(),  # type: ignore[arg-type]
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"context_segments": -1}, "context_segments"),
        ({"context_segments": 11}, "context_segments"),
        ({"tags": ("housing", "HOUSING")}, "duplicates"),
        ({"collections": ("",)}, "blank"),
        ({"note_text": "   "}, "note_text"),
    ],
)
def test_saved_search_intent_rejects_invalid_durable_state(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        SavedSearchIntent(
            query=SearchQuery("evidence"), **kwargs  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"saved_search_id": "   "},
        {"name": ""},
        {"description": "   "},
        {"created_at": ""},
        {"updated_at": ""},
    ],
)
def test_saved_search_value_object_rejects_missing_identity(
    kwargs: dict[str, str],
) -> None:
    values = {
        "saved_search_id": "search-1",
        "name": "Evidence",
        "description": None,
        "intent": SavedSearchIntent(query=SearchQuery("evidence")),
        "created_at": "2026-08-19T00:00:00+00:00",
        "updated_at": "2026-08-19T00:00:00+00:00",
    }
    values.update(kwargs)
    with pytest.raises(ValueError):
        SavedSearch(**values)  # type: ignore[arg-type]


def test_navigation_item_rejects_invalid_derived_view() -> None:
    with pytest.raises(ValueError, match="identity"):
        NavigationItem("", "name", 1, "2026-08-19T00:00:00+00:00")
    with pytest.raises(ValueError, match="positive"):
        NavigationItem("tag-1", "name", 0, "2026-08-19T00:00:00+00:00")
    with pytest.raises(ValueError, match="last_used_at"):
        NavigationItem("tag-1", "name", 1, "")


def test_saved_search_store_bounds_and_missing_mutations_fail_closed(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    with pytest.raises(ValueError, match="list limit"):
        store.saved_searches(limit=0)
    with pytest.raises(ValueError, match="list limit"):
        store.saved_searches(limit=10_001)
    with pytest.raises(ResearchStateError, match="does not exist"):
        store.update_saved_search(
            "missing",
            name="Missing",
            description=None,
            intent=SavedSearchIntent(query=SearchQuery("missing")),
        )
    with pytest.raises(ResearchStateError, match="does not exist"):
        store.delete_saved_search("missing")


def test_saved_search_store_rejects_invalid_identifiers_names_and_description(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    intent = SavedSearchIntent(query=SearchQuery("evidence"))

    with pytest.raises(ValueError, match="too long"):
        store.create_saved_search("x" * 201, intent)
    with pytest.raises(ValueError, match="control"):
        store.create_saved_search("bad\nname", intent)
    with pytest.raises(ValueError, match="too long"):
        store.create_saved_search(
            "valid",
            intent,
            saved_search_id="x" * 201,
        )
    with pytest.raises(ValueError, match="control"):
        store.saved_search("bad\nidentifier")
    with pytest.raises(ValueError, match="too long"):
        store.create_saved_search(
            "valid",
            intent,
            description="x" * 4_001,
        )
    with pytest.raises(ValueError, match="NUL"):
        store.create_saved_search(
            "valid",
            intent,
            description="bad\x00description",
        )


def test_saved_search_corrupt_json_and_enum_state_fail_closed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    created = store.create_saved_search(
        "Evidence",
        SavedSearchIntent(query=SearchQuery("evidence")),
        saved_search_id="search-1",
    )
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "UPDATE saved_searches SET tags_json = ? WHERE saved_search_id = ?",
            ("not-json", created.saved_search_id),
        )
        connection.commit()

    with pytest.raises(ResearchStateError, match="corrupt"):
        store.saved_search(created.saved_search_id)

    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "UPDATE saved_searches SET tags_json = ?, operator = ? "
            "WHERE saved_search_id = ?",
            ("[]", "not-an-operator", created.saved_search_id),
        )
        connection.commit()

    with pytest.raises(ResearchStateError, match="corrupt"):
        store.saved_search(created.saved_search_id)


def test_navigation_private_dispatch_rejects_unknown_closed_fragments(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    with sqlite3.connect(store.database_path) as connection:
        with pytest.raises(ValueError, match="navigation kind"):
            store._navigation_rows(  # noqa: SLF001
                connection,
                kind="unknown",
                order="usage",
                limit=1,
            )
        with pytest.raises(ValueError, match="navigation order"):
            store._navigation_rows(  # noqa: SLF001
                connection,
                kind="tag",
                order="unknown",
                limit=1,
            )
