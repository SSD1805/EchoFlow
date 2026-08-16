from dataclasses import FrozenInstanceError

import pytest

from echoflow.transcription.models import AudioSegmentWindow, SegmentationConfiguration


def test_segmentation_defaults_are_versioned_sequential_and_json_safe():
    configuration = SegmentationConfiguration()
    assert configuration.to_dict() == {
        "schema_version": 1,
        "segment_duration_seconds": 600,
        "overlap_seconds": 0,
        "concurrency": 1,
    }
    assert not hasattr(configuration, "__dict__")
    with pytest.raises(FrozenInstanceError):
        configuration.concurrency = 2


def test_segmentation_duration_lower_boundary_is_valid():
    assert (
        SegmentationConfiguration(segment_duration_seconds=1).segment_duration_seconds
        == 1
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {"segment_duration_seconds": 0},
            "segment_duration_seconds must be positive",
        ),
        (
            {"overlap_seconds": 1},
            "segmentation overlap is not supported by schema version 1",
        ),
        (
            {"concurrency": 0},
            "segmentation concurrency must be one for schema version 1",
        ),
        (
            {"concurrency": 2},
            "segmentation concurrency must be one for schema version 1",
        ),
        (
            {"schema_version": 2},
            "unsupported segmentation schema version",
        ),
    ],
)
def test_segmentation_configuration_rejects_unsupported_values(kwargs, message):
    with pytest.raises(ValueError, match=f"^{message}$"):
        SegmentationConfiguration(**kwargs)


def test_audio_segment_window_has_stable_frame_identity_and_seconds():
    window = AudioSegmentWindow(7, 16_000, 40_000, 16_000)
    assert window.segment_id == "audio-000007"
    assert window.start_seconds == 1.0
    assert window.end_seconds == 2.5
    assert window.duration_seconds == 1.5
    assert window.to_dict() == {
        "segment_id": "audio-000007",
        "index": 7,
        "start_frame": 16_000,
        "end_frame": 40_000,
        "sample_rate_hz": 16_000,
        "start_seconds": 1.0,
        "end_seconds": 2.5,
    }
    assert not hasattr(window, "__dict__")


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ((-1, 0, 1, 1), "audio segment index cannot be negative"),
        ((0, -1, 1, 1), "audio segment start_frame cannot be negative"),
        (
            (0, 1, 1, 1),
            "audio segment end_frame must be greater than start_frame",
        ),
        (
            (0, 2, 1, 1),
            "audio segment end_frame must be greater than start_frame",
        ),
        ((0, 0, 1, 0), "audio segment sample_rate_hz must be positive"),
    ],
)
def test_audio_segment_window_rejects_invalid_boundaries(args, message):
    with pytest.raises(ValueError, match=f"^{message}$"):
        AudioSegmentWindow(*args)
