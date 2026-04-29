from pyspark.sql import functions as F


class SparkDQEngine:
    def run_rule(self, data, rule: dict) -> dict:
        rt = rule["type"]
        total = data.count()
        if rt == "not_null":
            return self._build_result(rule, data.filter(F.col(rule["column"]).isNull()), total)
        if rt == "accepted_values":
            return self._build_result(rule, data.filter((~F.col(rule["column"]).isin(rule["values"])) | F.col(rule["column"]).isNull()), total)
        if rt == "min_value":
            return self._build_result(rule, data.filter((F.col(rule["column"]) < rule["value"]) | F.col(rule["column"]).isNull()), total)
        if rt == "max_value":
            return self._build_result(rule, data.filter((F.col(rule["column"]) > rule["value"]) | F.col(rule["column"]).isNull()), total)
        if rt == "between":
            c = F.col(rule["column"])
            return self._build_result(rule, data.filter((c < rule["min_value"]) | (c > rule["max_value"]) | c.isNull()), total)
        if rt == "unique":
            c = rule["column"]
            dup = data.groupBy(c).count().filter(F.col("count") > 1).select(c)
            return self._build_result(rule, data.join(dup, on=c, how="inner"), total)
        if rt == "duplicate_check":
            cols = rule["columns"]
            dup = data.groupBy(*cols).count().filter(F.col("count") > 1).select(*cols)
            return self._build_result(rule, data.join(dup, on=cols, how="inner"), total)
        if rt == "regex_match":
            c = F.col(rule["column"])
            return self._build_result(rule, data.filter((~c.cast("string").rlike(rule["pattern"])) | c.isNull()), total)
        if rt == "row_count_min":
            return self._build_result(rule, data if total < rule["value"] else data.limit(0), total)
        if rt == "row_count_max":
            return self._build_result(rule, data if total > rule["value"] else data.limit(0), total)
        if rt == "required_columns":
            return self._required_columns(data, rule, total)
        if rt == "schema_drift_check":
            return self._schema_drift_check(data, rule, total)
        raise ValueError(f"Unsupported Spark rule type: {rt}")

    def _required_columns(self, df, rule, total):
        required, actual = set(rule["columns"]), set(df.columns)
        missing = sorted(required - actual)
        return self._build_metadata_result(rule, "failed" if missing else "passed", total, {"missing_columns": missing, "required_columns": sorted(required), "actual_columns": sorted(actual)})

    def _schema_drift_check(self, df, rule, total):
        expected, actual = set(rule["expected_columns"]), set(df.columns)
        missing, extra = sorted(expected - actual), sorted(actual - expected)
        allow_extra = rule.get("allow_extra_columns", True)
        failed = bool(missing) or (not allow_extra and bool(extra))
        return self._build_metadata_result(rule, "failed" if failed else "passed", total, {"missing_columns": missing, "extra_columns": extra, "expected_columns": sorted(expected), "actual_columns": sorted(actual), "allow_extra_columns": allow_extra})

    def _build_result(self, rule, failed_df, total_rows):
        failed_count = failed_df.count()
        return {"rule_name": rule["name"], "rule_type": rule["type"], "column": rule.get("column"), "columns": rule.get("columns"), "dimension": rule.get("dimension", "validity"), "severity": rule.get("severity", "warning"), "status": "passed" if failed_count == 0 else "failed", "total_rows": total_rows, "failed_count": failed_count, "pass_rate": round((total_rows - failed_count) / total_rows, 4) if total_rows > 0 else 0, "failed_sample": [r.asDict() for r in failed_df.limit(10).collect()]}

    def _build_metadata_result(self, rule, status, total_rows, details):
        failed_count = total_rows if status == "failed" else 0
        return {"rule_name": rule["name"], "rule_type": rule["type"], "column": rule.get("column"), "columns": rule.get("columns"), "dimension": rule.get("dimension", "consistency"), "severity": rule.get("severity", "warning"), "status": status, "total_rows": total_rows, "failed_count": failed_count, "pass_rate": round((total_rows - failed_count) / total_rows, 4) if total_rows > 0 else 0, "details": details, "failed_sample": []}
