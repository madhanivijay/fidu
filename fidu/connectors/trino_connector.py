import os

import trino

from fidu.connectors.sql_connector import SQLConnector
from fidu.core.sql_safety import validate_identifier, validate_qualified_identifier


class TrinoConnector(SQLConnector):
    def __init__(self):
        self.connection = trino.dbapi.connect(
            host=os.getenv("TRINO_HOST"),
            port=int(os.getenv("TRINO_PORT", "443")),
            user=os.getenv("TRINO_USER"),
            catalog=os.getenv("TRINO_CATALOG"),
            schema=os.getenv("TRINO_SCHEMA"),
            http_scheme=os.getenv("TRINO_HTTP_SCHEME", "https"),
        )

    def __repr__(self):
        return f"<TrinoConnector host={os.getenv('TRINO_HOST')!r} user={os.getenv('TRINO_USER')!r} (credentials masked)>"

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
