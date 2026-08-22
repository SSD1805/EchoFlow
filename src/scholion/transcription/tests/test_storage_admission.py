from unittest.mock import Mock

import pytest

from scholion.transcription.errors import ResourceAdmissionError
from scholion.transcription.storage import StorageAdmissionPolicy, StorageAllocation
from scholion.transcription.tests.test_executor import executor, plan


def test_executor_admits_known_job_storage_before_workspace_claim(tmp_path) -> None:
    planned, paths = plan(tmp_path)
    service, probe, _, decoder, *_ = executor(tmp_path, planned, paths)
    admission = Mock(spec=StorageAdmissionPolicy)
    service.storage_admission = admission

    service.execute(planned)

    admission.admit.assert_called_once_with(
        (
            StorageAllocation(
                planned.job.workspace_dir,
                planned.resources.private_workspace_bytes,
            ),
            StorageAllocation(
                planned.job.output_dir,
                planned.resources.public_output_bytes,
            ),
        )
    )
    probe.probe.assert_called_once_with(planned.job.input_path)
    decoder.decode.assert_called_once()


def test_storage_rejection_happens_before_workspace_or_decode(tmp_path) -> None:
    planned, paths = plan(tmp_path)
    service, probe, _, decoder, segmenter, transcriber, *_ = executor(
        tmp_path, planned, paths
    )
    admission = Mock(spec=StorageAdmissionPolicy)
    admission.admit.side_effect = ResourceAdmissionError(
        "Available disk space is below the planned job allocation"
    )
    service.storage_admission = admission

    with pytest.raises(
        ResourceAdmissionError,
        match="^Available disk space is below the planned job allocation$",
    ):
        service.execute(planned)

    probe.probe.assert_called_once_with(planned.job.input_path)
    assert not paths.state_dir.exists()
    assert not paths.output_dir.exists()
    decoder.decode.assert_not_called()
    segmenter.plan.assert_not_called()
    transcriber.open_session.assert_not_called()
