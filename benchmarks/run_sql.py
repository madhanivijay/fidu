"""SQL-engine benchmark runner (in-process DuckDB).

Generates a synthetic Parquet file at the requested scale, exposes it to
DuckDB as a view, and runs the SQL-supported rule subset
(``benchmarks/rules_sql.yaml``) against it via ``DQExecutor("sql")``.

The SQL engine doesn't natively implement ``regex_match`` or
``required_columns`` -- those are filtered out of the SQL rule set so this
benchmark is comparing apples to apples on the engines that *do* support
the same rules.

Network warehouses (Snowflake, Trino, Databricks SQL, ClickHouse) are out
of scope here because their wall-clock is dominated by network round-trips
rather than the kit. Run the kit against your own warehouse to measure
those.

Usage:

    python -m benchmarks.run_sql --rows 100000
    python -m benchmarks.run_sql --rows 1000000 --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

# `resource` is Unix-only — guard the import so this module loads on Windows
# (RSS just reports 0.0 there). See benchmarks/run.py for the rationale.
try:
    import resource as _resource  # type: ignore[import-not-found]
except ModuleNotFoundError:
    _resource = None

import duckdb

from benchmarks.generate_data import generate
from fidu.connectors.connector_factory import register_connector
from fidu.connectors.sql_connector import SQLConnector
from fidu.core.dq_executor import DQExecutor
from fidu.core.rule_parser import load_yaml

_RULES_PATH = Path(__file__).resolve().parent / "rules_sql.yaml"
_BENCH_SOURCE_TYPE = "bench_duckdb_parquet"


class _BenchmarkDuckDBParquetConnector(SQLConnector):
    """In-process DuckDB connector that registers a parquet file as a view.

    The kit's regular ``DuckDBConnector`` reads CSVs through pandas; that's
    fine for production but defeats the point of a SQL benchmark. This
    connector hands DuckDB the parquet path directly so the engine measures
    DuckDB's own execution path.
    """

    def __init__(self, parquet_path: str, table_name: str):
        self._connection = duckdb.connect()
        self._parquet_path = os.path.abspath(parquet_path)
        self._table_name = table_name
        self._registered = False

    def _ensure_registered(self) -> None:
        if self._registered:
            return
        # DuckDB doesn't accept prepared params in DDL, so inline the path.
        # Path comes from tempfile.TemporaryDirectory in this process (not
        # user input), but escape single quotes anyway as a belt-and-braces
        # measure.
        escaped = self._parquet_path.replace("'", "''")
        self._connection.execute(
            f"CREATE OR REPLACE VIEW {self._table_name} AS "
            f"SELECT * FROM read_parquet('{escaped}')"
        )
        self._registered = True

    def execute_scalar_query(self, query: str, params=None):
        cursor = self._connection.execute(query, params or [])
        row = cursor.fetchone()
        return row[0] if row else None

    def get_table_ref(self, source_config: dict) -> str:
        self._ensure_registered()
        return self._table_name

    def get_row_count(self, table_ref: str) -> int:
        return int(self.execute_scalar_query(f"SELECT COUNT(*) FROM {table_ref}"))


def _peak_rss_mb() -> float:
    if _resource is None:
        return 0.0
    rss = _resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return round(rss / (1024 * 1024), 1)
    return round(rss / 1024, 1)


def run_benchmark(
    rows: int,
    cols: int = 50,
    seed: int = 42,
    rules_path: Path = _RULES_PATH,
) -> dict:
    df = generate(rows=rows, cols=cols, seed=seed)
    rules_doc = load_yaml(str(rules_path))

    with tempfile.TemporaryDirectory(prefix="dq_bench_sql_") as tmp:
        parquet_path = os.path.join(tmp, "bench.parquet")
        df.to_parquet(parquet_path, index=False)
        del df

        rss_before = _peak_rss_mb()

        table_name = rules_doc.get("source", {}).get("table", "bench_orders")
        # Register a fresh connector instance per run so the DuckDB session
        # is scoped to this benchmark and cleaned up when the temp dir goes.
        register_connector(
            _BENCH_SOURCE_TYPE,
            lambda p=parquet_path, t=table_name: _BenchmarkDuckDBParquetConnector(p, t),
        )
        rules_doc["source"] = {"type": _BENCH_SOURCE_TYPE, "table": table_name}

        executor = DQExecutor("sql")
        start = time.perf_counter()
        result = executor.execute_dataset_rules(rules_doc)
        wall_ms = round((time.perf_counter() - start) * 1000, 2)

        rss_peak = _peak_rss_mb()

    rule_durations = [
        {
            "name": r["rule_name"],
            "type": r["rule_type"],
            "duration_ms": r.get("duration_ms"),
            "status": r["status"],
        }
        for r in result["results"]
    ]

    return {
        "engine": "sql",
        "backend": "duckdb_in_process",
        "rows": rows,
        "cols": cols,
        "seed": seed,
        "rules": result["total_rules"],
        "passed": result["passed_rules"],
        "failed": result["failed_rules"],
        "skipped": result["skipped_rules"],
        "errored": result["errored_rules"],
        "wall_ms": wall_ms,
        "executor_duration_ms": result.get("duration_ms"),
        "peak_rss_mb": rss_peak,
        "peak_rss_delta_mb": round(rss_peak - rss_before, 1),
        "rule_durations": rule_durations,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Enterprise DQ Kit SQL-engine benchmark (in-process DuckDB)"
    )
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--cols", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--rules", default=str(_RULES_PATH))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = run_benchmark(
        rows=args.rows, cols=args.cols, seed=args.seed, rules_path=Path(args.rules)
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(
            f"| sql (duckdb) | {result['rows']:,} | {result['cols']} | "
            f"{result['rules']} | {result['wall_ms']:,.1f} | "
            f"{result['peak_rss_mb']:,.1f} | "
            f"{result['passed']}/{result['failed']}/{result['skipped']}/{result['errored']} |"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
