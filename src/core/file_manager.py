# src/core/file_manager.py

import os
import shutil
from typing import Optional
from structlog.stdlib import BoundLogger


class FileManagerFacade:
    """
    Facade to handle all file-related operations including file management,
    directory management, and filename sanitization.
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
            try:
                with open(file_path, "wb") as file:
                    file.write(content)
                self.logger.info(f"File saved successfully: {file_path}")
            except Exception as e:
                self.logger.error(f"Failed to save file {file_path}: {e}")
                raise

    def load_file(self, file_path: str) -> bytes:
        """Load and return binary content from a file."""
        with self.tracker.track_execution("Load File"):
            try:
                with open(file_path, "rb") as file:
                    content = file.read()
                self.logger.info(f"File loaded successfully: {file_path}")
                return content
            except Exception as e:
                self.logger.error(f"Failed to load file {file_path}: {e}")
                raise

    def delete_file(self, file_path: str):
        """Delete a specified file."""
        with self.tracker.track_execution("Delete File"):
            try:
                os.remove(file_path)
                self.logger.info(f"File deleted successfully: {file_path}")
            except Exception as e:
                self.logger.error(f"Failed to delete file {file_path}: {e}")
                raise

    def copy_file(self, source: str, destination: str):
        """Copy a file from source to destination."""
        with self.tracker.track_execution("Copy File"):
            try:
                shutil.copy2(source, destination)
                self.logger.info(f"File copied from {source} to {destination}")
            except Exception as e:
                self.logger.error(
                    f"Failed to copy file from {source} to {destination}: {e}"
                )
                raise

    def ensure_directory_exists(self, directory_path: str):
        """Ensure a directory exists, creating it if necessary."""
        try:
            os.makedirs(directory_path, exist_ok=True)
            self.logger.info(f"Directory ensured: {directory_path}")
        except Exception as e:
            self.logger.error(f"Failed to ensure directory {directory_path}: {e}")
            raise

    def list_files(self, directory_path: str, extensions: Optional[tuple] = None) -> list:
        """List files in a directory with optional filtering by extensions."""
        try:
            files = [
                os.path.join(directory_path, f)
                for f in os.listdir(directory_path)
                if os.path.isfile(os.path.join(directory_path, f))
                   and (not extensions or f.endswith(extensions))
            ]
            self.logger.info(
                f"Listed {len(files)} files in directory: {directory_path}"
            )
            return files
        except Exception as e:
            self.logger.error(
                f"Failed to list files in directory {directory_path}: {e}"
            )
            raise

    def sanitize_filename(self, filename: str) -> str:
        """Sanitize a filename to make it safe for file systems."""
        sanitized = "".join(
            c if c.isalnum() or c in " ._-()" else "_" for c in filename
        )
        self.logger.info(f"Sanitized filename: {sanitized}")
        return sanitized
