from __future__ import annotations

import hashlib
import math
from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from echoflow.library.index import IndexedSegment, IndexedTranscript, SearchQuery

type EmbeddingVector = tuple[float, ...]
type EvidenceKey = tuple[str, str]

_DEFAULT_MODEL_ID = "intfloat/multilingual-e5-small"
_DEFAULT_DIMENSIONS = 384
_DEFAULT_QUERY_PREFIX = "query: "
_DEFAULT_PASSAGE_PREFIX = "passage: "


@dataclass(frozen=True, slots=True)
class ChunkingProfile:
    """Immutable deterministic policy for derived semantic retrieval windows."""

    profile_id: str = "search-chunk-v1"
    target_words: int = 220
    max_words: int = 300

    def __post_init__(self) -> None:
        if not self.profile_id.strip():
            raise ValueError("chunking profile ID cannot be empty")
        if self.target_words < 1:
            raise ValueError("target_words must be positive")
        if self.max_words < self.target_words:
            raise ValueError("max_words must be greater than or equal to target_words")


_DEFAULT_CHUNKING_PROFILE = ChunkingProfile()


@dataclass(frozen=True, slots=True)
class SearchChunk:
    """Rebuildable retrieval window anchored to canonical transcript segments."""

    chunk_id: str
    document_id: str
    source_sha256: str
    canonical_sha256: str
    canonical_path: str
    source_path: str | None
    segment_ids: tuple[str, ...]
    first_segment_id: str
    last_segment_id: str
    start_seconds: float
    end_seconds: float
    text: str
    content_sha256: str
    chunking_profile_id: str
    languages: tuple[str, ...] = ()
    speaker_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_chunk_text_fields(self)
        for name, digest in (
            ("source_sha256", self.source_sha256),
            ("canonical_sha256", self.canonical_sha256),
            ("content_sha256", self.content_sha256),
        ):
            _validate_digest(name, digest)
        _validate_chunk_segments(self)
        _validate_sorted_values("languages", self.languages)
        _validate_sorted_values("speaker_refs", self.speaker_refs)


def _validate_chunk_text_fields(chunk: SearchChunk) -> None:
    for name, value in (
        ("chunk_id", chunk.chunk_id),
        ("document_id", chunk.document_id),
        ("canonical_path", chunk.canonical_path),
        ("first_segment_id", chunk.first_segment_id),
        ("last_segment_id", chunk.last_segment_id),
        ("chunking_profile_id", chunk.chunking_profile_id),
    ):
        if not value.strip():
            raise ValueError(f"{name} cannot be empty")
    if not chunk.text.strip():
        raise ValueError("search chunk text cannot be empty")


def _validate_digest(name: str, digest: str) -> None:
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ValueError(f"{name} must be a lowercase 64-character digest")


def _validate_chunk_segments(chunk: SearchChunk) -> None:
    if not chunk.segment_ids:
        raise ValueError("search chunk must contain at least one segment")
    if chunk.first_segment_id != chunk.segment_ids[0]:
        raise ValueError("first_segment_id must match the first segment")
    if chunk.last_segment_id != chunk.segment_ids[-1]:
        raise ValueError("last_segment_id must match the last segment")
    if len(set(chunk.segment_ids)) != len(chunk.segment_ids):
        raise ValueError("search chunk segment IDs must be unique")
    if chunk.start_seconds < 0 or chunk.end_seconds < chunk.start_seconds:
        raise ValueError("search chunk timestamps must be ordered and non-negative")


def _validate_sorted_values(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain empty values")
    if tuple(sorted(set(values))) != values:
        raise ValueError(f"{name} must be sorted and deduplicated")


@dataclass(frozen=True, slots=True)
class EmbeddingProfile:
    """Immutable identity of one coherent embedding space."""

    profile_id: str
    provider: str
    model_id: str
    resolved_revision: str
    dimensions: int
    normalization: str
    pooling: str
    distance_metric: str
    query_prefix: str
    passage_prefix: str
    chunking_profile_id: str
    snapshot_path: str
    embedding_schema_version: int = 1

    def __post_init__(self) -> None:
        for name in (
            "profile_id",
            "provider",
            "model_id",
            "resolved_revision",
            "normalization",
            "pooling",
            "distance_metric",
            "query_prefix",
            "passage_prefix",
            "chunking_profile_id",
            "snapshot_path",
        ):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} cannot be empty")
        if self.dimensions < 1:
            raise ValueError("embedding dimensions must be positive")
        if self.embedding_schema_version != 1:
            raise ValueError("unsupported embedding schema version")
        if self.normalization != "l2":
            raise ValueError("only l2-normalized embeddings are supported")
        if self.distance_metric != "dot":
            raise ValueError("only dot-product retrieval is supported")

    def identity_tuple(self) -> tuple[object, ...]:
        """Return every load-bearing field used to reject mixed vector spaces."""
        return (
            self.profile_id,
            self.provider,
            self.model_id,
            self.resolved_revision,
            self.dimensions,
            self.normalization,
            self.pooling,
            self.distance_metric,
            self.query_prefix,
            self.passage_prefix,
            self.chunking_profile_id,
            self.snapshot_path,
            self.embedding_schema_version,
        )


