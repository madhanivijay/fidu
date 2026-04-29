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

  benchmarks/
    __init__.py
    generate_data.py             # synthetic Parquet generator
    rules.yaml                   # fixed 8-rule benchmark set
    run.py                       # CLI: emits markdown row or JSON
    RESULTS.md                   # committed numbers from a reference machine

  configs/
    dq_config.yaml

  connectors/
    __init__.py                  # exports get_connector / register_connector
    base_connector.py
    connector_factory.py         # registry-backed lookup (lazy-imports heavy deps)
    csv_connector.py
    parquet_connector.py
    local_file_connector.py
    s3_file_connector.py
    adls_file_connector.py
    duckdb_connector.py
    snowflake_connector.py
    trino_connector.py
    databricks_sql_connector.py
    clickhouse_connector.py
    spark_file_connector.py
    sql_connector.py

  core/
    constants.py                 # severity weights, thresholds, exit codes, defaults, schema versions
    config_validator.py          # cached intelligence + Pydantic + input schema_version
    dq_executor.py               # safe_execute_dataset_rules + per-rule timeout
    logging.py                   # structured JSON logger, run_id correlation
    paths.py
    profiler.py
    registry.py                  # generic plugin registry used by factories
    regex_safety.py
    result_writer.py             # NaN/Inf-safe JSON writer + schema_version injection
    retry.py                     # exponential-backoff retry helper (pure stdlib)
    rule_filter.py
    rule_parser.py
    rule_result.py               # canonical rule-result schema
    rule_suggester.py
    schema_models.py             # optional Pydantic models for config/rules
    sql_safety.py
    timeout.py                   # run_with_timeout / RuleTimeoutError
    trust_score.py

  data/
    orders.csv

  docs/
    ARCHITECTURE.md
    EXTENDING.md                 # how to plug in custom connectors / engines / tool adapters
    ROADMAP.md
    USAGE.md

  drift/
    drift_detector.py

  engines/
    __init__.py                  # exports get_engine / register_engine
    base_engine.py
    engine_factory.py            # registry-backed lookup
    pandas_engine.py
    spark_engine.py
    sql_engine.py

  examples/
    custom_connector/            # worked JSONL connector + rules.yaml + sample data
      jsonl_connector.py
      orders.jsonl
      rules.yaml

  intelligence/
    engine_source_matrix.json
    rule_support_matrix.json
    rule_suggestions.json
    source_templates.json

  rules/
    orders_rules.yaml

  schemas/
    dq_results.schema.json       # JSON Schema 2020-12 for outputs/dq_results.json

  tests/                         # pytest suite

  tool_adapters/
    __init__.py                  # exports get_tool_adapter / register_tool_adapter
    base_tool_adapter.py
    tool_adapter_factory.py      # registry-backed lookup
    soda_adapter.py
    gx_adapter.py
    deequ_adapter.py

  tools/
    suggest_rules.py
    profile_and_suggest_rules.py
    review_rules.py

  translators/
    __init__.py
    soda_translator.py
    gx_translator.py
    deequ_translator.py

  ui/
    streamlit_app.py

  main.py
  CHANGELOG.md                   # output-schema changelog
  CONTRIBUTING.md                # dev loop, PR checklist, schema-bump rules
  Dockerfile                     # python:3.12-slim, non-root, multi-stage build
  pyproject.toml                 # build, optional-dependencies, ruff & pytest config
  requirements.txt
  requirements-lite.txt
  requirements-tools.txt
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

#### Install from TestPyPI / PyPI

Tagged releases are published to TestPyPI on every `v*` tag and promoted to
real PyPI for non-prerelease versions
(see [`.github/workflows/publish.yml`](.github/workflows/publish.yml)). To
install a specific tagged build for evaluation:

```bash
# TestPyPI (use --extra-index-url so runtime deps still come from PyPI)
pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  fidu

# PyPI (once the tag is promoted)
pip install fidu
```

The wheel installs a console script so `fidu --config ...`
works the same as `python -m fidu.main --config ...`.

### 3.3 Run sample DQ

```bash
python -m fidu.main
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
python -m fidu.main
```

Now drift detection has enough history to compare runs.

---

## 4. Configuration model

The main config lives at:

```text
configs/dq_config.yaml
```

