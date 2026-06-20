"""Factory-based process construction for foundation configs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from fungal_model.processes.base import Process
from fungal_model.processes.homogeneous import (
    FirstOrderDecayProcess,
    HomogeneousMichaelisMentenProcess,
    MassActionProcess,
)
from fungal_model.processes.rate_modifiers import (
    RateModifierProcess,
    product_inhibition_modifier_from_config,
)
from fungal_model.processes.surface import (
    AccessibleSitePool,
    AccessibleSurfaceAreaModel,
    LangmuirAdsorptionModel,
    ProductReleaseMap,
    SurfaceCatalysisModel,
    SurfaceCatalysisProcess,
)


@dataclass(frozen=True)
class BuildDecision:
    """Structured factory decision for one process config."""

    can_build: bool
    process_type: str
    factory: str
    reasons: tuple[str, ...] = ()
    missing_fields: tuple[str, ...] = ()
    missing_parameters: tuple[str, ...] = ()
    incompatible_entities: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "can_build": self.can_build,
            "process_type": self.process_type,
            "factory": self.factory,
            "reasons": list(self.reasons),
            "missing_fields": list(self.missing_fields),
            "missing_parameters": list(self.missing_parameters),
            "incompatible_entities": list(self.incompatible_entities),
        }


@dataclass(frozen=True)
class ProcessBuildContext:
    """Context available to process factories."""

    state_units: Mapping[str, str]
    product_maps: Mapping[str, ProductReleaseMap] = field(default_factory=dict)
    assumptions: tuple[Any, ...] = ()
    source: str = "Generic process factory."

    def __post_init__(self) -> None:
        object.__setattr__(self, "product_maps", dict(self.product_maps))
        object.__setattr__(self, "state_units", dict(self.state_units))


class ProcessFactory(Protocol):
    """Protocol implemented by process factories."""

    @property
    def process_type(self) -> str:
        ...

    def can_build(self, context: ProcessBuildContext, process_config: Any) -> BuildDecision:
        ...

    def build(self, context: ProcessBuildContext, process_config: Any) -> Process:
        ...


@dataclass(frozen=True)
class FirstOrderFactory:
    """Build generic first-order homogeneous benchmark processes."""

    process_type: str = "first_order"

    def can_build(self, context: ProcessBuildContext, process_config: Any) -> BuildDecision:
        missing = _missing_config_fields(process_config, ("id", "states", "parameters"))
        states = _mapping(getattr(process_config, "states", {}))
        parameters = _mapping(getattr(process_config, "parameters", {}))
        missing += _missing_mapping_fields(states, ("source",), prefix="states")
        missing += _missing_mapping_fields(parameters, ("rate_constant",), prefix="parameters")
        missing += tuple(
            f"state_units.{state}"
            for state in (states.get("source"), states.get("product"))
            if state is not None and state not in context.state_units
        )
        return _decision(self, missing_fields=missing)

    def build(self, context: ProcessBuildContext, process_config: Any) -> Process:
        _require_buildable(self.can_build(context, process_config))
        states = _mapping(process_config.states)
        parameters = _mapping(process_config.parameters)
        source_state = str(states["source"])
        product_state = None if states.get("product") is None else str(states["product"])
        process = FirstOrderDecayProcess(
            name=process_config.id,
            substrate_state=source_state,
            product_state=product_state,
            rate_constant_symbol=str(parameters["rate_constant"]),
            state_units=context.state_units[source_state],
            source=context.source,
            notes="Built from generic first-order process config.",
        )
        return _apply_rate_modifiers(context, process_config, process)


@dataclass(frozen=True)
class MassActionFactory:
    """Build generic mass-action homogeneous benchmark processes."""

    process_type: str = "mass_action"

    def can_build(self, context: ProcessBuildContext, process_config: Any) -> BuildDecision:
        missing = _missing_config_fields(process_config, ("id", "states", "parameters"))
        states = _mapping(getattr(process_config, "states", {}))
        parameters = _mapping(getattr(process_config, "parameters", {}))
        missing += _missing_mapping_fields(states, ("reactants", "products"), prefix="states")
        missing += _missing_mapping_fields(
            parameters,
            ("rate_constant", "rate_constant_units", "rate_units"),
            prefix="parameters",
        )
        species = set(_mapping(states.get("reactants", {}))) | set(_mapping(states.get("products", {})))
        missing += tuple(
            f"state_units.{state}"
            for state in sorted(species)
            if state not in context.state_units
        )
        return _decision(self, missing_fields=missing)

    def build(self, context: ProcessBuildContext, process_config: Any) -> Process:
        _require_buildable(self.can_build(context, process_config))
        states = _mapping(process_config.states)
        parameters = _mapping(process_config.parameters)
        species = set(states["reactants"]) | set(states["products"])
        process = MassActionProcess(
            name=process_config.id,
            reactants={str(name): float(value) for name, value in states["reactants"].items()},
            products={str(name): float(value) for name, value in states["products"].items()},
            state_units={str(name): context.state_units[str(name)] for name in species},
            rate_constant_symbol=str(parameters["rate_constant"]),
            rate_constant_units=str(parameters["rate_constant_units"]),
            rate_units=str(parameters["rate_units"]),
            source=context.source,
            notes="Built from generic mass-action process config.",
        )
        return _apply_rate_modifiers(context, process_config, process)


@dataclass(frozen=True)
class HomogeneousMichaelisMentenFactory:
    """Build generic homogeneous Michaelis-Menten benchmark processes."""

    process_type: str = "homogeneous_michaelis_menten"

    def can_build(self, context: ProcessBuildContext, process_config: Any) -> BuildDecision:
        missing = _missing_config_fields(process_config, ("id", "states", "parameters"))
        states = _mapping(getattr(process_config, "states", {}))
        parameters = _mapping(getattr(process_config, "parameters", {}))
        missing += _missing_mapping_fields(states, ("substrate",), prefix="states")
        missing += _missing_mapping_fields(parameters, ("km", "rate_units"), prefix="parameters")
        if "vmax" not in parameters and ("kcat" not in parameters or "enzyme" not in states):
            missing += ("parameters.vmax_or_kcat_with_states.enzyme",)
        missing += tuple(
            f"state_units.{state}"
            for state in (states.get("substrate"), states.get("product"), states.get("enzyme"))
            if state is not None and state not in context.state_units
        )
        product_map_id = getattr(process_config, "product_map", None)
        if isinstance(product_map_id, str):
            if product_map_id not in context.product_maps:
                missing += (f"product_maps.{product_map_id}",)
            else:
                missing += tuple(
                    f"state_units.{state}"
                    for state in sorted(context.product_maps[product_map_id].species)
                    if state not in context.state_units
                )
        return _decision(self, missing_fields=missing)

    def build(self, context: ProcessBuildContext, process_config: Any) -> Process:
        _require_buildable(self.can_build(context, process_config))
        states = _mapping(process_config.states)
        parameters = _mapping(process_config.parameters)
        substrate_state = str(states["substrate"])
        enzyme_state = None if states.get("enzyme") is None else str(states["enzyme"])
        product_map_id = getattr(process_config, "product_map", None)
        product_coefficients = (
            context.product_maps[product_map_id].products
            if isinstance(product_map_id, str) and product_map_id in context.product_maps
            else None
        )
        process = HomogeneousMichaelisMentenProcess(
            name=process_config.id,
            substrate_state=substrate_state,
            product_state=None if states.get("product") is None else str(states["product"]),
            product_coefficients=product_coefficients,
            substrate_units=context.state_units[substrate_state],
            enzyme_state=enzyme_state,
            enzyme_units=None if enzyme_state is None else context.state_units[enzyme_state],
            km_symbol=str(parameters["km"]),
            vmax_symbol=None if parameters.get("vmax") is None else str(parameters["vmax"]),
            kcat_symbol=None if parameters.get("kcat") is None else str(parameters["kcat"]),
            rate_units=str(parameters["rate_units"]),
            source=context.source,
            notes="Built from generic homogeneous Michaelis-Menten process config.",
        )
        return _apply_rate_modifiers(context, process_config, process)


@dataclass(frozen=True)
class SurfaceCatalysisFactory:
    """Build generic surface-catalysis benchmark processes."""

    process_type: str = "surface_catalysis"

    def can_build(self, context: ProcessBuildContext, process_config: Any) -> BuildDecision:
        missing = _missing_config_fields(process_config, ("id", "states", "parameters", "product_map"))
        states = _mapping(getattr(process_config, "states", {}))
        parameters = _mapping(getattr(process_config, "parameters", {}))
        missing += _missing_mapping_fields(states, ("substrate", "catalyst"), prefix="states")
        missing += _missing_mapping_fields(
            parameters,
            ("adsorption_constant", "surface_rate_constant", "accessible_surface_area"),
            prefix="parameters",
        )
        missing += tuple(
            f"state_units.{state}"
            for state in (states.get("substrate"), states.get("catalyst"), states.get("product"))
            if state is not None and state not in context.state_units
        )
        product_map_id = getattr(process_config, "product_map", None)
        if isinstance(product_map_id, str) and product_map_id not in context.product_maps:
            missing += (f"product_maps.{product_map_id}",)
        elif product_map_id is None:
            missing += ("product_map",)
        return _decision(self, missing_fields=missing)

    def build(self, context: ProcessBuildContext, process_config: Any) -> Process:
        _require_buildable(self.can_build(context, process_config))
        states = _mapping(process_config.states)
        parameters = _mapping(process_config.parameters)
        substrate_state = str(states["substrate"])
        catalyst_state = str(states["catalyst"])
        product_map = context.product_maps[str(process_config.product_map)]
        substrate_units = context.state_units[substrate_state]
        process = SurfaceCatalysisProcess(
            name=process_config.id,
            substrate_state=substrate_state,
            enzyme_state=catalyst_state,
            substrate_units=substrate_units,
            enzyme_units=context.state_units[catalyst_state],
            accessible_site_pool=AccessibleSitePool(
                name=str(states.get("accessible_site_pool", "configured accessible site pool")),
                bond_type=str(states.get("bond_type", "configured_bond")),
            ),
            accessible_surface_model=AccessibleSurfaceAreaModel.from_parameter(
                name="configured accessible surface",
                parameter_symbol=str(parameters["accessible_surface_area"]),
            ),
            adsorption_model=LangmuirAdsorptionModel(
                adsorption_symbol=str(parameters["adsorption_constant"]),
                enzyme_units=context.state_units[catalyst_state],
                source=context.source,
            ),
            catalytic_model=SurfaceCatalysisModel(
                surface_rate_symbol=str(parameters["surface_rate_constant"]),
                rate_units=str(parameters.get("rate_units", f"{substrate_units} / second")),
                source=context.source,
            ),
            product_release_map=product_map,
            state_units=context.state_units,
            source=context.source,
            notes="Built from generic surface-catalysis process config.",
        )
        return _apply_rate_modifiers(context, process_config, process)


def default_foundation_factories() -> tuple[ProcessFactory, ...]:
    return (
        FirstOrderFactory(),
        MassActionFactory(),
        HomogeneousMichaelisMentenFactory(),
        SurfaceCatalysisFactory(),
    )


def _decision(
    factory: Any,
    *,
    missing_fields: Sequence[str] = (),
    missing_parameters: Sequence[str] = (),
    incompatible_entities: Sequence[str] = (),
) -> BuildDecision:
    reasons: list[str] = []
    if missing_fields:
        reasons.append("missing_fields")
    if missing_parameters:
        reasons.append("missing_parameters")
    if incompatible_entities:
        reasons.append("incompatible_entities")
    return BuildDecision(
        can_build=not reasons,
        process_type=factory.process_type,
        factory=type(factory).__name__,
        reasons=tuple(reasons),
        missing_fields=tuple(missing_fields),
        missing_parameters=tuple(missing_parameters),
        incompatible_entities=tuple(incompatible_entities),
    )


def _require_buildable(decision: BuildDecision) -> None:
    if not decision.can_build:
        raise ValueError(f"Process factory cannot build config: {decision.to_dict()}")


def _apply_rate_modifiers(
    context: ProcessBuildContext,
    process_config: Any,
    process: Process,
) -> Process:
    modifiers = tuple(
        _build_rate_modifier(context, modifier_config)
        for modifier_config in getattr(process_config, "modifiers", ()) or ()
    )
    if not modifiers:
        return process
    return RateModifierProcess(
        base_process=process,
        rate_modifiers=modifiers,
        notes=f"{process.notes} Explicit generic rate modifiers configured.".strip(),
    )


def _build_rate_modifier(context: ProcessBuildContext, modifier_config: Any) -> Any:
    mapping = _mapping(modifier_config)
    modifier_type = str(mapping.get("type") or mapping.get("modifier_type") or "").strip()
    if modifier_type == "product_inhibition":
        return product_inhibition_modifier_from_config(mapping, state_units=context.state_units)
    raise ValueError(f"Unsupported rate modifier type: {modifier_type!r}.")


def _missing_config_fields(process_config: Any, fields: Sequence[str]) -> tuple[str, ...]:
    return tuple(field for field in fields if not _has_field(process_config, field))


def _missing_mapping_fields(
    mapping: Mapping[str, Any],
    fields: Sequence[str],
    *,
    prefix: str,
) -> tuple[str, ...]:
    return tuple(f"{prefix}.{field}" for field in fields if field not in mapping)


def _has_field(process_config: Any, field: str) -> bool:
    if not hasattr(process_config, field):
        return False
    value = getattr(process_config, field)
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


def _mapping(value: Any) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError("Expected a mapping.")
    return value


__all__ = [
    "BuildDecision",
    "FirstOrderFactory",
    "HomogeneousMichaelisMentenFactory",
    "MassActionFactory",
    "ProcessBuildContext",
    "ProcessFactory",
    "SurfaceCatalysisFactory",
    "default_foundation_factories",
]
