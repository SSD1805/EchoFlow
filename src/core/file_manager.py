# src/core/file_manager.py
import os
from typing import Optional

from structlog.stdlib import BoundLogger

from src.utils.file_utils import (
    copy_file_safe,
    delete_file_safe,
    file_exists,
    get_file_metadata,
    list_files_in_directory,
    safe_write,
    sanitize_filename_safe,
)


class FileManagerFacade:
    """
    Facade to handle all file-related operations using utilities from `file_utils`.
    """

    def __init__(self, logger: BoundLogger, tracker):
        """
        Initialize the FileManagerFacade with a logger and a performance tracker.

        Args:
            logger (BoundLogger): The logger instance.
            tracker: The performance tracker instance.
        """
        self.logger = logger
        self.tracker = tracker

    def save_file(self, content: bytes, file_path: str):
        """Save binary content to a specified file path."""
        with self.tracker.track_execution("Save File"):
            safe_write(content, file_path)
            self.logger.info(f"File saved successfully: {file_path}")

    def file_exists(self, file_path: str) -> bool:
        """Check if a file exists."""
        exists = file_exists(file_path)
        self.logger.info(f"File exists check for {file_path}: {exists}")
        return exists

    def get_file_metadata(self, file_path: str) -> dict:
        """Fetch metadata for a file."""
        metadata = get_file_metadata(file_path)
        self.logger.info(f"Metadata for {file_path}: {metadata}")
        return metadata

    def delete_file(self, file_path: str):
        """Delete a specified file."""
        with self.tracker.track_execution("Delete File"):
            delete_file_safe(file_path)
            self.logger.info(f"File deleted successfully: {file_path}")

    def copy_file(self, source: str, destination: str):
        """Copy a file from source to destination."""
        with self.tracker.track_execution("Copy File"):
            copy_file_safe(source, destination)
            self.logger.info(f"File copied from {source} to {destination}")

    def ensure_directory_exists(self, directory_path: str):
        """Ensure a directory exists, creating it if necessary."""
        with self.tracker.track_execution("Ensure Directory Exists"):
            os.makedirs(directory_path, exist_ok=True)
            self.logger.info(f"Directory ensured: {directory_path}")

    def list_files(self, directory_path: str, extensions: Optional[tuple] = None) -> list:
        """List files in a directory with optional filtering by extensions."""
        files = list_files_in_directory(directory_path, extensions)
        self.logger.info(
            f"Listed {len(files)} files in directory: {directory_path}"
        )
        return files

    def sanitize_filename(self, filename: str) -> str:
        """Sanitize a filename to make it safe for file systems."""
        sanitized = sanitize_filename_safe(filename)
        self.logger.info(f"Sanitized filename: {sanitized}")
        return sanitized
