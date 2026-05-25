"""Minimal fungal biomass growth and maintenance rate laws."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Quantity, assert_compatible, require_quantity


def maintenance_assumption() -> Assumption:
    """Return the Stage 6 active-biomass maintenance assumption."""

    return Assumption(
        name="first-order active biomass maintenance loss",
        description="Active biomass loses active mass according to dB_active/dt = -m_B * B_active.",
        justification="Maintenance costs should be able to reduce active biomass when growth is absent.",
        known_limitations=(
            "Does not distinguish respiration, dormancy transition, starvation "
            "physiology, autolysis, or death mechanisms."
        ),
        source="Stage 6 modelling assumption for fungal maintenance loss.",
    )


def product_limited_growth_assumption() -> Assumption:
    """Return the Stage 6 product-limited growth assumption."""

    return Assumption(
        name="growth requires assimilable degradation product",
        description=(
            "Active biomass growth can occur only from explicitly assimilable "
            "degradation product; non-assimilable products contribute zero growth."
        ),
        justification="Fungal biomass must not increase without an assimilable carbon/energy source.",
        known_limitations=(
            "Uses a simple product- and biomass-dependent uptake law. Does not "
            "model transporters, intracellular metabolic pathways, oxygen, "
            "toxicity, repression, or thermodynamic yield constraints."
        ),
        source="Stage 6 modelling assumption for product-coupled fungal growth.",
    )


def _ensure_non_negative(quantity: Quantity, name: str) -> None:
    if np.any(np.asarray(quantity.magnitude, dtype=float) < 0):
        raise ValueError(f"{name} must be non-negative.")


def biomass_maintenance_rate(
    *,
    active_biomass: Quantity,
    maintenance_constant: Quantity,
    rate_units: str | None = None,
) -> Quantity:
    """Compute first-order active-biomass maintenance loss."""

    biomass = require_quantity(active_biomass, name="active_biomass")
    maintenance = require_quantity(maintenance_constant, name="maintenance_constant")
    _ensure_non_negative(biomass, "active_biomass")
    _ensure_non_negative(maintenance, "maintenance_constant")
    rate = maintenance * biomass
    if rate_units is not None:
        return assert_compatible(rate, rate_units, name="biomass maintenance rate")
    return rate


@dataclass(frozen=True)
class BiomassMaintenanceRateLaw:
    """Callable first-order active-biomass maintenance rate law."""

    active_biomass: str
    maintenance_symbol: str
    rate_units: str
    biomass_units: str = "kilogram"

    @property
    def assumptions(self) -> list[Assumption]:
        return [maintenance_assumption()]

    def __call__(
        self,
        state: Mapping[str, Quantity],
        time: Quantity,
        parameters: ParameterSet,
    ) -> Quantity:
        del time
        return biomass_maintenance_rate(
            active_biomass=assert_compatible(
                state[self.active_biomass],
                self.biomass_units,
                name=self.active_biomass,
            ),
            maintenance_constant=parameters.require_quantity(self.maintenance_symbol, "1 / second"),
            rate_units=self.rate_units,
        )


__all__ = [
    "BiomassMaintenanceRateLaw",
    "biomass_maintenance_rate",
    "maintenance_assumption",
    "product_limited_growth_assumption",
]
