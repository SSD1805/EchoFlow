# src/interfaces/ifile_utility.py
from abc import ABC, abstractmethod
from typing import Optional, List


class IFileUtility(ABC):
    """
    Interface for file-related operations. Abstracts local and cloud-based file utilities.
    """

    @abstractmethod
    def safe_write(self, content: bytes, file_path: str) -> None:
        """Write binary content to a file safely."""
        raise NotImplementedError

    @abstractmethod
    def file_exists(self, file_path: str) -> bool:
        """Check if a file exists."""
        raise NotImplementedError

    @abstractmethod
    def get_file_metadata(self, file_path: str) -> dict:
        """Fetch metadata for a file."""
        raise NotImplementedError

    @abstractmethod
    def delete_file_safe(self, file_path: str) -> None:
        """Delete a file safely."""
        raise NotImplementedError

    @abstractmethod
    def copy_file_safe(self, source: str, destination: str) -> None:
        """Copy a file safely."""
        raise NotImplementedError

    @abstractmethod
    def list_files_in_directory(
        self, directory_path: str, extensions: Optional[tuple] = None
    ) -> List[str]:
        """List files in a directory with optional filtering by extensions."""
        raise NotImplementedError

    @abstractmethod
    def sanitize_filename_safe(self, filename: str) -> str:
        """Sanitize a filename to make it safe for file systems."""
        raise NotImplementedError

    # Placeholders for cloud-based operations
    @abstractmethod
    def upload_file(self, local_path: str, cloud_path: str) -> None:
        """Upload a file to cloud storage."""
        raise NotImplementedError

    @abstractmethod
    def download_file(self, cloud_path: str, local_path: str) -> None:
        """Download a file from cloud storage."""
        raise NotImplementedError

    @abstractmethod
    def list_cloud_files(self, cloud_path: str) -> List[str]:
        """List files in a cloud storage path."""
        raise NotImplementedError

    @abstractmethod
    def delete_cloud_file(self, cloud_path: str) -> None:
        """Delete a file from cloud storage."""
        raise NotImplementedError

    @abstractmethod
    def ensure_directory_exists(self, directory_path: str) -> None:
        """Ensure a directory exists, creating it if necessary."""
        raise NotImplementedError