import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from hypothesis import given
from hypothesis import strategies as st

from echoflow.core.errors import (
    StorageAlreadyExistsError,
    StorageError,
    StorageNotFoundError,
    StoragePermissionError,
)
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


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode contract")
def test_private_directories_are_created_and_tightened_to_owner_only(manager, tmp_path):
    private = tmp_path / "private"
    private.mkdir(mode=0o755)
    manager.ensure_directory_exists(private, private=True)
    assert private.stat().st_mode & 0o777 == 0o700

    reserved = private / "job"
    manager.reserve_directory(reserved, private=True)
    assert reserved.stat().st_mode & 0o777 == 0o700


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode contract")
def test_private_file_writes_are_owner_only(manager, tmp_path):
    destination = tmp_path / "checkpoint.json"

    manager.save_file(b"sensitive", destination, private=True)

    assert destination.stat().st_mode & 0o777 == 0o600


def test_private_operations_delegate_to_platform_policy(tmp_path):
    policy = Mock()
    manager = LocalFileManager(private_storage=policy)
    directory = tmp_path / "private"
    destination = directory / "checkpoint.json"

    manager.ensure_directory_exists(directory, private=True)
    manager.save_file(b"sensitive", destination, private=True)

    policy.protect_directory.assert_called_once_with(directory)
    assert policy.protect_file.call_count == 2
    assert policy.protect_file.call_args_list[-1].args == (destination.absolute(),)


def test_private_policy_failure_is_typed_permission_error(tmp_path):
    policy = Mock()
    policy.protect_directory.side_effect = PermissionError("ACL failure")
    manager = LocalFileManager(private_storage=policy)

    with pytest.raises(StoragePermissionError):
        manager.ensure_directory_exists(tmp_path / "private", private=True)


def test_directory_and_file_reservations_are_exclusive(manager, tmp_path):
    directory = tmp_path / "job"
    artifact = tmp_path / "transcript.json"
    manager.reserve_directory(directory)
    manager.reserve_file(artifact)
    assert directory.is_dir()
    assert artifact.read_bytes() == b""
    with pytest.raises(StorageAlreadyExistsError):
        manager.reserve_directory(directory)
    with pytest.raises(StorageAlreadyExistsError):
        manager.reserve_file(artifact)


@pytest.mark.parametrize(("name", "expected"), [("", "_"), (".", "_"), ("..", "__")])
def test_reserved_empty_and_traversal_names_are_not_preserved(manager, name, expected):
    assert manager.sanitize_filename(name) == expected


@pytest.mark.parametrize("name", ["CON", "con.txt", "LPT1.wav", "COM9.json"])
def test_windows_device_names_are_safe_on_every_platform(manager, name):
    assert manager.sanitize_filename(name).startswith("_")


def test_trailing_windows_dots_and_spaces_are_removed(manager):
    assert manager.sanitize_filename("recording. ") == "recording"


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
