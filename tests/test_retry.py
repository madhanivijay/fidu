"""Unit tests for ``core.retry`` plus an end-to-end retry through the executor."""

import io
import json
import logging

import pandas as pd
import pytest

from fidu.connectors.connector_factory import register_connector
from fidu.core.dq_executor import DQExecutor
from fidu.core.logging import LOGGER_NAMESPACE, configure_logging, reset_run_id
from fidu.core.retry import (
    DEFAULT_RETRYABLE,
    compute_delay_ms,
    parse_retry_config,
    with_retry,
)

# ---------- pure-function tests --------------------------------------------------------


def test_compute_delay_doubles_each_attempt_no_jitter():
    assert compute_delay_ms(1, 200, 5000, jitter=False) == 200
    assert compute_delay_ms(2, 200, 5000, jitter=False) == 400
    assert compute_delay_ms(3, 200, 5000, jitter=False) == 800


def test_compute_delay_caps_at_max():
    assert compute_delay_ms(10, 200, 5000, jitter=False) == 5000


def test_compute_delay_jitter_band():
    # attempt=2 -> raw 2*base = 2000ms, jitter band is [0.5, 1.5] of that
    samples = [compute_delay_ms(2, 1000, 10000, jitter=True) for _ in range(50)]
    assert all(1000 <= s <= 3000 for s in samples)


def test_with_retry_returns_value_on_first_success():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return 42

    assert with_retry(fn, attempts=3, sleep=lambda _: None) == 42
    assert calls["n"] == 1


def test_with_retry_recovers_after_transient_failures():
    attempts = []

    def fn():
        attempts.append(1)
        if len(attempts) < 3:
            raise OSError("transient")
        return "ok"

    sleeps: list[float] = []
    result = with_retry(
        fn, attempts=5, base_delay_ms=10, max_delay_ms=100, jitter=False, sleep=sleeps.append
    )
    assert result == "ok"
    assert len(attempts) == 3
    assert sleeps == [0.01, 0.02]  # only between attempts


def test_with_retry_reraises_last_exception_after_exhaustion():
    def fn():
        raise OSError("always-fails")

    with pytest.raises(OSError, match="always-fails"):
        with_retry(fn, attempts=3, base_delay_ms=1, max_delay_ms=2, sleep=lambda _: None)


def test_with_retry_passes_through_non_retryable_immediately():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise ValueError("logic bug, not transient")

    with pytest.raises(ValueError):
        with_retry(fn, attempts=5, sleep=lambda _: None)
    assert calls["n"] == 1  # no retries on non-retryable type


def test_with_retry_invokes_on_retry_callback():
    events: list[tuple[int, float, str]] = []

    def fn():
        if len(events) < 2:
            raise ConnectionError("flaky")
        return "done"

    def cb(attempt, delay, exc):
        events.append((attempt, delay, type(exc).__name__))

    with_retry(
        fn,
        attempts=5,
        base_delay_ms=10,
        max_delay_ms=20,
        jitter=False,
        on_retry=cb,
        sleep=lambda _: None,
    )
    assert events == [(1, 10.0, "ConnectionError"), (2, 20.0, "ConnectionError")]


def test_with_retry_attempts_one_means_no_retries():
    def fn():
        raise OSError()

    with pytest.raises(OSError):
        with_retry(fn, attempts=1, sleep=lambda _: None)


def test_with_retry_attempts_zero_rejected():
    with pytest.raises(ValueError):
        with_retry(lambda: None, attempts=0)


# ---------- config-parsing tests ------------------------------------------------------


def test_parse_retry_config_no_block_means_attempts_one():
    assert parse_retry_config({}) == {"attempts": 1}
    assert parse_retry_config(None) == {"attempts": 1}
    assert parse_retry_config({"type": "csv"}) == {"attempts": 1}
    assert parse_retry_config({"type": "csv", "retry": {}}) == {"attempts": 1}


