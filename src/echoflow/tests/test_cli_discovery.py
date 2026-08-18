import json
from pathlib import Path
from unittest.mock import Mock

import typer
from typer.testing import CliRunner

from echoflow.cli_library import register_library_commands
from echoflow.library.evidence import EvidenceAnchor, EvidenceContextSegment, EvidenceLocation
from echoflow.library.index import SearchQuery
from echoflow.library.research import (
    LocatedSearchPassage,
    ResearchSearchResponse,
    SpeakerDisplay,
)
from echoflow.library.research_state import ResearchCollection, ResearchNote, ResearchTag
from echoflow.library.research_workspace import (
    ResearchEvidenceView,
    ResearchNoteView,
    ResearchQueryFilters,
    WorkspaceDiscoveryResponse,
    WorkspaceSearchPassage,
    WorkspaceSearchResponse,
)
from echoflow.library.retrieval import RetrievalMode, SearchPassage, SearchResponse


def _anchor() -> EvidenceAnchor:
    return EvidenceAnchor(
        document_id="job-1",
        source_sha256="0" * 64,
        canonical_sha256="1" * 64,
        canonical_path="/private/interview.json",
        source_path="/private/interview.wav",
        segment_ids=("segment-000001",),
        start_seconds=1.5,
        end_seconds=2.5,
    )


def _discovery_response() -> WorkspaceDiscoveryResponse:
    query = SearchQuery("housing", limit=20)
    passage = SearchPassage(
        document_id="job-1",
        source_sha256="0" * 64,
        canonical_sha256="1" * 64,
        canonical_path="/private/interview.json",
        source_path=str(Path("/private") / "interview.wav"),
        chunk_id=None,
        segment_ids=("segment-000001",),
        matched_segment_ids=("segment-000001",),
        start_seconds=1.5,
        end_seconds=2.5,
        text="housing affordability matters",
        languages=("en",),
        speaker_refs=("speaker-02",),
        lexical_rank=1,
        semantic_rank=None,
        fused_rank=None,
    )
    retrieval = SearchResponse(
        query=query,
        mode=RetrievalMode.LEXICAL,
        lexical_backend_id="duckdb-bm25-v1",
        semantic_backend_id=None,
        semantic_profile=None,
        fusion_profile=None,
        results=(passage,),
    )
    context = EvidenceContextSegment(
        segment_id="segment-000001",
        start_seconds=1.5,
        end_seconds=2.5,
        text="housing affordability matters",
        speaker_refs=("speaker-02",),
        words=(),
        is_result_segment=True,
        lexical_match=True,
    )
    evidence = EvidenceLocation(
        document_id="job-1",
        source_sha256="0" * 64,
        canonical_sha256="1" * 64,
        canonical_path="/private/interview.json",
        source_path="/private/interview.wav",
        result_segment_ids=("segment-000001",),
        start_seconds=1.5,
        end_seconds=2.5,
        seek_seconds=1.5,
        result_speaker_refs=("speaker-02",),
        matched_words=(),
        context_segments=(context,),
    )
    located = LocatedSearchPassage(
        passage=passage,
        evidence=evidence,
        speakers=(SpeakerDisplay("speaker-02", "Dr. Chen"),),
    )
    navigation = ResearchSearchResponse(retrieval=retrieval, results=(located,))
    transcript_results = WorkspaceSearchResponse(
        navigation=navigation,
        filters=ResearchQueryFilters(),
        results=(
            WorkspaceSearchPassage(
                located,
                ResearchEvidenceView(
                    note_ids=("note-1",),
                    tags=("housing",),
                    collections=("Housing interviews",),
                ),
            ),
        ),
    )
    note = ResearchNote(
        note_id="note-1",
        body="Compare housing finding with the 2024 survey",
        anchor=_anchor(),
        tag_ids=("tag-housing",),
        collection_ids=("collection-housing",),
        created_at="2026-08-18T20:00:00Z",
        updated_at="2026-08-18T20:00:00Z",
    )
    return WorkspaceDiscoveryResponse(
        query="housing",
        transcripts=transcript_results,
        notes=(
            ResearchNoteView(
                note=note,
                current=True,
                tags=("housing",),
                collections=("Housing interviews",),
            ),
        ),
        tags=(ResearchTag("tag-housing", "housing"),),
        collections=(
            ResearchCollection("collection-housing", "Housing interviews"),
        ),
    )


def _app(workspace: Mock) -> typer.Typer:
    app = typer.Typer()
    container = Mock()
    container.research_workspace.return_value = workspace
    container.transcript_library.return_value = Mock()
    container.semantic_embedding_provider.return_value = Mock()
    register_library_commands(app, lambda context: container)
    return app


def test_library_find_json_preserves_typed_groups_and_forwards_discovery_options() -> None:
    workspace = Mock()
    workspace.discover.return_value = _discovery_response()
    app = _app(workspace)

    result = CliRunner().invoke(
        app,
        [
            "library",
            "find",
            "housing",
            "--mode",
            "hybrid",
            "--limit",
            "7",
            "--context-segments",
            "2",
            "--json",
        ],
    )

    assert result.exit_code == 0
    workspace.discover.assert_called_once_with(
        "housing",
        mode=RetrievalMode.HYBRID,
        limit=7,
        context_segments=2,
    )
    payload = json.loads(result.stdout)
    assert payload["query"] == "housing"
    assert payload["total_count"] == 4
    assert payload["groups"]["transcripts"]["count"] == 1
    assert payload["groups"]["transcripts"]["results"][0]["seek_seconds"] == 1.5
    assert payload["groups"]["transcripts"]["results"][0][
        "speaker_display_labels"
    ] == {"speaker-02": "Dr. Chen"}
    assert payload["groups"]["notes"]["results"][0]["body"].startswith("Compare")
    assert payload["groups"]["notes"]["results"][0]["current"] is True
    assert payload["groups"]["tags"]["results"] == [
        {"name": "housing", "tag_id": "tag-housing"}
    ]
    assert payload["groups"]["collections"]["results"] == [
        {
            "collection_id": "collection-housing",
            "name": "Housing interviews",
        }
    ]


def test_library_find_human_view_keeps_result_types_visibly_separate() -> None:
    workspace = Mock()
    workspace.discover.return_value = _discovery_response()
    app = _app(workspace)

    result = CliRunner().invoke(app, ["library", "find", "housing"])

    assert result.exit_code == 0
    assert "Transcript evidence" in result.stdout
    assert "Your notes" in result.stdout
    assert "Tags" in result.stdout
    assert "Collections" in result.stdout
    assert "interview.wav" in result.stdout
    assert "Dr. Chen" in result.stdout
    assert "housing affordability" in result.stdout
    assert "Compare housing finding" in result.stdout
    assert "Housing interviews" in result.stdout


def test_library_find_masks_unexpected_internal_errors() -> None:
    workspace = Mock()
    workspace.discover.side_effect = RuntimeError("/private/secret/research.sqlite3")
    app = _app(workspace)

    result = CliRunner().invoke(app, ["library", "find", "housing"])

    assert result.exit_code == 3
    assert "RuntimeError" in result.stderr
    assert "secret" not in result.stderr
