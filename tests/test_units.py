from __future__ import annotations

import pytest

from fungal_model.chemistry.reactions import Reaction
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_, UnitError, assert_compatible


def test_incompatible_units_fail() -> None:
    with pytest.raises(UnitError):
        assert_compatible(Q_(1, "meter"), "second")


def test_compatible_units_pass() -> None:
    converted = assert_compatible(Q_(1000, "millimole / liter"), "mole / liter")

    assert converted.magnitude == pytest.approx(1.0)


def test_rate_law_returns_correct_dimensions() -> None:
    parameters = ParameterSet(
        [
            Parameter(
                name="benchmark rate constant",
                symbol="k",
                value=0.2,
                units="1 / second",
                uncertainty=0.0,
                source="Analytical software benchmark; no physical claim.",
                confidence_level="testing",
                notes="Used only for dimensional tests.",
                measurement_method="defined benchmark value",
            )
        ]
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
        source="Analytical first-order benchmark.",
    )
    rate = reaction.rate({"A": Q_(2.0, "mole / liter")}, Q_(0, "second"), parameters)

    assert rate.to("mole / liter / second").magnitude == pytest.approx(0.4)

