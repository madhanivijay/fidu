# Extending the kit

The kit ships three plugin surfaces, all backed by the same registry pattern
in [`fidu/core/registry.py`](../fidu/core/registry.py):

| You want to add a... | Subclass | Register via | Used in YAML as |
|---|---|---|---|
| Source / connector | `connectors.base_connector.BaseConnector` | `register_connector(name, factory, aliases=...)` | `source.type` |
| Native execution engine | `engines.base_engine.BaseDQEngine` | `register_engine(name, factory, aliases=...)` | `execution.engine` |
| External DQ tool adapter | `tool_adapters.base_tool_adapter.BaseToolAdapter` | `register_tool_adapter(name, factory, aliases=...)` | `execution.tool` |

You don't need to fork the repo or modify `fidu/main.py`. Register at process
start (Airflow plugin `__init__`, embedding service entry point, test
`conftest.py`) and the executor will pick it up.

## Worked example: a JSONL connector

This example lives at [`examples/custom_connector/`](../examples/custom_connector)
and is exercised by [`tests/test_custom_connector_example.py`](../tests/test_custom_connector_example.py)
on every CI run -- so if the extension contract changes, this guide breaks
loudly.

### 1. Subclass `BaseConnector`

```python
# examples/custom_connector/jsonl_connector.py
import gzip, json
import pandas as pd
from fidu.connectors.base_connector import BaseConnector

class JSONLConnector(BaseConnector):
    def load_data(self, source_config: dict) -> pd.DataFrame:
        path = source_config["path"]
        opener = gzip.open if str(path).endswith(".gz") else open
        with opener(path, "rt", encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]
        return pd.DataFrame.from_records(records)
```

The contract is just `load_data(source_config) -> DataFrame`. The
`source_config` is the raw `source:` block from the rule YAML, so you can put
anything you want under it (paths, auth options, format flags) -- the kit
doesn't second-guess the schema.

### 2. Register a factory

```python
from fidu.connectors.connector_factory import register_connector

def install() -> None:
    register_connector("jsonl", lambda: JSONLConnector(), aliases=["json_lines"])
```

Use a **factory** (zero-arg callable returning an instance), not the class
itself. This is what gives the kit lazy initialization -- nothing imports
your module until a rule actually asks for `type: jsonl`.

The optional `aliases=` lets users opt for the form they prefer in YAML;
case-insensitive match is built in.

### 3. Point a config at it

```yaml
# examples/custom_connector/rules.yaml
dataset: example_orders
source:
  type: jsonl
  path: examples/custom_connector/orders.jsonl
rules:
  - name: order_id_not_null
    type: not_null
    column: order_id
    dimension: completeness
    severity: critical
```

That's it. From here the standard executor handles rule execution, trust
scoring, drift detection, and structured-log emission for you.

### 4. Make sure it stays working

Add a test that exercises the full path through `DQExecutor`:

```python
from fidu.core.dq_executor import DQExecutor
from examples.custom_connector.jsonl_connector import install

def test_my_connector():
    install()
    executor = DQExecutor("pandas")
    result = executor.execute_dataset_rules({
        "dataset": "smoke",
        "source": {"type": "jsonl", "path": "test_data/orders.jsonl"},
        "rules": [{"name": "id_not_null", "type": "not_null", "column": "order_id"}],
    })
    assert result["passed_rules"] == 1
```

If this test breaks, the kit's extension contract has changed -- pin to a
known version or update your subclass.

## Picking up retries for free

Once your connector is registered, the per-source `retry:` block (see
README §10a) just works. You don't need to touch your code; the executor
wraps every call to `load_data` in `with_retry` and emits `connector_retry`
events on transient failure. If your connector raises a non-retryable
exception type (e.g. `ValueError` from a malformed config), the executor
will re-raise immediately without consuming attempts.

To make a connection-level error retryable, raise an exception that's a
subclass of `OSError`, `ConnectionError`, or `TimeoutError` (the default
retryable set), or have users name it explicitly in their `retry.retryable`
list.

## Engines and tool adapters

The same pattern applies to engines and tool adapters; the contract methods
differ:

- **Engines** (`engines.base_engine.BaseDQEngine`) implement `run_rule(data, rule) -> dict`. Returned dict must conform to the rule-result schema in [`fidu/core/rule_result.py`](../fidu/core/rule_result.py).
- **Tool adapters** (`tool_adapters.base_tool_adapter.BaseToolAdapter`) implement `run_dataset(dataset_rules, tool_config) -> dict`. The dict has the same dataset-level shape the executor produces, so the trust-score and drift modules can consume it identically to native runs.

See [`fidu/engines/pandas_engine.py`](../fidu/engines/pandas_engine.py) and
[`fidu/tool_adapters/soda_adapter.py`](../fidu/tool_adapters/soda_adapter.py) for
production-grade reference implementations.

## Output schema is a contract too

Anything your custom engine or tool adapter emits ends up in
`outputs/dq_results.json`, which is validated against
[`schemas/dq_results.schema.json`](../schemas/dq_results.schema.json). If
your component returns a non-conforming rule result you'll see a
`jsonschema.ValidationError` in `tests/test_output_schema.py`. Either:

- Fix the result shape (preferred), or
- Bump `OUTPUT_SCHEMA_VERSION` in [`fidu/core/constants.py`](../fidu/core/constants.py),
  update the JSON Schema, and document the change in
  [`CHANGELOG.md`](../CHANGELOG.md). Treat consumers downstream of the kit
  as customers -- breaking the schema is breaking their code.
