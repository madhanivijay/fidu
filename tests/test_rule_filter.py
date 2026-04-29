from fidu.core.rule_filter import filter_executable_rules, is_executable


def test_non_draft_rule_is_executable():
    assert is_executable({"name": "r", "type": "not_null"})


def test_draft_rule_is_not_executable():
    assert not is_executable({"name": "r", "type": "not_null", "draft": True})


def test_approved_draft_rule_is_executable():
    assert is_executable(
        {"name": "r", "type": "not_null", "draft": True, "review_status": "approved"}
    )


def test_filter_executable_rules_strips_unapproved_drafts():
    rules = [
        {"name": "a", "type": "not_null"},
        {"name": "b", "type": "not_null", "draft": True},
        {
            "name": "c",
            "type": "not_null",
            "draft": True,
            "review_status": "approved",
        },
    ]
    kept = [r["name"] for r in filter_executable_rules(rules)]
    assert kept == ["a", "c"]
