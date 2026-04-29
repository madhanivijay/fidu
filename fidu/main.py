import argparse
import os
import sys

from fidu.core.config_validator import (
    validate_dataset_config,
    validate_dataset_for_tool,
    validate_top_level_config,
)
from fidu.core.constants import EXIT_CRITICAL_DRIFT, EXIT_CRITICAL_FAILURES, EXIT_OK
from fidu.core.dq_executor import DQExecutor
from fidu.core.logging import Timer, configure_logging, get_logger, new_run_id
from fidu.core.paths import resolve_relative
from fidu.core.result_writer import write_all_outputs
from fidu.core.rule_parser import load_yaml
from fidu.core.trust_score import calculate_project_trust_score
from fidu.drift.drift_detector import run_drift_detection
from fidu.tool_adapters.tool_adapter_factory import get_tool_adapter

_log = get_logger("main")


def has_critical_failures(final_output: dict) -> bool:
    return any(
        rule.get("severity") == "critical" and rule.get("status") == "failed"
        for ds in final_output["datasets"]
        for rule in ds["results"]
    )


def has_critical_drift(drift_report: dict) -> bool:
    return any(
        alert.get("severity") == "critical"
        for alert in drift_report.get("alerts", [])
    )


def _resolve_source_path(source: dict, base_dir: str) -> dict:
    """Resolve relative ``path`` inside a rule-file ``source`` block."""
    if not source or "path" not in source:
        return source
    return {**source, "path": resolve_relative(base_dir, source["path"])}


def _load_dataset_rules(rules_file: str) -> dict:
    rules = load_yaml(rules_file)
    rules_dir = os.path.dirname(os.path.abspath(rules_file))
    if "source" in rules:
        rules["source"] = _resolve_source_path(rules["source"], rules_dir)
    return rules


def _resolve_output_config(output_config: dict, base_dir: str) -> dict:
    if not output_config:
        return output_config
    resolved = {}
    for key, value in output_config.items():
        if isinstance(value, str):
            resolved[key] = resolve_relative(base_dir, value)
        else:
            resolved[key] = value
    return resolved


def _resolve_drift_config(drift_config: dict, base_dir: str) -> dict:
    if not drift_config:
        return drift_config
    resolved = dict(drift_config)
    for key in ("history_path", "drift_output_path"):
        if key in resolved and isinstance(resolved[key], str):
            resolved[key] = resolve_relative(base_dir, resolved[key])
    return resolved


def _resolve_tool_config(tool_config: dict, base_dir: str) -> dict:
    if not tool_config:
        return tool_config
    resolved = dict(tool_config)
    for key in ("artifact_dir", "configuration_file"):
        if key in resolved and isinstance(resolved[key], str):
            resolved[key] = resolve_relative(base_dir, resolved[key])
    return resolved


