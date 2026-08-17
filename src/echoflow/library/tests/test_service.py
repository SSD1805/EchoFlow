import hashlib
import json
from pathlib import Path

import pytest

from echoflow.library.duckdb_index import DuckDbTranscriptIndex
from echoflow.library.errors import TranscriptLibraryBuildError, TranscriptLibraryError
from echoflow.library.index import SearchQuery
from echoflow.library.service import SourceIntegrity, TranscriptLibraryService
from echoflow.workspace.lifecycle import JobLifecycleRecord, JobStatus
from echoflow.workspace.models import JobId, WorkspacePaths


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


class LifecycleStore:
    def __init__(self, records: tuple[JobLifecycleRecord, ...]) -> None:
        self.records = records

    def list_records(self) -> tuple[JobLifecycleRecord, ...]:
        return self.records


def _paths(tmp_path: Path) -> WorkspacePaths:
    return WorkspacePaths(
        state_dir=tmp_path / "state",
        cache_dir=tmp_path / "cache",
        model_dir=tmp_path / "cache" / "models",
        output_dir=tmp_path / "output",
    )


def _write_canonical(
    path: Path,
    *,
    job_id: str,
    source: Path,
    text: str = "housing evidence",
) -> str:
    source_bytes = source.read_bytes()
    digest = hashlib.sha256(source_bytes).hexdigest()
    stat = source.stat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "job_id": job_id,
                "source": {
                    "sha256": digest,
                    "size_bytes": len(source_bytes),
                    "modified_ns": stat.st_mtime_ns,
                },
                "detected_language": "en",
                "segments": [
                    {
                        "segment_id": "segment-000000",
                        "start_seconds": 1.25,
                        "end_seconds": 2.5,
                        "text": text,
                        "language": "en",
                        "speaker_ref": "speaker-01",
                    }
                ],
            }
        )
    )
    return digest


def _record(source: Path, canonical: Path, job_id: str = "job-1") -> JobLifecycleRecord:
    return JobLifecycleRecord(
        job_id=JobId(job_id),
        input_path=source,
        output_dir=canonical.parent,
        status=JobStatus.COMPLETED,
        started_at="2026-08-17T00:00:00+00:00",
        updated_at="2026-08-17T00:01:00+00:00",
        process_id=None,
        process_started_at=None,
        artifact_path=canonical,
    )


def _service(
    tmp_path: Path,
    records: tuple[JobLifecycleRecord, ...] = (),
) -> TranscriptLibraryService:
    paths = _paths(tmp_path)
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    store = LocalStore()
    index = DuckDbTranscriptIndex(
        paths.state_dir / "library" / "transcripts.duckdb",
        store,  # type: ignore[arg-type]
    )
    return TranscriptLibraryService(
        index=index,
        lifecycle_store=LifecycleStore(records),  # type: ignore[arg-type]
        paths=paths,
        file_manager=store,  # type: ignore[arg-type]
    )


def test_rebuild_discovers_known_canonical_and_skips_unrelated_output_json(
    tmp_path: Path,
) -> None:
    source = tmp_path / "audio.wav"
    source.write_bytes(b"original audio")
    canonical = _paths(tmp_path).output_dir / "interview.json"
    _write_canonical(canonical, job_id="job-1", source=source)
    (_paths(tmp_path).output_dir / "other.json").write_text('{"hello": "world"}')
    service = _service(tmp_path, (_record(source, canonical),))

    report = service.rebuild()

    assert report.backend_id == "duckdb-bm25-v1"
    assert report.indexed_documents == 1
    assert report.skipped_files == 1
    assert [item.document_id for item in service.documents()] == ["job-1"]
    match = service.search(SearchQuery("housing"))[0]
    assert match.start_seconds == 1.25
    assert match.source_path == str(source.resolve())


def test_rebuild_of_known_canonical_fails_closed_and_preserves_old_index(
    tmp_path: Path,
) -> None:
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    canonical = _paths(tmp_path).output_dir / "interview.json"
    _write_canonical(canonical, job_id="job-1", source=source)
    service = _service(tmp_path, (_record(source, canonical),))
    service.rebuild()
    canonical.write_text("not json")

    with pytest.raises(TranscriptLibraryBuildError, match="known canonical"):
        service.rebuild()

    assert [item.document_id for item in service.documents()] == ["job-1"]


def test_rebuild_rejects_duplicate_document_identity(tmp_path: Path) -> None:
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    first = tmp_path / "one" / "a.json"
    second = tmp_path / "two" / "b.json"
    _write_canonical(first, job_id="same-job", source=source)
    _write_canonical(second, job_id="same-job", source=source)
    service = _service(tmp_path)

    with pytest.raises(TranscriptLibraryBuildError, match="Duplicate"):
        service.rebuild((first, second))


def test_explicit_missing_rebuild_path_is_rejected(tmp_path: Path) -> None:
    service = _service(tmp_path)
    with pytest.raises(TranscriptLibraryBuildError, match="unavailable"):
        service.rebuild((tmp_path / "missing",))


def test_evidence_receipt_verifies_current_source_bytes(tmp_path: Path) -> None:
    source = tmp_path / "audio.wav"
    source.write_bytes(b"original audio")
    canonical = _paths(tmp_path).output_dir / "interview.json"
    original_digest = _write_canonical(canonical, job_id="job-1", source=source)
    service = _service(tmp_path, (_record(source, canonical),))
    service.rebuild()

    receipt = service.inspect("job-1")
    assert receipt.source_integrity is SourceIntegrity.MATCHES
    assert receipt.current_source_sha256 == original_digest
    assert receipt.source_handling == "read-only"
    assert receipt.index_custody == "private-rebuildable-derived-state"

    source.write_bytes(b"changed audio")
    changed = service.inspect("job-1")
    assert changed.source_integrity is SourceIntegrity.CHANGED
    assert changed.current_source_sha256 != original_digest

    source.unlink()
    missing = service.inspect("job-1")
    assert missing.source_integrity is SourceIntegrity.MISSING
    assert missing.current_source_sha256 is None


def test_explicit_canonical_without_lifecycle_has_unknown_source_path(
    tmp_path: Path,
) -> None:
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    canonical = tmp_path / "external.json"
    _write_canonical(canonical, job_id="external", source=source)
    service = _service(tmp_path)

    report = service.rebuild((canonical,))
    receipt = service.inspect("external")

    assert report.indexed_documents == 1
    assert receipt.document.source_path is None
    assert receipt.source_integrity is SourceIntegrity.UNKNOWN


def test_inspect_rejects_unknown_document(tmp_path: Path) -> None:
    service = _service(tmp_path)
    with pytest.raises(TranscriptLibraryError, match="not present"):
        service.inspect("missing")


def test_source_mutation_during_hash_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    canonical = _paths(tmp_path).output_dir / "interview.json"
    _write_canonical(canonical, job_id="job-1", source=source)
    service = _service(tmp_path, (_record(source, canonical),))
    service.rebuild()
    original = service._fingerprint

    def mutate(path: Path) -> str:
        digest = original(path)
        path.write_bytes(b"changed while hashing")
        return digest

    monkeypatch.setattr(service, "_fingerprint", mutate)
    with pytest.raises(TranscriptLibraryError, match="changed during"):
        service.inspect("job-1")
