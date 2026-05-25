"""Base substrate interfaces.

Substrate objects describe material identity, physical state, degradation
products, and provenance-backed physical parameters. They do not imply that a
kinetic model exists. Kinetic laws should consume substrate metadata only after
the relevant stage has been validated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import ParameterSet

CompletenessLevel = Literal["experimental", "partial", "placeholder"]
PhysicalState = Literal["dissolved", "solid_polymer", "solid_biomass", "mixed_solid", "unknown"]
DegradationModelPreference = Literal[
    "homogeneous_dissolved",
    "heterogeneous_surface",
    "reaction_diffusion",
    "unknown",
]


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
            "notes": self.notes,
            "references": list(self.references),
        }


__all__ = [
    "CompletenessLevel",
    "DegradationModelPreference",
    "DegradationProduct",
    "PhysicalState",
    "Substrate",
]
