"""Environment entity for process and modifier evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from fungal_model.core.assumptions import Assumption
from fungal_model.core.provenance import ProvenanceError, has_text
from fungal_model.core.units import Quantity, assert_compatible


def environment_assumption() -> Assumption:
    """Return the generic assumption for fixed environmental conditions."""

    return Assumption(
        name="fixed environmental condition metadata",
        description="Environmental values are supplied explicitly and read by modifiers or processes.",
        justification="Temperature, pH, oxygen, and water activity must not be hidden loose parameters.",
        known_limitations=(
            "This entity stores environmental conditions but does not model "
            "environmental dynamics, gradients, buffering, or feedback by itself."
        ),
        source="FungMod environment entity design.",
    )


@dataclass(frozen=True)
class Environment:
    """Environmental conditions read by processes and modifiers."""

    name: str
    temperature: Quantity | None = None
    ph: Quantity | None = None
    oxygen_concentration: Quantity | None = None
    oxygen_available: Quantity | None = None
    water_activity: Quantity | None = None
    nutrients: Mapping[str, Quantity] = field(default_factory=dict)
    ionic_strength: Quantity | None = None
    pressure: Quantity | None = None
    boundary_conditions: Mapping[str, Any] = field(default_factory=dict)
    validity_labels: tuple[str, ...] = ()
    assumptions: tuple[Assumption, ...] = field(default_factory=lambda: (environment_assumption(),))
    source: str | None = None
    notes: str = ""

    def validate(self, *, allow_unsourced_for_testing: bool = False) -> None:
        if not allow_unsourced_for_testing and not has_text(self.source):
            raise ProvenanceError(f"Environment {self.name!r} is missing a source.")
        if self.temperature is not None:
            assert_compatible(self.temperature, "kelvin", name="environment.temperature")
        if self.ph is not None:
            assert_compatible(self.ph, "dimensionless", name="environment.ph")
        if self.oxygen_concentration is not None:
            # Concentration units vary by model. This check verifies that units exist.
            assert_compatible(self.oxygen_concentration, str(self.oxygen_concentration.units), name="environment.oxygen_concentration")
        if self.oxygen_available is not None:
            assert_compatible(self.oxygen_available, "kilogram", name="environment.oxygen_available")
        if self.water_activity is not None:
            assert_compatible(self.water_activity, "dimensionless", name="environment.water_activity")
        for nutrient, quantity in self.nutrients.items():
            assert_compatible(quantity, str(quantity.units), name=f"environment.nutrients[{nutrient}]")
        if self.ionic_strength is not None:
            assert_compatible(self.ionic_strength, "mole / liter", name="environment.ionic_strength")
        if self.pressure is not None:
            assert_compatible(self.pressure, "pascal", name="environment.pressure")

    def require_temperature(self) -> Quantity:
        if self.temperature is None:
            raise ValueError(f"Environment {self.name!r} does not define temperature.")
        return assert_compatible(self.temperature, "kelvin", name="environment.temperature")

    def require_ph(self) -> Quantity:
        if self.ph is None:
            raise ValueError(f"Environment {self.name!r} does not define pH.")
        return assert_compatible(self.ph, "dimensionless", name="environment.ph")

    def require_oxygen_concentration(self, units: str) -> Quantity:
        if self.oxygen_concentration is None:
            raise ValueError(f"Environment {self.name!r} does not define oxygen concentration.")
        return assert_compatible(self.oxygen_concentration, units, name="environment.oxygen_concentration")

    def require_water_activity(self) -> Quantity:
        if self.water_activity is None:
            raise ValueError(f"Environment {self.name!r} does not define water activity.")
        return assert_compatible(self.water_activity, "dimensionless", name="environment.water_activity")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "temperature": _quantity_dict(self.temperature),
            "ph": _quantity_dict(self.ph),
            "oxygen_concentration": _quantity_dict(self.oxygen_concentration),
            "oxygen_available": _quantity_dict(self.oxygen_available),
            "water_activity": _quantity_dict(self.water_activity),
            "nutrients": {
                name: _quantity_dict(quantity)
                for name, quantity in self.nutrients.items()
            },
            "ionic_strength": _quantity_dict(self.ionic_strength),
            "pressure": _quantity_dict(self.pressure),
            "boundary_conditions": dict(self.boundary_conditions),
            "validity_labels": list(self.validity_labels),
            "assumptions": [assumption.to_dict() for assumption in self.assumptions],
            "source": self.source,
            "notes": self.notes,
        }


def _quantity_dict(quantity: Quantity | None) -> dict[str, Any] | None:
    if quantity is None:
        return None
    return {"value": quantity.magnitude, "units": str(quantity.units)}


__all__ = ["Environment", "environment_assumption"]
