from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from hypothesis import given, strategies as st

from echoflow.library.index import IndexedSegment, IndexedTranscript
from echoflow.library.semantic import (
    ChunkingProfile,
    SentenceTransformersE5Provider,
    build_search_chunks,
    corpus_fingerprint,
)


def _transcript(
    tmp_path: Path,
    *,
    canonical_digest: str = "1",
    segments: tuple[IndexedSegment, ...],
) -> IndexedTranscript:
    return IndexedTranscript(
        document_id="job-1",
        source_sha256="0" * 64,
        canonical_sha256=canonical_digest * 64,
        transcript_schema_version=1,
        detected_language="en",
        canonical_path=str(tmp_path / "job-1.json"),
        source_path=str(tmp_path / "job-1.wav"),
        source_size_bytes=10,
        source_modified_ns=1,
        segments=segments,
    )


def test_chunks_are_deterministic_context_windows_anchored_to_segments(
    tmp_path: Path,
) -> None:
    transcript = _transcript(
        tmp_path,
        segments=(
            IndexedSegment("s1", 0, 1, "one two", "en", "speaker-02"),
            IndexedSegment("s2", 1, 2, "three four", "fr", "speaker-01"),
            IndexedSegment("s3", 2, 3, "five six", "en", None),
        ),
    )
    profile = ChunkingProfile("tiny-test", target_words=3, max_words=4)

    first = build_search_chunks((transcript,), profile=profile)
    second = build_search_chunks((transcript,), profile=profile)

    assert first == second
    assert [chunk.segment_ids for chunk in first] == [("s1", "s2"), ("s3",)]
    assert first[0].text == "one two three four"
    assert first[0].start_seconds == 0
    assert first[0].end_seconds == 2
    assert first[0].languages == ("en", "fr")
    assert first[0].speaker_refs == ("speaker-01", "speaker-02")
    assert first[0].canonical_sha256 == "1" * 64
    assert first[0].chunk_id.startswith("chunk-")


def test_chunking_never_turns_a_long_source_segment_into_fake_evidence(
    tmp_path: Path,
) -> None:
    transcript = _transcript(
        tmp_path,
        segments=(
            IndexedSegment("long", 0, 10, " ".join(["word"] * 12)),
            IndexedSegment("short", 10, 11, "tail"),
        ),
    )
    profile = ChunkingProfile("tiny-test", target_words=3, max_words=4)

    chunks = build_search_chunks((transcript,), profile=profile)

    assert chunks[0].segment_ids == ("long",)
    assert chunks[0].start_seconds == 0
    assert chunks[0].end_seconds == 10
    assert chunks[1].segment_ids == ("short",)


@given(
    word_counts=st.lists(
        st.integers(min_value=1, max_value=24), min_size=1, max_size=16
    ),
    target_words=st.integers(min_value=1, max_value=12),
    slack=st.integers(min_value=0, max_value=12),
)
def test_chunking_property_preserves_every_evidence_segment_exactly_once(
    word_counts: list[int],
    target_words: int,
    slack: int,
) -> None:
    segments = tuple(
        IndexedSegment(
            f"s{index}",
            float(index),
            float(index + 1),
            " ".join([f"w{index}"] * word_count),
            "en" if index % 2 == 0 else "fr",
            f"speaker-{index % 3:02d}",
        )
        for index, word_count in enumerate(word_counts)
    )
    transcript = _transcript(Path("property-fixture"), segments=segments)
    profile = ChunkingProfile(
        "property-test",
        target_words=target_words,
        max_words=target_words + slack,
    )

    chunks = build_search_chunks((transcript,), profile=profile)

    assert tuple(
        segment_id for chunk in chunks for segment_id in chunk.segment_ids
    ) == tuple(segment.segment_id for segment in segments)
    assert chunks == build_search_chunks((transcript,), profile=profile)

    by_id = {segment.segment_id: segment for segment in segments}
    for chunk in chunks:
        first = by_id[chunk.segment_ids[0]]
        last = by_id[chunk.segment_ids[-1]]
        assert chunk.start_seconds == first.start_seconds
        assert chunk.end_seconds == last.end_seconds
        if len(chunk.text.split()) > profile.max_words:
            assert len(chunk.segment_ids) == 1
            assert len(first.text.split()) > profile.max_words


