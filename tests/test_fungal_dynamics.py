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



# --------------------------------------------------------------------------
# WP7: dissipation yield, carbon-limited Gibbs bound, yield caps dropped
# --------------------------------------------------------------------------

from fungal_model.chemistry import ElementalComposition, MacrochemicalBalance, MacrochemicalSpecies  # noqa: E402
from fungal_model.fungi.energetics import (  # noqa: E402
    HEIJNEN_DISSIPATION_MATURITY,
    HEIJNEN_DISSIPATION_SOURCE,
    DissipationYieldPrediction,
    GibbsEnergyYieldBound,
    GrowthEnergeticsError,
    heijnen_dissipation_from_composition,
    heijnen_dissipation_per_cmol_biomass,
)

ILLUSTRATIVE_SOURCE = (
    "Illustrative pH-7 formation energies from the 2026-10 macrochemistry audit record "
    "(scratch values for a software test; not registry data and not a physical claim)."
)
ILLUSTRATIVE_CONDITIONS = "pH 7, 298 K, unit activities; illustrative audit values."
# Glucose, NH4+, O2, HCO3-, H2O, H+, biomass CH1.8O0.5N0.2 in kJ/mol (audit report section 2.6).
ILLUSTRATIVE_GIBBS = {
    "glucose": -917.2,
    "ammonium": -79.4,
    "oxygen": 0.0,
    "bicarbonate": -586.8,
    "water": -237.2,
    "proton": -39.9,
    "biomass": -67.0,
}


def _energy(symbol: str, kilojoule_per_mole: float, *, source: str | None = ILLUSTRATIVE_SOURCE) -> Parameter:
    return Parameter(
        name=symbol,
        symbol=symbol,
        value=kilojoule_per_mole,
        units="kilojoule / mole",
        uncertainty=None,
        source=source,
        confidence_level="testing",
        notes="Illustrative value for a software test.",
    )


def _composition(formula: str | dict[str, float]) -> ElementalComposition:
    if isinstance(formula, str):
        return ElementalComposition.from_formula(formula, source=ILLUSTRATIVE_SOURCE)
    return ElementalComposition.from_elements(formula, source=ILLUSTRATIVE_SOURCE, formula="CH1.8O0.5N0.2")


def _aerobic_glucose_balance() -> MacrochemicalBalance:
    formulas: dict[str, tuple[str | dict[str, float], float]] = {
        "glucose": ("C6H12O6", 0.0),
        "ammonium": ("NH4", 1.0),
        "oxygen": ("O2", 0.0),
        "bicarbonate": ("HCO3", -1.0),
        "water": ("H2O", 0.0),
        "proton": ("H", 1.0),
        "biomass": ({"C": 1.0, "H": 1.8, "O": 0.5, "N": 0.2}, 0.0),
    }
    return MacrochemicalBalance(
        name="aerobic glucose growth on ammonium",
        species=tuple(
            MacrochemicalSpecies(
                name=name,
                composition=_composition(formula),
                charge=charge,
                charge_source=ILLUSTRATIVE_SOURCE,
                formation_gibbs=_energy(f"delta_f_G_{name}", ILLUSTRATIVE_GIBBS[name]),
            )
            for name, (formula, charge) in formulas.items()
        ),
        source=ILLUSTRATIVE_SOURCE,
        thermodynamic_conditions=ILLUSTRATIVE_CONDITIONS,
    )


def test_heijnen_dissipation_for_glucose_is_236_kilojoule_per_cmol() -> None:
    dissipation = heijnen_dissipation_per_cmol_biomass(carbon_atoms=6.0, degree_of_reduction_per_carbon=4.0)

    assert dissipation.quantity.to("kilojoule / mole").magnitude == pytest.approx(236.0, abs=1.0)
    assert dissipation.source == HEIJNEN_DISSIPATION_SOURCE
    assert dissipation.validity_range is not None and "1 to 6 carbon atoms" in dissipation.validity_range
    from_composition = heijnen_dissipation_from_composition(_composition("C6H12O6"), 0.0)
    assert from_composition.quantity.magnitude == pytest.approx(dissipation.quantity.magnitude)


def test_heijnen_dissipation_refuses_inputs_outside_the_transcribed_domain() -> None:
    with pytest.raises(GrowthEnergeticsError, match="carbon_atoms 7.0 is outside"):
        heijnen_dissipation_per_cmol_biomass(carbon_atoms=7.0, degree_of_reduction_per_carbon=4.0)
    with pytest.raises(GrowthEnergeticsError, match="degree_of_reduction_per_carbon 8.5 is outside"):
        heijnen_dissipation_per_cmol_biomass(carbon_atoms=1.0, degree_of_reduction_per_carbon=8.5)
    with pytest.raises(GrowthEnergeticsError, match="no carbon"):
        heijnen_dissipation_from_composition(_composition("NH4"), 1.0)


