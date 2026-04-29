from airflow.models import BaseOperator
from airflow.utils.context import Context

from fidu.main import run_from_config


class EnterpriseDQOperator(BaseOperator):
    """
    Airflow operator for Enterprise DQ Kit.

    It supports both native mode and external DQ tool adapter mode because it
    delegates execution to main.run_from_config(config_path).
    """

    template_fields = ("config_path",)

    def __init__(self, config_path: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config_path = config_path

    def execute(self, context: Context):
        self.log.info("Starting Enterprise DQ Operator")
        self.log.info("Config path: %s", self.config_path)

        result = run_from_config(self.config_path)

        score = result["trust_score_summary"]
        drift = result.get("drift_report", {})

        self.log.info("Execution Mode: %s", result.get("execution_mode"))
        self.log.info("Engine: %s", result.get("engine"))
        self.log.info("DQ Tool: %s", result.get("tool"))
        self.log.info("Overall Trust Score: %s", score.get("overall_trust_score"))
        self.log.info("Overall Grade: %s", score.get("overall_grade"))
        self.log.info("Drift Status: %s", drift.get("status"))
        self.log.info("Drift Alerts: %s", drift.get("alert_count", 0))

        return result
