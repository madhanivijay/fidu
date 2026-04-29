from fidu.core.sql_safety import (
    safe_numeric,
    safe_string_literal,
    validate_identifier,
    validate_identifier_list,
    validate_qualified_identifier,
)


class SQLDQEngine:
    """SQL rule-to-query builder.

    Identifiers are validated against a strict regex; numeric values are
    coerced to int/float; string values are wrapped in safely-escaped literals.
    Together these prevent SQL injection from malicious rule YAML.
    """

    def build_rule_query(self, table_ref: str, rule: dict) -> str:
        validate_qualified_identifier(table_ref)
        rule_type = rule["type"]

        if rule_type == "not_null":
            col = validate_identifier(rule["column"])
            return (
                f"SELECT COUNT(*) AS failed_count FROM {table_ref} "
                f"WHERE {col} IS NULL"
            )

        if rule_type == "accepted_values":
            col = validate_identifier(rule["column"])
            values = ", ".join(safe_string_literal(v) for v in rule["values"])
            return (
                f"SELECT COUNT(*) AS failed_count FROM {table_ref} "
                f"WHERE {col} NOT IN ({values}) OR {col} IS NULL"
            )

        if rule_type == "min_value":
            col = validate_identifier(rule["column"])
            value = safe_numeric(rule["value"])
            return (
                f"SELECT COUNT(*) AS failed_count FROM {table_ref} "
                f"WHERE {col} < {value} OR {col} IS NULL"
            )

        if rule_type == "max_value":
            col = validate_identifier(rule["column"])
            value = safe_numeric(rule["value"])
            return (
                f"SELECT COUNT(*) AS failed_count FROM {table_ref} "
                f"WHERE {col} > {value} OR {col} IS NULL"
            )

        if rule_type == "between":
            col = validate_identifier(rule["column"])
            lo = safe_numeric(rule["min_value"])
            hi = safe_numeric(rule["max_value"])
            return (
                f"SELECT COUNT(*) AS failed_count FROM {table_ref} "
                f"WHERE {col} < {lo} OR {col} > {hi} OR {col} IS NULL"
            )

        if rule_type == "unique":
            col = validate_identifier(rule["column"])
            return (
                f"SELECT COUNT(*) AS failed_count FROM "
                f"(SELECT {col} FROM {table_ref} GROUP BY {col} "
                f"HAVING COUNT(*) > 1) duplicates"
            )

        if rule_type == "duplicate_check":
            cols = ", ".join(validate_identifier_list(rule["columns"]))
            return (
                f"SELECT COUNT(*) AS failed_count FROM "
                f"(SELECT {cols} FROM {table_ref} GROUP BY {cols} "
                f"HAVING COUNT(*) > 1) duplicates"
            )

        if rule_type == "row_count_min":
            value = safe_numeric(rule["value"])
            return (
                f"SELECT CASE WHEN COUNT(*) < {value} THEN COUNT(*) "
                f"ELSE 0 END AS failed_count FROM {table_ref}"
            )

        if rule_type == "row_count_max":
            value = safe_numeric(rule["value"])
            return (
                f"SELECT CASE WHEN COUNT(*) > {value} THEN COUNT(*) "
                f"ELSE 0 END AS failed_count FROM {table_ref}"
            )

        raise ValueError(f"Unsupported SQL rule type: {rule_type}")
