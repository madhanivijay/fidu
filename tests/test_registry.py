import pytest

from fidu.connectors.connector_factory import connector_registry, get_connector
from fidu.core.registry import PluginRegistry
from fidu.engines.engine_factory import engine_registry, get_engine
from fidu.tool_adapters.tool_adapter_factory import (
    get_tool_adapter,
    tool_adapter_registry,
)


def test_registry_register_and_create():
    reg = PluginRegistry("widget")
    reg.register("alpha", lambda: {"kind": "alpha"})
    assert reg.create("alpha") == {"kind": "alpha"}
    assert reg.create("ALPHA") == {"kind": "alpha"}  # case-insensitive
    assert "alpha" in reg
    assert "missing" not in reg


def test_registry_aliases():
    reg = PluginRegistry("widget")
    reg.register("great_expectations", lambda: "gx-instance", aliases=["gx"])
    assert reg.create("gx") == "gx-instance"
    assert reg.create("great_expectations") == "gx-instance"


def test_registry_unknown_raises_with_listing():
    reg = PluginRegistry("widget")
    reg.register("alpha", lambda: 1)
    with pytest.raises(ValueError) as exc:
        reg.create("zeta")
    assert "alpha" in str(exc.value)
    assert "zeta" in str(exc.value)


def test_connector_registry_known_types():
    expected = {
        "csv",
        "parquet",
        "local_file",
        "s3_file",
        "adls_file",
        "duckdb_csv",
        "spark_file",
        "snowflake",
        "trino",
        "clickhouse",
        "databricks_sql",
    }
    assert expected.issubset(set(connector_registry.names()))


def test_connector_factory_csv_instantiates():
    assert get_connector("csv") is not None


def test_connector_factory_unknown_raises():
    with pytest.raises(ValueError):
        get_connector("not_a_real_source")


def test_engine_registry_known_engines():
    assert {"pandas", "sql", "spark"}.issubset(set(engine_registry.names()))


def test_engine_factory_pandas_instantiates():
    assert get_engine("pandas") is not None


def test_tool_adapter_aliases():
    assert get_tool_adapter("gx") is not None
    assert get_tool_adapter("great_expectations") is not None


def test_tool_adapter_registry_names():
    assert {"soda", "great_expectations", "deequ"}.issubset(
        set(tool_adapter_registry.names())
    )
