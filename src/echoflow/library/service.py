import hashlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.library.errors import (
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
from echoflow.workspace.lifecycle import JobLifecycleStore, JobStatus
from echoflow.workspace.models import WorkspacePaths

_HASH_BLOCK_SIZE = 1024 * 1024


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


class TranscriptLibraryService:
    """Coordinate canonical transcript discovery, indexing, search, and evidence."""

    def __init__(
        self,
        index: TranscriptIndex,
        lifecycle_store: JobLifecycleStore,
        paths: WorkspacePaths,
        file_manager: FileManagerFacade,
    ) -> None:
        self.index = index
        self.lifecycle_store = lifecycle_store
        self.paths = paths
        self.file_manager = file_manager

    def rebuild(self, additional_paths: tuple[Path, ...] = ()) -> LibraryRebuildReport:
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
        self.index.rebuild(ordered)
        return LibraryRebuildReport(
            backend_id=self.index.backend_id,
            indexed_documents=len(ordered),
            skipped_files=skipped,
        )

    def documents(self) -> tuple[IndexedDocument, ...]:
        return self.index.documents()

    def search(self, query: SearchQuery) -> tuple[TranscriptMatch, ...]:
        return self.index.search(query)

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
