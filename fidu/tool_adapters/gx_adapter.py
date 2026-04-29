from fidu.tool_adapters.base_tool_adapter import BaseToolAdapter
from fidu.translators.gx_translator import GreatExpectationsTranslator


class GreatExpectationsToolAdapter(BaseToolAdapter):
    """
    Great Expectations adapter.

    translate_only: emits a GX expectation-suite JSON and marks every source
    rule as ``skipped``.
    execute_checkpoint: not implemented (deployment-specific). Reports the same
    skipped per-rule results plus a tool-metadata record describing the gap.
    """

    tool_name = "great_expectations"

    def run_dataset(self, dataset_rules: dict, tool_config: dict) -> dict:
        artifact_dir = tool_config.get(
            "artifact_dir", "outputs/tool_artifacts/great_expectations"
        )
        execution_mode = tool_config.get("execution_mode", "translate_only")
        translator = GreatExpectationsTranslator()
        artifact_path = translator.write_artifact(dataset_rules, artifact_dir)
        source_rules = self._executable_source_rules(dataset_rules)

        if execution_mode == "translate_only":
            rule_results = [
                self._build_skipped_rule_result(rule, "translate_only", artifact_path)
                for rule in source_rules
            ]
            metadata = self._build_tool_metadata_result(
                rule_name="gx_expectation_suite_generated",
                status="passed",
                message="Great Expectations suite generated. DQ checks were not executed because execution_mode=translate_only.",
                artifact_path=artifact_path,
            )
        elif execution_mode == "execute_checkpoint":
            rule_results = [
                self._build_skipped_rule_result(
                    rule, "execute_checkpoint_not_implemented", artifact_path
                )
                for rule in source_rules
            ]
            metadata = self._build_tool_metadata_result(
                rule_name="gx_checkpoint_execution_not_implemented",
                status="failed",
                message="GX checkpoint execution is environment-specific. Use generated suite with your GX context/checkpoint or implement this adapter method.",
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
                rule_name="gx_invalid_execution_mode",
                status="failed",
                message=f"Unsupported Great Expectations execution_mode: {execution_mode}",
                artifact_path=artifact_path,
                severity="critical",
            )

        return self._compose_dataset_result(
            dataset_rules, rule_results, metadata, artifact_path
        )
