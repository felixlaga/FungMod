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
class ConfigReference:
    """Reference to a config-backed object."""

    id: str
    path: str | None = None
    loader: str | None = None
    data: Mapping[str, Any] | None = None
    role: str | None = None

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any],
        *,
        default_id: str | None = None,
    ) -> "ConfigReference":
        identifier = str(data.get("id") or default_id or "").strip()
        if not identifier:
            raise ModelConfigError("Config reference requires an id.")
        path = data.get("path")
        loader = data.get("loader")
        role = data.get("role")
        inline = data.get("data")
        return cls(
            id=identifier,
            path=None if path is None else str(path),
            loader=None if loader is None else str(loader),
            data=None if inline is None else deepcopy(inline),
            role=None if role is None else str(role),
        )

    def validate(self) -> ModelConfigValidationResult:
        if self.path is None and self.data is None:
            return ModelConfigValidationResult(
                passed=False,
                message="Config reference requires either path or data.",
                invalid_fields=(self.id,),
            )
        return ModelConfigValidationResult(
            passed=True,
            message="Config reference is valid.",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "loader": self.loader,
            "data": deepcopy(self.data),
            "role": self.role,
        }


@dataclass(frozen=True)
class EntityConfigRefs:
    """Config references for model entities."""

    fungus: ConfigReference | None = None
    substrates: tuple[ConfigReference, ...] = ()
    enzymes: tuple[ConfigReference, ...] = ()
    environment: ConfigReference | None = None
    geometry: ConfigReference | None = None
    product_maps: tuple[ConfigReference, ...] = ()
    extras: Mapping[str, Any] | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "EntityConfigRefs":
        known = {"fungus", "substrates", "enzymes", "environment", "geometry", "product_maps"}
        return cls(
            fungus=_optional_reference(data.get("fungus"), default_id="fungus"),
            substrates=_reference_tuple(data.get("substrates", ())),
            enzymes=_reference_tuple(data.get("enzymes", ())),
            environment=_optional_reference(data.get("environment"), default_id="environment"),
            geometry=_optional_reference(data.get("geometry"), default_id="geometry"),
            product_maps=_reference_tuple(data.get("product_maps", ())),
            extras={key: deepcopy(value) for key, value in data.items() if key not in known},
        )

    def validate(self) -> ModelConfigValidationResult:
        invalid = [
            reference.id
            for reference in self.references
            if not reference.validate().passed
        ]
        if invalid:
            return ModelConfigValidationResult(
                passed=False,
                message="At least one entity reference is invalid.",
                invalid_fields=tuple(invalid),
            )
        return ModelConfigValidationResult(
            passed=True,
            message="Entity config references are valid.",
        )

    @property
    def references(self) -> tuple[ConfigReference, ...]:
        references: list[ConfigReference] = []
        for reference in (self.fungus, self.environment, self.geometry):
            if reference is not None:
                references.append(reference)
        references.extend(self.substrates)
        references.extend(self.enzymes)
        references.extend(self.product_maps)
        return tuple(references)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fungus": None if self.fungus is None else self.fungus.to_dict(),
            "substrates": [reference.to_dict() for reference in self.substrates],
            "enzymes": [reference.to_dict() for reference in self.enzymes],
            "environment": None if self.environment is None else self.environment.to_dict(),
            "geometry": None if self.geometry is None else self.geometry.to_dict(),
            "product_maps": [reference.to_dict() for reference in self.product_maps],
            "extras": deepcopy(self.extras or {}),
        }


@dataclass(frozen=True)
class ParameterSetConfig:
    """Config reference or inline parameters for one parameter set."""

    id: str
    path: str | None = None
    parameters: tuple[Mapping[str, Any], ...] = ()

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ParameterSetConfig":
        identifier = str(data.get("id") or data.get("name") or "").strip()
        if not identifier:
            raise ModelConfigError("Parameter set config requires an id or name.")
        path = data.get("path")
        parameters = tuple(deepcopy(item) for item in data.get("parameters", ()) or ())
        return cls(
            id=identifier,
            path=None if path is None else str(path),
            parameters=parameters,
        )

    def validate(self) -> ModelConfigValidationResult:
        if self.path is None and not self.parameters:
            return ModelConfigValidationResult(
                passed=False,
                message="Parameter set requires either path or inline parameters.",
                invalid_fields=(self.id,),
            )
        return ModelConfigValidationResult(
            passed=True,
            message="Parameter set config is valid.",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "parameters": deepcopy(list(self.parameters)),
        }


