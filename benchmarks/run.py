"""Benchmark CLI for the native DQ engines.

Generates a synthetic Parquet file at the requested scale, runs the fixed
``benchmarks/rules.yaml`` rule set against it via ``DQExecutor``, and reports
wall-clock time, peak RSS, and per-rule durations.

The kit's structured logger has ``propagate=False`` and no handler attached
unless ``configure_logging()`` is called -- which we deliberately skip here so
the executor's INFO-level events become no-ops and don't pollute the timing
measurement with stdout I/O.

Usage:

    python -m benchmarks.run --engine pandas --rows 100000
    python -m benchmarks.run --engine pandas --rows 1000000 --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

# `resource` is Unix-only stdlib. On Windows it doesn't exist, so we guard
# the import and report 0.0 for RSS there — the harness still runs end-to-end
# for local development; reference numbers in RESULTS.md are taken on
# Linux/macOS only, which is also what CI uses.
try:
    import resource as _resource  # type: ignore[import-not-found]
except ModuleNotFoundError:
    _resource = None

from benchmarks.generate_data import generate
from fidu.core.dq_executor import DQExecutor
from fidu.core.rule_parser import load_yaml

_RULES_PATH = Path(__file__).resolve().parent / "rules.yaml"


def _peak_rss_mb() -> float:
    """Return peak RSS for the current process in megabytes.

    macOS reports ``ru_maxrss`` in bytes; Linux reports it in kilobytes.
    Windows lacks the ``resource`` module — returns 0.0 there.
    """
    if _resource is None:
        return 0.0
    rss = _resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return round(rss / (1024 * 1024), 1)
    return round(rss / 1024, 1)


def run_benchmark(
    engine: str,
    rows: int,
    cols: int = 50,
    seed: int = 42,
    rules_path: Path = _RULES_PATH,
) -> dict:
    """Run a single benchmark and return a result dict."""
    df = generate(rows=rows, cols=cols, seed=seed)

    rules_doc = load_yaml(str(rules_path))

    with tempfile.TemporaryDirectory(prefix="dq_bench_") as tmp:
        parquet_path = os.path.join(tmp, "bench.parquet")
        df.to_parquet(parquet_path, index=False)
        del df  # release the in-memory frame before timing the executor

        rss_before = _peak_rss_mb()

        rules_doc["source"] = {"type": "parquet", "format": "parquet", "path": parquet_path}

        executor = DQExecutor(engine)

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
        "engine": engine,
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


def _format_markdown_row(r: dict) -> str:
    return (
        f"| {r['engine']} | {r['rows']:,} | {r['cols']} | {r['rules']} | "
        f"{r['wall_ms']:,.1f} | {r['peak_rss_mb']:,.1f} | "
        f"{r['passed']}/{r['failed']}/{r['skipped']}/{r['errored']} |"
    )


def _format_markdown_header() -> str:
    return (
        "| engine | rows | cols | rules | wall_ms | peak_rss_mb | pass/fail/skip/err |\n"
        "|---|---:|---:|---:|---:|---:|---|"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enterprise DQ Kit benchmark runner")
    parser.add_argument("--engine", default="pandas", choices=["pandas", "sql", "spark"])
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--cols", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--rules", default=str(_RULES_PATH), help="Path to rule-set YAML"
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown")
    parser.add_argument(
        "--header", action="store_true", help="Print the Markdown table header only"
    )
    args = parser.parse_args(argv)

    if args.header:
        print(_format_markdown_header())
        return 0

    result = run_benchmark(
        engine=args.engine,
        rows=args.rows,
        cols=args.cols,
        seed=args.seed,
        rules_path=Path(args.rules),
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(_format_markdown_row(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
