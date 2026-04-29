import json
from functools import lru_cache

from fidu.core.constants import INPUT_SCHEMA_VERSION
from fidu.core.paths import resolve_in_package
from fidu.core.schema_models import (
    PYDANTIC_AVAILABLE,
    validate_config_dict,
    validate_dataset_rules_dict,
)


def _validate_input_schema_version(payload: dict, kind: str) -> list[str]:
    """Check the top-level ``schema_version`` declared on a YAML payload.

    Returns a warning if missing (treated as the current major). Raises
    ``ValueError`` on a non-int or unknown major so future breaking changes
    surface as hard errors instead of silent misreads.
    """
    if "schema_version" not in payload:
        return [
            f"{kind} is missing top-level schema_version "
            f"(treating as v{INPUT_SCHEMA_VERSION}); add 'schema_version: "
            f"{INPUT_SCHEMA_VERSION}' to silence this warning"
        ]
    declared = payload["schema_version"]
    if not isinstance(declared, int) or isinstance(declared, bool):
        raise ValueError(
            f"{kind} schema_version must be an integer (got {declared!r})"
        )
    if declared != INPUT_SCHEMA_VERSION:
        raise ValueError(
            f"{kind} schema_version {declared} is not supported by this "
            f"version of the kit (expected {INPUT_SCHEMA_VERSION})"
        )
    return []


def load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as file:
        return json.load(file)


@lru_cache(maxsize=1)
def _engine_source_matrix() -> dict:
    return load_json(resolve_in_package("intelligence", "engine_source_matrix.json"))


@lru_cache(maxsize=1)
def _rule_support_matrix() -> dict:
    return load_json(resolve_in_package("intelligence", "rule_support_matrix.json"))


def reset_intelligence_cache():
    """Clear cached intelligence matrices. Useful for tests or hot-reload scenarios."""
    _engine_source_matrix.cache_clear()
    _rule_support_matrix.cache_clear()


def validate_engine_source(engine_name: str, source_type: str):
    matrix = _engine_source_matrix()
    if engine_name not in matrix:
        raise ValueError(f"Unsupported engine: {engine_name}")
    supported = matrix[engine_name]["supported_sources"]
    if source_type not in supported:
        raise ValueError(
            f"Invalid configuration: engine '{engine_name}' does not support source "
            f"type '{source_type}'. Supported sources: {supported}"
        )


def validate_rule_support(engine_name: str, rules: list):
    matrix = _rule_support_matrix()
    errors, warnings = [], []
    for rule in rules:
        rt = rule["type"]
        if rt not in matrix:
            errors.append(f"Unknown rule type: {rt}")
            continue
        status = matrix[rt].get(engine_name, "not_supported")
        if status == "not_supported":
            errors.append(
                f"Rule '{rule['name']}' uses rule type '{rt}', which is not "
                f"supported by engine '{engine_name}'."
            )
        elif status == "planned":
            warnings.append(
                f"Rule '{rule['name']}' uses rule type '{rt}', which is marked "
                f"as planned for engine '{engine_name}'."
            )
    if errors:
        raise ValueError("Config validation failed:\n" + "\n".join(errors))
    return warnings


def validate_dataset_config(engine_name: str, dataset_rules: dict):
    warnings = _validate_input_schema_version(
        dataset_rules,
        f"rules file for dataset '{dataset_rules.get('dataset', '<unknown>')}'",
    )
    validate_dataset_rules_dict(dataset_rules)
    validate_engine_source(engine_name, dataset_rules["source"]["type"])
    warnings.extend(validate_rule_support(engine_name, dataset_rules["rules"]))
    return warnings


def validate_rule_set_for_tool(rules: list):
    """Lightweight check used by tool mode: rule types must be known to the matrix."""
    matrix = _rule_support_matrix()
    errors = []
    for rule in rules:
        rt = rule.get("type")
        if rt not in matrix:
            errors.append(f"Unknown rule type: {rt}")
    if errors:
        raise ValueError("Tool-mode rule validation failed:\n" + "\n".join(errors))


def validate_dataset_for_tool(dataset_rules: dict) -> list[str]:
    """Tool-mode counterpart to ``validate_dataset_config`` for input schema_version
    + rule-type sanity. Engines aren't involved in tool mode.
    """
    warnings = _validate_input_schema_version(
        dataset_rules,
        f"rules file for dataset '{dataset_rules.get('dataset', '<unknown>')}'",
    )
    validate_rule_set_for_tool(dataset_rules.get("rules", []))
    return warnings


def validate_top_level_config(config: dict) -> list[str]:
    """Validate the top-level ``dq_config`` dict.

    Runs the optional Pydantic schema check and the input ``schema_version``
    contract. Returns a list of non-fatal warnings (e.g. missing
    ``schema_version`` field) so callers can surface them to operators.
    """
    warnings = _validate_input_schema_version(config, "top-level config")
    validate_config_dict(config)
    return warnings


__all__ = [
    "PYDANTIC_AVAILABLE",
    "validate_dataset_config",
    "validate_dataset_for_tool",
    "validate_engine_source",
    "validate_rule_support",
    "validate_rule_set_for_tool",
    "validate_top_level_config",
]
