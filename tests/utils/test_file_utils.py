# tests/utils/test_file_utils.py

import os
import tempfile

import pytest

from src.utils.file_utils import (
    copy_file_safe,
    delete_file_safe,
    file_exists,
    get_file_metadata,
    list_files_in_directory,
    safe_write,
    sanitize_filename_safe,
)


@pytest.fixture
def temp_directory():
    """Fixture to create a temporary directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


def test_safe_write(temp_directory):
    """Test safe_write writes content atomically."""
    file_path = os.path.join(temp_directory, "test_file.txt")
    content = b"Hello, World!"

    safe_write(content, file_path)

    assert os.path.exists(file_path), "File should exist after safe_write"
    with open(file_path, "rb") as file:
        assert file.read() == content, "File content should match the written content"


def test_safe_write_failure():
    """Test safe_write handles failure gracefully."""
    with pytest.raises(IOError):
        safe_write(b"data", "/invalid_path/test_file.txt")


def test_file_exists(temp_directory):
    """Test file_exists correctly identifies file existence."""
    file_path = os.path.join(temp_directory, "test_file.txt")
    with open(file_path, "w") as file:
        file.write("content")

    assert file_exists(file_path), "File should exist"
    assert not file_exists(os.path.join(temp_directory, "non_existent.txt")), "File should not exist"


def test_get_file_metadata(temp_directory):
    """Test get_file_metadata fetches correct metadata."""
    file_path = os.path.join(temp_directory, "test_file.txt")
    content = b"Hello, Metadata!"
    safe_write(content, file_path)

    metadata = get_file_metadata(file_path)
    assert "size" in metadata, "Metadata should include size"
    assert metadata["size"] == len(content), "Metadata size should match file content size"


def test_get_file_metadata_failure():
    """Test get_file_metadata raises error for invalid files."""
    with pytest.raises(IOError):
        get_file_metadata("/non_existent_file.txt")


def test_delete_file_safe(temp_directory):
    """Test delete_file_safe removes files and handles missing files gracefully."""
    file_path = os.path.join(temp_directory, "test_file.txt")
    with open(file_path, "w") as file:
        file.write("content")

    delete_file_safe(file_path)
    assert not os.path.exists(file_path), "File should not exist after deletion"

    # Ensure no error for missing file
    delete_file_safe(file_path)


def test_copy_file_safe(temp_directory):
    """Test copy_file_safe copies files correctly."""
    source_path = os.path.join(temp_directory, "source.txt")
    destination_path = os.path.join(temp_directory, "destination.txt")

    content = b"Copy this content"
    safe_write(content, source_path)

    copy_file_safe(source_path, destination_path)

    assert os.path.exists(destination_path), "Destination file should exist"
    with open(destination_path, "rb") as file:
        assert file.read() == content, "Copied content should match source content"


def test_copy_file_safe_failure():
    """Test copy_file_safe raises error for invalid paths."""
    with pytest.raises(IOError):
        copy_file_safe("/non_existent_file.txt", "/invalid_destination.txt")


def test_list_files_in_directory(temp_directory):
    """Test list_files_in_directory lists files and applies filters."""
    extensions = (".txt", ".log")
    file1 = os.path.join(temp_directory, "file1.txt")
    file2 = os.path.join(temp_directory, "file2.log")
    file3 = os.path.join(temp_directory, "file3.jpg")
    with open(file1, "w"), open(file2, "w"), open(file3, "w"):
        pass

    files = list_files_in_directory(temp_directory, extensions)
    assert len(files) == 2, "Only files with specified extensions should be listed"
    assert file1 in files and file2 in files, "Files with matching extensions should be included"
    assert file3 not in files, "Files with non-matching extensions should be excluded"


def test_list_files_in_directory_failure():
    """Test list_files_in_directory raises error for invalid directories."""
    with pytest.raises(IOError):
        list_files_in_directory("/non_existent_directory")


def test_sanitize_filename_safe():
    """Test sanitize_filename_safe generates safe filenames."""
    unsafe_name = "unsafe/file*name?.txt"
    sanitized = sanitize_filename_safe(unsafe_name)
    assert sanitized == "unsafe_file_name_.txt", "Sanitized filename should be safe for file systems"


def test_sanitize_filename_safe_no_change():
    """Test sanitize_filename_safe keeps safe filenames unchanged."""
    safe_name = "safe_filename.txt"
    sanitized = sanitize_filename_safe(safe_name)
    assert sanitized == safe_name, "Safe filename should remain unchanged"
