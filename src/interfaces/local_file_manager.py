# src/interfaces/local_file_manager.py

from typing import Optional
from structlog.stdlib import BoundLogger
from src.interfaces.base_file_manager import BaseFileManager
from src.utils.file_utils import LocalFileUtility


class LocalFileManager(BaseFileManager):
    """Implementation of BaseFileManager for local file operations."""

    def __init__(self, file_utility: LocalFileUtility, logger: BoundLogger):
        self.file_utility = file_utility
        self.logger = logger

    def save_file(self, content: bytes, file_path: str):
        self.logger.info(f"Saving file: {file_path}")
        self.file_utility.safe_write(content, file_path)
        self.logger.info(f"File saved successfully: {file_path}")

    def file_exists(self, file_path: str) -> bool:
        exists = self.file_utility.file_exists(file_path)
        self.logger.info(f"File exists check for {file_path}: {exists}")
        return exists

    def get_file_metadata(self, file_path: str) -> dict:
        metadata = self.file_utility.get_file_metadata(file_path)
        self.logger.info(f"Metadata for {file_path}: {metadata}")
        return metadata

    def delete_file(self, file_path: str):
        self.logger.info(f"Deleting file: {file_path}")
        self.file_utility.delete_file_safe(file_path)
        self.logger.info(f"File deleted successfully: {file_path}")

    def copy_file(self, source: str, destination: str):
        self.logger.info(f"Copying file from {source} to {destination}")
        self.file_utility.copy_file_safe(source, destination)
        self.logger.info(f"File copied successfully: {source} -> {destination}")

    def ensure_directory_exists(self, directory_path: str):
        self.logger.info(f"Ensuring directory exists: {directory_path}")
        self.file_utility.ensure_directory_exists(directory_path)
        self.logger.info(f"Directory ensured: {directory_path}")

    def list_files(self, directory_path: str, extensions: Optional[tuple] = None) -> list:
        if not extensions:
            self.logger.info(f"Listing all files in {directory_path}")
        else:
            self.logger.info(f"Listing files in {directory_path} with extensions: {extensions}")
        return self.file_utility.list_files_in_directory(directory_path, extensions)

    def sanitize_filename(self, filename: str) -> str:
        sanitized = self.file_utility.sanitize_filename_safe(filename)
        self.logger.info(f"Sanitized filename: {filename} -> {sanitized}")
        return sanitized

    # Implement placeholders for cloud operations
    def upload_file(self, local_path: str, cloud_path: str):
        self.logger.info(f"Attempting to upload file from {local_path} to {cloud_path}")
        raise NotImplementedError("Cloud upload is not implemented.")

    def download_file(self, cloud_path: str, local_path: str):
        self.logger.info(f"Attempting to download file from {cloud_path} to {local_path}")
        raise NotImplementedError("Cloud download is not implemented.")

    def list_cloud_files(self, cloud_path: str):
        self.logger.info(f"Attempting to list files in cloud path: {cloud_path}")
        raise NotImplementedError("Cloud file listing is not implemented.")

    def delete_cloud_file(self, cloud_path: str):
        self.logger.info(f"Attempting to delete file in cloud path: {cloud_path}")
        raise NotImplementedError("Cloud file deletion is not implemented.")

    def log_operation(self, operation: str, details: dict):
        self.logger.info(f"Operation: {operation}", **details)
