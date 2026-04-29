# Changelog

All notable changes to the kit are tracked here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Two contracts are
versioned independently:

- **Package version** (`pyproject.toml`) — code, CLI flags, public Python API.
  Currently `0.1.0` (pre-release).
- **Output JSON schema version** (`OUTPUT_SCHEMA_VERSION` in
  [`core/constants.py`](core/constants.py)) — the shape of
  `outputs/dq_results.json`. Currently `1.1.0`.

Output-schema semver:

- **Patch** — additive, no field renames or removals.
- **Minor** — new optional fields.
- **Major** — renamed/removed fields, changed types, changed enum values.

When bumping the output schema, also update
[`schemas/dq_results.schema.json`](schemas/dq_results.schema.json) and run
`pytest tests/test_output_schema.py`.

## [Unreleased]

### Changed

- Renamed PyPI package from `enterprise-dq-kit` to `fidu` and namespaced all modules under a single `fidu` package. This prevents collisions with Apache Airflow and other generic top-level names when installed via pip. Importable: `from fidu.core import ...`, `from fidu.drift.history_backend import ...`. CLI: `fidu --config <path>` (was `python main.py --config <path>`).

### Added

- Input YAML `schema_version` contract (`INPUT_SCHEMA_VERSION = 1`) on every
  config and rule file. Validator warns when missing, errors on unknown major
  so YAMLs written for a future breaking version fail fast.
- Per-rule `timeout_seconds` field. Rules that exceed budget surface as
  `status: "error"` with a `RuleTimeoutError`; the surrounding run continues.
- Per-rule + per-dataset partial-result mode. Engine exceptions become
  `status: "error"` rule results; connector failures (after retry exhaustion)
  become `status: "error"` dataset results via
  `DQExecutor.safe_execute_dataset_rules`. One bad rule or one missing source
  no longer tanks the whole run.
- Connector-level retry with exponential backoff + jitter
  ([`core/retry.py`](core/retry.py)). Opt-in per source via a `retry:` block.
- Tool-mode dataset observability symmetry via `_run_tool_dataset` in
  `main.py` — same `dataset_start` / `dataset_complete` / `dataset_error`
  events as native mode.
- Dockerfile (multi-stage `python:3.12-slim`, non-root user).
- Custom-connector example under `examples/custom_connector/` plus the
  registry-extension guide at [`docs/EXTENDING.md`](docs/EXTENDING.md).
- Benchmark harness ([`benchmarks/`](benchmarks/)) with synthetic Parquet
  generator, fixed 8-rule set, wall-clock + peak RSS measurement, and
  committed numbers in [`benchmarks/RESULTS.md`](benchmarks/RESULTS.md).
  Now includes a 10M-row pandas data point plus dedicated SQL
  ([`benchmarks/run_sql.py`](benchmarks/run_sql.py)) and Spark
  ([`benchmarks/run_spark.py`](benchmarks/run_spark.py)) harnesses for
  engine-to-engine comparisons.
- Pluggable drift history backend
  ([`drift/history_backend.py`](drift/history_backend.py)) — `HistoryBackend`
  ABC with `FileHistoryBackend` / `InMemoryHistoryBackend` implementations
  and a registry hook (`register_history_backend`) so external code can
  persist run history in S3, Postgres, or any custom store via
  `drift.history_backend: {type: ...}` in YAML. Existing configs keep
  working unchanged (the default is still file-based).
- TestPyPI / PyPI publish workflow
  ([`.github/workflows/publish.yml`](.github/workflows/publish.yml)) that
  builds an sdist + wheel on every `v*` tag, publishes to TestPyPI via
  PyPI Trusted Publishing (OIDC), smoke-installs the artifact from
  TestPyPI, and promotes to real PyPI for non-prerelease tags.
- `CONTRIBUTING.md` with PR checklist and schema-bump rules.

### Changed

- `validate_top_level_config` now returns a list of warnings (used to return
  the validated dict, which was unused at every call site).
- `validate_rule_set_for_tool` is wrapped by the new
  `validate_dataset_for_tool` for parity with `validate_dataset_config`.
- Drift detector no longer reads/writes history files directly — it goes
  through the new `HistoryBackend` abstraction. `append_run_history` now
  takes a backend instance instead of a path; the legacy `_safe_load_history`
  helper has been removed in favour of `FileHistoryBackend.load`. The
  drift report payload now includes `history_backend` (e.g. `file://...`,
  `s3://...`, `memory://`) so consumers can see where history is stored.
  Existing call sites in `main.py` are unchanged thanks to the
  `history_path`-based default.

### Fixed

- NaN/Inf floats in `failed_sample` rows are sanitized to `null` so
  `dq_results.json` is RFC 8259-compliant and parses unchanged in strict
  environments (browsers, `jq`, Postgres `->>`).

## Output schema 1.1.0 — 2026-04-26

Additive (minor bump). No consumer of v1.0.0 needs to change.

- Per-dataset `status` field with values `completed` / `error`. Datasets that
  could not run end-to-end (connector failure after retries, tool adapter
  crash, unhandled engine exception caught by
  `safe_execute_dataset_rules`) are now emitted with `status: "error"` and
  an `error_message` instead of being silently dropped.
- `dataset.error_message` is now allowed alongside `status: "error"`.
- `dataset.source.type` is no longer required at the schema level — error
  datasets that never reached the connector layer can now serialize.

## Output schema 1.0.0 — 2026-04-26

Initial published schema. Covers:

- Top-level: `schema_version`, `project`, `execution_mode`, `run_id`, `engine`/`tool`, `duration_ms`, `validation_warnings`, `datasets`, `trust_score_summary`, `drift_report`.
- Per-dataset: `dataset`, `source`, rule counts (`total_rules`/`passed_rules`/etc.), `duration_ms`, `columns_seen`, `results`.
- Per-rule: `rule_name`, `rule_type`, `column`/`columns`, `dimension`, `severity` (critical/warning/info), `status` (passed/failed/skipped/error), `total_rows`, `failed_count`, `pass_rate`, `duration_ms`, `details`, `failed_sample`.
- Trust score summary with overall + per-dataset + per-dimension breakdowns.
- Drift report with `status`, `alert_count`, `alerts`.
