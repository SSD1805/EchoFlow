from types import SimpleNamespace
from typing import Any, cast

from echoflow.desktop.bridge import DesktopServices, handle_request
from echoflow.library.research_workspace import ResearchQueryFilters


class _UnusedLocationService:
    pass


class _Workspace:
    def __init__(self) -> None:
        self.filters: ResearchQueryFilters | None = None
        self.limit: int | None = None

    def notes(
        self,
        *,
        filters: ResearchQueryFilters | None = None,
        limit: int = 1_000,
    ):
        self.filters = filters
        self.limit = limit
        anchor = SimpleNamespace(
            document_id="interview-42",
            canonical_sha256="a" * 64,
            segment_ids=("segment-17",),
            start_seconds=862.1,
            end_seconds=870.4,
        )
        note = SimpleNamespace(
            note_id="note-7",
            body="Follow up on governance.",
            anchor=anchor,
            created_at="2026-08-19T19:20:00+00:00",
            updated_at="2026-08-19T19:25:00+00:00",
        )
        view = SimpleNamespace(
            note=note,
            current=True,
            tags=("governance", "program"),
            collections=("Oral histories",),
        )
        return (view,)


def _services(workspace: _Workspace) -> DesktopServices:
    return DesktopServices(
        locations=cast(Any, _UnusedLocationService()),
        workspace=cast(Any, workspace),
        research_search=cast(Any, object()),
        processing=cast(Any, object()),
    )


def _request(params: dict[str, object]) -> dict[str, object]:
    return {
        "protocol_version": 1,
        "request_id": "research-filter-1",
        "method": "workspace.research.notes.filter",
        "params": params,
    }


def test_research_note_filter_delegates_to_authoritative_workspace_semantics() -> None:
    workspace = _Workspace()
    response = handle_request(
        _request(
            {
                "tags": ["program", "governance"],
                "collections": ["Oral histories"],
            }
        ),
        _services(workspace),
    )

    assert response["ok"] is True
    assert workspace.filters == ResearchQueryFilters(
        tags=("governance", "program"),
        collections=("Oral histories",),
    )
    assert workspace.limit == 200
    result = response["result"]
    assert result["tags"] == ["governance", "program"]
    assert result["collections"] == ["Oral histories"]
    assert result["notes"][0]["note_id"] == "note-7"
    assert result["notes"][0]["current"] is True


def test_research_note_filter_rejects_sql_shaped_extra_params() -> None:
    workspace = _Workspace()
    response = handle_request(
        _request(
            {
                "tags": ["governance"],
                "collections": [],
                "sql": "SELECT * FROM notes",
            }
        ),
        _services(workspace),
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "invalid_request"
    assert workspace.filters is None


def test_research_note_filter_normalizes_duplicate_label_spellings() -> None:
    workspace = _Workspace()
    response = handle_request(
        _request(
            {
                "tags": [" Governance ", "governance"],
                "collections": [" Oral histories "],
            }
        ),
        _services(workspace),
    )

    assert response["ok"] is True
    assert workspace.filters == ResearchQueryFilters(
        tags=("Governance",),
        collections=("Oral histories",),
    )
