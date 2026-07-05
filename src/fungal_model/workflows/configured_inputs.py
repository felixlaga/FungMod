"""Input loading for generic configured-model workflows."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_, Quantity
from fungal_model.io.model_config import ConfigReference, ModelConfig
from fungal_model.io.parameters import (
    ParameterMergeError,
    merge_parameter_sets,
    parameter_set_from_config,
)
from fungal_model.io.product_maps import load_product_map
from fungal_model.io.registries import (
    GeometryLoaderRegistry,
    ProductMapRegistry,
    RegistryLookupError,
    SubstrateLoaderRegistry,
    ValidatorRegistry,
)
from fungal_model.io.yaml_loader import (
    enzyme_from_config,
    environment_from_config,
    load_enzyme,
    load_environment,
    load_fungus,
    load_geometry,
    load_parameter_set,
    load_substrate,
)
from fungal_model.workflows.configured_errors import raise_configured_model_execution_error


@dataclass(frozen=True)
class ConfiguredInputs:
    """Resolved input objects for a configured model run."""

    fungus: Any | None
    substrates: tuple[Any, ...]
    enzymes: tuple[Any, ...]
    environment: Any | None
    geometry: Any | None
    product_maps: Mapping[str, Any]
    parameters: ParameterSet
    validators: tuple[Any, ...]
    initial_state: Mapping[str, Quantity]
    t_span: tuple[Quantity, Quantity]
    t_eval: Quantity | None

    def maturity_entities(self) -> tuple[Any, ...]:
        entities: list[Any] = []
        for entity in (self.fungus, self.environment, self.geometry):
            if entity is not None:
                entities.append(entity)
        entities.extend(self.substrates)
        entities.extend(self.enzymes)
        return tuple(entities)

    def state_units(self) -> dict[str, str]:
        return {name: str(quantity.units) for name, quantity in self.initial_state.items()}


@dataclass(frozen=True)
class ConfiguredInputLoader:
    """Load config references, parameters, validators, state, and time grids."""

    substrate_registry: SubstrateLoaderRegistry | None = None
    geometry_registry: GeometryLoaderRegistry | None = None
    product_map_registry: ProductMapRegistry | None = None
    validator_registry: ValidatorRegistry | None = None

    def load(self, config: ModelConfig) -> ConfiguredInputs:
        try:
            substrates = tuple(
                _load_substrate_reference(reference, config, self.substrate_registry)
                for reference in config.entities.substrates
            )
            geometry = _load_geometry_reference(config.entities.geometry, config, self.geometry_registry)
            product_maps = {
                reference.id: _load_product_map_reference(reference, config, self.product_map_registry)
                for reference in config.entities.product_maps
            }
            parameter_sets = [
                *_entity_parameter_sets(
                    fungus=None,
                    substrates=substrates,
                    enzymes=(),
                ),
                *_configured_parameter_sets(config),
            ]
            fungus = _load_fungus_reference(config.entities.fungus, config)
            enzymes = tuple(_load_enzyme_reference(reference, config) for reference in config.entities.enzymes)
            environment = _load_environment_reference(config.entities.environment, config)
            parameter_sets.extend(_entity_parameter_sets(fungus=fungus, substrates=(), enzymes=enzymes))
            parameters = merge_parameter_sets(parameter_sets)
            validators = tuple(
                (self.validator_registry or ValidatorRegistry.default()).load(validator.to_dict())
                for validator in config.validators
            )
        except (ParameterMergeError, RegistryLookupError, ValueError) as exc:
            raise_configured_model_execution_error(
                config,
                stage="configured_input_loading",
                missing_capabilities=(),
                message=str(exc),
                details={"error_type": type(exc).__name__},
            )

        return ConfiguredInputs(
            fungus=fungus,
            substrates=substrates,
            enzymes=enzymes,
            environment=environment,
            geometry=geometry,
            product_maps=product_maps,
            parameters=parameters,
            validators=validators,
            initial_state=_initial_state(config),
            t_span=_time_span(config),
            t_eval=_time_eval(config),
        )


def _load_substrate_reference(
    reference: ConfigReference,
    config: ModelConfig,
    registry: SubstrateLoaderRegistry | None,
) -> Any:
    if reference.data is not None:
        return (registry or SubstrateLoaderRegistry.default()).load(
            _with_loader_key(reference.data, reference.loader, key="substrate_type")
        )
    return load_substrate(_resolve_path(reference, config), registry=registry)


def _load_geometry_reference(
    reference: ConfigReference | None,
    config: ModelConfig,
    registry: GeometryLoaderRegistry | None,
) -> Any | None:
    if reference is None:
        return None
    if reference.data is not None:
        return (registry or GeometryLoaderRegistry.default()).load(
            _with_loader_key(reference.data, reference.loader, key="geometry_type")
        )
    return load_geometry(_resolve_path(reference, config), registry=registry)


def _load_product_map_reference(
    reference: ConfigReference,
    config: ModelConfig,
    registry: ProductMapRegistry | None,
) -> Any:
    if reference.data is not None:
        return (registry or ProductMapRegistry.default()).load(
            _with_loader_key(reference.data, reference.loader, key="product_map_type")
        )
    return load_product_map(_resolve_path(reference, config), registry=registry)


def _load_environment_reference(reference: ConfigReference | None, config: ModelConfig) -> Any | None:
    if reference is None:
        return None
    if reference.data is not None:
        return environment_from_config(reference.data)
    _require_path_reference(reference, entity_name="environment")
    return load_environment(_resolve_path(reference, config))


def _load_fungus_reference(reference: ConfigReference | None, config: ModelConfig) -> Any | None:
    if reference is None:
        return None
    _require_path_reference(reference, entity_name="fungus")
    return load_fungus(_resolve_path(reference, config))


def _load_enzyme_reference(reference: ConfigReference, config: ModelConfig) -> Any:
    if reference.data is not None:
        return enzyme_from_config(reference.data)
    _require_path_reference(reference, entity_name="enzyme")
    return load_enzyme(_resolve_path(reference, config))


def _configured_parameter_sets(config: ModelConfig) -> list[ParameterSet]:
    parameter_sets: list[ParameterSet] = []
    for parameter_config in config.parameters:
        if parameter_config.path is not None:
            parameter_sets.append(load_parameter_set(_resolve_config_path(parameter_config.path, config)))
        if parameter_config.parameters:
            parameter_sets.append(parameter_set_from_config({"parameters": list(parameter_config.parameters)}))
    return parameter_sets


def _entity_parameter_sets(
    *,
    fungus: Any | None,
    substrates: tuple[Any, ...],
    enzymes: tuple[Any, ...],
) -> list[ParameterSet]:
    parameter_sets: list[ParameterSet] = []
    if fungus is not None and hasattr(fungus, "parameters"):
        parameter_sets.append(fungus.parameters)
    for substrate in substrates:
        if hasattr(substrate, "parameters"):
            parameter_sets.append(substrate.parameters)
    for enzyme in enzymes:
        if hasattr(enzyme, "catalytic_parameters"):
            parameter_sets.append(enzyme.catalytic_parameters)
        if hasattr(enzyme, "adsorption_parameters"):
            parameter_sets.append(enzyme.adsorption_parameters)
    return parameter_sets


def _initial_state(config: ModelConfig) -> dict[str, Quantity]:
    return {
        name: _quantity(value, field_name=f"initial_state.{name}")
        for name, value in config.initial_state.states.items()
    }


def _time_span(config: ModelConfig) -> tuple[Quantity, Quantity]:
    return (
        _quantity(config.time.start, field_name="time.start"),
        _quantity(config.time.stop, field_name="time.stop"),
    )


def _time_eval(config: ModelConfig) -> Quantity | None:
    if config.time.points is None:
        return None
    start, stop = _time_span(config)
    units = str(stop.units)
    values = np.linspace(
        float(start.to(units).magnitude),
        float(stop.to(units).magnitude),
        config.time.points,
    )
    return Q_(values, units)


def _quantity(data: Mapping[str, Any], *, field_name: str) -> Quantity:
    if "value" not in data or "units" not in data:
        raise ValueError(f"{field_name} requires value and units.")
    return Q_(data["value"], data["units"])


def _resolve_path(reference: ConfigReference, config: ModelConfig) -> Path:
    _require_path_reference(reference, entity_name=reference.id)
    assert reference.path is not None
    return _resolve_config_path(reference.path, config)


def _resolve_config_path(path: str, config: ModelConfig) -> Path:
    candidate = Path(path)
    if candidate.is_absolute() or candidate.exists():
        return candidate
    if config.path is not None:
        sibling = config.path.parent / candidate
        if sibling.exists():
            return sibling
    return candidate


def _require_path_reference(reference: ConfigReference, *, entity_name: str) -> None:
    if reference.path is None:
        raise ValueError(f"Configured {entity_name} loading currently requires a path reference.")


def _with_loader_key(
    data: Mapping[str, Any],
    loader: str | None,
    *,
    key: str,
) -> Mapping[str, Any]:
    if loader is None or key in data:
        return data
    copied = dict(data)
    copied[key] = loader
    return copied


__all__ = [
    "ConfiguredInputLoader",
    "ConfiguredInputs",
]