All relative paths inside a config (rule files, output directories, drift history, source paths) are resolved relative to the directory containing that config — not the shell's current working directory. This means the same config can be invoked from a DAG, a CI runner, or an IDE without rewriting paths. Use absolute paths only when you intentionally want to escape the config directory.

Example:

```yaml
project:
  name: enterprise_dq_starter_kit

execution:
  mode: native        # 'native' or 'tool'
  engine: pandas      # required when mode='native'; one of pandas|sql|spark
  # tool: soda        # required when mode='tool'; one of soda|great_expectations|deequ
  fail_on_critical: false        # exit 10 if a critical rule fails
  fail_on_critical_drift: false  # exit 11 if a critical drift alert fires

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

Common rule fields:

| Field | Required? | Notes |
| ----- | --------- | ----- |
| `name` | yes | Stable identifier, surfaces in reports and drift alerts. |
| `type` | yes | One of the supported rule types in §7. |
| `column` | most types | Single-column rules (e.g. `not_null`, `regex_match`). |
| `columns` | multi-column rules | Used by `required_columns`; `schema_drift_check` uses `expected_columns`. |
| `dimension` | optional | Defaults to `validity`; drives dimension-level trust score buckets. |
| `severity` | optional | `critical` / `warning` / `info`. Defaults to `warning`; weights live in `fidu/core/constants.py`. |
| `draft` | optional | When `true` the rule is excluded from execution (review-only). |
| `review_status` | optional | `pending` / `approved` / `rejected`; managed by `fidu/tools/review_rules.py`. |

Some sources also accept a top-level `columns:` list inside `source` (used by SQL connectors so the result CSV `columns_seen` field can populate even when only a subset of fields participated in checks).

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

`schema_drift_check` compares a dataset's observed columns against `expected_columns`, with optional `allow_extra_columns: true` to permit additions. The drift detector also raises separate `schema_columns_added` (info) and `schema_columns_removed` (critical) alerts based on `columns_seen` between successive runs — these complement the per-rule check rather than replace it.

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

## 10a. Connector retries

Any source block can opt into exponential-backoff retries on transient
connector failures. Retries are **off by default** (one call, one exception)
so test bugs aren't masked by silent retries.

```yaml
source:
  type: snowflake
  retry:
    attempts: 3            # total tries including the first call
    base_delay_ms: 200     # initial backoff
    max_delay_ms: 5000     # cap on per-attempt delay
    jitter: true           # uniform [0.5x, 1.5x] jitter (default true)
    retryable:             # optional; defaults to OSError/ConnectionError/TimeoutError
      - ConnectionError
      - TimeoutError
      - OSError
