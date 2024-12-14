# tests/interfaces/test_ifile_utility.py

import pytest
from typing import List, Optional
from src.interfaces.ifile_utility import IFileUtility


class MockFileUtility(IFileUtility):
    """Mock implementation of the IFileUtility interface for testing."""

    def safe_write(self, content: bytes, file_path: str) -> None:
        pass

    def file_exists(self, file_path: str) -> bool:
        return True

    def get_file_metadata(self, file_path: str) -> dict:
        return {"size": 123, "last_modified": 123456789, "last_accessed": 123456789}

    def delete_file_safe(self, file_path: str) -> None:
        pass

    def ensure_directory_exists(self, directory_path: str) -> None:
        # Mock implementation for testing
        pass

    def copy_file_safe(self, source: str, destination: str) -> None:
        pass

    def list_files_in_directory(
        self, directory_path: str, extensions: Optional[tuple] = None
    ) -> List[str]:
        return ["file1.txt", "file2.log"]

    def sanitize_filename_safe(self, filename: str) -> str:
        return "safe_filename.txt"

    def upload_file(self, local_path: str, cloud_path: str) -> None:
        pass

    def download_file(self, cloud_path: str, local_path: str) -> None:
        pass

    def list_cloud_files(self, cloud_path: str) -> List[str]:
        return ["cloud_file1.txt", "cloud_file2.txt"]

    def delete_cloud_file(self, cloud_path: str) -> None:
        pass


@pytest.fixture
def utility():
    """Fixture for MockFileUtility."""
    return MockFileUtility()


def test_safe_write(utility):
    """Test the safe_write method."""
    utility.safe_write(b"content", "file_path.txt")


def test_file_exists(utility):
    """Test the file_exists method."""
    assert utility.file_exists("some_file.txt")


def test_get_file_metadata(utility):
    """Test the get_file_metadata method."""
    metadata = utility.get_file_metadata("some_file.txt")
    assert metadata["size"] == 123


def test_delete_file_safe(utility):
    """Test the delete_file_safe method."""
    utility.delete_file_safe("file_path.txt")


def test_copy_file_safe(utility):
    """Test the copy_file_safe method."""
    utility.copy_file_safe("source.txt", "destination.txt")


def test_list_files_in_directory(utility):
    """Test the list_files_in_directory method."""
    files = utility.list_files_in_directory("/some/path")
    assert len(files) == 2


def test_sanitize_filename_safe(utility):
    """Test the sanitize_filename_safe method."""
    sanitized = utility.sanitize_filename_safe("unsafe/file*name?.txt")
    assert sanitized == "safe_filename.txt"


def test_upload_file(utility):
    """Test the upload_file method."""
    utility.upload_file("local_path.txt", "cloud_path.txt")


def test_download_file(utility):
    """Test the download_file method."""
    utility.download_file("cloud_path.txt", "local_path.txt")


def test_list_cloud_files(utility):
    """Test the list_cloud_files method."""
    cloud_files = utility.list_cloud_files("cloud/path")
    assert len(cloud_files) == 2


def test_delete_cloud_file(utility):
    """Test the delete_cloud_file method."""
    utility.delete_cloud_file("cloud_path.txt")

def test_ensure_directory_exists(utility):
    """Test the ensure_directory_exists method."""
    utility.ensure_directory_exists("/some/directory")