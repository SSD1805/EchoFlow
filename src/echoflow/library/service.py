import hashlib
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.library.errors import (
    SemanticSearchUnavailableError,
    TranscriptLibraryBuildError,
    TranscriptLibraryError,
    TranscriptProjectionError,
)
from echoflow.library.index import (
    IndexedDocument,
    IndexedTranscript,
    SearchQuery,
    TranscriptIndex,
    TranscriptMatch,
)
from echoflow.library.projection import load_indexed_transcript
from echoflow.library.retrieval import RetrievalMode, SearchResponse, TranscriptSearch
from echoflow.library.semantic import (
    ChunkingProfile,
    EmbeddingProfile,
    EmbeddingProvider,
    SemanticIndex,
    SemanticState,
    build_search_chunks,
    corpus_fingerprint,
)
from echoflow.workspace.lifecycle import JobLifecycleStore, JobStatus
from echoflow.workspace.models import WorkspacePaths

_HASH_BLOCK_SIZE = 1024 * 1024
type EmbeddingProviderFactory = Callable[[EmbeddingProfile], EmbeddingProvider]


class SourceIntegrity(StrEnum):
    MATCHES = "matches-recorded-source"
    CHANGED = "changed-since-transcription"
    MISSING = "source-file-missing"
    UNKNOWN = "source-path-unavailable"


@dataclass(frozen=True, slots=True)
class LibraryRebuildReport:
    backend_id: str
    indexed_documents: int
    skipped_files: int


@dataclass(frozen=True, slots=True)
class LibraryRefreshReport:
    backend_id: str
    indexed_documents: int
    added_document_ids: tuple[str, ...]
    updated_document_ids: tuple[str, ...]
    removed_document_ids: tuple[str, ...]
    unchanged_document_ids: tuple[str, ...]
    skipped_files: int
    semantic_invalidated: bool
    verified_all_tracked: bool

    @property
    def changed(self) -> bool:
        return bool(
            self.added_document_ids
            or self.updated_document_ids
            or self.removed_document_ids
        )


@dataclass(frozen=True, slots=True)
class SemanticRebuildReport:
    lexical_backend_id: str
    semantic_backend_id: str
    embedding_profile_id: str
    model_id: str
    resolved_revision: str
    corpus_fingerprint: str
    indexed_documents: int
    indexed_chunks: int
    skipped_files: int


@dataclass(frozen=True, slots=True)
class LibraryEvidenceReceipt:
    document: IndexedDocument
    source_integrity: SourceIntegrity
    current_source_sha256: str | None
    source_handling: str = "read-only"
    index_custody: str = "private-rebuildable-derived-state"


@dataclass(frozen=True, slots=True)
class _Candidate:
    canonical_path: Path
    source_path: Path | None
    strict: bool


@dataclass(frozen=True, slots=True)
class _RefreshCandidateResult:
    transcript: IndexedTranscript | None = None
    unchanged_document_id: str | None = None
    skipped: bool = False


@dataclass(frozen=True, slots=True)
class _RefreshDelta:
    upserts: tuple[IndexedTranscript, ...]
    added: tuple[str, ...]
    updated: tuple[str, ...]
    removed: tuple[str, ...]
    unchanged: tuple[str, ...]
    semantic_dirty: bool


