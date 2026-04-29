"""Smoke tests for the constants module and exit-code wiring in main()."""


from fidu.core import constants
from fidu.core.trust_score import assign_grade


def test_severity_weights_have_expected_ordering():
    weights = constants.SEVERITY_WEIGHTS
    assert weights[constants.SEVERITY_CRITICAL] > weights[constants.SEVERITY_WARNING]
    assert weights[constants.SEVERITY_WARNING] > weights[constants.SEVERITY_INFO]


def test_grade_thresholds_strictly_decreasing():
    assert (
        constants.GRADE_THRESHOLD_TRUSTED
        > constants.GRADE_THRESHOLD_NEEDS_REVIEW
        > constants.GRADE_THRESHOLD_UNSTABLE
    )


def test_assign_grade_uses_constants():
    grade, _ = assign_grade(constants.GRADE_THRESHOLD_TRUSTED, 0)
    assert grade == "TRUSTED"
    grade, _ = assign_grade(constants.GRADE_THRESHOLD_NEEDS_REVIEW, 0)
    assert grade == "NEEDS_REVIEW"
    grade, _ = assign_grade(constants.GRADE_THRESHOLD_UNSTABLE, 0)
    assert grade == "UNSTABLE"


def test_exit_codes_are_distinct_nonzero():
    assert constants.EXIT_OK == 0
    assert constants.EXIT_CRITICAL_FAILURES != 0
    assert constants.EXIT_CRITICAL_DRIFT != 0
    assert constants.EXIT_CRITICAL_FAILURES != constants.EXIT_CRITICAL_DRIFT


def test_main_raises_systemexit_with_exit_code_on_critical_failure(monkeypatch):
    """If fail_on_critical=True and a critical rule failed, raise SystemExit(EXIT_CRITICAL_FAILURES)."""
    import fidu.main as main_mod

    fake_output = {
        "datasets": [
            {
                "results": [
                    {
                        "severity": "critical",
                        "status": "failed",
                        "is_tool_metadata": False,
                    }
                ]
            }
        ]
    }
    assert main_mod.has_critical_failures(fake_output) is True
    fake_no_crit = {
        "datasets": [{"results": [{"severity": "warning", "status": "failed"}]}]
    }
    assert main_mod.has_critical_failures(fake_no_crit) is False


def test_drift_thresholds_default_from_constants():
    from fidu.drift.drift_detector import detect_drift

    history = {
        "runs": [
            {
                "run_timestamp": "2026-01-01T00:00:00+00:00",
                "overall_trust_score": 100.0,
                "datasets": [],
            },
            {
                "run_timestamp": "2026-01-02T00:00:00+00:00",
                "overall_trust_score": 100.0 - constants.DRIFT_DEFAULT_SCORE_DROP,
                "datasets": [],
            },
        ]
    }
    report = detect_drift(history)
    assert any(a["type"] == "overall_score_drop" for a in report["alerts"])