```

The retry wrapper applies to `load_data` (dataframe engines) and
`get_table_ref`, `get_row_count`, `execute_scalar_query` (SQL engine). Each
retry emits a structured `connector_retry` event with `attempt`, `delay_ms`,
`exception_type`, and `operation` so you can wire alerts on flapping sources.
Non-retryable exceptions (e.g. `ValueError`) raise immediately without
consuming attempts.

---

## 10b. Observability

Every run emits structured (JSON by default) log lines to **stderr**, one per
event. Each event carries the same `run_id` so a downstream pipeline can stitch
together everything that happened during a single execution.

### Event types

| Event | Source | Key fields |
| ----- | ------ | ---------- |
| `run_start` | `main.run_from_config` | `project`, `execution_mode`, `config_path`, `dataset_count` |
| `dataset_start` | `core.dq_executor` | `dataset`, `engine`, `source_type`, `rule_count` |
| `rule_complete` | `core.dq_executor` | `dataset`, `rule_name`, `rule_type`, `dimension`, `severity`, `status`, `failed_count`, `pass_rate`, `duration_ms` |
| `dataset_complete` | `core.dq_executor` / `main._run_tool_dataset` | `dataset`, `engine` _or_ `tool`, `duration_ms`, `total_rules`, `passed_rules`, `failed_rules`, `skipped_rules`, `errored_rules` |
| `dataset_error` | `core.dq_executor.safe_execute_dataset_rules` / `main._run_tool_dataset` | `dataset`, `engine` _or_ `tool`, `exception_type`, `exception_message` — emitted when a dataset can't run end-to-end (connector failure after retries, tool adapter crash) |
| `connector_retry` | `core.dq_executor` | `dataset`, `source_type`, `operation`, `attempt`, `delay_ms`, `exception_type`, `exception_message` — emitted at WARNING per failed attempt |
| `run_complete` | `main.run_from_config` | `project`, `overall_trust_score`, `overall_grade`, `drift_status`, `drift_alerts`, `duration_ms` |
| `run_failed` | `main.run_from_config` | `reason` (`critical_rule_failures` or `critical_drift`) — emitted before the SystemExit |

Per-rule `duration_ms` is also written into the rule result itself
(`results[*].duration_ms`) and surfaced at the dataset level
(`datasets[*].duration_ms`) and run level (`duration_ms`) inside
`outputs/dq_results.json`. This lets you build latency dashboards from either
the log stream or the JSON output, whichever your stack prefers.

### Configuration

Two environment variables (read at the start of a run):

| Variable | Values | Default | Effect |
| -------- | ------ | ------- | ------ |
| `ENTERPRISE_DQ_LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` / `ERROR` | `INFO` | Standard Python log level. |
| `ENTERPRISE_DQ_LOG_FORMAT` | `json` / `text` | `json` | `text` switches to a human-readable formatter for local debugging. |

Library users who embed `run_from_config` can also call
`core.logging.configure_logging(level=..., fmt=..., stream=...)` directly.

### Sample event

```json
{"timestamp": "2026-04-26T09:43:28.586+00:00", "level": "INFO",
 "logger": "enterprise_dq.executor", "message": "rule_complete",
 "run_id": "75f9e7605403", "event": "rule_complete",
 "dataset": "orders", "engine": "pandas",
 "rule_name": "customer_id_not_null", "rule_type": "not_null",
 "dimension": "completeness", "severity": "critical",
 "status": "failed", "failed_count": 1, "pass_rate": 0.8333,
 "duration_ms": 0.41}
```

The kit's logger is namespaced under `enterprise_dq.*` and does **not**
propagate to the Python root logger, so it won't pollute application logging
in embedding hosts (Airflow, Streamlit, services).

---

## 10c. Output schema

`outputs/dq_results.json` is a stable, versioned contract. Every emitted file
includes a top-level `schema_version` (semver) and conforms to
[`schemas/dq_results.schema.json`](schemas/dq_results.schema.json) (JSON
Schema 2020-12).

```json
{
  "schema_version": "1.1.0",
  "project": "...",
  "execution_mode": "native",
  "run_id": "75f9e7605403",
  "datasets": [...],
  "trust_score_summary": {...},
  "drift_report": {...}
}
```

Downstream consumers (BI tools, data catalogs, contract systems) should
validate against the schema and pin to a major version. Schema evolution
rules and changes are tracked in [`CHANGELOG.md`](CHANGELOG.md). The test
suite enforces this contract end-to-end via `tests/test_output_schema.py` — a
failing schema test is a signal that you're shipping a breaking change.

NaN/Inf floats in `failed_sample` rows are sanitized to `null` on write so
the file is RFC 8259-compliant and parses unchanged in strict environments
(browsers, `jq`, Postgres `->>`).

### Input `schema_version`

Every config and rule YAML declares an integer `schema_version` at the top
level (currently `1`):

```yaml
schema_version: 1
project:
  name: my_project
```

Missing the field surfaces a warning under `validation_warnings`. An unknown
major raises `ValueError` so a YAML written for a future breaking version
fails fast instead of silently misparsing. See `INPUT_SCHEMA_VERSION` in
`fidu/core/constants.py` and the schema-bump rules in
[`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## 10e. Resilience: timeouts and partial-result mode

Two layers of fault isolation keep a long DQ run from being torpedoed by one
flaky rule or one missing source.

**Per-rule timeout.** Any rule can opt into a wall-clock budget:

```yaml
- name: slow_business_rule
  type: row_count_min
  value: 1
  timeout_seconds: 30
```

The rule body runs in a worker thread; if it doesn't return within
`timeout_seconds`, the executor records the rule with `status: "error"` and
`error_message: "RuleTimeoutError: rule exceeded 30s timeout"` and moves on.
This is best-effort — Python can't cleanly interrupt arbitrary work, so for
warehouse engines you should also set a query-side statement timeout. See
[`fidu/core/timeout.py`](fidu/core/timeout.py).

