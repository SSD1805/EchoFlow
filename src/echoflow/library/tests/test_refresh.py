import hashlib
import json
import os
from pathlib import Path

import pytest

from echoflow.library.duckdb_index import DuckDbTranscriptIndex
from echoflow.library.errors import TranscriptLibraryBuildError
from echoflow.library.index import SearchQuery
from echoflow.library.service import TranscriptLibraryService
from echoflow.workspace.lifecycle import JobLifecycleRecord, JobStatus
from echoflow.workspace.models import JobId, WorkspacePaths


class CountingStore:
    def __init__(self) -> None:
        self.reads: list[Path] = []

    def ensure_directory_exists(
        self, directory_path: str | Path, *, private: bool = False
    ) -> None:
        path = Path(directory_path)
        path.mkdir(parents=True, exist_ok=True)

    def read_file(self, file_path: str | Path) -> bytes:
        path = Path(file_path)
        self.reads.append(path.resolve(strict=False))
        return path.read_bytes()

    def list_files(
        self,
        directory_path: str | Path,
        extensions: tuple[str, ...] | None = None,
    ) -> list[Path]:
        directory = Path(directory_path)
        if not directory.is_dir():
            return []
        paths = [path for path in directory.iterdir() if path.is_file()]
        if extensions is not None:
            paths = [path for path in paths if path.suffix.lower() in extensions]
        return sorted(paths)


class LifecycleStore:
    def __init__(self, records: tuple[JobLifecycleRecord, ...]) -> None:
        self.records = records

    def list_records(self) -> tuple[JobLifecycleRecord, ...]:
        return self.records


class SemanticStub:
    backend_id = "semantic-stub"

    def __init__(self) -> None:
        self.ready = True
        self.clear_calls = 0

    def state(self) -> object | None:
        return object() if self.ready else None

    def clear(self) -> None:
        self.clear_calls += 1
        self.ready = False


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
    text: str,
) -> None:
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
                        "start_seconds": 0.0,
                        "end_seconds": 1.0,
                        "text": text,
                        "language": "en",
                    }
                ],
            },
            sort_keys=True,
        )
    )


def _record(source: Path, canonical: Path, job_id: str) -> JobLifecycleRecord:
    return JobLifecycleRecord(
        job_id=JobId(job_id),
        input_path=source,
        output_dir=canonical.parent,
        status=JobStatus.COMPLETED,
        started_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:01:00+00:00",
        process_id=None,
        process_started_at=None,
        artifact_path=canonical,
    )


def _service(
    tmp_path: Path,
    store: CountingStore,
    records: tuple[JobLifecycleRecord, ...] = (),
    *,
    semantic: SemanticStub | None = None,
) -> TranscriptLibraryService:
    paths = _paths(tmp_path)
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    index = DuckDbTranscriptIndex(
        paths.state_dir / "library" / "transcripts.duckdb",
        store,  # type: ignore[arg-type]
    )
    return TranscriptLibraryService(
        index=index,
        lifecycle_store=LifecycleStore(records),  # type: ignore[arg-type]
        paths=paths,
        file_manager=store,  # type: ignore[arg-type]
        semantic_index=semantic,  # type: ignore[arg-type]
    )


def test_noop_refresh_skips_canonical_reads_for_unchanged_tracked_files(
    tmp_path: Path,
) -> None:
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    first = _paths(tmp_path).output_dir / "first.json"
    second = _paths(tmp_path).output_dir / "second.json"
    _write_canonical(first, job_id="job-1", source=source, text="alpha evidence")
    _write_canonical(second, job_id="job-2", source=source, text="beta evidence")
    store = CountingStore()
    service = _service(
        tmp_path,
        store,
        (_record(source, first, "job-1"), _record(source, second, "job-2")),
    )
    service.rebuild()
    store.reads.clear()

    report = service.refresh()

    assert store.reads == []
    assert report.added_document_ids == ()
    assert report.updated_document_ids == ()
    assert report.removed_document_ids == ()
    assert report.unchanged_document_ids == ("job-1", "job-2")
    assert report.indexed_documents == 2
    assert report.changed is False


