from __future__ import annotations

import numpy as np
import pytest

from fungal_model.chemistry.reactions import Reaction
from fungal_model.core.assumptions import Assumption
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.provenance import ProvenanceError
from fungal_model.core.simulation import SimulationEngine
from fungal_model.core.units import Q_, UnitError


def build_first_order_engine(*, sourced_reaction: bool = True) -> SimulationEngine:
    parameters = ParameterSet(
        [
            Parameter(
                name="first-order benchmark rate constant",
                symbol="k",
                value=0.1,
                units="1 / second",
                uncertainty=0.0,
                source="Analytical software benchmark; no physical claim.",
                confidence_level="testing",
                notes="Tests generic ODE integration.",
                measurement_method="defined benchmark value",
            )
        ]
    )
    assumption = Assumption(
        name="well-mixed first-order benchmark",
        description="A converts to B with rate k[A] in a closed well-mixed system.",
        justification="Minimal benchmark for ODE integration and mass conservation.",
        known_limitations="Not a fungal, PET, or enzyme mechanism.",
        source="Derived from canonical first-order kinetics.",
    )

    def rate_law(state, time, parameter_set):
        del time
        return parameter_set.require_quantity("k", "1 / second") * state["A"]

    reaction = Reaction(
        name="A to B",
        reactants={"A": 1},
        products={"B": 1},
        rate_law=rate_law,
        rate_units="mole / liter / second",
        assumptions=[] if not sourced_reaction else [assumption],
        source="Canonical first-order reaction benchmark." if sourced_reaction else None,
    )
    return SimulationEngine(
        reactions=[reaction],
        parameters=parameters,
        species_units={"A": "mole / liter", "B": "mole / liter"},
        assumptions=[assumption],
    )


def test_first_order_engine_runs_with_units() -> None:
    engine = build_first_order_engine()
    result = engine.simulate(
        initial_state={"A": Q_(1.0, "mole / liter"), "B": Q_(0.0, "mole / liter")},
        t_span=(Q_(0, "second"), Q_(10, "second")),
        t_eval=Q_(np.linspace(0, 10, 21), "second"),
    )

    assert result.success
    assert result.species["A"].magnitude[-1] < result.species["A"].magnitude[0]
    assert result.species["B"].magnitude[-1] > result.species["B"].magnitude[0]


def test_initial_state_requires_units() -> None:
    engine = build_first_order_engine()

    with pytest.raises(UnitError):
        engine.simulate(
            initial_state={"A": 1.0, "B": Q_(0.0, "mole / liter")},
            t_span=(Q_(0, "second"), Q_(1, "second")),
        )


def test_reaction_requires_provenance_before_scientific_run() -> None:
    engine = build_first_order_engine(sourced_reaction=False)

    with pytest.raises(ProvenanceError):
        engine.simulate(
            initial_state={"A": Q_(1.0, "mole / liter"), "B": Q_(0.0, "mole / liter")},
            t_span=(Q_(0, "second"), Q_(1, "second")),
        )

