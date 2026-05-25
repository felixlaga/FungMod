from __future__ import annotations

import numpy as np

from fungal_model.core.units import Q_
from fungal_model.core.validators import validate_non_negative
from tests.test_reaction_engine import build_first_order_engine


class FakeResult:
    species = {"A": Q_(np.array([1.0, -0.01]), "mole / liter")}


def test_solver_output_cannot_silently_go_negative() -> None:
    validation = validate_non_negative(FakeResult())

    assert not validation.passed
    assert "A" in validation.details["failures"]


def test_first_order_solution_remains_non_negative() -> None:
    result = build_first_order_engine().simulate(
        initial_state={"A": Q_(1.0, "mole / liter"), "B": Q_(0.0, "mole / liter")},
        t_span=(Q_(0, "second"), Q_(10, "second")),
    )

    validation = validate_non_negative(result)

    assert validation.passed

