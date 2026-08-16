from types import SimpleNamespace

from echoflow.transcription.backend import FasterWhisperSession
from echoflow.transcription.models import CpuEngineConfiguration


def configuration(tmp_path, *, language=None):
    return CpuEngineConfiguration(
        engine="faster-whisper",
        model="tiny",
        device="cpu",
        compute_type="int8",
        cpu_threads=2,
        beam_size=1,
        language=language,
        model_cache_path=tmp_path / "models",
    )


def test_session_detects_language_once_then_reuses_it_for_later_segments(tmp_path):
    calls = []

    class Model:
        def transcribe(self, path, **kwargs):
            calls.append((path, kwargs["language"]))
            return iter(()), SimpleNamespace(
                language="en", language_probability=0.99
            )

    session = FasterWhisperSession(
        model=Model(),
        configuration=configuration(tmp_path),
        engine_version="1.2.1",
    )

    first = session.transcribe(tmp_path / "audio-000000.wav")
    second = session.transcribe(tmp_path / "audio-000001.wav")

    assert calls == [
        (str(tmp_path / "audio-000000.wav"), None),
        (str(tmp_path / "audio-000001.wav"), "en"),
    ]
    assert first.language == second.language == "en"


def test_explicit_language_is_never_replaced_by_detected_metadata(tmp_path):
    calls = []

    class Model:
        def transcribe(self, _path, **kwargs):
            calls.append(kwargs["language"])
            return iter(()), SimpleNamespace(
                language="fr", language_probability=0.99
            )

    session = FasterWhisperSession(
        model=Model(),
        configuration=configuration(tmp_path, language="en"),
        engine_version="1.2.1",
    )

    session.transcribe(tmp_path / "audio-000000.wav")
    session.transcribe(tmp_path / "audio-000001.wav")

    assert calls == ["en", "en"]
