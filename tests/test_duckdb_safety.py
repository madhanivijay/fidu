import os

import pytest

from fidu.connectors.duckdb_connector import DuckDBConnector, UnsafeDataPath
from fidu.core.sql_safety import UnsafeSQLIdentifier


def _make_connector(tmp_path):
    return DuckDBConnector(allowed_root=str(tmp_path))


def test_resolve_path_rejects_path_outside_allowed_root(tmp_path):
    connector = _make_connector(tmp_path)
    with pytest.raises(UnsafeDataPath):
        connector._resolve_path("/etc/passwd")


def test_resolve_path_rejects_traversal(tmp_path):
    connector = _make_connector(tmp_path)
    with pytest.raises(UnsafeDataPath):
        connector._resolve_path(str(tmp_path) + "/../../../etc/passwd")


def test_resolve_path_accepts_in_root(tmp_path):
    csv = tmp_path / "data.csv"
    csv.write_text("a,b\n1,2\n")
    connector = _make_connector(tmp_path)
    resolved = connector._resolve_path(str(csv))
    assert resolved == os.path.abspath(str(csv))


def test_register_csv_validates_table_identifier(tmp_path):
    csv = tmp_path / "data.csv"
    csv.write_text("a,b\n1,2\n")
    connector = _make_connector(tmp_path)
    with pytest.raises(UnsafeSQLIdentifier):
        connector.register_csv_as_table("orders; DROP TABLE x", str(csv))


def test_register_csv_loads_via_pandas(tmp_path):
    csv = tmp_path / "data.csv"
    csv.write_text("a,b\n1,2\n3,4\n")
    connector = _make_connector(tmp_path)
    connector.register_csv_as_table("orders", str(csv))
    count = connector.execute_scalar_query("SELECT COUNT(*) FROM orders")
    assert count == 2