@pytest.mark.parametrize(
    ("target_words", "max_words", "message"),
    (
        (0, 1, "target_words"),
        (2, 1, "max_words"),
    ),
)
def test_chunking_profile_rejects_invalid_boundaries(
    target_words: int,
    max_words: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ChunkingProfile(
            "invalid",
            target_words=target_words,
            max_words=max_words,
        )


def test_corpus_fingerprint_tracks_canonical_evidence_not_only_source_media(
    tmp_path: Path,
) -> None:
    segments = (IndexedSegment("s1", 0, 1, "same source"),)
    before = _transcript(tmp_path, canonical_digest="1", segments=segments)
    after = _transcript(tmp_path, canonical_digest="2", segments=segments)

    assert corpus_fingerprint((before,)) != corpus_fingerprint((after,))


class _FakeEncoded:
    def __init__(self, rows: list[list[float]]) -> None:
        self.rows = rows

    def tolist(self) -> list[list[float]]:
        return self.rows


class _FakeModel:
    instances: list["_FakeModel"] = []

    def __init__(
        self,
        path: str,
        *,
        local_files_only: bool,
        trust_remote_code: bool,
    ) -> None:
        assert local_files_only is True
        assert trust_remote_code is False
        self.path = path
        self.calls: list[tuple[list[str], bool, bool]] = []
        self.instances.append(self)

    def encode(
        self,
        texts: list[str],
        *,
        normalize_embeddings: bool,
        show_progress_bar: bool,
    ) -> _FakeEncoded:
        self.calls.append((texts, normalize_embeddings, show_progress_bar))
        rows = []
        for _ in texts:
            row = [0.0] * 384
            row[0] = 1.0
            rows.append(row)
        return _FakeEncoded(rows)


def _module_loader(name: str) -> Any:
    assert name == "sentence_transformers"
    return SimpleNamespace(SentenceTransformer=_FakeModel)


def _module_loader_with_rows(rows: list[list[float]]) -> Any:
    class _ConfiguredModel:
        def __init__(
            self,
            path: str,
            *,
            local_files_only: bool,
            trust_remote_code: bool,
        ) -> None:
            assert path
            assert local_files_only is True
            assert trust_remote_code is False

        def encode(
            self,
            texts: list[str],
            *,
            normalize_embeddings: bool,
            show_progress_bar: bool,
        ) -> _FakeEncoded:
            assert texts
            assert normalize_embeddings is True
            assert show_progress_bar is False
            return _FakeEncoded(rows)

    def loader(name: str) -> Any:
        assert name == "sentence_transformers"
        return SimpleNamespace(SentenceTransformer=_ConfiguredModel)

    return loader


def _provider_with_rows(
    tmp_path: Path, rows: list[list[float]]
) -> SentenceTransformersE5Provider:
    snapshot = tmp_path / ("b" * 40)
    snapshot.mkdir(exist_ok=True)
    return SentenceTransformersE5Provider(
        snapshot_path=snapshot,
        resolved_revision=snapshot.name,
        module_loader=_module_loader_with_rows(rows),
    )


def test_e5_provider_keeps_query_and_passage_semantics_explicit_and_local(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / ("a" * 40)
    snapshot.mkdir()
    provider = SentenceTransformersE5Provider(
        snapshot_path=snapshot,
        resolved_revision=snapshot.name,
        module_loader=_module_loader,
    )

    query = provider.embed_queries(("housing insecurity",))
    passages = provider.embed_passages(("I could not make rent",))

    assert len(query[0]) == 384
    assert len(passages[0]) == 384
    model = _FakeModel.instances[-1]
    assert model.path == str(snapshot.resolve())
    assert model.calls[0][0] == ["query: housing insecurity"]
    assert model.calls[1][0] == ["passage: I could not make rent"]
    assert all(call[1] is True and call[2] is False for call in model.calls)
    assert provider.profile.model_id == "intfloat/multilingual-e5-small"
    assert provider.profile.resolved_revision == snapshot.name


def test_e5_provider_rejects_non_snapshot_path_and_revision_mismatch(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="unavailable"):
        SentenceTransformersE5Provider(
            snapshot_path=tmp_path / "missing",
            resolved_revision="revision",
        )

    snapshot = tmp_path / "revision"
    snapshot.mkdir()
    with pytest.raises(ValueError, match="must end"):
        SentenceTransformersE5Provider(
            snapshot_path=snapshot,
            resolved_revision="other",
        )


def test_e5_provider_rejects_wrong_vector_shape(tmp_path: Path) -> None:
    provider = _provider_with_rows(tmp_path, [[1.0]])

    with pytest.raises(RuntimeError, match="dimension"):
        provider.embed_queries(("housing",))


def test_e5_provider_rejects_non_finite_vectors(tmp_path: Path) -> None:
    row = [0.0] * 384
    row[0] = float("nan")
    provider = _provider_with_rows(tmp_path, [row])

    with pytest.raises(RuntimeError, match="non-finite"):
        provider.embed_queries(("housing",))


def test_e5_provider_rejects_non_normalized_vectors(tmp_path: Path) -> None:
    row = [0.0] * 384
    row[0] = 2.0
    provider = _provider_with_rows(tmp_path, [row])

    with pytest.raises(RuntimeError, match="l2-normalized"):
        provider.embed_queries(("housing",))


def test_e5_provider_rejects_wrong_output_count(tmp_path: Path) -> None:
    row = [0.0] * 384
    row[0] = 1.0
    provider = _provider_with_rows(tmp_path, [row])

    with pytest.raises(RuntimeError, match="wrong number"):
        provider.embed_queries(("housing", "rent"))


def test_e5_provider_rejects_blank_text_and_short_circuits_empty_batch(
    tmp_path: Path,
) -> None:
    provider = _provider_with_rows(tmp_path, [])

    assert provider.embed_queries(()) == ()
    with pytest.raises(ValueError, match="empty text"):
        provider.embed_queries(("   ",))
