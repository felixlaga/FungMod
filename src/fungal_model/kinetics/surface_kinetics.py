"""Surface-limited PET hydrolysis kinetics.

First model
-----------

``theta = K_ads * E / (1 + K_ads * E)``

``rate = k_surface * theta * A_accessible``

This is a deliberately small heterogeneous model. It represents an equilibrium
adsorption coverage and hydrolysis proportional to occupied accessible PET
surface area. It does not include dynamic adsorption/desorption state variables,
enzyme deactivation, product inhibition, diffusion, crystallinity evolution, or
changes in surface area during erosion.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.provenance import UnknownParameterError
from fungal_model.core.units import Q_, Quantity, assert_compatible, require_quantity
from fungal_model.kinetics.arrhenius import ArrheniusReferenceTemperatureScaler
from fungal_model.kinetics.langmuir import langmuir_surface_coverage
from fungal_model.kinetics.ph import GaussianPHActivityProfile
from fungal_model.substrates.pet import PETSubstrate


def pet_surface_hydrolysis_assumption() -> Assumption:
    """Return the explicit Stage 4 PET surface hydrolysis assumption."""

    return Assumption(
        name="equilibrium Langmuir PET surface hydrolysis",
        description=(
            "Free enzyme adsorbs to accessible PET surface according to a "
            "Langmuir equilibrium coverage, and hydrolysis rate is proportional "
            "to occupied accessible surface area."
        ),
        justification=(
            "A minimal heterogeneous model is needed before more detailed PET "
            "transport, adsorption dynamics, crystallinity evolution, or erosion "
            "models are introduced."
        ),
        known_limitations=(
            "Uses a constant accessible surface area supplied by PET metadata. "
            "Does not model enzyme depletion by binding, surface renewal, "
            "product inhibition, enzyme deactivation, diffusion limitation, or "
            "time-varying crystallinity."
        ),
        source="Modelling assumption derived from Langmuir adsorption coupled to a surface-proportional hydrolysis rate.",
    )


def _ensure_non_negative(quantity: Quantity, name: str) -> None:
    if np.any(np.asarray(quantity.magnitude, dtype=float) < 0):
        raise ValueError(f"{name} must be non-negative.")


def _is_zero_or_negative(quantity: Quantity) -> bool:
    values = np.asarray(quantity.magnitude, dtype=float)
    return bool(np.all(values <= 0))


def surface_hydrolysis_rate(
    *,
    free_enzyme: Quantity,
    adsorption_equilibrium_constant: Quantity,
    accessible_surface_area: Quantity,
    surface_hydrolysis_rate_constant: Quantity,
    pet_mass: Quantity | None = None,
    rate_units: str | None = None,
) -> Quantity:
    """Compute PET surface hydrolysis rate with dimensional checks."""

    enzyme = require_quantity(free_enzyme, name="free_enzyme")
    accessible_area = require_quantity(
        accessible_surface_area,
        name="accessible_surface_area",
    )
    surface_rate_constant = require_quantity(
        surface_hydrolysis_rate_constant,
        name="surface_hydrolysis_rate_constant",
    )
    _ensure_non_negative(enzyme, "free_enzyme")
    _ensure_non_negative(accessible_area, "accessible_surface_area")
    _ensure_non_negative(surface_rate_constant, "surface_hydrolysis_rate_constant")

    coverage = langmuir_surface_coverage(
        free_enzyme=enzyme,
        adsorption_equilibrium_constant=adsorption_equilibrium_constant,
    )
    rate = surface_rate_constant * coverage * accessible_area
    if pet_mass is not None:
        mass = require_quantity(pet_mass, name="pet_mass")
        if _is_zero_or_negative(mass):
            rate = rate * Q_(0.0, "dimensionless")
    if rate_units is not None:
        return assert_compatible(rate, rate_units, name="PET surface hydrolysis rate")
    return rate


@dataclass(frozen=True)
class PETSurfaceHydrolysisRateLaw:
    """Callable Stage 4 PET surface hydrolysis rate law for ``Reaction``."""

    pet: PETSubstrate
    enzyme: str
    pet_mass: str
    adsorption_symbol: str
    surface_rate_symbol: str
    rate_units: str
    enzyme_units: str | None = None
    temperature_scaler: ArrheniusReferenceTemperatureScaler | None = None
    ph_profile: GaussianPHActivityProfile | None = None

    def __post_init__(self) -> None:
        if not self.pet.uses_surface_degradation_by_default:
            raise ValueError("PETSurfaceHydrolysisRateLaw requires a surface-model PET substrate.")
        Q_(1, self.rate_units)
        if self.enzyme_units is not None:
            Q_(1, self.enzyme_units)

    @property
    def assumptions(self) -> list[Assumption]:
        assumptions = [pet_surface_hydrolysis_assumption(), *self.pet.assumptions]
        if self.temperature_scaler is not None:
            assumptions.extend(self.temperature_scaler.assumptions)
        if self.ph_profile is not None:
            assumptions.extend(self.ph_profile.assumptions)
        return assumptions

    def __call__(
        self,
        state: Mapping[str, Quantity],
        time: Quantity,
        parameters: ParameterSet,
    ) -> Quantity:
        del time
        enzyme = state[self.enzyme]
        enzyme_units = self.enzyme_units or str(enzyme.units)
        accessible_area = self.pet.accessible_surface_area()
        if accessible_area is None:
            raise UnknownParameterError(
                "PET accessible surface area is unknown for surface hydrolysis. "
                "Supply A_accessible, or supply A_surface, r_rough, and phi_amorphous/chi_c."
            )
        surface_rate_constant = parameters.require_quantity(
            self.surface_rate_symbol,
            f"{self.rate_units} / meter ** 2",
        )
        if self.temperature_scaler is not None:
            surface_rate_constant = self.temperature_scaler.scale(
                reference_rate=surface_rate_constant,
                parameters=parameters,
            )
        rate = surface_hydrolysis_rate(
            free_enzyme=assert_compatible(enzyme, enzyme_units, name=self.enzyme),
            adsorption_equilibrium_constant=parameters.require_quantity(
                self.adsorption_symbol,
                f"1 / ({enzyme_units})",
            ),
            accessible_surface_area=accessible_area,
            surface_hydrolysis_rate_constant=surface_rate_constant,
            pet_mass=state[self.pet_mass],
            rate_units=self.rate_units,
        )
        if self.ph_profile is not None:
            rate = self.ph_profile.scale(rate=rate, parameters=parameters)
        return assert_compatible(rate, self.rate_units, name="environment-scaled PET surface hydrolysis rate")


__all__ = [
    "PETSurfaceHydrolysisRateLaw",
    "pet_surface_hydrolysis_assumption",
    "surface_hydrolysis_rate",
]
