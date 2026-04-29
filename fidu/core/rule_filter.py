"""Shared rule-filtering logic used by native engines and every tool adapter."""


def is_executable(rule: dict) -> bool:
    """A rule is executable when it is not a draft or it has been approved."""
    return not rule.get("draft", False) or rule.get("review_status") == "approved"


def filter_executable_rules(rules: list) -> list:
    return [rule for rule in rules if is_executable(rule)]
