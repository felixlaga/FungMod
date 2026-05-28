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

from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.provenance import UnknownParameterError
from fungal_model.core.units import Q_, Quantity, assert_compatible
from fungal_model.kinetics.arrhenius import ArrheniusReferenceTemperatureScaler
from fungal_model.kinetics.ph import GaussianPHActivityProfile
from fungal_model.processes.surface import (
    AccessibleSitePool,
    LangmuirAdsorptionModel,
    SurfaceCatalysisModel,
    SurfaceCatalysisProcess,
    surface_catalysis_rate,
)
from fungal_model.substrates.pet import (
    PETAccessibleSurfaceAreaModel,
    PETSubstrate,
    pet_product_release_map,
)


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


def surface_hydrolysis_rate(
    *,
    free_enzyme: Quantity,
    adsorption_equilibrium_constant: Quantity,
    accessible_surface_area: Quantity,
    surface_hydrolysis_rate_constant: Quantity,
    pet_mass: Quantity | None = None,
    rate_units: str | None = None,
) -> Quantity:
    """Compute PET surface hydrolysis rate through generic surface catalysis."""

    return surface_catalysis_rate(
        free_enzyme=free_enzyme,
        adsorption_equilibrium_constant=adsorption_equilibrium_constant,
        accessible_surface_area=accessible_surface_area,
        surface_catalysis_rate_constant=surface_hydrolysis_rate_constant,
        substrate_amount=pet_mass,
        rate_units=rate_units,
    )


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

    def as_generic_process(self, product_state: str = "hydrolysate") -> SurfaceCatalysisProcess:
        """Return the generic surface-catalysis process used by this PET adapter."""

        enzyme_units = self.enzyme_units or "mole / liter"
        return SurfaceCatalysisProcess(
            name="PET surface hydrolysis through generic surface catalysis",
            substrate_state=self.pet_mass,
            enzyme_state=self.enzyme,
            substrate_units="kilogram",
            enzyme_units=enzyme_units,
            accessible_site_pool=AccessibleSitePool(
                name="PET accessible ester-bond surface",
                bond_type=self.pet.dominant_cleavable_bond_type,
                notes="PET-specific accessible surface metadata supplied to a generic surface process.",
            ),
            accessible_surface_model=PETAccessibleSurfaceAreaModel(self.pet),
            adsorption_model=LangmuirAdsorptionModel(
                adsorption_symbol=self.adsorption_symbol,
                enzyme_units=enzyme_units,
                source="PET adapter configured with a generic Langmuir adsorption model.",
            ),
            catalytic_model=SurfaceCatalysisModel(
                surface_rate_symbol=self.surface_rate_symbol,
                rate_units=self.rate_units,
                source="PET adapter configured with a generic surface catalysis model.",
            ),
            product_release_map=pet_product_release_map(
                substrate_state=self.pet_mass,
                product_state=product_state,
            ),
            state_units={self.pet_mass: "kilogram", product_state: "kilogram", self.enzyme: enzyme_units},
            source="PET-specific adapter composed from generic surface process components.",
            notes="PET identity remains outside the generic process module.",
        )

    def __call__(
        self,
        state: Mapping[str, Quantity],
        time: Quantity,
        parameters: ParameterSet,
    ) -> Quantity:
        del time
        enzyme = state[self.enzyme]
        enzyme_units = self.enzyme_units or str(enzyme.units)
        if self.temperature_scaler is None and self.ph_profile is None:
            return self.as_generic_process().rate(state, Q_(0.0, "second"), parameters)
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
