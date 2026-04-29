import re

MAX_PATTERN_LENGTH = 1024
_NESTED_QUANTIFIER_RE = re.compile(r"\([^)]*[+*][^)]*\)\s*[+*]")


class UnsafeRegexPattern(ValueError):
    pass


def validate_pattern(pattern: str) -> str:
    if not isinstance(pattern, str):
        raise UnsafeRegexPattern(f"Regex pattern must be a string, got {type(pattern).__name__}.")
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise UnsafeRegexPattern(
            f"Regex pattern exceeds {MAX_PATTERN_LENGTH} characters; reject to avoid ReDoS."
        )
    if _NESTED_QUANTIFIER_RE.search(pattern):
        raise UnsafeRegexPattern(
            f"Regex pattern '{pattern}' contains nested quantifiers that can cause "
            "catastrophic backtracking; rewrite without (...+)+ or (...*)*."
        )
    try:
        re.compile(pattern)
    except re.error as exc:
        raise UnsafeRegexPattern(f"Invalid regex pattern '{pattern}': {exc}") from exc
    return pattern
