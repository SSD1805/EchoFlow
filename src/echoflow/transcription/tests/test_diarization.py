import os
from types import SimpleNamespace

import pytest

from echoflow.transcription.diarization import (
    PyannoteSpeakerDiarizer,
    project_speaker_refs,
)
from echoflow.transcription.errors import DiarizationModelUnavailableError
from echoflow.transcription.models import RecognizedSegment
from echoflow.transcription.speaker_models import (
    SpeakerDiarizationRequest,
    SpeakerTurn,
)


def _segment(
    index: int, start: float, end: float, text: str = "hello"
) -> RecognizedSegment:
    return RecognizedSegment(
        index=index, start_seconds=start, end_seconds=end, text=text
    )


def test_request_rejects_conflicting_exact_and_bounded_counts():
    with pytest.raises(ValueError, match="cannot be combined"):
        SpeakerDiarizationRequest(num_speakers=2, min_speakers=1)


def test_request_rejects_inverted_bounds():
    with pytest.raises(ValueError, match="cannot exceed"):
        SpeakerDiarizationRequest(min_speakers=4, max_speakers=2)


def test_cache_only_diarization_disables_telemetry_and_normalizes_labels(tmp_path):
    snapshot_calls = []
    pipeline_calls = []

    def snapshot_loader(**kwargs):
        snapshot_calls.append(kwargs)
        return str(tmp_path / "snapshot")

    class Pipeline:
        @classmethod
        def from_pretrained(cls, path):
            assert path == str(tmp_path / "snapshot")
            return cls()

        def __call__(self, path, **kwargs):
            pipeline_calls.append((path, kwargs))
            return SimpleNamespace(
                speaker_diarization=(
                    (SimpleNamespace(start=4.0, end=5.0), "B"),
                    (SimpleNamespace(start=0.0, end=2.0), "A"),
                    (SimpleNamespace(start=2.0, end=4.0), "B"),
                )
            )

    diarizer = PyannoteSpeakerDiarizer(
        model_cache_path=tmp_path / "models",
        model_revision="revision-1",
        snapshot_loader=snapshot_loader,
        module_loader=lambda name: SimpleNamespace(Pipeline=Pipeline),
        version_reader=lambda name: "4.0.0",
    )
    result = diarizer.diarize(
        tmp_path / "audio.wav",
        allow_model_download=False,
        request=SpeakerDiarizationRequest(num_speakers=2),
    )

    assert os.environ["PYANNOTE_METRICS_ENABLED"] == "0"
    assert snapshot_calls == [
        {
            "repo_id": "pyannote/speaker-diarization-community-1",
            "revision": "revision-1",
            "cache_dir": str((tmp_path / "models").resolve()),
            "local_files_only": True,
        }
    ]
    assert pipeline_calls == [(str(tmp_path / "audio.wav"), {"num_speakers": 2})]
    assert result.turns == (
        SpeakerTurn(0.0, 2.0, "speaker-01"),
        SpeakerTurn(2.0, 4.0, "speaker-02"),
        SpeakerTurn(4.0, 5.0, "speaker-02"),
    )
    assert result.provenance.provider == "pyannote.audio"
    assert result.provenance.telemetry_enabled is False


def test_authorized_acquisition_allows_snapshot_download(tmp_path):
    calls = []

    def snapshot_loader(**kwargs):
        calls.append(kwargs)
        return str(tmp_path / "snapshot")

    class Pipeline:
        @classmethod
        def from_pretrained(cls, _path):
            return cls()

        def __call__(self, _path, **_kwargs):
            return SimpleNamespace(speaker_diarization=())

    diarizer = PyannoteSpeakerDiarizer(
        model_cache_path=tmp_path,
        snapshot_loader=snapshot_loader,
        module_loader=lambda _name: SimpleNamespace(Pipeline=Pipeline),
        version_reader=lambda _name: "4.0.0",
    )
    diarizer.diarize(tmp_path / "audio.wav", allow_model_download=True)
    assert calls[0]["local_files_only"] is False


def test_missing_cached_model_fails_closed(tmp_path):
    def snapshot_loader(**_kwargs):
        raise FileNotFoundError("not cached")

    diarizer = PyannoteSpeakerDiarizer(
        model_cache_path=tmp_path,
        snapshot_loader=snapshot_loader,
    )
    with pytest.raises(DiarizationModelUnavailableError, match="local cache"):
        diarizer.diarize(tmp_path / "audio.wav", allow_model_download=False)


def test_projection_attaches_only_one_unambiguous_overlapping_speaker():
    segments = (
        _segment(0, 0.0, 2.0, "first"),
        _segment(1, 2.0, 5.0, "handoff"),
        _segment(2, 5.0, 7.0, "second"),
    )
    turns = (
        SpeakerTurn(0.0, 3.0, "speaker-01"),
        SpeakerTurn(3.0, 7.0, "speaker-02"),
    )

    projected = project_speaker_refs(segments, turns)
    assert [segment.speaker_ref for segment in projected] == [
        "speaker-01",
        None,
        "speaker-02",
    ]


def test_projection_keeps_overlap_ambiguous():
    segment = _segment(0, 0.0, 2.0)
    turns = (
        SpeakerTurn(0.0, 2.0, "speaker-01"),
        SpeakerTurn(1.0, 2.0, "speaker-02"),
    )
    assert project_speaker_refs((segment,), turns)[0].speaker_ref is None


def test_projection_refuses_to_overwrite_existing_speaker_metadata():
    segment = RecognizedSegment(
        index=0,
        start_seconds=0.0,
        end_seconds=1.0,
        text="hello",
        speaker_ref="speaker-old",
    )
    with pytest.raises(ValueError, match="refuses to overwrite"):
        project_speaker_refs((segment,), (SpeakerTurn(0.0, 1.0, "speaker-01"),))
