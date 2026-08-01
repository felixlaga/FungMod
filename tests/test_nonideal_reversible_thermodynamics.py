from __future__ import annotations

import numpy as np
import pytest

from fungal_model.chemistry import (
    DETAILED_BALANCE_RATE_RATIO_SOURCE,
    IUPAC_ACTIVITY_COEFFICIENT_SOURCE,
    DynamicActivityParticipant,
    ExplicitActivityCoefficient,
    NonidealReversibleThermodynamics,
    Reaction,
    ReversibleThermodynamicRateLaw,
)
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.simulation import SimulationEngine
from fungal_model.core.units import Q_


SOURCE = f"{IUPAC_ACTIVITY_COEFFICIENT_SOURCE}; {DETAILED_BALANCE_RATE_RATIO_SOURCE}"


def test_explicit_nonideal_coefficients_shift_gibbs_by_rt_log_gamma_ratio() -> None:
    ideal = _thermodynamics(gamma_a=1.0, gamma_b=1.0)
    nonideal = _thermodynamics(gamma_a=2.0, gamma_b=0.5)
    state = {"A": Q_(1.0, "mole / liter"), "B": Q_(1.0, "mole / liter")}

    ideal_result = ideal.evaluate(state)
    result = nonideal.evaluate(state)
    rt = 8.31446261815324 * 298.15

    assert ideal_result.delta_gibbs == pytest.approx(0.0, abs=1e-12)
    assert result.delta_gibbs == pytest.approx(rt * np.log(0.25))
    assert result.activities == pytest.approx({"A": 2.0, "B": 0.5})
    assert result.direction == "forward"


def test_local_detailed_balance_is_zero_at_nonideal_equilibrium() -> None:
    thermodynamics = _thermodynamics(gamma_a=2.0, gamma_b=0.5)
    state = {"A": Q_(0.2, "mole / liter"), "B": Q_(0.8, "mole / liter")}

    net, evaluation = thermodynamics.net_rate(Q_(0.3, "mole / liter / second"), state)

    assert evaluation.reaction_quotient == pytest.approx(1.0)
    assert evaluation.reverse_to_forward_ratio == pytest.approx(1.0)
    assert evaluation.direction == "near_equilibrium"
    assert net.magnitude == pytest.approx(0.0, abs=1e-14)


def test_signed_net_rate_changes_direction_on_both_sides_of_equilibrium() -> None:
    thermodynamics = _thermodynamics()
    forward, forward_evaluation = thermodynamics.net_rate(
        Q_(0.5, "mole / liter / second"),
        {"A": Q_(0.8, "mole / liter"), "B": Q_(0.2, "mole / liter")},
    )
    reverse, reverse_evaluation = thermodynamics.net_rate(
        Q_(0.5, "mole / liter / second"),
        {"A": Q_(0.2, "mole / liter"), "B": Q_(0.8, "mole / liter")},
    )

    assert forward.magnitude > 0.0
    assert forward_evaluation.direction == "forward"
    assert reverse.magnitude < 0.0
    assert reverse_evaluation.direction == "reverse"
    assert reverse_evaluation.reverse_rate > reverse_evaluation.forward_rate


def test_reversible_rate_wrapper_relaxes_closed_reaction_to_equilibrium() -> None:
    thermodynamics = _thermodynamics()

    def one_way_rate(state, time, parameters):
        del time
        return parameters.require_quantity("k_forward", "1 / second") * state["A"]

    rate_law = ReversibleThermodynamicRateLaw(one_way_rate, thermodynamics)
    reaction = Reaction(
        name="reversible artificial A to B",
        reactants={"A": 1.0},
        products={"B": 1.0},
        rate_law=rate_law,
        rate_units="mole / liter / second",
        assumptions=list(rate_law.assumptions),
        source=SOURCE,
    )
    engine = SimulationEngine(
        reactions=[reaction],
        parameters=ParameterSet([_parameter("forward rate", "k_forward", 1.0, "1 / second")]),
        species_units={"A": "mole / liter", "B": "mole / liter"},
    )

    result = engine.simulate(
        initial_state={"A": Q_(0.9, "mole / liter"), "B": Q_(0.1, "mole / liter")},
        t_span=(Q_(0.0, "second"), Q_(10.0, "second")),
        t_eval=Q_([0.0, 10.0], "second"),
    )

    final = result.final_state()
    assert result.success
    assert final["A"].magnitude == pytest.approx(0.5, abs=2e-8)
    assert final["B"].magnitude == pytest.approx(0.5, abs=2e-8)
    assert final["A"].magnitude + final["B"].magnitude == pytest.approx(1.0)


def test_nonideal_model_fails_on_missing_or_nonpositive_activity_coefficients() -> None:
    missing = _thermodynamics(
        coefficients=(ExplicitActivityCoefficient("A", _parameter("gamma A", "gamma_A", 1.0, "dimensionless")),)
    )
    with pytest.raises(ValueError, match="exactly cover"):
        missing.validate()

    nonpositive = _thermodynamics(gamma_b=0.0)
    with pytest.raises(ValueError, match="finite and positive"):
        nonpositive.validate()


def _thermodynamics(
    *,
    gamma_a: float = 1.0,
    gamma_b: float = 1.0,
    coefficients: tuple[ExplicitActivityCoefficient, ...] | None = None,
) -> NonidealReversibleThermodynamics:
    return NonidealReversibleThermodynamics(
        participants=(
            DynamicActivityParticipant("A", "species_A", -1.0),
            DynamicActivityParticipant("B", "species_B", 1.0),
        ),
        activity_coefficients=coefficients
        or (
            ExplicitActivityCoefficient("A", _parameter("gamma A", "gamma_A", gamma_a, "dimensionless")),
            ExplicitActivityCoefficient("B", _parameter("gamma B", "gamma_B", gamma_b, "dimensionless")),
        ),
        standard_delta_gibbs=_parameter("standard Gibbs energy", "delta_g_0", 0.0, "joule / mole"),
        temperature=_parameter("temperature", "T", 298.15, "kelvin"),
        gas_constant=_parameter(
            "molar gas constant",
            "R",
            8.31446261815324,
            "joule / mole / kelvin",
        ),
        standard_concentration=_parameter(
            "standard concentration",
            "c_standard",
            1.0,
            "mole / liter",
        ),
        minimum_activity=_parameter("activity floor", "a_min", 1.0e-12, "dimensionless"),
        equilibrium_tolerance=_parameter(
            "equilibrium energy tolerance",
            "delta_g_tolerance",
            1.0e-9,
            "joule / mole",
        ),
        source=SOURCE,
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
        notes="Artificial thermodynamic software benchmark value.",
        measurement_method="definition",
    )
