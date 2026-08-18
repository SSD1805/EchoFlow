import multiprocessing
import os
import shutil
import wave
from pathlib import Path

import pytest
from dependency_injector import providers

from echoflow.app.app_container import AppContainer
from echoflow.core.config import AppConfig
from echoflow.runner.models import ProcessingProfile
from echoflow.transcription.alignment import AlignedRecognizedSegment, AlignedWord
from echoflow.transcription.models import AudioSegmentWindow, EngineTranscript
from echoflow.workspace.models import JobId

_EXIT_AFTER_CHECKPOINT = 73
_JOB_ID = JobId("crash-acceptance")
_WINDOW = AudioSegmentWindow(0, 0, 16_000, 16_000)


class _ManagedModelRegistry:
    def resolved_revision(self, model_id: str) -> str:
        assert model_id == "tiny"
        return "revision-1"


def _config(root: Path) -> AppConfig:
    return AppConfig(
        APP_ENV="test",
        DEBUG=False,
        LOG_LEVEL="INFO",
        STATE_DIR=root / "state",
        CACHE_DIR=root / "cache",
        MODEL_DIR=root / "cache" / "models",
        OUTPUT_DIR=root / "output",
        MIN_FREE_DISK_BYTES=0,
        WARN_FREE_DISK_BYTES=0,
        FFMPEG_TIMEOUT_SECONDS=2.0,
        FFPROBE_TIMEOUT_SECONDS=10.0,
        FFMPEG_PROCESS_TIMEOUT_SECONDS=30.0,
        _env_file=None,
    )


def _make_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16_000)
        output.writeframes(b"\x00\x00" * 16_000)


def _container(root: Path) -> AppContainer:
    container = AppContainer()
    container.config.override(_config(root))
    container.model_manager.override(providers.Object(_ManagedModelRegistry()))
    return container


def _crash_after_checkpoint(root_text: str) -> None:
    root = Path(root_text)
    source = root / "source.wav"
    container = _container(root)
    planner = container.transcription_planner()
    plan = planner.plan(
        source,
        profile=ProcessingProfile.SCREENING,
        job_id=_JOB_ID,
    )
    job = container.workspace_service().create_job(
        source,
        output_dir=_config(root).OUTPUT_DIR,
        job_id=_JOB_ID,
    )
    windows = (_WINDOW,)
    store = container.checkpoint_store()
    store.initialize(job, plan, windows)
    store.save_segment(
        job,
        plan,
        windows,
        _WINDOW,
        EngineTranscript(
            segments=(
                AlignedRecognizedSegment(
                    index=0,
                    start_seconds=0.0,
                    end_seconds=1.0,
                    text="Durable checkpoint.",
                    words=(
                        AlignedWord(
                            start_seconds=0.0,
                            end_seconds=1.0,
                            text=" Durable checkpoint.",
                            probability=0.99,
                        ),
                    ),
                ),
            ),
            language="en",
            language_probability=1.0,
            engine_version="crash-acceptance-engine",
        ),
    )
    os._exit(_EXIT_AFTER_CHECKPOINT)


def test_completed_checkpoint_survives_unceremonious_process_exit(tmp_path):
    if shutil.which("ffprobe") is None:
        pytest.skip("ffprobe is not installed")

    source = tmp_path / "source.wav"
    _make_wav(source)

    process = multiprocessing.get_context("spawn").Process(
        target=_crash_after_checkpoint,
        args=(str(tmp_path),),
    )
    process.start()
    process.join(timeout=30)
    if process.is_alive():
        process.terminate()
        process.join(timeout=5)
        pytest.fail("checkpoint crash worker did not exit")

    assert process.exitcode == _EXIT_AFTER_CHECKPOINT

    container = _container(tmp_path)
    plan = container.transcription_planner().plan_resume(source, job_id=_JOB_ID)
    restored = container.checkpoint_store().restore(plan.job, plan, (_WINDOW,))

    assert len(restored.completed) == 1
    window, transcript = restored.completed[0]
    assert window == _WINDOW
    assert transcript.segments[0].text == "Durable checkpoint."
    assert transcript.segments[0].to_dict()["words"] == [
        {
            "start_seconds": 0.0,
            "end_seconds": 1.0,
            "text": " Durable checkpoint.",
            "probability": 0.99,
            "speaker_ref": None,
        }
    ]
    assert transcript.language == "en"
    assert restored.engine_version == "crash-acceptance-engine"

    checkpoint = plan.job.workspace_dir / "checkpoints" / "audio-000000.json"
    assert checkpoint.is_file()
    assert source.is_file()
