import pytest

from echoflow.core.measurements import MeasurementRecorder, NoOpExecutionObserver


class StepClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        self.value += 1.0
        return self.value


def test_noop_observer_preserves_execution_and_accepts_values():
    observer = NoOpExecutionObserver()
    with observer.span("decode"):
        observer.record_value("segments.total", 2)


def test_recorder_aggregates_repeated_stages_and_latest_values():
    recorder = MeasurementRecorder(clock=StepClock())

    with recorder.span("segment.transcribe"):
        pass
    with recorder.span("segment.transcribe"):
        recorder.record_value("segments.completed", 2)

    stage = recorder.stages()[0]
    assert stage.name == "segment.transcribe"
    assert stage.count == 2
    assert stage.failed_count == 0
    assert stage.total_seconds == 2.0
    assert stage.max_seconds == 1.0
    assert recorder.values() == {"segments.completed": 2}


def test_recorder_marks_failed_span_without_swallowing_exception():
    recorder = MeasurementRecorder(clock=StepClock())

    with pytest.raises(RuntimeError, match="boom"):
        with recorder.span("engine.open"):
            raise RuntimeError("boom")

    stage = recorder.stages()[0]
    assert stage.count == 1
    assert stage.failed_count == 1
    assert stage.total_seconds == 1.0