@dataclass(frozen=True, slots=True)
class SemanticCandidate:
    chunk: SearchChunk
    score: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.score):
            raise ValueError("semantic score must be finite")


@dataclass(frozen=True, slots=True)
class SemanticState:
    profile: EmbeddingProfile
    corpus_fingerprint: str
    chunk_count: int

    def __post_init__(self) -> None:
        _validate_digest("corpus_fingerprint", self.corpus_fingerprint)
        if self.chunk_count < 0:
            raise ValueError("chunk_count cannot be negative")


@runtime_checkable
class EmbeddingProvider(Protocol):
    @property
    def profile(self) -> EmbeddingProfile: ...

    def embed_queries(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]: ...

    def embed_passages(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]: ...


@runtime_checkable
class SemanticIndex(Protocol):
    @property
    def backend_id(self) -> str: ...

    def rebuild(
        self,
        *,
        state: SemanticState,
        chunks: tuple[SearchChunk, ...],
        vectors: tuple[EmbeddingVector, ...],
    ) -> None: ...

    def state(self) -> SemanticState | None: ...

    def search(
        self, query: SearchQuery, query_vector: EmbeddingVector
    ) -> tuple[SemanticCandidate, ...]: ...

    def chunks_for_segments(
        self, keys: tuple[EvidenceKey, ...]
    ) -> dict[EvidenceKey, SearchChunk]: ...

    def clear(self) -> None: ...

    def close(self) -> None: ...