def test_dissipation_yield_prediction_reproduces_the_audit_value() -> None:
    balance = _aerobic_glucose_balance()
    prediction = DissipationYieldPrediction.predict(
        balance,
        biomass_species="biomass",
        substrate_species="glucose",
        dissipation_per_cmol_biomass=heijnen_dissipation_from_composition(_composition("C6H12O6"), 0.0),
        oxygen_species="oxygen",
    )

    assert prediction.yield_per_carbon == pytest.approx(0.669, rel=0.01)
    assert prediction.yield_per_substrate == pytest.approx(6.0 * prediction.yield_per_carbon)
    assert prediction.carbon_ceiling_per_substrate == pytest.approx(6.0)
    assert prediction.oxygen_per_cmol_biomass == pytest.approx(-0.446, abs=0.002)
    assert prediction.solution.reaction_gibbs().to("kilojoule / mole").magnitude == pytest.approx(-236.05, abs=0.05)
    assert prediction.solution.coefficients["biomass"] == 1.0

    data = prediction.to_dict()
    assert data["maturity"] == HEIJNEN_DISSIPATION_MATURITY
    assert data["assumptions"][0]["name"] == "heijnen_van_dijken_dissipation_correlation"
    assert data["yield_per_carbon_units"] == "C-mol biomass / C-mol substrate"
    assert "No rate" in data["limitations"]


def test_dissipation_yield_prediction_refuses_bad_inputs() -> None:
    balance = _aerobic_glucose_balance()
    dissipation = heijnen_dissipation_from_composition(_composition("C6H12O6"), 0.0)

    with pytest.raises(GrowthEnergeticsError, match="substrate_species 'ethanol' is not in balance"):
        DissipationYieldPrediction.predict(
            balance, biomass_species="biomass", substrate_species="ethanol", dissipation_per_cmol_biomass=dissipation
        )
    with pytest.raises(GrowthEnergeticsError, match="must differ"):
        DissipationYieldPrediction.predict(
            balance, biomass_species="glucose", substrate_species="glucose", dissipation_per_cmol_biomass=dissipation
        )
    with pytest.raises(GrowthEnergeticsError, match="finite and positive"):
        DissipationYieldPrediction.predict(
            balance,
            biomass_species="biomass",
            substrate_species="glucose",
            dissipation_per_cmol_biomass=_energy("D_e", -236.0),
        )
    with pytest.raises(GrowthEnergeticsError, match="Both biomass and substrate must contain carbon"):
        DissipationYieldPrediction.predict(
            balance, biomass_species="biomass", substrate_species="ammonium", dissipation_per_cmol_biomass=dissipation
        )


def test_gibbs_yield_bound_with_a_carbon_limit_rejects_three_cmol_per_cmol() -> None:
    bound = GibbsEnergyYieldBound(
        catabolic_delta_gibbs=_energy("dG_cat", -478.0),
        anabolic_delta_gibbs=_energy("dG_an", 100.0),
    )
    declared = Q_(3.0, "dimensionless")

    unconstrained = bound.validate_yield(declared)
    assert unconstrained.passed  # the Gibbs bound alone (4.78) knows nothing about atoms
    assert unconstrained.details["binding_limit"] == "thermodynamic"
    assert unconstrained.details["carbon_limit"] is None

    limited = bound.validate_yield(declared, carbon_limit=Q_(1.0, "dimensionless"))
    assert not limited.passed
    assert limited.details["binding_limit"] == "carbon_conservation"
    assert limited.details["maximum_yield"] == pytest.approx(1.0)
    assert limited.details["thermodynamic_ceiling"] == pytest.approx(4.78)
    assert "create carbon" in limited.message
    with pytest.raises(GrowthEnergeticsError, match="carbon"):
        bound.enforce_yield(declared, carbon_limit=Q_(1.0, "dimensionless"))
    with pytest.raises(GrowthEnergeticsError, match="carbon_limit must be finite and positive"):
        bound.validate_yield(declared, carbon_limit=Q_(0.0, "dimensionless"))
    assert bound.validate_yield(Q_(0.6, "dimensionless"), carbon_limit=Q_(1.0, "dimensionless")).passed


def test_biomass_yield_coefficient_accepts_values_above_one_and_refuses_negative() -> None:
    accepted = biomass_yield_coefficient(
        parameters=ParameterSet([parameter(name="yield", symbol="Y_B", value=1.2, units="dimensionless")]),
        yield_symbol="Y_B",
    )
    assert accepted == pytest.approx(1.2)
    with pytest.raises(ValueError, match="finite and non-negative"):
        biomass_yield_coefficient(
            parameters=ParameterSet([parameter(name="yield", symbol="Y_B", value=-0.1, units="dimensionless")]),
            yield_symbol="Y_B",
        )
