# Enterprise DQ Kit

**Enterprise DQ Kit** is a tool-agnostic, extensible data quality utility pack designed for teams that do not want to rebuild separate DQ operators, connectors, rule runners, scorecards, and drift detection for every repository and every platform.

The core idea is simple:

> **Write DQ rules once. Run them across Pandas, Spark, SQL engines, warehouses, lakehouse tables, and file stores.**

This repo includes:

- Config-driven DQ execution
- Common YAML rule schema
- Pandas engine
- Spark engine
- Generic SQL engine
- Local, S3, ADLS, Snowflake, Trino, Databricks SQL, ClickHouse connector templates
- Data Trust Score
- Dimension-level scorecards
- Failed-row samples
- Drift detection across runs
- Rule suggestion intelligence
- Profiling-based rule generation
- Rule review CLI
- Airflow Operator + demo DAG
- Streamlit UI for demo and adoption
- Extensive example configs and documentation

---

## 1. Why this utility exists

Enterprise DQ implementations often become fragmented:

- One repo uses Soda.
- Another uses Great Expectations.
- Another has raw SQL checks.
- Another has custom Spark checks.
- Another validates CSV or Parquet files directly.
- Airflow DAGs duplicate DQ logic.
- Data quality results are pass/fail but not business-readable.
- Drift is usually detected late, after dashboards or downstream pipelines break.

This kit solves that by creating an abstraction layer:

```text
DQ YAML Rules
    ↓
Config Validator
    ↓
Connector Layer
    ↓
Execution Engine
    ↓
Standardized Results
    ↓
Trust Score + Drift Report + Failed Rows
```

---

## 2. Repo structure

```text
fidu/
  airflow/
    dq_operator.py
    dq_dag.py

  configs/
    dq_config.yaml

  connectors/
    base_connector.py
    local_file_connector.py
    s3_file_connector.py
    adls_file_connector.py
    duckdb_connector.py
    snowflake_connector.py
    trino_connector.py
    databricks_sql_connector.py
    clickhouse_connector.py
    spark_file_connector.py

  core/
    dq_executor.py
    config_validator.py
    profiler.py
    result_writer.py
    rule_parser.py
    rule_suggester.py
    trust_score.py

  data/
    orders.csv

  drift/
    drift_detector.py

  engines/
    pandas_engine.py
    spark_engine.py
    sql_engine.py

  intelligence/
    engine_source_matrix.json
    rule_support_matrix.json
    rule_suggestions.json
    source_templates.json

  rules/
    orders_rules.yaml

  tools/
    suggest_rules.py
    profile_and_suggest_rules.py
    review_rules.py

  ui/
    streamlit_app.py

  main.py
  requirements.txt
  requirements-lite.txt
```

---

## 3. Quick start

### 3.1 Create virtual environment

```bash
python -m venv .venv
```

Activate it.

Linux/Mac:

```bash
source .venv/bin/activate
```

Windows:

```bash
.venv\Scripts\activate
```

### 3.2 Install minimal dependencies

For local Pandas + Streamlit demo:

```bash
pip install -r requirements-lite.txt
```

For all connectors:

```bash
pip install -r requirements.txt
```

### 3.3 Run sample DQ

```bash
python main.py
```

Expected outputs:

```text
outputs/dq_results.json
outputs/dq_rule_results.csv
outputs/dq_scorecard.csv
outputs/failed_rows/
outputs/history/dq_run_history.json
outputs/drift/drift_report.json
```

First run shows:

```text
Drift Status: insufficient_history
```

Run it again:

```bash
python main.py
```

Now drift detection has enough history to compare runs.

---

## 4. Configuration model

The main config lives at:

```text
configs/dq_config.yaml
```

Relative paths inside a config (rule files, output directories, drift history, source paths) are resolved against the directory of the config file itself, regardless of the shell's working directory. The shipped sample configs follow this convention by using `../rules/...` and `../outputs/...`.

Example:

```yaml
project:
  name: enterprise_dq_starter_kit

execution:
  engine: pandas
  fail_on_critical: false
  fail_on_critical_drift: false

outputs:
  json_path: outputs/dq_results.json
  rule_results_csv: outputs/dq_rule_results.csv
  scorecard_csv: outputs/dq_scorecard.csv
  failed_rows_dir: outputs/failed_rows

drift:
  enabled: true
  history_path: outputs/history/dq_run_history.json
  drift_output_path: outputs/drift/drift_report.json

datasets:
  - name: orders
    rules_file: rules/orders_rules.yaml
```

---

## 5. Rule schema

Rules are defined in YAML.

Example:

```yaml
dataset: orders

source:
  type: local_file
  format: csv
  path: data/orders.csv

rules:
  - name: order_id_not_null
    type: not_null
    column: order_id
    dimension: completeness
    severity: critical

  - name: amount_between_valid_range
    type: between
    column: amount
    min_value: 0
    max_value: 100000
    dimension: validity
    severity: critical
```

---

## 6. Supported DQ dimensions

The kit supports dimension-level scoring:

| Dimension | Meaning |
|---|---|
| completeness | Required data is present |
| validity | Values conform to allowed formats/ranges |
| uniqueness | Duplicate prevention |
| freshness | Data is recent enough |
| consistency | Schema/type/structure checks |
| volume | Row count thresholds |

---

## 7. Supported rule types

| Rule type | Description |
|---|---|
| not_null | Column must not contain nulls |
| min_value | Column value must be >= threshold |
| max_value | Column value must be <= threshold |
| between | Column value must be within min/max |
| accepted_values | Column value must be within allowed list |
| unique | Single column must be unique |
| duplicate_check | Composite key duplicate check |
| regex_match | Column value must match regex |
| freshness | Date column must be fresh |
| row_count_min | Dataset must have minimum rows |
| row_count_max | Dataset must not exceed maximum rows |
| required_columns | Required columns must exist |
| column_type_check | Column should match expected type |
| schema_drift_check | Expected schema should not drift |

---

## 8. Engines

### Pandas engine

Best for:

- Local CSV
- Local Parquet
- Small/medium datasets
- Fast demos
- CI checks

Config:

```yaml
execution:
  engine: pandas
```

### Spark engine

Best for:

- Large files
- S3 lakes
- ADLS lakes
- Delta tables
- Iceberg tables through Spark catalog

Config:

```yaml
execution:
  engine: spark
```

### SQL engine

Best for:

- Warehouses
- Query engines
- Lakehouse SQL layers

Supported connector templates:

- DuckDB CSV demo
- Snowflake
- Trino
- Databricks SQL
- ClickHouse

Config:

```yaml
execution:
  engine: sql
```

---

## 9. Source examples

### Local CSV

```yaml
source:
  type: local_file
  format: csv
  path: data/orders.csv
```

### S3 Parquet through Pandas

```yaml
source:
  type: s3_file
  format: parquet
  path: s3://my-bucket/raw/orders/
```

### ADLS Parquet through Pandas

```yaml
source:
  type: adls_file
  format: parquet
  path: abfs://container@account.dfs.core.windows.net/raw/orders/
```

### Spark Parquet

```yaml
source:
  type: spark_file
  format: parquet
  path: s3://my-bucket/raw/orders/
```

### Delta through Spark

```yaml
source:
  type: spark_file
  format: delta
  path: s3://my-bucket/delta/orders/
```

### Iceberg through Spark

```yaml
source:
  type: spark_file
  format: iceberg
  table: iceberg_catalog.stage.orders
```

### Iceberg through Trino

```yaml
source:
  type: trino
  catalog: iceberg
  schema: stage
  table: orders
```

### Snowflake

```yaml
source:
  type: snowflake
  database: ANALYTICS
  schema: STAGE
  table: ORDERS
```

### Databricks SQL

```yaml
source:
  type: databricks_sql
  catalog: main
  schema: stage
  table: orders
```

### ClickHouse

```yaml
source:
  type: clickhouse
  database: analytics
  table: orders
```

---

## 10. Environment variables for enterprise connectors

### Snowflake

```bash
export SNOWFLAKE_USER=
export SNOWFLAKE_PASSWORD=
export SNOWFLAKE_ACCOUNT=
export SNOWFLAKE_WAREHOUSE=
export SNOWFLAKE_DATABASE=
export SNOWFLAKE_SCHEMA=
export SNOWFLAKE_ROLE=
```

### Trino

```bash
export TRINO_HOST=
export TRINO_PORT=443
export TRINO_USER=
export TRINO_CATALOG=
export TRINO_SCHEMA=
export TRINO_HTTP_SCHEME=https
```

### Databricks SQL

```bash
export DATABRICKS_SERVER_HOSTNAME=
export DATABRICKS_HTTP_PATH=
export DATABRICKS_ACCESS_TOKEN=
```

### ClickHouse

```bash
export CLICKHOUSE_HOST=
export CLICKHOUSE_PORT=8443
export CLICKHOUSE_USER=
export CLICKHOUSE_PASSWORD=
export CLICKHOUSE_DATABASE=
export CLICKHOUSE_SECURE=true
```

### AWS S3

```bash
export AWS_ACCESS_KEY_ID=
export AWS_SECRET_ACCESS_KEY=
export AWS_SESSION_TOKEN=
```

### Azure Data Lake Storage