**Per-rule partial-result mode.** Any exception thrown by an engine is
captured into a canonical error rule result (`status: "error"`,
`error_message`) instead of propagating. The next rule still runs.

**Per-dataset partial-result mode.** `DQExecutor.safe_execute_dataset_rules`
wraps the dataset run; if the connector load fails after retry exhaustion the
dataset is recorded with `status: "error"` and the surrounding loop continues
with the next dataset. The native loop in `fidu/main.py` uses this method by
default. Tool mode has the symmetric `_run_tool_dataset` helper.

Both behaviours emit `dataset_error` / rule-level `status: error` log events
so flaky sources or rules show up cleanly in observability dashboards. See
`tests/test_resilience.py` for the contract.

---

## 10d. Benchmarks

A reproducible benchmark harness lives under [`benchmarks/`](benchmarks/). It
generates a synthetic Parquet file at the requested scale, runs the fixed
8-rule set in [`benchmarks/rules.yaml`](benchmarks/rules.yaml) against it, and
prints wall-clock + peak RSS + per-rule durations.

```bash
python -m benchmarks.run --engine pandas --rows 100000           # markdown row
python -m benchmarks.run --engine pandas --rows 1000000 --json   # full JSON
python -m benchmarks.run --header                                # print table header
```

Two additional harnesses cover the SQL and Spark engines so engine-to-engine
comparisons stay honest:

```bash
# In-process DuckDB; reads parquet directly via read_parquet()
python -m benchmarks.run_sql    --rows 1000000 --json

# Local PySpark session (requires the [spark] extra and a JVM)
python -m benchmarks.run_spark  --rows 1000000 --driver-memory 2g --json
```

The SQL benchmark uses a 6-rule subset
([`benchmarks/rules_sql.yaml`](benchmarks/rules_sql.yaml)) because the SQL
engine doesn't natively support `regex_match` / `required_columns`. The
Spark benchmark uses the full 8-rule set.

Headline numbers from this machine are committed to
[`benchmarks/RESULTS.md`](benchmarks/RESULTS.md). CI runs the pandas harness
at 50K rows on every push as a smoke check.

---

## 10f. Docker

A reproducible runtime image lives at the repo root:

```bash
docker build -t fidu:latest .

docker run --rm \
  -v "$(pwd)/configs:/app/configs:ro" \
  -v "$(pwd)/rules:/app/rules:ro" \
  -v "$(pwd)/data:/app/data:ro" \
  -v "$(pwd)/outputs:/app/outputs" \
  fidu:latest \
  --config configs/dq_config.yaml
```

The image is `python:3.12-slim`, multi-stage, runs as non-root `dq` (uid 1001),
and ships only the lite dependency set (pandas + duckdb + pyarrow + pyyaml).
For Soda / GX support, build `FROM fidu` and `pip install` the
extras you need, or pass `--build-arg EXTRAS=tools` to the root build.

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

Each dataset score also carries a `grade_reason` string so downstream consumers can render the cause without re-deriving it. Datasets with grade `TRANSLATION_ONLY` or `NO_RULES` produce a `null` numeric score and are excluded from the project-level average.

---

## 12. Drift detection

Drift detection compares the current run with the previous run.

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

If the history file is corrupt or malformed, it is archived as `<history>.corrupt-<timestamp>` and a fresh history is started. The warning is included in the next drift report under `history_warnings`.

In tool mode, adapters return one record per source rule (executed or skipped). Skipped rules carry `status: "skipped"` and are excluded from drift regression detection, so translating-only adapter runs do not trigger spurious alerts. Schema drift relies on `columns_seen` recorded by the engine or connector — provide one via `source.columns` for SQL sources or let pandas/Spark engines infer it from the dataframe.

### Pluggable history backends

History is stored through a `HistoryBackend` abstraction
([`fidu/drift/history_backend.py`](fidu/drift/history_backend.py)) so you can keep
the run log somewhere other than a local JSON file — S3, GCS, Postgres
JSONB, an HTTP API, an in-memory dict for tests. The default keeps the
original config surface working (just set `drift.history_path` and you
get a `FileHistoryBackend`), so existing setups don't need to change.

To swap in a custom store, register a factory at import time and reference
it from the YAML:

