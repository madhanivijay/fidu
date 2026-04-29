"""End-to-end test that the docs/EXTENDING.md example actually works.

If this test breaks, the extension contract has changed -- update the docs in
the same commit.
"""

import os

import pytest

from examples.custom_connector.jsonl_connector import install
from fidu.core.dq_executor import DQExecutor

_RULES = os.path.join(
    os.path.dirname(__file__), "..", "examples", "custom_connector", "rules.yaml"
)


@pytest.fixture(autouse=True)
def _install_jsonl_connector():
    install()
    yield


def test_custom_connector_runs_end_to_end():
    from fidu.core.rule_parser import load_yaml

    dataset_rules = load_yaml(os.path.abspath(_RULES))
    dataset_rules["source"]["path"] = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", dataset_rules["source"]["path"])
    )

    executor = DQExecutor("pandas")
    result = executor.execute_dataset_rules(dataset_rules)

    assert result["dataset"] == "example_orders"
    assert result["total_rules"] == 5
    rule_names = {r["rule_name"] for r in result["results"]}
    assert rule_names == {
        "order_id_not_null",
        "order_id_unique",
        "customer_id_not_null",
        "amount_in_range",
        "valid_status",
    }
    # the sample data has known violations -- prove the rules actually ran
    by_name = {r["rule_name"]: r for r in result["results"]}
    assert by_name["order_id_not_null"]["status"] == "passed"
    assert by_name["customer_id_not_null"]["status"] == "failed"  # null in row 3
    assert by_name["amount_in_range"]["status"] == "failed"       # -50 in row 4
    assert by_name["valid_status"]["status"] == "failed"          # INVALID_STATUS row 5


def test_alias_resolves_to_same_connector():
    from fidu.connectors.connector_factory import connector_registry

    assert "jsonl" in connector_registry
    assert "json_lines" in connector_registry
    a = connector_registry.create("jsonl")
    b = connector_registry.create("json_lines")
    assert type(a) is type(b)
