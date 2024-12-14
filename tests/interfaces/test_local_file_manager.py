import os
import pytest
from structlog import get_logger
from tempfile import TemporaryDirectory
from src.interfaces.local_file_manager import LocalFileManager
from src.utils.file_utils import LocalFileUtility

@pytest.fixture
def logger():
    """Fixture for a mock logger."""
    return get_logger()

@pytest.fixture
def file_utility():
    """Fixture for LocalFileUtility."""
    return LocalFileUtility()

@pytest.fixture
def file_manager(file_utility, logger):
    """Fixture for LocalFileManager."""
    return LocalFileManager(file_utility, logger)

@pytest.fixture
def temp_directory():
    """Fixture for creating a temporary directory."""
    with TemporaryDirectory() as temp_dir:
        yield temp_dir

def test_save_file(file_manager, temp_directory):
    """Test save_file functionality."""
    file_path = os.path.join(temp_directory, "test_file.txt")
    content = b"Hello, World!"

    file_manager.save_file(content, file_path)

    assert os.path.exists(file_path), "File should exist after save_file"
    with open(file_path, "rb") as file:
        assert file.read() == content, "File content should match the written content"

def test_file_exists(file_manager, temp_directory):
    """Test file_exists functionality."""
    file_path = os.path.join(temp_directory, "test_file.txt")
    with open(file_path, "w") as file:
        file.write("test")

    assert file_manager.file_exists(file_path), "File should exist"
    assert not file_manager.file_exists("non_existent.txt"), "Non-existent file should return False"

def test_get_file_metadata(file_manager, temp_directory):
    """Test get_file_metadata functionality."""
    file_path = os.path.join(temp_directory, "test_file.txt")
    content = b"File metadata test!"
    file_manager.save_file(content, file_path)

    metadata = file_manager.get_file_metadata(file_path)
    assert "size" in metadata, "Metadata should include file size"
    assert metadata["size"] == len(content), "Size should match file content length"

def test_delete_file(file_manager, temp_directory):
    """Test delete_file functionality."""
    file_path = os.path.join(temp_directory, "test_file.txt")
    with open(file_path, "w") as file:
        file.write("Delete me")

    file_manager.delete_file(file_path)
    assert not os.path.exists(file_path), "File should not exist after deletion"

def test_copy_file(file_manager, temp_directory):
    """Test copy_file functionality."""
    source_path = os.path.join(temp_directory, "source.txt")
    destination_path = os.path.join(temp_directory, "destination.txt")

    content = b"Copy file test!"
    file_manager.save_file(content, source_path)
    file_manager.copy_file(source_path, destination_path)

    assert os.path.exists(destination_path), "Destination file should exist"
    with open(destination_path, "rb") as file:
        assert file.read() == content, "Destination file content should match source file content"

def test_ensure_directory_exists(file_manager, temp_directory):
    """Test ensure_directory_exists functionality."""
    new_directory = os.path.join(temp_directory, "new_directory")
    file_manager.ensure_directory_exists(new_directory)
    assert os.path.exists(new_directory) and os.path.isdir(new_directory), "Directory should exist"

def test_list_files(file_manager, temp_directory):
    """Test list_files functionality."""
    extensions = (".txt", ".log")
    file1 = os.path.join(temp_directory, "file1.txt")
    file2 = os.path.join(temp_directory, "file2.log")
    file3 = os.path.join(temp_directory, "file3.jpg")

    with open(file1, "w"), open(file2, "w"), open(file3, "w"):
        pass

    files = file_manager.list_files(temp_directory, extensions)
    assert len(files) == 2, "Only files with specified extensions should be listed"
    assert file1 in files and file2 in files, "Files with matching extensions should be included"
    assert file3 not in files, "Files with non-matching extensions should not be included"

def test_sanitize_filename(file_manager):
    """Test sanitize_filename functionality."""
    unsafe_name = "unsafe/file*name?.txt"
    sanitized = file_manager.sanitize_filename(unsafe_name)
    assert sanitized == "unsafe_file_name_.txt", "Filename should be sanitized correctly"

def test_upload_file_placeholder(file_manager):
    """Test that upload_file raises NotImplementedError."""
    with pytest.raises(NotImplementedError):
        file_manager.upload_file("local_path.txt", "cloud_path.txt")

def test_download_file_placeholder(file_manager):
    """Test that download_file raises NotImplementedError."""
    with pytest.raises(NotImplementedError):
        file_manager.download_file("cloud_path.txt", "local_path.txt")
