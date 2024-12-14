# tests/core/test_file_manager_facade.py
"""
File Path: tests/core/test_file_manager_facade.py
Test suite for the FileManagerFacade class.
"""

import pytest
from unittest.mock import MagicMock
from src.core.file_manager_facade import FileManagerFacade
from src.interfaces.base_file_manager import BaseFileManager


@pytest.fixture
def mock_file_manager():
    """Mock implementation of the BaseFileManager."""
    mock = MagicMock(spec=BaseFileManager)
    return mock


@pytest.fixture
def mock_logger():
    """Mock logger instance."""
    return MagicMock()


@pytest.fixture
def mock_tracker():
    """Mock tracker instance."""
    tracker = MagicMock()
    tracker.track_execution = MagicMock()
    return tracker


@pytest.fixture
def file_manager_facade(mock_file_manager, mock_logger, mock_tracker):
    """Fixture for FileManagerFacade."""
    return FileManagerFacade(mock_file_manager, mock_logger, mock_tracker())


def test_save_file(file_manager_facade, mock_file_manager, mock_logger):
    """Test save_file functionality."""
    content = b"Test Content"
    file_path = "test_file.txt"
    file_manager_facade.save_file(content, file_path)

    mock_file_manager.save_file.assert_called_once_with(content, file_path)
    mock_logger.info.assert_any_call("Save File Operation", operation="save_file", path=file_path)


def test_file_exists(file_manager_facade, mock_file_manager, mock_logger):
    """Test file_exists functionality."""
    file_path = "test_file.txt"
    mock_file_manager.file_exists.return_value = True

    exists = file_manager_facade.file_exists(file_path)

    mock_file_manager.file_exists.assert_called_once_with(file_path)
    mock_logger.info.assert_any_call(
        "File Exists Check", operation="file_exists", path=file_path, exists=True
    )
    assert exists is True


def test_get_file_metadata(file_manager_facade, mock_file_manager, mock_logger):
    """Test get_file_metadata functionality."""
    file_path = "test_file.txt"
    metadata = {"size": 1024, "last_modified": 123456789}
    mock_file_manager.get_file_metadata.return_value = metadata

    result = file_manager_facade.get_file_metadata(file_path)

    mock_file_manager.get_file_metadata.assert_called_once_with(file_path)
    mock_logger.info.assert_any_call(
        "Get File Metadata", operation="get_file_metadata", path=file_path, metadata=metadata
    )
    assert result == metadata


def test_delete_file(file_manager_facade, mock_file_manager, mock_logger):
    """Test delete_file functionality."""
    file_path = "test_file.txt"
    file_manager_facade.delete_file(file_path)

    mock_file_manager.delete_file.assert_called_once_with(file_path)
    mock_logger.info.assert_any_call("Delete File Operation", operation="delete_file", path=file_path)


def test_copy_file(file_manager_facade, mock_file_manager, mock_logger):
    """Test copy_file functionality."""
    source = "source.txt"
    destination = "destination.txt"
    file_manager_facade.copy_file(source, destination)

    mock_file_manager.copy_file.assert_called_once_with(source, destination)
    mock_logger.info.assert_any_call(
        "Copy File Operation", operation="copy_file", source=source, destination=destination
    )


def test_ensure_directory_exists(file_manager_facade, mock_file_manager, mock_logger):
    """Test ensure_directory_exists functionality."""
    directory_path = "test_directory"
    file_manager_facade.ensure_directory_exists(directory_path)

    mock_file_manager.ensure_directory_exists.assert_called_once_with(directory_path)
    mock_logger.info.assert_any_call(
        "Ensure Directory Exists", operation="ensure_directory_exists", path=directory_path
    )


def test_list_files(file_manager_facade, mock_file_manager, mock_logger):
    """Test list_files functionality."""
    directory_path = "test_directory"
    extensions = (".txt", ".log")
    mock_file_manager.list_files.return_value = ["file1.txt", "file2.log"]

    files = file_manager_facade.list_files(directory_path, extensions)

    mock_file_manager.list_files.assert_called_once_with(directory_path, extensions)
    mock_logger.info.assert_any_call(
        "List Files Operation",
        operation="list_files",
        path=directory_path,
        extensions=extensions,
        file_count=2,
    )
    assert files == ["file1.txt", "file2.log"]


def test_sanitize_filename(file_manager_facade, mock_file_manager, mock_logger):
    """Test sanitize_filename functionality."""
    filename = "unsafe/file*name?.txt"
    sanitized = "safe_filename.txt"
    mock_file_manager.sanitize_filename.return_value = sanitized

    result = file_manager_facade.sanitize_filename(filename)

    mock_file_manager.sanitize_filename.assert_called_once_with(filename)
    mock_logger.info.assert_any_call(
        "Sanitize Filename", operation="sanitize_filename", original=filename, sanitized=sanitized
    )
    assert result == sanitized


def test_upload_file(file_manager_facade, mock_file_manager, mock_logger):
    """Test upload_file functionality."""
    local_path = "local.txt"
    cloud_path = "cloud.txt"
    file_manager_facade.upload_file(local_path, cloud_path)

    mock_file_manager.upload_file.assert_called_once_with(local_path, cloud_path)
    mock_logger.info.assert_any_call(
        "Upload File Operation", operation="upload_file", local_path=local_path, cloud_path=cloud_path
    )


def test_download_file(file_manager_facade, mock_file_manager, mock_logger):
    """Test download_file functionality."""
    cloud_path = "cloud.txt"
    local_path = "local.txt"
    file_manager_facade.download_file(cloud_path, local_path)

    mock_file_manager.download_file.assert_called_once_with(cloud_path, local_path)
    mock_logger.info.assert_any_call(
        "Download File Operation", operation="download_file", cloud_path=cloud_path, local_path=local_path
    )


def test_list_cloud_files(file_manager_facade, mock_file_manager, mock_logger):
    """Test list_cloud_files functionality."""
    cloud_path = "cloud_directory"
    mock_file_manager.list_cloud_files.return_value = ["cloud_file1.txt", "cloud_file2.txt"]

    files = file_manager_facade.list_cloud_files(cloud_path)

    mock_file_manager.list_cloud_files.assert_called_once_with(cloud_path)
    mock_logger.info.assert_any_call(
        "List Cloud Files Operation",
        operation="list_cloud_files",
        cloud_path=cloud_path,
        file_count=2,
    )
    assert files == ["cloud_file1.txt", "cloud_file2.txt"]


def test_delete_cloud_file(file_manager_facade, mock_file_manager, mock_logger):
    """Test delete_cloud_file functionality."""
    cloud_path = "cloud_file.txt"
    file_manager_facade.delete_cloud_file(cloud_path)

    mock_file_manager.delete_cloud_file.assert_called_once_with(cloud_path)
    mock_logger.info.assert_any_call(
        "Delete Cloud File Operation", operation="delete_cloud_file", cloud_path=cloud_path
    )