def corpus_fingerprint(transcripts: tuple[IndexedTranscript, ...]) -> str:
    """Bind a semantic generation to exact canonical artifacts, not source media alone."""
    digest = hashlib.sha256()
    for transcript in sorted(transcripts, key=lambda item: item.document_id):
        digest.update(transcript.document_id.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_canonical_digest(transcript).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _canonical_digest(transcript: IndexedTranscript) -> str:
    if transcript.canonical_sha256 is None:
        raise ValueError(
            "semantic indexing requires a canonical transcript SHA-256; rebuild the library"
        )
    return transcript.canonical_sha256


def build_search_chunks(
    transcripts: tuple[IndexedTranscript, ...],
    *,
    profile: ChunkingProfile = _DEFAULT_CHUNKING_PROFILE,
) -> tuple[SearchChunk, ...]:
    """Combine adjacent ASR segments into deterministic, evidence-anchored windows."""
    chunks: list[SearchChunk] = []
    for transcript in sorted(transcripts, key=lambda item: item.document_id):
        current: list[IndexedSegment] = []
        current_words = 0
        for segment in transcript.segments:
            words = max(1, len(segment.text.split()))
            if current and (
                current_words >= profile.target_words
                or current_words + words > profile.max_words
            ):
                chunks.append(_make_chunk(transcript, tuple(current), profile))
                current = []
                current_words = 0
            current.append(segment)
            current_words += words
            if current_words >= profile.max_words:
                chunks.append(_make_chunk(transcript, tuple(current), profile))
                current = []
                current_words = 0
        if current:
            chunks.append(_make_chunk(transcript, tuple(current), profile))
    return tuple(chunks)


def _make_chunk(
    transcript: IndexedTranscript,
    segments: tuple[IndexedSegment, ...],
    profile: ChunkingProfile,
) -> SearchChunk:
    text = " ".join(segment.text.strip() for segment in segments)
    content_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    material = "\0".join(
        (
            profile.profile_id,
            transcript.document_id,
            segments[0].segment_id,
            segments[-1].segment_id,
            content_sha256,
        )
    )
    chunk_id = "chunk-" + hashlib.sha256(material.encode("utf-8")).hexdigest()
    return SearchChunk(
        chunk_id=chunk_id,
        document_id=transcript.document_id,
        source_sha256=transcript.source_sha256,
        canonical_sha256=_canonical_digest(transcript),
        canonical_path=transcript.canonical_path,
        source_path=transcript.source_path,
        segment_ids=tuple(segment.segment_id for segment in segments),
        first_segment_id=segments[0].segment_id,
        last_segment_id=segments[-1].segment_id,
        start_seconds=segments[0].start_seconds,
        end_seconds=segments[-1].end_seconds,
        text=text,
        content_sha256=content_sha256,
        chunking_profile_id=profile.profile_id,
        languages=tuple(
            sorted(
                {
                    segment.language
                    for segment in segments
                    if segment.language is not None
                }
            )
        ),
        speaker_refs=tuple(
            sorted(
                {
                    segment.speaker_ref
                    for segment in segments
                    if segment.speaker_ref is not None
                }
            )
        ),
    )


def e5_profile(
    *,
    snapshot_path: Path,
    resolved_revision: str,
    chunking_profile_id: str = "search-chunk-v1",
) -> EmbeddingProfile:
    resolved = snapshot_path.expanduser().resolve(strict=False)
    identity_material = "\0".join(
        (
            "sentence-transformers",
            _DEFAULT_MODEL_ID,
            resolved_revision,
            str(_DEFAULT_DIMENSIONS),
            "l2",
            "mean",
            "dot",
            _DEFAULT_QUERY_PREFIX,
            _DEFAULT_PASSAGE_PREFIX,
            chunking_profile_id,
            "1",
        )
    )
    profile_id = (
        "embedding-" + hashlib.sha256(identity_material.encode("utf-8")).hexdigest()
    )
    return EmbeddingProfile(
        profile_id=profile_id,
        provider="sentence-transformers",
        model_id=_DEFAULT_MODEL_ID,
        resolved_revision=resolved_revision,
        dimensions=_DEFAULT_DIMENSIONS,
        normalization="l2",
        pooling="mean",
        distance_metric="dot",
        query_prefix=_DEFAULT_QUERY_PREFIX,
        passage_prefix=_DEFAULT_PASSAGE_PREFIX,
        chunking_profile_id=chunking_profile_id,
        snapshot_path=str(resolved),
    )


class SentenceTransformersE5Provider:
    """Strict-local multilingual E5 adapter with query/passage-specific encoding."""

    def __init__(
        self,
        *,
        snapshot_path: Path,
        resolved_revision: str,
        chunking_profile_id: str = "search-chunk-v1",
        module_loader: Callable[[str], Any] = import_module,
    ) -> None:
        resolved = snapshot_path.expanduser().resolve(strict=False)
        if not resolved.is_dir():
            raise ValueError("semantic model snapshot path is unavailable")
        if not resolved_revision.strip():
            raise ValueError("semantic model revision cannot be empty")
        if resolved.name != resolved_revision:
            raise ValueError(
                "semantic model path must end in the immutable resolved revision"
            )
        self._profile = e5_profile(
            snapshot_path=resolved,
            resolved_revision=resolved_revision,
            chunking_profile_id=chunking_profile_id,
        )
        self._module_loader = module_loader
        self._model: Any | None = None

    @classmethod
    def from_profile(
        cls,
        profile: EmbeddingProfile,
        *,
        module_loader: Callable[[str], Any] = import_module,
    ) -> SentenceTransformersE5Provider:
        expected = e5_profile(
            snapshot_path=Path(profile.snapshot_path),
            resolved_revision=profile.resolved_revision,
            chunking_profile_id=profile.chunking_profile_id,
        )
        if profile.identity_tuple() != expected.identity_tuple():
            raise ValueError("stored embedding profile is not a supported E5 profile")
        return cls(
            snapshot_path=Path(profile.snapshot_path),
            resolved_revision=profile.resolved_revision,
            chunking_profile_id=profile.chunking_profile_id,
            module_loader=module_loader,
        )

    @property
    def profile(self) -> EmbeddingProfile:
        return self._profile

    def embed_queries(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
        return self._embed(texts, self.profile.query_prefix)

    def embed_passages(self, texts: tuple[str, ...]) -> tuple[EmbeddingVector, ...]:
        return self._embed(texts, self.profile.passage_prefix)

    def _embed(
        self, texts: tuple[str, ...], prefix: str
    ) -> tuple[EmbeddingVector, ...]:
        if not texts:
            return ()
        if any(not text.strip() for text in texts):
            raise ValueError("embedding input cannot contain empty text")
        model = self._load_model()
        encoded = model.encode(
            [prefix + text.strip() for text in texts],
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        rows = encoded.tolist() if hasattr(encoded, "tolist") else encoded
        vectors = tuple(self._vector(row) for row in rows)
        if len(vectors) != len(texts):
            raise RuntimeError("embedding runtime returned the wrong number of vectors")
        return vectors

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        module = self._module_loader("sentence_transformers")
        self._model = module.SentenceTransformer(
            self.profile.snapshot_path,
            local_files_only=True,
            trust_remote_code=False,
        )
        return self._model

    def _vector(self, row: Any) -> EmbeddingVector:
        values = tuple(float(value) for value in row)
        if len(values) != self.profile.dimensions:
            raise RuntimeError(
                "embedding runtime returned an unexpected vector dimension"
            )
        if any(not math.isfinite(value) for value in values):
            raise RuntimeError("embedding runtime returned a non-finite vector")
        norm = math.sqrt(sum(value * value for value in values))
        if not math.isclose(norm, 1.0, rel_tol=1e-4, abs_tol=1e-4):
            raise RuntimeError("embedding runtime did not return l2-normalized vectors")
        return values
