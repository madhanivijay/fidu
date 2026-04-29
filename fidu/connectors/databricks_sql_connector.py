import os

from databricks import sql

from fidu.connectors.sql_connector import SQLConnector
from fidu.core.sql_safety import validate_identifier, validate_qualified_identifier


class DatabricksSQLConnector(SQLConnector):
    def __init__(self):
        self.connection = sql.connect(
            server_hostname=os.getenv("DATABRICKS_SERVER_HOSTNAME"),
            http_path=os.getenv("DATABRICKS_HTTP_PATH"),
            access_token=os.getenv("DATABRICKS_ACCESS_TOKEN"),
        )

    def __repr__(self):
        return f"<DatabricksSQLConnector host={os.getenv('DATABRICKS_SERVER_HOSTNAME')!r} (credentials masked)>"

    def execute_scalar_query(self, query: str, params=None):
        cursor = self.connection.cursor()
        try:
            cursor.execute(query, params or ())
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            cursor.close()

    def get_table_ref(self, source_config: dict) -> str:
        catalog = source_config.get("catalog")
        schema = source_config.get("schema")
        table = validate_identifier(source_config["table"])
        if catalog and schema:
            return validate_qualified_identifier(
                f"{validate_identifier(catalog)}.{validate_identifier(schema)}.{table}"
            )
        if schema:
            return validate_qualified_identifier(
                f"{validate_identifier(schema)}.{table}"
            )
        return table

    def get_row_count(self, table_ref: str) -> int:
        validate_qualified_identifier(table_ref)
        return int(self.execute_scalar_query(f"SELECT COUNT(*) FROM {table_ref}"))