@dataclass(frozen=True)
class ProcessConfig:
    """Config for a process to be built by a later factory layer."""

    id: str
    process_type: str
    states: Mapping[str, Any]
    parameters: Mapping[str, Any]
    product_map: str | Mapping[str, Any] | None = None
    assumptions: tuple[str, ...] = ()
    raw: Mapping[str, Any] | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ProcessConfig":
        identifier = str(data.get("id") or data.get("name") or "").strip()
        process_type = str(data.get("process_type") or data.get("type") or "").strip()
        if not identifier:
            raise ModelConfigError("Process config requires an id or name.")
        if not process_type:
            raise ModelConfigError(f"Process config {identifier!r} requires process_type.")
        return cls(
            id=identifier,
            process_type=process_type,
            states=deepcopy(data.get("states", {})),
            parameters=deepcopy(data.get("parameters", {})),
            product_map=deepcopy(data.get("product_map")),
            assumptions=tuple(str(item) for item in data.get("assumptions", ()) or ()),
            raw=deepcopy(dict(data)),
        )

    def validate(self) -> ModelConfigValidationResult:
        invalid = []
        if not self.process_type:
            invalid.append(f"{self.id}.process_type")
        if not isinstance(self.states, Mapping):
            invalid.append(f"{self.id}.states")
        if not isinstance(self.parameters, Mapping):
            invalid.append(f"{self.id}.parameters")
        if invalid:
            return ModelConfigValidationResult(
                passed=False,
                message="Process config is invalid.",
                invalid_fields=tuple(invalid),
            )
        return ModelConfigValidationResult(passed=True, message="Process config is valid.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "process_type": self.process_type,
            "states": deepcopy(dict(self.states)),
            "parameters": deepcopy(dict(self.parameters)),
            "product_map": deepcopy(self.product_map),
            "assumptions": list(self.assumptions),
            "raw": deepcopy(dict(self.raw or {})),
        }


@dataclass(frozen=True)
class InitialStateConfig:
    """Initial state values with explicit units."""

    states: Mapping[str, Mapping[str, Any]]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "InitialStateConfig":
        states = data.get("states", data)
        if not isinstance(states, Mapping):
            raise ModelConfigError("Initial state must be a mapping.")
        return cls(states=deepcopy(states))

    def validate(self) -> ModelConfigValidationResult:
        invalid = [
            name
            for name, value in self.states.items()
            if not isinstance(value, Mapping) or "value" not in value or "units" not in value
        ]
        if invalid:
            return ModelConfigValidationResult(
                passed=False,
                message="Initial state entries require value and units.",
                invalid_fields=tuple(invalid),
            )
        return ModelConfigValidationResult(passed=True, message="Initial state config is valid.")

    def to_dict(self) -> dict[str, Any]:
        return {"states": deepcopy(dict(self.states))}


@dataclass(frozen=True)
class TimeConfig:
    """Time grid config."""

    start: Mapping[str, Any]
    stop: Mapping[str, Any]
    points: int | None = None
    step: Mapping[str, Any] | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "TimeConfig":
        return cls(
            start=deepcopy(data.get("start", {})),
            stop=deepcopy(data.get("stop", data.get("end", {}))),
            points=None if data.get("points") is None else int(data["points"]),
            step=None if data.get("step") is None else deepcopy(data["step"]),
        )

    def validate(self) -> ModelConfigValidationResult:
        invalid = []
        for name, value in (("start", self.start), ("stop", self.stop)):
            if not isinstance(value, Mapping) or "value" not in value or "units" not in value:
                invalid.append(name)
        if self.points is not None and self.points < 2:
            invalid.append("points")
        if invalid:
            return ModelConfigValidationResult(
                passed=False,
                message="Time config requires unit-bearing start and stop, and at least two points when provided.",
                invalid_fields=tuple(invalid),
            )
        return ModelConfigValidationResult(passed=True, message="Time config is valid.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": deepcopy(dict(self.start)),
            "stop": deepcopy(dict(self.stop)),
            "points": self.points,
            "step": deepcopy(self.step),
        }


@dataclass(frozen=True)
class ValidatorConfig:
    """Validator requested by a model config."""

    id: str
    validator_type: str
    settings: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ValidatorConfig":
        validator_type = str(data.get("validator_type") or data.get("type") or "").strip()
        identifier = str(data.get("id") or validator_type).strip()
        if not identifier or not validator_type:
            raise ModelConfigError("Validator config requires id/type and validator_type.")
        settings = {key: deepcopy(value) for key, value in data.items() if key not in {"id", "type", "validator_type"}}
        return cls(id=identifier, validator_type=validator_type, settings=settings)

    def validate(self) -> ModelConfigValidationResult:
        return ModelConfigValidationResult(passed=True, message="Validator config is valid.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "validator_type": self.validator_type,
            **deepcopy(dict(self.settings)),
        }


