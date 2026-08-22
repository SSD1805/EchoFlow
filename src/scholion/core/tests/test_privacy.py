from pathlib import Path

from scholion.core.privacy import PathDisclosure, path_log_context


def test_path_disclosure_wire_values_are_stable():
    assert [policy.value for policy in PathDisclosure] == ["redact", "full"]


def test_redaction_omits_every_path_field():
    assert (
        path_log_context(
            PathDisclosure.REDACT,
            path=Path("participant-004.wav"),
            destination="study-name/transcript.txt",
        )
        == {}
    )


def test_full_disclosure_is_explicit_and_stringifies_paths():
    assert path_log_context(
        PathDisclosure.FULL,
        path=Path("recording.wav"),
        destination=Path("transcript.txt"),
    ) == {"path": "recording.wav", "destination": "transcript.txt"}