def test_refresh_cost_is_proportional_to_changed_canonical_files(
    tmp_path: Path,
) -> None:
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    store = CountingStore()
    service = _service(tmp_path, store)
    output = _paths(tmp_path).output_dir
    for index in range(100):
        _write_canonical(
            output / f"transcript-{index:03d}.json",
            job_id=f"job-{index:03d}",
            source=source,
            text=f"evidence {index}",
        )
    service.rebuild()
    store.reads.clear()

    unchanged = service.refresh()

    assert unchanged.indexed_documents == 100
    assert len(unchanged.unchanged_document_ids) == 100
    assert store.reads == []

    changed_path = output / "transcript-042.json"
    _write_canonical(
        changed_path,
        job_id="job-042",
        source=source,
        text="replacement evidence with changed length for forty two",
    )
    store.reads.clear()

    changed = service.refresh()

    assert changed.updated_document_ids == ("job-042",)
    assert len(changed.unchanged_document_ids) == 99
    assert store.reads == [changed_path.resolve()]


def test_refresh_reads_and_reindexes_only_changed_generation(tmp_path: Path) -> None:
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    first = _paths(tmp_path).output_dir / "first.json"
    second = _paths(tmp_path).output_dir / "second.json"
    _write_canonical(first, job_id="job-1", source=source, text="alpha evidence")
    _write_canonical(second, job_id="job-2", source=source, text="beta evidence")
    store = CountingStore()
    service = _service(tmp_path, store)
    service.rebuild()
    store.reads.clear()

    _write_canonical(
        second,
        job_id="job-2",
        source=source,
        text="gamma replacement evidence with a changed size",
    )
    report = service.refresh()

    assert store.reads == [second.resolve()]
    assert report.updated_document_ids == ("job-2",)
    assert report.unchanged_document_ids == ("job-1",)
    assert [match.document_id for match in service.search(SearchQuery("gamma"))] == [
        "job-2"
    ]
    assert service.search(SearchQuery("beta")) == ()


def test_refresh_adds_new_and_removes_missing_in_one_reconciliation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    old = _paths(tmp_path).output_dir / "old.json"
    _write_canonical(old, job_id="old", source=source, text="old evidence")
    store = CountingStore()
    service = _service(tmp_path, store)
    service.rebuild()
    old.unlink()

    new = _paths(tmp_path).output_dir / "new.json"
    _write_canonical(new, job_id="new", source=source, text="new evidence")
    report = service.refresh()

    assert report.added_document_ids == ("new",)
    assert report.removed_document_ids == ("old",)
    assert [item.document_id for item in service.documents()] == ["new"]


def test_refresh_keeps_explicit_import_tracked_without_repeating_import_path(
    tmp_path: Path,
) -> None:
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    external = tmp_path / "external" / "interview.json"
    _write_canonical(external, job_id="external", source=source, text="outside")
    store = CountingStore()
    service = _service(tmp_path, store)
    service.rebuild((external,))
    store.reads.clear()

    report = service.refresh()

    assert report.unchanged_document_ids == ("external",)
    assert store.reads == []
    assert service.documents()[0].canonical_path == str(external.resolve())


def test_refresh_updates_moved_tracked_canonical_without_losing_known_source_path(
    tmp_path: Path,
) -> None:
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    canonical = _paths(tmp_path).output_dir / "interview.json"
    _write_canonical(canonical, job_id="job-1", source=source, text="moving evidence")
    store = CountingStore()
    service = _service(
        tmp_path,
        store,
        (_record(source, canonical, "job-1"),),
    )
    service.rebuild()

    moved = tmp_path / "archive" / "interview.json"
    moved.parent.mkdir()
    canonical.rename(moved)
    report = service.refresh((moved,))

    assert report.updated_document_ids == ("job-1",)
    document = service.documents()[0]
    assert document.canonical_path == str(moved.resolve())
    assert document.source_path == str(source.resolve())


