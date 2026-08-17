from types import SimpleNamespace

import pytest

from echoflow.transcription.backend import FasterWhisperSession
from echoflow.transcription.models import AutoLanguageMode, CpuEngineConfiguration


def configuration(
    tmp_path,
    *,
    language=None,
    auto_language_mode=AutoLanguageMode.JOB_LATCHED,
):
    return CpuEngineConfiguration(
        engine="faster-whisper",
        model="tiny",
        device="cpu",
        compute_type="int8",
        cpu_threads=2,
        beam_size=1,
        language=language,
        model_cache_path=tmp_path / "models",
        auto_language_mode=auto_language_mode,
    )


def test_legacy_session_detects_language_once_then_reuses_it_for_later_segments(
    tmp_path,
):
    calls = []

    class Model:
        def transcribe(self, path, **kwargs):
            calls.append((path, kwargs["language"]))
            return iter(()), SimpleNamespace(language="en", language_probability=0.99)

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


def test_per_segment_session_redetects_language_for_each_work_unit(tmp_path):
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
                (kwargs["language"], kwargs["multilingual"], kwargs["chunk_length"])
            )
            return iter(()), next(infos)

    session = FasterWhisperSession(
        model=Model(),
        configuration=configuration(
            tmp_path,
            auto_language_mode=AutoLanguageMode.NATIVE_MULTILINGUAL,
        ),
        engine_version="1.2.1",
    )

    first = session.transcribe(tmp_path / "audio-000000.wav")
    second = session.transcribe(tmp_path / "audio-000001.wav")

    assert calls == [(None, True, 10), (None, True, 10)]
    assert first.language == "en"
    assert second.language == "fr"


def test_resumed_detected_language_is_used_for_first_remaining_legacy_segment(tmp_path):
    calls = []

    class Model:
        def transcribe(self, _path, **kwargs):
            calls.append(kwargs["language"])
            return iter(()), SimpleNamespace(language="de", language_probability=0.98)

    session = FasterWhisperSession(
        model=Model(),
        configuration=configuration(tmp_path),
        engine_version="1.2.1",
        detected_language="de",
    )

    session.transcribe(tmp_path / "audio-000004.wav")

    assert calls == ["de"]


def test_per_segment_session_rejects_resume_language_seed(tmp_path):
    with pytest.raises(
        ValueError,
        match="^detected_language cannot seed a per-segment language session$",
    ):
        FasterWhisperSession(
            model=object(),
            configuration=configuration(
                tmp_path,
                auto_language_mode=AutoLanguageMode.NATIVE_MULTILINGUAL,
            ),
            engine_version="1.2.1",
            detected_language="de",
        )


def test_explicit_language_is_never_replaced_by_detected_metadata(tmp_path):
    calls = []

    class Model:
        def transcribe(self, _path, **kwargs):
            calls.append(kwargs["language"])
            return iter(()), SimpleNamespace(language="fr", language_probability=0.99)

    session = FasterWhisperSession(
        model=Model(),
        configuration=configuration(tmp_path, language="en"),
        engine_version="1.2.1",
        detected_language="de",
    )

    session.transcribe(tmp_path / "audio-000000.wav")
    session.transcribe(tmp_path / "audio-000001.wav")

    assert calls == ["en", "en"]


def test_empty_resumed_language_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="^detected_language cannot be empty$"):
        FasterWhisperSession(
            model=object(),
            configuration=configuration(tmp_path),
            engine_version="1.2.1",
            detected_language=" ",
        )
