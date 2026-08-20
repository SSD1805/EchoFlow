from pathlib import Path

import pytest

from echoflow.library.errors import ResearchStateError
from echoflow.library.index import SearchQuery
from echoflow.library.workspace_metadata import (
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


def _intent(text: str) -> SavedSearchIntent:
    return SavedSearchIntent(query=SearchQuery(text, limit=20))


def test_saved_search_update_refuses_stale_version_without_mutation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    created = store.create_saved_search(
        "Housing",
        _intent("housing"),
        saved_search_id="search-1",
    )
    current = store.update_saved_search(
        created.saved_search_id,
        name="Housing current",
        description=None,
        intent=created.intent,
        expected_updated_at=created.updated_at,
    )

    with pytest.raises(ResearchStateError, match="changed since it was opened"):
        store.update_saved_search(
            created.saved_search_id,
            name="Stale overwrite",
            description=None,
            intent=_intent("stale"),
            expected_updated_at=created.updated_at,
        )

    assert store.saved_search(created.saved_search_id) == current


def test_saved_search_delete_refuses_stale_version_without_mutation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    created = store.create_saved_search(
        "Housing",
        _intent("housing"),
        saved_search_id="search-1",
    )
    current = store.update_saved_search(
        created.saved_search_id,
        name="Housing current",
        description=None,
        intent=created.intent,
        expected_updated_at=created.updated_at,
    )

    with pytest.raises(ResearchStateError, match="changed since it was opened"):
        store.delete_saved_search(
            created.saved_search_id,
            expected_updated_at=created.updated_at,
        )

    assert store.saved_search(created.saved_search_id) == current
    store.delete_saved_search(
        current.saved_search_id,
        expected_updated_at=current.updated_at,
    )
    assert store.saved_search(current.saved_search_id) is None
