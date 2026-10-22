"""Contracts reconciled when AUDIT-001 was merged onto main after BIO-004.

* main's state-driven pH and oxygen modifiers and its cardinal water-activity
  modifier speak the WP4 modifier protocol (``condition``, ``read_states``,
  ``compile_activity_gradient``), so the stacked-condition guard classifies
  them and the product-rule Jacobian sees the states they read;
* a state-reading modifier without ``compile_activity_gradient`` falls back to
  the recorded finite-difference path instead of failing;
* the WP6 closure-stoichiometry check reads main's unit-bearing coefficients
  in the pool's own units, and WP6's endogenous maintenance accepts main's
  separate state bases and optional oxidant.

The Jacobian reference is a Richardson extrapolation of central differences of
the compiled right-hand side, never the implementation's own stencil. Every
number here is synthetic and is not biological evidence.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from fungal_model.core.kernels import KernelContext
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.entities import Environment
from fungal_model.kinetics import cardinal_cm2_activity, cardinal_water_activity_activity
from fungal_model.modifiers import (
    CONDITION_OXYGEN,
    CONDITION_PH,
    CONDITION_STATE,
    CONDITION_WATER_ACTIVITY,
    CardinalPHModifier,
    CardinalWaterActivityModifier,
    OxygenModifier,
    PHModifier,
    RossoRobinsonWaterActivityModifier,
)
from fungal_model.processes import (
    HomogeneousMichaelisMentenProcess,
    ModelBuilder,
    ProcessRegistry,
    RateModifierProcess,
)
from fungal_model.processes.culture import EndogenousMaintenanceProcess, ResourceLimitedGrowthProcess
from fungal_model.solvers import ProcessODESolver, RunRequest
from fungal_model.solvers.compiled import JACOBIAN_ANALYTIC, JACOBIAN_FINITE_DIFFERENCE

SOURCE = "artificial merge-reconciliation benchmark; not biological evidence"


def _parameter(symbol: str, value: float, units: str) -> Parameter:
    return Parameter(
        name=symbol, symbol=symbol, value=value, units=units, uncertainty=None,
        source=SOURCE, confidence_level="testing", notes=SOURCE,
    )


PARAMETERS = ParameterSet(
    [
        _parameter("K_m", 0.4, "millimolar"),
        _parameter("V_max", 0.05, "millimolar / second"),
        _parameter("K_O2", 0.03, "millimolar"),
        _parameter("pH_opt", 5.0, "dimensionless"),
        _parameter("pH_width", 1.0, "dimensionless"),
        _parameter("pH_min", 2.0, "dimensionless"),
        _parameter("pH_max", 9.0, "dimensionless"),
        _parameter("aw_min", 0.8, "dimensionless"),
        _parameter("aw_opt", 0.95, "dimensionless"),
        _parameter("aw_max", 1.0, "dimensionless"),
    ]
)


def _michaelis_menten() -> HomogeneousMichaelisMentenProcess:
    return HomogeneousMichaelisMentenProcess(
        name="modified MM", substrate_state="S", product_state="P", km_symbol="K_m", vmax_symbol="V_max",
        rate_units="millimolar / second", substrate_units="millimolar",
    )


def _compile(process: Any, initial: dict[str, Any], environment: Environment | None = None) -> Any:
    model = ModelBuilder(
        process_library=ProcessRegistry([process]),
        requested_processes=(process.name,),
        parameters=PARAMETERS,
        environment=environment,
        allow_unsourced_for_testing=True,
    ).assemble()
    request = RunRequest(initial_state=initial, t_span=(Q_(0.0, "second"), Q_(1.0, "second")))
    return ProcessODESolver(model).compile(request)


def _richardson_jacobian(rhs: Any, state: np.ndarray, base_step: float = 1e-3) -> np.ndarray:
    size = state.size
    matrix = np.zeros((size, size), dtype=float)
    for index in range(size):
        step = base_step * max(abs(state[index]), 1.0)
        unit = np.zeros(size)
        unit[index] = 1.0

        def central(h: float) -> np.ndarray:
            return (rhs(0.0, state + h * unit) - rhs(0.0, state - h * unit)) / (2.0 * h)

        matrix[:, index] = (4.0 * central(step / 2.0) - central(step)) / 3.0
    return matrix


def _assert_matches_reference(compiled: Any, values: dict[str, float]) -> None:
    state = np.array([values[name] for name in compiled.state_names], dtype=float)
    expected = _richardson_jacobian(compiled.rhs, state)
    actual = compiled.jacobian(0.0, state)
    scale = max(float(np.max(np.abs(expected))), 1.0)
    np.testing.assert_allclose(actual, expected, rtol=1e-6, atol=1e-9 * scale, err_msg=str(values))


def test_main_modifiers_declare_the_wp4_protocol() -> None:
    static_ph = PHModifier("pH_opt", "pH_width", SOURCE)
    dynamic_ph = PHModifier("pH_opt", "pH_width", SOURCE, state_source="pH")
    dynamic_cardinal = CardinalPHModifier("pH_min", "pH_opt", "pH_max", SOURCE, state_source="pH")
    dynamic_oxygen = OxygenModifier("K_O2", "millimolar", state_source="O2")
    water = CardinalWaterActivityModifier("aw_min", "aw_opt", SOURCE)

    assert (static_ph.condition, static_ph.read_states) == (CONDITION_PH, ())
    assert (dynamic_ph.condition, dynamic_ph.read_states) == (CONDITION_PH, (("pH", "dimensionless"),))
    assert dynamic_cardinal.read_states == (("pH", "dimensionless"),)
    assert (dynamic_oxygen.condition, dynamic_oxygen.read_states) == (CONDITION_OXYGEN, (("O2", "millimolar"),))
    assert OxygenModifier("K_O2", "millimolar").read_states == ()
    assert (water.condition, water.read_states) == (CONDITION_WATER_ACTIVITY, ())


def test_state_driven_ph_and_oxygen_give_an_analytic_product_rule_jacobian() -> None:
    process = RateModifierProcess(
        base_process=_michaelis_menten(),
        rate_modifiers=(
            PHModifier("pH_opt", "pH_width", SOURCE, state_source="pH"),
            OxygenModifier("K_O2", "millimolar", state_source="O2"),
        ),
    )
    roles = {spec.name: spec.role for spec in process.required_state_variables}
    assert roles["pH"] == "ph" and roles["O2"] == "dissolved_oxygen"
    compiled = _compile(
        process,
        {"S": Q_(0.8, "millimolar"), "P": Q_(0.1, "millimolar"), "O2": Q_(0.05, "millimolar"), "pH": Q_(5.6, "dimensionless")},
    )
    assert compiled.processes[0].jacobian_kind == JACOBIAN_ANALYTIC
    for values in ({"S": 0.8, "P": 0.1, "O2": 0.05, "pH": 5.6}, {"S": 0.2, "P": 0.4, "O2": 0.01, "pH": 4.1}):
        _assert_matches_reference(compiled, values)
        state = np.array([values[name] for name in compiled.state_names], dtype=float)
        jacobian = compiled.jacobian(0.0, state)
        assert jacobian[compiled.state_names.index("S"), compiled.state_names.index("pH")] != 0.0
        assert jacobian[compiled.state_names.index("S"), compiled.state_names.index("O2")] != 0.0


def test_stacked_guard_counts_a_state_driven_ph_law_with_an_environment_ph_law() -> None:
    modifiers = (
        PHModifier("pH_opt", "pH_width", SOURCE),
        CardinalPHModifier("pH_min", "pH_opt", "pH_max", SOURCE, state_source="pH"),
    )
    with pytest.raises(ValueError, match="stacked"):
        RateModifierProcess(base_process=_michaelis_menten(), rate_modifiers=modifiers)
    allowed = RateModifierProcess(
        base_process=_michaelis_menten(), rate_modifiers=modifiers, allow_stacked_condition_laws=True
    )
    assert allowed.to_dict()["modifier_conditions"] == [CONDITION_PH, CONDITION_PH]


def test_both_cardinal_water_activity_types_are_one_condition_and_one_law() -> None:
    main_type = CardinalWaterActivityModifier("aw_min", "aw_opt", SOURCE)
    audit_type = RossoRobinsonWaterActivityModifier("aw_min", "aw_opt", "aw_max", SOURCE)
    with pytest.raises(ValueError, match="stacked"):
        RateModifierProcess(base_process=_michaelis_menten(), rate_modifiers=(main_type, audit_type))
    environment = Environment(name="bench", water_activity=Q_(0.9, "dimensionless"), source=SOURCE)
    grid = np.linspace(0.75, 1.0, 11)
    main_values = np.array([
        float(cardinal_water_activity_activity(
            water_activity=Q_(value, "dimensionless"), minimum_water_activity=Q_(0.8, "dimensionless"),
            optimum_water_activity=Q_(0.95, "dimensionless"), source=SOURCE,
        ).magnitude)
        for value in grid
    ])
    np.testing.assert_array_equal(main_values, cardinal_cm2_activity(grid, 0.8, 0.95, 1.0))
    a_main = main_type.activity(parameters=PARAMETERS, environment=environment)
    a_audit = audit_type.activity(parameters=PARAMETERS, environment=environment)
    assert float(a_main.magnitude) == float(a_audit.magnitude)
    compiled = _compile(
        RateModifierProcess(base_process=_michaelis_menten(), rate_modifiers=(main_type,)),
        {"S": Q_(0.8, "millimolar"), "P": Q_(0.1, "millimolar")},
        environment,
    )
    assert compiled.processes[0].jacobian_kind == JACOBIAN_ANALYTIC
    _assert_matches_reference(compiled, {"S": 0.8, "P": 0.1})


class _StateReaderWithoutGradient:
    """A protocol-conforming state-reading modifier that offers no analytic gradient."""

    name = "state reader without gradient"
    condition = CONDITION_STATE
    read_states = (("P", "millimolar"),)
    assumptions = ()

    def activity(self, *, parameters: Any, environment: Any, state: Any = None) -> Any:
        del parameters, environment
        product = float(state["P"].to("millimolar").magnitude)
        return Q_(1.0 / (1.0 + product), "dimensionless")

    def scale(self, *, rate: Any, parameters: Any, environment: Any, state: Any = None) -> Any:
        return rate * self.activity(parameters=parameters, environment=environment, state=state)

    def compile_activity(self, context: KernelContext) -> Any:
        index, factor = context.state_slot("P", "millimolar")

        def activity(time: float, state: np.ndarray) -> float:
            del time
            return 1.0 / (1.0 + state[index] * factor)

        return activity


def test_a_state_reader_without_gradient_falls_back_to_recorded_finite_differences() -> None:
    process = RateModifierProcess(base_process=_michaelis_menten(), rate_modifiers=(_StateReaderWithoutGradient(),))
    assert process.compile_jacobian is not None
    compiled = _compile(process, {"S": Q_(0.8, "millimolar"), "P": Q_(0.3, "millimolar")})
    assert compiled.processes[0].jacobian_kind == JACOBIAN_FINITE_DIFFERENCE
    assert compiled.summary()["jacobian_kernels"] == {"modified MM": JACOBIAN_FINITE_DIFFERENCE}
    state = np.array([{"S": 0.8, "P": 0.3}[name] for name in compiled.state_names])
    reference = _richardson_jacobian(compiled.rhs, state)
    np.testing.assert_allclose(compiled.jacobian(0.0, state), reference, rtol=1e-6, atol=1e-10)


def _closure_parameters() -> ParameterSet:
    return ParameterSet([
        _parameter("Y", 0.05, "g/mmol"), _parameter("m", 0.2, "mmol/g/h"), _parameter("q", 10.0, "mmol/g/h"),
        _parameter("K", 1.0, "mmol/L"), _parameter("KO", 0.01, "mmol/L"), _parameter("Ye", 30.0, "mmol/g"),
    ])


def test_closure_consistency_reads_unit_bearing_coefficients_in_pool_units() -> None:
    units = {"G": "mmol/L", "X": "g/L"}
    common = dict(
        name="uptake", substrate_state="G", biomass_state="X", concentration_units="mmol/L", state_units=units,
        time_units="h", true_yield_symbol="Y", maintenance_demand_symbol="m", uptake_capacity_symbol="q",
        substrate_half_saturation_symbol="K",
    )
    context = KernelContext(state_index={"G": 0, "X": 1}, state_units=units, time_units="h", parameters=_closure_parameters())
    consistent = ResourceLimitedGrowthProcess(**common, stoichiometry={"G": {"value": -20, "units": "mmol/g"}, "X": 1.0})
    assert consistent.compile_rate(context) is not None
    drifted = ResourceLimitedGrowthProcess(**common, stoichiometry={"G": {"value": -25, "units": "mmol/g"}, "X": 1.0})
    with pytest.raises(ValueError, match="-1/Y"):
        drifted.compile_rate(context)


@pytest.mark.parametrize("oxidant", [False, True])
def test_endogenous_maintenance_on_separate_bases_with_optional_oxidant(oxidant: bool) -> None:
    units = {"G": "mmol/L", "X": "g/L", "O": "mmol/L"}
    process = EndogenousMaintenanceProcess(
        name="endogenous", substrate_state="G", biomass_state="X", oxidant_state="O" if oxidant else None,
        concentration_units="mmol/L", state_units=units, time_units="h", true_yield_symbol="Y",
        maintenance_demand_symbol="m", uptake_capacity_symbol="q", substrate_half_saturation_symbol="K",
        oxidant_half_saturation_symbol="KO" if oxidant else None, endogenous_yield_symbol="Ye",
        stoichiometry={"X": -1.0},
    )
    assert {requirement.symbol: requirement.units for requirement in process.required_parameters}["Ye"] == "(mmol/L) / (g/L)"
    context = KernelContext(state_index={"G": 0, "X": 1, "O": 2}, state_units=units, time_units="h", parameters=_closure_parameters())
    kernel, gradient = process.compile_rate(context), process.compile_jacobian(context)
    assert kernel is not None and gradient is not None
    # Starved state: capacity 10 * 0.01/1.01 (* O/(KO+O)) < m = 0.2, so biomass is oxidised.
    vector = np.array([0.01, 0.3, 0.2])
    numerical = _richardson_jacobian(lambda t, y: np.array([kernel(t, y)]), vector, base_step=1e-4)[0]
    np.testing.assert_allclose(gradient(0.0, vector), numerical, rtol=1e-7, atol=1e-12)
    state = {name: Q_(vector[index], units[name]) for name, index in context.state_index.items()}
    assert kernel(0.0, vector) == pytest.approx(float(process.rate(state, Q_(0.0, "h"), context.parameters).magnitude))
    assert kernel(0.0, vector) > 0.0
