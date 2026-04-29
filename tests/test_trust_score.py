from fidu.core.trust_score import (
    GRADE_HIGH_RISK,
    GRADE_NO_RULES,
    GRADE_TRANSLATION_ONLY,
    GRADE_TRUSTED,
    assign_grade,
    calculate_dataset_trust_score,
    calculate_project_trust_score,
)


def _rule(status, severity="warning", pass_rate=1.0, dimension="validity", **kw):
    return {
        "rule_name": kw.get("name", "r"),
        "rule_type": kw.get("type", "not_null"),
        "status": status,
        "severity": severity,
        "pass_rate": pass_rate,
        "dimension": dimension,
        "failed_count": 0 if status == "passed" else 1,
        "total_rows": 10,
    }


def test_translation_only_dataset_yields_no_score():
    dataset = {
        "dataset": "orders",
        "results": [
            _rule("skipped", pass_rate=None),
            _rule("skipped", pass_rate=None),
        ],
    }
    score = calculate_dataset_trust_score(dataset)
    assert score["trust_score"] is None
    assert score["grade"] == GRADE_TRANSLATION_ONLY
    assert "translated only" in score["grade_reason"].lower()


def test_no_rules_dataset_yields_no_score():
    dataset = {"dataset": "empty", "results": []}
    score = calculate_dataset_trust_score(dataset)
    assert score["trust_score"] is None
    assert score["grade"] == GRADE_NO_RULES


def test_critical_failure_overrides_score_grade():
    grade, reason = assign_grade(94, critical_failures=1)
    assert grade == GRADE_HIGH_RISK
    assert "critical" in reason.lower()


def test_score_above_95_is_trusted():
    grade, _ = assign_grade(98, critical_failures=0)
    assert grade == GRADE_TRUSTED


def test_project_score_excludes_translation_only_datasets():
    final = {
        "datasets": [
            {
                "dataset": "executed",
                "results": [
                    _rule("passed", pass_rate=1.0, severity="critical"),
                    _rule("passed", pass_rate=1.0, severity="warning"),
                ],
            },
            {
                "dataset": "translated",
                "results": [_rule("skipped", pass_rate=None)],
            },
        ]
    }
    summary = calculate_project_trust_score(final)
    assert summary["overall_trust_score"] == 100
    assert summary["overall_grade"] == GRADE_TRUSTED
    grades = {d["dataset"]: d["grade"] for d in summary["dataset_scores"]}
    assert grades["translated"] == GRADE_TRANSLATION_ONLY


def test_project_score_with_no_executable_rules_is_translation_only():
    final = {
        "datasets": [
            {
                "dataset": "translated",
                "results": [_rule("skipped", pass_rate=None)],
            }
        ]
    }
    summary = calculate_project_trust_score(final)
    assert summary["overall_trust_score"] is None
    assert summary["overall_grade"] == GRADE_TRANSLATION_ONLY
