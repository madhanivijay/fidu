import pytest

from fidu.core.sql_safety import UnsafeSQLIdentifier
from fidu.engines.sql_engine import SQLDQEngine


def test_build_rule_query_rejects_injected_column():
    engine = SQLDQEngine()
    with pytest.raises(UnsafeSQLIdentifier):
        engine.build_rule_query(
            "orders",
            {"name": "x", "type": "not_null", "column": "id; DROP TABLE users"},
        )


def test_build_rule_query_rejects_injected_table():
    engine = SQLDQEngine()
    with pytest.raises(UnsafeSQLIdentifier):
        engine.build_rule_query(
            "orders; DROP TABLE users",
            {"name": "x", "type": "not_null", "column": "id"},
        )


def test_accepted_values_quotes_strings_safely():
    engine = SQLDQEngine()
    sql = engine.build_rule_query(
        "orders",
        {
            "name": "x",
            "type": "accepted_values",
            "column": "status",
            "values": ["O'Brien", "ok"],
        },
    )
    assert "'O''Brien'" in sql
    assert "'ok'" in sql
    assert "DROP" not in sql.upper().replace("DROPPED", "")


def test_between_validates_numeric_values():
    engine = SQLDQEngine()
    with pytest.raises(ValueError):
        engine.build_rule_query(
            "orders",
            {
                "name": "x",
                "type": "between",
                "column": "amount",
                "min_value": "1; DROP",
                "max_value": 100,
            },
        )


def test_unsupported_rule_type_raises():
    engine = SQLDQEngine()
    with pytest.raises(ValueError):
        engine.build_rule_query("orders", {"name": "x", "type": "freshness", "column": "d"})
