from __future__ import annotations

import numpy as np
import pytest

from fungal_model.chemistry import Reaction
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.fungi.energetics import GibbsEnergyYieldBound, GrowthEnergeticsError
from fungal_model.fungi import (
    EnzymeCapability,
    EnzymeProfile,
    FUNGAL_COUPLING_MATURITY,
    FungalCouplingModel,
    Fungus,
    ProductAssimilation,
    make_fungal_parameter_set,
)


SOURCE = "Artificial coupled fungal benchmark; no organism or physical claim."


def test_coupled_model_runs_secretion_degradation_uptake_growth_and_losses() -> None:
    model = _model()
    result = model.build_engine().simulate(
        initial_state={
            "substrate": Q_(1.0, "kilogram"),
            "product": Q_(0.0, "kilogram"),
            "enzyme": Q_(0.02, "mole / liter"),
            "active_biomass": Q_(0.1, "kilogram"),
            "inactive_biomass": Q_(0.0, "kilogram"),
        },
        t_span=(Q_(0.0, "second"), Q_(20.0, "second")),
        t_eval=Q_(np.linspace(0.0, 20.0, 41), "second"),
    )

    assert result.success
    final = result.final_state()
    assert final["substrate"].magnitude < 1.0
    assert final["product"].magnitude > 0.0
    assert final["active_biomass"].magnitude > 0.1
    assert final["enzyme"].magnitude > 0.0
    assert {reaction.name for reaction in result.reactions} == {
        "artificial extracellular depolymerization",
        "fungal extracellular enzyme secretion",
        "extracellular enzyme decay",
        "enzyme secretion active biomass cost",
        "assimilable degradation-product uptake",
        "active biomass maintenance loss",
    }
    assert model.to_dict()["maturity"] == FUNGAL_COUPLING_MATURITY
    assert "no intracellular metabolism" in str(model.to_dict()["limitations"])


def test_no_active_biomass_means_no_secretion_uptake_or_growth() -> None:
    result = _model().build_engine().simulate(
        initial_state={
            "substrate": Q_(1.0, "kilogram"),
            "product": Q_(0.2, "kilogram"),
            "enzyme": Q_(0.0, "mole / liter"),
            "active_biomass": Q_(0.0, "kilogram"),
            "inactive_biomass": Q_(0.0, "kilogram"),
        },
        t_span=(Q_(0.0, "second"), Q_(10.0, "second")),
    )

    final = result.final_state()
    assert final["substrate"].magnitude == pytest.approx(1.0)
    assert final["product"].magnitude == pytest.approx(0.2)
    assert final["enzyme"].magnitude == pytest.approx(0.0)
    assert final["active_biomass"].magnitude == pytest.approx(0.0)


def test_coupling_fails_without_matching_enzyme_capability() -> None:
    model = _model(enzyme_class="unsupported enzyme")

    with pytest.raises(ValueError, match="matching extracellular enzyme capability"):
        model.validate()


def test_coupling_fails_for_explicitly_nonassimilable_product() -> None:
    model = _model(assimilable=False)

    with pytest.raises(ValueError, match="explicitly non-assimilable"):
        model.validate()


def test_coupling_rejects_parameter_overlap_and_unsupported_maturity() -> None:
    overlap = ParameterSet([_parameter("duplicate alpha", "alpha_E", 1.0, "mole / liter / kilogram / second")])
    with pytest.raises(ValueError, match="overlap"):
        _model(additional_parameters=overlap).parameters
    with pytest.raises(ValueError, match="maturity"):
        _model(maturity="validated")


def _model(
    *,
    enzyme_class: str = "artificial hydrolase",
    assimilable: bool = True,
    additional_parameters: ParameterSet | None = None,
    maturity: str = FUNGAL_COUPLING_MATURITY,
    yield_bound: GibbsEnergyYieldBound | None = None,
) -> FungalCouplingModel:
    def degradation_rate(state, time, parameters):
        del time
        return (
            parameters.require_quantity("k_deg", "liter / mole / second")
            * state["substrate"]
            * state["enzyme"]
        )

    degradation = Reaction(
        name="artificial extracellular depolymerization",
        reactants={"substrate": 1.0},
        products={"product": 1.0},
        rate_law=degradation_rate,
        rate_units="kilogram / second",
        source=SOURCE,
    )
    return FungalCouplingModel(
        fungus=_fungus(assimilable=assimilable),
        degradation_reactions=(degradation,),
        additional_parameters=additional_parameters
        or ParameterSet([_parameter("degradation coefficient", "k_deg", 0.5, "liter / mole / second")]),
        substrate_state="substrate",
        product_state="product",
        enzyme_state="enzyme",
        active_biomass_state="active_biomass",
        inactive_biomass_state="inactive_biomass",
        substrate_name="artificial polymer",
        product_name="artificial assimilable product",
        target_bond_type="artificial bond",
        enzyme_class=enzyme_class,
        coupling_source=SOURCE,
        maturity=maturity,
        yield_bound=yield_bound,
    )


