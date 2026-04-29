import pytest

from fidu.core.regex_safety import UnsafeRegexPattern, validate_pattern


def test_simple_pattern_passes():
    assert validate_pattern(r"^[A-Z]+$") == r"^[A-Z]+$"


def test_overlong_pattern_rejected():
    with pytest.raises(UnsafeRegexPattern):
        validate_pattern("a" * 2000)


@pytest.mark.parametrize("pattern", ["(a+)+", "(ab*)+", "(.*)*"])
def test_nested_quantifier_rejected(pattern):
    with pytest.raises(UnsafeRegexPattern):
        validate_pattern(pattern)


def test_invalid_pattern_rejected():
    with pytest.raises(UnsafeRegexPattern):
        validate_pattern("(unbalanced")


def test_non_string_rejected():
    with pytest.raises(UnsafeRegexPattern):
        validate_pattern(123)
