from types import SimpleNamespace
from typing import Any, cast

from echoflow.desktop.bridge import DesktopServices, handle_request
from echoflow.library.evidence import EvidenceContextSegment, EvidenceWord
from echoflow.library.errors import ResearchStateError
from echoflow.library.index import SearchQuery
from echoflow.library.retrieval import RetrievalMode
from echoflow.library.workspace_metadata import SavedSearch, SavedSearchIntent


class _UnusedLocationService:
    pass


class _Workspace:
    def __init__(self) -> None:
        self.created_query: SearchQuery | None = None
        self.created_context: int | None = None
        self.rename_call: dict[str, object] | None = None
        self.delete_call: dict[str, object] | None = None
        self.open_call: tuple[str, int] | None = None
        self.saved = SavedSearch(
            saved_search_id="search-1",
            name="Governance",
            description="Questions to revisit",
            intent=SavedSearchIntent(
                query=SearchQuery("governance", limit=20),
                mode=RetrievalMode.LEXICAL,
                context_segments=1,
            ),
            created_at="2026-08-19T20:00:00+00:00",
            updated_at="2026-08-19T20:01:00+00:00",
        )

    def open_note_evidence(self, note_id: str, *, context_segments: int):
        self.open_call = (note_id, context_segments)
        word = EvidenceWord(
            segment_id="segment-3",
            word_index=0,
            start_seconds=128.4,
            end_seconds=128.7,
            text="Earlier",
            speaker_ref="speaker-old",
        )
        segment = EvidenceContextSegment(
            segment_id="segment-3",
            start_seconds=128.4,
            end_seconds=135.2,
            text="Earlier verified evidence.",
            speaker_refs=("speaker-old",),
            words=(word,),
            is_result_segment=True,
            lexical_match=False,
        )
        evidence = SimpleNamespace(
            document_id="interview-11",
            source_sha256="d" * 64,
            canonical_sha256="c" * 64,
            canonical_path="/sensitive/old.json",
            source_path="/sensitive/interview.wav",
            result_segment_ids=("segment-3",),
            start_seconds=128.4,
            end_seconds=135.2,
            seek_seconds=128.4,
            result_speaker_refs=("speaker-old",),
            matched_words=(),
            context_segments=(segment,),
        )
        return SimpleNamespace(
            note=SimpleNamespace(
                note=SimpleNamespace(note_id="note-older"),
                current=False,
                tags=("review",),
                collections=("Field notes",),
            ),
            located=SimpleNamespace(
                evidence=evidence,
                speakers=(
                    SimpleNamespace(
                        speaker_ref="speaker-old",
                        display_label="Earlier participant",
                    ),
                ),
            ),
        )

    def save_search(
        self,
        name: str,
        query: SearchQuery,
        *,
        context_segments: int,
        description: str | None,
    ) -> SavedSearch:
        self.created_query = query
        self.created_context = context_segments
        return SavedSearch(
            saved_search_id="search-created",
            name=name,
            description=description,
            intent=SavedSearchIntent(
                query=query,
                mode=RetrievalMode.LEXICAL,
                context_segments=context_segments,
            ),
            created_at="2026-08-19T21:00:00+00:00",
            updated_at="2026-08-19T21:00:00+00:00",
        )

    def rename_saved_search(
        self,
        identifier: str,
        *,
        name: str,
        description: str | None,
        expected_updated_at: str,
    ) -> SavedSearch:
        self.rename_call = {
            "identifier": identifier,
            "name": name,
            "description": description,
            "expected_updated_at": expected_updated_at,
        }
        return SavedSearch(
            saved_search_id=self.saved.saved_search_id,
            name=name,
            description=description,
            intent=self.saved.intent,
            created_at=self.saved.created_at,
            updated_at="2026-08-19T21:02:00+00:00",
        )

    def delete_saved_search(
        self,
        identifier: str,
        *,
        expected_updated_at: str,
    ) -> None:
        self.delete_call = {
            "identifier": identifier,
            "expected_updated_at": expected_updated_at,
        }

    def saved_search(self, identifier: str) -> SavedSearch | None:
        return self.saved if identifier == self.saved.saved_search_id else None

    def run_saved_search(self, identifier: str):
        assert identifier == self.saved.saved_search_id
        evidence = SimpleNamespace(
            document_id="interview-42",
            source_sha256="b" * 64,
            canonical_sha256="a" * 64,
            result_segment_ids=("segment-17",),
            start_seconds=862.1,
            end_seconds=870.4,
            seek_seconds=862.1,
            matched_words=(),
            context_segments=(),
        )
        located = SimpleNamespace(
            evidence=evidence,
            passage=SimpleNamespace(text="Governance evidence", languages=("en",)),
            speakers=(),
        )
        research = SimpleNamespace(note_count=1, tags=("program",), collections=())
        return SimpleNamespace(
            navigation=SimpleNamespace(
                retrieval=SimpleNamespace(query=SearchQuery("governance", limit=20))
            ),
            results=(SimpleNamespace(located=located, research=research),),
        )


