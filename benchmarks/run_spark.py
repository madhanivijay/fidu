"""Spark-engine benchmark runner (local PySpark session).

Generates a synthetic Parquet file at the requested scale and runs the same
8-rule set used by the pandas benchmark (``benchmarks/rules.yaml``) against
it via ``DQExecutor("spark")`` and a local ``SparkSession``.

This benchmark requires the ``[spark]`` extra:

    pip install -e ".[spark]"

It also requires a working Java runtime (Spark's hard dep). On macOS the
simplest setup is ``brew install openjdk@17`` and exporting ``JAVA_HOME``.

The PySpark session is configured for local mode with a small driver memory
footprint -- this is meant to be a *kit-overhead* measurement, not a tuning
exercise. Cluster benchmarks (Databricks, EMR, on-prem YARN) are out of
scope here; run the kit against your own cluster to measure those.

Usage:

    python -m benchmarks.run_spark --rows 100000
    python -m benchmarks.run_spark --rows 1000000 --json
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

from benchmarks.generate_data import generate
from fidu.core.dq_executor import DQExecutor
from fidu.core.rule_parser import load_yaml

_RULES_PATH = Path(__file__).resolve().parent / "rules.yaml"


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
    driver_memory: str = "2g",
) -> dict:
    try:
        from pyspark.sql import SparkSession
    except ImportError as exc:
        raise SystemExit(
            "PySpark is not installed. Install the kit with the [spark] extra:\n"
            "  pip install -e \".[spark]\""
        ) from exc

    df = generate(rows=rows, cols=cols, seed=seed)
    rules_doc = load_yaml(str(rules_path))

    # Spin up a local SparkSession sized for a single-node benchmark. Re-using
    # an existing session via getOrCreate() means consecutive runs share a
    # warm JVM, which is exactly what you'd see in a long-lived job.
    spark = (
        SparkSession.builder.appName("EnterpriseDQKitBench")
        .master("local[*]")
        .config("spark.driver.memory", driver_memory)
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")

    with tempfile.TemporaryDirectory(prefix="dq_bench_spark_") as tmp:
        parquet_path = os.path.join(tmp, "bench.parquet")
        df.to_parquet(parquet_path, index=False)
        del df

        rss_before = _peak_rss_mb()

        # Use the kit's spark_file connector to load the parquet into a
        # DataFrame so the benchmark exercises the same code path the
        # production engine takes.
        rules_doc["source"] = {
            "type": "spark_file",
            "format": "parquet",
            "path": parquet_path,
        }

        executor = DQExecutor("spark")

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
        "engine": "spark",
        "backend": "local_pyspark",
        "rows": rows,
        "cols": cols,
        "seed": seed,
        "driver_memory": driver_memory,
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
        description="Enterprise DQ Kit Spark-engine benchmark (local PySpark)"
    )
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--cols", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--rules", default=str(_RULES_PATH))
    parser.add_argument("--driver-memory", default="2g")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = run_benchmark(
        rows=args.rows,
        cols=args.cols,
        seed=args.seed,
        rules_path=Path(args.rules),
        driver_memory=args.driver_memory,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(
            f"| spark (local) | {result['rows']:,} | {result['cols']} | "
            f"{result['rules']} | {result['wall_ms']:,.1f} | "
            f"{result['peak_rss_mb']:,.1f} | "
            f"{result['passed']}/{result['failed']}/{result['skipped']}/{result['errored']} |"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
