# src/interfaces/base_file_manager.py
"""
File Path: src/interfaces/base_file_manager.py
Abstract base class for file management operations.
"""

from abc import ABC, abstractmethod
from typing import Optional, List


class BaseFileManager(ABC):
    """
    Abstract base class for file management operations.
    Defines the contract for all file management implementations.
    """

    @abstractmethod
    def save_file(self, content: bytes, file_path: str) -> None:
        """
        Save binary content to a specified file path.
        """
        pass

    @abstractmethod
    def ensure_directory_exists(self, directory_path: str):
        """Ensure a directory exists, creating it if necessary."""
        raise NotImplementedError

    @abstractmethod
    def file_exists(self, file_path: str) -> bool:
        """
        Check if a file exists.
        """
        pass

    @abstractmethod
    def get_file_metadata(self, file_path: str) -> dict:
        """
        Fetch metadata for a file.
        """
        pass

    @abstractmethod
    def delete_file(self, file_path: str) -> None:
        """
        Delete a specified file.
        """
        pass

    @abstractmethod
    def copy_file(self, source: str, destination: str) -> None:
        """
        Copy a file from source to destination.
        """
        pass

    @abstractmethod
    def ensure_directory_exists(self, directory_path: str) -> None:
        """
        Ensure that a directory exists, creating it if necessary.
        """
        pass

    @abstractmethod
    def list_files(
        self, directory_path: str, extensions: Optional[tuple] = None
    ) -> List[str]:
        """
        List files in a directory with optional filtering by extensions.
        """
        pass

    @abstractmethod
    def sanitize_filename(self, filename: str) -> str:
        """
        Sanitize a filename to make it safe for file systems.
        """
        pass

    @abstractmethod
    def log_operation(self, operation: str, details: Optional[dict] = None) -> None:
        """
        Log file operations for monitoring and debugging purposes.

        Args:
            operation (str): Description of the operation performed.
            details (Optional[dict]): Additional information about the operation.
        """
        pass

    @abstractmethod
    def upload_file(self, local_path: str, cloud_path: str) -> None:
        """
        Upload a file to a cloud storage system (placeholder for cloud integration).
        """
        pass

    @abstractmethod
    def download_file(self, cloud_path: str, local_path: str) -> None:
        """
        Download a file from a cloud storage system (placeholder for cloud integration).
        """
        pass

    @abstractmethod
    def list_cloud_files(self, cloud_path: str) -> List[str]:
        """
        List files in a cloud directory (placeholder for cloud integration).
        """
        pass

    @abstractmethod
    def delete_cloud_file(self, cloud_path: str) -> None:
        """
        Delete a file from a cloud storage system (placeholder for cloud integration).
        """
        pass