def _services(workspace: _Workspace) -> DesktopServices:
    return DesktopServices(
        locations=cast(Any, _UnusedLocationService()),
        workspace=cast(Any, workspace),
    )


def _request(method: str, params: dict[str, object]) -> dict[str, object]:
    return {
        "protocol_version": 1,
        "request_id": "research-next-1",
        "method": method,
        "params": params,
    }


def test_note_evidence_reopens_exact_generation_without_paths() -> None:
    workspace = _Workspace()
    response = handle_request(
        _request(
            "workspace.research.note.evidence",
            {"note_id": "note-older", "context_segments": 1},
        ),
        _services(workspace),
    )

    assert response["ok"] is True
    assert workspace.open_call == ("note-older", 1)
    result = response["result"]
    assert result["current"] is False
    assert result["evidence"]["canonical_sha256"] == "c" * 64
    assert result["evidence"]["text"] == "Earlier verified evidence."
    assert "/sensitive" not in str(result)
    assert "canonical_path" not in str(result)
    assert "source_path" not in str(result)


def test_note_evidence_rejects_sql_shaped_extra_params() -> None:
    workspace = _Workspace()
    response = handle_request(
        _request(
            "workspace.research.note.evidence",
            {
                "note_id": "note-older",
                "context_segments": 1,
                "sql": "SELECT * FROM notes",
            },
        ),
        _services(workspace),
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "invalid_request"
    assert workspace.open_call is None


def test_saved_search_create_compiles_desktop_defaults_behind_bridge() -> None:
    workspace = _Workspace()
    response = handle_request(
        _request(
            "workspace.research.saved_search.create",
            {
                "name": "Methods",
                "query_text": "methodology",
                "description": "Current interviews",
            },
        ),
        _services(workspace),
    )

    assert response["ok"] is True
    assert workspace.created_query == SearchQuery("methodology", limit=20)
    assert workspace.created_context == 1
    assert response["result"]["query_text"] == "methodology"


def test_saved_search_update_and_delete_pass_optimistic_version() -> None:
    workspace = _Workspace()
    update = handle_request(
        _request(
            "workspace.research.saved_search.update",
            {
                "saved_search_id": "search-1",
                "expected_updated_at": workspace.saved.updated_at,
                "name": "Governance follow-up",
                "description": None,
            },
        ),
        _services(workspace),
    )
    assert update["ok"] is True
    assert workspace.rename_call == {
        "identifier": "search-1",
        "name": "Governance follow-up",
        "description": None,
        "expected_updated_at": workspace.saved.updated_at,
    }

    delete = handle_request(
        _request(
            "workspace.research.saved_search.delete",
            {
                "saved_search_id": "search-1",
                "expected_updated_at": workspace.saved.updated_at,
            },
        ),
        _services(workspace),
    )
    assert delete["ok"] is True
    assert workspace.delete_call == {
        "identifier": "search-1",
        "expected_updated_at": workspace.saved.updated_at,
    }


def test_saved_search_run_returns_verified_evidence_without_paths() -> None:
    workspace = _Workspace()
    response = handle_request(
        _request(
            "workspace.research.saved_search.run",
            {"saved_search_id": "search-1"},
        ),
        _services(workspace),
    )

    assert response["ok"] is True
    result = response["result"]
    assert result["query"] == "governance"
    assert result["evidence"][0]["canonical_sha256"] == "a" * 64
    assert result["evidence"][0]["text"] == "Governance evidence"
    assert "canonical_path" not in str(result)
    assert "source_path" not in str(result)


def test_saved_search_stale_error_is_returned_without_internal_details() -> None:
    class _StaleWorkspace(_Workspace):
        def rename_saved_search(
            self,
            identifier: str,
            *,
            name: str,
            description: str | None,
            expected_updated_at: str,
        ) -> SavedSearch:
            raise ResearchStateError(
                "Saved search changed since it was opened; refresh before saving"
            )

    workspace = _StaleWorkspace()
    response = handle_request(
        _request(
            "workspace.research.saved_search.update",
            {
                "saved_search_id": "search-1",
                "expected_updated_at": workspace.saved.updated_at,
                "name": "Stale",
                "description": None,
            },
        ),
        _services(workspace),
    )

    assert response["ok"] is False
    assert "changed since it was opened" in response["error"]["message"]
    assert "Traceback" not in str(response)
