"""Input ``schema_version`` contract.

Both the top-level config YAML and per-dataset rule YAMLs declare a
``schema_version`` so the kit can detect future breaking changes:

* missing  -> non-fatal warning surfaced via ``validation_warnings``
* wrong type / unknown major -> hard ``ValueError`` so the run fails fast
"""

import pytest

from fidu.core.config_validator import (
    _validate_input_schema_version,
    validate_dataset_config,
    validate_dataset_for_tool,
    validate_top_level_config,
)
from fidu.core.constants import INPUT_SCHEMA_VERSION


def _good_dataset() -> dict:
    return {
        "schema_version": INPUT_SCHEMA_VERSION,
        "dataset": "orders",
        "source": {"type": "local_file", "format": "csv", "path": "/tmp/orders.csv"},
        "rules": [
            {
                "name": "id_not_null",
                "type": "not_null",
                "column": "id",
                "dimension": "completeness",
                "severity": "critical",
            }
        ],
    }


def _good_config() -> dict:
    return {
        "schema_version": INPUT_SCHEMA_VERSION,
        "project": {"name": "demo"},
        "execution": {"mode": "native", "engine": "pandas"},
        "datasets": [{"name": "orders", "rules_file": "x.yaml"}],
    }


def test_helper_returns_no_warning_on_correct_version():
    assert _validate_input_schema_version({"schema_version": INPUT_SCHEMA_VERSION}, "x") == []


def test_helper_warns_when_missing():
    warnings = _validate_input_schema_version({}, "rules file")
    assert len(warnings) == 1
    assert "missing" in warnings[0]
    assert "schema_version" in warnings[0]
    assert str(INPUT_SCHEMA_VERSION) in warnings[0]


def test_helper_raises_on_unknown_major():
    with pytest.raises(ValueError, match="not supported"):
        _validate_input_schema_version({"schema_version": 999}, "rules file")


def test_helper_raises_on_non_int():
    with pytest.raises(ValueError, match="must be an integer"):
        _validate_input_schema_version({"schema_version": "1"}, "rules file")


def test_helper_raises_on_bool_masquerading_as_int():
    # True == 1 in Python so without the explicit bool guard this would pass.
    with pytest.raises(ValueError, match="must be an integer"):
        _validate_input_schema_version({"schema_version": True}, "rules file")


def test_top_level_validator_returns_warning_when_missing():
    config = _good_config()
    del config["schema_version"]
    warnings = validate_top_level_config(config)
    assert any("schema_version" in w for w in warnings)


def test_top_level_validator_clean_when_present():
    assert validate_top_level_config(_good_config()) == []


def test_top_level_validator_raises_on_unknown_version():
    config = _good_config()
    config["schema_version"] = 99
    with pytest.raises(ValueError):
        validate_top_level_config(config)


def test_dataset_validator_warns_when_missing():
    rules = _good_dataset()
    del rules["schema_version"]
    warnings = validate_dataset_config("pandas", rules)
    assert any("schema_version" in w for w in warnings)
    # rule-support warnings list still empty for this clean rule set
    assert all("not supported" not in w for w in warnings)


def test_dataset_validator_clean_when_present():
    assert validate_dataset_config("pandas", _good_dataset()) == []


def test_dataset_validator_raises_on_unknown_version():
    rules = _good_dataset()
    rules["schema_version"] = 7
    with pytest.raises(ValueError):
        validate_dataset_config("pandas", rules)


def test_tool_dataset_validator_warns_when_missing():
    rules = _good_dataset()
    del rules["schema_version"]
    warnings = validate_dataset_for_tool(rules)
    assert any("schema_version" in w for w in warnings)


def test_tool_dataset_validator_clean_when_present():
    assert validate_dataset_for_tool(_good_dataset()) == []
