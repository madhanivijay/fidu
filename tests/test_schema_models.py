import pytest

from fidu.core.schema_models import (
    PYDANTIC_AVAILABLE,
    validate_config_dict,
    validate_dataset_rules_dict,
)

pytestmark = pytest.mark.skipif(not PYDANTIC_AVAILABLE, reason="pydantic not installed")


def test_minimal_dataset_rules_validates():
    out = validate_dataset_rules_dict(
        {
            "dataset": "orders",
            "source": {"type": "local_file", "format": "csv", "path": "data/orders.csv"},
            "rules": [{"name": "id_not_null", "type": "not_null", "column": "id"}],
        }
    )
    assert out["dataset"] == "orders"


def test_native_mode_requires_engine():
    with pytest.raises(ValueError):
        validate_config_dict(
            {
                "project": {"name": "demo"},
                "execution": {"mode": "native"},
                "datasets": [{"name": "orders", "rules_file": "rules/orders.yaml"}],
            }
        )


def test_tool_mode_requires_tool():
    with pytest.raises(ValueError):
        validate_config_dict(
            {
                "project": {"name": "demo"},
                "execution": {"mode": "tool"},
                "datasets": [{"name": "orders", "rules_file": "rules/orders.yaml"}],
            }
        )


def test_invalid_severity_rejected():
    with pytest.raises(ValueError):
        validate_dataset_rules_dict(
            {
                "dataset": "orders",
                "source": {"type": "local_file"},
                "rules": [
                    {
                        "name": "bad",
                        "type": "not_null",
                        "column": "id",
                        "severity": "blocker",
                    }
                ],
            }
        )


def test_full_config_validates():
    out = validate_config_dict(
        {
            "project": {"name": "demo"},
            "execution": {"mode": "native", "engine": "pandas"},
            "datasets": [{"name": "orders", "rules_file": "rules/orders.yaml"}],
            "outputs": {"json_path": "outputs/dq_results.json"},
            "drift": {"enabled": True},
        }
    )
    assert out["execution"]["engine"] == "pandas"
