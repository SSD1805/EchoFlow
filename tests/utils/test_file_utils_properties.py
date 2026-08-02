from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given
from hypothesis import strategies as st

from src.utils.file_utils import LocalFileUtility


@given(content=st.binary(max_size=4096))
def test_safe_write_round_trips_arbitrary_bytes(content):
    with TemporaryDirectory() as directory:
        destination = Path(directory) / "payload.bin"

        LocalFileUtility().safe_write(content, str(destination))

        assert destination.read_bytes() == content


@given(filename=st.text(max_size=128))
def test_sanitized_filenames_contain_only_supported_characters(filename):
    sanitized = LocalFileUtility().sanitize_filename_safe(filename)

    assert len(sanitized) == len(filename)
    assert all(character.isalnum() or character in " ._-()" for character in sanitized)