class TranscriptLibraryService:
    """Coordinate canonical transcript discovery, indexing, search, and evidence."""

    def __init__(
        self,
        index: TranscriptIndex,
        lifecycle_store: JobLifecycleStore,
        paths: WorkspacePaths,
        file_manager: FileManagerFacade,
        semantic_index: SemanticIndex | None = None,
        embedding_provider_factory: EmbeddingProviderFactory | None = None,
    ) -> None:
        self.index = index
        self.lifecycle_store = lifecycle_store
        self.paths = paths
        self.file_manager = file_manager
        self.semantic_index = semantic_index
        self.embedding_provider_factory = embedding_provider_factory

    def rebuild(self, additional_paths: tuple[Path, ...] = ()) -> LibraryRebuildReport:
        ordered, skipped = self._load_transcripts(additional_paths)
        self.index.rebuild(ordered)
        return LibraryRebuildReport(
            backend_id=self.index.backend_id,
            indexed_documents=len(ordered),
            skipped_files=skipped,
        )

    def refresh(
        self,
        additional_paths: tuple[Path, ...] = (),
        *,
        verify: bool = False,
    ) -> LibraryRefreshReport:
        """Reconcile changed canonical generations without rebuilding unchanged documents."""
        existing = {
            document.document_id: document for document in self.index.documents()
        }
        existing_by_path = {
            self._resolved_path(document.canonical_path): document
            for document in existing.values()
        }
        candidates = self._refresh_candidates(existing, additional_paths)
        loaded, unchanged, skipped = self._load_refresh_candidates(
            candidates,
            existing,
            existing_by_path,
            verify=verify,
        )
        delta = self._plan_refresh_delta(existing, loaded, unchanged)
        semantic_invalidated = self._apply_refresh_delta(delta)
        return LibraryRefreshReport(
            backend_id=self.index.backend_id,
            indexed_documents=len(self.index.documents()),
            added_document_ids=delta.added,
            updated_document_ids=delta.updated,
            removed_document_ids=delta.removed,
            unchanged_document_ids=delta.unchanged,
            skipped_files=skipped,
            semantic_invalidated=semantic_invalidated,
            verified_all_tracked=verify,
        )

    def rebuild_semantic(
        self,
        provider: EmbeddingProvider,
        additional_paths: tuple[Path, ...] = (),
    ) -> SemanticRebuildReport:
        semantic_index = self._require_semantic_index()
        chunking = ChunkingProfile()
        if provider.profile.chunking_profile_id != chunking.profile_id:
            raise TranscriptLibraryBuildError(
                "Embedding profile does not match EchoFlow's current chunking policy"
            )
        transcripts, skipped = self._load_transcripts(additional_paths)
        chunks = build_search_chunks(transcripts, profile=chunking)
        try:
            vectors = provider.embed_passages(tuple(chunk.text for chunk in chunks))
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            raise SemanticSearchUnavailableError(
                "The local semantic embedding runtime could not build the index",
                cause=exc,
            ) from exc
        state = SemanticState(
            profile=provider.profile,
            corpus_fingerprint=corpus_fingerprint(transcripts),
            chunk_count=len(chunks),
        )
        try:
            self.index.rebuild(transcripts)
            semantic_index.rebuild(state=state, chunks=chunks, vectors=vectors)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            raise TranscriptLibraryBuildError(
                "The semantic transcript index could not be replaced safely",
                cause=exc,
            ) from exc
        return SemanticRebuildReport(
            lexical_backend_id=self.index.backend_id,
            semantic_backend_id=semantic_index.backend_id,
            embedding_profile_id=state.profile.profile_id,
            model_id=state.profile.model_id,
            resolved_revision=state.profile.resolved_revision,
            corpus_fingerprint=state.corpus_fingerprint,
            indexed_documents=len(transcripts),
            indexed_chunks=len(chunks),
            skipped_files=skipped,
        )

    def semantic_state(self) -> SemanticState | None:
        if self.semantic_index is None:
            return None
        return self.semantic_index.state()

    def documents(self) -> tuple[IndexedDocument, ...]:
        return self.index.documents()

    def search(self, query: SearchQuery) -> tuple[TranscriptMatch, ...]:
        """Compatibility path for direct lexical segment search."""
        return self.index.search(query)

    def retrieve(
        self,
        query: SearchQuery,
        *,
        mode: RetrievalMode = RetrievalMode.LEXICAL,
    ) -> SearchResponse:
        if mode is RetrievalMode.LEXICAL:
            return TranscriptSearch(lexical=self.index).search(query, mode=mode)

        semantic_index = self._require_semantic_index()
        state = semantic_index.state()
        if state is None:
            raise SemanticSearchUnavailableError(
                "Semantic index is empty; build local embeddings first"
            )
        current_fingerprint = self._current_index_fingerprint()
        if state.corpus_fingerprint != current_fingerprint:
            raise SemanticSearchUnavailableError(
                "Semantic index is stale; rebuild embeddings for the current transcripts"
            )
        if self.embedding_provider_factory is None:
            raise SemanticSearchUnavailableError(
                "Semantic embedding runtime is not configured"
            )
        try:
            provider = self.embedding_provider_factory(state.profile)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            raise SemanticSearchUnavailableError(
                "The indexed semantic model is unavailable locally",
                cause=exc,
            ) from exc
        try:
            return TranscriptSearch(
                lexical=self.index,
                semantic=semantic_index,
                embedding_provider=provider,
            ).search(query, mode=mode)
        except (KeyboardInterrupt, SystemExit, SemanticSearchUnavailableError):
            raise
        except Exception as exc:
            raise SemanticSearchUnavailableError(
                "Local semantic retrieval failed", cause=exc
            ) from exc

    def inspect(self, document_id: str) -> LibraryEvidenceReceipt:
        document = next(
            (
                item
                for item in self.index.documents()
                if item.document_id == document_id
            ),
            None,
        )
        if document is None:
            raise TranscriptLibraryError(
                "Transcript is not present in the local library"
            )
        integrity, digest = self._source_integrity(document)
        return LibraryEvidenceReceipt(
            document=document,
            source_integrity=integrity,
            current_source_sha256=digest,
        )

    def _load_transcripts(
        self, additional_paths: tuple[Path, ...]
    ) -> tuple[tuple[IndexedTranscript, ...], int]:
        candidates = self._discover(additional_paths)
        transcripts: dict[str, IndexedTranscript] = {}
        skipped = 0
        for candidate in candidates:
            try:
                transcript = load_indexed_transcript(
                    candidate.canonical_path,
                    source_path=candidate.source_path,
                    file_manager=self.file_manager,
                )
            except TranscriptProjectionError as exc:
                if candidate.strict:
                    raise TranscriptLibraryBuildError(
                        "A known canonical transcript could not be indexed",
                        cause=exc,
                    ) from exc
                skipped += 1
                continue
            existing = transcripts.get(transcript.document_id)
            if (
                existing is not None
                and existing.canonical_path != transcript.canonical_path
            ):
                raise TranscriptLibraryBuildError(
                    "Duplicate canonical transcript job ID found while rebuilding library"
                )
            transcripts[transcript.document_id] = transcript
        ordered = tuple(transcripts[key] for key in sorted(transcripts))
        return ordered, skipped

    def _load_refresh_candidates(
        self,
        candidates: tuple[_Candidate, ...],
        existing: dict[str, IndexedDocument],
        existing_by_path: dict[Path, IndexedDocument],
        *,
        verify: bool,
    ) -> tuple[dict[str, IndexedTranscript], set[str], int]:
        loaded: dict[str, IndexedTranscript] = {}
        unchanged: set[str] = set()
        skipped = 0
        for candidate in candidates:
            result = self._load_refresh_candidate(
                candidate,
                existing_by_path.get(candidate.canonical_path),
                existing,
                verify=verify,
            )
            if result.skipped:
                skipped += 1
                continue
            if result.unchanged_document_id is not None:
                unchanged.add(result.unchanged_document_id)
                continue
            transcript = result.transcript
            if transcript is None:
                raise RuntimeError("refresh candidate produced no disposition")
            self._reject_duplicate_refresh_identity(
                transcript,
                candidate.canonical_path,
                existing,
                loaded,
            )
            loaded[transcript.document_id] = transcript
        return loaded, unchanged, skipped

    def _load_refresh_candidate(
        self,
        candidate: _Candidate,
        existing_at_path: IndexedDocument | None,
        existing: dict[str, IndexedDocument],
        *,
        verify: bool,
    ) -> _RefreshCandidateResult:
        source_path = self._effective_source_path(candidate, existing_at_path)
        if self._can_fast_skip(
            candidate,
            existing_at_path,
            source_path,
            verify=verify,
        ):
            if existing_at_path is None:
                raise RuntimeError("fast refresh skip requires an indexed document")
            return _RefreshCandidateResult(
                unchanged_document_id=existing_at_path.document_id
            )
        try:
            transcript = load_indexed_transcript(
                candidate.canonical_path,
                source_path=source_path,
                file_manager=self.file_manager,
            )
        except TranscriptProjectionError as exc:
            if candidate.strict or existing_at_path is not None:
                raise TranscriptLibraryBuildError(
                    "A tracked canonical transcript could not be refreshed safely",
                    cause=exc,
                ) from exc
            return _RefreshCandidateResult(skipped=True)
        previous = existing.get(transcript.document_id)
        if (
            transcript.source_path is None
            and previous is not None
            and previous.source_path is not None
        ):
            transcript = replace(transcript, source_path=previous.source_path)
        return _RefreshCandidateResult(transcript=transcript)

    def _can_fast_skip(
        self,
        candidate: _Candidate,
        existing_at_path: IndexedDocument | None,
        source_path: Path | None,
        *,
        verify: bool,
    ) -> bool:
        if verify or existing_at_path is None:
            return False
        return self._signature_matches(
            existing_at_path, candidate.canonical_path
        ) and self._same_source_path(existing_at_path.source_path, source_path)

    def _plan_refresh_delta(
        self,
        existing: dict[str, IndexedDocument],
        loaded: dict[str, IndexedTranscript],
        unchanged: set[str],
    ) -> _RefreshDelta:
        upserts: list[IndexedTranscript] = []
        added: list[str] = []
        updated: list[str] = []
        semantic_dirty = False
        for document_id in sorted(loaded):
            transcript = loaded[document_id]
            previous = existing.get(document_id)
            if previous is None:
                added.append(document_id)
                upserts.append(transcript)
                semantic_dirty = True
            elif self._same_indexed_projection(previous, transcript):
                unchanged.add(document_id)
            else:
                updated.append(document_id)
                upserts.append(transcript)
                semantic_dirty = (
                    semantic_dirty
                    or self._semantic_projection_changed(previous, transcript)
                )
        removed = self._removed_documents(existing, loaded, unchanged)
        return _RefreshDelta(
            upserts=tuple(upserts),
            added=tuple(added),
            updated=tuple(updated),
            removed=removed,
            unchanged=tuple(sorted(unchanged)),
            semantic_dirty=semantic_dirty or bool(removed),
        )

    def _removed_documents(
        self,
        existing: dict[str, IndexedDocument],
        loaded: dict[str, IndexedTranscript],
        unchanged: set[str],
    ) -> tuple[str, ...]:
        removed: list[str] = []
        for document_id, document in sorted(existing.items()):
            if document_id in loaded or document_id in unchanged:
                continue
            canonical = self._resolved_path(document.canonical_path)
            if canonical.is_file():
                raise TranscriptLibraryBuildError(
                    "A tracked canonical transcript changed availability during refresh; "
                    "retry the refresh"
                )
            removed.append(document_id)
        return tuple(removed)

    def _apply_refresh_delta(self, delta: _RefreshDelta) -> bool:
        semantic_invalidated = self._invalidate_semantic_if_needed(
            delta.semantic_dirty
        )
        try:
            self.index.apply_delta(
                upserts=delta.upserts,
                removals=delta.removed,
            )
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            detail = (
                " Semantic embeddings were already invalidated."
                if semantic_invalidated
                else ""
            )
            raise TranscriptLibraryBuildError(
                "The incremental transcript index refresh could not be applied atomically."
                + detail,
                cause=exc,
            ) from exc
        return semantic_invalidated

    def _refresh_candidates(
        self,
        existing: dict[str, IndexedDocument],
        additional_paths: tuple[Path, ...],
    ) -> tuple[_Candidate, ...]:
        candidates = {
            candidate.canonical_path: candidate
            for candidate in self._discover(additional_paths)
        }
        for document in existing.values():
            canonical = self._resolved_path(document.canonical_path)
            if not canonical.is_file():
                continue
            source = (
                None
                if document.source_path is None
                else self._resolved_path(document.source_path)
            )
            discovered = candidates.get(canonical)
            if discovered is None:
                candidates[canonical] = _Candidate(canonical, source, True)
                continue
            candidates[canonical] = _Candidate(
                canonical,
                discovered.source_path or source,
                True,
            )
        return tuple(candidates[path] for path in sorted(candidates))

    @staticmethod
    def _effective_source_path(
        candidate: _Candidate,
        existing: IndexedDocument | None,
    ) -> Path | None:
        if candidate.source_path is not None:
            return candidate.source_path
        if existing is None or existing.source_path is None:
            return None
        return Path(existing.source_path).expanduser().resolve(strict=False)

    @staticmethod
    def _signature_matches(document: IndexedDocument, canonical_path: Path) -> bool:
        if (
            document.canonical_size_bytes is None
            or document.canonical_modified_ns is None
        ):
            return False
        try:
            stat = canonical_path.stat()
        except OSError as exc:
            raise TranscriptLibraryBuildError(
                "A tracked canonical transcript could not be inspected for refresh",
                cause=exc,
            ) from exc
        return (
            stat.st_size == document.canonical_size_bytes
            and stat.st_mtime_ns == document.canonical_modified_ns
        )

    @staticmethod
    def _same_source_path(stored: str | None, candidate: Path | None) -> bool:
        stored_path = (
            None
            if stored is None
            else Path(stored).expanduser().resolve(strict=False)
        )
        return stored_path == candidate

    @staticmethod
    def _same_indexed_projection(
        previous: IndexedDocument,
        current: IndexedTranscript,
    ) -> bool:
        return (
            previous.canonical_sha256 == current.canonical_sha256
            and TranscriptLibraryService._resolved_path(previous.canonical_path)
            == TranscriptLibraryService._resolved_path(current.canonical_path)
            and TranscriptLibraryService._same_source_path(
                previous.source_path,
                None if current.source_path is None else Path(current.source_path),
            )
            and previous.canonical_size_bytes == current.canonical_size_bytes
            and previous.canonical_modified_ns == current.canonical_modified_ns
        )

    @staticmethod
    def _semantic_projection_changed(
        previous: IndexedDocument,
        current: IndexedTranscript,
    ) -> bool:
        return (
            previous.canonical_sha256 != current.canonical_sha256
            or TranscriptLibraryService._resolved_path(previous.canonical_path)
            != TranscriptLibraryService._resolved_path(current.canonical_path)
            or not TranscriptLibraryService._same_source_path(
                previous.source_path,
                None if current.source_path is None else Path(current.source_path),
            )
        )

    def _reject_duplicate_refresh_identity(
        self,
        transcript: IndexedTranscript,
        candidate_path: Path,
        existing: dict[str, IndexedDocument],
        loaded: dict[str, IndexedTranscript],
    ) -> None:
        loaded_match = loaded.get(transcript.document_id)
        if (
            loaded_match is not None
            and self._resolved_path(loaded_match.canonical_path) != candidate_path
        ):
            raise TranscriptLibraryBuildError(
                "Duplicate canonical transcript job ID found while refreshing library"
            )
        previous = existing.get(transcript.document_id)
        if previous is None:
            return
        previous_path = self._resolved_path(previous.canonical_path)
        if previous_path != candidate_path and previous_path.is_file():
            raise TranscriptLibraryBuildError(
                "Duplicate canonical transcript job ID found while refreshing library"
            )

    def _invalidate_semantic_if_needed(self, semantic_dirty: bool) -> bool:
        if not semantic_dirty or self.semantic_index is None:
            return False
        try:
            state = self.semantic_index.state()
            if state is None:
                return False
            self.semantic_index.clear()
            return True
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            raise TranscriptLibraryBuildError(
                "Stale semantic state could not be invalidated before library refresh",
                cause=exc,
            ) from exc

    def _current_index_fingerprint(self) -> str:
        documents = self.index.documents()
        digest = hashlib.sha256()
        for document in sorted(documents, key=lambda item: item.document_id):
            if document.canonical_sha256 is None:
                raise SemanticSearchUnavailableError(
                    "Transcript index predates canonical hashing; rebuild the library"
                )
            digest.update(document.document_id.encode("utf-8"))
            digest.update(b"\0")
            digest.update(document.canonical_sha256.encode("ascii"))
            digest.update(b"\0")
        return digest.hexdigest()

    def _require_semantic_index(self) -> SemanticIndex:
        if self.semantic_index is None:
            raise SemanticSearchUnavailableError(
                "Semantic indexing is not configured in this EchoFlow installation"
            )
        return self.semantic_index

    def _discover(self, additional_paths: tuple[Path, ...]) -> tuple[_Candidate, ...]:
        candidates: dict[Path, _Candidate] = {}
        for record in self.lifecycle_store.list_records():
            if record.status is not JobStatus.COMPLETED or record.artifact_path is None:
                continue
            artifact = record.artifact_path.resolve(strict=False)
            if artifact.suffix.lower() != ".json" or not artifact.is_file():
                continue
            candidates[artifact] = _Candidate(artifact, record.input_path, True)
        self._add_directory(self.paths.output_dir, candidates, strict=False)
        for path in additional_paths:
            resolved = path.expanduser().resolve(strict=False)
            if resolved.is_file():
                candidates[resolved] = _Candidate(resolved, None, True)
            elif resolved.is_dir():
                self._add_directory(resolved, candidates, strict=False)
            else:
                raise TranscriptLibraryBuildError(
                    "Requested transcript library path is unavailable"
                )
        return tuple(candidates[path] for path in sorted(candidates))

    def _add_directory(
        self,
        directory: Path,
        candidates: dict[Path, _Candidate],
        *,
        strict: bool,
    ) -> None:
        if not directory.is_dir():
            return
        for path in self.file_manager.list_files(directory, (".json",)):
            resolved = path.resolve(strict=False)
            candidates.setdefault(resolved, _Candidate(resolved, None, strict))

    def _source_integrity(
        self, document: IndexedDocument
    ) -> tuple[SourceIntegrity, str | None]:
        if document.source_path is None:
            return SourceIntegrity.UNKNOWN, None
        source = Path(document.source_path)
        if not source.is_file():
            return SourceIntegrity.MISSING, None
        try:
            before = source.stat()
            digest = self._fingerprint(source)
            after = source.stat()
        except OSError as exc:
            raise TranscriptLibraryError(
                "Source integrity could not be verified", cause=exc
            ) from exc
        if (
            before.st_size,
            before.st_mtime_ns,
            before.st_dev,
            before.st_ino,
        ) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_dev,
            after.st_ino,
        ):
            raise TranscriptLibraryError("Source changed during integrity verification")
        status = (
            SourceIntegrity.MATCHES
            if digest == document.source_sha256
            else SourceIntegrity.CHANGED
        )
        return status, digest

    @staticmethod
    def _fingerprint(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while block := source.read(_HASH_BLOCK_SIZE):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _resolved_path(path: str | Path) -> Path:
        return Path(path).expanduser().resolve(strict=False)
