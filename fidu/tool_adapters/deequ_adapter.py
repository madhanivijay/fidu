from fidu.tool_adapters.base_tool_adapter import BaseToolAdapter
from fidu.translators.deequ_translator import DeequTranslator


class DeequToolAdapter(BaseToolAdapter):
    """
    Deequ/PyDeequ adapter.

    translate_only: emits a PyDeequ check script and marks every source rule
    as ``skipped``.
    execute_spark: not implemented (deployment-specific). Same skipped pattern
    plus a tool-metadata record describing the gap.
    """

    tool_name = "deequ"

    def run_dataset(self, dataset_rules: dict, tool_config: dict) -> dict:
        artifact_dir = tool_config.get(
            "artifact_dir", "outputs/tool_artifacts/deequ"
        )
        execution_mode = tool_config.get("execution_mode", "translate_only")
        translator = DeequTranslator()
        artifact_path = translator.write_artifact(dataset_rules, artifact_dir)
        source_rules = self._executable_source_rules(dataset_rules)

        if execution_mode == "translate_only":
            rule_results = [
                self._build_skipped_rule_result(rule, "translate_only", artifact_path)
                for rule in source_rules
            ]
            metadata = self._build_tool_metadata_result(
                rule_name="deequ_check_script_generated",
                status="passed",
                message="PyDeequ check script generated. DQ checks were not executed because execution_mode=translate_only.",
                artifact_path=artifact_path,
            )
        elif execution_mode == "execute_spark":
            rule_results = [
                self._build_skipped_rule_result(
                    rule, "execute_spark_not_implemented", artifact_path
                )
                for rule in source_rules
            ]
            metadata = self._build_tool_metadata_result(
                rule_name="deequ_spark_execution_not_implemented",
                status="failed",
                message="Deequ Spark execution is environment-specific. Use generated script in your Spark/EMR/Databricks runtime or implement this adapter method.",
                artifact_path=artifact_path,
                severity="warning",
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
                rule_name="deequ_invalid_execution_mode",
                status="failed",
                message=f"Unsupported Deequ execution_mode: {execution_mode}",
                artifact_path=artifact_path,
                severity="critical",
            )

        return self._compose_dataset_result(
            dataset_rules, rule_results, metadata, artifact_path
        )
