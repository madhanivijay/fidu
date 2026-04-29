from abc import ABC, abstractmethod


class SQLConnector(ABC):
    """Base contract for SQL-style connectors used by the SQL engine."""

    @abstractmethod
    def execute_scalar_query(self, query: str, params=None):
        raise NotImplementedError

    @abstractmethod
    def get_table_ref(self, source_config: dict) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_row_count(self, table_ref: str) -> int:
        raise NotImplementedError
