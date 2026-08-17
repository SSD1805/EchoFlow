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
        model_revision="managed-revision",
    )


def test_automatic_language_is_redetected_for_each_work_unit(tmp_path):
    calls = []
    infos = iter(
        (
            SimpleNamespace(language="en", language_probability=0.99),
            SimpleNamespace(language="fr", language_probability=0.98),
        )
    )

    class Model:
        def transcribe(self, _path, **kwargs):
            calls.append(
                (
                    kwargs["language"],
                    kwargs["multilingual"],
                    kwargs["chunk_length"],
                    kwargs["condition_on_previous_text"],
                )
            )
            return iter(()), next(infos)

    session = FasterWhisperSession(
        model=Model(),
        configuration=configuration(tmp_path),
        engine_version="1.2.1",
    )

    first = session.transcribe(tmp_path / "audio-000000.wav")
    second = session.transcribe(tmp_path / "audio-000001.wav")

    assert calls == [(None, True, 8, False), (None, True, 8, False)]
    assert first.language == "en"
    assert second.language == "fr"


def test_explicit_language_stays_fixed_across_work_units(tmp_path):
    calls = []

    class Model:
        def transcribe(self, _path, **kwargs):
            calls.append(
                (
                    kwargs["language"],
                    kwargs["multilingual"],
                    kwargs["chunk_length"],
                    kwargs["condition_on_previous_text"],
                )
            )
            return iter(()), SimpleNamespace(language="fr", language_probability=0.99)

    session = FasterWhisperSession(
        model=Model(),
        configuration=configuration(tmp_path, language="en"),
        engine_version="1.2.1",
    )

    session.transcribe(tmp_path / "audio-000000.wav")
    session.transcribe(tmp_path / "audio-000001.wav")

    assert calls == [("en", False, None, True), ("en", False, None, True)]
