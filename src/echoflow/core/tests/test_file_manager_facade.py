from contextlib import contextmanager
from unittest.mock import Mock

import pytest

from echoflow.core.errors import StorageNotFoundError
from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.core.performance_tracker import PerformanceTracker
from echoflow.interfaces.local_file_manager import LocalFileManager


@pytest.fixture
def logger():
    return Mock()


@pytest.fixture
def facade(logger):
    return FileManagerFacade(LocalFileManager(), logger, PerformanceTracker())


def test_real_facade_round_trip_has_one_application_success_event(
    facade, logger, tmp_path
):
    path = tmp_path / "audio.bin"
    facade.save_file(b"audio", path)
    assert facade.file_exists(path)
    assert path.read_bytes() == b"audio"
    save_events = [
        call
        for call in logger.info.call_args_list
        if call.kwargs.get("operation") == "save_file"
    ]
    assert len(save_events) == 1
    assert save_events[0].args == ("File operation completed",)
    assert save_events[0].kwargs["duration_seconds"] >= 0


def test_failure_is_timed_logged_once_and_re_raised_without_success(
    facade, logger, tmp_path
):
    missing = tmp_path / "missing.bin"
    with pytest.raises(StorageNotFoundError):
        facade.get_file_metadata(missing)
    assert facade.tracker.get_metric("get_file_metadata") is not None
    logger.error.assert_called_once()
    assert logger.error.call_args.kwargs["error_code"] == "storage_not_found"
    assert logger.error.call_args.kwargs["exc_info"] is True
    assert not logger.info.called


def test_copy_preserves_source_destination_argument_order(logger):
    storage = Mock()
    tracker = PerformanceTracker()
    facade = FileManagerFacade(storage, logger, tracker)
    facade.copy_file("source.wav", "destination.wav")
    storage.copy_file.assert_called_once_with("source.wav", "destination.wav")


def test_reservations_reach_storage_once(logger):
    storage = Mock()
    facade = FileManagerFacade(storage, logger, PerformanceTracker())
    facade.reserve_directory("jobs/job-1")
    facade.reserve_file("output/transcript.json")
    storage.reserve_directory.assert_called_once_with("jobs/job-1")
    storage.reserve_file.assert_called_once_with("output/transcript.json")


def test_tracker_context_sees_exception():
    class RecordingTracker:
        def __init__(self):
            self.exception_type = None

        @contextmanager
        def track_execution(self, _operation):
            try:
                yield
            except Exception as exc:
                self.exception_type = type(exc)
                raise

        def get_metric(self, _operation):
            return 0.0

    storage = Mock()
    storage.delete_file.side_effect = StorageNotFoundError("delete", "missing")
    tracker = RecordingTracker()
    facade = FileManagerFacade(storage, Mock(), tracker)
    with pytest.raises(StorageNotFoundError):
        facade.delete_file("missing")
    assert tracker.exception_type is StorageNotFoundError
