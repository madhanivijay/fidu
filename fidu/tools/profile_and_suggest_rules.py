import argparse

import pandas as pd
import yaml

from fidu.core.profiler import profile_dataframe
from fidu.core.rule_suggester import default_dimension, default_severity


def load_data(path: str, file_format: str):
    if file_format == "csv":
        return pd.read_csv(path)
    if file_format == "parquet":
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported format: {file_format}")

def make_column_rule(column_name: str, rule_type: str) -> dict:
    return {"name": f"{column_name}_{rule_type}", "type": rule_type, "column": column_name, "dimension": default_dimension(rule_type), "severity": default_severity(rule_type)}

def mark_rules_as_draft(rules: list) -> list:
    for rule in rules:
        rule["draft"] = True
        rule["review_status"] = "pending"
        rule["review_comment"] = "Auto-generated from profiling. Please review before production use."
    return rules

def build_rules_from_profile(dataset_name: str, source_config: dict, profile: dict, draft: bool = True) -> dict:
    rules = []
    names = [c["name"] for c in profile["columns"]]
    rules.append({"name": f"{dataset_name}_required_columns_available", "type": "required_columns", "columns": names, "dimension": "consistency", "severity": "critical"})
    rules.append({"name": f"{dataset_name}_schema_should_not_drift", "type": "schema_drift_check", "expected_columns": names, "allow_extra_columns": False, "dimension": "consistency", "severity": "warning"})
    rules.append({"name": f"{dataset_name}_minimum_row_volume", "type": "row_count_min", "value": max(1, int(profile["row_count"] * 0.8)), "dimension": "volume", "severity": "critical"})
    for col in profile["columns"]:
        name = col["name"]
        typ = col["inferred_type"]
        if col["null_rate"] == 0:
            rules.append(make_column_rule(name, "not_null"))
        if col["distinct_rate"] == 1:
            rules.append(make_column_rule(name, "unique"))
        if typ == "numeric" and col.get("min") is not None:
            rules.append({"name": f"{name}_between_profiled_range", "type": "between", "column": name, "min_value": col["min"], "max_value": col["max"], "dimension": "validity", "severity": "warning"})
        if typ == "string":
            top_values = col.get("top_values", {})
            if 1 < col.get("distinct_count", 0) <= 20:
                rules.append({"name": f"{name}_accepted_values", "type": "accepted_values", "column": name, "values": list(top_values.keys()), "dimension": "validity", "severity": "warning"})
            if "email" in name.lower():
                rules.append({"name": f"{name}_email_format_valid", "type": "regex_match", "column": name, "pattern": "^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$", "dimension": "validity", "severity": "warning"})
        if typ == "date":
            rules.append({"name": f"{name}_freshness", "type": "freshness", "column": name, "max_age_days": 1, "dimension": "freshness", "severity": "critical"})
    return {"dataset": dataset_name, "source": source_config, "profile_summary": profile, "rules": mark_rules_as_draft(rules) if draft else rules}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--source-type", default="local_file")
    parser.add_argument("--format", default="csv")
    parser.add_argument("--path", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--approved", action="store_true")
    args = parser.parse_args()
    df = load_data(args.path, args.format)
    source_config = {"type": args.source_type, "format": args.format, "path": args.path}
    rules = build_rules_from_profile(args.dataset, source_config, profile_dataframe(df), draft=not args.approved)
    with open(args.output, "w", encoding="utf-8") as file:
        yaml.safe_dump(rules, file, sort_keys=False)
    print(f"Profile-based rules written to: {args.output}")

if __name__ == "__main__":
    main()
