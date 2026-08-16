from importlib import metadata
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from echoflow.transcription.backend import FasterWhisperTranscriber
from echoflow.transcription.errors import (
    ModelUnavailableError,
    TranscriptionDependencyError,
    TranscriptionError,
)
from echoflow.transcription.models import CpuEngineConfiguration


def configuration(tmp_path, *, revision=None):
    return CpuEngineConfiguration(
        engine="faster-whisper",
        model="tiny",
        device="cpu",
        compute_type="int8",
        cpu_threads=2,
        beam_size=1,
        language=None,
        model_cache_path=tmp_path / "models/faster-whisper",
        model_revision=revision,
    )


def segment(start=0.0, end=1.0, text=" hello ", avg=-0.2, no_speech=0.1):
    return SimpleNamespace(
        start=start,
        end=end,
        text=text,
        avg_logprob=avg,
        no_speech_prob=no_speech,
    )


def backend(model_class, *, version_reader=lambda _name: "1.2.1"):
    module = SimpleNamespace(WhisperModel=model_class)
    return FasterWhisperTranscriber(
        module_loader=lambda name: module,
        version_reader=version_reader,
    )


def transcribe_once(transcriber, path, config, *, allowed=False):
    session = transcriber.open_session(config, allow_model_download=allowed)
    return session.transcribe(path)


def test_local_cpu_session_uses_exact_plan_and_consumes_generator(tmp_path):
    calls = []

    class Model:
        def __init__(self, model, **kwargs):
            calls.append((model, kwargs))

        def transcribe(self, path, **kwargs):
            calls.append((path, kwargs))

            def generated():
                calls.append("iterated")
                yield segment()
                yield segment(1.0, 1.5, "   ")
                yield segment(1.5, 2.0, "world", -0.4, 0.2)

            return generated(), SimpleNamespace(
                language=" en ", language_probability="0.95"
            )

    config = configuration(tmp_path, revision="immutable-revision")
    transcriber = backend(Model)
    session = transcriber.open_session(config, allow_model_download=False)
    result = session.transcribe(tmp_path / "audio.wav")

    assert calls[0] == (
        "tiny",
        {
            "device": "cpu",
            "compute_type": "int8",
            "cpu_threads": 2,
            "num_workers": 1,
            "download_root": str(config.model_cache_path),
            "local_files_only": True,
            "revision": "immutable-revision",
        },
    )
    assert calls[1] == (
        str(tmp_path / "audio.wav"),
        {
            "beam_size": 1,
            "language": None,
            "word_timestamps": False,
            "vad_filter": False,
            "log_progress": False,
        },
    )
    assert calls[2] == "iterated"
    assert [item.text for item in result.segments] == ["hello", "world"]
    assert [item.index for item in result.segments] == [0, 1]
    assert result.segments[0].average_log_probability == -0.2
    assert result.segments[1].no_speech_probability == 0.2
    assert result.language == "en"
    assert result.language_probability == 0.95
    assert result.engine_version == "1.2.1"


def test_one_loaded_model_is_reused_for_multiple_audio_segments(tmp_path):
    model = Mock()
    model.transcribe.return_value = (
        iter(()),
        SimpleNamespace(language="en", language_probability=1.0),
    )
    factory = Mock(return_value=model)
    transcriber = backend(factory)

    session = transcriber.open_session(
        configuration(tmp_path), allow_model_download=False
    )
    first = session.transcribe(tmp_path / "audio-000000.wav")
    second = session.transcribe(tmp_path / "audio-000001.wav")

    factory.assert_called_once()
    assert model.transcribe.call_count == 2
    assert first.engine_version == second.engine_version == "1.2.1"


def test_explicit_download_authorization_disables_local_only_mode(tmp_path):
    model = Mock()
    model.transcribe.return_value = (
        iter(()),
        SimpleNamespace(language=None, language_probability=None),
    )
    factory = Mock(return_value=model)
    result = transcribe_once(
        backend(factory),
        tmp_path / "audio.wav",
        configuration(tmp_path),
        allowed=True,
    )
    assert factory.call_args.kwargs["local_files_only"] is False
    assert result.segments == ()
    assert result.language is None


