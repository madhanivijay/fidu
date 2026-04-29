"""Tiny-scale regression test for the SQL-engine (DuckDB) benchmark harness.

Mirrors ``test_benchmarks.py`` but exercises the SQL path. Skipped if DuckDB
isn't installed -- but DuckDB is a base dependency of the kit, so the skip
path is mostly defensive for stripped-down installs.
"""

import json
import subprocess
import sys

import pytest

duckdb = pytest.importorskip("duckdb")  # noqa: F841

from benchmarks.run_sql import run_benchmark  # noqa: E402


def test_run_sql_benchmark_returns_expected_shape():
    result = run_benchmark(rows=500, cols=10, seed=42)
    assert result["engine"] == "sql"
    assert result["backend"] == "duckdb_in_process"
    assert result["rows"] == 500
    assert result["cols"] == 10
    # 6 SQL-supported rules (no regex_match / required_columns)
    assert result["rules"] == 6
    assert result["passed"] + result["failed"] + result["skipped"] + result["errored"] == 6
    assert result["wall_ms"] >= 0.0
    # RSS is 0.0 on Windows (no `resource` module); positive on Linux/macOS.
    assert result["peak_rss_mb"] >= 0.0
    rule_names = {r["name"] for r in result["rule_durations"]}
    assert "order_id_unique" in rule_names
    assert "amount_in_range" in rule_names
    # SQL benchmark must NOT include the rules SQL doesn't support
    assert "email_regex" not in rule_names
    assert "required_columns_present" not in rule_names


def test_run_sql_benchmark_cli_emits_json():
    proc = subprocess.run(
        [sys.executable, "-m", "benchmarks.run_sql", "--rows", "200", "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(proc.stdout)
    assert payload["engine"] == "sql"
    assert payload["rows"] == 200
    assert payload["rules"] == 6
