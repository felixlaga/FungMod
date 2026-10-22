"""Analytic activity gradients of state-reading modifiers and the product-rule Jacobian of the wrapper.

The reference is never the implementation's own stencil: it is a Richardson
extrapolation of central differences of the compiled right-hand side with a
state-scaled step, one-sided (forward Richardson) at the non-negative boundary.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.entities import Environment
from fungal_model.modifiers import (
    CompetitiveInhibitionModifier,
    CoupledSubstrateProductInhibitionModifier,
    InhibitorTerm,
    MixedInhibitionModifier,
    PHModifier,
    ProductInhibitionModifier,
    SubstrateInhibitionModifier,
    SubstrateReactivityModifier,
    TemperatureModifier,
    CardinalTemperatureModifier,
)
from fungal_model.processes import (
    FirstOrderDecayProcess,
    HomogeneousMichaelisMentenProcess,
    ModelBuilder,
    ProcessRegistry,
    RateModifierProcess,
)
from fungal_model.processes.rate_modifiers import gamma_concept_assumption
from fungal_model.solvers import ProcessODESolver, RunRequest
from fungal_model.solvers.compiled import JACOBIAN_ANALYTIC, JACOBIAN_FINITE_DIFFERENCE

SOURCE = "artificial gradient benchmark; not biological evidence"
MATURITY = "framework_benchmark"


def _parameter(symbol: str, value: float, units: str) -> Parameter:
    return Parameter(
        name=symbol, symbol=symbol, value=value, units=units, uncertainty=None,
        source=SOURCE, confidence_level="testing", notes=SOURCE,
    )


PARAMETERS = ParameterSet(
    [
        _parameter("K_m", 0.4, "millimolar"),
        _parameter("V_max", 0.05, "millimolar / second"),
        _parameter("K_i", 0.7, "millimolar"),
        _parameter("K_p", 0.9, "millimolar"),
        _parameter("K_s", 2.0, "millimolar"),
        _parameter("K_ic", 0.5, "millimolar"),
        _parameter("K_iu", 1.5, "millimolar"),
        _parameter("K_g", 0.25, "millimolar"),
        _parameter("k", 0.1, "1 / second"),
        _parameter("k2", 0.05, "1 / second"),
        _parameter("S_ref", 1.0, "millimolar"),
        _parameter("n_one", 1.0, "dimensionless"),
        _parameter("n_two", 2.0, "dimensionless"),
        _parameter("n_half", 0.5, "dimensionless"),
        _parameter("Ea", 50e3, "joule / mole"),
        _parameter("T_ref", 300.0, "kelvin"),
        _parameter("T_min", 280.0, "kelvin"),
        _parameter("T_opt", 305.0, "kelvin"),
        _parameter("T_max", 310.0, "kelvin"),
        _parameter("pH_opt", 5.0, "dimensionless"),
        _parameter("pH_width", 1.0, "dimensionless"),
    ]
)
ENVIRONMENT = Environment(
    name="bench", temperature=Q_(300.0, "kelvin"), ph=Q_(5.5, "dimensionless"), source=SOURCE
)


def _michaelis_menten(units: str = "millimolar") -> HomogeneousMichaelisMentenProcess:
    return HomogeneousMichaelisMentenProcess(
        name="modified MM", substrate_state="S", product_state="P", km_symbol="K_m", vmax_symbol="V_max",
        rate_units="millimolar / second", substrate_units=units,
    )


def _first_order(name: str, source: str, product: str, rate_constant: str) -> FirstOrderDecayProcess:
    return FirstOrderDecayProcess(
        name=name, substrate_state=source, product_state=product, rate_constant_symbol=rate_constant,
        state_units="millimolar",
    )


def _compile(processes: list[Any], initial: dict[str, float], environment: Environment | None = None):
    model = ModelBuilder(
        process_library=ProcessRegistry(processes),
        requested_processes=tuple(process.name for process in processes),
        parameters=PARAMETERS,
        environment=environment,
        allow_unsourced_for_testing=True,
    ).assemble()
    request = RunRequest(
        initial_state={name: Q_(value, "millimolar") for name, value in initial.items()},
        t_span=(Q_(0.0, "second"), Q_(1.0, "second")),
    )
    return ProcessODESolver(model).compile(request)


def _vector(compiled: Any, values: dict[str, float]) -> np.ndarray:
    return np.array([values[name] for name in compiled.state_names], dtype=float)


def _richardson_jacobian(rhs: Any, state: np.ndarray, base_step: float = 1e-3) -> np.ndarray:
    size = state.size
    matrix = np.zeros((size, size), dtype=float)
    for index in range(size):
        step = base_step * max(abs(state[index]), 1.0)
        unit = np.zeros(size)
        unit[index] = 1.0

        def forward(h: float) -> np.ndarray:
            return (rhs(0.0, state + h * unit) - rhs(0.0, state)) / h

        def central(h: float) -> np.ndarray:
            return (rhs(0.0, state + h * unit) - rhs(0.0, state - h * unit)) / (2.0 * h)

        if state[index] - step < 0.0:
            # One-sided at the non-negative boundary: a smaller step keeps the O(h^2) residual below the floor.
            boundary_step = step / 10.0
            matrix[:, index] = 2.0 * forward(boundary_step / 2.0) - forward(boundary_step)
        else:
            matrix[:, index] = (4.0 * central(step / 2.0) - central(step)) / 3.0
    return matrix


def _assert_matches_reference(compiled: Any, values: dict[str, float]) -> None:
    state = _vector(compiled, values)
    expected = _richardson_jacobian(compiled.rhs, state)
    actual = compiled.jacobian(0.0, state)
    scale = max(float(np.max(np.abs(expected))), 1.0)
    np.testing.assert_allclose(actual, expected, rtol=1e-5, atol=1e-8 * scale, err_msg=str(values))


def _mixed(*terms: InhibitorTerm) -> MixedInhibitionModifier:
    return MixedInhibitionModifier(
        substrate_state="S", michaelis_constant_symbol="K_m", substrate_units="millimolar",
        inhibitors=terms, primary_source=SOURCE, maturity=MATURITY,
    )


STATE_MODIFIER_CASES: dict[str, tuple[Any, dict[str, float]]] = {
    "product_inhibition": (
        ProductInhibitionModifier(product_state="P", inhibition_constant_symbol="K_i", product_units="millimolar"),
        {"S": 0.8, "P": 0.3},
    ),
    "competitive_inhibition": (
        CompetitiveInhibitionModifier(
            substrate_state="S", inhibitor_state="P", michaelis_constant_symbol="K_m",
            inhibition_constant_symbol="K_i", substrate_units="millimolar", inhibitor_units="millimolar",
            primary_source=SOURCE, maturity=MATURITY,
        ),
        {"S": 0.8, "P": 0.3},
    ),
    "substrate_inhibition": (
        SubstrateInhibitionModifier(
            substrate_state="S", michaelis_constant_symbol="K_m", inhibition_constant_symbol="K_s",
            substrate_units="millimolar", primary_source=SOURCE, maturity=MATURITY,
        ),
        {"S": 0.8, "P": 0.3},
    ),
    "coupled_substrate_product_inhibition": (
        CoupledSubstrateProductInhibitionModifier(
            substrate_state="S", product_state="P", michaelis_constant_symbol="K_m",
            substrate_inhibition_constant_symbol="K_s", product_inhibition_constant_symbol="K_p",
            substrate_units="millimolar", product_units="millimolar", primary_source=SOURCE, maturity=MATURITY,
        ),
        {"S": 0.8, "P": 0.3},
    ),
    "mixed_inhibition_two_inhibitors": (
        _mixed(
            InhibitorTerm(state="P", units="millimolar", mechanism="mixed",
                          competitive_constant_symbol="K_ic", uncompetitive_constant_symbol="K_iu"),
            InhibitorTerm(state="G", units="millimolar", mechanism="noncompetitive",
                          competitive_constant_symbol="K_g", uncompetitive_constant_symbol="K_g"),
        ),
        {"S": 0.8, "P": 0.3, "G": 0.2},
    ),
    "mixed_inhibition_competitive_and_uncompetitive": (
        _mixed(
            InhibitorTerm(state="P", units="millimolar", mechanism="competitive", competitive_constant_symbol="K_ic"),
            InhibitorTerm(state="G", units="millimolar", mechanism="uncompetitive",
                          uncompetitive_constant_symbol="K_iu"),
        ),
        {"S": 0.8, "P": 0.3, "G": 0.2},
    ),
}


@pytest.mark.parametrize("case", sorted(STATE_MODIFIER_CASES))
def test_every_state_modifier_matches_richardson_at_interior_and_zero_states(case: str) -> None:
    modifier, interior = STATE_MODIFIER_CASES[case]
    process = RateModifierProcess(base_process=_michaelis_menten(), rate_modifiers=(modifier,))
    compiled = _compile([process], interior)
    assert compiled.processes[0].jacobian_kind == JACOBIAN_ANALYTIC
    _assert_matches_reference(compiled, interior)
    for name in interior:
        _assert_matches_reference(compiled, {**interior, name: 0.0})
    _assert_matches_reference(compiled, {name: 0.0 for name in interior})


def test_competitive_gradient_holds_across_state_and_modifier_units() -> None:
    modifier = CompetitiveInhibitionModifier(
        substrate_state="S", inhibitor_state="P", michaelis_constant_symbol="K_m",
        inhibition_constant_symbol="K_i", substrate_units="micromolar", inhibitor_units="millimolar",
        primary_source=SOURCE, maturity=MATURITY,
    )
    process = RateModifierProcess(base_process=_michaelis_menten(), rate_modifiers=(modifier,))
    compiled = _compile([process], {"S": 0.8, "P": 0.3})
    assert compiled.processes[0].jacobian_kind == JACOBIAN_ANALYTIC
    _assert_matches_reference(compiled, {"S": 0.8, "P": 0.3})
    _assert_matches_reference(compiled, {"S": 0.0, "P": 0.3})


@pytest.mark.parametrize("exponent", ["n_one", "n_two"])
def test_reactivity_gradient_matches_richardson_for_exponents_of_one_and_above(exponent: str) -> None:
    modifier = SubstrateReactivityModifier(
        substrate_state="A", reference_concentration_symbol="S_ref", exponent_symbol=exponent,
        substrate_units="millimolar",
    )
    process = RateModifierProcess(base_process=_first_order("loss", "A", "B", "k"), rate_modifiers=(modifier,))
    compiled = _compile([process], {"A": 2.0, "B": 0.0})
    assert compiled.processes[0].jacobian_kind == JACOBIAN_ANALYTIC
    _assert_matches_reference(compiled, {"A": 2.0, "B": 0.0})
    _assert_matches_reference(compiled, {"A": 0.0, "B": 0.0})


def test_reactivity_below_exponent_one_offers_no_gradient_and_is_recorded_as_finite_difference() -> None:
    modifier = SubstrateReactivityModifier(
        substrate_state="A", reference_concentration_symbol="S_ref", exponent_symbol="n_half",
        substrate_units="millimolar",
    )
    process = RateModifierProcess(base_process=_first_order("loss", "A", "B", "k"), rate_modifiers=(modifier,))
    compiled = _compile([process], {"A": 2.0, "B": 0.0})
    assert compiled.processes[0].jacobian_kind == JACOBIAN_FINITE_DIFFERENCE
    assert compiled.summary()["jacobian_kernels"] == {"loss": JACOBIAN_FINITE_DIFFERENCE}


def test_two_process_reactivity_case_differentiates_the_state_another_process_owns() -> None:
    modifier = SubstrateReactivityModifier(
        substrate_state="C", reference_concentration_symbol="S_ref", exponent_symbol="n_one",
        substrate_units="millimolar",
    )
    loss = RateModifierProcess(base_process=_first_order("loss", "A", "B", "k"), rate_modifiers=(modifier,))
    other = _first_order("other", "C", "D", "k2")
    assert [spec.name for spec in loss.state_variables] == ["A", "C", "B"]
    assert next(spec for spec in loss.state_variables if spec.name == "C").role == "modifier_input"
    compiled = _compile([loss, other], {"A": 2.0, "B": 0.0, "C": 0.5, "D": 0.0})
    assert compiled.summary()["jacobian_kernels"] == {"loss": JACOBIAN_ANALYTIC, "other": JACOBIAN_ANALYTIC}
    state = _vector(compiled, {"A": 2.0, "B": 0.0, "C": 0.5, "D": 0.0})
    jacobian = compiled.jacobian(0.0, state)
    row_a, column_c = compiled.state_names.index("A"), compiled.state_names.index("C")
    assert jacobian[row_a, column_c] == pytest.approx(-0.2)
    _assert_matches_reference(compiled, {"A": 2.0, "B": 0.0, "C": 0.5, "D": 0.0})
    _assert_matches_reference(compiled, {"A": 2.0, "B": 0.0, "C": 0.0, "D": 0.0})


def test_a_modified_michaelis_menten_reports_an_analytic_jacobian_kernel() -> None:
    modifier = ProductInhibitionModifier(product_state="P", inhibition_constant_symbol="K_i", product_units="millimolar")
    process = RateModifierProcess(base_process=_michaelis_menten(), rate_modifiers=(modifier,))
    compiled = _compile([process], {"S": 0.8, "P": 0.3})
    assert compiled.summary()["jacobian_kernels"] == {"modified MM": JACOBIAN_ANALYTIC}
    assert compiled.summary()["analytic_jacobian_count"] == 1


def test_an_undeclared_read_state_is_reported_by_name_rather_than_as_a_key_error() -> None:
    modifier = SubstrateReactivityModifier(
        substrate_state="C", reference_concentration_symbol="S_ref", exponent_symbol="n_one",
        substrate_units="millimolar",
    )
    process = RateModifierProcess(base_process=_first_order("loss", "A", "B", "k"), rate_modifiers=(modifier,))
    assert ("C", "millimolar") in {(spec.name, spec.units) for spec in process.required_state_variables}
    with pytest.raises(ValueError, match=r"Missing: \['C'\]") as info:
        _compile([process], {"A": 2.0, "B": 0.0})
    assert not isinstance(info.value, KeyError)


def _temperature() -> TemperatureModifier:
    return TemperatureModifier(activation_energy_symbol="Ea", reference_temperature_symbol="T_ref", source=SOURCE)


def _cardinal() -> CardinalTemperatureModifier:
    return CardinalTemperatureModifier(
        minimum_temperature_symbol="T_min", optimum_temperature_symbol="T_opt",
        maximum_temperature_symbol="T_max", source=SOURCE,
    )


def test_two_laws_for_one_condition_are_refused_unless_stacking_is_declared() -> None:
    base = _first_order("loss", "A", "B", "k")
    with pytest.raises(ValueError, match="more than one environment law per condition"):
        RateModifierProcess(base_process=base, rate_modifiers=(_cardinal(), _temperature(), _cardinal()))
    process = RateModifierProcess(
        base_process=base, rate_modifiers=(_cardinal(), _temperature()), allow_stacked_condition_laws=True
    )
    data = process.to_dict()
    assert data["allow_stacked_condition_laws"] is True
    assert data["modifier_conditions"] == ["temperature", "temperature"]
    assert any("Stacked environment laws were allowed explicitly" in text for text in process.validity.limitations)
    assert gamma_concept_assumption().name in {assumption.name for assumption in process.assumptions}


def test_mixed_conditions_compose_and_environment_factors_have_zero_gradient() -> None:
    inhibition = ProductInhibitionModifier(product_state="P", inhibition_constant_symbol="K_i", product_units="millimolar")
    ph = PHModifier(optimum_symbol="pH_opt", width_symbol="pH_width", source=SOURCE)
    process = RateModifierProcess(base_process=_michaelis_menten(), rate_modifiers=(_cardinal(), ph, inhibition))
    assert process.to_dict()["modifier_conditions"] == ["temperature", "ph", "state"]
    assert process.to_dict()["allow_stacked_condition_laws"] is False
    compiled = _compile([process], {"S": 0.8, "P": 0.3}, environment=ENVIRONMENT)
    assert compiled.processes[0].jacobian_kind == JACOBIAN_ANALYTIC
    _assert_matches_reference(compiled, {"S": 0.8, "P": 0.3})
    _assert_matches_reference(compiled, {"S": 0.0, "P": 0.0})
    plain = _compile(
        [RateModifierProcess(base_process=_michaelis_menten(), rate_modifiers=(inhibition,))], {"S": 0.8, "P": 0.3}
    )
    state = np.array([0.8, 0.3])
    ratio = compiled.rhs(0.0, state) / plain.rhs(0.0, state)
    np.testing.assert_allclose(compiled.jacobian(0.0, state), plain.jacobian(0.0, state) * ratio[0], rtol=1e-12)