def _fungus(*, assimilable: bool) -> Fungus:
    profile = EnzymeProfile(
        capabilities=(
            EnzymeCapability(
                name="artificial extracellular enzyme",
                enzyme_class="artificial hydrolase",
                target_substrate="artificial polymer",
                target_bond_type="artificial bond",
                evidence="Defined software benchmark capability.",
                source=SOURCE,
            ),
        ),
        source=SOURCE,
    )
    return Fungus(
        species_name="Artificial benchmark fungus",
        enzyme_profile=profile,
        parameters=make_fungal_parameter_set(
            [
                _parameter("minimum temperature", "T_growth_min", 290.0, "kelvin"),
                _parameter("maximum temperature", "T_growth_max", 320.0, "kelvin"),
                _parameter("minimum pH", "pH_growth_min", 4.0, "dimensionless"),
                _parameter("maximum pH", "pH_growth_max", 8.0, "dimensionless"),
                _parameter("minimum water activity", "a_w_min", 0.9, "dimensionless"),
                _parameter(
                    "secretion coefficient",
                    "alpha_E",
                    1.0e-4,
                    "mole / liter / kilogram / second",
                ),
                _parameter("enzyme decay", "delta_E", 0.01, "1 / second"),
                _parameter("secretion cost", "c_E", 0.0, "kilogram / (mole / liter)"),
                _parameter("maintenance", "m_B", 0.0, "1 / second"),
                _parameter("product uptake", "q_product", 0.5, "1 / kilogram / second"),
                _parameter("biomass yield", "Y_B", 0.5, "dimensionless"),
            ]
        ),
        known_substrates=("artificial polymer",),
        uptake_capabilities=(
            ProductAssimilation(
                product="artificial assimilable product",
                assimilable=assimilable,
                source=SOURCE,
            ),
        ),
        notes="Artificial software benchmark only.",
        references=(SOURCE,),
    )


def _parameter(name: str, symbol: str, value: float, units: str) -> Parameter:
    return Parameter(
        name=name,
        symbol=symbol,
        value=value,
        units=units,
        uncertainty=0.0,
        source=SOURCE,
        confidence_level="testing",
        notes="Artificial software benchmark value.",
        measurement_method="definition",
    )


# --------------------------------------------------------------------------
# Thermodynamic yield ceiling
# --------------------------------------------------------------------------


def _yield_bound(*, catabolic: float, anabolic: float) -> GibbsEnergyYieldBound:
    return GibbsEnergyYieldBound(
        catabolic_delta_gibbs=_parameter("catabolic Gibbs energy", "dG_cat", catabolic, "joule / kilogram"),
        anabolic_delta_gibbs=_parameter("anabolic Gibbs energy", "dG_ana", anabolic, "joule / kilogram"),
    )


def test_coupling_without_a_yield_bound_is_unconstrained() -> None:
    """The bound is opt-in, so existing configurations keep working."""

    model = _model()

    assert model.yield_bound is None
    assert model.validate_yield_energetics() is None
    model.validate()
    assert model.to_dict()["yield_bound"] is None


def test_coupling_accepts_a_yield_within_its_thermodynamic_ceiling() -> None:
    # The fixture declares Y_B = 0.5; a ceiling of 2.0 admits it.
    model = _model(yield_bound=_yield_bound(catabolic=-1.2e7, anabolic=6.0e6))

    result = model.validate_yield_energetics()

    assert result is not None and result.passed
    model.validate()
    assert model.to_dict()["yield_bound"]["maximum_yield"] == pytest.approx(2.0)


def test_coupling_rejects_a_yield_that_would_create_free_energy() -> None:
    """A configured yield above the ceiling must fail before the model can run."""

    # Ceiling of 0.25 against the fixture's declared Y_B = 0.5.
    model = _model(yield_bound=_yield_bound(catabolic=-1.5e6, anabolic=6.0e6))

    with pytest.raises(GrowthEnergeticsError, match="create free energy"):
        model.validate()
    with pytest.raises(GrowthEnergeticsError):
        model.reactions()
