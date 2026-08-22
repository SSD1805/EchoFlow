from pathlib import Path
from typing import Any, cast

from echoflow.desktop.bridge import DesktopServices, handle_request
from echoflow.library.errors import LibraryLocationError
from echoflow.library.evidence import (
    EvidenceAnchor,
    EvidenceContextSegment,
    EvidenceLocation,
    EvidenceWord,
)
from echoflow.library.index import SearchQuery
from echoflow.library.locations import (
    DiscoveredRecording,
    LibraryLocation,
    LibraryLocationKind,
    ManagedTranscriptRefreshReport,
    RecordingDiscoveryReport,
    RecordingProcessingPolicy,
)
from echoflow.library.research import (
    LocatedSearchPassage,
    ResearchSearchResponse,
    SpeakerDisplay,
)
from echoflow.library.research_state import (
    ResearchCollection,
    ResearchNote,
    ResearchTag,
)
from echoflow.library.research_workspace import (
    ResearchEvidenceView,
    ResearchNoteView,
    ResearchQueryFilters,
    WorkspaceDiscoveryResponse,
    WorkspaceSearchPassage,
    WorkspaceSearchResponse,
)
from echoflow.library.retrieval import RetrievalMode, SearchPassage, SearchResponse
from echoflow.library.service import LibraryRefreshReport


class _LocationService:
    def __init__(self) -> None:
        self.location = LibraryLocation(
            location_id="location-one",
            path=str(Path("/research").resolve()),
            kind=LibraryLocationKind.RECORDING_SOURCE,
            enabled=True,
            processing_policy=RecordingProcessingPolicy.MANUAL,
            created_at="2026-08-19T19:20:00+00:00",
            updated_at="2026-08-19T19:20:00+00:00",
        )
        self.add_calls = []

    def locations(self):
        return (self.location,)

    def add(self, path, *, kind, processing_policy):
        self.add_calls.append((path, kind, processing_policy))
        return self.location

    def discover_recordings(self):
        return RecordingDiscoveryReport(
            recordings=(
                DiscoveredRecording(
                    path=str(Path("/research/interview.mp4").resolve()),
                    size_bytes=42,
                    location_ids=("location-one",),
                    automatic_processing_requested=False,
                ),
            ),
            unavailable_location_ids=(),
        )

    def refresh_transcript_locations(self, *, verify=False):
        return ManagedTranscriptRefreshReport(
            refresh=LibraryRefreshReport(
                backend_id="test",
                indexed_documents=1,
                added_document_ids=(),
                updated_document_ids=(),
                removed_document_ids=(),
                unchanged_document_ids=("doc-1",),
                skipped_files=0,
                semantic_invalidated=False,
                verified_all_tracked=verify,
            ),
            unavailable_location_ids=(),
        )


class _WorkspaceService:
    def __init__(self) -> None:
        self.calls = []

    def discover(self, text, *, limit=20, context_segments=0):
        self.calls.append((text, limit, context_segments))
        return _workspace_discovery(text)


def _services(
    locations: _LocationService | None = None,
    workspace: _WorkspaceService | None = None,
) -> DesktopServices:
    return DesktopServices(
        locations=cast(Any, locations or _LocationService()),
        workspace=cast(Any, workspace or _WorkspaceService()),
        research_search=cast(Any, object()),
        processing=cast(Any, object()),
    )


def _evidence_context(query_text: str) -> tuple[EvidenceContextSegment, ...]:
    previous_word = EvidenceWord(
        segment_id="segment-0",
        word_index=0,
        start_seconds=850.0,
        end_seconds=850.4,
        text="Earlier",
        speaker_ref="speaker-1",
    )
    result_words = (
        EvidenceWord(
            segment_id="segment-1",
            word_index=0,
            start_seconds=862.0,
            end_seconds=862.3,
            text="The",
            speaker_ref="speaker-1",
        ),
        EvidenceWord(
            segment_id="segment-1",
            word_index=1,
            start_seconds=862.5,
            end_seconds=862.8,
            text=query_text,
            speaker_ref="speaker-1",
            highlighted=True,
        ),
        EvidenceWord(
            segment_id="segment-1",
            word_index=2,
            start_seconds=862.9,
            end_seconds=863.4,
            text="program",
            speaker_ref="speaker-1",
        ),
    )
    next_word = EvidenceWord(
        segment_id="segment-2",
        word_index=0,
        start_seconds=871.0,
        end_seconds=871.4,
        text="Later",
        speaker_ref="speaker-1",
    )
    return (
        EvidenceContextSegment(
            segment_id="segment-0",
            start_seconds=850.0,
            end_seconds=861.0,
            text="Earlier context before the result.",
            speaker_refs=("speaker-1",),
            words=(previous_word,),
            is_result_segment=False,
            lexical_match=False,
        ),
        EvidenceContextSegment(
            segment_id="segment-1",
            start_seconds=862.0,
            end_seconds=870.0,
            text=f"The {query_text} program started here.",
            speaker_refs=("speaker-1",),
            words=result_words,
            is_result_segment=True,
            lexical_match=True,
        ),
        EvidenceContextSegment(
            segment_id="segment-2",
            start_seconds=871.0,
            end_seconds=880.0,
            text="Later context after the result.",
            speaker_refs=("speaker-1",),
            words=(next_word,),
            is_result_segment=False,
            lexical_match=False,
        ),
    )


