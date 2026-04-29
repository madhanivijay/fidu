import pandas as pd
import pytest

from fidu.core.regex_safety import UnsafeRegexPattern
from fidu.engines.pandas_engine import PandasDQEngine


@pytest.fixture
def engine():
    return PandasDQEngine()


def test_between_default_treats_null_as_failure(engine):
    df = pd.DataFrame({"a": [1, 2, None, 5]})
    result = engine.run_rule(
        df, {"name": "b", "type": "between", "column": "a", "min_value": 0, "max_value": 4}
    )
    # 5 is out of range; None counted as failure by default
    assert result["failed_count"] == 2
    assert result["status"] == "failed"


def test_between_with_treat_null_as_pass(engine):
    df = pd.DataFrame({"a": [1, 2, None, 5]})
    result = engine.run_rule(
        df,
        {
            "name": "b",
            "type": "between",
            "column": "a",
            "min_value": 0,
            "max_value": 4,
            "treat_null_as": "pass",
        },
    )
    assert result["failed_count"] == 1


def test_accepted_values_treats_null_consistently(engine):
    df = pd.DataFrame({"s": ["a", None, "x"]})
    result = engine.run_rule(
        df, {"name": "x", "type": "accepted_values", "column": "s", "values": ["a", "b"]}
    )
    assert result["failed_count"] == 2


def test_regex_match_handles_nan_explicitly(engine):
    df = pd.DataFrame({"e": ["a@b.com", None, "bad"]})
    result = engine.run_rule(
        df, {"name": "r", "type": "regex_match", "column": "e", "pattern": r"^.+@.+\..+$"}
    )
    # nan and "bad" both fail
    assert result["failed_count"] == 2


def test_regex_match_rejects_redos_pattern(engine):
    df = pd.DataFrame({"e": ["a"]})
    with pytest.raises(UnsafeRegexPattern):
        engine.run_rule(
            df, {"name": "r", "type": "regex_match", "column": "e", "pattern": "(a+)+"}
        )


def test_regex_match_rejects_overlong_pattern(engine):
    df = pd.DataFrame({"e": ["a"]})
    with pytest.raises(UnsafeRegexPattern):
        engine.run_rule(
            df,
            {
                "name": "r",
                "type": "regex_match",
                "column": "e",
                "pattern": "a" * 2000,
            },
        )


def test_freshness_handles_tz_aware_dates(engine):
    df = pd.DataFrame(
        {"d": ["2026-04-25T00:00:00+00:00", "2026-04-26T12:00:00+05:30", "bogus"]}
    )
    result = engine.run_rule(
        df, {"name": "f", "type": "freshness", "column": "d", "max_age_days": 60}
    )
    assert result["status"] == "passed"
