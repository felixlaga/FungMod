"""Base substrate interfaces.

Substrate objects describe material identity, physical state, degradation
products, and provenance-backed physical parameters. They do not imply that a
kinetic model exists. Kinetic laws should consume substrate metadata only after
the relevant stage has been validated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

from fungal_model.chemistry.thermodynamics import GibbsFreeEnergyEstimate
from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_, UnitError

CompletenessLevel = Literal["experimental", "partial", "placeholder"]
PhysicalState = Literal["dissolved", "solid_polymer", "solid_biomass", "mixed_solid", "unknown"]
DegradationModelPreference = Literal[
    "homogeneous_dissolved",
    "heterogeneous_surface",
    "reaction_diffusion",
    "unknown",
]


@dataclass(frozen=True)
class SubstrateParameterSpec:
    """Expected units and meaning for one substrate physical parameter."""

    symbol: str
    name: str
    units: str
    notes: str


def make_unknown_substrate_parameter(
    spec: SubstrateParameterSpec,
    *,
    substrate_name: str,
    stage_notes: str,
) -> Parameter:
    """Create a provenance-backed explicitly unknown substrate parameter."""

    return Parameter(
        name=spec.name,
        symbol=spec.symbol,
        value=None,
        units=spec.units,
        uncertainty=None,
        source=(
            f"Not provided; explicitly marked unknown by {substrate_name} "
            "substrate construction."
        ),
        confidence_level="unknown",
        notes=f"{stage_notes} {spec.notes}".strip(),
        measurement_method=None,
    )


def make_substrate_parameter_set(
    specs: Iterable[SubstrateParameterSpec],
    *,
    substrate_name: str,
    stage_notes: str,
    overrides: Iterable[Parameter] | None = None,
) -> ParameterSet:
    """Create a parameter set with unknown defaults and unit-checked overrides."""

    spec_by_symbol = {spec.symbol: spec for spec in specs}
    parameters = {
        symbol: make_unknown_substrate_parameter(
            spec,
            substrate_name=substrate_name,
            stage_notes=stage_notes,
        )
        for symbol, spec in spec_by_symbol.items()
    }
    for override in overrides or ():
        try:
            spec = spec_by_symbol[override.symbol]
        except KeyError as exc:
            raise KeyError(
                f"{override.symbol!r} is not a recognized {substrate_name} parameter symbol."
            ) from exc
        try:
            Q_(1, override.units).to(spec.units)
        except Exception as exc:
            raise UnitError(
                f"{substrate_name} parameter {override.symbol} must use units "
                f"compatible with {spec.units}."
            ) from exc
        parameters[override.symbol] = override
    return ParameterSet(parameters.values())


def validate_substrate_parameter_units(
    parameters: ParameterSet,
    specs: Iterable[SubstrateParameterSpec],
    *,
    substrate_name: str,
) -> None:
    """Validate that a substrate parameter set contains expected unit dimensions."""

    for spec in specs:
        parameter = parameters.get(spec.symbol)
        try:
            Q_(1, parameter.units).to(spec.units)
        except Exception as exc:
            raise UnitError(
                f"{substrate_name} parameter {spec.symbol} must use units "
                f"compatible with {spec.units}."
            ) from exc


@dataclass(frozen=True)
class DegradationProduct:
    """A named degradation product or product class.

    ``assimilable`` is intentionally nullable because product uptake and
    metabolism should not be guessed from product identity alone.
    """

    name: str
    formula: str | None = None
    assimilable: bool | None = None
    notes: str = ""
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "formula": self.formula,
            "assimilable": self.assimilable,
            "notes": self.notes,
            "source": self.source,
        }


@dataclass(frozen=True)
class Substrate:
    """Material description shared by specific substrate modules."""

    name: str
    chemical_class: str
    physical_state: PhysicalState
    bond_types: tuple[str, ...]
    accessible_bonds: tuple[str, ...]
    required_enzyme_classes: tuple[str, ...]
    degradation_products: tuple[DegradationProduct, ...]
    parameters: ParameterSet
    assumptions: tuple[Assumption, ...] = field(default_factory=tuple)
    completeness: CompletenessLevel = "placeholder"
    default_degradation_model: DegradationModelPreference = "unknown"
    water_activity_dependence: str = "unknown"
    thermodynamic_data: tuple[GibbsFreeEnergyEstimate, ...] = field(default_factory=tuple)
    notes: str = ""
    references: tuple[str, ...] = field(default_factory=tuple)

    def validate(
        self,
        *,
        allow_unsourced_for_testing: bool = False,
        require_parameter_values: bool = False,
    ) -> None:
        """Validate parameter provenance and, optionally, require values."""

        self.parameters.validate(
            allow_unsourced_for_testing=allow_unsourced_for_testing,
            require_values=require_parameter_values,
        )
        for estimate in self.thermodynamic_data:
            estimate.validate(
                allow_unsourced_for_testing=allow_unsourced_for_testing,
                require_value=require_parameter_values,
            )

    def parameter(self, symbol: str) -> Parameter:
        """Return a named physical parameter for this substrate."""

        return self.parameters.get(symbol)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "chemical_class": self.chemical_class,
            "physical_state": self.physical_state,
            "bond_types": list(self.bond_types),
            "accessible_bonds": list(self.accessible_bonds),
            "required_enzyme_classes": list(self.required_enzyme_classes),
            "degradation_products": [
                product.to_dict() for product in self.degradation_products
            ],
            "parameters": self.parameters.to_dict(),
            "assumptions": [assumption.to_dict() for assumption in self.assumptions],
            "completeness": self.completeness,
            "default_degradation_model": self.default_degradation_model,
            "water_activity_dependence": self.water_activity_dependence,
            "thermodynamic_data": [
                estimate.to_dict() for estimate in self.thermodynamic_data
            ],
            "notes": self.notes,
            "references": list(self.references),
        }


__all__ = [
    "CompletenessLevel",
    "DegradationModelPreference",
    "DegradationProduct",
    "PhysicalState",
    "Substrate",
    "SubstrateParameterSpec",
    "make_substrate_parameter_set",
    "make_unknown_substrate_parameter",
    "validate_substrate_parameter_units",
]
