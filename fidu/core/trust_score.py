"""Trust scoring with explicit handling of skipped rules and grade reasons."""

from fidu.core.constants import (
    DEFAULT_SEVERITY,
    GRADE_THRESHOLD_NEEDS_REVIEW,
    GRADE_THRESHOLD_TRUSTED,
    GRADE_THRESHOLD_UNSTABLE,
    SEVERITY_WEIGHTS,
)

GRADE_TRUSTED = "TRUSTED"
GRADE_NEEDS_REVIEW = "NEEDS_REVIEW"
GRADE_UNSTABLE = "UNSTABLE"
GRADE_HIGH_RISK = "HIGH_RISK"
GRADE_NO_RULES = "NO_RULES"
GRADE_TRANSLATION_ONLY = "TRANSLATION_ONLY"


def calculate_rule_score(rule_result: dict) -> float:
    return round(rule_result.get("pass_rate", 0) * 100, 2)


def severity_weight(severity: str) -> float:
    return SEVERITY_WEIGHTS.get(severity, SEVERITY_WEIGHTS[DEFAULT_SEVERITY])


def assign_grade(score, critical_failures: int) -> tuple:
    """Returns (grade, grade_reason)."""
    if score is None:
        return GRADE_TRANSLATION_ONLY, "All rules were translated only; no execution occurred."
    if critical_failures > 0 and score < GRADE_THRESHOLD_TRUSTED:
        return (
            GRADE_HIGH_RISK,
            f"{critical_failures} critical rule failure(s) override score-based grade.",
        )
    if score >= GRADE_THRESHOLD_TRUSTED:
        return GRADE_TRUSTED, f"Score {score} >= {GRADE_THRESHOLD_TRUSTED} with no critical failures."
    if score >= GRADE_THRESHOLD_NEEDS_REVIEW:
        return GRADE_NEEDS_REVIEW, (
            f"Score {score} between {GRADE_THRESHOLD_NEEDS_REVIEW} and {GRADE_THRESHOLD_TRUSTED}."
        )
    if score >= GRADE_THRESHOLD_UNSTABLE:
        return GRADE_UNSTABLE, (
            f"Score {score} between {GRADE_THRESHOLD_UNSTABLE} and {GRADE_THRESHOLD_NEEDS_REVIEW}."
        )
    return GRADE_HIGH_RISK, f"Score {score} below {GRADE_THRESHOLD_UNSTABLE}."


def _scoreable_rules(rules: list) -> list:
    """Rules that contribute to numeric trust score."""
    return [
        rule for rule in rules
        if rule.get("status") in ("passed", "failed")
        and not rule.get("is_tool_metadata")
        and rule.get("pass_rate") is not None
    ]


def calculate_dimension_scores(rule_results: list) -> dict:
    buckets = {}
    for rule in _scoreable_rules(rule_results):
        dim = rule.get("dimension", "validity")
        score = calculate_rule_score(rule)
        weight = severity_weight(rule.get("severity", "warning"))
        bucket = buckets.setdefault(
            dim,
            {"weighted_score_sum": 0, "total_weight": 0, "failed_rules": 0, "total_rules": 0},
        )
        bucket["weighted_score_sum"] += score * weight
        bucket["total_weight"] += weight
        bucket["total_rules"] += 1
        if rule["status"] == "failed":
            bucket["failed_rules"] += 1
    return {
        dim: {
            "score": round(v["weighted_score_sum"] / v["total_weight"], 2)
            if v["total_weight"] else 0,
            "failed_rules": v["failed_rules"],
            "total_rules": v["total_rules"],
        }
        for dim, v in buckets.items()
    }


def calculate_dataset_trust_score(dataset_result: dict) -> dict:
    raw_rules = dataset_result.get("results", [])
    if not raw_rules:
        grade, reason = GRADE_NO_RULES, "Dataset has no rules."
        return {
            "dataset": dataset_result["dataset"],
            "trust_score": None,
            "grade": grade,
            "grade_reason": reason,
            "critical_failures": 0,
            "warning_failures": 0,
            "skipped_rules": 0,
            "errored_rules": 0,
            "dimension_scores": {},
        }

    skipped = sum(1 for r in raw_rules if r.get("status") == "skipped")
    errored = sum(1 for r in raw_rules if r.get("status") == "error")
    rules = _scoreable_rules(raw_rules)

    if not rules:
        if skipped > 0 and errored == 0:
            grade, reason = (
                GRADE_TRANSLATION_ONLY,
                f"All {skipped} rule(s) were translated only; no execution occurred.",
            )
        elif errored > 0:
            grade, reason = (
                GRADE_HIGH_RISK,
                f"{errored} rule(s) errored; no scoreable results.",
            )
        else:
            grade, reason = GRADE_NO_RULES, "No scoreable rules in dataset."
        return {
            "dataset": dataset_result["dataset"],
            "trust_score": None,
            "grade": grade,
            "grade_reason": reason,
            "critical_failures": 0,
            "warning_failures": 0,
            "skipped_rules": skipped,
            "errored_rules": errored,
            "dimension_scores": {},
        }

    weighted_sum, total_weight = 0, 0
    critical_failures, warning_failures = 0, 0
    for rule in rules:
        score = calculate_rule_score(rule)
        weight = severity_weight(rule.get("severity", "warning"))
        weighted_sum += score * weight
        total_weight += weight
        if rule["status"] == "failed" and rule.get("severity") == "critical":
            critical_failures += 1
        if rule["status"] == "failed" and rule.get("severity") == "warning":
            warning_failures += 1
    trust_score = round(weighted_sum / total_weight, 2) if total_weight else 0
    grade, reason = assign_grade(trust_score, critical_failures)
    return {
        "dataset": dataset_result["dataset"],
        "trust_score": trust_score,
        "grade": grade,
        "grade_reason": reason,
        "critical_failures": critical_failures,
        "warning_failures": warning_failures,
        "skipped_rules": skipped,
        "errored_rules": errored,
        "dimension_scores": calculate_dimension_scores(raw_rules),
    }


def calculate_project_trust_score(all_results: dict) -> dict:
    scores = [calculate_dataset_trust_score(ds) for ds in all_results["datasets"]]
    numeric = [d["trust_score"] for d in scores if d["trust_score"] is not None]
    overall = round(sum(numeric) / len(numeric), 2) if numeric else None
    criticals = sum(d["critical_failures"] for d in scores)
    if overall is None:
        if any(d["grade"] == GRADE_TRANSLATION_ONLY for d in scores):
            grade, reason = (
                GRADE_TRANSLATION_ONLY,
                "No datasets produced executable rule results.",
            )
        else:
            grade, reason = GRADE_NO_RULES, "No datasets had scoreable rules."
    else:
        grade, reason = assign_grade(overall, criticals)
    return {
        "overall_trust_score": overall,
        "overall_grade": grade,
        "grade_reason": reason,
        "dataset_scores": scores,
    }
