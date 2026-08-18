"""Thermodynamic constraints that remove degrees of freedom from fitted models.

These tests pin two claims. Thermodynamics couples kinetic parameters and bounds
biomass yield, so both become constrained rather than free. Thermodynamics does
not supply a rate, so nothing here may be read as predicting one.
"""

from __future__ import annotations

import math

import pytest

from fungal_model.chemistry.haldane import (
    HaldaneError,
    check_haldane_consistency,
    equilibrium_constant_from_gibbs,
    haldane_equilibrium_constant,
    reverse_vmax_from_haldane,
)
from fungal_model.core.parameters import Parameter
from fungal_model.core.provenance import ProvenanceError
from fungal_model.core.units import Q_
from fungal_model.fungi.energetics import GibbsEnergyYieldBound, GrowthEnergeticsError


def _gibbs(symbol: str, value: float, units: str) -> Parameter:
    return Parameter(
        name=f"test {symbol}",
        symbol=symbol,
        value=value,
        units=units,
        uncertainty=None,
        source="Fixture value for a thermodynamic-contract test.",
        confidence_level="exploratory_assumption",
        notes="",
    )


# --------------------------------------------------------------------------
# Haldane relations
# --------------------------------------------------------------------------


def test_equilibrium_constant_matches_the_van_t_hoff_definition() -> None:
    keq = equilibrium_constant_from_gibbs(
        standard_delta_gibbs=Q_(-15000.0, "joule / mole"),
        temperature=Q_(323.15, "kelvin"),
    )

    expected = math.exp(15000.0 / (8.31446261815324 * 323.15))
    assert keq == pytest.approx(expected, rel=1e-12)


def test_zero_gibbs_energy_gives_unit_equilibrium_constant() -> None:
    keq = equilibrium_constant_from_gibbs(
        standard_delta_gibbs=Q_(0.0, "joule / mole"),
        temperature=Q_(298.15, "kelvin"),
    )

    assert keq == pytest.approx(1.0)


def test_endergonic_reaction_gives_equilibrium_constant_below_one() -> None:
    keq = equilibrium_constant_from_gibbs(
        standard_delta_gibbs=Q_(+10000.0, "joule / mole"),
        temperature=Q_(298.15, "kelvin"),
    )

    assert 0.0 < keq < 1.0


def test_haldane_relation_round_trips_through_the_reverse_rate() -> None:
    """The constraint determines the fourth parameter from the other three."""

    keq = equilibrium_constant_from_gibbs(
        standard_delta_gibbs=Q_(-15000.0, "joule / mole"),
        temperature=Q_(323.15, "kelvin"),
    )
    reverse = reverse_vmax_from_haldane(
        equilibrium_constant=keq,
        forward_vmax=Q_(20.0, "millimolar / minute"),
        substrate_km=Q_(43.0, "millimolar"),
        product_km=Q_(34.0, "millimolar"),
    )
    recovered = haldane_equilibrium_constant(
        forward_vmax=Q_(20.0, "millimolar / minute"),
        reverse_vmax=reverse,
        substrate_km=Q_(43.0, "millimolar"),
        product_km=Q_(34.0, "millimolar"),
    )

    assert recovered == pytest.approx(keq, rel=1e-12)


def test_consistent_parameter_set_passes_the_haldane_check() -> None:
    keq = equilibrium_constant_from_gibbs(
        standard_delta_gibbs=Q_(-15000.0, "joule / mole"),
        temperature=Q_(323.15, "kelvin"),
    )
    reverse = reverse_vmax_from_haldane(
        equilibrium_constant=keq,
        forward_vmax=Q_(20.0, "millimolar / minute"),
        substrate_km=Q_(43.0, "millimolar"),
        product_km=Q_(34.0, "millimolar"),
    )

    result = check_haldane_consistency(
        forward_vmax=Q_(20.0, "millimolar / minute"),
        reverse_vmax=reverse,
        substrate_km=Q_(43.0, "millimolar"),
        product_km=Q_(34.0, "millimolar"),
        standard_delta_gibbs=Q_(-15000.0, "joule / mole"),
        temperature=Q_(323.15, "kelvin"),
    )

    assert result.passed
    assert result.details["relative_error"] == pytest.approx(0.0, abs=1e-12)


def test_thermodynamically_impossible_parameter_set_is_rejected() -> None:
    """A parameter set no enzyme could have must fail, however well it fits."""

    result = check_haldane_consistency(
        forward_vmax=Q_(20.0, "millimolar / minute"),
        reverse_vmax=Q_(20.0, "millimolar / minute"),  # implies K_eq near 1
        substrate_km=Q_(43.0, "millimolar"),
        product_km=Q_(34.0, "millimolar"),
        standard_delta_gibbs=Q_(-15000.0, "joule / mole"),  # implies K_eq near 266
        temperature=Q_(323.15, "kelvin"),
    )

    assert not result.passed
    assert result.details["equilibrium_constant_from_gibbs"] > 100.0
    assert result.details["equilibrium_constant_from_kinetics"] < 2.0
    assert "thermodynamically inconsistent" in result.message


def test_haldane_rejects_nonpositive_and_unitless_inputs() -> None:
    with pytest.raises(HaldaneError):
        haldane_equilibrium_constant(
            forward_vmax=Q_(0.0, "millimolar / minute"),
            reverse_vmax=Q_(1.0, "millimolar / minute"),
            substrate_km=Q_(43.0, "millimolar"),
            product_km=Q_(34.0, "millimolar"),
        )
    with pytest.raises(HaldaneError):
        reverse_vmax_from_haldane(
            equilibrium_constant=0.0,
            forward_vmax=Q_(20.0, "millimolar / minute"),
            substrate_km=Q_(43.0, "millimolar"),
            product_km=Q_(34.0, "millimolar"),
        )
    with pytest.raises(HaldaneError):
        equilibrium_constant_from_gibbs(
            standard_delta_gibbs=Q_(-1000.0, "joule / mole"),
            temperature=Q_(0.0, "kelvin"),
        )


