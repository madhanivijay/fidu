import json
import os
import subprocess

from fidu.tool_adapters.base_tool_adapter import BaseToolAdapter
from fidu.translators.soda_translator import SodaTranslator

DEFAULT_SODA_TIMEOUT_SECONDS = 600


class SodaToolAdapter(BaseToolAdapter):
    """
    Soda adapter.

    Modes:
    - translate_only: emits a SodaCL artifact and marks every source rule as
      ``skipped`` so trust score does not pretend execution happened.
    - execute_cli: runs ``soda scan`` with ``-srf`` and parses the JSON scan
      results back into per-rule outcomes.
    """

    tool_name = "soda"

    def run_dataset(self, dataset_rules: dict, tool_config: dict) -> dict:
        artifact_dir = tool_config.get("artifact_dir", "outputs/tool_artifacts/soda")
        table_name = tool_config.get("table_name")
        translator = SodaTranslator()
        artifact_path = translator.write_artifact(dataset_rules, artifact_dir, table_name)

        execution_mode = tool_config.get("execution_mode", "translate_only")
        source_rules = self._executable_source_rules(dataset_rules)

        if execution_mode == "translate_only":
            rule_results = [
                self._build_skipped_rule_result(rule, "translate_only", artifact_path)
                for rule in source_rules
            ]
            metadata = self._build_tool_metadata_result(
                rule_name="soda_artifact_generated",
                status="passed",
                message="SodaCL artifact generated. DQ checks were not executed because execution_mode=translate_only.",
                artifact_path=artifact_path,
            )
        elif execution_mode == "execute_cli":
            rule_results, metadata = self._execute_soda_cli(
                source_rules, artifact_path, tool_config
            )
        else:
            rule_results = [
                self._build_skipped_rule_result(
                    rule,
                    f"unsupported_execution_mode:{execution_mode}",
                    artifact_path,
                )
                for rule in source_rules
            ]
            metadata = self._build_tool_metadata_result(
                rule_name="soda_invalid_execution_mode",
                status="failed",
                message=f"Unsupported Soda execution_mode: {execution_mode}",
                artifact_path=artifact_path,
                severity="critical",
            )

        return self._compose_dataset_result(
            dataset_rules, rule_results, metadata, artifact_path
        )

    def _execute_soda_cli(self, source_rules, artifact_path, tool_config):
        configuration_file = tool_config.get("configuration_file", "configuration.yml")
        data_source = tool_config.get("data_source", "default")
        soda_binary = tool_config.get("soda_binary", "soda")
        timeout_s = tool_config.get("timeout_seconds", DEFAULT_SODA_TIMEOUT_SECONDS)

        scan_results_path = os.path.join(
            os.path.dirname(artifact_path),
            f"{os.path.splitext(os.path.basename(artifact_path))[0]}_scan_results.json",
        )

        command = [
            soda_binary, "scan",
            "-d", data_source,
            "-c", configuration_file,
            "-srf", scan_results_path,
            artifact_path,
        ]

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_s,
            )
        except FileNotFoundError as exc:
            metadata = self._build_tool_metadata_result(
                rule_name="soda_cli_missing",
                status="failed",
                message="Soda CLI binary not found. Install soda-core or switch execution_mode to translate_only.",
                artifact_path=artifact_path,
                severity="critical",
                error=str(exc),
            )
            rule_results = [
                self._build_skipped_rule_result(rule, "soda_cli_missing", artifact_path)
                for rule in source_rules
            ]
            return rule_results, metadata
        except subprocess.TimeoutExpired as exc:
            metadata = self._build_tool_metadata_result(
                rule_name="soda_cli_timeout",
                status="failed",
                message=f"Soda CLI exceeded timeout of {timeout_s}s.",
                artifact_path=artifact_path,
                severity="critical",
                error=str(exc),
            )
            rule_results = [
                self._build_skipped_rule_result(rule, "soda_cli_timeout", artifact_path)
                for rule in source_rules
            ]
            return rule_results, metadata

        scan_payload = self._read_scan_results(scan_results_path)
        rule_results = self._map_scan_results_to_rules(
            source_rules, scan_payload, artifact_path
        )

        metadata_status = "passed" if completed.returncode == 0 else "failed"
        metadata = self._build_tool_metadata_result(
            rule_name="soda_cli_scan",
            status=metadata_status,
            message=f"Soda CLI finished with return code {completed.returncode}.",
            artifact_path=artifact_path,
            severity="critical" if metadata_status == "failed" else "info",
            output=completed.stdout,
            error=completed.stderr,
        )
        return rule_results, metadata

    def _read_scan_results(self, scan_results_path: str):
        if not os.path.exists(scan_results_path):
            return None
        try:
            with open(scan_results_path, encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError):
            return None

    def _map_scan_results_to_rules(self, source_rules, scan_payload, artifact_path):
        check_index = self._index_soda_checks(scan_payload)
        results = []
        for rule in source_rules:
            check = check_index.get(rule["name"]) or check_index.get(rule["name"].lower())
            if check is None:
                results.append(
                    self._build_skipped_rule_result(
                        rule, "no_matching_soda_check", artifact_path
                    )
                )
                continue

            outcome = (check.get("outcome") or "").lower()
            metric_value = check.get("value")
            row_count = check.get("rowCount") or check.get("row_count")
            failed = (
                int(metric_value)
                if isinstance(metric_value, (int, float)) and outcome != "pass"
                else (0 if outcome == "pass" else 1)
            )
            status_map = {"pass": "passed", "fail": "failed", "warn": "failed"}
            status = status_map.get(outcome, "error")
            results.append(
                self._build_executed_rule_result(
                    rule,
                    status=status,
                    total_rows=row_count,
                    failed_count=failed,
                    message=check.get("definition") or "",
                    details={"soda_outcome": outcome, "soda_value": metric_value},
                    artifact_path=artifact_path,
                )
            )
        return results

    def _index_soda_checks(self, scan_payload):
        if not scan_payload:
            return {}
        index = {}
        for check in scan_payload.get("checks", []) or []:
            name = check.get("name") or check.get("identifier")
            if name:
                index[name] = check
                index[name.lower()] = check
        return index
