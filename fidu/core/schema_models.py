"""Optional Pydantic schemas for early validation of rule and config YAML.

These models are used by ``core.config_validator.validate_with_schema`` when
Pydantic is available. If Pydantic is not installed, schema validation is
silently skipped so the kit remains usable in minimal environments.
"""

from typing import Any, Literal

try:
    from pydantic import BaseModel, ConfigDict, Field, model_validator

    PYDANTIC_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when pydantic missing
    PYDANTIC_AVAILABLE = False


if PYDANTIC_AVAILABLE:

    class RuleModel(BaseModel):
        model_config = ConfigDict(extra="allow")

        name: str
        type: str
        column: str | None = None
        columns: list[str] | None = None
        dimension: str | None = None
        severity: Literal["critical", "warning", "info"] | None = None
        draft: bool = False
        review_status: str | None = None

    class SourceModel(BaseModel):
        model_config = ConfigDict(extra="allow")

        type: str
        format: str | None = None
        path: str | None = None
        table: str | None = None
        columns: list[str] | None = None

    class DatasetRulesModel(BaseModel):
        model_config = ConfigDict(extra="allow")

        dataset: str
        source: SourceModel
        rules: list[RuleModel] = Field(default_factory=list)

    class ExecutionModel(BaseModel):
        model_config = ConfigDict(extra="allow")

        mode: Literal["native", "tool"] = "native"
        engine: Literal["pandas", "sql", "spark"] | None = None
        tool: Literal["soda", "great_expectations", "deequ"] | None = None
        fail_on_critical: bool = False
        fail_on_critical_drift: bool = False

        @model_validator(mode="after")
        def _check_mode_dependencies(self):
            if self.mode == "native" and not self.engine:
                raise ValueError("execution.engine is required when mode='native'")
            if self.mode == "tool" and not self.tool:
                raise ValueError("execution.tool is required when mode='tool'")
            return self

    class DatasetEntryModel(BaseModel):
        model_config = ConfigDict(extra="allow")

        name: str
        rules_file: str

    class ConfigModel(BaseModel):
        model_config = ConfigDict(extra="allow")

        project: dict[str, Any]
        execution: ExecutionModel
        datasets: list[DatasetEntryModel]
        outputs: dict[str, Any] | None = None
        drift: dict[str, Any] | None = None
        tool_config: dict[str, Any] | None = None


def validate_dataset_rules_dict(data: dict) -> dict:
    if not PYDANTIC_AVAILABLE:
        return data
    return DatasetRulesModel.model_validate(data).model_dump(exclude_none=False)


def validate_config_dict(data: dict) -> dict:
    if not PYDANTIC_AVAILABLE:
        return data
    return ConfigModel.model_validate(data).model_dump(exclude_none=False)
