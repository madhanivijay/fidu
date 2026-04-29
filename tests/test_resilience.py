"""Phase C resilience guarantees:

* per-rule timeout via ``rule.timeout_seconds`` -> ``RuleTimeoutError``
* per-rule exception capture -> ``status: error`` rule result, run continues
* per-dataset exception capture (``safe_execute_dataset_rules``) -> ``status: error``
  dataset result with ``error_message``, surrounding loop continues
* tool-mode dataset events are log-symmetric with native mode
"""

import io
import json
import logging
import time

import pandas as pd
import pytest

from fidu.connectors.connector_factory import register_connector
from fidu.core.dq_executor import DQExecutor
from fidu.core.logging import LOGGER_NAMESPACE, configure_logging, reset_run_id
from fidu.core.timeout import RuleTimeoutError, run_with_timeout
from fidu.engines.base_engine import BaseDQEngine
from fidu.engines.engine_factory import register_engine
from fidu.main import _run_tool_dataset


@pytest.fixture(autouse=True)
def _clean_logger():
    reset_run_id()
    root = logging.getLogger(LOGGER_NAMESPACE)
    root.handlers = []
    yield
    reset_run_id()
    root.handlers = []


class _FixedDataFrameConnector:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def load_data(self, source_config: dict) -> pd.DataFrame:
        return self._df


class _ExplodingConnector:
    def load_data(self, source_config: dict) -> pd.DataFrame:
        raise ConnectionError("boom: cannot reach data source")


class _ExplodingEngine(BaseDQEngine):
    """Raises on rules whose name starts with ``explode_``; passes otherwise."""

    def run_rule(self, data, rule: dict) -> dict:
        if rule["name"].startswith("explode_"):
            raise RuntimeError("simulated engine failure")
        return {
            "rule_name": rule["name"],
            "rule_type": rule["type"],
            "column": rule.get("column"),
            "columns": rule.get("columns"),
            "dimension": rule.get("dimension", "validity"),
            "severity": rule.get("severity", "warning"),
            "status": "passed",
            "total_rows": len(data),
            "failed_count": 0,
            "pass_rate": 1.0,
            "details": {},
            "failed_sample": [],
        }


class _SlowEngine(BaseDQEngine):
    """Sleeps 2 s on every rule -- forces ``timeout_seconds`` to fire."""

    def run_rule(self, data, rule: dict) -> dict:
        time.sleep(2.0)
        return {
            "rule_name": rule["name"],
            "rule_type": rule["type"],
            "column": rule.get("column"),
            "columns": rule.get("columns"),
            "dimension": rule.get("dimension", "validity"),
            "severity": rule.get("severity", "warning"),
            "status": "passed",
            "total_rows": len(data),
            "failed_count": 0,
            "pass_rate": 1.0,
            "details": {},
            "failed_sample": [],
        }


# --- run_with_timeout primitive -------------------------------------------


def test_run_with_timeout_returns_value_when_fast():
    assert run_with_timeout(lambda: 42, timeout_seconds=1.0) == 42


def test_run_with_timeout_raises_on_slow_call():
    def _slow():
        time.sleep(0.5)
        return 1

    with pytest.raises(RuleTimeoutError, match="exceeded"):
        run_with_timeout(_slow, timeout_seconds=0.05)


def test_run_with_timeout_propagates_other_exceptions():
    def _raise():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        run_with_timeout(_raise, timeout_seconds=1.0)


def test_run_with_timeout_zero_means_no_timeout():
    # 0/None disables the wrapper entirely; the call still runs.
    assert run_with_timeout(lambda: "ok", timeout_seconds=0) == "ok"
    assert run_with_timeout(lambda: "ok", timeout_seconds=None) == "ok"


# --- per-rule partial-result mode (engine throws) -------------------------


def test_engine_exception_yields_error_rule_result_other_rules_continue():
    df = pd.DataFrame({"id": [1, 2, 3]})
    register_connector("_test_partial_rule", lambda: _FixedDataFrameConnector(df))
    register_engine("_test_explode", lambda: _ExplodingEngine())

    executor = DQExecutor("_test_explode")
    dataset_rules = {
        "dataset": "orders",
        "source": {"type": "_test_partial_rule"},
        "rules": [
            {"name": "explode_first", "type": "not_null", "column": "id"},
            {"name": "ok_second", "type": "not_null", "column": "id"},
        ],
    }
    result = executor.execute_dataset_rules(dataset_rules)

    assert result["total_rules"] == 2
    assert result["errored_rules"] == 1
    assert result["passed_rules"] == 1

    err = next(r for r in result["results"] if r["rule_name"] == "explode_first")
    assert err["status"] == "error"
    assert "RuntimeError" in err["error_message"]
    assert err["total_rows"] == 3
    assert err["pass_rate"] is None
    assert "duration_ms" in err

    ok = next(r for r in result["results"] if r["rule_name"] == "ok_second")
    assert ok["status"] == "passed"


# --- per-rule timeout (engine hangs) --------------------------------------


