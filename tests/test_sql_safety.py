import pytest

from fidu.core.sql_safety import (
    UnsafeSQLIdentifier,
    safe_numeric,
    safe_string_literal,
    validate_identifier,
    validate_identifier_list,
    validate_qualified_identifier,
)


@pytest.mark.parametrize("name", ["orders", "Orders_2024", "_internal", "a" * 128])
def test_validate_identifier_accepts_safe_names(name):
    assert validate_identifier(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "orders; DROP TABLE users",
        "a b",
        "1col",
        "",
        None,
        "col)",
        "a-b",
        "a" * 129,
    ],
)
def test_validate_identifier_rejects_unsafe_names(name):
    with pytest.raises(UnsafeSQLIdentifier):
        validate_identifier(name)


def test_validate_qualified_identifier_allows_dotted():
    assert validate_qualified_identifier("db.schema.table") == "db.schema.table"


def test_validate_qualified_identifier_rejects_too_many_parts():
    with pytest.raises(UnsafeSQLIdentifier):
        validate_qualified_identifier("a.b.c.d.e")


def test_validate_qualified_identifier_rejects_unsafe_part():
    with pytest.raises(UnsafeSQLIdentifier):
        validate_qualified_identifier("db.schema.tab--le")


def test_validate_identifier_list_requires_non_empty():
    with pytest.raises(UnsafeSQLIdentifier):
        validate_identifier_list([])


def test_safe_numeric_accepts_int_float_str():
    assert safe_numeric(5) == "5"
    assert safe_numeric(5.5) == repr(5.5)
    assert safe_numeric("12") == "12"


def test_safe_numeric_rejects_bool_and_garbage():
    with pytest.raises(ValueError):
        safe_numeric(True)
    with pytest.raises(ValueError):
        safe_numeric("12; DROP")


def test_safe_string_literal_escapes_single_quote():
    assert safe_string_literal("O'Brien") == "'O''Brien'"
    assert safe_string_literal(None) == "NULL"


def test_safe_string_literal_rejects_nul_byte():
    with pytest.raises(ValueError):
        safe_string_literal("a\x00b")