```python
# my_kit_extensions.py
from drift.history_backend import HistoryBackend, register_history_backend

class S3HistoryBackend(HistoryBackend):
    def __init__(self, config: dict):
        self.bucket = config["bucket"]
        self.key = config["key"]
    def load(self) -> dict: ...
    def save(self, history: dict) -> None: ...
    def describe(self) -> str:
        return f"s3://{self.bucket}/{self.key}"

register_history_backend("s3", lambda config: S3HistoryBackend(config))
```

```yaml
# configs/dq_config.yaml
drift:
  enabled: true
  history_backend:
    type: s3
    bucket: my-data-quality-bucket
    key: prod/dq_history.json
```

Built-in types: `file` (default) and `memory` (test-friendly, persists
nothing). The drift report includes `history_backend: "<describe()>"` so
you can see which backend served the run in the JSON output.

To test:

```bash
python -m fidu.main
python -m fidu.main
```

Then edit `data/orders.csv`, add/remove columns or change values, and run:

```bash
python -m fidu.main
```

---

## 13. Streamlit UI

Run:

```bash
streamlit run fidu/ui/streamlit_app.py
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
python fidu/tools/suggest_rules.py \
  --dataset orders \
  --source-type local_file \
  --source-format csv \
  --path data/orders.csv \
  --columns "order_id:string,customer_id:string,amount:numeric,status:string,order_date:date,email:string" \
  --output rules/orders_suggested_rules.yaml
```

### Profile-based suggestions

```bash
python fidu/tools/profile_and_suggest_rules.py \
  --dataset orders \
  --source-type local_file \
  --format csv \
  --path data/orders.csv \
  --output rules/orders_profiled_rules.yaml
```

By default, profiled rules are generated as draft/pending.

### Generate approved rules directly

```bash
python fidu/tools/profile_and_suggest_rules.py \
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
python fidu/tools/review_rules.py \
  --file rules/orders_profiled_rules.yaml \
  --action list
```

Approve rule 3:

```bash
python fidu/tools/review_rules.py \
  --file rules/orders_profiled_rules.yaml \
  --action approve \
  --index 3
```

Reject rule 5:

```bash
python fidu/tools/review_rules.py \
  --file rules/orders_profiled_rules.yaml \
  --action reject \
  --index 5
```

Approve all:

```bash
python fidu/tools/review_rules.py \
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

The kit's connectors, engines, and tool adapters are all backed by the same
plugin registry pattern -- you can register your own at process start
without forking the repo. See [`docs/EXTENDING.md`](docs/EXTENDING.md) for
the full guide, including a runnable JSONL-connector example at
[`examples/custom_connector/`](examples/custom_connector) that's covered
by CI.

Quick reference:

| Add a... | Subclass | Register via |
|---|---|---|
| Source connector | `connectors.base_connector.BaseConnector` | `register_connector(name, factory, aliases=...)` |
| Native engine | `engines.base_engine.BaseDQEngine` | `register_engine(name, factory, aliases=...)` |
| External tool adapter | `tool_adapters.base_tool_adapter.BaseToolAdapter` | `register_tool_adapter(name, factory, aliases=...)` |

### Add a new rule (in-tree, for built-in engines)

1. Add support to the engine, for example `fidu/engines/pandas_engine.py`.
2. Add support to `fidu/engines/spark_engine.py` and/or `fidu/engines/sql_engine.py` if needed.
3. Update `intelligence/rule_support_matrix.json`.
4. Add docs.

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
- Pydantic-based YAML schema validation
- Docker Compose demo
- dbt integration
- Pytest baseline + GitHub Actions CI
- Python package setup
- Telemetry / structured run logs

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
python -m fidu.main
python -m fidu.main
streamlit run fidu/ui/streamlit_app.py
```

That is enough to demonstrate:

- DQ checks
- Trust score
- Scorecard
- Failed rows
- Drift detection
- UI

---

## 15. Native engine mode vs external DQ tool mode

The kit now supports two execution modes.

### 15.1 Native mode

Native mode runs checks through this kit's own engines.

```yaml
execution:
  mode: native
  engine: pandas   # pandas | sql | spark
  fail_on_critical: true
  fail_on_critical_drift: false
```

Use native mode when you want the utility itself to execute rules and produce detailed failed-row samples, trust scores, scorecards, and drift reports.

Typical native examples:

```bash
python -m fidu.main --config configs/dq_config.yaml
```

