import json
import math
import os

import pandas as pd

from fidu.core.constants import OUTPUT_SCHEMA_VERSION


def ensure_dir(path: str):
    if path:
        os.makedirs(path, exist_ok=True)


def _sanitize_for_json(obj):
    """Replace NaN/Inf floats with None so the emitted file is valid RFC 8259 JSON.

    Pandas-derived ``failed_sample`` rows can contain NaN where the source had
    nulls. The default ``json.dump`` would emit literal ``NaN`` tokens, which
    strict parsers (browsers, jq, Postgres ``->>``) reject.
    """
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    return obj


def write_json_result(result: dict, output_path: str):
    ensure_dir(os.path.dirname(output_path))
    versioned = {"schema_version": OUTPUT_SCHEMA_VERSION, **result}
    payload = _sanitize_for_json(versioned)
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, default=str, allow_nan=False)


def write_rule_results_csv(final_output: dict, output_path: str):
    rows = []
    for dataset in final_output["datasets"]:
        for rule in dataset["results"]:
            rows.append({
                "dataset": dataset["dataset"], "rule_name": rule["rule_name"],
                "rule_type": rule["rule_type"], "dimension": rule.get("dimension"),
                "severity": rule.get("severity"), "status": rule.get("status"),
                "total_rows": rule.get("total_rows"), "failed_count": rule.get("failed_count"),
                "pass_rate": rule.get("pass_rate")
            })
    ensure_dir(os.path.dirname(output_path))
    pd.DataFrame(rows).to_csv(output_path, index=False)


def write_scorecard_csv(final_output: dict, output_path: str):
    rows = []
    for ds in final_output["trust_score_summary"]["dataset_scores"]:
        rows.append({"dataset": ds["dataset"], "dimension": "overall", "score": ds["trust_score"], "grade": ds["grade"], "critical_failures": ds["critical_failures"], "warning_failures": ds["warning_failures"]})
        for dim, detail in ds["dimension_scores"].items():
            rows.append({"dataset": ds["dataset"], "dimension": dim, "score": detail["score"], "grade": "", "critical_failures": "", "warning_failures": "", "failed_rules": detail["failed_rules"], "total_rules": detail["total_rules"]})
    ensure_dir(os.path.dirname(output_path))
    pd.DataFrame(rows).to_csv(output_path, index=False)


def write_failed_rows(final_output: dict, output_dir: str):
    ensure_dir(output_dir)
    for dataset in final_output["datasets"]:
        for rule in dataset["results"]:
            sample = rule.get("failed_sample", [])
            if sample:
                safe = rule["rule_name"].replace(" ", "_").lower()
                pd.DataFrame(sample).to_csv(os.path.join(output_dir, f"{dataset['dataset']}_{safe}.csv"), index=False)


def write_all_outputs(final_output: dict, output_config: dict):
    write_json_result(final_output, output_config.get("json_path", "outputs/dq_results.json"))
    write_rule_results_csv(final_output, output_config.get("rule_results_csv", "outputs/dq_rule_results.csv"))
    write_scorecard_csv(final_output, output_config.get("scorecard_csv", "outputs/dq_scorecard.csv"))
    write_failed_rows(final_output, output_config.get("failed_rows_dir", "outputs/failed_rows"))
