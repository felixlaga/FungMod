from __future__ import annotations

import numpy as np
import pytest

from fungal_model.core.errors import IncompatibleUnitsError
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_, UnitError
from fungal_model.core.validators import validate_mass_balance, validate_non_negative
from fungal_model.processes import (
    FirstOrderDecayProcess,
    HomogeneousMichaelisMentenProcess,
    MassActionProcess,
    ModelBuilder,
    ProcessRegistry,
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
        source="Artificial homogeneous-process benchmark value; no physical claim.",
        confidence_level="testing",
        notes="Used to test generic homogeneous process behaviour.",
        measurement_method="defined benchmark value",
    )


def test_first_order_process_runs_through_native_process_solver() -> None:
    process = FirstOrderDecayProcess(
        name="generic first-order A to B",
        substrate_state="A",
        product_state="B",
        rate_constant_symbol="k",
        state_units="mole / liter",
    )
    model = ModelBuilder(
        process_library=ProcessRegistry([process]),
        requested_processes=("first_order_decay",),
        parameters=ParameterSet(
            [
                parameter(
                    name="first-order rate constant",
                    symbol="k",
                    value=0.1,
                    units="1 / second",
                )
            ]
        ),
        validators=[
            validate_non_negative,
            lambda result: validate_mass_balance(result, conserved_weights={"A": 1.0, "B": 1.0}),
        ],
    ).assemble()

    result = model.run(
        initial_state={"A": Q_(1.0, "mole / liter"), "B": Q_(0.0, "mole / liter")},
        t_span=(Q_(0.0, "second"), Q_(5.0, "second")),
        t_eval=Q_(np.linspace(0.0, 5.0, 11), "second"),
    )

    assert result.state("A").magnitude[-1] < result.state("A").magnitude[0]
    assert result.state("B").magnitude[-1] > result.state("B").magnitude[0]
    assert result.rate("generic first-order A to B").magnitude[0] > 0.0
    assert all(validation.passed for validation in result.validation_results)


def test_mass_action_process_rate_and_unit_checks() -> None:
    process = MassActionProcess(
        name="generic A plus B to C",
        reactants={"A": 1.0, "B": 1.0},
        products={"C": 1.0},
        state_units={"A": "mole / liter", "B": "mole / liter", "C": "mole / liter"},
        rate_constant_symbol="k2",
        rate_constant_units="liter / mole / second",
        rate_units="mole / liter / second",
    )
    parameters = ParameterSet(
        [
            parameter(
                name="second-order rate constant",
                symbol="k2",
                value=2.0,
                units="liter / mole / second",
            )
        ]
    )

    rate = process.rate(
        {"A": Q_(0.5, "mole / liter"), "B": Q_(0.25, "mole / liter")},
        Q_(0.0, "second"),
        parameters,
    )

    assert rate.to("mole / liter / second").magnitude == pytest.approx(0.25)
    with pytest.raises(UnitError):
        process.rate(
            {"A": Q_(0.5, "kilogram"), "B": Q_(0.25, "mole / liter")},
            Q_(0.0, "second"),
            parameters,
        )


def test_homogeneous_michaelis_menten_process_limiting_cases() -> None:
    process = HomogeneousMichaelisMentenProcess(
        name="generic dissolved Michaelis-Menten",
        substrate_state="S",
        product_state="P",
        vmax_symbol="Vmax",
        km_symbol="Km",
        substrate_units="mole / liter",
        rate_units="mole / liter / second",
    )
    parameters = ParameterSet(
        [
            parameter(name="maximum rate", symbol="Vmax", value=10.0, units="mole / liter / second"),
            parameter(name="Michaelis constant", symbol="Km", value=1.0, units="mole / liter"),
        ]
    )

    low = process.rate({"S": Q_(1.0e-6, "mole / liter")}, Q_(0.0, "second"), parameters)
    high = process.rate({"S": Q_(1.0e6, "mole / liter")}, Q_(0.0, "second"), parameters)
    zero = process.rate({"S": Q_(0.0, "mole / liter")}, Q_(0.0, "second"), parameters)

    assert low.to("mole / liter / second").magnitude == pytest.approx(1.0e-5, rel=1.0e-5)
    assert high.to("mole / liter / second").magnitude == pytest.approx(10.0, rel=1.0e-5)
    assert zero.to("mole / liter / second").magnitude == pytest.approx(0.0)


def test_enzyme_explicit_homogeneous_process_zero_enzyme_gives_zero_rate() -> None:
    process = HomogeneousMichaelisMentenProcess(
        name="generic enzyme-explicit dissolved Michaelis-Menten",
        substrate_state="S",
        product_state="P",
        enzyme_state="E",
        enzyme_units="mole / liter",
        kcat_symbol="kcat",
        km_symbol="Km",
        substrate_units="mole / liter",
        rate_units="mole / liter / second",
    )
    parameters = ParameterSet(
        [
            parameter(name="turnover coefficient", symbol="kcat", value=5.0, units="1 / second"),
            parameter(name="Michaelis constant", symbol="Km", value=1.0, units="mole / liter"),
        ]
    )

    rate = process.rate(
        {"S": Q_(1.0, "mole / liter"), "E": Q_(0.0, "mole / liter")},
        Q_(0.0, "second"),
        parameters,
    )

    assert rate.to("mole / liter / second").magnitude == pytest.approx(0.0)


def test_homogeneous_process_assembly_reports_bad_units() -> None:
    process = HomogeneousMichaelisMentenProcess(
        name="generic dissolved Michaelis-Menten",
        substrate_state="S",
        vmax_symbol="Vmax",
        km_symbol="Km",
        substrate_units="mole / liter",
        rate_units="mole / liter / second",
    )
    builder = ModelBuilder(
        process_library=ProcessRegistry([process]),
        requested_processes=("homogeneous_michaelis_menten",),
        parameters=ParameterSet(
            [
                parameter(name="maximum rate", symbol="Vmax", value=1.0, units="meter"),
                parameter(name="Michaelis constant", symbol="Km", value=1.0, units="mole / liter"),
            ]
        ),
    )

    with pytest.raises(IncompatibleUnitsError) as exc_info:
        builder.assemble()

    assert exc_info.value.report.incompatible_units[0].symbol == "Vmax"
