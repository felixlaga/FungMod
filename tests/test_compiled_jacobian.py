"""The compiled Jacobian: per-process gradients, analytic or finite-difference, assembled through the stoichiometry."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from fungal_model.core.kernels import KernelContext
from fungal_model.core.numerics import JACOBIAN_COMPILED, JACOBIAN_FINITE_DIFFERENCE_BY_BACKEND, SolverSettings
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.io.model_config import load_model_config
from fungal_model.plugins.pet import pet_substrate_loader_registry
from fungal_model.processes import MassActionProcess, ModelBuilder, ProcessRegistry, RateModifierProcess
from fungal_model.solvers import ProcessODESolver, RunRequest
from fungal_model.solvers.compiled import JACOBIAN_ANALYTIC, JACOBIAN_BY_BACKEND, JACOBIAN_COMPILED_LABEL, JACOBIAN_FINITE_DIFFERENCE
from fungal_model.workflows.configured_model import ConfiguredInputLoader, ConfiguredProcessAssembler, require_runnable_config
from tests.test_degrading_culture import model as degrading_model
from tests.test_degrading_culture import state as degrading_state

ROOT = Path(__file__).resolve().parents[1]
MODEL_CONFIGS = sorted((ROOT / "data" / "model_configs").glob("*.yml"))
SOURCE = "Artificial Jacobian benchmark; no physical claim."


def _configured(path: Path):
    options = {"substrate_registry": pet_substrate_loader_registry()} if "pet_plugin" in path.name else {}
    config = load_model_config(path)
    require_runnable_config(config)
    inputs = ConfiguredInputLoader(**options).load(config)
    model = ConfiguredProcessAssembler().assemble(config, inputs).model
    request = RunRequest(initial_state=inputs.initial_state, t_span=inputs.t_span, t_eval=inputs.t_eval)
    return model, request


def _finite_difference_jacobian(rhs, time: float, state: np.ndarray, *, relative_step: float = 1e-6) -> np.ndarray:
    size = state.size
    matrix = np.zeros((size, size), dtype=float)
    for index in range(size):
        step = relative_step * max(abs(state[index]), 1.0)
        upper, lower = state.copy(), state.copy()
        upper[index] += step
        lower[index] -= step
        if lower[index] < 0.0:
            lower[index] = state[index]
            matrix[:, index] = (rhs(time, upper) - rhs(time, lower)) / step
        else:
            matrix[:, index] = (rhs(time, upper) - rhs(time, lower)) / (2.0 * step)
    return matrix


@pytest.mark.parametrize("config_path", MODEL_CONFIGS, ids=[path.stem for path in MODEL_CONFIGS])
def test_compiled_jacobian_is_the_derivative_of_the_compiled_rhs(config_path: Path) -> None:
    model, request = _configured(config_path)
    compiled = ProcessODESolver(model).compile(request)
    summary = compiled.summary()
    assert set(summary["jacobian_kernels"].values()) <= {JACOBIAN_ANALYTIC, JACOBIAN_FINITE_DIFFERENCE}
    assert summary["analytic_jacobian_count"] == sum(kind == JACOBIAN_ANALYTIC for kind in summary["jacobian_kernels"].values())
    for process in compiled.processes:
        if process.constraint is not None:
            assert process.jacobian_kind == JACOBIAN_FINITE_DIFFERENCE, process.name
        elif isinstance(process.process, RateModifierProcess):
            dynamic = any(getattr(modifier, "state_source", None) is not None for modifier in process.process.rate_modifiers)
            expected_kind = JACOBIAN_ANALYTIC if dynamic and process.process.compile_jacobian(compiled.context) is not None else JACOBIAN_FINITE_DIFFERENCE
            assert process.jacobian_kind == expected_kind, process.name
    initial = np.array([float(Q_(request.initial_state[name]).to(units).magnitude) for name, units in zip(compiled.state_names, compiled.state_units, strict=True)])
    rng = np.random.default_rng(3)
    for trial in range(3):
        state = initial if trial == 0 else initial * rng.uniform(0.5, 1.5, initial.size) + 1e-6 * rng.uniform(0.0, 1.0, initial.size)
        expected = _finite_difference_jacobian(compiled.rhs, 0.0, state)
        actual = compiled.jacobian(0.0, state)
        scale = float(np.max(np.abs(expected))) if np.any(expected) else 1.0
        np.testing.assert_allclose(actual, expected, rtol=1e-4, atol=1e-6 * scale, err_msg=f"{config_path.name} trial {trial}")


def test_the_simple_laws_and_the_closure_offer_analytic_gradients() -> None:
    for name in ("toy_homogeneous_ab.yml", "toy_proportional_synthesis_dissolved.yml", "toy_resource_limited_chemostat.yml"):
        model, request = _configured(ROOT / "data" / "model_configs" / name)
        summary = ProcessODESolver(model).compile(request).summary()
        assert set(summary["jacobian_kernels"].values()) == {JACOBIAN_ANALYTIC}, (name, summary["jacobian_kernels"])
        assert summary["jacobian"] == JACOBIAN_BY_BACKEND


def _parameter(symbol: str, value: float, units: str) -> Parameter:
    return Parameter(f"artificial {symbol}", symbol, value, units, None, SOURCE, "testing", "Artificial benchmark value.")


def test_mass_action_gradient_covers_catalysts_and_fractional_orders() -> None:
    process = MassActionProcess(
        name="catalysed", reactants={"A": 0.5, "B": 2.0}, products={"C": 1.0}, catalysts={"E": 1.0},
        state_units={"A": "millimolar", "B": "millimolar", "C": "millimolar", "E": "millimolar"},
        rate_constant_symbol="k", rate_constant_units="1 / millimolar ** 2.5 / second", rate_units="millimolar / second", source=SOURCE,
    )
    names = ("A", "B", "C", "E")
    context = KernelContext(state_index={n: i for i, n in enumerate(names)}, state_units=dict.fromkeys(names, "molar"),
                            time_units="second", parameters=ParameterSet([_parameter("k", 0.7, "1 / millimolar ** 2.5 / second")]))
    rate = process.compile_rate(context)
    gradient = process.compile_jacobian(context)
    assert rate is not None and gradient is not None
    state = np.array([1.2e-3, 0.4e-3, 0.0, 0.3e-3])
    expected = np.zeros(4)
    for index in range(4):
        step = 1e-7 * max(state[index], 1.0)
        upper, lower = state.copy(), state.copy()
        upper[index] += step
        lower[index] -= step
        expected[index] = (rate(0.0, upper) - rate(0.0, lower)) / (2.0 * step)
    np.testing.assert_allclose(gradient(0.0, state), expected, rtol=1e-5, atol=1e-9)
    assert gradient(0.0, state)[2] == 0.0  # the product does not enter the rate
    at_zero = gradient(0.0, np.array([0.0, 0.4e-3, 0.0, 0.3e-3]))
    assert np.isfinite(at_zero).all() and at_zero[0] == 0.0  # order 0.5 at a zero state: the only finite choice
    with pytest.raises(ValueError, match="non-negative"):
        gradient(0.0, np.array([-1e-3, 0.4e-3, 0.0, 0.3e-3]))


def test_integration_with_the_compiled_jacobian_reproduces_the_backend_differences() -> None:
    model, request = _configured(ROOT / "data" / "model_configs" / "toy_resource_limited_chemostat.yml")
    reference = ProcessODESolver(replace(model, solver_settings=SolverSettings(method="BDF", rtol=1e-9, atol=1e-12))).run(request)
    compiled = ProcessODESolver(
        replace(model, solver_settings=SolverSettings(method="BDF", rtol=1e-9, atol=1e-12, jacobian=JACOBIAN_COMPILED))
    ).run(request)
    for name in reference.states:
        np.testing.assert_allclose(compiled.states[name].magnitude, reference.states[name].magnitude, rtol=1e-6, atol=1e-10)
    assert reference.solver_metadata["kernel"]["jacobian"] == JACOBIAN_BY_BACKEND
    assert compiled.solver_metadata["kernel"]["jacobian"] == JACOBIAN_COMPILED_LABEL
    assert compiled.solver_metadata["njev"] and compiled.solver_metadata["njev"] > 0
    assert compiled.solver_settings.to_dict()["jacobian"] == JACOBIAN_COMPILED
    assert "jacobian" not in reference.solver_settings.to_dict()
    explicit = ProcessODESolver(
        replace(model, solver_settings=SolverSettings(method="DOP853", rtol=1e-9, atol=1e-12, jacobian=JACOBIAN_COMPILED))
    ).run(request)
    assert explicit.solver_metadata["kernel"]["jacobian"] == JACOBIAN_BY_BACKEND  # explicit methods take no Jacobian


def test_degrading_culture_compiled_jacobian_matches_the_classes_analytic_one() -> None:
    culture = degrading_model(dilution=0.02)
    settings = SolverSettings(method="BDF", rtol=1e-10, atol=1e-13)
    native = culture.simulate(initial_state=degrading_state(), times=Q_(np.linspace(0, 120, 61), "h"), solver_settings=settings)
    compiled = culture.simulate_compiled(initial_state=degrading_state(), times=Q_(np.linspace(0, 120, 61), "h"),
                                         solver_settings=replace(settings, jacobian=JACOBIAN_COMPILED))
    for name in culture.names:
        np.testing.assert_allclose(compiled.concentrations[name].magnitude, native.concentrations[name].magnitude, rtol=1e-7, atol=1e-11)
    assert native.diagnostics["jacobian"] == "analytic piecewise"
    assert compiled.diagnostics["jacobian"] == JACOBIAN_COMPILED_LABEL
    kernel = compiled.diagnostics["kernel"]
    assert set(kernel["jacobian_kernels"].values()) == {JACOBIAN_ANALYTIC} and kernel["analytic_jacobian_count"] == 13


def test_solver_settings_validate_and_serialise_the_jacobian_option() -> None:
    with pytest.raises(ValueError, match="jacobian option"):
        SolverSettings(jacobian="symbolic")
    assert SolverSettings().jacobian == JACOBIAN_FINITE_DIFFERENCE_BY_BACKEND
    assert SolverSettings(method="BDF").uses_jacobian and not SolverSettings(method="RK45").uses_jacobian
    assert "jacobian" not in SolverSettings().to_dict()
    assert SolverSettings(jacobian=JACOBIAN_COMPILED).to_dict()["jacobian"] == JACOBIAN_COMPILED


def test_a_process_without_an_analytic_gradient_is_differentiated_numerically_and_recorded() -> None:
    from fungal_model.processes.base import ParameterRequirement, Process, StateVariableSpec

    class OnlyRate(Process):
        def __init__(self) -> None:
            Process.__init__(self, name="square law", process_type="artificial",
                             required_state_variables=(StateVariableSpec("A", "millimolar", role="reactant"),),
                             changed_state_variables=(StateVariableSpec("A", "millimolar", role="reactant"),),
                             required_parameters=(ParameterRequirement(symbol="k", units="1 / millimolar / second", name="k"),),
                             assumptions=(), source=SOURCE)

        def rate(self, state, time, parameters, environment=None, geometry=None):
            del time, environment, geometry
            return parameters.require_quantity("k", "1 / millimolar / second") * state["A"] ** 2

        def compile_rate(self, context):
            index, to_state = context.state_slot("A", "millimolar")
            k = context.parameter("k", "1 / millimolar / second")
            return lambda time, state: k * (state[index] * to_state) ** 2

        def contributions(self, rate):
            return {"A": -rate}

    process = OnlyRate()
    model = ModelBuilder(process_library=ProcessRegistry([process]), requested_processes=("square law",),
                         parameters=ParameterSet([_parameter("k", 0.25, "1 / millimolar / second")])).assemble()
    compiled = ProcessODESolver(model).compile(RunRequest(initial_state={"A": Q_(2.0, "millimolar")}, t_span=(Q_(0.0, "second"), Q_(1.0, "second"))))
    assert compiled.summary()["jacobian_kernels"] == {"square law": JACOBIAN_FINITE_DIFFERENCE}
    assert compiled.jacobian(0.0, np.array([2.0]))[0, 0] == pytest.approx(-0.25 * 2.0 * 2.0, rel=1e-6)
    assert compiled.jacobian(0.0, np.array([-1.0]))[0, 0] == 0.0  # below the orthant the projected rate is flat
