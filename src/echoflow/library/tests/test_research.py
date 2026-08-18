from unittest.mock import Mock

from echoflow.library.evidence import EvidenceLocation
from echoflow.library.index import SearchQuery
from echoflow.library.research import ResearchNavigationService
from echoflow.library.retrieval import RetrievalMode, SearchPassage, SearchResponse


def _passage() -> SearchPassage:
    return SearchPassage(
        document_id="job-1",
        source_sha256="a" * 64,
        canonical_sha256="b" * 64,
        canonical_path="/canonical.json",
        source_path="/recording.wav",
        chunk_id=None,
        segment_ids=("segment-000001",),
        matched_segment_ids=("segment-000001",),
        start_seconds=1.0,
        end_seconds=2.0,
        text="Housing matters",
        languages=("en",),
        speaker_refs=("speaker-02",),
        lexical_rank=1,
        semantic_rank=None,
        fused_rank=None,
    )


def _location(*, refs: tuple[str, ...] = ("speaker-02",)) -> EvidenceLocation:
    return EvidenceLocation(
        document_id="job-1",
        source_sha256="a" * 64,
        canonical_sha256="b" * 64,
        canonical_path="/canonical.json",
        source_path="/recording.wav",
        result_segment_ids=("segment-000001",),
        start_seconds=1.0,
        end_seconds=2.0,
        seek_seconds=1.0,
        result_speaker_refs=refs,
        matched_words=(),
        context_segments=(),
    )


def _retrieval(*passages: SearchPassage) -> SearchResponse:
    return SearchResponse(
        query=SearchQuery("housing"),
        mode=RetrievalMode.LEXICAL,
        lexical_backend_id="duckdb-bm25-v1",
        semantic_backend_id=None,
        semantic_profile=None,
        fusion_profile=None,
        results=tuple(passages),
    )


def test_research_navigation_adds_display_names_without_mutating_retrieval() -> None:
    passage = _passage()
    retrieval = _retrieval(passage)
    library = Mock()
    library.retrieve.return_value = retrieval
    locator = Mock()
    locator.locate_response.return_value = (_location(),)
    labels = Mock()
    labels.display_labels.return_value = {"speaker-02": "Dr. Chen"}
    service = ResearchNavigationService(library, locator, labels)

    response = service.search(SearchQuery("housing"), context_segments=1)

    assert response.retrieval is retrieval
    assert response.results[0].passage is passage
    assert response.results[0].passage.speaker_refs == ("speaker-02",)
    assert response.results[0].speakers[0].display_name == "Dr. Chen (speaker-02)"
    locator.locate_response.assert_called_once_with(retrieval, context_segments=1)
    labels.display_labels.assert_called_once_with(
        document_id="job-1",
        canonical_sha256="b" * 64,
        speaker_refs=("speaker-02",),
    )


def test_label_lookup_is_batched_per_canonical_generation() -> None:
    first = _passage()
    second = SearchPassage(
        document_id=first.document_id,
        source_sha256=first.source_sha256,
        canonical_sha256=first.canonical_sha256,
        canonical_path=first.canonical_path,
        source_path=first.source_path,
        chunk_id=None,
        segment_ids=("segment-000002",),
        matched_segment_ids=("segment-000002",),
        start_seconds=3.0,
        end_seconds=4.0,
        text="Another speaker",
        languages=("en",),
        speaker_refs=("speaker-03",),
        lexical_rank=2,
        semantic_rank=None,
        fused_rank=None,
    )
    retrieval = _retrieval(first, second)
    library = Mock()
    library.retrieve.return_value = retrieval
    locator = Mock()
    locator.locate_response.return_value = (
        _location(refs=("speaker-02",)),
        EvidenceLocation(
            document_id="job-1",
            source_sha256="a" * 64,
            canonical_sha256="b" * 64,
            canonical_path="/canonical.json",
            source_path="/recording.wav",
            result_segment_ids=("segment-000002",),
            start_seconds=3.0,
            end_seconds=4.0,
            seek_seconds=3.0,
            result_speaker_refs=("speaker-03",),
            matched_words=(),
            context_segments=(),
        ),
    )
    labels = Mock()
    labels.display_labels.return_value = {
        "speaker-02": "Dr. Chen",
        "speaker-03": "Interviewer",
    }
    service = ResearchNavigationService(library, locator, labels)

    response = service.search(SearchQuery("housing"))

    assert labels.display_labels.call_count == 1
    labels.display_labels.assert_called_once_with(
        document_id="job-1",
        canonical_sha256="b" * 64,
        speaker_refs=("speaker-02", "speaker-03"),
    )
    assert [result.speakers[0].display_name for result in response.results] == [
        "Dr. Chen (speaker-02)",
        "Interviewer (speaker-03)",
    ]
