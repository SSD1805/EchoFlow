from unittest.mock import call

import pytest

from scholion.transcription.alignment import AlignedRecognizedSegment, AlignedWord
from scholion.transcription.checkpoint import LocalCheckpointStore
from scholion.transcription.errors import CheckpointError, TranscriptionError
from scholion.transcription.models import EngineTranscript
from scholion.transcription.tests.test_executor import executor, plan


def local_result(text, *, language="en", probability=0.98):
    return EngineTranscript(
        (
            AlignedRecognizedSegment(
                0,
                0.0,
                1.0,
                text,
                -0.2,
                0.1,
                words=(AlignedWord(0.0, 1.0, text, 0.9),),
            ),
        ),
        language,
        probability,
        "1.2.1",
    )


def _with_real_checkpoints(service):
    service.checkpoint_store = LocalCheckpointStore(service.file_manager)
    return service


def test_interrupted_job_resumes_from_completed_prefix_and_clears_checkpoints(tmp_path):
    planned, paths = plan(tmp_path)
    (
        service,
        _,
        _,
        _,
        segmenter,
        transcriber,
        session,
        logger,
        materialized,
    ) = executor(tmp_path, planned, paths)
    _with_real_checkpoints(service)
    session.transcribe.side_effect = (
        local_result("Hello"),
        TranscriptionError("simulated crash"),
    )

    with pytest.raises(TranscriptionError, match="^simulated crash$"):
        service.execute(planned)

    checkpoint_dir = planned.job.workspace_dir / "checkpoints"
    assert (checkpoint_dir / "manifest.json").is_file()
    assert (checkpoint_dir / "audio-000000.json").is_file()
    assert not (checkpoint_dir / "audio-000001.json").exists()
    assert not planned.artifact.path.exists()

    session.reset_mock()
    transcriber.reset_mock()
    segmenter.materialize.reset_mock()
    segmenter.cleanup.reset_mock()
    transcriber.open_session.return_value = session
    session.engine_version = "1.2.1"
    session.transcribe.side_effect = (local_result("world."),)
    segmenter.materialize.side_effect = (materialized[1],)

    resumed = service.execute(planned, resume=True)

    assert resumed.transcript.text == "Hello world."
    assert session.transcribe.call_args_list == [call(materialized[1].path)]
    assert segmenter.materialize.call_count == 1
    transcriber.open_session.assert_called_once_with(planned.engine)
    assert list(checkpoint_dir.iterdir()) == []
    log_text = " ".join(str(item) for item in logger.info.call_args_list)
    assert "transcription_resume_validated" in log_text
    assert str(planned.job.input_path) not in log_text
    assert "Hello" not in log_text
    assert "world" not in log_text


def test_fully_checkpointed_job_publishes_without_loading_model_again(tmp_path):
    planned, paths = plan(tmp_path)
    service, _, _, _, segmenter, transcriber, session, logger, _ = executor(
        tmp_path, planned, paths
    )
    store = LocalCheckpointStore(service.file_manager)
    service.checkpoint_store = store
    job = service.workspace_service.create_job(
        planned.job.input_path,
        output_dir=planned.job.output_dir,
        job_id=planned.job.job_id,
    )
    windows = segmenter.plan.return_value
    store.initialize(job, planned, windows)
    store.save_segment(job, planned, windows, windows[0], local_result("Hello"))
    store.save_segment(job, planned, windows, windows[1], local_result("world."))

    result = service.execute(planned, resume=True)

    assert result.transcript.text == "Hello world."
    transcriber.open_session.assert_not_called()
    session.transcribe.assert_not_called()
    segmenter.materialize.assert_not_called()
    assert list((job.workspace_dir / "checkpoints").iterdir()) == []
    log_text = " ".join(str(item) for item in logger.info.call_args_list)
    assert "transcription_resume_recognition_complete" in log_text


def test_resume_refuses_engine_version_change_before_new_segment_work(tmp_path):
    planned, paths = plan(tmp_path)
    service, _, _, _, segmenter, transcriber, session, _, materialized = executor(
        tmp_path, planned, paths
    )
    _with_real_checkpoints(service)
    session.transcribe.side_effect = (
        local_result("first"),
        TranscriptionError("stop"),
    )

    with pytest.raises(TranscriptionError, match="^stop$"):
        service.execute(planned)

    session.reset_mock()
    transcriber.reset_mock()
    segmenter.materialize.reset_mock()
    transcriber.open_session.return_value = session
    session.engine_version = "9.9.9"
    segmenter.materialize.side_effect = (materialized[1],)

    with pytest.raises(
        CheckpointError,
        match="^Installed transcription engine version does not match checkpoints$",
    ):
        service.execute(planned, resume=True)

    segmenter.materialize.assert_not_called()
    session.transcribe.assert_not_called()
    assert (planned.job.workspace_dir / "checkpoints" / "audio-000000.json").is_file()
