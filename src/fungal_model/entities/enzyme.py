"""Explicit enzyme entities for process compatibility matching."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.provenance import ProvenanceError, has_text


def enzyme_entity_assumption() -> Assumption:
    return Assumption(
        name="explicit enzyme entity",
        description="Enzyme target classes, target bonds, parameters, and validity labels are represented explicitly.",
        justification="Catalytic behavior should not be hidden inside substrate-specific rate laws.",
        known_limitations="This metadata object does not by itself implement catalysis, secretion, adsorption, or inactivation.",
        source="FungMod enzyme entity design.",
    )


@dataclass(frozen=True)
class Enzyme:
    """Catalyst metadata used to match fungi, substrates, and processes."""

    name: str
    enzyme_class: str
    target_bond_types: tuple[str, ...]
    target_substrate_classes: tuple[str, ...] = ()
    target_substrate_names: tuple[str, ...] = ()
    catalytic_parameters: ParameterSet = field(default_factory=ParameterSet)
    adsorption_parameters: ParameterSet = field(default_factory=ParameterSet)
    ph_profile: Any | None = None
    temperature_profile: Any | None = None
    validity_labels: tuple[str, ...] = ()
    assumptions: tuple[Assumption, ...] = field(default_factory=lambda: (enzyme_entity_assumption(),))
    source: str | None = None
    notes: str = ""

    def validate(self, *, allow_unsourced_for_testing: bool = False) -> None:
        if not allow_unsourced_for_testing and not has_text(self.source):
            raise ProvenanceError(f"Enzyme {self.name!r} is missing a source.")
        self.catalytic_parameters.validate(
            allow_unsourced_for_testing=allow_unsourced_for_testing,
            require_values=False,
        )
        self.adsorption_parameters.validate(
            allow_unsourced_for_testing=allow_unsourced_for_testing,
            require_values=False,
        )
        if not self.target_bond_types:
            raise ValueError(f"Enzyme {self.name!r} must declare at least one target bond type.")

    def compatible_with_substrate(self, substrate: Any, *, bond_type: str | None = None) -> bool:
        """Return whether this enzyme can plausibly act on substrate metadata."""

        substrate_name = str(getattr(substrate, "name", "")).casefold()
        chemical_class = str(getattr(substrate, "chemical_class", "")).casefold()
        accessible_bonds = {str(bond).casefold() for bond in getattr(substrate, "accessible_bonds", ())}
        required_classes = {str(item).casefold() for item in getattr(substrate, "required_enzyme_classes", ())}
        enzyme_class_ok = not required_classes or self.enzyme_class.casefold() in required_classes
        requested_bond = bond_type.casefold() if bond_type is not None else None
        target_bonds = {bond.casefold() for bond in self.target_bond_types}
        bond_ok = (
            requested_bond in target_bonds
            if requested_bond is not None
            else bool(target_bonds.intersection(accessible_bonds))
        )
        target_names = {name.casefold() for name in self.target_substrate_names}
        target_classes = {name.casefold() for name in self.target_substrate_classes}
        substrate_ok = (
            not target_names and not target_classes
        ) or substrate_name in target_names or chemical_class in target_classes
        return enzyme_class_ok and bond_ok and substrate_ok

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enzyme_class": self.enzyme_class,
            "target_bond_types": list(self.target_bond_types),
            "target_substrate_classes": list(self.target_substrate_classes),
            "target_substrate_names": list(self.target_substrate_names),
            "catalytic_parameters": self.catalytic_parameters.to_dict(),
            "adsorption_parameters": self.adsorption_parameters.to_dict(),
            "ph_profile": None if self.ph_profile is None else str(self.ph_profile),
            "temperature_profile": None if self.temperature_profile is None else str(self.temperature_profile),
            "validity_labels": list(self.validity_labels),
            "assumptions": [assumption.to_dict() for assumption in self.assumptions],
            "source": self.source,
            "notes": self.notes,
        }


__all__ = ["Enzyme", "enzyme_entity_assumption"]
