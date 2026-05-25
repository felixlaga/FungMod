from __future__ import annotations

import numpy as np
import pytest

from fungal_model.chemistry.reactions import Reaction
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.provenance import UnknownParameterError
from fungal_model.core.simulation import SimulationEngine
from fungal_model.core.units import Q_, UnitError
from fungal_model.core.validators import validate_non_negative
from fungal_model.fungi import (
    BiomassMaintenanceRateLaw,
    EnzymeCapability,
    EnzymeDecayRateLaw,
    EnzymeProductionCostRateLaw,
    EnzymeProfile,
    EnzymeSecretionRateLaw,
    Fungus,
    ProductAssimilation,
    ProductUptakeRateLaw,
    biomass_yield_coefficient,
    make_fungal_parameter_set,
)


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
        source="Artificial Stage 6 fungal-dynamics benchmark value; no physical claim.",
        confidence_level="testing",
        notes="Used only for validating Stage 6 fungal model behaviour.",
        measurement_method="defined benchmark value",
    )


def fungal_parameters() -> ParameterSet:
    return make_fungal_parameter_set(
        [
            parameter(
                name="minimum growth temperature",
                symbol="T_growth_min",
                value=290.0,
                units="kelvin",
            ),
            parameter(
                name="maximum growth temperature",
                symbol="T_growth_max",
                value=320.0,
                units="kelvin",
            ),
            parameter(
                name="minimum growth pH",
                symbol="pH_growth_min",
                value=5.0,
                units="dimensionless",
            ),
            parameter(
                name="maximum growth pH",
                symbol="pH_growth_max",
                value=8.0,
                units="dimensionless",
            ),
            parameter(
                name="minimum water activity",
                symbol="a_w_min",
                value=0.9,
                units="dimensionless",
            ),
            parameter(
                name="enzyme secretion coefficient",
                symbol="alpha_E",
                value=1.0e-6,
                units="mole / liter / kilogram / second",
            ),
            parameter(
                name="enzyme decay constant",
                symbol="delta_E",
                value=0.1,
                units="1 / second",
            ),
            parameter(
                name="enzyme secretion biomass cost",
                symbol="c_E",
                value=1.0e-4,
                units="kilogram / (mole / liter)",
            ),
            parameter(
                name="active biomass maintenance constant",
                symbol="m_B",
                value=0.01,
                units="1 / second",
            ),
            parameter(
                name="product uptake coefficient",
                symbol="q_product",
                value=2.0,
                units="1 / kilogram / second",
            ),
            parameter(
                name="biomass yield on assimilated product",
                symbol="Y_B",
                value=0.5,
                units="dimensionless",
            ),
        ]
    )


def enzyme_profile() -> EnzymeProfile:
    return EnzymeProfile(
        capabilities=(
            EnzymeCapability(
                name="toy PET-active hydrolase",
                enzyme_class="PETase-like hydrolase",
                target_substrate="polyethylene terephthalate",
                target_bond_type="ester",
                evidence="Artificial Stage 6 test capability.",
                source="Artificial Stage 6 fungal metadata test.",
                notes="No organism-specific claim.",
            ),
        ),
        source="Artificial Stage 6 fungal metadata test.",
        notes="No organism-specific claim.",
    )


def test_fungus_metadata_requires_known_parameter_values_for_scientific_use() -> None:
    fungus = Fungus(
        species_name="Test fungus",
        enzyme_profile=enzyme_profile(),
        parameters=make_fungal_parameter_set(),
        known_substrates=("polyethylene terephthalate",),
    )

    fungus.validate(require_parameter_values=False)
    with pytest.raises(UnknownParameterError):
        fungus.validate(require_parameter_values=True)


def test_fungal_parameter_units_are_enforced() -> None:
    bad = parameter(
        name="bad secretion coefficient",
        symbol="alpha_E",
        value=1.0,
        units="second",
    )

    with pytest.raises(UnitError):
        make_fungal_parameter_set([bad])