def _workspace_discovery(query_text: str = "ABC") -> WorkspaceDiscoveryResponse:
    source_sha = "b" * 64
    canonical_sha = "a" * 64
    query = SearchQuery(query_text, limit=20)
    passage = SearchPassage(
        document_id="doc-1",
        source_sha256=source_sha,
        canonical_sha256=canonical_sha,
        canonical_path="/sensitive/canonical.json",
        source_path="/sensitive/interview.wav",
        chunk_id=None,
        segment_ids=("segment-1",),
        matched_segment_ids=("segment-1",),
        start_seconds=862.0,
        end_seconds=870.0,
        text=f"The {query_text} program started here.",
        languages=("en",),
        speaker_refs=("speaker-1",),
        lexical_rank=1,
        semantic_rank=None,
        fused_rank=None,
    )
    retrieval = SearchResponse(
        query=query,
        mode=RetrievalMode.LEXICAL,
        lexical_backend_id="test-lexical",
        semantic_backend_id=None,
        semantic_profile=None,
        fusion_profile=None,
        results=(passage,),
    )
    matched_word = EvidenceWord(
        segment_id="segment-1",
        word_index=1,
        start_seconds=862.5,
        end_seconds=862.8,
        text=query_text,
        speaker_ref="speaker-1",
        highlighted=True,
    )
    evidence = EvidenceLocation(
        document_id="doc-1",
        source_sha256=source_sha,
        canonical_sha256=canonical_sha,
        canonical_path="/sensitive/canonical.json",
        source_path="/sensitive/interview.wav",
        result_segment_ids=("segment-1",),
        start_seconds=862.0,
        end_seconds=870.0,
        seek_seconds=862.5,
        result_speaker_refs=("speaker-1",),
        matched_words=(matched_word,),
        context_segments=_evidence_context(query_text),
    )
    located = LocatedSearchPassage(
        passage=passage,
        evidence=evidence,
        speakers=(SpeakerDisplay("speaker-1", "Participant A"),),
    )
    navigation = ResearchSearchResponse(retrieval=retrieval, results=(located,))
    transcript_result = WorkspaceSearchPassage(
        located=located,
        research=ResearchEvidenceView(
            note_ids=("note-1",),
            tags=("program",),
            collections=("Oral histories",),
        ),
    )
    transcripts = WorkspaceSearchResponse(
        navigation=navigation,
        filters=ResearchQueryFilters(),
        results=(transcript_result,),
    )
    anchor = EvidenceAnchor(
        document_id="doc-1",
        source_sha256=source_sha,
        canonical_sha256=canonical_sha,
        canonical_path="/sensitive/canonical.json",
        source_path="/sensitive/interview.wav",
        segment_ids=("segment-1",),
        start_seconds=862.0,
        end_seconds=870.0,
    )
    note = ResearchNote(
        note_id="note-1",
        body=f"Follow up on the {query_text} program.",
        anchor=anchor,
        tag_ids=("tag-1",),
        collection_ids=("collection-1",),
        created_at="2026-08-19T20:00:00+00:00",
        updated_at="2026-08-19T20:00:00+00:00",
    )
    return WorkspaceDiscoveryResponse(
        query=query_text,
        transcripts=transcripts,
        notes=(
            ResearchNoteView(
                note=note,
                current=True,
                tags=("program",),
                collections=("Oral histories",),
            ),
        ),
        tags=(ResearchTag(tag_id="tag-1", name="program"),),
        collections=(
            ResearchCollection(collection_id="collection-1", name="Oral histories"),
        ),
    )


