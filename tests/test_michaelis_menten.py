from __future__ import annotations

import numpy as np
import pytest

from fungal_model.chemistry.reactions import Reaction
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.simulation import SimulationEngine
from fungal_model.core.units import Q_, UnitError
from fungal_model.core.validators import validate_mass_balance, validate_non_negative
from fungal_model.kinetics.michaelis_menten import (
    EnzymeExplicitMichaelisMentenRateLaw,
    MichaelisMentenRateLaw,
    enzyme_explicit_michaelis_menten_rate,
    homogeneous_michaelis_menten_assumption,
    michaelis_menten_rate,
)


def benchmark_parameters() -> ParameterSet:
    return ParameterSet(
        [
            Parameter(
                name="benchmark Michaelis constant",
                symbol="Km",
                value=1.0,
                units="mole / liter",
                uncertainty=0.0,
                source="Artificial Stage 2 benchmark value; no physical claim.",
                confidence_level="testing",
                notes="Used to test homogeneous Michaelis-Menten limiting behavior.",
                measurement_method="defined benchmark value",
            ),
            Parameter(
                name="benchmark maximum rate",
                symbol="Vmax",
                value=10.0,
                units="mole / liter / second",
                uncertainty=0.0,
                source="Artificial Stage 2 benchmark value; no physical claim.",
                confidence_level="testing",
                notes="Used to test homogeneous Michaelis-Menten limiting behavior.",
                measurement_method="defined benchmark value",
            ),
            Parameter(
                name="benchmark catalytic turnover",
                symbol="kcat",
                value=5.0,
                units="1 / second",
                uncertainty=0.0,
                source="Artificial Stage 2 benchmark value; no physical claim.",
                confidence_level="testing",
                notes="Used to test enzyme-explicit Michaelis-Menten behavior.",
                measurement_method="defined benchmark value",
            ),
        ]
    )


def test_low_substrate_limit_is_approximately_first_order() -> None:
    rate = michaelis_menten_rate(
        substrate=Q_(1e-6, "mole / liter"),
        vmax=Q_(10.0, "mole / liter / second"),
        km=Q_(1.0, "mole / liter"),
        rate_units="mole / liter / second",
    )
    first_order_limit = Q_(10.0, "1 / second") * Q_(1e-6, "mole / liter")

    assert rate.to("mole / liter / second").magnitude == pytest.approx(
        first_order_limit.to("mole / liter / second").magnitude,
        rel=1e-5,
    )


def test_high_substrate_limit_approaches_vmax() -> None:
    rate = michaelis_menten_rate(
        substrate=Q_(1e6, "mole / liter"),
        vmax=Q_(10.0, "mole / liter / second"),
        km=Q_(1.0, "mole / liter"),
        rate_units="mole / liter / second",
    )

    assert rate.to("mole / liter / second").magnitude == pytest.approx(10.0, rel=1e-5)


def test_zero_substrate_gives_zero_rate() -> None:
    rate = michaelis_menten_rate(
        substrate=Q_(0.0, "mole / liter"),
        vmax=Q_(10.0, "mole / liter / second"),
        km=Q_(1.0, "mole / liter"),
        rate_units="mole / liter / second",
    )

    assert rate.to("mole / liter / second").magnitude == pytest.approx(0.0)


def test_zero_enzyme_gives_zero_rate() -> None:
    rate = enzyme_explicit_michaelis_menten_rate(
        substrate=Q_(1.0, "mole / liter"),
        enzyme=Q_(0.0, "mole / liter"),
        kcat=Q_(5.0, "1 / second"),
        km=Q_(1.0, "mole / liter"),
        rate_units="mole / liter / second",
    )

    assert rate.to("mole / liter / second").magnitude == pytest.approx(0.0)


def test_rate_law_units_are_checked() -> None:
    with pytest.raises(UnitError):
        michaelis_menten_rate(
            substrate=Q_(1.0, "mole / liter"),
            vmax=Q_(10.0, "mole / liter / second"),
            km=Q_(1.0, "second"),
            rate_units="mole / liter / second",
        )


def test_negative_substrate_is_rejected() -> None:
    with pytest.raises(ValueError):
        michaelis_menten_rate(
            substrate=Q_(-1.0, "mole / liter"),
            vmax=Q_(10.0, "mole / liter / second"),
            km=Q_(1.0, "mole / liter"),
            rate_units="mole / liter / second",
        )


def test_homogeneous_rate_law_can_drive_reaction_engine() -> None:
    rate_law = MichaelisMentenRateLaw(
        substrate="S",
        vmax_symbol="Vmax",
        km_symbol="Km",
        rate_units="mole / liter / second",
        substrate_units="mole / liter",
    )
    reaction = Reaction(
        name="dissolved toy substrate to product",
        reactants={"S": 1.0},
        products={"P": 1.0},
        rate_law=rate_law,
        rate_units="mole / liter / second",
        assumptions=rate_law.assumptions,
        source="Canonical Michaelis-Menten benchmark reaction.",
    )
    engine = SimulationEngine(
        reactions=[reaction],
        parameters=benchmark_parameters(),
        species_units={"S": "mole / liter", "P": "mole / liter"},
        assumptions=[homogeneous_michaelis_menten_assumption()],
    )

    result = engine.simulate(
        initial_state={"S": Q_(2.0, "mole / liter"), "P": Q_(0.0, "mole / liter")},
        t_span=(Q_(0.0, "second"), Q_(0.1, "second")),
        t_eval=Q_(np.linspace(0.0, 0.1, 11), "second"),
    )

    assert result.success
    assert validate_non_negative(result).passed
    assert validate_mass_balance(result, conserved_weights={"S": 1.0, "P": 1.0}).passed
    assert result.species["S"].magnitude[-1] < result.species["S"].magnitude[0]
    assert result.species["P"].magnitude[-1] > result.species["P"].magnitude[0]


def test_enzyme_explicit_rate_law_uses_enzyme_state() -> None:
    rate_law = EnzymeExplicitMichaelisMentenRateLaw(
        substrate="S",
        enzyme="E",
        kcat_symbol="kcat",
        km_symbol="Km",
        rate_units="mole / liter / second",
        substrate_units="mole / liter",
        enzyme_units="mole / liter",
    )
    rate = rate_law(
        {"S": Q_(1.0, "mole / liter"), "E": Q_(2.0, "mole / liter")},
        Q_(0.0, "second"),
        benchmark_parameters(),
    )

    assert rate.to("mole / liter / second").magnitude == pytest.approx(5.0)

