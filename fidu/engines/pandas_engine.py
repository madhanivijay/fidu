from datetime import timezone

import pandas as pd

from fidu.core.regex_safety import validate_pattern
from fidu.engines.base_engine import BaseDQEngine


class PandasDQEngine(BaseDQEngine):
    def run_rule(self, data, rule: dict) -> dict:
        rule_type = rule["type"]
        handlers = {
            "not_null": self._not_null,
            "min_value": self._min_value,
            "max_value": self._max_value,
            "between": self._between,
            "accepted_values": self._accepted_values,
            "unique": self._unique,
            "duplicate_check": self._duplicate_check,
            "regex_match": self._regex_match,
            "freshness": self._freshness,
            "row_count_min": self._row_count_min,
            "row_count_max": self._row_count_max,
            "required_columns": self._required_columns,
            "column_type_check": self._column_type_check,
            "schema_drift_check": self._schema_drift_check,
        }
        if rule_type not in handlers:
            raise ValueError(f"Unsupported Pandas rule type: {rule_type}")
        return handlers[rule_type](data, rule)

    @staticmethod
    def _apply_null_policy(df, column, value_violation_mask, treat_null_as: str):
        """Combine value-violation mask with null handling. Default: nulls fail."""
        is_null = df[column].isna()
        if treat_null_as == "pass" or treat_null_as == "skip":
            failed_mask = value_violation_mask & ~is_null
        else:
            failed_mask = value_violation_mask | is_null
        return df[failed_mask]

    def _not_null(self, df, rule):
        return self._build_result(rule, df[df[rule["column"]].isna()], len(df))

    def _min_value(self, df, rule):
        c = rule["column"]
        violation = df[c] < rule["value"]
        failed = self._apply_null_policy(df, c, violation.fillna(False), rule.get("treat_null_as", "fail"))
        return self._build_result(rule, failed, len(df))

    def _max_value(self, df, rule):
        c = rule["column"]
        violation = df[c] > rule["value"]
        failed = self._apply_null_policy(df, c, violation.fillna(False), rule.get("treat_null_as", "fail"))
        return self._build_result(rule, failed, len(df))

    def _between(self, df, rule):
        c = rule["column"]
        violation = (df[c] < rule["min_value"]) | (df[c] > rule["max_value"])
        failed = self._apply_null_policy(df, c, violation.fillna(False), rule.get("treat_null_as", "fail"))
        return self._build_result(rule, failed, len(df))

    def _accepted_values(self, df, rule):
        c = rule["column"]
        violation = ~df[c].isin(rule["values"])
        failed = self._apply_null_policy(df, c, violation, rule.get("treat_null_as", "fail"))
        return self._build_result(rule, failed, len(df))

    def _unique(self, df, rule):
        c = rule["column"]
        return self._build_result(rule, df[df[c].duplicated(keep=False)], len(df))

    def _duplicate_check(self, df, rule):
        cols = rule["columns"]
        return self._build_result(rule, df[df.duplicated(subset=cols, keep=False)], len(df))

    def _regex_match(self, df, rule):
        c = rule["column"]
        column = df[c]
        pattern = validate_pattern(rule["pattern"])
        treat_null_as = rule.get("treat_null_as", "fail")
        matches = column.astype("string").str.match(pattern, na=False)
        if treat_null_as in ("pass", "skip"):
            matches = matches | column.isna()
        failed = df[~matches]
        return self._build_result(rule, failed, len(df))

    def _freshness(self, df, rule):
        dates = pd.to_datetime(df[rule["column"]], errors="coerce", utc=True)
        latest = dates.max()
        if pd.isna(latest):
            failed = df
        else:
            now = pd.Timestamp.now(tz=timezone.utc)
            age_days = (now - latest).days
            failed = df if age_days > rule.get("max_age_days", 1) else df.iloc[0:0]
        return self._build_result(rule, failed, len(df))

    def _row_count_min(self, df, rule):
        failed = df if len(df) < rule["value"] else df.iloc[0:0]
        return self._build_result(rule, failed, len(df))

    def _row_count_max(self, df, rule):
        failed = df if len(df) > rule["value"] else df.iloc[0:0]
        return self._build_result(rule, failed, len(df))

    def _required_columns(self, df, rule):
        required = set(rule["columns"])
        actual = set(df.columns)
        missing = sorted(required - actual)
        return self._build_metadata_result(rule, "failed" if missing else "passed", len(df), {
            "missing_columns": missing,
            "required_columns": sorted(required),
            "actual_columns": sorted(actual),
        })

    def _column_type_check(self, df, rule):
        c = rule["column"]
        expected = rule["expected_type"]
        if c not in df.columns:
            return self._build_metadata_result(rule, "failed", len(df), {"reason": "column_not_found", "column": c})
        s = df[c]
        if expected == "numeric":
            converted = pd.to_numeric(s, errors="coerce")
            failed_count = int(converted.isna().sum() - s.isna().sum())
        elif expected == "date":
            converted = pd.to_datetime(s, errors="coerce")
            failed_count = int(converted.isna().sum() - s.isna().sum())
        elif expected == "string":
            failed_count = 0
        else:
            raise ValueError(f"Unsupported expected_type: {expected}")
        return self._build_metadata_result(rule, "passed" if failed_count == 0 else "failed", len(df), {
            "column": c, "expected_type": expected, "failed_count": failed_count
        }, failed_count=failed_count)

    def _schema_drift_check(self, df, rule):
        expected = set(rule["expected_columns"])
        actual = set(df.columns)
        extra = sorted(actual - expected)
        missing = sorted(expected - actual)
        allow_extra = rule.get("allow_extra_columns", True)
        failed = bool(missing) or (not allow_extra and bool(extra))
        return self._build_metadata_result(rule, "failed" if failed else "passed", len(df), {
            "missing_columns": missing, "extra_columns": extra,
            "expected_columns": sorted(expected), "actual_columns": sorted(actual),
            "allow_extra_columns": allow_extra
        })

    def _build_result(self, rule, failed_rows, total_rows):
        failed_count = len(failed_rows)
        return {
            "rule_name": rule["name"],
            "rule_type": rule["type"],
            "column": rule.get("column"),
            "columns": rule.get("columns"),
            "dimension": rule.get("dimension", "validity"),
            "severity": rule.get("severity", "warning"),
            "status": "passed" if failed_count == 0 else "failed",
            "total_rows": total_rows,
            "failed_count": failed_count,
            "pass_rate": round((total_rows - failed_count) / total_rows, 4) if total_rows > 0 else 0,
            "failed_sample": failed_rows.head(10).to_dict(orient="records")
        }

    def _build_metadata_result(self, rule, status, total_rows, details, failed_count=None):
        if failed_count is None:
            failed_count = total_rows if status == "failed" else 0
        return {
            "rule_name": rule["name"],
            "rule_type": rule["type"],
            "column": rule.get("column"),
            "columns": rule.get("columns"),
            "dimension": rule.get("dimension", "consistency"),
            "severity": rule.get("severity", "warning"),
            "status": status,
            "total_rows": total_rows,
            "failed_count": failed_count,
            "pass_rate": round((total_rows - failed_count) / total_rows, 4) if total_rows > 0 else 0,
            "details": details,
            "failed_sample": []
        }
