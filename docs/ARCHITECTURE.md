# Architecture

Enterprise DQ Kit is built around six layers:

1. **Rules** — YAML definition of checks (`rules/*.yaml`). Each rule has `name`, `type`, optional `column`/`columns`, `dimension`, `severity`, optional `draft`/`review_status`, and rule-specific parameters.
2. **Connectors** (`connectors/`) — load data or execute SQL against a source. File connectors return a pandas/Spark DataFrame; SQL connectors expose `get_table_ref`, `execute_scalar_query(query, params=None)`, and `get_row_count`.
3. **Engines** (`engines/`) — execute rule semantics. `PandasDQEngine` and `SparkDQEngine` consume DataFrames; `SQLDQEngine` builds parameter-validated SQL via `core.sql_safety` helpers.
4. **Tool Adapters** (`tool_adapters/`) — alternative to engines: route the same rules to Soda/Great Expectations/Deequ. Each adapter emits one normalized rule-result per source rule, marking translate-only results as `status: "skipped"`.
5. **Trust Score + Drift** (`core/trust_score.py`, `drift/drift_detector.py`) — convert rule results into dataset/project scores with explicit `grade_reason`, and compare runs over time using a corruption-tolerant history file.
6. **Intelligence** (`intelligence/`) — JSON matrices describing engine/source/rule support and rule suggestions, used by `core.config_validator` and the rule generators. Matrices are loaded once and cached via `functools.lru_cache`; tests can call `core.config_validator.reset_intelligence_cache()` to force a reload.

## Plugin registries

Connectors, engines, and tool adapters are looked up through tiny string→factory registries (`core/registry.py`). The factories defined in `connectors/connector_factory.py`, `engines/engine_factory.py`, and `tool_adapters/tool_adapter_factory.py` lazily import their heavy optional dependencies, so installing only `requirements-lite.txt` is sufficient unless a specific connector/engine is requested. Downstream code can call `register_connector(name, factory)`, `register_engine(...)`, or `register_tool_adapter(...)` to plug in custom implementations without editing the kit.

## Translators

Each translator (`translators/soda_translator.py`, `gx_translator.py`, `deequ_translator.py`) maps the canonical rule schema to the target tool's native check syntax. Internally each uses a dispatch table keyed by `rule.type`, so adding a new rule type means adding one entry per translator rather than extending an `if/elif` chain.

## Result schema contract

Every rule result, regardless of engine or adapter, conforms to the canonical schema in `core/rule_result.py`:

```
rule_name, rule_type, column, columns, dimension, severity,
status (passed | failed | skipped | error),
total_rows, failed_count, pass_rate, failed_sample
```

Tool adapters add `is_tool_metadata: true` for adapter-only records (e.g., generated artifact paths) so trust score and drift can ignore them.

## Path resolution

`main.run_from_config(config_path)` resolves the config to an absolute path, then resolves every relative path inside the config (rules, outputs, drift history, source paths) against the config's directory. This makes the same config portable across CWDs (CLI, Airflow worker, Streamlit, CI).

## Security

- `core/sql_safety.py` whitelists identifiers via regex and provides `safe_numeric`/`safe_string_literal` helpers. The SQL engine and every SQL connector route untrusted YAML values through these.
- `connectors/duckdb_connector.py` validates file paths against an `allowed_root` and reads via `pandas.read_csv` + `connection.register()` rather than templating the path into DDL.
- `core/regex_safety.py` caps regex pattern length at 1024 chars and rejects nested-quantifier patterns to bound `re` evaluation cost.
- Connector classes mask credentials in `__repr__`.
- The Soda CLI adapter applies a configurable subprocess timeout (default 600s, see `core.constants.DEFAULT_TOOL_TIMEOUT_SECONDS`).

## Exit codes

`main.py` returns severity-aware exit codes (defined in `core/constants.py`) so CI pipelines can branch on the failure type:

| Code | Constant | Meaning |
| ---- | -------- | ------- |
| 0 | `EXIT_OK` | Run completed; no triggering condition met. |
| 10 | `EXIT_CRITICAL_FAILURES` | `execution.fail_on_critical: true` and at least one critical rule failed. |
| 11 | `EXIT_CRITICAL_DRIFT` | `execution.fail_on_critical_drift: true` and a critical drift alert was raised. |

## Layer flow

```text
YAML rules + dq_config.yaml
        ↓
core.config_validator (engine/source/rule support, tool-mode rule check)
        ↓
core.dq_executor (native)  OR  tool_adapters.* (tool mode)
        ↓
canonical rule results
        ↓
core.trust_score (with grade_reason)
        ↓
result_writer + drift.drift_detector
        ↓
JSON / CSV / failed-row samples / drift report
```

See `README.md` and `docs/USAGE.md` for end-user instructions.
