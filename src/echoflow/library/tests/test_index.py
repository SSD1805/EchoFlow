import pytest

from echoflow.library.index import (
    IndexedSegment,
    IndexedTranscript,
    SearchOperator,
    SearchQuery,
    SearchSort,
    TranscriptMatch,
)


def test_indexed_segment_validates_identity_timestamps_text_and_optional_labels() -> None:
    with pytest.raises(ValueError, match="segment_id"):
        IndexedSegment(" ", 0, 1, "text")
    with pytest.raises(ValueError, match="timestamps"):
        IndexedSegment("segment-1", 2, 1, "text")
    with pytest.raises(ValueError, match="text"):
        IndexedSegment("segment-1", 0, 1, " ")
    with pytest.raises(ValueError, match="language"):
        IndexedSegment("segment-1", 0, 1, "text", language=" ")
    with pytest.raises(ValueError, match="speaker_ref"):
        IndexedSegment("segment-1", 0, 1, "text", speaker_ref=" ")


def test_indexed_transcript_validates_evidence_identity() -> None:
    segment = IndexedSegment("segment-1", 0, 1, "hello")
    with pytest.raises(ValueError, match="document_id"):
        IndexedTranscript(" ", "0" * 64, 1, None, "/a.json", None, 1, 0, (segment,))
    with pytest.raises(ValueError, match="source_sha256"):
        IndexedTranscript("job", "BAD", 1, None, "/a.json", None, 1, 0, (segment,))
    with pytest.raises(ValueError, match="schema"):
        IndexedTranscript("job", "0" * 64, 0, None, "/a.json", None, 1, 0, (segment,))
    with pytest.raises(ValueError, match="canonical_path"):
        IndexedTranscript("job", "0" * 64, 1, None, " ", None, 1, 0, (segment,))
    with pytest.raises(ValueError, match="source_path"):
        IndexedTranscript("job", "0" * 64, 1, None, "/a.json", " ", 1, 0, (segment,))
    with pytest.raises(ValueError, match="source_size_bytes"):
        IndexedTranscript("job", "0" * 64, 1, None, "/a.json", None, 0, 0, (segment,))
    with pytest.raises(ValueError, match="source_modified_ns"):
        IndexedTranscript("job", "0" * 64, 1, None, "/a.json", None, 1, -1, (segment,))
    with pytest.raises(ValueError, match="unique"):
        IndexedTranscript(
            "job",
            "0" * 64,
            1,
            None,
            "/a.json",
            None,
            1,
            0,
            (segment, segment),
        )


def test_search_query_is_typed_bounded_and_deduplicated() -> None:
    query = SearchQuery(
        "housing security",
        phrase=True,
        operator=SearchOperator.ALL,
        speaker_refs=("speaker-01",),
        languages=("en",),
        document_ids=("job-1",),
        sort=SearchSort.TIMELINE,
        limit=25,
    )
    assert query.phrase is True
    assert query.operator is SearchOperator.ALL
    assert query.sort is SearchSort.TIMELINE

    with pytest.raises(ValueError, match="query text"):
        SearchQuery(" ")
    with pytest.raises(ValueError, match="between 1 and 1000"):
        SearchQuery("housing", limit=0)
    with pytest.raises(ValueError, match="between 1 and 1000"):
        SearchQuery("housing", limit=1_001)
    with pytest.raises(ValueError, match="empty"):
        SearchQuery("housing", languages=("",))
    with pytest.raises(ValueError, match="duplicates"):
        SearchQuery("housing", speaker_refs=("speaker-01", "speaker-01"))


def test_transcript_match_validates_evidence_shape() -> None:
    match = TranscriptMatch(
        document_id="job",
        source_sha256="0" * 64,
        canonical_path="/transcript.json",
        source_path="/audio.wav",
        segment_id="segment-1",
        start_seconds=0,
        end_seconds=1,
        text="hello",
        language="en",
        speaker_ref="speaker-01",
        score=1.2,
    )
    assert match.score == 1.2
    with pytest.raises(ValueError, match="document_id"):
        TranscriptMatch("", "0" * 64, "/a", None, "s", 0, 1, "x", None, None, 0)
    with pytest.raises(ValueError, match="segment_id"):
        TranscriptMatch("j", "0" * 64, "/a", None, "", 0, 1, "x", None, None, 0)
    with pytest.raises(ValueError, match="timestamps"):
        TranscriptMatch("j", "0" * 64, "/a", None, "s", 2, 1, "x", None, None, 0)
    with pytest.raises(ValueError, match="text"):
        TranscriptMatch("j", "0" * 64, "/a", None, "s", 0, 1, " ", None, None, 0)
