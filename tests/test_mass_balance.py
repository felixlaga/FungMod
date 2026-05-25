from __future__ import annotations

import numpy as np

from fungal_model.core.units import Q_
from fungal_model.core.validators import validate_mass_balance
from tests.test_reaction_engine import build_first_order_engine


def test_closed_toy_reaction_conserves_mass() -> None:
    result = build_first_order_engine().simulate(
        initial_state={"A": Q_(1.0, "mole / liter"), "B": Q_(0.0, "mole / liter")},
        t_span=(Q_(0, "second"), Q_(10, "second")),
        t_eval=Q_(np.linspace(0, 10, 51), "second"),
    )

    validation = validate_mass_balance(result, conserved_weights={"A": 1.0, "B": 1.0})

    assert validation.passed


def test_open_system_reports_external_flux_requirement() -> None:
    result = build_first_order_engine().simulate(
        initial_state={"A": Q_(1.0, "mole / liter"), "B": Q_(0.0, "mole / liter")},
        t_span=(Q_(0, "second"), Q_(1, "second")),
    )

    validation = validate_mass_balance(result, closed_system=False)

    assert validation.passed
    assert validation.details["closed_system"] is False