### 15.2 External DQ tool adapter mode

Tool mode routes the same standard rule YAML to an external DQ tool adapter.

```yaml
execution:
  mode: tool
  tool: soda        # soda | great_expectations | deequ
  fail_on_critical: false
  fail_on_critical_drift: false
```

The adapter layer is useful when a repo or team already uses Soda, Great Expectations, or Deequ, but you still want one common rule schema, one config pattern, one Airflow operator, one scorecard contract, and one place to extend DQ behavior.

### 15.3 Mode quick reference

| Aspect | `mode: native` | `mode: tool` |
| ------ | -------------- | ------------ |
| Required key | `execution.engine` (`pandas` / `sql` / `spark`) | `execution.tool` (`soda` / `great_expectations` / `deequ`) |
| Who runs the rules | `core.dq_executor` via `fidu/engines/*` | The third-party tool, or translate-only artifacts in `outputs/tool_artifacts/` |
| Failed-row samples | Yes (where the engine supports it) | Only when the tool itself produced them |
| Drift report | Yes | Yes (driven by canonical results emitted by the adapter) |
| Optional dependencies | `pyspark` for spark engine, warehouse drivers for SQL connectors | Tool-specific install (`soda-core`, `great_expectations`, `pydeequ`) |

### 15.4 CLI exit codes

`fidu/main.py` propagates severity-aware exit codes (defined in `fidu/core/constants.py`) so CI can branch on the failure type:

| Code | Constant | When it fires |
| ---- | -------- | ------------- |
| 0 | `EXIT_OK` | Successful run with no triggering condition. |
| 10 | `EXIT_CRITICAL_FAILURES` | `execution.fail_on_critical: true` and at least one critical rule failed. |
| 11 | `EXIT_CRITICAL_DRIFT` | `execution.fail_on_critical_drift: true` and a critical drift alert was raised. |

---

## 16. Soda adapter

Example config:

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
python -m fidu.main --config configs/dq_config_soda.yaml
```

This generates SodaCL YAML under:

```text
outputs/tool_artifacts/soda/
```

To execute Soda CLI directly:

```yaml
tool_config:
  soda:
    execution_mode: execute_cli
    soda_binary: soda
    data_source: trino
    configuration_file: path/to/soda/configuration.yml
```

Then run:

```bash
python -m fidu.main --config configs/dq_config_soda.yaml
```

Important: `execute_cli` requires Soda to be installed in the runtime and the Soda configuration file to be available.

---

## 17. Great Expectations adapter

Example config:

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
python -m fidu.main --config configs/dq_config_gx.yaml
```

This generates a GX expectation suite JSON under:

```text
outputs/tool_artifacts/great_expectations/
```

GX runtime execution is intentionally left as an extension point because GX projects differ significantly in context, datasource, validator, batch request, and checkpoint setup. The generated suite can be copied into your GX project or wired into your existing checkpoint flow.

---

## 18. Deequ / PyDeequ adapter

Example config:

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
python -m fidu.main --config configs/dq_config_deequ.yaml
```

This generates a PyDeequ check script under:

```text
outputs/tool_artifacts/deequ/
```

Deequ execution is usually done inside a controlled Spark runtime such as EMR, Glue, Databricks, or a cluster configured with JVM dependencies. The generated script is meant to be plugged into that runtime.

---

## 19. What changes in `fidu/main.py`

`fidu/main.py` now accepts a config path:

```bash
python -m fidu.main
```

uses:

```text
configs/dq_config.yaml
```

This:

```bash
python -m fidu.main --config configs/dq_config_soda.yaml
```

uses the Soda adapter config.

This:

```bash
python -m fidu.main --config configs/dq_config_gx.yaml
```

uses the Great Expectations adapter config.

This:

```bash
python -m fidu.main --config configs/dq_config_deequ.yaml
```

uses the Deequ adapter config.

---

## 20. How to use inside your current Airflow repo

If your current repo keeps DQ YAML files next to DAGs, you can keep that pattern.

Example:

```text
dags/
  publishing_dag.py
  publishing_dq_config.yaml
  orders_dq.yaml
  customers_dq.yaml
```

Your config can point to those rule files:

```yaml
project:
  name: publishing_dq

execution:
  mode: native
  engine: sql
  fail_on_critical: true
  fail_on_critical_drift: false

