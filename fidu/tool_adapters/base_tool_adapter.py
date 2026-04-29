from abc import ABC, abstractmethod

from fidu.core.rule_filter import filter_executable_rules

SKIPPED_PASS_RATE = None
TOOL_METADATA_DIMENSION = "tool_execution"


class BaseToolAdapter(ABC):
    """
    Base interface for external DQ tool adapters.

    Adapters must return one rule-result per *source rule* so that downstream
    consumers (trust score, drift, scorecard, UI) see the same shape regardless
    of execution mode. They may also append a separate metadata record that
    describes the tool execution itself (artifact path, CLI exit status...).
    """

    tool_name: str = "unknown"

    @abstractmethod
    def run_dataset(self, dataset_rules: dict, tool_config: dict) -> dict:
        """Return a standardized dataset result."""
        raise NotImplementedError

    def _build_skipped_rule_result(
        self,
        source_rule: dict,
        skip_reason: str,
        artifact_path: str = None,
    ) -> dict:
        """One per source rule, used when the tool only translated and did not execute."""
        return {
            "rule_name": source_rule["name"],
            "rule_type": source_rule.get("type"),
            "column": source_rule.get("column"),
            "columns": source_rule.get("columns"),
            "dimension": source_rule.get("dimension", "validity"),
            "severity": source_rule.get("severity", "warning"),
            "status": "skipped",
            "total_rows": None,
            "failed_count": 0,
            "pass_rate": SKIPPED_PASS_RATE,
            "tool": self.tool_name,
            "artifact_path": artifact_path,
            "skip_reason": skip_reason,
            "failed_sample": [],
        }

    def _build_executed_rule_result(
        self,
        source_rule: dict,
        status: str,
        total_rows: int = None,
        failed_count: int = 0,
        message: str = "",
        details: dict = None,
        artifact_path: str = None,
    ) -> dict:
        if total_rows in (None, 0):
            pass_rate = None if total_rows is None else 0.0
        else:
            pass_rate = round((total_rows - failed_count) / total_rows, 4)
        return {
            "rule_name": source_rule["name"],
            "rule_type": source_rule.get("type"),
            "column": source_rule.get("column"),
            "columns": source_rule.get("columns"),
            "dimension": source_rule.get("dimension", "validity"),
            "severity": source_rule.get("severity", "warning"),
            "status": status,
            "total_rows": total_rows,
            "failed_count": failed_count,
            "pass_rate": pass_rate,
            "tool": self.tool_name,
            "artifact_path": artifact_path,
            "message": message,
            "details": details or {},
            "failed_sample": [],
        }

    def _build_tool_metadata_result(
        self,
        rule_name: str,
        status: str,
        message: str,
        artifact_path: str = None,
        severity: str = "info",
        output: str = "",
        error: str = "",
    ) -> dict:
        """Describes the tool execution itself (not a rule)."""
        return {
            "rule_name": rule_name,
            "rule_type": f"{self.tool_name}_tool_execution",
            "column": None,
            "columns": None,
            "dimension": TOOL_METADATA_DIMENSION,
            "severity": severity,
            "status": status,
            "total_rows": None,
            "failed_count": 0 if status == "passed" else 1,
            "pass_rate": SKIPPED_PASS_RATE,
            "tool": self.tool_name,
            "artifact_path": artifact_path,
            "message": message,
            "output": output,
            "error": error,
            "is_tool_metadata": True,
            "failed_sample": [],
        }

    def _executable_source_rules(self, dataset_rules: dict) -> list:
        return filter_executable_rules(dataset_rules.get("rules", []))

    def _compose_dataset_result(
        self,
        dataset_rules: dict,
        rule_results: list,
        tool_metadata: dict,
        artifact_path: str,
    ) -> dict:
        all_results = list(rule_results)
        if tool_metadata is not None:
            all_results.append(tool_metadata)
        rule_only_results = [r for r in all_results if not r.get("is_tool_metadata")]
        return {
            "dataset": dataset_rules["dataset"],
            "source": dataset_rules.get("source", {}),
            "tool_execution": {
                "tool": self.tool_name,
                "artifact_path": artifact_path,
                "status": tool_metadata["status"] if tool_metadata else "unknown",
            },
            "total_rules": len(rule_only_results),
            "passed_rules": sum(1 for r in rule_only_results if r["status"] == "passed"),
            "failed_rules": sum(1 for r in rule_only_results if r["status"] == "failed"),
            "skipped_rules": sum(1 for r in rule_only_results if r["status"] == "skipped"),
            "errored_rules": sum(1 for r in rule_only_results if r["status"] == "error"),
            "results": all_results,
        }
