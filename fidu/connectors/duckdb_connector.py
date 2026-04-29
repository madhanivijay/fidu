import os

import duckdb

from fidu.connectors.sql_connector import SQLConnector
from fidu.core.sql_safety import validate_identifier, validate_qualified_identifier


class UnsafeDataPath(ValueError):
    """Raised when a configured data path escapes the allowed root."""


class DuckDBConnector(SQLConnector):
    """In-process DuckDB connector with hardened identifier and path handling."""

    def __init__(self, allowed_root: str = None):
        self.connection = duckdb.connect()
        self.allowed_root = os.path.abspath(allowed_root) if allowed_root else None

    def _resolve_path(self, raw_path: str) -> str:
        if not isinstance(raw_path, str) or not raw_path:
            raise UnsafeDataPath(f"Invalid path: {raw_path!r}")
        if "\x00" in raw_path:
            raise UnsafeDataPath("NUL byte not allowed in path.")
        resolved = os.path.abspath(raw_path)
        if self.allowed_root and not (
            resolved == self.allowed_root
            or resolved.startswith(self.allowed_root + os.sep)
        ):
            raise UnsafeDataPath(
                f"Path {resolved!r} is outside allowed root {self.allowed_root!r}."
            )
        return resolved

    def register_csv_as_table(self, table_name: str, path: str):
        validate_identifier(table_name)
        safe_path = self._resolve_path(path)
        # Read with pandas + DuckDB's register API rather than interpolating the
        # path into DDL. DuckDB does not support prepared params in DDL.
        import pandas as pd

        df = pd.read_csv(safe_path)
        self.connection.register(table_name, df)

    def execute_scalar_query(self, query: str, params=None):
        cursor = self.connection.execute(query, params or [])
        result = cursor.fetchone()
        return result[0] if result else None

    def get_table_ref(self, source_config: dict) -> str:
        table_name = source_config["table"]
        validate_identifier(table_name)
        if source_config.get("type") == "duckdb_csv":
            self.register_csv_as_table(table_name, source_config["path"])
        validate_qualified_identifier(table_name)
        return table_name

    def get_row_count(self, table_ref: str) -> int:
        validate_qualified_identifier(table_ref)
        return int(self.execute_scalar_query(f"SELECT COUNT(*) FROM {table_ref}"))