def _request(method, params=None):
    return {
        "protocol_version": 1,
        "request_id": "request-1",
        "method": method,
        "params": {} if params is None else params,
    }


def test_list_locations_serializes_only_typed_location_state():
    response = handle_request(_request("locations.list"), _services())

    assert response["ok"] is True
    assert response["result"][0]["location_id"] == "location-one"
    assert response["result"][0]["kind"] == "recording-source"


def test_add_location_preserves_explicit_automatic_opt_in():
    service = _LocationService()
    response = handle_request(
        _request(
            "locations.add",
            {
                "path": "/research",
                "kind": "recording-source",
                "processing_policy": "automatic",
            },
        ),
        _services(locations=service),
    )

    assert response["ok"] is True
    assert service.add_calls == [
        (
            "/research",
            LibraryLocationKind.RECORDING_SOURCE,
            RecordingProcessingPolicy.AUTOMATIC,
        )
    ]


def test_unknown_method_fails_closed_without_dispatch():
    response = handle_request(_request("shell.exec"), _services())

    assert response["ok"] is False
    assert response["error"] == {
        "code": "invalid_request",
        "message": "The desktop request was invalid or incompatible",
    }


def test_extra_params_fail_closed():
    response = handle_request(
        _request("locations.list", {"sql": "DROP TABLE transcripts"}),
        _services(),
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "invalid_request"


def test_safe_application_error_crosses_bridge_without_cause_details():
    class _FailingService(_LocationService):
        def add(self, path, *, kind, processing_policy):
            raise LibraryLocationError(
                "That location is not available",
                cause=RuntimeError("secret internal path detail"),
            )

    response = handle_request(
        _request(
            "locations.add",
            {
                "path": "/research",
                "kind": "recording-source",
                "processing_policy": "manual",
            },
        ),
        _services(locations=_FailingService()),
    )

    assert response["ok"] is False
    assert response["error"]["message"] == "That location is not available"
    assert "secret internal path detail" not in str(response)


def test_recording_discovery_does_not_claim_processing_occurred():
    response = handle_request(_request("recordings.discover"), _services())

    assert response["ok"] is True
    assert response["result"]["recordings"] == [
        {
            "path": str(Path("/research/interview.mp4").resolve()),
            "size_bytes": 42,
            "location_ids": ["location-one"],
            "automatic_processing_requested": False,
        }
    ]


def test_transcript_refresh_respects_verify_flag():
    response = handle_request(
        _request("transcripts.refresh", {"verify": True}),
        _services(),
    )

    assert response["ok"] is True
    assert response["result"]["verified_all_tracked"] is True


def test_workspace_discovery_returns_verified_context_without_paths():
    workspace = _WorkspaceService()
    response = handle_request(
        _request(
            "workspace.discover",
            {"text": "  ABC  ", "limit": 12, "context_segments": 2},
        ),
        _services(workspace=workspace),
    )

    assert response["ok"] is True
    assert workspace.calls == [("ABC", 12, 2)]
    result = response["result"]
    assert result["query"] == "ABC"
    assert result["total_count"] == 4
    evidence = result["evidence"][0]
    assert evidence["seek_seconds"] == 862.5
    assert evidence["matched_words"][0]["text"] == "ABC"
    assert evidence["matched_words"][0]["highlighted"] is True
    assert [item["segment_id"] for item in evidence["context_segments"]] == [
        "segment-0",
        "segment-1",
        "segment-2",
    ]
    assert evidence["context_segments"][1]["is_result_segment"] is True
    assert evidence["context_segments"][1]["words"][1]["highlighted"] is True
    assert result["notes"][0]["current"] is True
    assert result["tags"] == [{"tag_id": "tag-1", "name": "program"}]
    assert "/sensitive" not in str(result)
    assert "canonical_path" not in str(result)
    assert "source_path" not in str(result)


def test_workspace_discovery_rejects_blank_text_and_extra_fields():
    blank = handle_request(
        _request("workspace.discover", {"text": "   "}),
        _services(),
    )
    extra = handle_request(
        _request("workspace.discover", {"text": "ABC", "sql": "SELECT *"}),
        _services(),
    )

    assert blank["ok"] is False
    assert blank["error"]["code"] == "invalid_request"
    assert extra["ok"] is False
    assert extra["error"]["code"] == "invalid_request"