outputs:
  json_path: /tmp/dq_results.json
  rule_results_csv: /tmp/dq_rule_results.csv
  scorecard_csv: /tmp/dq_scorecard.csv
  failed_rows_dir: /tmp/failed_rows

drift:
  enabled: true
  history_path: /tmp/dq_run_history.json
  drift_output_path: /tmp/drift_report.json

datasets:
  - name: orders
    rules_file: dags/orders_dq.yaml
  - name: customers
    rules_file: dags/customers_dq.yaml
```

In your DAG:

```python
from fidu.airflow.dq_operator import EnterpriseDQOperator

run_dq = EnterpriseDQOperator(
    task_id="run_publishing_dq",
    config_path="dags/publishing_dq_config.yaml"
)

transform_task >> run_dq >> publish_task
```

If you want the same DAG to generate Soda artifacts instead:

```yaml
execution:
  mode: tool
  tool: soda

tool_config:
  soda:
    execution_mode: translate_only
    artifact_dir: /tmp/soda_checks
```

No DAG code changes are required. Only the config changes.

---

## 21. Important behavior notes

### Native mode actually runs DQ checks

Native mode validates data directly through Pandas, Spark, or SQL engines.

### Tool `translate_only` mode generates tool-native artifacts

For Soda/GX/Deequ, `translate_only` does not validate the data. It generates the tool-native check files. The adapter still emits one rule-result record per source rule with `status: "skipped"` and `is_tool_metadata` markers so that downstream scoring, drift, and dashboards see the rule was deliberately not executed. Trust score reports the dataset as `TRANSLATION_ONLY` with an explicit `grade_reason` instead of inflating to 100/`TRUSTED`.

### Soda `execute_cli` can run the external tool

Soda has a simple CLI execution path, so the adapter includes `execute_cli` support. The runtime must have Soda installed and configured. The adapter passes `-srf scan_results.json`, parses the structured output, and maps each Soda check result back onto the source rule. A subprocess timeout (`tool_config.<tool>.timeout_seconds`, default 600) prevents hangs.

### GX and Deequ execution are extension points

GX and Deequ runtime execution usually depends on project-specific context, datasource, Spark session, batch request, and environment setup. The adapter files are structured so teams can implement their own execution method without changing the common rule schema or Airflow operator.

### Null semantics and rule safety

Pandas value rules (`min_value`, `max_value`, `between`, `accepted_values`, `regex_match`) accept an optional `treat_null_as` field with values `fail` (default), `pass`, or `skip`. `not_null` is the dedicated check for null presence. `regex_match` patterns are length-capped and rejected if they contain unsafe nested quantifiers, to keep evaluation bounded.

### SQL safety

All SQL identifiers (table, schema, column names) are whitelisted against an ANSI-friendly regex before being interpolated into queries; literal values are coerced or escaped. This prevents the rule YAML from acting as a SQL injection vector. DuckDB CSV reads validate the file path against an `allowed_root` and load via pandas + `connection.register()` instead of templating the path into DDL.

### Connector credentials

Connector classes mask secrets in their `__repr__` output. When logging connectors directly (e.g., via Airflow XCom debug), credentials will not leak.

---

## 22. Adapter layer structure

```text
tool_adapters/
  base_tool_adapter.py
  tool_adapter_factory.py
  soda_adapter.py
  gx_adapter.py
  deequ_adapter.py

translators/
  soda_translator.py
  gx_translator.py
  deequ_translator.py
```

The separation is deliberate:

```text
translator = converts standard rules into tool-native artifacts
adapter    = decides whether to only generate artifacts or execute the tool
```

This keeps the core DQ rule schema stable while allowing each repo to extend execution behavior.

---

## 23. Optional DQ tool dependencies

The default install does not force every DQ tool dependency because most repos will use only one backend.

For native mode:

```bash
pip install -r requirements-lite.txt
```

For all data connectors:

```bash
pip install -r requirements.txt
```

For optional external DQ tools:

```bash
pip install -r requirements-tools.txt
```

In enterprise repos, it is usually better to install only the specific adapter dependency you need. For example:

```bash
pip install soda-core
```

or:

```bash
pip install great_expectations
```

or configure PyDeequ inside your Spark/EMR/Glue/Databricks runtime.
