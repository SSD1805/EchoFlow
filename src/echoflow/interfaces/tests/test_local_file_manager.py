from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given
from hypothesis import strategies as st

from echoflow.core.errors import StorageError, StorageNotFoundError
from echoflow.interfaces.base_file_manager import FileManager
from echoflow.interfaces.local_file_manager import LocalFileManager


@pytest.fixture
def manager():
    return LocalFileManager()


def test_manager_satisfies_local_capability(manager):
    assert isinstance(manager, FileManager)


def test_round_trip_overwrite_metadata_copy_list_and_delete(manager, tmp_path):
    source = tmp_path / "b.bin"
    copied = tmp_path / "a.bin"
    ignored = tmp_path / "c.txt"
    manager.save_file(b"first", source)
    manager.save_file(b"second", source)
    manager.copy_file(source, copied)
    ignored.write_text("text")

    assert source.read_bytes() == b"second"
    assert copied.read_bytes() == b"second"
    assert manager.get_file_metadata(source)["size"] == 6
    assert manager.list_files(tmp_path, (".bin",)) == [copied, source]
    assert manager.list_files(tmp_path, ()) == [copied, source, ignored]

    manager.delete_file(source)
    manager.delete_file(source)
    assert not manager.file_exists(source)


def test_ensure_directory_is_recursive_and_idempotent(manager, tmp_path):
    nested = tmp_path / "one" / "two"
    manager.ensure_directory_exists(nested)
    manager.ensure_directory_exists(nested)
    assert nested.is_dir()


@pytest.mark.parametrize(("name", "expected"), [("", "_"), (".", "_"), ("..", "__")])
def test_reserved_empty_and_traversal_names_are_not_preserved(manager, name, expected):
    assert manager.sanitize_filename(name) == expected


@given(st.binary(max_size=4096))
def test_arbitrary_bytes_round_trip(content):
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        destination = Path(directory) / "payload.bin"
        LocalFileManager().save_file(content, destination)
        assert destination.read_bytes() == content


@given(st.text(max_size=100))
def test_sanitizer_is_idempotent_and_nonempty(filename):
    manager = LocalFileManager()
    sanitized = manager.sanitize_filename(filename)
    assert sanitized
    assert manager.sanitize_filename(sanitized) == sanitized
    assert "/" not in sanitized
    assert "\\" not in sanitized


def test_missing_source_and_metadata_are_typed_not_found_errors(manager, tmp_path):
    with pytest.raises(StorageNotFoundError) as copy_error:
        manager.copy_file(tmp_path / "missing", tmp_path / "copy")
    with pytest.raises(StorageNotFoundError):
        manager.get_file_metadata(tmp_path / "missing")
    assert isinstance(copy_error.value.__cause__, FileNotFoundError)


def test_write_requires_existing_parent(manager, tmp_path):
    with pytest.raises(StorageNotFoundError):
        manager.save_file(b"data", tmp_path / "missing" / "file.bin")


def test_copy_reports_missing_destination_parent_not_existing_source(manager, tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"data")
    destination = tmp_path / "missing" / "copy.bin"
    with pytest.raises(StorageNotFoundError) as error:
        manager.copy_file(source, destination)
    assert error.value.path == destination


def test_atomic_replace_failure_cleans_temp_and_preserves_destination(
    manager, tmp_path
):
    destination = tmp_path / "existing.bin"
    destination.write_bytes(b"original")
    before = set(tmp_path.iterdir())
    with (
        patch(
            "echoflow.interfaces.local_file_manager.os.replace",
            side_effect=OSError("replace"),
        ),
        pytest.raises(StorageError),
    ):
        manager.save_file(b"replacement", destination)
    assert destination.read_bytes() == b"original"
    assert set(tmp_path.iterdir()) == before


def test_relative_destination_is_resolved_when_operation_runs(
    manager, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    manager.save_file(b"relative", "recording.bin")
    assert (tmp_path / "recording.bin").read_bytes() == b"relative"


def test_list_excludes_nested_files(manager, tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "hidden.txt").write_text("hidden")
    assert manager.list_files(tmp_path) == []
