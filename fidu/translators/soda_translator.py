"""Soda Core (SodaCL) translator.

Maps internal rule definitions to SodaCL check fragments. Each handler accepts
the rule dict and returns one of:

- ``str`` — a single check expression
- ``list[str]`` — multiple check expressions
- ``dict`` — a structured check with metadata or schema config
- ``None`` — rule type unsupported by Soda; caller emits an ``unsupported_rule`` marker
"""

import os
from collections.abc import Callable

import yaml

from fidu.core.rule_filter import filter_executable_rules

CheckFragment = str | dict[str, object] | list[str]
RuleHandler = Callable[[dict], CheckFragment | None]


class SodaTranslator:
    def __init__(self) -> None:
        self._handlers: dict[str, RuleHandler] = {
            "not_null": lambda r: f"missing_count({r.get('column')}) = 0",
            "unique": lambda r: f"duplicate_count({r.get('column')}) = 0",
            "accepted_values": self._accepted_values,
            "min_value": lambda r: f"min({r.get('column')}) >= {r['value']}",
            "max_value": lambda r: f"max({r.get('column')}) <= {r['value']}",
            "between": lambda r: [
                f"min({r.get('column')}) >= {r['min_value']}",
                f"max({r.get('column')}) <= {r['max_value']}",
            ],
            "row_count_min": lambda r: f"row_count >= {r['value']}",
            "row_count_max": lambda r: f"row_count <= {r['value']}",
            "freshness": lambda r: f"freshness({r.get('column')}) < {r.get('max_age_days', 1)}d",
            "required_columns": self._required_columns,
            "schema_drift_check": self._schema_drift_check,
            "regex_match": lambda r: f"invalid_count({r.get('column')}) = 0",
        }

    @staticmethod
    def _accepted_values(rule: dict) -> dict[str, object]:
        col = rule.get("column")
        return {
            f"invalid_count({col}) = 0": {
                "valid values": list(rule.get("values", [])),
            }
        }

    @staticmethod
    def _required_columns(rule: dict) -> dict[str, object]:
        return {
            "schema": {
                "fail": {
                    "when required column missing": list(rule.get("columns", [])),
                }
            }
        }

    @staticmethod
    def _schema_drift_check(rule: dict) -> dict[str, object]:
        return {"schema": {"fail": {"when schema changes": "any"}}}

    def translate_rule(self, rule: dict) -> CheckFragment | None:
        handler = self._handlers.get(rule["type"])
        return handler(rule) if handler else None

    def translate_dataset(self, dataset_rules: dict, table_name: str | None = None) -> str:
        dataset_name = (
            table_name
            or dataset_rules.get("source", {}).get("table")
            or dataset_rules["dataset"]
        )
        checks: list[object] = []
        for rule in filter_executable_rules(dataset_rules.get("rules", [])):
            translated = self.translate_rule(rule)
            if translated is None:
                checks.append(
                    {
                        f"unsupported_rule__{rule['name']}": {
                            "metadata": {"original_rule_type": rule.get("type")}
                        }
                    }
                )
            elif isinstance(translated, list):
                checks.extend(translated)
            else:
                checks.append(translated)
        return yaml.safe_dump({f"checks for {dataset_name}": checks}, sort_keys=False)

    def write_artifact(
        self, dataset_rules: dict, output_dir: str, table_name: str | None = None
    ) -> str:
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, f"{dataset_rules['dataset']}_soda_checks.yml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.translate_dataset(dataset_rules, table_name))
        return path
