import yaml

from fidu.translators.deequ_translator import DeequTranslator
from fidu.translators.gx_translator import GreatExpectationsTranslator
from fidu.translators.soda_translator import SodaTranslator


def test_soda_accepted_values_emits_valid_sodacl_dict():
    out = SodaTranslator().translate_rule(
        {
            "name": "status",
            "type": "accepted_values",
            "column": "status",
            "values": ["new", "shipped"],
        }
    )
    assert isinstance(out, dict)
    assert "invalid_count(status) = 0" in out
    assert out["invalid_count(status) = 0"]["valid values"] == ["new", "shipped"]


def test_soda_translator_filters_drafts():
    dataset = {
        "dataset": "orders",
        "rules": [
            {"name": "a", "type": "not_null", "column": "id"},
            {"name": "b", "type": "not_null", "column": "id", "draft": True},
        ],
    }
    out_yaml = SodaTranslator().translate_dataset(dataset, table_name="orders")
    parsed = yaml.safe_load(out_yaml)
    checks = parsed["checks for orders"]
    assert any("missing_count(id) = 0" in (c if isinstance(c, str) else "") for c in checks)
    # draft rule should not appear
    assert len(checks) == 1


def test_gx_translator_filters_drafts_and_emits_meta():
    dataset = {
        "dataset": "orders",
        "rules": [
            {
                "name": "a",
                "type": "not_null",
                "column": "id",
                "dimension": "completeness",
                "severity": "critical",
            },
            {
                "name": "draft_rule",
                "type": "not_null",
                "column": "id",
                "draft": True,
            },
        ],
    }
    suite = GreatExpectationsTranslator().translate_dataset(dataset)
    assert suite["expectation_suite_name"] == "orders_suite"
    assert len(suite["expectations"]) == 1
    expectation = suite["expectations"][0]
    assert expectation["expectation_type"] == "expect_column_values_to_not_be_null"
    assert expectation["meta"]["rule_name"] == "a"


def test_deequ_translator_emits_check_calls():
    dataset = {
        "dataset": "orders",
        "rules": [
            {"name": "a", "type": "not_null", "column": "id"},
            {"name": "b", "type": "unique", "column": "id"},
        ],
    }
    script = DeequTranslator().translate_dataset(dataset)
    assert "isComplete('id')" in script
    assert "isUnique('id')" in script
