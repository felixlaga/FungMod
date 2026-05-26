from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from fungal_model.chemistry.reactions import Reaction
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.provenance import UnknownParameterError
from fungal_model.core.simulation import SimulationEngine
from fungal_model.core.units import Q_
from fungal_model.core.validators import validate_mass_balance, validate_non_negative
from fungal_model.kinetics.surface_kinetics import PETSurfaceHydrolysisRateLaw
from fungal_model.processes import (
    AccessibleSitePool,
    AccessibleSurfaceAreaModel,
    LangmuirAdsorptionModel,
    ProductReleaseMap,
    SurfaceCatalysisModel,
    SurfaceCatalysisProcess,
    surface_catalysis_rate,
)
from fungal_model.substrates.pet import PETSubstrate, make_pet_parameter_set, pet_product_release_map


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
        source="Artificial generic surface-process benchmark value; no physical claim.",
        confidence_level="testing",
        notes="Used to test generic surface process behaviour.",
        measurement_method="defined benchmark value",
    )


def surface_parameters() -> ParameterSet:
    return ParameterSet(
        [
            parameter(name="adsorption constant", symbol="K_ads", value=1.0, units="liter / mole"),
            parameter(
                name="surface catalysis constant",
                symbol="k_surface",
                value=1.0e-6,
                units="kilogram / meter ** 2 / second",
            ),
        ]
    )


def dummy_surface_process() -> SurfaceCatalysisProcess:
    return SurfaceCatalysisProcess(
        name="dummy non-PET surface cleavage",
        substrate_state="cellulose_mass",
        enzyme_state="E",
        substrate_units="kilogram",
        enzyme_units="mole / liter",
        accessible_site_pool=AccessibleSitePool(
            name="dummy cellulose accessible beta-glycosidic surface",
            bond_type="beta-1,4-glycosidic",
        ),
        accessible_surface_model=AccessibleSurfaceAreaModel.from_quantity(
            name="dummy accessible surface",
            area=Q_(0.5, "meter ** 2"),
        ),
        adsorption_model=LangmuirAdsorptionModel(
            adsorption_symbol="K_ads",
            enzyme_units="mole / liter",
            source="Artificial generic surface-process benchmark.",
        ),
        catalytic_model=SurfaceCatalysisModel(
            surface_rate_symbol="k_surface",
            rate_units="kilogram / second",
            source="Artificial generic surface-process benchmark.",
        ),
        product_release_map=ProductReleaseMap.one_to_one(
            substrate_state="cellulose_mass",
            product_state="soluble_product",
        ),
        state_units={
            "cellulose_mass": "kilogram",
            "soluble_product": "kilogram",
            "E": "mole / liter",
        },
    )


def test_surface_catalysis_rate_limiting_cases() -> None:
    base = dict(
        free_enzyme=Q_(1.0, "mole / liter"),
        adsorption_equilibrium_constant=Q_(1.0, "liter / mole"),
        accessible_surface_area=Q_(1.0, "meter ** 2"),
        surface_catalysis_rate_constant=Q_(1.0e-6, "kilogram / meter ** 2 / second"),
        substrate_amount=Q_(1.0, "kilogram"),
        rate_units="kilogram / second",
    )

    assert surface_catalysis_rate(**{**base, "free_enzyme": Q_(0.0, "mole / liter")}).magnitude == pytest.approx(0.0)
    assert surface_catalysis_rate(**{**base, "accessible_surface_area": Q_(0.0, "meter ** 2")}).magnitude == pytest.approx(0.0)
    assert surface_catalysis_rate(**{**base, "substrate_amount": Q_(0.0, "kilogram")}).magnitude == pytest.approx(0.0)

    small = surface_catalysis_rate(**{**base, "accessible_surface_area": Q_(1.0, "meter ** 2")})
    large = surface_catalysis_rate(**{**base, "accessible_surface_area": Q_(2.0, "meter ** 2")})
    assert large.to("kilogram / second").magnitude > small.to("kilogram / second").magnitude


