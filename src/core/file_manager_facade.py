# src/core/file_manager_facade.py
"""
Facade for managing file operations using various file manager implementations.
"""

from structlog.stdlib import BoundLogger
from typing import Optional
from src.interfaces.base_file_manager import BaseFileManager


class FileManagerFacade:
    """
    Facade to handle all file-related operations using implementations of `BaseFileManager`.
    """

    def __init__(self, file_manager: BaseFileManager, logger: BoundLogger, tracker):
        """
        Initialize the FileManagerFacade with a file manager, logger, and a performance tracker.

        Args:
            file_manager (BaseFileManager): An instance of a file manager implementation (local or cloud).
            logger (BoundLogger): A logger instance for logging operations.
            tracker: A performance tracker instance for monitoring execution time.
        """
        self.file_manager = file_manager
        self.logger = logger
        self.tracker = tracker

    def save_file(self, content: bytes, file_path: str):
        """Save binary content to a specified file path."""
        with self.tracker.track_execution("Save File"):
            self.file_manager.save_file(content, file_path)
            self.logger.info("Save File Operation", operation="save_file", path=file_path)

    def file_exists(self, file_path: str) -> bool:
        """Check if a file exists."""
        with self.tracker.track_execution("Check File Exists"):
            exists = self.file_manager.file_exists(file_path)
            self.logger.info("File Exists Check", operation="file_exists", path=file_path, exists=exists)
            return exists

    def get_file_metadata(self, file_path: str) -> dict:
        """Fetch metadata for a file."""
        with self.tracker.track_execution("Get File Metadata"):
            metadata = self.file_manager.get_file_metadata(file_path)
            self.logger.info("Get File Metadata", operation="get_file_metadata", path=file_path, metadata=metadata)
            return metadata

    def delete_file(self, file_path: str):
        """Delete a specified file."""
        with self.tracker.track_execution("Delete File"):
            self.file_manager.delete_file(file_path)
            self.logger.info("Delete File Operation", operation="delete_file", path=file_path)

    def copy_file(self, source: str, destination: str):
        """Copy a file from source to destination."""
        with self.tracker.track_execution("Copy File"):
            self.file_manager.copy_file(source, destination)
            self.logger.info("Copy File Operation", operation="copy_file", source=source, destination=destination)

    def ensure_directory_exists(self, directory_path: str):
        """Ensure a directory exists, creating it if necessary."""
        with self.tracker.track_execution("Ensure Directory Exists"):
            self.file_manager.ensure_directory_exists(directory_path)
            self.logger.info("Ensure Directory Exists", operation="ensure_directory_exists", path=directory_path)

    def list_files(self, directory_path: str, extensions: Optional[tuple] = None) -> list:
        """List files in a directory with optional filtering by extensions."""
        with self.tracker.track_execution("List Files"):
            files = self.file_manager.list_files(directory_path, extensions)
            self.logger.info(
                "List Files Operation",
                operation="list_files",
                path=directory_path,
                extensions=extensions,
                file_count=len(files),
            )
            return files

    def sanitize_filename(self, filename: str) -> str:
        """Sanitize a filename to make it safe for file systems."""
        sanitized = self.file_manager.sanitize_filename(filename)
        self.logger.info("Sanitize Filename", operation="sanitize_filename", original=filename, sanitized=sanitized)
        return sanitized

    def upload_file(self, local_path: str, cloud_path: str):
        """Upload a file to cloud storage."""
        with self.tracker.track_execution("Upload File"):
            self.file_manager.upload_file(local_path, cloud_path)
            self.logger.info("Upload File Operation", operation="upload_file", local_path=local_path, cloud_path=cloud_path)

    def download_file(self, cloud_path: str, local_path: str):
        """Download a file from cloud storage."""
        with self.tracker.track_execution("Download File"):
            self.file_manager.download_file(cloud_path, local_path)
            self.logger.info("Download File Operation", operation="download_file", cloud_path=cloud_path, local_path=local_path)

    def list_cloud_files(self, cloud_path: str) -> list:
        """List files in a cloud storage path."""
        with self.tracker.track_execution("List Cloud Files"):
            files = self.file_manager.list_cloud_files(cloud_path)
            self.logger.info("List Cloud Files Operation", operation="list_cloud_files", cloud_path=cloud_path, file_count=len(files))
            return files

    def delete_cloud_file(self, cloud_path: str):
        """Delete a file from cloud storage."""
        with self.tracker.track_execution("Delete Cloud File"):
            self.file_manager.delete_cloud_file(cloud_path)
            self.logger.info("Delete Cloud File Operation", operation="delete_cloud_file", cloud_path=cloud_path)
