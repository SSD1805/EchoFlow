from unittest.mock import MagicMock, Mock, patch

import pytest

from src.core.file_manager import FileManagerFacade


@pytest.fixture
def mock_logger():
    """Mock the logger dependency."""
    return Mock()


@pytest.fixture
def mock_tracker():
    """Mock the performance tracker dependency."""
    tracker = Mock()
    tracker.track_execution = MagicMock()
    return tracker


@pytest.fixture
def file_manager(mock_logger, mock_tracker):
    """Create an instance of FileManagerFacade with mocked dependencies."""
    return FileManagerFacade(logger=mock_logger, tracker=mock_tracker)


@patch("src.core.file_manager.safe_write")
def test_save_file(mock_safe_write, file_manager, mock_logger, mock_tracker):
    """Test saving a file."""
    file_path = "test.txt"
    content = b"Hello, World!"
    file_manager.save_file(content, file_path)

    mock_safe_write.assert_called_once_with(content, file_path)
    mock_logger.info.assert_called_once_with(f"File saved successfully: {file_path}")
    mock_tracker.track_execution.assert_called_once_with("Save File")


@patch("src.core.file_manager.file_exists")
def test_file_exists(mock_file_exists, file_manager, mock_logger):
    """Test checking if a file exists."""
    file_path = "test.txt"
    mock_file_exists.return_value = True

    result = file_manager.file_exists(file_path)

    mock_file_exists.assert_called_once_with(file_path)
    assert result is True
    mock_logger.info.assert_called_once_with(f"File exists check for {file_path}: True")


@patch("src.core.file_manager.get_file_metadata")
def test_get_file_metadata(mock_get_metadata, file_manager, mock_logger):
    """Test fetching file metadata."""
    file_path = "test.txt"
    metadata = {"size": 1024, "last_modified": 1683202323, "last_accessed": 1683202023}
    mock_get_metadata.return_value = metadata

    result = file_manager.get_file_metadata(file_path)

    mock_get_metadata.assert_called_once_with(file_path)
    assert result == metadata
    mock_logger.info.assert_called_once_with(f"Metadata for {file_path}: {metadata}")


@patch("src.core.file_manager.delete_file_safe")
def test_delete_file(mock_delete_safe, file_manager, mock_logger, mock_tracker):
    """Test deleting a file."""
    file_path = "test.txt"
    file_manager.delete_file(file_path)

    mock_delete_safe.assert_called_once_with(file_path)
    mock_logger.info.assert_called_once_with(f"File deleted successfully: {file_path}")
    mock_tracker.track_execution.assert_called_once_with("Delete File")


@patch("src.core.file_manager.copy_file_safe")
def test_copy_file(mock_copy_safe, file_manager, mock_logger, mock_tracker):
    """Test copying a file."""
    source = "source.txt"
    destination = "destination.txt"
    file_manager.copy_file(source, destination)

    mock_copy_safe.assert_called_once_with(source, destination)
    mock_logger.info.assert_called_once_with(
        f"File copied from {source} to {destination}"
    )
    mock_tracker.track_execution.assert_called_once_with("Copy File")


@patch("os.makedirs")
def test_ensure_directory_exists(mock_makedirs, file_manager, mock_logger, mock_tracker):
    """Test ensuring a directory exists."""
    directory_path = "test_dir"
    file_manager.ensure_directory_exists(directory_path)

    mock_makedirs.assert_called_once_with(directory_path, exist_ok=True)
    mock_logger.info.assert_called_once_with(f"Directory ensured: {directory_path}")
    mock_tracker.track_execution.assert_called_once_with("Ensure Directory Exists")


@patch("src.core.file_manager.list_files_in_directory")
def test_list_files(mock_list_files, file_manager, mock_logger):
    """Test listing files in a directory."""
    directory_path = "test_dir"
    mock_list_files.return_value = ["file1.txt", "file2.txt"]
    extensions = (".txt",)

    result = file_manager.list_files(directory_path, extensions)

    mock_list_files.assert_called_once_with(directory_path, extensions)
    assert result == ["file1.txt", "file2.txt"]
    mock_logger.info.assert_called_once_with(
        f"Listed {len(result)} files in directory: {directory_path}"
    )


@patch("src.core.file_manager.sanitize_filename_safe")
def test_sanitize_filename(mock_sanitize, file_manager, mock_logger):
    """Test sanitizing a filename."""
    filename = "unsafe/file*name?.txt"
    sanitized = "unsafe_file_name_.txt"
    mock_sanitize.return_value = sanitized

    result = file_manager.sanitize_filename(filename)

    mock_sanitize.assert_called_once_with(filename)
    assert result == sanitized
    mock_logger.info.assert_called_once_with(f"Sanitized filename: {sanitized}")
