import io
import json
import logging

import pytest

from scholion.core.ilogger import ILogger
from scholion.core.logger import configure_logging, reset_logging


@pytest.fixture(autouse=True)
def isolated_logging():
    reset_logging()
    yield
    reset_logging()


def test_development_logger_emits_event_and_structured_context():
    stream = io.StringIO()
    logger = configure_logging("INFO", "development", stream)
    logger.bind(job_id="abc").info("job.started", input_count=2)
    rendered = stream.getvalue()
    assert "job.started" in rendered
    assert "job_id" in rendered
    assert "abc" in rendered
    assert "input_count" in rendered


def test_production_logger_emits_parseable_json():
    stream = io.StringIO()
    logger = configure_logging("INFO", "production", stream)
    logger.error("job.failed", error_code="storage_error")
    event = json.loads(stream.getvalue())
    assert event["event"] == "job.failed"
    assert event["error_code"] == "storage_error"
    assert event["level"] == "error"


def test_log_level_filters_lower_severity_events():
    stream = io.StringIO()
    logger = configure_logging("WARNING", "production", stream)
    logger.info("hidden")
    logger.warning("visible")
    assert "hidden" not in stream.getvalue()
    assert "visible" in stream.getvalue()


def test_exception_logging_keeps_structured_traceback():
    stream = io.StringIO()
    logger = configure_logging("INFO", "production", stream)
    try:
        raise ValueError("decoder failed")
    except ValueError:
        logger.error("transcription.failed", exc_info=True)
    event = json.loads(stream.getvalue())
    assert event["event"] == "transcription.failed"
    assert "ValueError" in event["exception"]
    assert "decoder failed" in event["exception"]


def test_newline_in_event_remains_one_json_record():
    stream = io.StringIO()
    logger = configure_logging("INFO", "production", stream)
    logger.info("first line\nsecond line")
    records = stream.getvalue().splitlines()
    assert len(records) == 1
    assert json.loads(records[0])["event"] == "first line\nsecond line"


def test_invalid_log_level_fails_before_logger_is_returned():
    with pytest.raises(ValueError, match="Invalid LOG_LEVEL"):
        configure_logging("verbose", "development")


def test_configured_logger_satisfies_application_protocol():
    logger = configure_logging("INFO", "production", io.StringIO())
    assert isinstance(logger, ILogger)


def test_default_log_stream_does_not_contaminate_standard_output(capsys):
    logger = configure_logging("INFO", "development")
    logger.info("workspace.initialized")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "workspace.initialized" in captured.err


def test_bound_context_is_publicly_available_without_structlog_private_state():
    logger = configure_logging("INFO", "production", io.StringIO())
    bound = logger.bind(job_id="abc", profile="screening")
    assert bound.context == {"job_id": "abc", "profile": "screening"}
    assert logger.context == {}


def test_configuring_scholion_does_not_replace_host_root_handlers():
    root = logging.getLogger()
    host_handler = logging.StreamHandler(io.StringIO())
    root.addHandler(host_handler)
    try:
        configure_logging("INFO", "production", io.StringIO())
        assert host_handler in root.handlers
    finally:
        root.removeHandler(host_handler)
