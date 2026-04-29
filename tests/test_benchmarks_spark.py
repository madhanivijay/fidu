"""Import-only smoke test for the Spark benchmark harness.

We don't actually spin up a Spark session here -- that requires a JVM, which
isn't part of the default test environment. This test just confirms the
module imports, the CLI parses, and the SystemExit message is helpful when
PySpark isn't installed.
"""

import importlib
import subprocess
import sys

import pytest


def test_spark_benchmark_module_imports():
    # Module must import cleanly even without pyspark; the import inside
    # run_benchmark is deferred.
    mod = importlib.import_module("benchmarks.run_spark")
    assert hasattr(mod, "run_benchmark")
    assert hasattr(mod, "main")


def test_spark_benchmark_cli_help():
    proc = subprocess.run(
        [sys.executable, "-m", "benchmarks.run_spark", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Spark-engine benchmark" in proc.stdout
    assert "--rows" in proc.stdout
    assert "--driver-memory" in proc.stdout


def test_spark_benchmark_emits_helpful_error_without_pyspark():
    """When pyspark is missing, run_benchmark should exit with install hint."""
    try:
        import pyspark  # noqa: F401
    except ImportError:
        pass
    else:
        pytest.skip("pyspark is installed; this test only runs in the lite env")

    from benchmarks.run_spark import run_benchmark

    with pytest.raises(SystemExit, match=r"\[spark\]"):
        run_benchmark(rows=10, cols=6)
