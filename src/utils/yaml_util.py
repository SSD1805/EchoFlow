# src/utils/yaml_util.py

import yaml
from yaml.parser import ParserError
from yaml.scanner import ScannerError
from typing import Any, Optional, Type
from pydantic import BaseModel, ValidationError


class YAMLUtility:
    """
    A utility class for YAML file operations with hooks for future extensions.
    """

    @staticmethod
    def read_yaml(file_path: str) -> Optional[dict]:
        """
        Reads a YAML file and returns its contents as a dictionary.

        Args:
            file_path (str): Path to the YAML file.

        Returns:
            dict: Parsed contents of the YAML file.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file content is invalid YAML.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                data = yaml.safe_load(file)
                if not isinstance(data, dict):
                    raise ValueError(f"Expected a dictionary in {file_path}, but got {type(data).__name__}.")
                return data
        except (FileNotFoundError, ParserError, ScannerError) as e:
            raise ValueError(f"Error reading YAML file '{file_path}': {e}")

    @staticmethod
    def write_yaml(data: dict, file_path: str):
        """
        Writes a dictionary to a YAML file.

        Args:
            data (dict): Data to write.
            file_path (str): Path to the YAML file.

        Raises:
            ValueError: If the data is not a dictionary.
            IOError: If the file could not be written.
        """
        if not isinstance(data, dict):
            raise ValueError("Data to write must be a dictionary.")
        try:
            with open(file_path, "w", encoding="utf-8") as file:
                yaml.safe_dump(data, file, default_flow_style=False, sort_keys=False)
        except IOError as e:
            raise IOError(f"Error writing YAML file '{file_path}': {e}")

    @staticmethod
    def validate_with_pydantic(data: dict, schema: Type[BaseModel]) -> bool:
        """
        Validates a YAML dictionary against a Pydantic model.

        Args:
            data (dict): YAML data to validate.
            schema (Type[BaseModel]): Pydantic model to validate against.

        Returns:
            bool: True if validation passes.

        Raises:
            ValidationError: If validation fails.
        """
        try:
            schema(**data)
            return True
        except ValidationError as e:
            raise ValueError(f"Validation error: {e}")

    # Placeholder for JSON Schema validation
    @staticmethod
    def validate_with_json_schema(data: dict, schema: dict) -> bool:
        """
        Validates a YAML dictionary against a JSON schema.

        Args:
            data (dict): YAML data to validate.
            schema (dict): JSON schema.

        Returns:
            bool: True if validation passes.

        Raises:
            ValueError: If validation fails.
        """
        # Future: Use a library like `jsonschema` for validation
        raise NotImplementedError("JSON Schema validation is not yet implemented.")

    # Placeholder for encrypted YAML handling
    @staticmethod
    def read_encrypted_yaml(file_path: str, decryption_key: str) -> dict:
        """
        Reads and decrypts a YAML file.

        Args:
            file_path (str): Path to the encrypted YAML file.
            decryption_key (str): Key to decrypt the file.

        Returns:
            dict: Decrypted YAML data.

        Raises:
            NotImplementedError: Placeholder for future functionality.
        """
        # Future: Implement encrypted YAML reading (e.g., using Fernet or AES)
        raise NotImplementedError("Encrypted YAML reading is not yet implemented.")

    @staticmethod
    def write_encrypted_yaml(data: dict, file_path: str, encryption_key: str):
        """
        Encrypts and writes a dictionary to a YAML file.

        Args:
            data (dict): Data to encrypt and write.
            file_path (str): Path to the YAML file.
            encryption_key (str): Key to encrypt the file.

        Raises:
            NotImplementedError: Placeholder for future functionality.
        """
        # Future: Implement encrypted YAML writing
        raise NotImplementedError("Encrypted YAML writing is not yet implemented.")

    # Placeholder for extended validation rules
    @staticmethod
    def validate_custom_rules(data: dict, rules: dict) -> bool:
        """
        Validates a YAML dictionary against custom rules.

        Args:
            data (dict): YAML data to validate.
            rules (dict): Custom rules for validation.

        Returns:
            bool: True if validation passes.

        Raises:
            ValueError: If validation fails.
        """
        # Future: Implement custom validation rules logic
        raise NotImplementedError("Custom rule validation is not yet implemented.")
