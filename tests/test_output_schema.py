"""Schema validation for outputs/dq_results.json.

The schema is a contract for downstream consumers (BI tools, data catalogs,
contract systems). Any change that fails this test is by definition a breaking
change to that contract -- bump ``OUTPUT_SCHEMA_VERSION`` and document in
CHANGELOG.md before merging.
"""

import json
import math
import os
import tempfile
from pathlib import Path

import jsonschema
import pytest

from fidu.core.constants import OUTPUT_SCHEMA_VERSION
from fidu.core.result_writer import write_json_result

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "dq_results.schema.json"


@pytest.fixture(scope="module")
def schema():
    with open(_SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def validator(schema):
    cls = jsonschema.validators.validator_for(schema)
    cls.check_schema(schema)
    return cls(schema)


def _minimal_run() -> dict:
    return {
        "project": "demo",
        "execution_mode": "native",
        "config_path": "/tmp/x.yaml",
        "run_id": "abc123",
        "engine": "pandas",
        "duration_ms": 1.0,
        "validation_warnings": [],
        "datasets": [
            {
                "dataset": "orders",
                "source": {"type": "csv", "path": "/tmp/orders.csv"},
                "total_rules": 1,
                "passed_rules": 1,
                "failed_rules": 0,
                "skipped_rules": 0,
                "errored_rules": 0,
                "duration_ms": 1.0,
                "columns_seen": ["id"],
                "results": [
                    {
                        "rule_name": "id_not_null",
                        "rule_type": "not_null",
                        "column": "id",
                        "columns": None,
                        "dimension": "completeness",
                        "severity": "critical",
                        "status": "passed",
                        "total_rows": 10,
                        "failed_count": 0,
                        "pass_rate": 1.0,
                        "duration_ms": 0.5,
                        "failed_sample": [],
                    }
                ],
            }
        ],
        "trust_score_summary": {
            "overall_trust_score": 100.0,
            "overall_grade": "TRUSTED",
            "grade_reason": "all rules passed",
            "dataset_scores": [
                {
                    "dataset": "orders",
                    "trust_score": 100.0,
                    "grade": "TRUSTED",
                    "grade_reason": "all rules passed",
                    "critical_failures": 0,
                    "warning_failures": 0,
                    "skipped_rules": 0,
                    "errored_rules": 0,
                    "dimension_scores": {
                        "completeness": {"score": 100.0, "failed_rules": 0, "total_rules": 1}
                    },
                }
            ],
        },
        "drift_report": {"status": "disabled", "alerts": []},
    }


def test_schema_is_self_consistent(schema):
    cls = jsonschema.validators.validator_for(schema)
    cls.check_schema(schema)


def test_minimal_run_validates(validator):
    payload = {"schema_version": OUTPUT_SCHEMA_VERSION, **_minimal_run()}
    validator.validate(payload)


def test_writer_emits_schema_version(validator):
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "result.json")
        write_json_result(_minimal_run(), out)
        with open(out, encoding="utf-8") as f:
            payload = json.load(f)
    assert payload["schema_version"] == OUTPUT_SCHEMA_VERSION
    validator.validate(payload)


def test_writer_sanitizes_nan_and_inf(validator):
    run = _minimal_run()
    run["datasets"][0]["results"][0]["failed_sample"] = [
        {"id": 1, "amount": float("nan"), "score": float("inf")}
    ]
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "result.json")
        write_json_result(run, out)
        with open(out, encoding="utf-8") as f:
            text = f.read()
            payload = json.loads(text)  # strict parse — would fail if NaN leaked through
    assert "NaN" not in text
    assert "Infinity" not in text
    sample = payload["datasets"][0]["results"][0]["failed_sample"][0]
    assert sample["amount"] is None
    assert sample["score"] is None
    validator.validate(payload)


def test_invalid_severity_is_rejected(validator):
    payload = {"schema_version": OUTPUT_SCHEMA_VERSION, **_minimal_run()}
    payload["datasets"][0]["results"][0]["severity"] = "panic"
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(payload)


def test_invalid_status_is_rejected(validator):
    payload = {"schema_version": OUTPUT_SCHEMA_VERSION, **_minimal_run()}
    payload["datasets"][0]["results"][0]["status"] = "ok"
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(payload)


def test_missing_required_top_level_field_rejected(validator):
    payload = {"schema_version": OUTPUT_SCHEMA_VERSION, **_minimal_run()}
    del payload["trust_score_summary"]
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(payload)


def test_schema_version_format(validator):
    payload = {"schema_version": "not-semver", **_minimal_run()}
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(payload)


def test_real_executor_output_validates_end_to_end(validator):
    """Run the full pipeline on the demo config and validate the emitted file."""
    from fidu.main import run_from_config

    with tempfile.TemporaryDirectory() as tmp:
        json_path = os.path.join(tmp, "dq_results.json")
        os.environ["_DQ_TEST_JSON_PATH"] = json_path  # not used; exercise the writer directly
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "configs", "dq_config.yaml"
        )
        result = run_from_config(os.path.abspath(config_path))
        write_json_result(result, json_path)
        with open(json_path, encoding="utf-8") as f:
            payload = json.load(f)
    assert payload["schema_version"] == OUTPUT_SCHEMA_VERSION
    validator.validate(payload)
    # spot-check a couple of fields beyond the schema
    assert payload["execution_mode"] in ("native", "tool")
    assert isinstance(payload["datasets"], list) and payload["datasets"]
    for ds in payload["datasets"]:
        for r in ds["results"]:
            assert not (isinstance(r.get("pass_rate"), float) and math.isnan(r["pass_rate"]))