def secretion_engine(parameters: ParameterSet | None = None) -> SimulationEngine:
    params = parameters or fungal_parameters()
    secretion = EnzymeSecretionRateLaw(
        active_biomass="B_active",
        secretion_symbol="alpha_E",
        rate_units="mole / liter / second",
    )
    cost = EnzymeProductionCostRateLaw(
        active_biomass="B_active",
        secretion_symbol="alpha_E",
        secretion_cost_symbol="c_E",
        enzyme_rate_units="mole / liter / second",
        biomass_rate_units="kilogram / second",
    )
    reactions = [
        Reaction(
            name="fungal enzyme secretion",
            reactants={},
            products={"E": 1.0},
            rate_law=secretion,
            rate_units="mole / liter / second",
            assumptions=secretion.assumptions,
            source="Stage 6 enzyme secretion benchmark.",
        ),
        Reaction(
            name="enzyme secretion active biomass cost",
            reactants={"B_active": 1.0},
            products={"B_dead": 1.0},
            rate_law=cost,
            rate_units="kilogram / second",
            assumptions=cost.assumptions,
            source="Stage 6 enzyme cost benchmark.",
        ),
    ]
    return SimulationEngine(
        reactions=reactions,
        parameters=params,
        species_units={
            "B_active": "kilogram",
            "B_dead": "kilogram",
            "E": "mole / liter",
        },
        assumptions=[*secretion.assumptions, *cost.assumptions],
    )


def test_no_biomass_means_no_enzyme_production() -> None:
    result = secretion_engine().simulate(
        initial_state={
            "B_active": Q_(0.0, "kilogram"),
            "B_dead": Q_(0.0, "kilogram"),
            "E": Q_(0.0, "mole / liter"),
        },
        t_span=(Q_(0.0, "second"), Q_(10.0, "second")),
        t_eval=Q_(np.linspace(0.0, 10.0, 11), "second"),
    )

    assert result.success
    assert result.species["E"].magnitude[-1] == pytest.approx(0.0)
    assert validate_non_negative(result).passed


def test_enzyme_production_has_biomass_cost() -> None:
    result = secretion_engine().simulate(
        initial_state={
            "B_active": Q_(1.0, "kilogram"),
            "B_dead": Q_(0.0, "kilogram"),
            "E": Q_(0.0, "mole / liter"),
        },
        t_span=(Q_(0.0, "second"), Q_(10.0, "second")),
        t_eval=Q_(np.linspace(0.0, 10.0, 11), "second"),
    )

    assert result.success
    assert result.species["E"].magnitude[-1] > 0.0
    assert result.species["B_active"].magnitude[-1] < result.species["B_active"].magnitude[0]
    assert result.species["B_dead"].magnitude[-1] > 0.0
    assert validate_non_negative(result).passed


def test_enzyme_degradation_occurs_over_time() -> None:
    decay = EnzymeDecayRateLaw(
        enzyme="E",
        decay_symbol="delta_E",
        rate_units="mole / liter / second",
        enzyme_units="mole / liter",
    )
    reaction = Reaction(
        name="extracellular enzyme decay",
        reactants={"E": 1.0},
        products={},
        rate_law=decay,
        rate_units="mole / liter / second",
        assumptions=decay.assumptions,
        source="Stage 6 enzyme decay benchmark.",
    )
    engine = SimulationEngine(
        reactions=[reaction],
        parameters=fungal_parameters(),
        species_units={"E": "mole / liter"},
        assumptions=decay.assumptions,
    )

    result = engine.simulate(
        initial_state={"E": Q_(1.0e-6, "mole / liter")},
        t_span=(Q_(0.0, "second"), Q_(10.0, "second")),
        t_eval=Q_(np.linspace(0.0, 10.0, 11), "second"),
    )

    assert result.success
    assert result.species["E"].magnitude[-1] < result.species["E"].magnitude[0]
    assert validate_non_negative(result).passed


