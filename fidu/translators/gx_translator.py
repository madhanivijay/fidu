"""Great Expectations translator.

Each handler returns the ``kwargs`` dict for the corresponding expectation type.
A small adapter wraps the handler output with ``expectation_type`` and ``meta``.
"""

import json
import os
from collections.abc import Callable

from fidu.core.rule_filter import filter_executable_rules

ExpectationSpec = tuple[str, dict[str, object]]
RuleHandler = Callable[[dict], ExpectationSpec | None]


class GreatExpectationsTranslator:
    def __init__(self) -> None:
        self._handlers: dict[str, RuleHandler] = {
            "not_null": lambda r: (
                "expect_column_values_to_not_be_null",
                {"column": r.get("column")},
            ),
            "unique": lambda r: (
                "expect_column_values_to_be_unique",
                {"column": r.get("column")},
            ),
            "accepted_values": lambda r: (
                "expect_column_values_to_be_in_set",
                {"column": r.get("column"), "value_set": r.get("values", [])},
            ),
            "between": lambda r: (
                "expect_column_values_to_be_between",
                {
                    "column": r.get("column"),
                    "min_value": r.get("min_value"),
                    "max_value": r.get("max_value"),
                },
            ),
            "regex_match": lambda r: (
                "expect_column_values_to_match_regex",
                {"column": r.get("column"), "regex": r.get("pattern")},
            ),
            "row_count_min": lambda r: (
                "expect_table_row_count_to_be_between",
                {"min_value": r.get("value")},
            ),
            "row_count_max": lambda r: (
                "expect_table_row_count_to_be_between",
                {"max_value": r.get("value")},
            ),
            "required_columns": lambda r: (
                "expect_table_columns_to_match_set",
                {"column_set": r.get("columns", []), "exact_match": False},
            ),
            "schema_drift_check": lambda r: (
                "expect_table_columns_to_match_set",
                {
                    "column_set": r.get("expected_columns", []),
                    "exact_match": not r.get("allow_extra_columns", True),
                },
            ),
            "min_value": lambda r: (
                "expect_column_min_to_be_between",
                {"column": r.get("column"), "min_value": r["value"]},
            ),
            "max_value": lambda r: (
                "expect_column_max_to_be_between",
                {"column": r.get("column"), "max_value": r["value"]},
            ),
        }

    def translate_rule(self, rule: dict) -> dict[str, object] | None:
        handler = self._handlers.get(rule["type"])
        if handler is None:
            return None
        spec = handler(rule)
        if spec is None:
            return None
        expectation_type, kwargs = spec
        return {
            "expectation_type": expectation_type,
            "kwargs": kwargs,
            "meta": {
                "rule_name": rule["name"],
                "severity": rule.get("severity"),
                "dimension": rule.get("dimension"),
            },
        }

    def translate_dataset(self, dataset_rules: dict) -> dict[str, object]:
        expectations = []
        for rule in filter_executable_rules(dataset_rules.get("rules", [])):
            translated = self.translate_rule(rule)
            if translated is None:
                translated = {
                    "expectation_type": "unsupported_rule",
                    "kwargs": {"rule_name": rule["name"], "rule_type": rule.get("type")},
                }
            expectations.append(translated)
        return {
            "expectation_suite_name": f"{dataset_rules['dataset']}_suite",
            "expectations": expectations,
            "meta": {"generated_by": "fidu"},
        }

    def write_artifact(self, dataset_rules: dict, output_dir: str) -> str:
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(
            output_dir, f"{dataset_rules['dataset']}_gx_expectation_suite.json"
        )
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.translate_dataset(dataset_rules), f, indent=2)
        return path
