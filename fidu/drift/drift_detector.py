import json
import os
from datetime import datetime, timezone

from fidu.drift.history_backend import (
    FileHistoryBackend,
    HistoryBackend,
    resolve_history_backend,
)


def load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def save_json(data: dict, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, default=str)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def infer_columns_from_dataset(dataset_result: dict) -> list:
    """
    Prefer dataset-level columns recorded by engines/connectors. Fall back to
    inferring from rule output details so that legacy results still work.
    """
    declared = dataset_result.get("columns_seen") or dataset_result.get("columns")
    if declared:
        return sorted(set(declared))
    cols = set()
    for rule in dataset_result.get("results", []):
        if rule.get("column"):
            cols.add(rule["column"])
        for c in rule.get("columns") or []:
            cols.add(c)
        details = rule.get("details") or {}
        for c in details.get("actual_columns", []):
            cols.add(c)
    return sorted(cols)


def build_dataset_records(final_output: dict) -> list:
    score_lookup = {
        d["dataset"]: d
        for d in final_output["trust_score_summary"]["dataset_scores"]
    }
    records = []
    for dataset in final_output["datasets"]:
        ds_name = dataset["dataset"]
        ds_score = score_lookup.get(ds_name, {})
        rule_statuses = {}
        for r in dataset["results"]:
            if r.get("is_tool_metadata"):
                continue
            rule_statuses[r["rule_name"]] = {
                "status": r["status"],
                "failed_count": r.get("failed_count"),
                "pass_rate": r.get("pass_rate"),
                "dimension": r.get("dimension"),
                "severity": r.get("severity"),
            }
        records.append({
            "dataset": ds_name,
            "total_rules": dataset.get("total_rules"),
            "passed_rules": dataset.get("passed_rules"),
            "failed_rules": dataset.get("failed_rules"),
            "skipped_rules": dataset.get("skipped_rules", 0),
            "errored_rules": dataset.get("errored_rules", 0),
            "trust_score": ds_score.get("trust_score"),
            "grade": ds_score.get("grade"),
            "grade_reason": ds_score.get("grade_reason"),
            "critical_failures": ds_score.get("critical_failures"),
            "warning_failures": ds_score.get("warning_failures"),
            "dimension_scores": ds_score.get("dimension_scores", {}),
            "rule_statuses": rule_statuses,
            "columns_seen": infer_columns_from_dataset(dataset),
        })
    return records


def build_run_record(final_output: dict) -> dict:
    return {
        "run_timestamp": _utcnow_iso(),
        "project": final_output.get("project"),
        "engine": final_output.get("engine"),
        "tool": final_output.get("tool"),
        "execution_mode": final_output.get("execution_mode"),
        "overall_trust_score": final_output["trust_score_summary"]["overall_trust_score"],
        "overall_grade": final_output["trust_score_summary"]["overall_grade"],
        "datasets": build_dataset_records(final_output),
    }


def append_run_history(final_output: dict, backend: HistoryBackend) -> dict:
    """Append a new run record via the configured backend.

    Accepts a ``HistoryBackend`` instance so callers can swap in S3, Postgres,
    or an in-memory store for tests without touching the detector. For the
    historical "just give me a path" call sites, build a ``FileHistoryBackend``
    and pass it in.
    """
    history = backend.load()
    history["runs"].append(build_run_record(final_output))
    backend.save(history)
    return history


def _safe_score_drop(prev_score, curr_score):
    if prev_score is None or curr_score is None:
        return None
    return prev_score - curr_score


