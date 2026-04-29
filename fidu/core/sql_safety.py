"""Defense-in-depth helpers for safely building SQL queries from rule YAML.

Identifier names are validated against a strict regex so they cannot escape
into SQL syntax. Numeric values are coerced via ``int``/``float``. String
values are wrapped as SQL string literals with ``'`` doubled (ANSI standard,
supported by Snowflake, Trino, Databricks SQL, ClickHouse, DuckDB).
"""

import re

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_MAX_QUALIFIED_PARTS = 4


class UnsafeSQLIdentifier(ValueError):
    """Raised when an identifier from a rule fails validation."""


def validate_identifier(name) -> str:
    if not isinstance(name, str) or not _IDENTIFIER_RE.match(name):
        raise UnsafeSQLIdentifier(f"Unsafe SQL identifier: {name!r}")
    return name


def validate_qualified_identifier(name) -> str:
    if not isinstance(name, str):
        raise UnsafeSQLIdentifier(f"Unsafe qualified identifier: {name!r}")
    parts = name.split(".")
    if not parts or len(parts) > _MAX_QUALIFIED_PARTS:
        raise UnsafeSQLIdentifier(f"Unsafe qualified identifier: {name!r}")
    for part in parts:
        validate_identifier(part)
    return name


def validate_identifier_list(names) -> list:
    if not isinstance(names, (list, tuple)) or not names:
        raise UnsafeSQLIdentifier(f"Identifier list must be a non-empty list, got {names!r}")
    return [validate_identifier(n) for n in names]


def safe_numeric(value) -> str:
    if isinstance(value, bool):
        raise ValueError(f"Numeric expected, got bool: {value!r}")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        try:
            return str(int(value))
        except ValueError:
            pass
        try:
            return repr(float(value))
        except ValueError:
            pass
    raise ValueError(f"Numeric value expected, got {value!r}")


def safe_string_literal(value) -> str:
    if value is None:
        return "NULL"
    s = str(value)
    if "\x00" in s:
        raise ValueError("NUL byte not allowed in SQL string literal.")
    return "'" + s.replace("'", "''") + "'"
