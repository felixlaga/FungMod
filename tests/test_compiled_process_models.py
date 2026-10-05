"""The compiled right-hand side must reproduce the unit-aware process path.

These tests treat the unit-aware ``Process.rate``/``contributions`` evaluation
as the reference and require the compiled kernels, stoichiometry and
trajectories to match it on every packaged model config, on custom processes
without kernels, and on mixed-unit models. They also pin the explicit kernel
bookkeeping so that a slow path can never be silent.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pytest

from fungal_model.core.kernels import KernelContext, RateKernel
from fungal_model.core.numerics import solve_checked
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_, Quantity, assert_compatible
from fungal_model.entities.environment import Environment
from fungal_model.io.model_config import load_model_config
from fungal_model.kinetics.arrhenius import EnvironmentalValidityWarning
from fungal_model.modifiers import PHModifier, TemperatureModifier
from fungal_model.plugins.pet import pet_substrate_loader_registry
from fungal_model.processes import (
    FirstOrderDecayProcess,
    HomogeneousMichaelisMentenProcess,
    MassActionProcess,
    ModelBuilder,
    ProcessRegistry,
    RateModifierProcess,
)
from fungal_model.processes.base import ParameterRequirement, Process, StateVariableSpec
from fungal_model.solvers import ProcessODESolver, RunRequest, compile_assembled_model
from fungal_model.solvers.compiled import (
    KERNEL_NUMERIC,
    KERNEL_NUMERIC_THERMODYNAMIC,
    KERNEL_QUANTITY_WRAPPED,
    MODEL_REPRESENTATION,
    NEGATIVE_STATE_POLICY,
    NUMERIC_KERNEL_KINDS,
    CompiledModel,
    resolve_state_units,
)
from fungal_model.workflows.configured_inputs import ConfiguredInputLoader
from fungal_model.workflows.configured_processes import ConfiguredProcessAssembler, require_runnable_config

ROOT = Path(__file__).resolve().parents[1]
MODEL_CONFIGS = sorted((ROOT / "data" / "model_configs").glob("*.yml"))
SHIPPED_PROCESS_TYPES = {
    "first_order_decay",
    "mass_action",
    "homogeneous_michaelis_menten",
    "ph_ionization_michaelis_menten",
    "proportional_synthesis",
    "surface_catalysis",
    "substrate_transglycosylation",
    "thermal_inactivation",
}


def _parameter(symbol: str, value: float, units: str) -> Parameter:
    return Parameter(
        name=f"artificial {symbol}",
        symbol=symbol,
        value=value,
        units=units,
        uncertainty=0.0,
        source="Artificial compiled-kernel parity benchmark value; no physical claim.",
        confidence_level="testing",
        notes="Used only to test the compiled process core.",
        measurement_method="defined benchmark value",
    )


def _configured(path: Path):
    options = {"substrate_registry": pet_substrate_loader_registry()} if "pet_plugin" in path.name else {}
    config = load_model_config(path)
    require_runnable_config(config)
    inputs = ConfiguredInputLoader(**options).load(config)
    model = ConfiguredProcessAssembler().assemble(config, inputs).model
    request = RunRequest(initial_state=inputs.initial_state, t_span=inputs.t_span, t_eval=inputs.t_eval)
    return model, request


def _reference_rhs(model, compiled: CompiledModel):
    """The unit-aware evaluation the compiled right-hand side must reproduce."""

    constraints = {constraint.process_id: constraint for constraint in model.thermodynamic_constraints}
    names, units, time_units = compiled.state_names, compiled.state_units, compiled.time_units
    units_by_name = dict(zip(names, units, strict=True))

    def rhs(time: float, vector: np.ndarray) -> list[float]:
        state = {name: Q_(value, unit) for name, unit, value in zip(names, units, vector, strict=True)}
        derivative = {name: Q_(0.0, f"{unit} / {time_units}") for name, unit in units_by_name.items()}
        for process in model.processes:
            rate = process.rate(
                state, Q_(time, time_units), model.parameters, model.context.environment, model.context.geometry
            )
            constraint = constraints.get(process.name)
            if constraint is not None:
                rate, _ = constraint.enforce(rate, state)
            for species, contribution in process.contributions(rate).items():
                derivative[species] += assert_compatible(contribution, f"{units_by_name[species]} / {time_units}")
        return [float(derivative[name].to(f"{units_by_name[name]} / {time_units}").magnitude) for name in names]

    return rhs


def _numeric_request(model, request: RunRequest):
    state_units = resolve_state_units(model)
    time_units = str(request.t_span[1].units)
    span = (
        float(request.t_span[0].to(time_units).magnitude),
        float(request.t_span[1].to(time_units).magnitude),
    )
    t_eval = None if request.t_eval is None else np.asarray(request.t_eval.to(time_units).magnitude, dtype=float)
    y0 = np.asarray(
        [float(request.initial_state[name].to(units).magnitude) for name, units in state_units.items()],
        dtype=float,
    )
    return state_units, time_units, span, t_eval, y0


def _trial_states(y0: np.ndarray, count: int = 6) -> list[np.ndarray]:
    generator = np.random.default_rng(20261004)
    states = [y0.copy()]
    for _ in range(count - 1):
        states.append(y0 * generator.uniform(0.05, 1.5, size=y0.shape))
    return states


@pytest.mark.parametrize("config_path", MODEL_CONFIGS, ids=[path.stem for path in MODEL_CONFIGS])
def test_compiled_rhs_and_trajectory_match_unit_aware_reference(config_path: Path) -> None:
    model, request = _configured(config_path)
    compiled = ProcessODESolver(model).compile(request)
    state_units, time_units, span, t_eval, y0 = _numeric_request(model, request)
    reference = _reference_rhs(model, compiled)

    for state in _trial_states(y0):
        np.testing.assert_allclose(compiled.rhs(span[0], state), reference(span[0], state), rtol=1e-12, atol=0.0)

    options = model.solver_settings.scipy_options(state_units, time_units)
    with pytest.warns() if "modifier" in config_path.stem else _no_warning_filter():
        compiled_solution = solve_checked(compiled.rhs, span, y0, t_eval=t_eval, **options)
        reference_solution = solve_checked(reference, span, y0, t_eval=t_eval, **options)
    scale = np.maximum(np.max(np.abs(reference_solution.y), axis=1, keepdims=True), 1e-300)
    np.testing.assert_allclose(compiled_solution.y / scale, reference_solution.y / scale, rtol=0.0, atol=1e-9)
    assert compiled_solution.nfev == reference_solution.nfev

    kinds = compiled.summary()["process_kernels"]
    assert set(kinds.values()) <= NUMERIC_KERNEL_KINDS, kinds
    assert set(kinds) == {process.name for process in model.processes}


class _no_warning_filter:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.mark.parametrize("config_path", MODEL_CONFIGS, ids=[path.stem for path in MODEL_CONFIGS])
def test_every_kernel_matches_its_process_rate_pointwise(config_path: Path) -> None:
    model, request = _configured(config_path)
    compiled = ProcessODESolver(model).compile(request)
    _, time_units, span, _, y0 = _numeric_request(model, request)
    constraints = {constraint.process_id: constraint for constraint in model.thermodynamic_constraints}

    for state in _trial_states(y0):
        quantity_state = compiled.quantity_state(state)
        for process in compiled.processes:
            expected = process.process.rate(
                quantity_state, Q_(span[0], time_units), model.parameters, model.context.environment,
                model.context.geometry,
            )
            constraint = constraints.get(process.name)
            if constraint is not None:
                expected, _ = constraint.enforce(expected, quantity_state)
            expected_value = float(assert_compatible(expected, process.rate_units).magnitude)
            assert process.rate(span[0], state) == pytest.approx(expected_value, rel=1e-12, abs=0.0)


def test_run_records_kernel_kinds_and_numeric_thermodynamic_enforcement() -> None:
    model, request = _configured(ROOT / "data" / "model_configs" / "showcase_dynamic_thermodynamics.yml")
    result = ProcessODESolver(model).run(request)

    kernel = result.solver_metadata["kernel"]
    assert kernel["representation"] == MODEL_REPRESENTATION
    assert kernel["unit_resolution"] == "build_time"
    assert kernel["quantity_wrapped_kernel_count"] == 0
    assert kernel["numeric_kernel_count"] == len(model.processes)
    constrained = {constraint.process_id for constraint in model.thermodynamic_constraints}
    assert constrained
    for name, kind in kernel["process_kernels"].items():
        assert kind == (KERNEL_NUMERIC_THERMODYNAMIC if name in constrained else KERNEL_NUMERIC)
    assert result.solver_metadata["dynamic_thermodynamics"]["enabled"] is True
    assert result.solver_metadata["backend"] == "scipy.solve_ivp"


def test_shipped_process_types_all_compile_to_numeric_kernels() -> None:
    """Architecture-debt boundary: no shipped mechanism may silently use the slow path."""

    seen: dict[str, set[str]] = {}
    for config_path in MODEL_CONFIGS:
        model, request = _configured(config_path)
        compiled = ProcessODESolver(model).compile(request)
        for process in compiled.processes:
            seen.setdefault(process.process_type, set()).add(process.kernel_kind)
    mass_action = MassActionProcess(
        name="artificial A + B -> C",
        reactants={"A": 1.0, "B": 1.0},
        products={"C": 1.0},
        state_units={"A": "millimolar", "B": "millimolar", "C": "millimolar"},
        rate_constant_symbol="k2",
        rate_constant_units="1 / (millimolar * second)",
        rate_units="millimolar / second",
    )
    model = ModelBuilder(
        process_library=ProcessRegistry([mass_action]),
        requested_processes=("mass_action",),
        parameters=ParameterSet([_parameter("k2", 0.3, "1 / (millimolar * second)")]),
    ).assemble()
    request = RunRequest(
        initial_state={"A": Q_(2.0, "millimolar"), "B": Q_(1.0, "millimolar"), "C": Q_(0.0, "millimolar")},
        t_span=(Q_(0.0, "second"), Q_(4.0, "second")),
    )
    compiled = ProcessODESolver(model).compile(request)
    seen.setdefault("mass_action", set()).update(process.kernel_kind for process in compiled.processes)
    assert SHIPPED_PROCESS_TYPES <= set(seen), sorted(seen)
    for process_type in SHIPPED_PROCESS_TYPES:
        assert seen[process_type] <= NUMERIC_KERNEL_KINDS, (process_type, seen[process_type])


class _UnitAwareOnlyDecay(Process):
    """A process that implements only the unit-aware interface."""

    def __init__(self) -> None:
        Process.__init__(
            self,
            name="unit-aware only decay",
            process_type="first_order_decay",
            required_state_variables=(StateVariableSpec("A", "mole / liter"),),
            changed_state_variables=(StateVariableSpec("A", "mole / liter"), StateVariableSpec("B", "mole / liter")),
            required_parameters=(ParameterRequirement(symbol="k", units="1 / second"),),
            source="Artificial compiled-core fallback benchmark.",
        )

    def rate(self, state, time, parameters, environment=None, geometry=None) -> Quantity:
        del time, environment, geometry
        return assert_compatible(parameters.require_quantity("k", "1 / second") * state["A"], "mole / liter / second")

    def contributions(self, rate: Quantity) -> Mapping[str, Quantity]:
        value = assert_compatible(rate, "mole / liter / second")
        return {"A": -value, "B": value}


def _decay_request() -> RunRequest:
    return RunRequest(
        initial_state={"A": Q_(1.0, "mole / liter"), "B": Q_(0.0, "mole / liter")},
        t_span=(Q_(0.0, "second"), Q_(5.0, "second")),
        t_eval=Q_(np.linspace(0.0, 5.0, 11), "second"),
    )


def test_process_without_kernel_uses_recorded_quantity_wrapped_path_exactly() -> None:
    parameters = ParameterSet([_parameter("k", 0.1, "1 / second")])
    wrapped_model = ModelBuilder(
        process_library=ProcessRegistry([_UnitAwareOnlyDecay()]),
        requested_processes=("first_order_decay",),
        parameters=parameters,
    ).assemble()
    numeric_model = ModelBuilder(
        process_library=ProcessRegistry(
            [FirstOrderDecayProcess(name="numeric decay", substrate_state="A", product_state="B",
                                    rate_constant_symbol="k", state_units="mole / liter")]
        ),
        requested_processes=("first_order_decay",),
        parameters=parameters,
    ).assemble()

    wrapped = ProcessODESolver(wrapped_model).run(_decay_request())
    numeric = ProcessODESolver(numeric_model).run(_decay_request())

    assert wrapped.solver_metadata["kernel"]["process_kernels"] == {"unit-aware only decay": KERNEL_QUANTITY_WRAPPED}
    assert wrapped.solver_metadata["kernel"]["quantity_wrapped_kernel_count"] == 1
    assert numeric.solver_metadata["kernel"]["process_kernels"] == {"numeric decay": KERNEL_NUMERIC}
    expected = np.exp(-0.1 * np.linspace(0.0, 5.0, 11))
    np.testing.assert_allclose(wrapped.state("A").magnitude, expected, rtol=1e-6)
    np.testing.assert_allclose(wrapped.state("A").magnitude, numeric.state("A").magnitude, rtol=1e-12)
    np.testing.assert_allclose(
        wrapped.rate("unit-aware only decay").magnitude, numeric.rate("numeric decay").magnitude, rtol=1e-12
    )


class _QuadraticContributions(_UnitAwareOnlyDecay):
    def contributions(self, rate: Quantity) -> Mapping[str, Quantity]:
        value = assert_compatible(rate, "mole / liter / second")
        quadratic = value * value / Q_(1.0, "mole / liter / second")
        return {"A": -quadratic, "B": quadratic}


class _GhostContributions(_UnitAwareOnlyDecay):
    def contributions(self, rate: Quantity) -> Mapping[str, Quantity]:
        value = assert_compatible(rate, "mole / liter / second")
        return {"A": -value, "ghost": value}


def test_contributions_that_are_not_linear_in_rate_are_rejected() -> None:
    model = ModelBuilder(
        process_library=ProcessRegistry([_QuadraticContributions()]),
        requested_processes=("first_order_decay",),
        parameters=ParameterSet([_parameter("k", 0.1, "1 / second")]),
    ).assemble()
    with pytest.raises(ValueError, match="not linear in its rate"):
        ProcessODESolver(model).run(_decay_request())


def test_contribution_to_unknown_state_is_rejected_with_the_same_message() -> None:
    model = ModelBuilder(
        process_library=ProcessRegistry([_GhostContributions()]),
        requested_processes=("first_order_decay",),
        parameters=ParameterSet([_parameter("k", 0.1, "1 / second")]),
    ).assemble()
    with pytest.raises(ValueError, match="contributed to unknown state 'ghost'"):
        ProcessODESolver(model).run(_decay_request())


def test_mixed_units_resolve_at_build_time_and_match_closed_form() -> None:
    process = FirstOrderDecayProcess(
        name="micromolar decay",
        substrate_state="A",
        product_state="B",
        rate_constant_symbol="k",
        state_units="micromolar",
        rate_units="millimolar / hour",
    )
    model = ModelBuilder(
        process_library=ProcessRegistry([process]),
        requested_processes=("first_order_decay",),
        parameters=ParameterSet([_parameter("k", 0.5, "1 / minute")]),
    ).assemble()
    request = RunRequest(
        initial_state={"A": Q_(2.0, "millimolar"), "B": Q_(0.0, "micromolar")},
        t_span=(Q_(0.0, "hour"), Q_(0.2, "hour")),
        t_eval=Q_(np.linspace(0.0, 0.2, 9), "hour"),
    )
    compiled = ProcessODESolver(model).compile(request)
    assert compiled.state_units == ("micromolar", "micromolar")
    assert compiled.time_units == "hour"
    # One micromolar per hour of decay per unit rate (millimolar / hour): factor 1000 in each column.
    np.testing.assert_allclose(compiled.stoichiometry[:, 0], [-1000.0, 1000.0])

    result = ProcessODESolver(model).run(request)
    minutes = np.linspace(0.0, 0.2, 9) * 60.0
    np.testing.assert_allclose(result.state("A").to("millimolar").magnitude, 2.0 * np.exp(-0.5 * minutes), rtol=1e-7)
    np.testing.assert_allclose(
        (result.state("A") + result.state("B")).to("millimolar").magnitude, 2.0, rtol=1e-9
    )
    reference = _reference_rhs(model, compiled)
    _, _, span, t_eval, y0 = _numeric_request(model, request)
    options = model.solver_settings.scipy_options(resolve_state_units(model), "hour")
    reference_solution = solve_checked(reference, span, y0, t_eval=t_eval, **options)
    np.testing.assert_allclose(result.state("A").magnitude, reference_solution.y[0], rtol=1e-9)


def _environment_modified_model(temperature_c: float, *, t_end: float = 120.0):
    base = HomogeneousMichaelisMentenProcess(
        name="modified MM",
        substrate_state="S",
        product_state="P",
        km_symbol="Km",
        vmax_symbol="Vmax",
        rate_units="millimolar / second",
        substrate_units="millimolar",
    )
    process = RateModifierProcess(
        base_process=base,
        rate_modifiers=(
            TemperatureModifier(
                activation_energy_symbol="Ea",
                reference_temperature_symbol="T_ref",
                minimum_temperature_symbol="T_min",
                maximum_temperature_symbol="T_max",
                source="Artificial compiled-core environment benchmark.",
            ),
            PHModifier(optimum_symbol="pH_opt", width_symbol="pH_width", source="Artificial compiled-core benchmark."),
        ),
    )
    environment = Environment(
        name="bench",
        temperature=Q_(temperature_c, "degC").to("kelvin"),
        ph=Q_(5.5, "dimensionless"),
        source="Artificial compiled-core environment benchmark.",
    )
    model = ModelBuilder(
        process_library=ProcessRegistry([process]),
        requested_processes=("homogeneous_michaelis_menten",),
        environment=environment,
        parameters=ParameterSet(
            [
                _parameter("Km", 0.4, "millimolar"),
                _parameter("Vmax", 0.05, "millimolar / second"),
                _parameter("Ea", 45000.0, "joule / mole"),
                _parameter("T_ref", 298.15, "kelvin"),
                _parameter("T_min", 288.15, "kelvin"),
                _parameter("T_max", 318.15, "kelvin"),
                _parameter("pH_opt", 5.0, "dimensionless"),
                _parameter("pH_width", 1.0, "dimensionless"),
            ]
        ),
    ).assemble()
    request = RunRequest(
        initial_state={"S": Q_(3.0, "millimolar"), "P": Q_(0.0, "millimolar")},
        t_span=(Q_(0.0, "second"), Q_(t_end, "second")),
        t_eval=Q_(np.linspace(0.0, t_end, 25), "second"),
    )
    return model, request


def test_environment_modifiers_fold_into_constant_kernels_that_match_reference() -> None:
    model, request = _environment_modified_model(temperature_c=30.0)
    compiled = ProcessODESolver(model).compile(request)
    assert compiled.summary()["process_kernels"] == {"modified MM": KERNEL_NUMERIC}
    reference = _reference_rhs(model, compiled)
    state_units, time_units, span, t_eval, y0 = _numeric_request(model, request)
    for state in _trial_states(y0):
        np.testing.assert_allclose(compiled.rhs(0.0, state), reference(0.0, state), rtol=1e-12, atol=0.0)
    result = ProcessODESolver(model).run(request)
    options = model.solver_settings.scipy_options(state_units, time_units)
    reference_solution = solve_checked(reference, span, y0, t_eval=t_eval, **options)
    np.testing.assert_allclose(result.state("S").magnitude, reference_solution.y[0], rtol=1e-9)
    # The Arrhenius factor above the reference temperature must accelerate the reference-rate process.
    unmodified = compiled.processes[0].process.base_process.compile_rate(compiled.context)
    assert unmodified is not None
    assert compiled.processes[0].rate(0.0, y0) > unmodified(0.0, y0) * 0.9


def test_environment_validity_warnings_still_surface_from_a_compiled_run() -> None:
    # Above T_max; a short horizon keeps the accelerated substrate away from depletion roundoff.
    model, request = _environment_modified_model(temperature_c=60.0, t_end=5.0)
    with pytest.warns(EnvironmentalValidityWarning):
        ProcessODESolver(model).run(request)


def test_negative_trial_states_are_projected_for_rate_evaluation_only() -> None:
    """Solver trial iterates below zero evaluate at max(state, 0); the public rate API stays strict."""

    model, request = _configured(ROOT / "data" / "model_configs" / "toy_homogeneous_ab.yml")
    compiled = ProcessODESolver(model).compile(request)
    _, _, span, _, y0 = _numeric_request(model, request)
    negative = y0.copy()
    negative[0] = -1.0e-12
    reference = _reference_rhs(model, compiled)
    with pytest.raises(ValueError, match="must be non-negative"):
        reference(span[0], negative)
    projected = np.maximum(negative, 0.0)
    np.testing.assert_array_equal(compiled.rhs(span[0], negative), reference(span[0], projected))
    np.testing.assert_array_equal(compiled.rhs(span[0], negative), compiled.rhs(span[0], projected))
    assert compiled.summary()["negative_state_policy"] == NEGATIVE_STATE_POLICY


def test_substrate_depletion_integrates_without_clipping_the_trajectory() -> None:
    """A first-order pool decaying over many lifetimes must integrate to completion."""

    model, request = _configured(ROOT / "data" / "model_configs" / "toy_homogeneous_ab.yml")
    long_request = RunRequest(
        initial_state=request.initial_state,
        t_span=(request.t_span[0], Q_(400.0, "second")),
        t_eval=Q_(np.linspace(0.0, 400.0, 41), "second"),
    )
    result = ProcessODESolver(model).run(long_request)
    source = np.asarray(result.states["dissolved_substrate_amount"].magnitude, dtype=float)
    assert source[-1] < 1e-15
    assert source.min() > -1e-9, "accepted trajectory must not be materially negative"
    assert result.solver_metadata["kernel"]["negative_state_policy"] == NEGATIVE_STATE_POLICY


def test_kernel_context_rejects_unknown_states_and_incompatible_units() -> None:
    context = KernelContext(
        state_index={"A": 0},
        state_units={"A": "millimolar"},
        time_units="second",
        parameters=ParameterSet([_parameter("k", 1.0, "1 / second")]),
    )
    assert context.state_slot("A", "molar") == (0, pytest.approx(1e-3))
    assert context.parameter("k", "1 / minute") == pytest.approx(60.0)
    with pytest.raises(KeyError):
        context.state_slot("B", "millimolar")
    with pytest.raises(ValueError):
        context.state_slot("A", "kilogram")


def test_compile_assembled_model_requires_known_constraint_processes() -> None:
    model, request = _configured(ROOT / "data" / "model_configs" / "showcase_dynamic_thermodynamics.yml")
    constraint = model.thermodynamic_constraints[0]
    _, time_units, _, _, y0 = _numeric_request(model, request)
    with pytest.raises(ValueError, match="unknown processes"):
        compile_assembled_model(
            model, time_units=time_units, initial_state=y0, constraints_by_process={"no such process": constraint}
        )


def test_rate_kernel_type_is_callable_on_plain_floats() -> None:
    kernel: RateKernel = lambda time, state: float(state[0]) * 2.0  # noqa: E731
    assert kernel(0.0, np.array([1.5])) == 3.0