def test_per_rule_timeout_marks_rule_as_error_and_continues():
    df = pd.DataFrame({"id": [1, 2, 3]})
    register_connector("_test_timeout", lambda: _FixedDataFrameConnector(df))
    register_engine("_test_slow", lambda: _SlowEngine())

    executor = DQExecutor("_test_slow")
    dataset_rules = {
        "dataset": "orders",
        "source": {"type": "_test_timeout"},
        "rules": [
            {
                "name": "slow_rule",
                "type": "not_null",
                "column": "id",
                "timeout_seconds": 0.05,
            },
        ],
    }
    result = executor.execute_dataset_rules(dataset_rules)

    assert result["errored_rules"] == 1
    err = result["results"][0]
    assert err["status"] == "error"
    assert "RuleTimeoutError" in err["error_message"]
    assert err["total_rows"] == 3


# --- per-dataset partial-result mode (connector throws) -------------------


def test_safe_execute_dataset_rules_returns_error_stub_on_connector_failure():
    register_connector("_test_exploding", lambda: _ExplodingConnector())

    executor = DQExecutor("pandas")
    dataset_rules = {
        "dataset": "orders",
        # no retry block -> single attempt, no backoff in tests
        "source": {"type": "_test_exploding"},
        "rules": [{"name": "id_not_null", "type": "not_null", "column": "id"}],
    }
    result = executor.safe_execute_dataset_rules(dataset_rules)

    assert result["status"] == "error"
    assert "ConnectionError" in result["error_message"]
    assert result["dataset"] == "orders"
    assert result["results"] == []
    assert result["total_rules"] == 0


def test_safe_execute_emits_dataset_error_event():
    register_connector("_test_exploding2", lambda: _ExplodingConnector())
    buf = io.StringIO()
    configure_logging(level="INFO", fmt="json", stream=buf)

    executor = DQExecutor("pandas")
    executor.safe_execute_dataset_rules(
        {
            "dataset": "orders",
            "source": {"type": "_test_exploding2"},
            "rules": [{"name": "id_not_null", "type": "not_null", "column": "id"}],
        }
    )
    events = [json.loads(line) for line in buf.getvalue().strip().splitlines()]
    event_types = [e.get("event") for e in events]
    assert "dataset_error" in event_types
    err_event = next(e for e in events if e.get("event") == "dataset_error")
    assert err_event["dataset"] == "orders"
    assert "ConnectionError" in err_event["exception_type"] or "ConnectionError" in err_event[
        "exception_message"
    ]


# --- tool-mode observability symmetry --------------------------------------


class _StubAdapter:
    def __init__(self, behaviour="ok"):
        self._behaviour = behaviour

    def run_dataset(self, dataset_rules: dict, tool_config: dict) -> dict:
        if self._behaviour == "explode":
            raise RuntimeError("tool fell over")
        rules = dataset_rules.get("rules", [])
        return {
            "dataset": dataset_rules.get("dataset"),
            "source": dataset_rules.get("source", {}),
            "total_rules": len(rules),
            "passed_rules": len(rules),
            "failed_rules": 0,
            "skipped_rules": 0,
            "errored_rules": 0,
            "results": [
                {
                    "rule_name": r["name"],
                    "rule_type": r["type"],
                    "column": r.get("column"),
                    "columns": r.get("columns"),
                    "dimension": r.get("dimension", "validity"),
                    "severity": r.get("severity", "warning"),
                    "status": "passed",
                }
                for r in rules
            ],
            "columns_seen": [],
        }


def test_run_tool_dataset_emits_start_and_complete_events_on_success():
    buf = io.StringIO()
    configure_logging(level="INFO", fmt="json", stream=buf)

    rules = {
        "dataset": "orders",
        "source": {"type": "csv"},
        "rules": [{"name": "id_not_null", "type": "not_null", "column": "id"}],
    }
    result = _run_tool_dataset(_StubAdapter("ok"), "stub", rules, {})

    assert result["status"] == "completed"
    assert result["total_rules"] == 1
    assert result["passed_rules"] == 1
    assert "duration_ms" in result

    events = [json.loads(line) for line in buf.getvalue().strip().splitlines()]
    types = [e.get("event") for e in events]
    assert "dataset_start" in types
    assert "dataset_complete" in types
    start = next(e for e in events if e.get("event") == "dataset_start")
    assert start["tool"] == "stub"
    assert start["dataset"] == "orders"


def test_run_tool_dataset_returns_error_stub_and_emits_event_on_failure():
    buf = io.StringIO()
    configure_logging(level="INFO", fmt="json", stream=buf)

    rules = {
        "dataset": "orders",
        "source": {"type": "csv"},
        "rules": [{"name": "id_not_null", "type": "not_null", "column": "id"}],
    }
    result = _run_tool_dataset(_StubAdapter("explode"), "stub", rules, {})

    assert result["status"] == "error"
    assert "RuntimeError" in result["error_message"]
    assert result["total_rules"] == 0
    assert result["results"] == []
    assert "duration_ms" in result

    events = [json.loads(line) for line in buf.getvalue().strip().splitlines()]
    types = [e.get("event") for e in events]
    assert "dataset_error" in types
    err = next(e for e in events if e.get("event") == "dataset_error")
    assert err["tool"] == "stub"
    assert err["exception_type"] == "RuntimeError"
