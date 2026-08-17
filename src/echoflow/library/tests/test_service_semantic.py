import hashlib
import json
from pathlib import Path

import pytest

from echoflow.library.duckdb_index import DuckDbTranscriptIndex
from echoflow.library.duckdb_semantic import DuckDbSemanticIndex
from echoflow.library.errors import SemanticSearchUnavailableError
from echoflow.library.index import SearchQuery
from echoflow.library.retrieval import RetrievalMode
from echoflow.library.semantic import EmbeddingProfile
from echoflow.library.service import TranscriptLibraryService
from echoflow.workspace.models import WorkspacePaths


class LocalStore:
    def ensure_directory_exists(
        self, directory_path: str | Path, *, private: bool = False
    ) -> None:
        path = Path(directory_path)
        path.mkdir(parents=True, exist_ok=True)
        if "library" in path.parts:
            assert private

    def read_file(self, file_path: str | Path) -> bytes:
        return Path(file_path).read_bytes()

    def list_files(
        self,
        directory_path: str | Path,
        extensions: tuple[str, ...] | None = None,
    ) -> list[Path]:
        paths = [path for path in Path(directory_path).iterdir() if path.is_file()]
        if extensions is not None:
            paths = [path for path in paths if path.suffix.lower() in extensions]
        return sorted(paths)


class EmptyLifecycle:
    def list_records(self) -> tuple[object, ...]:
        return ()


class FakeEmbeddingProvider:
    def __init__(self, tmp_path: Path) -> None:
        self._profile = EmbeddingProfile(
            profile_id="fake-profile",
            provider="fake",
            model_id="fake/multilingual",
            resolved_revision="revision",
            dimensions=2,
            normalization="l2",
            pooling="mean",
            distance_metric="dot",
            query_prefix="query: ",
            passage_prefix="passage: ",
            chunking_profile_id="search-chunk-v1",
            snapshot_path=str(tmp_path / "revision"),
        )

    @property
    def profile(self) -> EmbeddingProfile:
        return self._profile

    def embed_queries(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return tuple((1.0, 0.0) for _ in texts)

    def embed_passages(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        return tuple((1.0, 0.0) for _ in texts)


def _paths(tmp_path: Path) -> WorkspacePaths:
    return WorkspacePaths(
        state_dir=tmp_path / "state",
        cache_dir=tmp_path / "cache",
        model_dir=tmp_path / "models",
        output_dir=tmp_path / "output",
    )


def _write_canonical(path: Path, source: Path, text: str) -> None:
    source_bytes = source.read_bytes()
    stat = source.stat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "job_id": "job-1",
                "source": {
                    "sha256": hashlib.sha256(source_bytes).hexdigest(),
                    "size_bytes": len(source_bytes),
                    "modified_ns": stat.st_mtime_ns,
                },
                "detected_language": "en",
                "segments": [
                    {
                        "segment_id": "s1",
                        "start_seconds": 0,
                        "end_seconds": 2,
                        "text": text,
                        "language": "en",
                        "speaker_ref": "speaker-01",
                    }
                ],
            },
            sort_keys=True,
        )
    )


def _service(
    tmp_path: Path,
) -> tuple[TranscriptLibraryService, FakeEmbeddingProvider, Path]:
    paths = _paths(tmp_path)
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    canonical = paths.output_dir / "interview.json"
    _write_canonical(canonical, source, "housing affordability")
    store = LocalStore()
    lexical = DuckDbTranscriptIndex(
        paths.state_dir / "library" / "transcripts.duckdb",
        store,  # type: ignore[arg-type]
    )
    semantic = DuckDbSemanticIndex(
        paths.state_dir / "library" / "semantic.duckdb",
        store,  # type: ignore[arg-type]
    )
    provider = FakeEmbeddingProvider(tmp_path)
    service = TranscriptLibraryService(
        index=lexical,
        lifecycle_store=EmptyLifecycle(),  # type: ignore[arg-type]
        paths=paths,
        file_manager=store,  # type: ignore[arg-type]
        semantic_index=semantic,
        embedding_provider_factory=lambda profile: provider,
    )
    return service, provider, canonical


def test_semantic_rebuild_uses_same_canonical_corpus_and_hybrid_response(
    tmp_path: Path,
) -> None:
    service, provider, _ = _service(tmp_path)

    report = service.rebuild_semantic(provider)
    response = service.retrieve(
        SearchQuery("housing"),
        mode=RetrievalMode.HYBRID,
    )

    assert report.indexed_documents == 1
    assert report.indexed_chunks == 1
    assert report.semantic_backend_id == "duckdb-exact-vector-v1"
    assert len(report.corpus_fingerprint) == 64
    assert response.mode is RetrievalMode.HYBRID
    assert response.results[0].segment_ids == ("s1",)
    assert response.results[0].lexical_rank == 1
    assert response.results[0].semantic_rank == 1
    assert response.results[0].canonical_sha256 is not None


def test_canonical_change_invalidates_semantic_generation_after_lexical_rebuild(
    tmp_path: Path,
) -> None:
    service, provider, canonical = _service(tmp_path)
    service.rebuild_semantic(provider)
    before = service.documents()[0].canonical_sha256
    source = tmp_path / "audio.wav"

    _write_canonical(canonical, source, "housing became unaffordable")
    service.rebuild()

    after = service.documents()[0].canonical_sha256
    assert before != after
    with pytest.raises(SemanticSearchUnavailableError, match="stale"):
        service.retrieve(
            SearchQuery("housing"),
            mode=RetrievalMode.SEMANTIC,
        )


def test_lexical_retrieval_remains_available_without_semantic_runtime(
    tmp_path: Path,
) -> None:
    service, _, _ = _service(tmp_path)
    service.rebuild()

    response = service.retrieve(SearchQuery("housing"))

    assert response.mode is RetrievalMode.LEXICAL
    assert response.results[0].matched_segment_ids == ("s1",)