```bash
export AZURE_STORAGE_ACCOUNT_NAME=
export AZURE_STORAGE_ACCOUNT_KEY=
export AZURE_TENANT_ID=
export AZURE_CLIENT_ID=
export AZURE_CLIENT_SECRET=
```

---

## 11. Data Trust Score

The kit converts rule results into a dataset-level score.

A rule score is based on pass rate.

```text
rule_score = pass_rate * 100
```

Severity weighting:

| Severity | Weight |
|---|---|
| critical | 1.0 |
| warning | 0.5 |
| info | 0.25 |

Dataset trust score:

```text
weighted average of all rule scores
```

Grades:

| Score / condition | Grade |
|---|---|
| >= 95 | TRUSTED |
| >= 85 | NEEDS_REVIEW |
| >= 70 | UNSTABLE |
| otherwise | HIGH_RISK |
| critical failures + score < 95 | HIGH_RISK |
| no executed rules (translate-only adapter run) | TRANSLATION_ONLY |
| dataset has zero rules to execute | NO_RULES |

`trust_score_summary.dataset_scores[]` always includes a `grade_reason` field. `TRANSLATION_ONLY` and `NO_RULES` datasets contribute `null` to the dataset score and are excluded from the project-level overall score.

---

## 12. Drift detection

Drift detection compares the current run with the previous run. Skipped tool-mode results are filtered before comparison so that a translate-only adapter run does not look like a regression of a previously-executed run. Schema drift is keyed off `columns_seen`, populated by the engine (pandas/Spark) or by the SQL `source.columns` array. If history is corrupt, it is archived under `<history>.corrupt-<timestamp>` and a `history_warnings` field is included in the next drift report.

It detects:

- Overall score drop
- Dataset score drop
- Rule regression
- New rule
- Missing rule
- Dimension score drop
- Schema columns added
- Schema columns removed
- New dataset
- Missing dataset

Outputs:

```text
outputs/history/dq_run_history.json
outputs/drift/drift_report.json
```

To test:

```bash
python main.py
python main.py
```

Then edit `data/orders.csv`, add/remove columns or change values, and run:

```bash
python main.py
```

---

## 13. Streamlit UI

Run:

```bash
streamlit run ui/streamlit_app.py
```

The UI supports:

- Existing config execution
- CSV upload quick demo
- Profiling-based rule generation
- Trust score display
- Dimension scorecard
- Rule result table
- Failed-rule table
- Drift alerts
- Download JSON and CSV outputs

---

## 14. Airflow integration

Files:

```text
airflow/dq_operator.py
airflow/dq_dag.py
```

In a real Airflow repo, copy these into the DAGs folder:

```text
dags/
  dq_operator.py
  dq_dag.py
```

The operator:

- Reads config
- Validates engine/source/rule compatibility
- Runs DQ checks
- Writes output files
- Computes trust score
- Runs drift detection
- Can fail the task on critical DQ failures
- Can fail the task on critical drift alerts

Important: for packaging as a proper Python library, install this repo into the Airflow image and update imports accordingly.

---

## 15. Rule generation

### Name/type-based suggestions

```bash
python tools/suggest_rules.py \
  --dataset orders \
  --source-type local_file \
  --source-format csv \
  --path data/orders.csv \
  --columns "order_id:string,customer_id:string,amount:numeric,status:string,order_date:date,email:string" \
  --output rules/orders_suggested_rules.yaml
```

### Profile-based suggestions

```bash
python tools/profile_and_suggest_rules.py \
  --dataset orders \
  --source-type local_file \
  --format csv \
  --path data/orders.csv \
  --output rules/orders_profiled_rules.yaml
```

By default, profiled rules are generated as draft/pending.

### Generate approved rules directly

```bash
python tools/profile_and_suggest_rules.py \
  --dataset orders \
  --source-type local_file \
  --format csv \
  --path data/orders.csv \
  --output rules/orders_profiled_rules.yaml \
  --approved
```

---

## 16. Rule review CLI

List rules:

```bash
python tools/review_rules.py \
  --file rules/orders_profiled_rules.yaml \
  --action list
```

Approve rule 3:

```bash
python tools/review_rules.py \
  --file rules/orders_profiled_rules.yaml \
  --action approve \
  --index 3
```

Reject rule 5:

```bash
python tools/review_rules.py \
  --file rules/orders_profiled_rules.yaml \
  --action reject \
  --index 5
```

Approve all:

```bash
python tools/review_rules.py \
  --file rules/orders_profiled_rules.yaml \
  --action approve_all
```

---

## 17. Intelligence files

The `intelligence/` folder helps repositories, developers, and AI assistants understand what is supported.

### `engine_source_matrix.json`