def test_maintenance_cost_can_make_active_biomass_decline() -> None:
    maintenance = BiomassMaintenanceRateLaw(
        active_biomass="B_active",
        maintenance_symbol="m_B",
        rate_units="kilogram / second",
    )
    reaction = Reaction(
        name="active biomass maintenance loss",
        reactants={"B_active": 1.0},
        products={"B_dead": 1.0},
        rate_law=maintenance,
        rate_units="kilogram / second",
        assumptions=maintenance.assumptions,
        source="Stage 6 maintenance benchmark.",
    )
    engine = SimulationEngine(
        reactions=[reaction],
        parameters=fungal_parameters(),
        species_units={"B_active": "kilogram", "B_dead": "kilogram"},
        assumptions=maintenance.assumptions,
    )

    result = engine.simulate(
        initial_state={"B_active": Q_(1.0, "kilogram"), "B_dead": Q_(0.0, "kilogram")},
        t_span=(Q_(0.0, "second"), Q_(10.0, "second")),
    )

    assert result.success
    assert result.species["B_active"].magnitude[-1] < result.species["B_active"].magnitude[0]
    assert result.species["B_dead"].magnitude[-1] > 0.0
    assert validate_non_negative(result).passed


def assimilation_engine(assimilation: ProductAssimilation) -> SimulationEngine:
    parameters = fungal_parameters()
    yield_value = biomass_yield_coefficient(parameters=parameters, yield_symbol="Y_B")
    uptake = ProductUptakeRateLaw(
        product="hydrolysate",
        active_biomass="B_active",
        uptake_symbol="q_product",
        assimilation=assimilation,
        rate_units="kilogram / second",
    )
    reaction = Reaction(
        name="assimilable product uptake",
        reactants={"hydrolysate": 1.0},
        products={"B_active": yield_value},
        rate_law=uptake,
        rate_units="kilogram / second",
        assumptions=uptake.assumptions,
        source="Stage 6 product assimilation benchmark.",
        notes="Unassimilated mass is an untracked open-system flux at this stage.",
    )
    return SimulationEngine(
        reactions=[reaction],
        parameters=parameters,
        species_units={"hydrolysate": "kilogram", "B_active": "kilogram"},
        assumptions=uptake.assumptions,
    )


def test_no_product_means_no_positive_growth() -> None:
    engine = assimilation_engine(
        ProductAssimilation(
            product="hydrolysate",
            assimilable=True,
            source="Artificial Stage 6 assimilation test.",
        )
    )
    result = engine.simulate(
        initial_state={
            "hydrolysate": Q_(0.0, "kilogram"),
            "B_active": Q_(1.0, "kilogram"),
        },
        t_span=(Q_(0.0, "second"), Q_(10.0, "second")),
    )

    assert result.success
    assert result.species["B_active"].magnitude[-1] == pytest.approx(
        result.species["B_active"].magnitude[0]
    )


def test_non_assimilable_product_cannot_support_growth() -> None:
    engine = assimilation_engine(
        ProductAssimilation(
            product="hydrolysate",
            assimilable=False,
            source="Artificial Stage 6 non-assimilation test.",
        )
    )
    result = engine.simulate(
        initial_state={
            "hydrolysate": Q_(1.0, "kilogram"),
            "B_active": Q_(1.0, "kilogram"),
        },
        t_span=(Q_(0.0, "second"), Q_(10.0, "second")),
    )

    assert result.success
    assert result.species["B_active"].magnitude[-1] == pytest.approx(
        result.species["B_active"].magnitude[0]
    )
    assert result.species["hydrolysate"].magnitude[-1] == pytest.approx(
        result.species["hydrolysate"].magnitude[0]
    )


def test_assimilable_product_can_support_growth() -> None:
    engine = assimilation_engine(
        ProductAssimilation(
            product="hydrolysate",
            assimilable=True,
            source="Artificial Stage 6 assimilation test.",
        )
    )
    result = engine.simulate(
        initial_state={
            "hydrolysate": Q_(1.0, "kilogram"),
            "B_active": Q_(1.0, "kilogram"),
        },
        t_span=(Q_(0.0, "second"), Q_(0.1, "second")),
        t_eval=Q_(np.linspace(0.0, 0.1, 11), "second"),
    )

    assert result.success
    assert result.species["B_active"].magnitude[-1] > result.species["B_active"].magnitude[0]
    assert result.species["hydrolysate"].magnitude[-1] < result.species["hydrolysate"].magnitude[0]
    assert validate_non_negative(result).passed

