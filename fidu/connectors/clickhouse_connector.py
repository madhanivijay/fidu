import os

import clickhouse_connect

from fidu.connectors.sql_connector import SQLConnector
from fidu.core.sql_safety import validate_identifier, validate_qualified_identifier


class ClickHouseConnector(SQLConnector):
    def __init__(self):
        self.client = clickhouse_connect.get_client(
            host=os.getenv("CLICKHOUSE_HOST"),
            port=int(os.getenv("CLICKHOUSE_PORT", "8443")),
            username=os.getenv("CLICKHOUSE_USER"),
            password=os.getenv("CLICKHOUSE_PASSWORD"),
            database=os.getenv("CLICKHOUSE_DATABASE"),
            secure=os.getenv("CLICKHOUSE_SECURE", "true").lower() == "true",
        )

    def __repr__(self):
        return f"<ClickHouseConnector host={os.getenv('CLICKHOUSE_HOST')!r} (credentials masked)>"

    def execute_scalar_query(self, query: str, params=None):
        result = self.client.query(query, parameters=params or {})
        return result.result_rows[0][0] if result.result_rows else None

    def get_table_ref(self, source_config: dict) -> str:
        database = source_config.get("database")
        table = validate_identifier(source_config["table"])
        if database:
            return validate_qualified_identifier(
                f"{validate_identifier(database)}.{table}"
            )
        return table

    def get_row_count(self, table_ref: str) -> int:
        validate_qualified_identifier(table_ref)
        return int(self.execute_scalar_query(f"SELECT COUNT(*) FROM {table_ref}"))
