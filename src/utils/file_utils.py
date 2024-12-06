# src/utils/file_utils.py
import os
import shutil
import tempfile
from typing import Optional


def safe_write(content: bytes, file_path: str):
    """
    Save binary content to a file atomically by writing to a temporary file first.
    """
    try:
        dir_name = os.path.dirname(file_path)
        tmp_file = tempfile.NamedTemporaryFile(delete=False, dir=dir_name)
        with open(tmp_file.name, "wb") as temp_file:
            temp_file.write(content)
        shutil.move(tmp_file.name, file_path)
    except Exception as e:
        raise OSError(f"Failed to safely write file {file_path}: {e}")


def file_exists(file_path: str) -> bool:
    """Check if a file exists."""
    return os.path.isfile(file_path)


def get_file_metadata(file_path: str) -> dict:
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


def delete_file_safe(file_path: str):
    """Delete a file safely."""
    try:
        os.remove(file_path)
    except FileNotFoundError:
        pass  # No-op if the file doesn't exist
    except Exception as e:
        raise OSError(f"Failed to delete file {file_path}: {e}")


def copy_file_safe(source: str, destination: str):
    """Copy a file safely."""
    try:
        shutil.copy2(source, destination)
    except Exception as e:
        raise OSError(f"Failed to copy file from {source} to {destination}: {e}")


def list_files_in_directory(directory_path: str, extensions: Optional[tuple] = None) -> list:
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


def sanitize_filename_safe(filename: str) -> str:
    """
    Sanitize a filename to make it safe for file systems.
    """
    return "".join(c if c.isalnum() or c in " ._-()" else "_" for c in filename)
