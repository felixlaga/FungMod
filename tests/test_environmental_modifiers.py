from __future__ import annotations

import numpy as np
import pytest

from fungal_model.chemistry.reactions import Reaction
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.provenance import UnknownParameterError
from fungal_model.core.simulation import SimulationEngine
from fungal_model.core.units import Q_
from fungal_model.core.validators import validate_mass_balance, validate_non_negative
from fungal_model.kinetics.arrhenius import (
    ArrheniusReferenceTemperatureScaler,
    EnvironmentalValidityWarning,
    arrhenius_rate_constant,
    arrhenius_reference_scaled_rate,
)
from fungal_model.kinetics.ph import GaussianPHActivityProfile, gaussian_ph_activity
from fungal_model.kinetics.surface_kinetics import PETSurfaceHydrolysisRateLaw
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
        source="Artificial Stage 5 environmental-modifier benchmark value; no physical claim.",
        confidence_level="testing",
        notes="Used only for validating Stage 5 temperature and pH modifiers.",
        measurement_method="defined benchmark value",
    )


def environmental_parameters(*, temperature=310.0, ph=7.0) -> ParameterSet:
    return ParameterSet(
        [
            parameter(
                name="benchmark PET adsorption equilibrium constant",
                symbol="K_ads",
                value=1.0,
                units="liter / mole",
            ),
            parameter(
                name="benchmark PET surface hydrolysis constant at reference temperature",
                symbol="k_surface",
                value=1.0e-6,
                units="kilogram / meter ** 2 / second",
            ),
            parameter(
                name="benchmark activation energy",
                symbol="Ea",
                value=40.0,
                units="kilojoule / mole",
            ),
            parameter(
                name="benchmark reference temperature",
                symbol="T_ref",
                value=300.0,
                units="kelvin",
            ),
            parameter(
                name="benchmark environmental temperature",
                symbol="T",
                value=temperature,
                units="kelvin",
            ),
            parameter(
                name="benchmark minimum measured temperature",
                symbol="T_min",
                value=290.0,
                units="kelvin",
            ),
            parameter(
                name="benchmark maximum measured temperature",
                symbol="T_max",
                value=330.0,
                units="kelvin",
            ),
            parameter(
                name="benchmark pH",
                symbol="pH",
                value=ph,
                units="dimensionless",
            ),
            parameter(
                name="benchmark pH optimum",
                symbol="pH_opt",
                value=7.0,
                units="dimensionless",
            ),
            parameter(
                name="benchmark pH Gaussian width",
                symbol="pH_sigma",
                value=1.0,
                units="dimensionless",
            ),
            parameter(
                name="benchmark minimum measured pH",
                symbol="pH_min",
                value=5.0,
                units="dimensionless",
            ),
            parameter(
                name="benchmark maximum measured pH",
                symbol="pH_max",
                value=9.0,
                units="dimensionless",
            ),
        ]
    )


def pet_with_accessible_area(area=0.1) -> PETSubstrate:
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


def temperature_scaler() -> ArrheniusReferenceTemperatureScaler:
    return ArrheniusReferenceTemperatureScaler(
        activation_energy_symbol="Ea",
        reference_temperature_symbol="T_ref",
        temperature_symbol="T",
        minimum_temperature_symbol="T_min",
        maximum_temperature_symbol="T_max",
        source="Artificial Stage 5 temperature validity range.",
    )


def ph_profile() -> GaussianPHActivityProfile:
    return GaussianPHActivityProfile(
        ph_symbol="pH",
        optimum_symbol="pH_opt",
        width_symbol="pH_sigma",
        minimum_ph_symbol="pH_min",
        maximum_ph_symbol="pH_max",
        source="Artificial Stage 5 pH validity range.",
    )


def test_arrhenius_reference_rate_equals_reference_at_reference_temperature() -> None:
    scaled = arrhenius_reference_scaled_rate(
        reference_rate=Q_(2.0, "1 / second"),
        activation_energy=Q_(40.0, "kilojoule / mole"),
        temperature=Q_(300.0, "kelvin"),
        reference_temperature=Q_(300.0, "kelvin"),
        minimum_temperature=Q_(290.0, "kelvin"),
        maximum_temperature=Q_(330.0, "kelvin"),
        source="Artificial Stage 5 Arrhenius test range.",
        output_units="1 / second",
    )

    assert scaled.to("1 / second").magnitude == pytest.approx(2.0)


def test_arrhenius_increases_rate_with_temperature_inside_valid_range() -> None:
    low = arrhenius_reference_scaled_rate(
        reference_rate=Q_(1.0, "1 / second"),
        activation_energy=Q_(40.0, "kilojoule / mole"),
        temperature=Q_(300.0, "kelvin"),
        reference_temperature=Q_(300.0, "kelvin"),
        minimum_temperature=Q_(290.0, "kelvin"),
        maximum_temperature=Q_(330.0, "kelvin"),
        source="Artificial Stage 5 Arrhenius test range.",
        output_units="1 / second",
    )
    high = arrhenius_reference_scaled_rate(
        reference_rate=Q_(1.0, "1 / second"),
        activation_energy=Q_(40.0, "kilojoule / mole"),
        temperature=Q_(320.0, "kelvin"),
        reference_temperature=Q_(300.0, "kelvin"),
        minimum_temperature=Q_(290.0, "kelvin"),
        maximum_temperature=Q_(330.0, "kelvin"),
        source="Artificial Stage 5 Arrhenius test range.",
        output_units="1 / second",
    )

    assert high.magnitude > low.magnitude


