from fidu.connectors.connector_factory import get_connector
from fidu.core.logging import Timer, get_logger
from fidu.core.retry import parse_retry_config, with_retry
from fidu.core.rule_filter import filter_executable_rules
from fidu.core.timeout import run_with_timeout
from fidu.engines.engine_factory import get_engine

_log = get_logger("executor")


def _make_error_rule_result(
    rule: dict, exc: BaseException, total_rows: int | None = None
) -> dict:
    """Build a canonical ``status: error`` rule result for a thrown exception."""
    return {
        "rule_name": rule["name"],
        "rule_type": rule["type"],
        "column": rule.get("column"),
        "columns": rule.get("columns"),
        "dimension": rule.get("dimension", "validity"),
        "severity": rule.get("severity", "warning"),
        "status": "error",
        "total_rows": total_rows,
        "failed_count": None,
        "pass_rate": None,
        "details": {},
        "failed_sample": [],
        "error_message": f"{type(exc).__name__}: {exc}",
    }


def _make_error_dataset_result(dataset_rules: dict, exc: BaseException) -> dict:
    """Build a canonical ``status: error`` dataset result when the dataset can't run.

    Used when the connector load fails after retry exhaustion or any other
    pre-rule-loop exception bubbles. Lets the run continue with the next
    dataset instead of tanking the whole job.
    """
    return {
        "dataset": dataset_rules.get("dataset"),
        "source": dataset_rules.get("source", {}),
        "status": "error",
        "error_message": f"{type(exc).__name__}: {exc}",
        "total_rules": 0,
        "passed_rules": 0,
        "failed_rules": 0,
        "skipped_rules": 0,
        "errored_rules": 0,
        "results": [],
        "columns_seen": [],
    }


