import hashlib
import json
from pathlib import Path

import pytest

from echoflow.interfaces.local_file_manager import LocalFileManager
from echoflow.library.evidence import EvidenceLocator
from echoflow.library.errors import EvidenceNavigationError
from echoflow.library.index import SearchQuery
from echoflow.library.retrieval import (
    RetrievalMode,
    SearchPassage,
    SearchResponse,
)
from echoflow.library.semantic import EmbeddingProfile


def _canonical(path: Path) -> str:
    document = {
        "schema_version": 1,
        "job_id": "job-1",
        "source": {"sha256": "a" * 64},
        "segments": [
            {
                "segment_id": "segment-000000",
                "start_seconds": 0.0,
                "end_seconds": 1.0,
                "text": "Before the answer.",
                "speaker_ref": "speaker-01",
                "words": [
                    {
                        "start_seconds": 0.0,
                        "end_seconds": 0.4,
                        "text": "Before",
                        "speaker_ref": "speaker-01",
                    },
                    {
                        "start_seconds": 0.5,
                        "end_seconds": 0.8,
                        "text": " the",
                        "speaker_ref": "speaker-01",
                    },
                    {
                        "start_seconds": 0.8,
                        "end_seconds": 1.0,
                        "text": " answer.",
                        "speaker_ref": "speaker-01",
                    },
                ],
            },
            {
                "segment_id": "segment-000001",
                "start_seconds": 1.0,
                "end_seconds": 3.0,
                "text": "Housing affordability matters here.",
                "speaker_ref": "speaker-02",
                "words": [
                    {
                        "start_seconds": 1.1,
                        "end_seconds": 1.5,
                        "text": "Housing",
                        "speaker_ref": "speaker-02",
                    },
                    {
                        "start_seconds": 1.6,
                        "end_seconds": 2.2,
                        "text": " affordability",
                        "speaker_ref": "speaker-02",
                    },
                    {
                        "start_seconds": 2.3,
                        "end_seconds": 2.6,
                        "text": " matters",
                        "speaker_ref": "speaker-02",
                    },
                    {
                        "start_seconds": 2.7,
                        "end_seconds": 3.0,
                        "text": " here.",
                        "speaker_ref": "speaker-02",
                    },
                ],
            },
            {
                "segment_id": "segment-000002",
                "start_seconds": 3.0,
                "end_seconds": 4.0,
                "text": "After the answer.",
                "speaker_ref": None,
            },
        ],
    }
    payload = json.dumps(document, sort_keys=True).encode()
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _passage(path: Path, digest: str, *, matched: bool = True) -> SearchPassage:
    return SearchPassage(
        document_id="job-1",
        source_sha256="a" * 64,
        canonical_sha256=digest,
        canonical_path=str(path),
        source_path="/recording.wav",
        chunk_id=None,
        segment_ids=("segment-000001",),
        matched_segment_ids=("segment-000001",) if matched else (),
        start_seconds=1.0,
        end_seconds=3.0,
        text="Housing affordability matters here.",
        languages=("en",),
        speaker_refs=("speaker-02",),
        lexical_rank=1 if matched else None,
        semantic_rank=None if matched else 1,
        fused_rank=None,
    )


def _response(
    passage: SearchPassage,
    *,
    query: SearchQuery,
    mode: RetrievalMode = RetrievalMode.LEXICAL,
) -> SearchResponse:
    return SearchResponse(
        query=query,
        mode=mode,
        lexical_backend_id="duckdb-bm25-v1" if mode is RetrievalMode.LEXICAL else None,
        semantic_backend_id=(
            None if mode is RetrievalMode.LEXICAL else "duckdb-exact-vector-v1"
        ),
        semantic_profile=None,
        fusion_profile=None,
        results=(passage,),
    )


def _locator() -> EvidenceLocator:
    return EvidenceLocator(LocalFileManager())  # type: ignore[arg-type]


def test_lexical_result_highlights_aligned_words_and_seeks_to_first_match(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "transcript.json"
    digest = _canonical(canonical)
    passage = _passage(canonical, digest)
    response = _response(passage, query=SearchQuery("housing matters"))

    location = _locator().locate_response(response)[0]

    assert [word.text.strip() for word in location.matched_words] == [
        "Housing",
        "matters",
    ]
    assert location.seek_seconds == 1.1
    assert location.result_speaker_refs == ("speaker-02",)
    assert location.context_segments[0].segment_id == "segment-000001"


def test_phrase_highlight_requires_contiguous_canonical_word_tokens(tmp_path: Path) -> None:
    canonical = tmp_path / "transcript.json"
    digest = _canonical(canonical)
    passage = _passage(canonical, digest)
    response = _response(
        passage,
        query=SearchQuery("housing affordability", phrase=True),
    )

    location = _locator().locate_response(response)[0]

    assert [word.word_index for word in location.matched_words] == [0, 1]
    assert [word.text.strip() for word in location.matched_words] == [
        "Housing",
        "affordability",
    ]


def test_semantic_only_result_does_not_invent_exact_word_highlight(tmp_path: Path) -> None:
    canonical = tmp_path / "transcript.json"
    digest = _canonical(canonical)
    passage = _passage(canonical, digest, matched=False)
    response = SearchResponse(
        query=SearchQuery("people struggling to pay rent"),
        mode=RetrievalMode.SEMANTIC,
        lexical_backend_id=None,
        semantic_backend_id="duckdb-exact-vector-v1",
        semantic_profile=EmbeddingProfile(
            profile_id="profile",
            provider="fake",
            model_id="fake/model",
            resolved_revision="revision",
            dimensions=2,
            normalization="l2",
            pooling="mean",
            distance_metric="dot",
            query_prefix="query: ",
            passage_prefix="passage: ",
            chunking_profile_id="search-chunk-v1",
            snapshot_path="/private/revision",
        ),
        fusion_profile=None,
        results=(passage,),
    )

    location = _locator().locate_response(response)[0]

    assert location.matched_words == ()
    assert location.seek_seconds == 1.0
    assert not any(
        word.highlighted
        for segment in location.context_segments
        for word in segment.words
    )


def test_context_expansion_keeps_neighbors_distinct_from_result(tmp_path: Path) -> None:
    canonical = tmp_path / "transcript.json"
    digest = _canonical(canonical)
    response = _response(_passage(canonical, digest), query=SearchQuery("housing"))

    location = _locator().locate_response(response, context_segments=1)[0]

    assert [segment.segment_id for segment in location.context_segments] == [
        "segment-000000",
        "segment-000001",
        "segment-000002",
    ]
    assert [segment.is_result_segment for segment in location.context_segments] == [
        False,
        True,
        False,
    ]
    assert location.context_segments[2].words == ()


def test_stale_canonical_bytes_fail_closed(tmp_path: Path) -> None:
    canonical = tmp_path / "transcript.json"
    digest = _canonical(canonical)
    response = _response(_passage(canonical, digest), query=SearchQuery("housing"))
    canonical.write_text('{"schema_version": 1}')

    with pytest.raises(EvidenceNavigationError, match="changed"):
        _locator().locate_response(response)


@pytest.mark.parametrize("context_segments", [-1, 11])
def test_context_expansion_is_bounded(tmp_path: Path, context_segments: int) -> None:
    canonical = tmp_path / "transcript.json"
    digest = _canonical(canonical)
    response = _response(_passage(canonical, digest), query=SearchQuery("housing"))

    with pytest.raises(ValueError, match="between 0 and 10"):
        _locator().locate_response(response, context_segments=context_segments)
