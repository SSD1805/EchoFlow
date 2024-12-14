# tests/interfaces/test_base_file_manager.py

import pytest
from typing import Optional, List
from src.interfaces.base_file_manager import BaseFileManager


class MockFileManager(BaseFileManager):
    """Mock implementation of BaseFileManager for testing."""

    def save_file(self, content: bytes, file_path: str) -> None:
        pass

    def ensure_directory_exists(self, directory_path: str) -> None:
        pass

    def file_exists(self, file_path: str) -> bool:
        return True

    def get_file_metadata(self, file_path: str) -> dict:
        return {"size": 123, "last_modified": 123456789, "last_accessed": 123456789}

    def delete_file(self, file_path: str) -> None:
        pass

    def copy_file(self, source: str, destination: str) -> None:
        pass

    def list_files(
        self, directory_path: str, extensions: Optional[tuple] = None
    ) -> List[str]:
        return ["file1.txt", "file2.log"]

    def sanitize_filename(self, filename: str) -> str:
        return "safe_filename.txt"

    def log_operation(self, operation: str, details: Optional[dict] = None) -> None:
        pass

    def upload_file(self, local_path: str, cloud_path: str) -> None:
        pass

    def download_file(self, cloud_path: str, local_path: str) -> None:
        pass

    def list_cloud_files(self, cloud_path: str) -> List[str]:
        return ["cloud_file1.txt", "cloud_file2.txt"]

    def delete_cloud_file(self, cloud_path: str) -> None:
        pass


@pytest.fixture
def base_file_manager():
    """Fixture for MockFileManager."""
    return MockFileManager()


# Test methods
def test_save_file(base_file_manager):
    """Test save_file method."""
    base_file_manager.save_file(b"content", "file_path.txt")


def test_file_exists(base_file_manager):
    """Test file_exists method."""
    assert base_file_manager.file_exists("some_file.txt")


def test_get_file_metadata(base_file_manager):
    """Test get_file_metadata method."""
    metadata = base_file_manager.get_file_metadata("some_file.txt")
    assert metadata["size"] == 123


def test_delete_file(base_file_manager):
    """Test delete_file method."""
    base_file_manager.delete_file("file_path.txt")


def test_copy_file(base_file_manager):
    """Test copy_file method."""
    base_file_manager.copy_file("source.txt", "destination.txt")


def test_ensure_directory_exists(base_file_manager):
    """Test ensure_directory_exists method."""
    base_file_manager.ensure_directory_exists("/some/directory")


def test_list_files(base_file_manager):
    """Test list_files method."""
    files = base_file_manager.list_files("/some/path")
    assert len(files) == 2


def test_sanitize_filename(base_file_manager):
    """Test sanitize_filename method."""
    sanitized = base_file_manager.sanitize_filename("unsafe/file*name?.txt")
    assert sanitized == "safe_filename.txt"


def test_log_operation(base_file_manager):
    """Test log_operation method."""
    base_file_manager.log_operation("test_operation", {"key": "value"})


def test_upload_file(base_file_manager):
    """Test upload_file method."""
    base_file_manager.upload_file("local_path.txt", "cloud_path.txt")


def test_download_file(base_file_manager):
    """Test download_file method."""
    base_file_manager.download_file("cloud_path.txt", "local_path.txt")


def test_list_cloud_files(base_file_manager):
    """Test list_cloud_files method."""
    cloud_files = base_file_manager.list_cloud_files("cloud/path")
    assert len(cloud_files) == 2


def test_delete_cloud_file(base_file_manager):
    """Test delete_cloud_file method."""
    base_file_manager.delete_cloud_file("cloud_path.txt")
