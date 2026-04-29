"""Shared constants used across engines, translators, and trust scoring."""

SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

SEVERITY_WEIGHTS = {
    SEVERITY_CRITICAL: 1.0,
    SEVERITY_WARNING: 0.5,
    SEVERITY_INFO: 0.25,
}

DEFAULT_SEVERITY = SEVERITY_WARNING
DEFAULT_DIMENSION = "validity"

GRADE_THRESHOLD_TRUSTED = 95
GRADE_THRESHOLD_NEEDS_REVIEW = 85
GRADE_THRESHOLD_UNSTABLE = 70

DRIFT_DEFAULT_SCORE_DROP = 5.0
DRIFT_DEFAULT_DIMENSION_DROP = 10.0

EXIT_OK = 0
EXIT_CRITICAL_FAILURES = 10
EXIT_CRITICAL_DRIFT = 11

DEFAULT_TOOL_TIMEOUT_SECONDS = 600

OUTPUT_SCHEMA_VERSION = "1.1.0"

# Input contract: rule and config YAMLs must declare a top-level
# ``schema_version: 1`` so the kit can detect future breaking changes early.
# Missing => warning; unknown major => error.
INPUT_SCHEMA_VERSION = 1
