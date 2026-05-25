from __future__ import annotations

import numpy as np
import pytest

from fungal_model.chemistry.reactions import Reaction
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.simulation import SimulationEngine
from fungal_model.core.units import Q_, UnitError
from fungal_model.core.validators import validate_mass_balance, validate_non_negative
from fungal_model.kinetics.langmuir import langmuir_surface_coverage
from fungal_model.kinetics.surface_kinetics import (
    PETSurfaceHydrolysisRateLaw,
    pet_surface_hydrolysis_assumption,
    surface_hydrolysis_rate,
)
from fungal_model.substrates.pet import PETSubstrate, make_pet_parameter_set


def parameter(
    *,
    name: str,
    symbol: str,
    value,
    units: str,
) -> Parameter:
    return Parameter(
        name=name,
        symbol=symbol,
        value=value,
        units=units,
        uncertainty=0.0 if value is not None else None,
        source="Artificial Stage 4 surface-kinetics benchmark value; no physical claim.",
        confidence_level="testing",
        notes="Used only for validating limiting behaviour of the Stage 4 model.",
        measurement_method="defined benchmark value",
    )


def surface_parameters() -> ParameterSet:
    return ParameterSet(
        [
            parameter(
                name="benchmark PET adsorption equilibrium constant",
                symbol="K_ads",
                value=1.0,
                units="liter / mole",
            ),
            parameter(
                name="benchmark PET surface hydrolysis constant",
                symbol="k_surface",
                value=1.0e-6,
                units="kilogram / meter ** 2 / second",
            ),
        ]
    )


def pet_with_accessible_area(area) -> PETSubstrate:
    return PETSubstrate(
        geometry_type="film",
        parameters=make_pet_parameter_set(
            [
                parameter(
                    name="PET accessible surface area",
                    symbol="A_accessible",
                    value=area,
                    units="meter ** 2",
                )
            ]
        ),
    )


def test_langmuir_coverage_zero_enzyme_is_zero() -> None:
    coverage = langmuir_surface_coverage(
        free_enzyme=Q_(0.0, "mole / liter"),
        adsorption_equilibrium_constant=Q_(1.0, "liter / mole"),
    )

    assert coverage.to("dimensionless").magnitude == pytest.approx(0.0)


def test_langmuir_coverage_rejects_incompatible_units() -> None:
    with pytest.raises(UnitError):
        langmuir_surface_coverage(
            free_enzyme=Q_(1.0, "mole / liter"),
            adsorption_equilibrium_constant=Q_(1.0, "second"),
        )


def test_zero_surface_area_gives_zero_degradation() -> None:
    rate = surface_hydrolysis_rate(
        free_enzyme=Q_(1.0, "mole / liter"),
        adsorption_equilibrium_constant=Q_(1.0, "liter / mole"),
        accessible_surface_area=Q_(0.0, "meter ** 2"),
        surface_hydrolysis_rate_constant=Q_(1.0e-6, "kilogram / meter ** 2 / second"),
        pet_mass=Q_(1.0, "kilogram"),
        rate_units="kilogram / second",
    )

    assert rate.to("kilogram / second").magnitude == pytest.approx(0.0)


def test_zero_enzyme_gives_zero_degradation() -> None:
    rate = surface_hydrolysis_rate(
        free_enzyme=Q_(0.0, "mole / liter"),
        adsorption_equilibrium_constant=Q_(1.0, "liter / mole"),
        accessible_surface_area=Q_(1.0, "meter ** 2"),
        surface_hydrolysis_rate_constant=Q_(1.0e-6, "kilogram / meter ** 2 / second"),
        pet_mass=Q_(1.0, "kilogram"),
        rate_units="kilogram / second",
    )

    assert rate.to("kilogram / second").magnitude == pytest.approx(0.0)


def test_zero_pet_mass_gives_zero_degradation() -> None:
    rate = surface_hydrolysis_rate(
        free_enzyme=Q_(1.0, "mole / liter"),
        adsorption_equilibrium_constant=Q_(1.0, "liter / mole"),
        accessible_surface_area=Q_(1.0, "meter ** 2"),
        surface_hydrolysis_rate_constant=Q_(1.0e-6, "kilogram / meter ** 2 / second"),
        pet_mass=Q_(0.0, "kilogram"),
        rate_units="kilogram / second",
    )

    assert rate.to("kilogram / second").magnitude == pytest.approx(0.0)


