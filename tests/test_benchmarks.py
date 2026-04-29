"""Tiny-scale regression test for the benchmark harness.

This is *not* a performance test -- it just verifies that the data generator,
rule set, and CLI orchestrator wire together correctly so the benchmark suite
keeps working as the executor evolves.
"""

import json
import subprocess
import sys

from benchmarks.generate_data import generate
from benchmarks.run import run_benchmark


def test_generate_minimum_schema():
    df = generate(rows=200, cols=6, seed=1)
    assert len(df) == 200
    assert set(df.columns) == {"order_id", "customer_id", "amount", "status", "email", "created_at"}
    assert df["order_id"].is_unique


def test_generate_pads_to_target_column_count():
    df = generate(rows=50, cols=12, seed=1)
    assert len(df.columns) == 12
    extra_cols = [c for c in df.columns if c.startswith(("text_", "num_"))]
    assert len(extra_cols) == 6


def test_generate_is_deterministic_for_seed():
    a = generate(rows=100, cols=10, seed=99)
    b = generate(rows=100, cols=10, seed=99)
    assert a.equals(b)


def test_run_benchmark_returns_expected_shape():
    result = run_benchmark(engine="pandas", rows=500, cols=10, seed=42)
    assert result["engine"] == "pandas"
    assert result["rows"] == 500
    assert result["cols"] == 10
    assert result["rules"] == 8
    assert result["passed"] + result["failed"] + result["skipped"] + result["errored"] == 8
    assert result["wall_ms"] >= 0.0
    # RSS is 0.0 on Windows (no `resource` module); positive on Linux/macOS.
    assert result["peak_rss_mb"] >= 0.0
    rule_names = {r["name"] for r in result["rule_durations"]}
    assert "order_id_unique" in rule_names
    assert "email_regex" in rule_names
    for r in result["rule_durations"]:
        assert r["duration_ms"] >= 0.0


def test_run_benchmark_cli_emits_json():
    proc = subprocess.run(
        [sys.executable, "-m", "benchmarks.run", "--rows", "200", "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(proc.stdout)
    assert payload["rows"] == 200
    assert payload["rules"] == 8


def test_run_benchmark_cli_emits_markdown_row():
    proc = subprocess.run(
        [sys.executable, "-m", "benchmarks.run", "--rows", "200"],
        capture_output=True,
        text=True,
        check=True,
    )
    line = proc.stdout.strip()
    assert line.startswith("| pandas |")
    assert line.endswith("|")
    assert line.count("|") >= 8
