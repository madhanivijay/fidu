import io
import json
import logging
import time

import pytest

from fidu.core.logging import (
    LOGGER_NAMESPACE,
    JsonFormatter,
    Timer,
    configure_logging,
    current_run_id,
    get_logger,
    new_run_id,
    reset_run_id,
)


@pytest.fixture(autouse=True)
def _reset_logger_state():
    reset_run_id()
    root = logging.getLogger(LOGGER_NAMESPACE)
    root.handlers = []
    yield
    reset_run_id()
    root.handlers = []


def test_json_formatter_emits_required_fields():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="enterprise_dq.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="hello",
        args=(),
        exc_info=None,
    )
    payload = json.loads(formatter.format(record))
    assert payload["level"] == "INFO"
    assert payload["logger"] == "enterprise_dq.test"
    assert payload["message"] == "hello"
    assert "timestamp" in payload


def test_json_formatter_merges_extras_and_run_id():
    new_run_id()
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="enterprise_dq.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="event",
        args=(),
        exc_info=None,
    )
    record.event = "rule_complete"
    record.dataset = "orders"
    record.duration_ms = 12.5
    payload = json.loads(formatter.format(record))
    assert payload["event"] == "rule_complete"
    assert payload["dataset"] == "orders"
    assert payload["duration_ms"] == 12.5
    assert payload["run_id"] == current_run_id()


def test_configure_logging_emits_json_to_stream():
    buf = io.StringIO()
    configure_logging(level="INFO", fmt="json", stream=buf)
    log = get_logger("test")
    log.info("hello", extra={"event": "smoke", "n": 1})
    line = buf.getvalue().strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["event"] == "smoke"
    assert payload["n"] == 1
    assert payload["message"] == "hello"


def test_configure_logging_is_idempotent():
    buf1 = io.StringIO()
    configure_logging(stream=buf1)
    buf2 = io.StringIO()
    configure_logging(stream=buf2)
    log = get_logger("test")
    log.info("once", extra={"event": "x"})
    assert buf1.getvalue() == ""
    assert "once" in buf2.getvalue()


def test_configure_logging_does_not_propagate_to_root():
    root_buf = io.StringIO()
    root_handler = logging.StreamHandler(root_buf)
    logging.getLogger().addHandler(root_handler)
    try:
        configure_logging(stream=io.StringIO())
        log = get_logger("test")
        log.info("isolated", extra={"event": "x"})
        assert "isolated" not in root_buf.getvalue()
    finally:
        logging.getLogger().removeHandler(root_handler)


def test_configure_logging_text_mode():
    buf = io.StringIO()
    configure_logging(fmt="text", stream=buf)
    log = get_logger("test")
    log.info("plain message")
    out = buf.getvalue()
    assert "plain message" in out
    assert not out.strip().startswith("{")


def test_timer_records_positive_duration():
    with Timer() as t:
        time.sleep(0.005)
    assert t.duration_ms >= 4.0


def test_timer_records_zero_when_no_sleep():
    with Timer() as t:
        pass
    assert t.duration_ms >= 0.0
    assert t.duration_ms < 50.0


def test_new_run_id_is_stable_until_reset():
    rid1 = new_run_id()
    assert current_run_id() == rid1
    rid2 = new_run_id()
    assert rid2 != rid1
    reset_run_id()
    assert current_run_id() is None
