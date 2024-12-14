# src/utils/file_utils.py
"""
File Path: src/utils/local_file_utility.py
Local file utilities for managing file operations independently of interfaces.
"""

import os
import shutil
import tempfile
from typing import List, Optional


class LocalFileUtility:
    """
    A utility class for local file operations with instance-level design.
    """

    def __init__(self):
        """
        Initialize the LocalFileUtility instance.
        Future attributes like logging or configuration can be added here.
        """
        self.default_directory = os.getcwd()  # Example instance-level attribute

    def safe_write(self, content: bytes, file_path: str) -> None:
        """
        Save binary content to a file atomically by writing to a temporary file first.
        """
        try:
            dir_name = os.path.dirname(file_path) or self.default_directory
            tmp_file = tempfile.NamedTemporaryFile(delete=False, dir=dir_name)
            with open(tmp_file.name, "wb") as temp_file:
                temp_file.write(content)
            shutil.move(tmp_file.name, file_path)
        except Exception as e:
            raise OSError(f"Failed to safely write file {file_path}: {e}")

    def file_exists(self, file_path: str) -> bool:
        """Check if a file exists."""
        return os.path.isfile(file_path)

    def get_file_metadata(self, file_path: str) -> dict:
        """Fetch metadata for a file."""
        try:
            stats = os.stat(file_path)
            return {
                "size": stats.st_size,
                "last_modified": stats.st_mtime,
                "last_accessed": stats.st_atime,
            }
        except Exception as e:
            raise OSError(f"Failed to fetch metadata for {file_path}: {e}")

    def delete_file_safe(self, file_path: str) -> None:
        """Delete a file safely."""
        try:
            os.remove(file_path)
        except FileNotFoundError:
            pass
        except Exception as e:
            raise OSError(f"Failed to delete file {file_path}: {e}")

    def copy_file_safe(self, source: str, destination: str) -> None:
        """Copy a file safely."""
        try:
            shutil.copy2(source, destination)
        except Exception as e:
            raise OSError(f"Failed to copy file from {source} to {destination}: {e}")

    def list_files_in_directory(
        self, directory_path: str, extensions: Optional[tuple] = None
    ) -> List[str]:
        """
        List files in a directory with optional filtering by extensions.
        """
        try:
            return [
                os.path.join(directory_path, f)
                for f in os.listdir(directory_path)
                if os.path.isfile(os.path.join(directory_path, f))
                and (not extensions or f.endswith(extensions))
            ]
        except Exception as e:
            raise OSError(f"Failed to list files in directory {directory_path}: {e}")

    def sanitize_filename_safe(self, filename: str) -> str:
        """
        Sanitize a filename to make it safe for file systems.
        """
        return "".join(c if c.isalnum() or c in " ._-()" else "_" for c in filename)

    def ensure_directory_exists(self, directory_path: str) -> None:
        """
        Ensure a directory exists, creating it if necessary.
        """
        try:
            os.makedirs(directory_path, exist_ok=True)
        except Exception as e:
            raise OSError(f"Failed to ensure directory exists at {directory_path}: {e}")