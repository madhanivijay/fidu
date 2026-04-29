"""Connector registry + lookup.

Heavy optional dependencies (duckdb, snowflake-connector, trino, clickhouse,
databricks, pyspark, s3fs, adlfs) are imported only when the corresponding
connector is actually requested.
"""

from fidu.core.registry import PluginRegistry

connector_registry: PluginRegistry = PluginRegistry("source type")


def _csv():
    from fidu.connectors.csv_connector import CSVConnector
    return CSVConnector()


def _parquet():
    from fidu.connectors.parquet_connector import ParquetConnector
    return ParquetConnector()


def _local_file():
    from fidu.connectors.local_file_connector import LocalFileConnector
    return LocalFileConnector()


def _s3_file():
    from fidu.connectors.s3_file_connector import S3FileConnector
    return S3FileConnector()


def _adls_file():
    from fidu.connectors.adls_file_connector import ADLSFileConnector
    return ADLSFileConnector()


def _duckdb():
    from fidu.connectors.duckdb_connector import DuckDBConnector
    return DuckDBConnector()


def _spark_file():
    from fidu.connectors.spark_file_connector import SparkFileConnector
    return SparkFileConnector()


def _snowflake():
    from fidu.connectors.snowflake_connector import SnowflakeConnector
    return SnowflakeConnector()


def _trino():
    from fidu.connectors.trino_connector import TrinoConnector
    return TrinoConnector()


def _clickhouse():
    from fidu.connectors.clickhouse_connector import ClickHouseConnector
    return ClickHouseConnector()


def _databricks_sql():
    from fidu.connectors.databricks_sql_connector import DatabricksSQLConnector
    return DatabricksSQLConnector()


connector_registry.register("csv", _csv)
connector_registry.register("parquet", _parquet)
connector_registry.register("local_file", _local_file)
connector_registry.register("s3_file", _s3_file)
connector_registry.register("adls_file", _adls_file)
connector_registry.register("duckdb_csv", _duckdb)
connector_registry.register("spark_file", _spark_file)
connector_registry.register("snowflake", _snowflake)
connector_registry.register("trino", _trino)
connector_registry.register("clickhouse", _clickhouse)
connector_registry.register("databricks_sql", _databricks_sql)


def get_connector(source_type: str):
    return connector_registry.create(source_type)


def register_connector(name, factory, aliases=None):
    """Public hook for downstream code to register a custom connector."""
    connector_registry.register(name, factory, aliases=aliases)
