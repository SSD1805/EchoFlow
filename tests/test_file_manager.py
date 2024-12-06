# tests/test_file_manager.py
import pytest
import os
from unittest.mock import Mock, patch, MagicMock, mock_open
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


@patch("builtins.open", new_callable=mock_open)
def test_save_file(mock_open, file_manager, mock_logger, mock_tracker):
    """Test saving a file."""
    file_path = "test.txt"
    content = b"Hello, World!"
    file_manager.save_file(content, file_path)

    mock_open.assert_called_once_with(file_path, "wb")
    mock_open().write.assert_called_once_with(content)
    mock_logger.info.assert_called_once_with(f"File saved successfully: {file_path}")
    mock_tracker.track_execution.assert_called_once_with("Save File")


@patch("builtins.open", new_callable=mock_open)
def test_load_file(mock_open, file_manager, mock_logger, mock_tracker):
    """Test loading a file."""
    file_path = "test.txt"
    content = b"Hello, World!"
    mock_open.return_value.read.return_value = content  # Simulate file content

    result = file_manager.load_file(file_path)

    # Assert that `open` was called with the correct arguments
    mock_open.assert_called_once_with(file_path, "rb")
    # Assert that the `read` method was called once on the file object
    mock_open.return_value.read.assert_called_once()
    # Assert that the result matches the expected content
    assert result == content

    # Verify logger and tracker calls
    mock_logger.info.assert_called_once_with(f"File loaded successfully: {file_path}")
    mock_tracker.track_execution.assert_called_once_with("Load File")



@patch("os.remove")
def test_delete_file(mock_remove, file_manager, mock_logger, mock_tracker):
    """Test deleting a file."""
    file_path = "test.txt"
    file_manager.delete_file(file_path)

    mock_remove.assert_called_once_with(file_path)
    mock_logger.info.assert_called_once_with(f"File deleted successfully: {file_path}")
    mock_tracker.track_execution.assert_called_once_with("Delete File")


@patch("shutil.copy2")
def test_copy_file(mock_copy, file_manager, mock_logger, mock_tracker):
    """Test copying a file."""
    source = "source.txt"
    destination = "destination.txt"
    file_manager.copy_file(source, destination)

    mock_copy.assert_called_once_with(source, destination)
    mock_logger.info.assert_called_once_with(
        f"File copied from {source} to {destination}"
    )
    mock_tracker.track_execution.assert_called_once_with("Copy File")


@patch("os.makedirs")
def test_ensure_directory_exists(mock_makedirs, file_manager, mock_logger):
    """Test ensuring a directory exists."""
    directory_path = "test_dir"
    file_manager.ensure_directory_exists(directory_path)

    mock_makedirs.assert_called_once_with(directory_path, exist_ok=True)
    mock_logger.info.assert_called_once_with(f"Directory ensured: {directory_path}")


@patch("os.listdir")
@patch("os.path.isfile")
def test_list_files(mock_isfile, mock_listdir, file_manager, mock_logger):
    """Test listing files in a directory."""
    directory_path = "test_dir"
    mock_listdir.return_value = ["file1.txt", "file2.txt", "file3.log"]
    mock_isfile.side_effect = lambda filepath: True
    extensions = (".txt",)

    result = file_manager.list_files(directory_path, extensions)

    assert result == [
        os.path.join(directory_path, "file1.txt"),
        os.path.join(directory_path, "file2.txt"),
    ]
    mock_logger.info.assert_called_once_with(
        f"Listed {len(result)} files in directory: {directory_path}"
    )


def test_sanitize_filename(file_manager, mock_logger):
    """Test sanitizing a filename."""
    filename = "unsafe/file*name?.txt"
    expected = "unsafe_file_name_.txt"

    result = file_manager.sanitize_filename(filename)

    assert result == expected
    mock_logger.info.assert_called_once_with(f"Sanitized filename: {expected}")
