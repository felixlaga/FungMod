"""Generic model-configuration loading primitives."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml


REQUIRED_MODEL_CONFIG_FIELDS = (
    "kind",
    "name",
    "mode",
    "maturity",
    "entities",
    "parameters",
    "processes",
    "initial_state",
    "time",
    "validators",
    "outputs",
)

VALID_MODEL_MODES = ("toy", "scientific", "strict")
VALID_MODEL_MATURITIES = ("toy", "synthetic", "framework_benchmark", "scientific")


class ModelConfigError(ValueError):
    """Raised when a generic model config cannot be loaded or validated."""


@dataclass(frozen=True)
class ModelConfigValidationResult:
    """Structured validation result for a generic model config."""

    passed: bool
    message: str
    missing_fields: tuple[str, ...] = ()
    invalid_fields: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "message": self.message,
            "missing_fields": list(self.missing_fields),
            "invalid_fields": list(self.invalid_fields),
        }


@dataclass(frozen=True)
class ModelConfig:
    """Loaded generic model configuration."""

    kind: str
    name: str
    mode: str
    maturity: str
    entities: Mapping[str, Any]
    parameters: Any
    processes: Any
    initial_state: Mapping[str, Any]
    time: Mapping[str, Any]
    validators: Any
    outputs: Mapping[str, Any]
    raw: Mapping[str, Any]
    path: Path | None = None

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any],
        *,
        path: str | Path | None = None,
    ) -> "ModelConfig":
        result = validate_model_config_mapping(data)
        if not result.passed:
            details = ", ".join(result.missing_fields + result.invalid_fields)
            raise ModelConfigError(f"Invalid model config: {details}")
        return cls(
            kind=str(data["kind"]),
            name=str(data["name"]),
            mode=str(data["mode"]),
            maturity=str(data["maturity"]),
            entities=deepcopy(data["entities"]),
            parameters=deepcopy(data["parameters"]),
            processes=deepcopy(data["processes"]),
            initial_state=deepcopy(data["initial_state"]),
            time=deepcopy(data["time"]),
            validators=deepcopy(data["validators"]),
            outputs=deepcopy(data["outputs"]),
            raw=deepcopy(dict(data)),
            path=None if path is None else Path(path),
        )

    def validate(self) -> ModelConfigValidationResult:
        return validate_model_config_mapping(self.raw)

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(dict(self.raw))


def load_model_config(path: str | Path) -> ModelConfig:
    """Load and validate a generic model config from YAML."""

    config_path = Path(path)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ModelConfigError(f"Model config {config_path} did not produce a mapping.")
    return ModelConfig.from_mapping(data, path=config_path)


def validate_model_config_mapping(data: Mapping[str, Any]) -> ModelConfigValidationResult:
    """Validate the top-level generic model-config contract."""

    missing = tuple(field for field in REQUIRED_MODEL_CONFIG_FIELDS if field not in data)
    invalid: list[str] = []
    if not missing:
        if data["kind"] != "model_config":
            invalid.append("kind")
        if str(data["name"]).strip() == "":
            invalid.append("name")
        if data["mode"] not in VALID_MODEL_MODES:
            invalid.append("mode")
        if data["maturity"] not in VALID_MODEL_MATURITIES:
            invalid.append("maturity")
        for field in ("entities", "initial_state", "time", "outputs"):
            if not isinstance(data[field], Mapping):
                invalid.append(field)

    passed = not missing and not invalid
    if passed:
        return ModelConfigValidationResult(
            passed=True,
            message="Model config satisfies the top-level generic contract.",
        )
    return ModelConfigValidationResult(
        passed=False,
        message="Model config violates the top-level generic contract.",
        missing_fields=missing,
        invalid_fields=tuple(invalid),
    )


__all__ = [
    "ModelConfig",
    "ModelConfigError",
    "ModelConfigValidationResult",
    "REQUIRED_MODEL_CONFIG_FIELDS",
    "VALID_MODEL_MATURITIES",
    "VALID_MODEL_MODES",
    "load_model_config",
    "validate_model_config_mapping",
]
