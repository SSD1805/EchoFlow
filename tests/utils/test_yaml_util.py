# tests/utils/test_yaml_util.py

import pytest
from src.utils.yaml_util import YAMLUtility
from pydantic import BaseModel


class TestSchema(BaseModel):
    key1: str
    key2: int


@pytest.fixture
def temp_yaml_file(tmp_path):
    """Fixture for creating a temporary YAML file."""
    return tmp_path / "test.yaml"


def test_read_yaml_valid(temp_yaml_file):
    """Test reading a valid YAML file."""
    content = {"key1": "value1", "key2": "value2"}
    YAMLUtility.write_yaml(content, temp_yaml_file)

    data = YAMLUtility.read_yaml(temp_yaml_file)
    assert data == content


def test_read_yaml_invalid(temp_yaml_file):
    """Test reading an invalid YAML file."""
    temp_yaml_file.write_text("{invalid: yaml")

    with pytest.raises(ValueError, match="Error reading YAML file"):
        YAMLUtility.read_yaml(temp_yaml_file)


def test_write_yaml_valid(temp_yaml_file):
    """Test writing valid YAML data."""
    content = {"key1": "value1", "key2": "value2"}
    YAMLUtility.write_yaml(content, temp_yaml_file)

    with open(temp_yaml_file, "r", encoding="utf-8") as file:
        assert file.read().strip() == "key1: value1\nkey2: value2"


def test_write_yaml_invalid(temp_yaml_file):
    """Test writing invalid data."""
    with pytest.raises(ValueError, match="Data to write must be a dictionary"):
        YAMLUtility.write_yaml("invalid_data", temp_yaml_file)


def test_validate_with_pydantic_valid():
    """Test validating YAML data using a Pydantic schema."""
    data = {"key1": "value1", "key2": 42}
    assert YAMLUtility.validate_with_pydantic(data, TestSchema)


def test_validate_with_pydantic_invalid():
    """Test validation with a Pydantic schema for invalid data."""
    data = {"key1": "value1", "key2": "not_an_int"}

    with pytest.raises(ValueError, match="Validation error:"):
        YAMLUtility.validate_with_pydantic(data, TestSchema)


@pytest.mark.skip(reason="Future feature: JSON Schema validation not implemented yet")
def test_validate_with_json_schema_placeholder():
    """Test placeholder for JSON Schema validation."""
    data = {"key1": "value1", "key2": 42}
    schema = {"type": "object", "properties": {"key1": {"type": "string"}, "key2": {"type": "integer"}}}

    with pytest.raises(NotImplementedError):
        YAMLUtility.validate_with_json_schema(data, schema)


@pytest.mark.skip(reason="Future feature: Encrypted YAML reading not implemented yet")
def test_read_encrypted_yaml_placeholder(temp_yaml_file):
    """Test placeholder for reading encrypted YAML files."""
    with pytest.raises(NotImplementedError):
        YAMLUtility.read_encrypted_yaml(temp_yaml_file, "encryption_key")


@pytest.mark.skip(reason="Future feature: Encrypted YAML writing not implemented yet")
def test_write_encrypted_yaml_placeholder(temp_yaml_file):
    """Test placeholder for writing encrypted YAML files."""
    data = {"key1": "value1", "key2": 42}
    with pytest.raises(NotImplementedError):
        YAMLUtility.write_encrypted_yaml(data, temp_yaml_file, "encryption_key")


@pytest.mark.skip(reason="Future feature: Encrypted YAML writing not implemented yet")
def test_write_encrypted_yaml_placeholder(temp_yaml_file):
    """Test placeholder for writing encrypted YAML files."""
    data = {"key1": "value1", "key2": 42}
    with pytest.raises(NotImplementedError):
        YAMLUtility.write_encrypted_yaml(data, temp_yaml_file, "encryption_key")
