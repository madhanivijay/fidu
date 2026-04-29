import os

import snowflake.connector

from fidu.connectors.sql_connector import SQLConnector
from fidu.core.sql_safety import validate_identifier, validate_qualified_identifier


class SnowflakeConnector(SQLConnector):
    def __init__(self):
        self.connection = snowflake.connector.connect(
            user=os.getenv("SNOWFLAKE_USER"),
            password=os.getenv("SNOWFLAKE_PASSWORD"),
            account=os.getenv("SNOWFLAKE_ACCOUNT"),
            warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
            database=os.getenv("SNOWFLAKE_DATABASE"),
            schema=os.getenv("SNOWFLAKE_SCHEMA"),
            role=os.getenv("SNOWFLAKE_ROLE"),
        )

    def __repr__(self):
        return f"<SnowflakeConnector account={os.getenv('SNOWFLAKE_ACCOUNT')!r} user={os.getenv('SNOWFLAKE_USER')!r} (credentials masked)>"

    def execute_scalar_query(self, query: str, params=None):
        cursor = self.connection.cursor()
        try:
            cursor.execute(query, params or ())
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            cursor.close()

    def get_table_ref(self, source_config: dict) -> str:
        database = source_config.get("database")
        schema = source_config.get("schema")
        table = validate_identifier(source_config["table"])
        if database and schema:
            return validate_qualified_identifier(
                f"{validate_identifier(database)}.{validate_identifier(schema)}.{table}"
            )
        if schema:
            return validate_qualified_identifier(
                f"{validate_identifier(schema)}.{table}"
            )
        return table

    def get_row_count(self, table_ref: str) -> int:
        validate_qualified_identifier(table_ref)
        return int(self.execute_scalar_query(f"SELECT COUNT(*) FROM {table_ref}"))