def test_haldane_does_not_predict_an_absolute_rate() -> None:
    """Two enzymes sharing a reaction share K_eq exactly and may differ in rate.

    This is the structural reason thermodynamics cannot supply a turnover
    number: K_eq is a property of the reaction, V_max of the catalyst.
    """

    gibbs = Q_(-15000.0, "joule / mole")
    temperature = Q_(323.15, "kelvin")
    keq = equilibrium_constant_from_gibbs(standard_delta_gibbs=gibbs, temperature=temperature)

    slow_reverse = reverse_vmax_from_haldane(
        equilibrium_constant=keq,
        forward_vmax=Q_(150.8, "millimolar / hour"),   # Bgl6 wild type
        substrate_km=Q_(6.244, "millimolar"),
        product_km=Q_(34.66, "millimolar"),
    )
    fast_reverse = reverse_vmax_from_haldane(
        equilibrium_constant=keq,
        forward_vmax=Q_(1413.0, "millimolar / hour"),  # mutant M3
        substrate_km=Q_(6.244, "millimolar"),
        product_km=Q_(34.66, "millimolar"),
    )

    # Both parameter sets are thermodynamically admissible at the same K_eq,
    # while their maximal rates differ by roughly an order of magnitude.
    for reverse, forward in ((slow_reverse, 150.8), (fast_reverse, 1413.0)):
        recovered = haldane_equilibrium_constant(
            forward_vmax=Q_(forward, "millimolar / hour"),
            reverse_vmax=reverse,
            substrate_km=Q_(6.244, "millimolar"),
            product_km=Q_(34.66, "millimolar"),
        )
        assert recovered == pytest.approx(keq, rel=1e-12)
    ratio = float(fast_reverse.magnitude) / float(slow_reverse.magnitude)
    assert ratio == pytest.approx(1413.0 / 150.8, rel=1e-9)


# --------------------------------------------------------------------------
# Gibbs-energy yield bound
# --------------------------------------------------------------------------


def test_yield_ceiling_is_the_ratio_of_gibbs_energies() -> None:
    bound = GibbsEnergyYieldBound(
        catabolic_delta_gibbs=_gibbs("dG_cat", -1.56e7, "joule / kilogram"),
        anabolic_delta_gibbs=_gibbs("dG_ana", 6.0e6, "joule / kilogram"),
    )

    assert float(bound.maximum_yield().magnitude) == pytest.approx(1.56e7 / 6.0e6)


def test_yield_below_the_ceiling_passes_and_above_it_is_rejected() -> None:
    bound = GibbsEnergyYieldBound(
        catabolic_delta_gibbs=_gibbs("dG_cat", -1.56e7, "joule / kilogram"),
        anabolic_delta_gibbs=_gibbs("dG_ana", 6.0e6, "joule / kilogram"),
    )

    ok = bound.validate_yield(Q_(0.4, "dimensionless"))
    assert ok.passed
    assert ok.details["fraction_of_ceiling"] < 1.0

    bad = bound.validate_yield(Q_(3.0, "dimensionless"))
    assert not bad.passed
    assert "create free energy" in bad.message
    with pytest.raises(GrowthEnergeticsError):
        bound.enforce_yield(Q_(3.0, "dimensionless"))


def test_yield_bound_requires_exergonic_catabolism_and_endergonic_anabolism() -> None:
    with pytest.raises(GrowthEnergeticsError):
        GibbsEnergyYieldBound(
            catabolic_delta_gibbs=_gibbs("dG_cat", +1.0e6, "joule / kilogram"),
            anabolic_delta_gibbs=_gibbs("dG_ana", 6.0e6, "joule / kilogram"),
        )
    with pytest.raises(GrowthEnergeticsError):
        GibbsEnergyYieldBound(
            catabolic_delta_gibbs=_gibbs("dG_cat", -1.0e6, "joule / kilogram"),
            anabolic_delta_gibbs=_gibbs("dG_ana", -6.0e6, "joule / kilogram"),
        )


def test_yield_bound_refuses_unsourced_gibbs_energies() -> None:
    """The bound constrains a parameter; it must never invent an energy value."""

    unsourced = Parameter(
        name="unsourced catabolic energy",
        symbol="dG_cat",
        value=-1.0e7,
        units="joule / kilogram",
        uncertainty=None,
        source=None,
        confidence_level="exploratory_assumption",
        notes="",
    )
    with pytest.raises(ProvenanceError):
        GibbsEnergyYieldBound(
            catabolic_delta_gibbs=unsourced,
            anabolic_delta_gibbs=_gibbs("dG_ana", 6.0e6, "joule / kilogram"),
        )


def test_yield_bound_reports_its_claim_boundary() -> None:
    bound = GibbsEnergyYieldBound(
        catabolic_delta_gibbs=_gibbs("dG_cat", -1.56e7, "joule / kilogram"),
        anabolic_delta_gibbs=_gibbs("dG_ana", 6.0e6, "joule / kilogram"),
    )
    data = bound.to_dict()

    assert "does not predict a reaction rate" in data["claim_boundary"]
    assert data["maximum_yield"] > 0.0
