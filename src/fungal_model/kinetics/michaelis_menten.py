"""Homogeneous Michaelis-Menten kinetics.

Equations
---------

Classic dissolved-substrate form:

``v = Vmax * S / (Km + S)``

Enzyme-explicit form:

``v = kcat * E * S / (Km + S)``

Assumptions
-----------

This module represents homogeneous enzyme kinetics for dissolved, well-mixed
substrate. It is suitable as a benchmark layer for the ODE engine and for
genuinely dissolved substrates. It is not a default PET model: PET is a solid
polymer whose degradation is surface-limited and accessibility-limited. Any use
of this module for PET should be labelled as an artificial benchmark.

Reference
---------

The equations are the canonical Michaelis-Menten / Briggs-Haldane rate forms.
The implementation does not supply numerical parameter values; all values must
come through provenance-tracked ``Parameter`` objects.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import numpy as np

from fungal_model.chemistry.reactions import RateLaw
from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity

KineticsContext = Literal["homogeneous_dissolved"]


def homogeneous_michaelis_menten_assumption() -> Assumption:
    """Return the explicit assumption attached to these rate laws."""

    return Assumption(
        name="homogeneous Michaelis-Menten kinetics",
        description=(
            "The substrate and enzyme are represented as well-mixed dissolved "
            "quantities with rate v = Vmax*S/(Km + S), or v = kcat*E*S/(Km + S)."
        ),
        justification=(
            "This is a standard reduced enzyme-kinetic form and is useful as a "
            "validated benchmark before heterogeneous surface models are added."
        ),
        known_limitations=(
            "Does not represent adsorption, solid-polymer accessibility, PET "
            "crystallinity, product inhibition, enzyme deactivation, transport, "
            "or surface-area limitation."
        ),
        source="Canonical Michaelis-Menten / Briggs-Haldane enzyme kinetics.",
    )


def _ensure_not_negative(quantity: Quantity, name: str) -> None:
    values = np.asarray(quantity.magnitude, dtype=float)
    if np.any(values < 0):
        raise ValueError(f"{name} must be non-negative for Michaelis-Menten kinetics.")


def _ensure_positive(quantity: Quantity, name: str) -> None:
    values = np.asarray(quantity.magnitude, dtype=float)
    if np.any(values <= 0):
        raise ValueError(f"{name} must be positive for Michaelis-Menten kinetics.")


def michaelis_menten_rate(
    *,
    substrate: Quantity,
    vmax: Quantity,
    km: Quantity,
    rate_units: str | None = None,
) -> Quantity:
    """Compute ``v = Vmax * S / (Km + S)`` with dimensional checks.

    Parameters are quantities, not naked numbers. ``substrate`` and ``km`` must
    have compatible dimensions. ``vmax`` sets the rate dimensions; if
    ``rate_units`` is provided, the output is converted to those units and
    incompatibilities raise ``UnitError``.
    """

    substrate_q = require_quantity(substrate, name="substrate")
    km_q = require_quantity(km, name="km")
    vmax_q = require_quantity(vmax, name="vmax")

    substrate_in_km_units = assert_compatible(substrate_q, str(km_q.units), name="substrate")
    _ensure_not_negative(substrate_in_km_units, "substrate")
    _ensure_positive(km_q, "km")
    _ensure_not_negative(vmax_q, "vmax")

    saturation = (substrate_in_km_units / (km_q + substrate_in_km_units)).to("dimensionless")
    rate = vmax_q * saturation
    if rate_units is not None:
        return assert_compatible(rate, rate_units, name="Michaelis-Menten rate")
    return rate


def enzyme_explicit_michaelis_menten_rate(
    *,
    substrate: Quantity,
    enzyme: Quantity,
    kcat: Quantity,
    km: Quantity,
    rate_units: str | None = None,
) -> Quantity:
    """Compute ``v = kcat * E * S / (Km + S)`` with dimensional checks."""

    enzyme_q = require_quantity(enzyme, name="enzyme")
    kcat_q = require_quantity(kcat, name="kcat")
    _ensure_not_negative(enzyme_q, "enzyme")
    _ensure_not_negative(kcat_q, "kcat")
    return michaelis_menten_rate(
        substrate=substrate,
        vmax=kcat_q * enzyme_q,
        km=km,
        rate_units=rate_units,
    )


@dataclass(frozen=True)
class MichaelisMentenRateLaw:
    """Callable homogeneous Michaelis-Menten rate law for ``Reaction`` objects."""

    substrate: str
    vmax_symbol: str
    km_symbol: str
    rate_units: str
    substrate_units: str | None = None
    context: KineticsContext = "homogeneous_dissolved"

    def __post_init__(self) -> None:
        if self.context != "homogeneous_dissolved":
            raise ValueError("MichaelisMentenRateLaw currently supports only homogeneous_dissolved context.")
        Q_(1, self.rate_units)
        if self.substrate_units is not None:
            Q_(1, self.substrate_units)

    @property
    def assumptions(self) -> list[Assumption]:
        return [homogeneous_michaelis_menten_assumption()]

    def __call__(
        self,
        state: Mapping[str, Quantity],
        time: Quantity,
        parameters: ParameterSet,
    ) -> Quantity:
        del time
        substrate = state[self.substrate]
        substrate_units = self.substrate_units or str(substrate.units)
        return michaelis_menten_rate(
            substrate=assert_compatible(substrate, substrate_units, name=self.substrate),
            vmax=parameters.require_quantity(self.vmax_symbol, self.rate_units),
            km=parameters.require_quantity(self.km_symbol, substrate_units),
            rate_units=self.rate_units,
        )

    def as_rate_law(self) -> RateLaw:
        return self


@dataclass(frozen=True)
class EnzymeExplicitMichaelisMentenRateLaw:
    """Callable enzyme-explicit Michaelis-Menten rate law for ``Reaction`` objects."""

    substrate: str
    enzyme: str
    kcat_symbol: str
    km_symbol: str
    rate_units: str
    substrate_units: str | None = None
    enzyme_units: str | None = None
    context: KineticsContext = "homogeneous_dissolved"

    def __post_init__(self) -> None:
        if self.context != "homogeneous_dissolved":
            raise ValueError(
                "EnzymeExplicitMichaelisMentenRateLaw currently supports only homogeneous_dissolved context."
            )
        Q_(1, self.rate_units)
        if self.substrate_units is not None:
            Q_(1, self.substrate_units)
        if self.enzyme_units is not None:
            Q_(1, self.enzyme_units)

    @property
    def assumptions(self) -> list[Assumption]:
        return [homogeneous_michaelis_menten_assumption()]

    def __call__(
        self,
        state: Mapping[str, Quantity],
        time: Quantity,
        parameters: ParameterSet,
    ) -> Quantity:
        del time
        substrate = state[self.substrate]
        enzyme = state[self.enzyme]
        substrate_units = self.substrate_units or str(substrate.units)
        enzyme_units = self.enzyme_units or str(enzyme.units)
        return enzyme_explicit_michaelis_menten_rate(
            substrate=assert_compatible(substrate, substrate_units, name=self.substrate),
            enzyme=assert_compatible(enzyme, enzyme_units, name=self.enzyme),
            kcat=parameters.require_quantity(self.kcat_symbol),
            km=parameters.require_quantity(self.km_symbol, substrate_units),
            rate_units=self.rate_units,
        )

    def as_rate_law(self) -> RateLaw:
        return self


__all__ = [
    "EnzymeExplicitMichaelisMentenRateLaw",
    "KineticsContext",
    "MichaelisMentenRateLaw",
    "enzyme_explicit_michaelis_menten_rate",
    "homogeneous_michaelis_menten_assumption",
    "michaelis_menten_rate",
]