@pytest.mark.parametrize(
    "failure",
    [ModuleNotFoundError("faster_whisper"), ImportError("native dependency")],
)
def test_missing_optional_engine_dependency_has_install_instruction(tmp_path, failure):
    transcriber = FasterWhisperTranscriber(
        module_loader=Mock(side_effect=failure), version_reader=Mock()
    )
    with pytest.raises(
        TranscriptionDependencyError,
        match="^CPU transcription support is not installed; install EchoFlow's transcription extra$",
    ):
        transcriber.open_session(
            configuration(tmp_path),
            allow_model_download=False,
        )


def test_missing_package_metadata_is_a_dependency_failure(tmp_path):
    transcriber = FasterWhisperTranscriber(
        module_loader=lambda _name: SimpleNamespace(),
        version_reader=Mock(side_effect=metadata.PackageNotFoundError("missing")),
    )
    with pytest.raises(TranscriptionDependencyError):
        transcriber.open_session(
            configuration(tmp_path),
            allow_model_download=False,
        )


@pytest.mark.parametrize(
    ("allowed", "error_type", "message"),
    [
        (
            False,
            ModelUnavailableError,
            "The selected model is not available locally",
        ),
        (
            True,
            TranscriptionError,
            "The selected model could not be downloaded or initialized",
        ),
    ],
)
def test_model_initialization_failure_reflects_download_authorization(
    tmp_path, allowed, error_type, message
):
    class Model:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("private hub detail")

    with pytest.raises(error_type, match=f"^{message}") as error:
        backend(Model).open_session(
            configuration(tmp_path),
            allow_model_download=allowed,
        )
    assert "private hub detail" not in str(error.value)


def test_engine_iteration_failure_is_redacted(tmp_path):
    class Model:
        def __init__(self, *_args, **_kwargs):
            pass

        def transcribe(self, *_args, **_kwargs):
            def generated():
                raise RuntimeError("sensitive decoder detail")
                yield

            return generated(), SimpleNamespace(language="en", language_probability=1.0)

    session = backend(Model).open_session(
        configuration(tmp_path), allow_model_download=False
    )
    with pytest.raises(
        TranscriptionError,
        match="^The transcription engine failed while processing audio$",
    ) as error:
        session.transcribe(tmp_path / "audio.wav")
    assert "sensitive decoder detail" not in str(error.value)


@pytest.mark.parametrize(
    "bad_segment",
    [
        SimpleNamespace(text="words", start="bad", end=1),
        SimpleNamespace(text="words", start=2, end=1),
    ],
)
def test_invalid_engine_segment_values_are_typed(tmp_path, bad_segment):
    class Model:
        def __init__(self, *_args, **_kwargs):
            pass

        def transcribe(self, *_args, **_kwargs):
            return iter((bad_segment,)), SimpleNamespace(
                language="en", language_probability=1.0
            )

    session = backend(Model).open_session(
        configuration(tmp_path), allow_model_download=False
    )
    with pytest.raises(
        TranscriptionError,
        match="^The transcription engine returned invalid segment data$",
    ):
        session.transcribe(tmp_path / "audio.wav")


def test_invalid_language_probability_is_typed_without_native_detail(tmp_path):
    class Model:
        def __init__(self, *_args, **_kwargs):
            pass

        def transcribe(self, *_args, **_kwargs):
            return iter(()), SimpleNamespace(
                language="en", language_probability="not-a-number"
            )

    session = backend(Model).open_session(
        configuration(tmp_path), allow_model_download=False
    )
    with pytest.raises(
        TranscriptionError,
        match="^The transcription engine returned invalid probability data$",
    ):
        session.transcribe(tmp_path / "audio.wav")


def test_keyboard_interrupt_is_not_wrapped_during_model_loading(tmp_path):
    class Model:
        def __init__(self, *_args, **_kwargs):
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        backend(Model).open_session(
            configuration(tmp_path),
            allow_model_download=False,
        )