def test_parse_retry_config_full_block():
    cfg = parse_retry_config(
        {
            "type": "snowflake",
            "retry": {
                "attempts": 4,
                "base_delay_ms": 100,
                "max_delay_ms": 2000,
                "jitter": False,
                "retryable": ["ConnectionError", "TimeoutError"],
            },
        }
    )
    assert cfg["attempts"] == 4
    assert cfg["base_delay_ms"] == 100.0
    assert cfg["max_delay_ms"] == 2000.0
    assert cfg["jitter"] is False
    assert ConnectionError in cfg["retryable"]
    assert TimeoutError in cfg["retryable"]
    assert OSError in cfg["retryable"]  # always included as a safety net


def test_parse_retry_config_unknown_exception_names_ignored():
    cfg = parse_retry_config(
        {"retry": {"attempts": 2, "retryable": ["NotARealException", "OSError"]}}
    )
    assert cfg["retryable"] == (OSError,)


def test_parse_retry_config_default_retryable():
    cfg = parse_retry_config({"retry": {"attempts": 2}})
    assert cfg["retryable"] == DEFAULT_RETRYABLE


# ---------- end-to-end through executor -----------------------------------------------


class _FlakyConnector:
    """Fails ``fail_count`` times with OSError, then returns ``df``."""

    def __init__(self, df: pd.DataFrame, fail_count: int):
        self._df = df
        self._fail_count = fail_count
        self.calls = 0

    def load_data(self, source_config: dict) -> pd.DataFrame:
        self.calls += 1
        if self.calls <= self._fail_count:
            raise OSError(f"simulated transient #{self.calls}")
        return self._df


@pytest.fixture(autouse=True)
def _clean_logger():
    reset_run_id()
    root = logging.getLogger(LOGGER_NAMESPACE)
    root.handlers = []
    yield
    reset_run_id()
    root.handlers = []


def test_executor_retries_load_data_and_emits_connector_retry_event():
    df = pd.DataFrame({"id": [1, 2, 3]})
    flaky = _FlakyConnector(df, fail_count=2)
    register_connector("_test_flaky", lambda: flaky)

    buf = io.StringIO()
    configure_logging(level="DEBUG", fmt="json", stream=buf)

    executor = DQExecutor("pandas")
    dataset_rules = {
        "dataset": "orders",
        "source": {
            "type": "_test_flaky",
            "retry": {"attempts": 5, "base_delay_ms": 1, "max_delay_ms": 2, "jitter": False},
        },
        "rules": [{"name": "id_not_null", "type": "not_null", "column": "id"}],
    }
    result = executor.execute_dataset_rules(dataset_rules)

    assert flaky.calls == 3  # 2 failures + 1 success
    assert result["passed_rules"] == 1

    events = [json.loads(line) for line in buf.getvalue().strip().splitlines()]
    retry_events = [e for e in events if e.get("event") == "connector_retry"]
    assert len(retry_events) == 2
    assert retry_events[0]["operation"] == "load_data"
    assert retry_events[0]["dataset"] == "orders"
    assert retry_events[0]["attempt"] == 1
    assert retry_events[1]["attempt"] == 2
    assert retry_events[0]["exception_type"] == "OSError"


def test_executor_no_retry_block_means_one_call():
    df = pd.DataFrame({"id": [1]})
    flaky = _FlakyConnector(df, fail_count=1)
    register_connector("_test_flaky_norietry", lambda: flaky)

    executor = DQExecutor("pandas")
    dataset_rules = {
        "dataset": "orders",
        "source": {"type": "_test_flaky_norietry"},
        "rules": [{"name": "id_not_null", "type": "not_null", "column": "id"}],
    }
    with pytest.raises(OSError):
        executor.execute_dataset_rules(dataset_rules)
    assert flaky.calls == 1


def test_executor_exhausts_attempts_and_raises():
    df = pd.DataFrame({"id": [1]})
    flaky = _FlakyConnector(df, fail_count=10)
    register_connector("_test_flaky_exhausted", lambda: flaky)

    executor = DQExecutor("pandas")
    dataset_rules = {
        "dataset": "orders",
        "source": {
            "type": "_test_flaky_exhausted",
            "retry": {"attempts": 3, "base_delay_ms": 1, "max_delay_ms": 2, "jitter": False},
        },
        "rules": [{"name": "id_not_null", "type": "not_null", "column": "id"}],
    }
    with pytest.raises(OSError):
        executor.execute_dataset_rules(dataset_rules)
    assert flaky.calls == 3
