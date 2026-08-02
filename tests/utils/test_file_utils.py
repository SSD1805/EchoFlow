# tests/utils/test_file_utils.py

# tests/utils/test_local_file_utility.py

import os
import tempfile
from unittest.mock import MagicMock

import pytest

from src.utils.file_utils import LocalFileUtility


@pytest.fixture
def file_utility():
    """Fixture to instantiate the LocalFileUtility."""
    return LocalFileUtility()


@pytest.fixture
def temp_directory():
    """Fixture to create a temporary directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


def test_safe_write(file_utility, temp_directory):
    """Test safe_write writes content atomically."""
    file_path = os.path.join(temp_directory, "test_file.txt")
    content = b"Hello, EchoFlow!"

    file_utility.safe_write(content, file_path)

    assert os.path.exists(file_path), "File should exist after safe_write"
    with open(file_path, "rb") as file:
        assert file.read() == content, "File content should match the written content"


def test_safe_write_failure(file_utility):
    """Test safe_write handles failure gracefully."""
    with pytest.raises(OSError, match="Failed to safely write file"):
        file_utility.safe_write(b"data", "/invalid_path/test_file.txt")


def test_safe_write_supports_relative_paths(file_utility, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    file_utility.safe_write(b"relative", "recording.bin")

    assert (tmp_path / "recording.bin").read_bytes() == b"relative"


def test_safe_write_cleans_temporary_file_when_replace_fails(
    file_utility, tmp_path, monkeypatch
):
    destination = tmp_path / "recording.bin"

    def fail_replace(_source, _destination):
        raise PermissionError("destination is locked")

    monkeypatch.setattr("src.utils.file_utils.os.replace", fail_replace)

    with pytest.raises(OSError, match="Failed to safely write file"):
        file_utility.safe_write(b"data", str(destination))

    assert list(tmp_path.iterdir()) == []


def test_safe_write_uses_destination_directory_and_syncs_before_replace(
    file_utility, tmp_path, monkeypatch
):
    destination = tmp_path / "nested" / "recording.bin"
    temporary = MagicMock()
    temporary.name = str(tmp_path / "nested" / "temporary.bin")
    context_manager = MagicMock()
    context_manager.__enter__.return_value = temporary
    named_temporary_file = MagicMock(return_value=context_manager)
    replace = MagicMock()
    fsync = MagicMock()
    monkeypatch.setattr(
        "src.utils.file_utils.tempfile.NamedTemporaryFile", named_temporary_file
    )
    monkeypatch.setattr("src.utils.file_utils.os.replace", replace)
    monkeypatch.setattr("src.utils.file_utils.os.fsync", fsync)

    file_utility.safe_write(b"data", str(destination))

    named_temporary_file.assert_called_once_with(
        mode="wb", delete=False, dir=str(destination.parent)
    )
    temporary.write.assert_called_once_with(b"data")
    temporary.flush.assert_called_once_with()
    fsync.assert_called_once_with(temporary.fileno.return_value)
    replace.assert_called_once_with(temporary.name, str(destination))


def test_file_exists(file_utility, temp_directory):
    """Test file_exists correctly identifies file existence."""
    file_path = os.path.join(temp_directory, "test_file.txt")
    with open(file_path, "w") as file:
        file.write("content")

    assert file_utility.file_exists(file_path), "File should exist"
    assert not file_utility.file_exists(
        os.path.join(temp_directory, "non_existent.txt")
    ), "File should not exist"


def test_get_file_metadata(file_utility, temp_directory):
    """Test get_file_metadata fetches correct metadata."""
    file_path = os.path.join(temp_directory, "test_file.txt")
    content = b"File Metadata Testing"
    file_utility.safe_write(content, file_path)

    metadata = file_utility.get_file_metadata(file_path)
    assert set(metadata) == {"size", "last_modified", "last_accessed"}
    assert metadata["size"] == len(content), (
        "Metadata size should match file content size"
    )


def test_get_file_metadata_wraps_filesystem_errors(file_utility, tmp_path):
    with pytest.raises(OSError, match="Failed to fetch metadata"):
        file_utility.get_file_metadata(str(tmp_path / "missing.bin"))


def test_delete_file_safe(file_utility, temp_directory):
    """Test delete_file_safe removes files and handles missing files gracefully."""
    file_path = os.path.join(temp_directory, "test_file.txt")
    with open(file_path, "w") as file:
        file.write("content")

    file_utility.delete_file_safe(file_path)
    assert not os.path.exists(file_path), "File should not exist after deletion"

    # Ensure no error for missing file
    file_utility.delete_file_safe(file_path)


def test_delete_file_safe_wraps_unexpected_errors(file_utility, monkeypatch):
    def fail_remove(_path):
        raise PermissionError("denied")

    monkeypatch.setattr("src.utils.file_utils.os.remove", fail_remove)

    with pytest.raises(OSError, match="Failed to delete file"):
        file_utility.delete_file_safe("protected.bin")


def test_copy_file_safe(file_utility, temp_directory):
    """Test copy_file_safe copies files correctly."""
    source_path = os.path.join(temp_directory, "source.txt")
    destination_path = os.path.join(temp_directory, "destination.txt")

    content = b"Copy this content!"
    file_utility.safe_write(content, source_path)

    file_utility.copy_file_safe(source_path, destination_path)

    assert os.path.exists(destination_path), "Destination file should exist"
    with open(destination_path, "rb") as file:
        assert file.read() == content, "Copied content should match source content"


def test_copy_file_safe_wraps_filesystem_errors(file_utility, tmp_path):
    with pytest.raises(OSError, match="Failed to copy file"):
        file_utility.copy_file_safe(
            str(tmp_path / "missing.bin"), str(tmp_path / "copy.bin")
        )


def test_list_files_in_directory(file_utility, temp_directory):
    """Test list_files_in_directory lists files and applies filters."""
    extensions = (".txt", ".log")
    file1 = os.path.join(temp_directory, "file1.txt")
    file2 = os.path.join(temp_directory, "file2.log")
    file3 = os.path.join(temp_directory, "file3.jpg")
    with open(file1, "w"), open(file2, "w"), open(file3, "w"):
        pass

    files = file_utility.list_files_in_directory(temp_directory, extensions)
    assert len(files) == 2, "Only files with specified extensions should be listed"
    assert file1 in files and file2 in files, (
        "Files with matching extensions should be included"
    )
    assert file3 not in files, "Files with non-matching extensions should be excluded"


def test_list_files_in_directory_without_filter(file_utility, temp_directory):
    expected = {
        os.path.join(temp_directory, "one.txt"),
        os.path.join(temp_directory, "two.wav"),
    }
    for path in expected:
        with open(path, "wb"):
            pass

    assert set(file_utility.list_files_in_directory(temp_directory)) == expected


def test_list_files_in_directory_wraps_filesystem_errors(file_utility, tmp_path):
    with pytest.raises(OSError, match="Failed to list files"):
        file_utility.list_files_in_directory(str(tmp_path / "missing"))


def test_sanitize_filename_safe(file_utility):
    """Test sanitize_filename_safe generates safe filenames."""
    unsafe_name = "unsafe/file*name?.txt"
    sanitized = file_utility.sanitize_filename_safe(unsafe_name)
    assert sanitized == "unsafe_file_name_.txt", (
        "Sanitized filename should be safe for file systems"
    )


def test_sanitize_filename_safe_no_change(file_utility):
    """Test sanitize_filename_safe keeps safe filenames unchanged."""
    safe_name = "safe_filename.txt"
    sanitized = file_utility.sanitize_filename_safe(safe_name)
    assert sanitized == safe_name, "Safe filename should remain unchanged"


def test_ensure_directory_exists_is_idempotent(file_utility, tmp_path):
    directory = tmp_path / "existing"

    file_utility.ensure_directory_exists(str(directory))
    file_utility.ensure_directory_exists(str(directory))

    assert directory.is_dir()


def test_ensure_directory_exists_wraps_filesystem_errors(file_utility, monkeypatch):
    def fail_makedirs(*_args, **_kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr("src.utils.file_utils.os.makedirs", fail_makedirs)

    with pytest.raises(OSError, match="Failed to ensure directory"):
        file_utility.ensure_directory_exists("protected")