def test_increasing_surface_area_increases_degradation() -> None:
    small = surface_hydrolysis_rate(
        free_enzyme=Q_(1.0, "mole / liter"),
        adsorption_equilibrium_constant=Q_(1.0, "liter / mole"),
        accessible_surface_area=Q_(1.0, "meter ** 2"),
        surface_hydrolysis_rate_constant=Q_(1.0e-6, "kilogram / meter ** 2 / second"),
        pet_mass=Q_(1.0, "kilogram"),
        rate_units="kilogram / second",
    )
    large = surface_hydrolysis_rate(
        free_enzyme=Q_(1.0, "mole / liter"),
        adsorption_equilibrium_constant=Q_(1.0, "liter / mole"),
        accessible_surface_area=Q_(2.0, "meter ** 2"),
        surface_hydrolysis_rate_constant=Q_(1.0e-6, "kilogram / meter ** 2 / second"),
        pet_mass=Q_(1.0, "kilogram"),
        rate_units="kilogram / second",
    )

    assert large.to("kilogram / second").magnitude > small.to("kilogram / second").magnitude


def test_increasing_crystallinity_decreases_derived_accessible_surface() -> None:
    low_crystallinity = PETSubstrate(
        parameters=make_pet_parameter_set(
            [
                parameter(
                    name="geometric surface area",
                    symbol="A_surface",
                    value=1.0,
                    units="meter ** 2",
                ),
                parameter(
                    name="roughness factor",
                    symbol="r_rough",
                    value=1.0,
                    units="dimensionless",
                ),
                parameter(
                    name="low crystallinity",
                    symbol="chi_c",
                    value=0.2,
                    units="dimensionless",
                ),
            ]
        )
    )
    high_crystallinity = PETSubstrate(
        parameters=make_pet_parameter_set(
            [
                parameter(
                    name="geometric surface area",
                    symbol="A_surface",
                    value=1.0,
                    units="meter ** 2",
                ),
                parameter(
                    name="roughness factor",
                    symbol="r_rough",
                    value=1.0,
                    units="dimensionless",
                ),
                parameter(
                    name="high crystallinity",
                    symbol="chi_c",
                    value=0.8,
                    units="dimensionless",
                ),
            ]
        )
    )

    assert (
        low_crystallinity.require_accessible_surface_area().to("meter ** 2").magnitude
        > high_crystallinity.require_accessible_surface_area().to("meter ** 2").magnitude
    )


def test_explicit_accessible_surface_overrides_crystallinity_effect() -> None:
    low_crystallinity = PETSubstrate(
        parameters=make_pet_parameter_set(
            [
                parameter(
                    name="explicit accessible surface",
                    symbol="A_accessible",
                    value=0.3,
                    units="meter ** 2",
                ),
                parameter(
                    name="low crystallinity",
                    symbol="chi_c",
                    value=0.2,
                    units="dimensionless",
                ),
            ]
        )
    )
    high_crystallinity = PETSubstrate(
        parameters=make_pet_parameter_set(
            [
                parameter(
                    name="explicit accessible surface",
                    symbol="A_accessible",
                    value=0.3,
                    units="meter ** 2",
                ),
                parameter(
                    name="high crystallinity",
                    symbol="chi_c",
                    value=0.8,
                    units="dimensionless",
                ),
            ]
        )
    )

    assert low_crystallinity.require_accessible_surface_area().magnitude == pytest.approx(
        high_crystallinity.require_accessible_surface_area().magnitude
    )


def test_pet_surface_rate_law_drives_mass_conserving_ode() -> None:
    pet = pet_with_accessible_area(0.1)
    rate_law = PETSurfaceHydrolysisRateLaw(
        pet=pet,
        enzyme="E",
        pet_mass="PET",
        adsorption_symbol="K_ads",
        surface_rate_symbol="k_surface",
        rate_units="kilogram / second",
        enzyme_units="mole / liter",
    )
    reaction = Reaction(
        name="PET to hydrolysate mass equivalent",
        reactants={"PET": 1.0},
        products={"hydrolysate": 1.0},
        rate_law=rate_law,
        rate_units="kilogram / second",
        assumptions=rate_law.assumptions,
        source="Stage 4 PET surface hydrolysis benchmark.",
        notes="Product is a mass-equivalent lump, not a chemically resolved product distribution.",
    )
    engine = SimulationEngine(
        reactions=[reaction],
        parameters=surface_parameters(),
        species_units={
            "PET": "kilogram",
            "hydrolysate": "kilogram",
            "E": "mole / liter",
        },
        assumptions=[pet_surface_hydrolysis_assumption()],
    )

    result = engine.simulate(
        initial_state={
            "PET": Q_(1.0e-4, "kilogram"),
            "hydrolysate": Q_(0.0, "kilogram"),
            "E": Q_(1.0, "mole / liter"),
        },
        t_span=(Q_(0.0, "second"), Q_(10.0, "second")),
        t_eval=Q_(np.linspace(0.0, 10.0, 11), "second"),
    )

    assert result.success
    assert validate_non_negative(result).passed
    assert validate_mass_balance(
        result,
        conserved_weights={"PET": 1.0, "hydrolysate": 1.0},
    ).passed
    assert result.species["PET"].magnitude[-1] < result.species["PET"].magnitude[0]
    assert result.species["hydrolysate"].magnitude[-1] > result.species["hydrolysate"].magnitude[0]

