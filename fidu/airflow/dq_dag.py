"""Sample Airflow DAG for the Enterprise DQ Kit.

Deployment: copy ``dq_dag.py`` and ``dq_operator.py`` into your Airflow
``dags/`` folder (or a folder on Airflow's DAGs path). The import below uses a
flat module name so that it works once both files sit alongside each other in
that folder. Inside the source repo we use the same flat import by inserting
this folder onto ``sys.path``.
"""

import os
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.empty import EmptyOperator

# Ensure ``dq_operator`` is importable both when this file is dropped into a
# ``dags/`` folder *and* when running from the source repo where it sits next
# to dq_operator.py.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from fidu.airflow.dq_operator import EnterpriseDQOperator  # noqa: E402

DEFAULT_ARGS = {
    "owner": "data_quality",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

# Resolve the demo config path relative to this DAG file so the DAG works from
# any Airflow worker's cwd (Airflow's cwd is typically the dags folder, but
# this is safer).
# _THIS_DIR is fidu/airflow/ — go up two levels to reach the repo root.
_REPO_ROOT = os.path.dirname(os.path.dirname(_THIS_DIR))
_NATIVE_CONFIG = os.path.join(_REPO_ROOT, "configs", "dq_config.yaml")
_SODA_CONFIG = os.path.join(_REPO_ROOT, "configs", "dq_config_soda.yaml")


with DAG(
    dag_id="enterprise_dq_starter_kit_demo",
    default_args=DEFAULT_ARGS,
    description="Enterprise DQ Kit demo DAG",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["data-quality", "dq", "trust-score"],
) as dag:

    start = EmptyOperator(task_id="start")

    run_native_dq_checks = EnterpriseDQOperator(
        task_id="run_native_dq_checks",
        config_path=_NATIVE_CONFIG,
    )

    run_soda_translation = EnterpriseDQOperator(
        task_id="run_soda_translation",
        config_path=_SODA_CONFIG,
    )

    end = EmptyOperator(task_id="end")

    start >> run_native_dq_checks >> run_soda_translation >> end
