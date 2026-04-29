"""Canonical rule-result schema used by every engine and tool adapter.

Native engines (pandas / SQL / Spark) and tool adapters (Soda / GX / Deequ)
all return dictionaries with at least these keys. Downstream consumers
(scorecard CSV, drift detector, Streamlit UI) rely on this contract.
"""

CANONICAL_KEYS = (
    "rule_name",
    "rule_type",
    "column",
    "columns",
    "dimension",
    "severity",
    "status",
    "total_rows",
    "failed_count",
    "pass_rate",
    "failed_sample",
)

VALID_STATUSES = frozenset({"passed", "failed", "skipped", "error"})


def is_canonical(result: dict) -> bool:
    if not isinstance(result, dict):
        return False
    if not all(key in result for key in CANONICAL_KEYS):
        return False
    return result["status"] in VALID_STATUSES


def assert_canonical(result: dict) -> dict:
    if not is_canonical(result):
        missing = [k for k in CANONICAL_KEYS if k not in result]
        status = result.get("status") if isinstance(result, dict) else None
        raise ValueError(
            f"Non-canonical rule result. missing_keys={missing}, status={status!r}"
        )
    return result
