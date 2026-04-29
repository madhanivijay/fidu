from __future__ import annotations

import json

from fidu.core.paths import resolve_in_package


def load_rule_suggestions(path: str | None = None) -> dict:
    if path is None:
        path = resolve_in_package("intelligence", "rule_suggestions.json")
    with open(path, encoding="utf-8") as file:
        return json.load(file)

def infer_column_family(column_name: str) -> str:
    name = column_name.lower()
    if name.endswith("_id") or name == "id":
        return "id"
    if "email" in name:
        return "email"
    if "phone" in name or "mobile" in name:
        return "phone"
    if "status" in name or "type" in name or "category" in name:
        return "status"
    if "created_at" in name or "updated_at" in name or "date" in name or "timestamp" in name:
        return "date"
    if "amount" in name or "price" in name or "cost" in name or "revenue" in name:
        return "amount"
    if "quantity" in name or "qty" in name or "count" in name:
        return "quantity"
    return "generic"

def default_dimension(rule_type: str) -> str:
    return {
        "not_null":"completeness", "required_columns":"consistency", "accepted_values":"validity",
        "regex_match":"validity", "between":"validity", "min_value":"validity", "max_value":"validity",
        "unique":"uniqueness", "duplicate_check":"uniqueness", "freshness":"freshness",
        "row_count_min":"volume", "row_count_max":"volume", "schema_drift_check":"consistency",
        "column_type_check":"consistency"
    }.get(rule_type, "validity")

def default_severity(rule_type: str) -> str:
    return "critical" if rule_type in {"not_null","unique","required_columns","schema_drift_check","freshness"} else "warning"

def build_rule_template(column_name: str, rule_type: str) -> dict:
    base = {
        "name": f"{column_name}_{rule_type}",
        "type": rule_type,
        "column": column_name,
        "severity": default_severity(rule_type),
        "dimension": default_dimension(rule_type),
    }
    if rule_type == "accepted_values":
        base["values"] = ["TODO_VALUE_1", "TODO_VALUE_2"]
    if rule_type == "regex_match":
        base["pattern"] = (
            r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
            if "email" in column_name.lower()
            else "TODO_REGEX_PATTERN"
        )
    if rule_type == "between":
        base.update({"min_value": 0, "max_value": "TODO_MAX_VALUE"})
    if rule_type == "min_value":
        base["value"] = 0
    if rule_type == "max_value":
        base["value"] = "TODO_MAX_VALUE"
    if rule_type == "freshness":
        base["max_age_days"] = 1
    return base

def suggest_rules_for_column(column_name: str, data_type: str = "string") -> list:
    suggestions = load_rule_suggestions()
    family = infer_column_family(column_name)
    by_name = suggestions.get("by_column_name", {})
    rules_from_name = by_name.get(column_name.lower(), by_name.get(family, []))
    rules_from_type = suggestions.get("by_data_type", {}).get(data_type.lower(), [])
    combined = list(dict.fromkeys(rules_from_name + rules_from_type))
    return [build_rule_template(column_name, rt) for rt in combined]

def suggest_dataset_rules(dataset_name: str, source_config: dict, columns: list) -> dict:
    names = [c["name"] for c in columns]
    rules = [
        {"name": f"{dataset_name}_required_columns_available", "type": "required_columns", "columns": names, "dimension": "consistency", "severity": "critical"},
        {"name": f"{dataset_name}_schema_should_not_drift", "type": "schema_drift_check", "expected_columns": names, "allow_extra_columns": False, "dimension": "consistency", "severity": "warning"},
    ]
    for col in columns:
        rules.extend(suggest_rules_for_column(col["name"], col.get("type", "string")))
    return {"dataset": dataset_name, "source": source_config, "rules": rules}
