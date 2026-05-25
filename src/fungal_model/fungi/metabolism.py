"""Minimal product assimilation interfaces for Stage 6."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.provenance import ProvenanceError, has_text
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity
from fungal_model.fungi.growth import product_limited_growth_assumption


@dataclass(frozen=True)
class ProductAssimilation:
    """Evidence that a degradation product can or cannot support growth."""

    product: str
    assimilable: bool
    source: str | None
    notes: str = ""

    def validate(self, *, allow_unsourced_for_testing: bool = False) -> None:
        if allow_unsourced_for_testing:
            return
        if not has_text(self.source):
            raise ProvenanceError(f"Product assimilation claim for {self.product!r} is missing a source.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "product": self.product,
            "assimilable": self.assimilable,
            "source": self.source,
            "notes": self.notes,
        }


def _ensure_non_negative(quantity: Quantity, name: str) -> None:
    if np.any(np.asarray(quantity.magnitude, dtype=float) < 0):
        raise ValueError(f"{name} must be non-negative.")


def product_uptake_rate(
    *,
    product: Quantity,
    active_biomass: Quantity,
    uptake_coefficient: Quantity,
    assimilation: ProductAssimilation,
    rate_units: str | None = None,
) -> Quantity:
    """Compute product uptake rate gated by assimilability evidence."""

    product_quantity = require_quantity(product, name="product")
    biomass = require_quantity(active_biomass, name="active_biomass")
    coefficient = require_quantity(uptake_coefficient, name="uptake_coefficient")
    _ensure_non_negative(product_quantity, "product")
    _ensure_non_negative(biomass, "active_biomass")
    _ensure_non_negative(coefficient, "uptake_coefficient")
    rate = coefficient * product_quantity * biomass
    if not assimilation.assimilable:
        rate = rate * Q_(0.0, "dimensionless")
    if rate_units is not None:
        return assert_compatible(rate, rate_units, name="product uptake rate")
    return rate


def biomass_yield_coefficient(
    *,
    parameters: ParameterSet,
    yield_symbol: str,
) -> float:
    """Return a dimensionless biomass yield coefficient between 0 and 1."""

    yield_quantity = parameters.require_quantity(yield_symbol, "dimensionless")
    value = float(yield_quantity.magnitude)
    if value < 0.0 or value > 1.0:
        raise ValueError(f"{yield_symbol} must be between 0 and 1 for Stage 6 growth.")
    return value


@dataclass(frozen=True)
class ProductUptakeRateLaw:
    """Callable product uptake rate law gated by explicit assimilation evidence."""

    product: str
    active_biomass: str
    uptake_symbol: str
    assimilation: ProductAssimilation
    rate_units: str
    product_units: str = "kilogram"
    biomass_units: str = "kilogram"

    @property
    def assumptions(self) -> list[Assumption]:
        return [product_limited_growth_assumption()]

    def __call__(
        self,
        state: Mapping[str, Quantity],
        time: Quantity,
        parameters: ParameterSet,
    ) -> Quantity:
        del time
        return product_uptake_rate(
            product=assert_compatible(state[self.product], self.product_units, name=self.product),
            active_biomass=assert_compatible(
                state[self.active_biomass],
                self.biomass_units,
                name=self.active_biomass,
            ),
            uptake_coefficient=parameters.require_quantity(
                self.uptake_symbol,
                f"1 / ({self.biomass_units} * second)",
            ),
            assimilation=self.assimilation,
            rate_units=self.rate_units,
        )


__all__ = [
    "ProductAssimilation",
    "ProductUptakeRateLaw",
    "biomass_yield_coefficient",
    "product_uptake_rate",
]