def test_arrhenius_warns_outside_measured_temperature_range() -> None:
    with pytest.warns(EnvironmentalValidityWarning):
        arrhenius_reference_scaled_rate(
            reference_rate=Q_(1.0, "1 / second"),
            activation_energy=Q_(40.0, "kilojoule / mole"),
            temperature=Q_(350.0, "kelvin"),
            reference_temperature=Q_(300.0, "kelvin"),
            minimum_temperature=Q_(290.0, "kelvin"),
            maximum_temperature=Q_(330.0, "kelvin"),
            source="Artificial Stage 5 Arrhenius test range.",
            output_units="1 / second",
        )


def test_arrhenius_prefactor_form_returns_expected_units() -> None:
    rate = arrhenius_rate_constant(
        pre_exponential_factor=Q_(1.0e6, "1 / second"),
        activation_energy=Q_(40.0, "kilojoule / mole"),
        temperature=Q_(310.0, "kelvin"),
        minimum_temperature=Q_(290.0, "kelvin"),
        maximum_temperature=Q_(330.0, "kelvin"),
        source="Artificial Stage 5 Arrhenius test range.",
        output_units="1 / second",
    )

    assert rate.check("[time] ** -1")


def test_gaussian_ph_activity_is_one_at_optimum_and_lower_away() -> None:
    optimum = gaussian_ph_activity(
        ph=Q_(7.0, "dimensionless"),
        optimum_ph=Q_(7.0, "dimensionless"),
        width=Q_(1.0, "dimensionless"),
        minimum_ph=Q_(5.0, "dimensionless"),
        maximum_ph=Q_(9.0, "dimensionless"),
        source="Artificial Stage 5 pH profile range.",
    )
    away = gaussian_ph_activity(
        ph=Q_(8.0, "dimensionless"),
        optimum_ph=Q_(7.0, "dimensionless"),
        width=Q_(1.0, "dimensionless"),
        minimum_ph=Q_(5.0, "dimensionless"),
        maximum_ph=Q_(9.0, "dimensionless"),
        source="Artificial Stage 5 pH profile range.",
    )

    assert optimum.to("dimensionless").magnitude == pytest.approx(1.0)
    assert away.to("dimensionless").magnitude < optimum.to("dimensionless").magnitude


def test_gaussian_ph_activity_warns_outside_measured_range() -> None:
    with pytest.warns(EnvironmentalValidityWarning):
        gaussian_ph_activity(
            ph=Q_(10.0, "dimensionless"),
            optimum_ph=Q_(7.0, "dimensionless"),
            width=Q_(1.0, "dimensionless"),
            minimum_ph=Q_(5.0, "dimensionless"),
            maximum_ph=Q_(9.0, "dimensionless"),
            source="Artificial Stage 5 pH profile range.",
        )


def test_gaussian_ph_width_must_be_positive() -> None:
    with pytest.raises(ValueError):
        gaussian_ph_activity(
            ph=Q_(7.0, "dimensionless"),
            optimum_ph=Q_(7.0, "dimensionless"),
            width=Q_(0.0, "dimensionless"),
            source="Artificial Stage 5 pH profile range.",
        )


def test_environmentally_scaled_pet_surface_rate_law_drives_ode() -> None:
    pet = pet_with_accessible_area(0.1)
    rate_law = PETSurfaceHydrolysisRateLaw(
        pet=pet,
        enzyme="E",
        pet_mass="PET",
        adsorption_symbol="K_ads",
        surface_rate_symbol="k_surface",
        rate_units="kilogram / second",
        enzyme_units="mole / liter",
        temperature_scaler=temperature_scaler(),
        ph_profile=ph_profile(),
    )
    reaction = Reaction(
        name="environment-scaled PET surface hydrolysis",
        reactants={"PET": 1.0},
        products={"hydrolysate": 1.0},
        rate_law=rate_law,
        rate_units="kilogram / second",
        assumptions=rate_law.assumptions,
        source="Stage 5 environmental modifier benchmark.",
    )
    engine = SimulationEngine(
        reactions=[reaction],
        parameters=environmental_parameters(),
        species_units={
            "PET": "kilogram",
            "hydrolysate": "kilogram",
            "E": "mole / liter",
        },
        assumptions=rate_law.assumptions,
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


def test_temperature_scaler_requires_activation_energy_value() -> None:
    parameters = environmental_parameters()
    parameters.parameters["Ea"] = parameter(
        name="unknown activation energy",
        symbol="Ea",
        value=None,
        units="joule / mole",
    )

    with pytest.raises(UnknownParameterError):
        temperature_scaler().scale(
            reference_rate=Q_(1.0, "1 / second"),
            parameters=parameters,
        )


def test_ph_profile_requires_source() -> None:
    with pytest.raises(ValueError):
        GaussianPHActivityProfile(
            ph_symbol="pH",
            optimum_symbol="pH_opt",
            width_symbol="pH_sigma",
            source="",
        )