@dataclass(frozen=True)
class OutputConfig:
    """Output settings for a configured run."""

    directory: str | None = None
    save: tuple[str, ...] = ()
    plots: tuple[str, ...] = ()
    raw: Mapping[str, Any] | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "OutputConfig":
        directory = data.get("directory")
        return cls(
            directory=None if directory is None else str(directory),
            save=tuple(str(item) for item in data.get("save", ()) or ()),
            plots=tuple(str(item) for item in data.get("plots", ()) or ()),
            raw=deepcopy(dict(data)),
        )

    def validate(self) -> ModelConfigValidationResult:
        return ModelConfigValidationResult(passed=True, message="Output config is valid.")

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(dict(self.raw or {}))


@dataclass(frozen=True)
class ModelConfig:
    """Loaded generic model configuration."""

    kind: str
    name: str
    mode: str
    maturity: str
    entities: EntityConfigRefs
    parameters: tuple[ParameterSetConfig, ...]
    processes: tuple[ProcessConfig, ...]
    initial_state: InitialStateConfig
    time: TimeConfig
    validators: tuple[ValidatorConfig, ...]
    outputs: OutputConfig
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
            entities=EntityConfigRefs.from_mapping(data["entities"]),
            parameters=tuple(ParameterSetConfig.from_mapping(item) for item in _as_sequence(data["parameters"])),
            processes=tuple(ProcessConfig.from_mapping(item) for item in _as_sequence(data["processes"])),
            initial_state=InitialStateConfig.from_mapping(data["initial_state"]),
            time=TimeConfig.from_mapping(data["time"]),
            validators=tuple(ValidatorConfig.from_mapping(item) for item in _as_sequence(data["validators"])),
            outputs=OutputConfig.from_mapping(data["outputs"]),
            raw=deepcopy(dict(data)),
            path=None if path is None else Path(path),
        )

    def validate(self) -> ModelConfigValidationResult:
        result = validate_model_config_mapping(self.raw)
        if not result.passed:
            return result
        section_results = (
            self.entities.validate(),
            *(parameter_set.validate() for parameter_set in self.parameters),
            *(process.validate() for process in self.processes),
            self.initial_state.validate(),
            self.time.validate(),
            *(validator.validate() for validator in self.validators),
            self.outputs.validate(),
        )
        invalid = tuple(
            field
            for section_result in section_results
            for field in section_result.invalid_fields
        )
        if invalid:
            return ModelConfigValidationResult(
                passed=False,
                message="Model config section validation failed.",
                invalid_fields=invalid,
            )
        return ModelConfigValidationResult(
            passed=True,
            message="Model config satisfies the structured generic contract.",
        )

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
        for field in ("parameters", "processes", "validators"):
            if not isinstance(data[field], list):
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
    "ConfigReference",
    "EntityConfigRefs",
    "InitialStateConfig",
    "OutputConfig",
    "ParameterSetConfig",
    "ProcessConfig",
    "REQUIRED_MODEL_CONFIG_FIELDS",
    "TimeConfig",
    "VALID_MODEL_MATURITIES",
    "VALID_MODEL_MODES",
    "ValidatorConfig",
    "load_model_config",
    "validate_model_config_mapping",
]


def _optional_reference(value: Any, *, default_id: str) -> ConfigReference | None:
    if value is None:
        return None
    if isinstance(value, str):
        return ConfigReference(id=default_id, path=value)
    if isinstance(value, Mapping):
        return ConfigReference.from_mapping(value, default_id=default_id)
    raise ModelConfigError(f"Entity reference {default_id!r} must be a path or mapping.")


def _reference_tuple(value: Any) -> tuple[ConfigReference, ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        raise ModelConfigError("Entity reference group must be a sequence.")
    return tuple(
        ConfigReference(id=f"reference_{index}", path=item)
        if isinstance(item, str)
        else ConfigReference.from_mapping(item)
        for index, item in enumerate(value)
    )


def _as_sequence(value: Any) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        raise ModelConfigError("Model config section must be a sequence of mappings.")
    if not all(isinstance(item, Mapping) for item in value):
        raise ModelConfigError("Model config section entries must be mappings.")
    return tuple(value)