Defines which engines support which source types.

### `rule_support_matrix.json`

Defines which rule types are supported, planned, or unsupported by each engine.

### `rule_suggestions.json`

Maps column names, data types, and dimensions to suggested checks.

### `source_templates.json`

Provides ready examples for common platforms.

---

## 18. Extending the kit

### Add a new rule

1. Add support to the engine, for example `engines/pandas_engine.py`.
2. Add support to `engines/spark_engine.py` and/or `engines/sql_engine.py` if needed.
3. Update `intelligence/rule_support_matrix.json`.
4. Add docs.

### Add a new connector

1. Create `connectors/new_connector.py`.
2. Implement either `BaseConnector` or `SQLConnector`.
3. Add it to `connectors/connector_factory.py`.
4. Add it to `intelligence/engine_source_matrix.json`.
5. Add a source template to `intelligence/source_templates.json`.

---

## 19. Product positioning

You can position this as:

> **Enterprise DQ Kit: a configurable utility layer for running standard data quality checks across files, warehouses, query engines, and lakehouse platforms without rebuilding operators per tool or repository.**

Strong selling points:

- Tool-agnostic
- Source-agnostic
- Engine-agnostic
- YAML-first
- Airflow-ready
- UI-ready
- Drift-aware
- Scorecard-driven
- Extensible through intelligence files

---

## 20. Current limitations

This is a strong starter framework, but not a finished commercial SaaS.

Known limitations:

- SQL engine currently supports core rules only.
- SQL regex/freshness/schema/type checks are marked as planned.
- Enterprise connectors are templates and require real credentials/environment setup.
- Spark Delta/Iceberg support depends on Spark session packages/catalog configuration.
- No authentication in Streamlit UI.
- No database-backed result store yet.
- No alerting integration yet.

Recommended next enhancements:

- Slack/Email alerts
- Postgres/Snowflake audit table writer
- Great Expectations/Soda/Deequ translators
- Docker Compose demo
- dbt integration
- YAML schema validation
- Unit tests
- GitHub Actions CI
- Python package setup

---

## 21. Recommended roadmap

### v1

- Local/Pandas demo
- Trust score
- Drift
- Streamlit
- Airflow
- Rule generator

### v1.5

- Postgres result store
- Slack alerting
- Dockerized demo
- More SQL rules

### v2

- Soda translator
- Great Expectations translator
- Deequ translator
- dbt artifacts integration
- Metadata/catalog integration

### v3

- Multi-team dashboard
- Approval workflow UI
- Data product scorecards
- Business-domain scoring
- AI-assisted rule recommendation

---

## 22. Demo commands

```bash
pip install -r requirements-lite.txt
python main.py
python main.py
streamlit run ui/streamlit_app.py
```

That is enough to demonstrate:

- DQ checks
- Trust score
- Scorecard
- Failed rows
- Drift detection
- UI

---

# External DQ Tool Adapter Usage

The utility supports two execution modes.

## Native mode

Runs checks directly through the kit.

```yaml
execution:
  mode: native
  engine: pandas
```

Run:

```bash
python main.py --config configs/dq_config.yaml
```

## Soda mode

Generates SodaCL checks, and optionally runs Soda CLI.

```yaml
execution:
  mode: tool
  tool: soda

tool_config:
  soda:
    execution_mode: translate_only
    artifact_dir: outputs/tool_artifacts/soda
```

Run:

```bash
python main.py --config configs/dq_config_soda.yaml
```

To execute Soda CLI:

```yaml
tool_config:
  soda:
    execution_mode: execute_cli
    soda_binary: soda
    data_source: trino
    configuration_file: path/to/configuration.yml
```

## Great Expectations mode

```yaml
execution:
  mode: tool
  tool: great_expectations

tool_config:
  great_expectations:
    execution_mode: translate_only
    artifact_dir: outputs/tool_artifacts/great_expectations
```

Run:

```bash
python main.py --config configs/dq_config_gx.yaml
```

This produces a GX expectation suite JSON.

## Deequ mode

```yaml
execution:
  mode: tool
  tool: deequ

tool_config:
  deequ:
    execution_mode: translate_only
    artifact_dir: outputs/tool_artifacts/deequ
```

Run:

```bash
python main.py --config configs/dq_config_deequ.yaml
```

This produces a PyDeequ check script.

## Airflow usage

Your DAG code remains the same regardless of backend:

```python
run_dq = EnterpriseDQOperator(
    task_id="run_dq",
    config_path="dags/publishing_dq_config.yaml"
)
```

To switch backend, change only the config:

```yaml
execution:
  mode: native
  engine: sql
```

or:

```yaml
execution:
  mode: tool
  tool: soda
```