def detect_drift(
    history: dict,
    score_drop_threshold: float = None,
    dimension_drop_threshold: float = None,
) -> dict:
    from fidu.core.constants import DRIFT_DEFAULT_DIMENSION_DROP, DRIFT_DEFAULT_SCORE_DROP

    if score_drop_threshold is None:
        score_drop_threshold = DRIFT_DEFAULT_SCORE_DROP
    if dimension_drop_threshold is None:
        dimension_drop_threshold = DRIFT_DEFAULT_DIMENSION_DROP
    runs = history.get("runs", [])
    if len(runs) < 2:
        return {
            "status": "insufficient_history",
            "message": "At least two runs are required for drift detection.",
            "alerts": [],
        }
    prev, curr = runs[-2], runs[-1]
    alerts = []
    drop = _safe_score_drop(
        prev.get("overall_trust_score"), curr.get("overall_trust_score")
    )
    if drop is not None and drop >= score_drop_threshold:
        alerts.append({
            "type": "overall_score_drop", "severity": "warning",
            "previous_score": prev.get("overall_trust_score"),
            "current_score": curr.get("overall_trust_score"),
            "drop": round(drop, 2),
            "message": f"Overall trust score dropped by {round(drop, 2)} points.",
        })
    prev_ds = {d["dataset"]: d for d in prev["datasets"]}
    curr_ds = {d["dataset"]: d for d in curr["datasets"]}
    for name, cur in curr_ds.items():
        old = prev_ds.get(name)
        if not old:
            alerts.append({"type": "new_dataset", "severity": "info", "dataset": name,
                           "message": f"New dataset detected: {name}"})
            continue
        ds_drop = _safe_score_drop(old.get("trust_score"), cur.get("trust_score"))
        if ds_drop is not None and ds_drop >= score_drop_threshold:
            alerts.append({
                "type": "dataset_score_drop", "severity": "warning", "dataset": name,
                "previous_score": old.get("trust_score"),
                "current_score": cur.get("trust_score"),
                "drop": round(ds_drop, 2),
            })
        for rname, current_rule in cur.get("rule_statuses", {}).items():
            previous_rule = old.get("rule_statuses", {}).get(rname)
            if not previous_rule:
                alerts.append({"type": "new_rule", "severity": "info",
                               "dataset": name, "rule_name": rname})
            elif previous_rule["status"] == "passed" and current_rule["status"] == "failed":
                alerts.append({
                    "type": "rule_regression",
                    "severity": "critical" if current_rule.get("severity") == "critical" else "warning",
                    "dataset": name, "rule_name": rname,
                    "current_failed_count": current_rule["failed_count"],
                })
        for rname in old.get("rule_statuses", {}):
            if rname not in cur.get("rule_statuses", {}):
                alerts.append({"type": "missing_rule", "severity": "warning",
                               "dataset": name, "rule_name": rname})
        for dim, cdet in cur.get("dimension_scores", {}).items():
            odet = old.get("dimension_scores", {}).get(dim)
            if odet:
                dd = odet.get("score", 0) - cdet.get("score", 0)
                if dd >= dimension_drop_threshold:
                    alerts.append({"type": "dimension_score_drop", "severity": "warning",
                                   "dataset": name, "dimension": dim, "drop": round(dd, 2)})
        old_cols, cur_cols = set(old.get("columns_seen", [])), set(cur.get("columns_seen", []))
        added, removed = sorted(cur_cols - old_cols), sorted(old_cols - cur_cols)
        if added:
            alerts.append({"type": "schema_columns_added", "severity": "info",
                           "dataset": name, "added_columns": added})
        if removed:
            alerts.append({"type": "schema_columns_removed", "severity": "critical",
                           "dataset": name, "removed_columns": removed})
    for name in prev_ds:
        if name not in curr_ds:
            alerts.append({"type": "missing_dataset", "severity": "critical",
                           "dataset": name})
    return {
        "status": "completed",
        "previous_run_timestamp": prev["run_timestamp"],
        "current_run_timestamp": curr["run_timestamp"],
        "alert_count": len(alerts),
        "alerts": alerts,
        "history_warnings": history.get("warnings", []),
    }


def run_drift_detection(
    final_output: dict,
    history_path: str = "outputs/history/dq_run_history.json",
    drift_output_path: str = "outputs/drift/drift_report.json",
    drift_config: dict | None = None,
    backend: HistoryBackend | None = None,
) -> dict:
    """Append the run to history, run drift detection, and persist the report.

    Backend resolution precedence:
    1. Explicit ``backend`` kwarg (library callers injecting a custom store).
    2. ``drift_config['history_backend']`` — either a ``HistoryBackend``
       instance or a ``{"type": ...}`` spec resolved through the registry.
    3. Default: ``FileHistoryBackend(history_path)`` so existing configs
       keep working unchanged.
    """
    if backend is None:
        if drift_config is not None:
            backend = resolve_history_backend(history_path, drift_config)
        else:
            backend = FileHistoryBackend(history_path)
    history = append_run_history(final_output, backend)
    report = detect_drift(history)
    report["history_backend"] = backend.describe()
    save_json(report, drift_output_path)
    return report
