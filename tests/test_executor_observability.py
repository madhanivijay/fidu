"""End-to-end check that DQExecutor emits structured events and per-rule duration_ms."""

import io
import json
import logging

import pandas as pd
import pytest

from fidu.connectors.connector_factory import register_connector
from fidu.core.dq_executor import DQExecutor
from fidu.core.logging import LOGGER_NAMESPACE, configure_logging, reset_run_id


class _DataFrameStubConnector:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def load_data(self, source_config: dict) -> pd.DataFrame:
        return self._df


@pytest.fixture(autouse=True)
def _clean_logger():
    reset_run_id()
    root = logging.getLogger(LOGGER_NAMESPACE)
    root.handlers = []
    yield
    reset_run_id()
    root.handlers = []


@pytest.fixture
def stub_connector_source():
    df = pd.DataFrame({"id": [1, 2, 3, 4], "amount": [10, 20, 30, 40]})
    register_connector("_test_stub", lambda: _DataFrameStubConnector(df))
    yield "_test_stub"


def test_executor_records_duration_ms_on_each_result(stub_connector_source):
    executor = DQExecutor("pandas")
    dataset_rules = {
        "dataset": "orders",
        "source": {"type": stub_connector_source},
        "rules": [
            {"name": "id_not_null", "type": "not_null", "column": "id"},
            {
                "name": "amount_in_range",
                "type": "between",
                "column": "amount",
                "min_value": 0,
                "max_value": 100,
            },
        ],
    }
    result = executor.execute_dataset_rules(dataset_rules)
    assert "duration_ms" in result
    assert result["duration_ms"] >= 0.0
    for rule_result in result["results"]:
        assert "duration_ms" in rule_result
        assert rule_result["duration_ms"] >= 0.0


def test_executor_emits_structured_events(stub_connector_source):
    buf = io.StringIO()
    configure_logging(level="INFO", fmt="json", stream=buf)

    executor = DQExecutor("pandas")
    dataset_rules = {
        "dataset": "orders",
        "source": {"type": stub_connector_source},
        "rules": [{"name": "id_not_null", "type": "not_null", "column": "id"}],
    }
    executor.execute_dataset_rules(dataset_rules)

    events = [json.loads(line) for line in buf.getvalue().strip().splitlines()]
    event_types = [e.get("event") for e in events]
    assert "dataset_start" in event_types
    assert "rule_complete" in event_types
    assert "dataset_complete" in event_types

    rule_event = next(e for e in events if e.get("event") == "rule_complete")
    assert rule_event["dataset"] == "orders"
    assert rule_event["rule_name"] == "id_not_null"
    assert rule_event["status"] == "passed"
    assert "duration_ms" in rule_event

    complete_event = next(e for e in events if e.get("event") == "dataset_complete")
    assert complete_event["total_rules"] == 1
    assert complete_event["passed_rules"] == 1