def _emit_connector_retry(dataset: str, source_type: str | None, op: str):
    """Build an ``on_retry`` callback that emits a structured event per attempt."""

    def _cb(attempt: int, delay_ms: float, exc: BaseException) -> None:
        _log.warning(
            "connector_retry",
            extra={
                "event": "connector_retry",
                "dataset": dataset,
                "source_type": source_type,
                "operation": op,
                "attempt": attempt,
                "delay_ms": round(delay_ms, 2),
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
        )

    return _cb


class DQExecutor:
    def __init__(self, engine_name: str):
        self.engine_name = engine_name
        self.engine = get_engine(engine_name)

    def execute_dataset_rules(self, dataset_rules: dict) -> dict:
        dataset_name = dataset_rules["dataset"]
        source_type = dataset_rules.get("source", {}).get("type")
        _log.info(
            "dataset_start",
            extra={
                "event": "dataset_start",
                "dataset": dataset_name,
                "engine": self.engine_name,
                "source_type": source_type,
                "rule_count": len(dataset_rules.get("rules", [])),
            },
        )
        with Timer() as timer:
            if self.engine_name == "sql":
                result = self._execute_sql_dataset_rules(dataset_rules)
            else:
                result = self._execute_dataframe_dataset_rules(dataset_rules)
        result["duration_ms"] = timer.duration_ms
        result.setdefault("status", "completed")
        _log.info(
            "dataset_complete",
            extra={
                "event": "dataset_complete",
                "dataset": dataset_name,
                "engine": self.engine_name,
                "duration_ms": timer.duration_ms,
                "total_rules": result["total_rules"],
                "passed_rules": result["passed_rules"],
                "failed_rules": result["failed_rules"],
                "skipped_rules": result["skipped_rules"],
                "errored_rules": result["errored_rules"],
            },
        )
        return result

    def safe_execute_dataset_rules(self, dataset_rules: dict) -> dict:
        """Same as ``execute_dataset_rules`` but never raises.

        On any exception the dataset is recorded with ``status: error`` and
        an ``error_message`` field, so the surrounding run can continue with
        the next dataset.
        """
        try:
            return self.execute_dataset_rules(dataset_rules)
        except Exception as exc:
            _log.error(
                "dataset_error",
                extra={
                    "event": "dataset_error",
                    "dataset": dataset_rules.get("dataset"),
                    "engine": self.engine_name,
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                },
            )
            return _make_error_dataset_result(dataset_rules, exc)

    def _execute_dataframe_dataset_rules(self, dataset_rules: dict) -> dict:
        dataset_name = dataset_rules["dataset"]
        source_config = dataset_rules["source"]
        rules = filter_executable_rules(dataset_rules["rules"])
        connector = get_connector(source_config["type"])
        data = with_retry(
            lambda: connector.load_data(source_config),
            on_retry=_emit_connector_retry(dataset_name, source_config.get("type"), "load_data"),
            **parse_retry_config(source_config),
        )
        results = [self._run_dataframe_rule(data, rule, dataset_name) for rule in rules]
        columns_seen = list(getattr(data, "columns", []))
        return self._build_dataset_result(
            dataset_name, source_config, rules, results, columns_seen
        )

    def _run_dataframe_rule(self, data, rule: dict, dataset_name: str) -> dict:
        timeout_s = rule.get("timeout_seconds")
        error: BaseException | None = None
        result: dict | None = None
        with Timer() as timer:
            try:
                if timeout_s:
                    result = run_with_timeout(
                        lambda: self.engine.run_rule(data, rule), float(timeout_s)
                    )
                else:
                    result = self.engine.run_rule(data, rule)
            except Exception as exc:  # noqa: BLE001
                error = exc
        if error is not None:
            result = _make_error_rule_result(rule, error, total_rows=len(data))
        assert result is not None
        result["duration_ms"] = timer.duration_ms
        self._log_rule(dataset_name, rule, result, timer.duration_ms)
        return result

    def _execute_sql_dataset_rules(self, dataset_rules: dict) -> dict:
        dataset_name = dataset_rules["dataset"]
        source_config = dataset_rules["source"]
        rules = filter_executable_rules(dataset_rules["rules"])
        connector = get_connector(source_config["type"])
        retry_kwargs = parse_retry_config(source_config)
        source_type = source_config.get("type")
        table_ref = with_retry(
            lambda: connector.get_table_ref(source_config),
            on_retry=_emit_connector_retry(dataset_name, source_type, "get_table_ref"),
            **retry_kwargs,
        )
        total_rows = with_retry(
            lambda: connector.get_row_count(table_ref),
            on_retry=_emit_connector_retry(dataset_name, source_type, "get_row_count"),
            **retry_kwargs,
        )
        results = [
            self._run_sql_rule(
                connector, table_ref, rule, total_rows, dataset_name, retry_kwargs, source_type
            )
            for rule in rules
        ]
        columns_seen = source_config.get("columns") or []
        return self._build_dataset_result(
            dataset_name, source_config, rules, results, columns_seen
        )

    def _run_sql_rule(
        self, connector, table_ref, rule, total_rows, dataset_name, retry_kwargs, source_type
    ):
        timeout_s = rule.get("timeout_seconds")
        query = self.engine.build_rule_query(table_ref, rule)

        def _run_query():
            return with_retry(
                lambda: connector.execute_scalar_query(query),
                on_retry=_emit_connector_retry(
                    dataset_name, source_type, "execute_scalar_query"
                ),
                **retry_kwargs,
            )

        error: BaseException | None = None
        failed_count = 0
        with Timer() as timer:
            try:
                raw_count = (
                    run_with_timeout(_run_query, float(timeout_s)) if timeout_s else _run_query()
                )
                failed_count = int(raw_count or 0)
            except Exception as exc:  # noqa: BLE001
                error = exc

        if error is not None:
            err = _make_error_rule_result(rule, error, total_rows=total_rows)
            err["duration_ms"] = timer.duration_ms
            err["details"] = {"query": query.strip()}
            self._log_rule(dataset_name, rule, err, timer.duration_ms)
            return err

        pass_rate = (
            round((total_rows - failed_count) / total_rows, 4)
            if total_rows and total_rows > 0
            else 0
        )
        result = {
            "rule_name": rule["name"],
            "rule_type": rule["type"],
            "column": rule.get("column"),
            "columns": rule.get("columns"),
            "dimension": rule.get("dimension", "validity"),
            "severity": rule.get("severity", "warning"),
            "status": "passed" if failed_count == 0 else "failed",
            "total_rows": total_rows,
            "failed_count": failed_count,
            "pass_rate": pass_rate,
            "details": {"query": query.strip()},
            "failed_sample": [],
            "duration_ms": timer.duration_ms,
        }
        self._log_rule(dataset_name, rule, result, timer.duration_ms)
        return result

    def _log_rule(self, dataset_name: str, rule: dict, result: dict, duration_ms: float) -> None:
        _log.info(
            "rule_complete",
            extra={
                "event": "rule_complete",
                "dataset": dataset_name,
                "engine": self.engine_name,
                "rule_name": rule["name"],
                "rule_type": rule["type"],
                "dimension": rule.get("dimension", "validity"),
                "severity": rule.get("severity", "warning"),
                "status": result["status"],
                "failed_count": result.get("failed_count"),
                "pass_rate": result.get("pass_rate"),
                "duration_ms": duration_ms,
            },
        )

    def _build_dataset_result(self, dataset_name, source_config, rules, rule_results, columns_seen):
        return {
            "dataset": dataset_name,
            "source": source_config,
            "total_rules": len(rules),
            "passed_rules": sum(1 for r in rule_results if r["status"] == "passed"),
            "failed_rules": sum(1 for r in rule_results if r["status"] == "failed"),
            "skipped_rules": sum(1 for r in rule_results if r["status"] == "skipped"),
            "errored_rules": sum(1 for r in rule_results if r["status"] == "error"),
            "results": rule_results,
            "columns_seen": list(columns_seen) if columns_seen else [],
        }