def test_refresh_rejects_duplicate_document_identity_when_original_still_exists(
    tmp_path: Path,
) -> None:
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    canonical = _paths(tmp_path).output_dir / "interview.json"
    _write_canonical(canonical, job_id="job-1", source=source, text="evidence")
    duplicate = tmp_path / "copy.json"
    duplicate.write_bytes(canonical.read_bytes())
    store = CountingStore()
    service = _service(tmp_path, store)
    service.rebuild()

    with pytest.raises(TranscriptLibraryBuildError, match="Duplicate"):
        service.refresh((duplicate,))

    assert [item.document_id for item in service.documents()] == ["job-1"]


def test_refresh_fails_closed_for_corrupt_tracked_canonical_and_keeps_old_index(
    tmp_path: Path,
) -> None:
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    canonical = _paths(tmp_path).output_dir / "interview.json"
    _write_canonical(canonical, job_id="job-1", source=source, text="old evidence")
    store = CountingStore()
    service = _service(tmp_path, store)
    service.rebuild()
    canonical.write_text("not json and definitely a different size")

    with pytest.raises(TranscriptLibraryBuildError, match="tracked canonical"):
        service.refresh()

    assert service.search(SearchQuery("old"))[0].document_id == "job-1"


def test_verify_bypasses_metadata_fast_path_and_catches_same_signature_tamper(
    tmp_path: Path,
) -> None:
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    canonical = _paths(tmp_path).output_dir / "interview.json"
    _write_canonical(canonical, job_id="job-1", source=source, text="alpha evidence")
    store = CountingStore()
    service = _service(tmp_path, store)
    service.rebuild()
    original_stat = canonical.stat()
    original_bytes = canonical.read_bytes()
    tampered = original_bytes.replace(b"alpha", b"omega")
    assert len(tampered) == len(original_bytes)
    canonical.write_bytes(tampered)
    os.utime(
        canonical,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
    )
    store.reads.clear()

    fast = service.refresh()
    assert fast.unchanged_document_ids == ("job-1",)
    assert store.reads == []
    assert service.search(SearchQuery("alpha"))

    verified = service.refresh(verify=True)
    assert verified.updated_document_ids == ("job-1",)
    assert verified.verified_all_tracked is True
    assert service.search(SearchQuery("alpha")) == ()
    assert service.search(SearchQuery("omega"))


def test_semantic_state_is_preserved_for_stat_only_touch_but_invalidated_for_content(
    tmp_path: Path,
) -> None:
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    canonical = _paths(tmp_path).output_dir / "interview.json"
    _write_canonical(canonical, job_id="job-1", source=source, text="alpha evidence")
    store = CountingStore()
    semantic = SemanticStub()
    service = _service(tmp_path, store, semantic=semantic)
    service.rebuild()

    stat = canonical.stat()
    os.utime(canonical, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    touched = service.refresh()
    assert touched.updated_document_ids == ("job-1",)
    assert touched.semantic_invalidated is False
    assert semantic.clear_calls == 0

    _write_canonical(
        canonical,
        job_id="job-1",
        source=source,
        text="replacement evidence with new content",
    )
    changed = service.refresh()
    assert changed.semantic_invalidated is True
    assert semantic.clear_calls == 1


def test_refresh_skips_untracked_invalid_json_but_tracked_invalid_json_is_strict(
    tmp_path: Path,
) -> None:
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    canonical = _paths(tmp_path).output_dir / "interview.json"
    _write_canonical(canonical, job_id="job-1", source=source, text="evidence")
    unrelated = _paths(tmp_path).output_dir / "preferences.json"
    unrelated.write_text('{"not": "a transcript"}')
    store = CountingStore()
    service = _service(tmp_path, store)

    first = service.refresh()
    assert first.added_document_ids == ("job-1",)
    assert first.skipped_files == 1

    canonical.write_text('{"broken": true}')
    with pytest.raises(TranscriptLibraryBuildError, match="tracked canonical"):
        service.refresh()
