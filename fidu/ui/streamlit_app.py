import json
import os
import tempfile

import pandas as pd
import plotly.express as px
import streamlit as st
import yaml

from fidu.core.profiler import profile_dataframe
from fidu.main import run_from_config
from fidu.tools.profile_and_suggest_rules import build_rules_from_profile


def _ensure_session_workspace() -> str:
    workspace = st.session_state.get("dq_workspace")
    if workspace and os.path.isdir(workspace):
        return workspace
    holder = tempfile.TemporaryDirectory(prefix="dq_kit_ui_")
    st.session_state["_dq_workspace_holder"] = holder
    st.session_state["dq_workspace"] = holder.name
    for sub in ("data", "rules", "configs", "outputs"):
        os.makedirs(os.path.join(holder.name, sub), exist_ok=True)
    return holder.name

st.set_page_config(page_title="Enterprise DQ Kit", page_icon="✅", layout="wide")

def flatten_rule_results(final_output: dict) -> pd.DataFrame:
    rows = []
    for dataset in final_output["datasets"]:
        for rule in dataset["results"]:
            rows.append({
                "dataset": dataset["dataset"],
                "rule_name": rule["rule_name"],
                "rule_type": rule["rule_type"],
                "dimension": rule.get("dimension"),
                "severity": rule.get("severity"),
                "status": rule.get("status"),
                "total_rows": rule.get("total_rows"),
                "failed_count": rule.get("failed_count"),
                "pass_rate": rule.get("pass_rate"),
            })
    return pd.DataFrame(rows)

def flatten_scorecard(final_output: dict) -> pd.DataFrame:
    rows = []
    for ds in final_output["trust_score_summary"]["dataset_scores"]:
        rows.append({"dataset": ds["dataset"], "dimension": "overall", "score": ds["trust_score"], "grade": ds["grade"]})
        for dim, detail in ds["dimension_scores"].items():
            rows.append({"dataset": ds["dataset"], "dimension": dim, "score": detail["score"], "grade": ""})
    return pd.DataFrame(rows)

st.title("Enterprise Data Quality Kit")
st.caption("Tool-agnostic DQ execution, trust scoring, drift detection, and scorecard reporting.")

with st.sidebar:
    st.header("Run Configuration")
    mode = st.radio("Choose mode", ["Use existing config", "Upload CSV quick demo"])
    if mode == "Use existing config":
        config_path = st.text_input("Config path", value="configs/dq_config.yaml")
        run_button = st.button("Run DQ Checks", type="primary")
    else:
        uploaded_file = st.file_uploader("Upload CSV", type=["csv"])
        dataset_name = st.text_input("Dataset name", value="uploaded_dataset")
        run_button = st.button("Run Quick Profiling Demo", type="primary")

if mode == "Use existing config" and run_button:
    try:
        st.session_state["dq_result"] = run_from_config(config_path)
        st.success("DQ execution completed.")
    except Exception as e:
        st.error(str(e))

if mode == "Upload CSV quick demo" and run_button:
    if uploaded_file is None:
        st.warning("Please upload a CSV file.")
    else:
        try:
            workspace = _ensure_session_workspace()
            csv_path = os.path.join(workspace, "data", f"{dataset_name}.csv")
            with open(csv_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            df = pd.read_csv(csv_path)
            profile = profile_dataframe(df)
            source_config = {"type": "local_file", "format": "csv", "path": csv_path}
            rules = build_rules_from_profile(dataset_name, source_config, profile, draft=False)
            for rule in rules["rules"]:
                rule["draft"] = False
                rule["review_status"] = "approved"
            rules_path = os.path.join(workspace, "rules", f"{dataset_name}_ui_rules.yaml")
            with open(rules_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(rules, f, sort_keys=False)
            outputs_dir = os.path.join(workspace, "outputs")
            config = {
                "project": {"name": "enterprise_dq_ui_demo"},
                "execution": {"mode": "native", "engine": "pandas", "fail_on_critical": False, "fail_on_critical_drift": False},
                "outputs": {
                    "json_path": os.path.join(outputs_dir, "dq_results.json"),
                    "rule_results_csv": os.path.join(outputs_dir, "dq_rule_results.csv"),
                    "scorecard_csv": os.path.join(outputs_dir, "dq_scorecard.csv"),
                    "failed_rows_dir": os.path.join(outputs_dir, "failed_rows"),
                },
                "drift": {
                    "enabled": True,
                    "history_path": os.path.join(outputs_dir, "history", "dq_run_history.json"),
                    "drift_output_path": os.path.join(outputs_dir, "drift", "drift_report.json"),
                },
                "datasets": [{"name": dataset_name, "rules_file": rules_path}],
            }
            config_path = os.path.join(workspace, "configs", f"{dataset_name}_ui_config.yaml")
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(config, f, sort_keys=False)
            st.session_state["dq_result"] = run_from_config(config_path)
            st.success("Quick profiling demo completed.")
        except Exception as e:
            st.error(str(e))

if "dq_result" in st.session_state:
    final_output = st.session_state["dq_result"]
    score = final_output["trust_score_summary"]["overall_trust_score"]
    grade = final_output["trust_score_summary"]["overall_grade"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Overall Trust Score", score)
    c2.metric("Overall Grade", grade)
    c3.metric("Backend", final_output.get("engine") or final_output.get("tool") or "unknown")
    c4.metric("Datasets", len(final_output["datasets"]))

    if final_output.get("validation_warnings"):
        with st.expander("Validation warnings"):
            for warning in final_output["validation_warnings"]:
                st.warning(warning)

    scorecard_df = flatten_scorecard(final_output)
    rule_df = flatten_rule_results(final_output)

    st.subheader("Dimension Scorecard")
    chart_df = scorecard_df[scorecard_df["dimension"] != "overall"]
    if not chart_df.empty:
        fig = px.bar(chart_df, x="dimension", y="score", color="dataset", barmode="group", range_y=[0, 100], title="DQ Dimension Scores")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Rule Results")
    st.dataframe(rule_df, use_container_width=True)

    failed_rules = rule_df[rule_df["status"] == "failed"]
    st.subheader("Failed Rules")
    if failed_rules.empty:
        st.success("No failed rules.")
    else:
        st.dataframe(failed_rules, use_container_width=True)

    st.subheader("Drift Detection")
    drift_report = final_output.get("drift_report")
    if not drift_report:
        st.info("No drift report available.")
    elif drift_report["status"] == "insufficient_history":
        st.info(drift_report["message"])
    elif drift_report["status"] == "disabled":
        st.info("Drift detection disabled.")
    else:
        alert_count = drift_report.get("alert_count", 0)
        if alert_count == 0:
            st.success("No drift detected.")
        else:
            st.warning(f"{alert_count} drift alert(s) detected.")
            st.dataframe(pd.DataFrame(drift_report["alerts"]), use_container_width=True)

    with st.expander("Raw JSON Output"):
        st.json(final_output)

    st.download_button("Download JSON Result", data=json.dumps(final_output, indent=2, default=str), file_name="dq_results.json", mime="application/json")
    st.download_button("Download Rule Results CSV", data=rule_df.to_csv(index=False), file_name="dq_rule_results.csv", mime="text/csv")
    st.download_button("Download Scorecard CSV", data=scorecard_df.to_csv(index=False), file_name="dq_scorecard.csv", mime="text/csv")