def test_dummy_non_pet_surface_process_runs_mass_conserving_ode() -> None:
    process = dummy_surface_process()
    engine = SimulationEngine(
        reactions=[process.as_reaction()],
        parameters=surface_parameters(),
        species_units={
            "cellulose_mass": "kilogram",
            "soluble_product": "kilogram",
            "E": "mole / liter",
        },
        assumptions=list(process.assumptions),
    )

    result = engine.simulate(
        initial_state={
            "cellulose_mass": Q_(1.0e-4, "kilogram"),
            "soluble_product": Q_(0.0, "kilogram"),
            "E": Q_(1.0, "mole / liter"),
        },
        t_span=(Q_(0.0, "second"), Q_(10.0, "second")),
        t_eval=Q_(np.linspace(0.0, 10.0, 11), "second"),
    )

    assert result.success
    assert result.species["cellulose_mass"].magnitude[-1] < result.species["cellulose_mass"].magnitude[0]
    assert result.species["soluble_product"].magnitude[-1] > result.species["soluble_product"].magnitude[0]
    assert validate_non_negative(result).passed
    assert validate_mass_balance(
        result,
        conserved_weights={"cellulose_mass": 1.0, "soluble_product": 1.0},
    ).passed


def test_generic_surface_process_module_contains_no_pet_imports() -> None:
    path = Path(__file__).resolve().parents[1] / "src" / "fungal_model" / "processes" / "surface.py"
    source = path.read_text(encoding="utf-8")

    assert "PETSubstrate" not in source
    assert "substrates.pet" not in source


def test_pet_rate_law_uses_generic_surface_process_composition() -> None:
    pet = PETSubstrate(
        parameters=make_pet_parameter_set(
            [
                parameter(
                    name="PET accessible surface area",
                    symbol="A_accessible",
                    value=0.25,
                    units="meter ** 2",
                )
            ]
        )
    )
    rate_law = PETSurfaceHydrolysisRateLaw(
        pet=pet,
        enzyme="E",
        pet_mass="PET",
        adsorption_symbol="K_ads",
        surface_rate_symbol="k_surface",
        rate_units="kilogram / second",
        enzyme_units="mole / liter",
    )
    generic_process = rate_law.as_generic_process(product_state="hydrolysate")
    state = {"PET": Q_(1.0, "kilogram"), "E": Q_(1.0, "mole / liter")}

    assert isinstance(generic_process, SurfaceCatalysisProcess)
    assert generic_process.accessible_site_pool.bond_type == "ester"
    assert rate_law(state, Q_(0.0, "second"), surface_parameters()).magnitude == pytest.approx(
        generic_process.rate(state, Q_(0.0, "second"), surface_parameters()).magnitude
    )


def test_pet_generic_surface_process_fails_when_accessible_surface_missing() -> None:
    pet = PETSubstrate()
    rate_law = PETSurfaceHydrolysisRateLaw(
        pet=pet,
        enzyme="E",
        pet_mass="PET",
        adsorption_symbol="K_ads",
        surface_rate_symbol="k_surface",
        rate_units="kilogram / second",
        enzyme_units="mole / liter",
    )

    with pytest.raises(UnknownParameterError):
        rate_law.as_generic_process().rate(
            {"PET": Q_(1.0, "kilogram"), "E": Q_(1.0, "mole / liter")},
            Q_(0.0, "second"),
            surface_parameters(),
        )


def test_pet_product_release_map_conserves_mass_equivalent_benchmark() -> None:
    product_map = pet_product_release_map(substrate_state="PET", product_state="hydrolysate")

    assert product_map.validate_weight_conservation({"PET": 1.0, "hydrolysate": 1.0})


def test_pet_generic_surface_process_can_drive_reaction_engine() -> None:
    pet = PETSubstrate(
        parameters=make_pet_parameter_set(
            [
                parameter(
                    name="PET accessible surface area",
                    symbol="A_accessible",
                    value=0.1,
                    units="meter ** 2",
                )
            ]
        )
    )
    generic_process = PETSurfaceHydrolysisRateLaw(
        pet=pet,
        enzyme="E",
        pet_mass="PET",
        adsorption_symbol="K_ads",
        surface_rate_symbol="k_surface",
        rate_units="kilogram / second",
        enzyme_units="mole / liter",
    ).as_generic_process(product_state="hydrolysate")
    reaction = Reaction(
        name="PET through generic surface process",
        reactants={"PET": 1.0},
        products={"hydrolysate": 1.0},
        rate_law=generic_process.rate,
        rate_units="kilogram / second",
        assumptions=list(generic_process.assumptions),
        source="Generic surface process PET integration test.",
    )
    engine = SimulationEngine(
        reactions=[reaction],
        parameters=surface_parameters(),
        species_units={"PET": "kilogram", "hydrolysate": "kilogram", "E": "mole / liter"},
        assumptions=list(generic_process.assumptions),
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
    assert validate_mass_balance(result, conserved_weights={"PET": 1.0, "hydrolysate": 1.0}).passed