def _run_tool_dataset(adapter, tool_name: str, dataset_rules: dict, tool_config: dict) -> dict:
    """Run one dataset through a tool adapter with the same observability events
    and partial-result safety the native executor provides.

    Emits ``dataset_start`` / ``dataset_complete`` (or ``dataset_error``) so a
    tool-mode run is log-symmetric with native mode -- downstream consumers
    can subscribe to one event stream regardless of execution mode.
    """
    dataset_name = dataset_rules.get("dataset")
    source_type = dataset_rules.get("source", {}).get("type")
    _log.info(
        "dataset_start",
        extra={
            "event": "dataset_start",
            "dataset": dataset_name,
            "tool": tool_name,
            "source_type": source_type,
            "rule_count": len(dataset_rules.get("rules", [])),
        },
    )
    timer = Timer()
    timer.__enter__()
    try:
        result = adapter.run_dataset(dataset_rules, tool_config)
    except Exception as exc:
        timer.__exit__(None, None, None)
        _log.error(
            "dataset_error",
            extra={
                "event": "dataset_error",
                "dataset": dataset_name,
                "tool": tool_name,
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
        )
        return {
            "dataset": dataset_name,
            "source": dataset_rules.get("source", {}),
            "status": "error",
            "error_message": f"{type(exc).__name__}: {exc}",
            "total_rules": 0,
            "passed_rules": 0,
            "failed_rules": 0,
            "skipped_rules": 0,
            "errored_rules": 0,
            "results": [],
            "columns_seen": [],
            "duration_ms": timer.duration_ms,
        }
    timer.__exit__(None, None, None)
    result.setdefault("duration_ms", timer.duration_ms)
    result.setdefault("status", "completed")
    _log.info(
        "dataset_complete",
        extra={
            "event": "dataset_complete",
            "dataset": dataset_name,
            "tool": tool_name,
            "duration_ms": result["duration_ms"],
            "total_rules": result.get("total_rules", 0),
            "passed_rules": result.get("passed_rules", 0),
            "failed_rules": result.get("failed_rules", 0),
            "skipped_rules": result.get("skipped_rules", 0),
            "errored_rules": result.get("errored_rules", 0),
        },
    )
    return result


def run_from_config(config_path: str = "configs/dq_config.yaml") -> dict:
    """Run DQ using a config file. Paths inside the config are resolved relative
    to the directory of the config file itself, so the same config works from
    any cwd (CLI, Airflow, Streamlit).
    """
    configure_logging()
    run_id = new_run_id()
    run_timer = Timer()
    run_timer.__enter__()

    config_path = os.path.abspath(config_path)
    config_dir = os.path.dirname(config_path)
    config = load_yaml(config_path)
    config_warnings = validate_top_level_config(config)

    execution_config = config["execution"]
    execution_mode = execution_config.get("mode", "native")

    _log.info(
        "run_start",
        extra={
            "event": "run_start",
            "project": config["project"]["name"],
            "execution_mode": execution_mode,
            "config_path": config_path,
            "dataset_count": len(config.get("datasets", [])),
        },
    )

    output_config = _resolve_output_config(config.get("outputs", {}), config_dir)
    drift_config = _resolve_drift_config(config.get("drift", {}), config_dir)

    all_results = {
        "project": config["project"]["name"],
        "execution_mode": execution_mode,
        "config_path": config_path,
        "run_id": run_id,
        "validation_warnings": list(config_warnings),
        "datasets": [],
    }

    if execution_mode == "native":
        engine_name = execution_config["engine"]
        all_results["engine"] = engine_name
        executor = DQExecutor(engine_name)

        for dataset in config["datasets"]:
            rules_file = resolve_relative(config_dir, dataset["rules_file"])
            dataset_rules = _load_dataset_rules(rules_file)
            all_results["validation_warnings"].extend(
                validate_dataset_config(engine_name, dataset_rules)
            )
            all_results["datasets"].append(
                executor.safe_execute_dataset_rules(dataset_rules)
            )

    elif execution_mode == "tool":
        tool_name = execution_config["tool"]
        all_results["tool"] = tool_name
        adapter = get_tool_adapter(tool_name)
        raw_tool_config = config.get("tool_config", {}).get(tool_name, {})
        tool_config = _resolve_tool_config(raw_tool_config, config_dir)

        for dataset in config["datasets"]:
            rules_file = resolve_relative(config_dir, dataset["rules_file"])
            dataset_rules = _load_dataset_rules(rules_file)
            all_results["validation_warnings"].extend(
                validate_dataset_for_tool(dataset_rules)
            )
            all_results["datasets"].append(
                _run_tool_dataset(adapter, tool_name, dataset_rules, tool_config)
            )

    else:
        raise ValueError(
            f"Unsupported execution.mode: {execution_mode}. "
            "Use 'native' or 'tool'."
        )

    trust_score = calculate_project_trust_score(all_results)

    final_output = {**all_results, "trust_score_summary": trust_score}

    write_all_outputs(final_output, output_config)

    if drift_config.get("enabled", True):
        drift_report = run_drift_detection(
            final_output,
            drift_config.get(
                "history_path",
                resolve_relative(config_dir, "outputs/history/dq_run_history.json"),
            ),
            drift_config.get(
                "drift_output_path",
                resolve_relative(config_dir, "outputs/drift/drift_report.json"),
            ),
            drift_config=drift_config,
        )
        final_output["drift_report"] = drift_report
    else:
        final_output["drift_report"] = {"status": "disabled", "alerts": []}

    fail_on_critical = execution_config.get("fail_on_critical", False)
    fail_on_critical_drift = execution_config.get("fail_on_critical_drift", False)

    run_timer.__exit__(None, None, None)
    final_output["duration_ms"] = run_timer.duration_ms
    _log.info(
        "run_complete",
        extra={
            "event": "run_complete",
            "project": final_output["project"],
            "execution_mode": execution_mode,
            "overall_trust_score": trust_score["overall_trust_score"],
            "overall_grade": trust_score["overall_grade"],
            "drift_status": final_output["drift_report"].get("status"),
            "drift_alerts": final_output["drift_report"].get("alert_count", 0),
            "duration_ms": run_timer.duration_ms,
        },
    )

    if fail_on_critical and has_critical_failures(final_output):
        _log.error(
            "run_failed_critical_rules",
            extra={"event": "run_failed", "reason": "critical_rule_failures"},
        )
        print("DQ failed because critical rules failed.", file=sys.stderr)
        raise SystemExit(EXIT_CRITICAL_FAILURES)

    if fail_on_critical_drift and has_critical_drift(final_output["drift_report"]):
        _log.error(
            "run_failed_critical_drift",
            extra={"event": "run_failed", "reason": "critical_drift"},
        )
        print("DQ failed because critical drift was detected.", file=sys.stderr)
        raise SystemExit(EXIT_CRITICAL_DRIFT)

    return final_output


def main():
    parser = argparse.ArgumentParser(
        prog="fidu",
        description="fidu — tool-agnostic data quality runner with trust scores and drift detection",
    )
    parser.add_argument(
        "--config",
        default="configs/dq_config.yaml",
        help="Path to DQ config YAML file",
    )
    args = parser.parse_args()

    result = run_from_config(args.config)

    score = result["trust_score_summary"]
    drift = result.get("drift_report", {})
    overall_score = score["overall_trust_score"]
    score_display = "N/A (no executed rules)" if overall_score is None else overall_score

    print("DQ execution completed.")
    print(f"Config: {args.config}")
    print(f"Execution Mode: {result.get('execution_mode')}")
    if result.get("engine"):
        print(f"Engine: {result.get('engine')}")
    if result.get("tool"):
        print(f"DQ Tool: {result.get('tool')}")
    print(f"Overall Trust Score: {score_display}")
    print(f"Overall Grade: {score['overall_grade']}")
    print(f"Grade Reason: {score.get('grade_reason', '')}")
    print(f"Drift Status: {drift.get('status')}")
    print(f"Drift Alerts: {drift.get('alert_count', 0)}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
