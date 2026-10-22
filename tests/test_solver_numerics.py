"""Shared error control, completeness, and sparse spatial numerical contracts."""
import json
from types import SimpleNamespace

import numpy as np
import pytest

from fungal_model.chemistry import Reaction
from fungal_model.core import numerics
from fungal_model.core.numerics import IntegrationError, SolverSettings, solve_checked
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.simulation import SimulationEngine
from fungal_model.core.units import Q_, UnitError
from fungal_model.processes import FirstOrderDecayProcess, HomogeneousMichaelisMentenProcess, ModelBuilder, ProcessRegistry
from fungal_model.solvers import ProcessODESolver, RunRequest
from fungal_model.solvers.compiled import JACOBIAN_ANALYTIC, JACOBIAN_FINITE_DIFFERENCE
from fungal_model.transport._sparsity import cartesian_jacobian_sparsity
from fungal_model.transport import BoundaryConditionsND, ReactionDiffusionEngineND, UniformCartesianGrid
from fungal_model.transport import BoundaryConditions1D, ReactionDiffusionEngine1D, UniformGrid1D


@pytest.mark.parametrize("kwargs", [dict(rtol=0), dict(rtol=np.nan), dict(rtol=1e-18), dict(atol=-1),
                                    dict(atol=np.inf), dict(atol={}), dict(method="guess"),
                                    dict(max_step=Q_(0, "s")), dict(first_step=Q_(-1, "s"))])
def test_invalid_solver_settings_fail_before_integration(kwargs):
    with pytest.raises(ValueError):
        SolverSettings(**kwargs)


def test_named_atol_converts_units_repeats_fields_and_serializes():
    settings = SolverSettings(atol={"trace": Q_(1, "nmol/L"), "bulk": Q_(.001, "g/L")}, first_step=Q_(1, "ms"))
    np.testing.assert_allclose(settings.absolute_tolerances({"bulk": "mg/L", "trace": "mol/L"}, cells=3),
                               [1, 1, 1, 1e-9, 1e-9, 1e-9])
    assert settings.scipy_options({"bulk": "mg/L", "trace": "mol/L"}, "s")["first_step"] == .001
    assert json.loads(json.dumps(settings.to_dict()))["atol"]["trace"]["value"] == 1
    with pytest.raises(ValueError, match="exactly"):
        settings.absolute_tolerances({"trace": "mol/L"})
    with pytest.raises(UnitError):
        settings.absolute_tolerances({"trace": "g", "bulk": "g/L"})


@pytest.mark.parametrize("grid", [[], [0, np.nan], [0, 0], [1, 0], [-1, 1], [0, 2]])
def test_bad_evaluation_times_rejected(grid):
    with pytest.raises(IntegrationError):
        solve_checked(lambda t, y: -y, (0, 1), [1], t_eval=grid)


def test_failed_and_nonfinite_outputs_never_escape_as_partial_results(monkeypatch):
    for success, status, times, values in [(False, -1, [0], [[1]]), (True, 0, [0, 1], [[1, np.nan]]),
                                           (True, 0, [0], [[1]]), (True, 1, [0, 1], [[1, .5]])]:
        monkeypatch.setattr(numerics, "solve_ivp", lambda *a, **k: SimpleNamespace(
            success=success, status=status, t=np.array(times), y=np.array(values), message="test incomplete"))
        with pytest.raises(IntegrationError, match="incomplete"):
            solve_checked(lambda t, y: -y, (0, 1), [1], t_eval=[0, 1])


def test_invalid_rhs_and_initial_state_and_span_rejected():
    with pytest.raises(IntegrationError, match="RHS"):
        solve_checked(lambda t, y: [np.nan], (0, 1), [1])
    with pytest.raises(IntegrationError, match="Initial"):
        solve_checked(lambda t, y: -y, (0, 1), [np.inf])
    with pytest.raises(IntegrationError, match="t_span"):
        solve_checked(lambda t, y: -y, (0, np.nan), [1])
    # Signed mathematical states must not be silently floored in generic numerics.
    result = solve_checked(lambda t, y: -y, (0, 1), [-1], rtol=1e-10, atol=1e-12)
    assert result.y[0, -1] == pytest.approx(-np.exp(-1), rel=1e-9)


def parameter(name, value, units):
    return Parameter(name=name, symbol=name, value=value, units=units,
                     source="Artificial numerical verification only.", uncertainty=None, confidence_level="testing", notes="Artificial software test")


@pytest.mark.parametrize("native", [False, True])
def test_main_engines_preserve_trace_species_with_explicit_tolerance(native):
    settings = SolverSettings(method="BDF", rtol=1e-9,
                              atol={"A": Q_(1e-10, "mol/L"), "B": Q_(1e-22, "mol/L")})
    params = ParameterSet([parameter("k", .1, "1/s")])
    if native:
        process = FirstOrderDecayProcess(name="decay", substrate_state="B", product_state="A",
                                        rate_constant_symbol="k", state_units="mol/L")
        model = ModelBuilder(process_library=ProcessRegistry([process]), requested_processes=("first_order_decay",),
                             parameters=params, solver_settings=settings).assemble()
        result = model.run(initial_state={"A": Q_(1, "mol/L"), "B": Q_(1e-12, "mol/L")},
                           t_span=(Q_(0, "s"), Q_(10, "s")), t_eval=Q_([0, 10], "s"))
        values = result.states
    else:
        reaction = Reaction(name="decay", reactants={"B": 1}, products={"A": 1},
                            rate_law=lambda s, t, p: p.require_quantity("k", "1/s")*s["B"],
                            rate_units="mol/L/s", source="Artificial numerical test")
        model = SimulationEngine([reaction], params, {"A": "mol/L", "B": "mol/L"})
        result = model.simulate(initial_state={"A": Q_(1, "mol/L"), "B": Q_(1e-12, "mol/L")},
                                t_span=(Q_(0, "s"), Q_(10, "s")), t_eval=Q_([0, 10], "s"), solver_settings=settings)
        values = result.species
    assert values["B"].magnitude[-1] == pytest.approx(1e-12*np.exp(-1), rel=1e-7, abs=0)


def test_cartesian_stencil_contains_periodic_neighbours_and_local_species_only():
    matrix = cartesian_jacobian_sparsity((3, 4), 2, local_reactions=True).toarray()
    assert matrix.shape == (24, 24)
    assert matrix[0, 12] and matrix[0, 8] and matrix[0, 3]
    assert not matrix[0, 13]  # other species in a different cell is not cell-local


@pytest.mark.parametrize("shape", [(5, 4), (3, 3, 3)])
@pytest.mark.parametrize("method", ["BDF", "Radau"])
def test_sparse_cartesian_solver_matches_discrete_diffusion(shape, method):
    grid = UniformCartesianGrid(axis_lengths=tuple(parameter(f"L{i}", 1, "m") for i in range(len(shape))), shape=shape)
    x = np.arange(shape[0]) + .5
    initial = np.broadcast_to((1+.2*np.cos(2*np.pi*x/shape[0])).reshape((-1,)+(1,)*(len(shape)-1)), shape).copy()
    engine = ReactionDiffusionEngineND(grid=grid, field_units={"C": "mol/L"},
        boundary_conditions={"C": BoundaryConditionsND.periodic(len(shape))},
        parameters=ParameterSet([parameter("D", .03, "m^2/s")]), diffusion_symbols={"C": "D"})
    result = engine.simulate(initial_fields={"C": Q_(initial, "mol/L")}, t_span=(Q_(0, "s"), Q_(1, "s")),
        t_eval=Q_([0, 1], "s"), solver_settings=SolverSettings(method=method, atol={"C": Q_(1e-11, "mol/L")}))
    eigenvalue = 4*np.sin(np.pi/shape[0])**2 * shape[0]**2
    np.testing.assert_allclose(result.fields["C"].magnitude[-1], 1+(initial-1)*np.exp(-.03*eigenvalue), rtol=1e-7)
    assert result.solver_metadata["jacobian_structure"] == "cartesian_sparse"


def test_sparse_1d_reaction_diffusion_couples_local_species_and_preserves_total():
    grid = UniformGrid1D(length=parameter("L", 1, "m"), n_cells=10)
    reaction = Reaction(name="local conversion", reactants={"A": 1}, products={"B": 1},
        rate_law=lambda s, t, p: p.require_quantity("k", "1/s")*s["A"], rate_units="mol/L/s",
        source="Artificial numerical verification")
    engine = ReactionDiffusionEngine1D(grid=grid, field_units={"A": "mol/L", "B": "mol/L"},
        reactions=[reaction], parameters=ParameterSet([parameter("k", .3, "1/s"), parameter("D", .01, "m^2/s")]),
        boundary_conditions={n: BoundaryConditions1D.periodic() for n in ("A", "B")},
        diffusion_symbols={"A": "D", "B": "D"})
    result = engine.simulate(initial_fields={"A": Q_(np.ones(10), "mol/L"), "B": Q_(np.zeros(10), "mol/L")},
        t_span=(Q_(0, "s"), Q_(2, "s")), t_eval=Q_([0, 2], "s"), solver_settings=SolverSettings(
            method="BDF", atol={"A": Q_(1e-12, "mol/L"), "B": Q_(1e-12, "mol/L")}))
    np.testing.assert_allclose(result.fields["A"].magnitude[-1], np.exp(-.6), rtol=1e-7)
    np.testing.assert_allclose(result.fields["A"].magnitude+result.fields["B"].magnitude, 1, atol=1e-12)
    assert result.solver_metadata["jacobian_structure"] == "cartesian_sparse"


def test_finite_difference_scales_follow_the_tolerances_not_the_units():
    units = {"S": "mole / liter", "P": "mole / liter"}
    np.testing.assert_allclose(SolverSettings().finite_difference_scales(units), [1e-2, 1e-2])
    tight = SolverSettings(atol={"S": Q_(1e-12, "mol/L"), "P": Q_(1, "nmol/L")})
    np.testing.assert_allclose(tight.finite_difference_scales(units), [1e-4, 1e-1])
    np.testing.assert_allclose(SolverSettings(rtol=1e-6, atol=1e-12).finite_difference_scales(units), [1e-6, 1e-6])


class _NumericOnlyMichaelisMenten(HomogeneousMichaelisMentenProcess):
    """The shipped law with its analytic gradient withheld, so the compiled core must difference it."""

    def compile_jacobian(self, context):
        del context
        return None


def _nanomolar_mm_model(process_class, settings, units="mole / liter"):
    process = process_class(name="mm", substrate_state="S", product_state="P", enzyme_state="E", km_symbol="Km",
                            kcat_symbol="kcat", rate_units=f"{units} / second", substrate_units=units, enzyme_units=units)
    params = ParameterSet([parameter("Km", 1e-5, "mole / liter"), parameter("kcat", 10.0, "1 / second")])
    return ModelBuilder(process_library=ProcessRegistry([process]), requested_processes=("homogeneous_michaelis_menten",),
                        parameters=params, solver_settings=settings).assemble()


@pytest.mark.parametrize("settings, bound", [
    (SolverSettings(), 1e-4),
    (SolverSettings(atol={n: Q_(1e-12, "mol/L") for n in "SPE"}), 1e-6),
])
def test_finite_difference_gradient_at_nanomolar_substrate_in_mole_per_liter(settings, bound):
    request = RunRequest(initial_state={"S": Q_(1e-7, "mol/L"), "P": Q_(0, "mol/L"), "E": Q_(1e-8, "mol/L")},
                         t_span=(Q_(0, "s"), Q_(1, "s")))
    numeric = ProcessODESolver(_nanomolar_mm_model(_NumericOnlyMichaelisMenten, settings)).compile(request)
    analytic = ProcessODESolver(_nanomolar_mm_model(HomogeneousMichaelisMentenProcess, settings)).compile(request)
    assert numeric.summary()["jacobian_kernels"] == {"mm": JACOBIAN_FINITE_DIFFERENCE}
    assert analytic.summary()["jacobian_kernels"] == {"mm": JACOBIAN_ANALYTIC}
    probe = {"S": 1e-7, "P": 0.0, "E": 1e-8}  # S = Km / 100 in mol/L: the regime the unit-blind step destroyed
    state = np.array([probe[name] for name in numeric.state_names])
    expected = analytic.jacobian(0.0, state)
    actual = numeric.jacobian(0.0, state)
    column = numeric.state_names.index("S")
    nonzero = expected[:, column] != 0.0  # the enzyme row is identically zero: MM conserves E
    assert np.all(actual[~nonzero, column] == 0.0)
    relative = np.abs(actual[nonzero, column] - expected[nonzero, column]) / np.abs(expected[nonzero, column])
    assert float(np.max(relative)) < bound, relative


def test_identical_nanomolar_trajectories_across_unit_systems_with_per_state_atol():
    settings = SolverSettings.from_config({"atol": {n: {"value": 1e-20, "units": "mol/L"} for n in "SPE"}})
    trajectories = {}
    for units in ("mole / liter", "micromolar", "nanomolar"):
        process = HomogeneousMichaelisMentenProcess(name="mm", substrate_state="S", product_state="P", enzyme_state="E",
                                                    km_symbol="Km", kcat_symbol="kcat", rate_units=f"{units} / second",
                                                    substrate_units=units, enzyme_units=units)
        params = ParameterSet([parameter("Km", 2e-8, "mole / liter"), parameter("kcat", 5.0, "1 / second")])
        model = ModelBuilder(process_library=ProcessRegistry([process]), requested_processes=("homogeneous_michaelis_menten",),
                             parameters=params, solver_settings=settings).assemble()
        result = model.run(initial_state={"S": Q_(1e-7, "mol/L").to(units), "P": Q_(0, units), "E": Q_(1e-9, "mol/L").to(units)},
                           t_span=(Q_(0, "s"), Q_(30, "s")), t_eval=Q_(np.linspace(0, 30, 31), "s"))
        trajectories[units] = result.state("S").to("mol/L").magnitude
    reference = trajectories["nanomolar"]
    for units, values in trajectories.items():
        np.testing.assert_allclose(values, reference, rtol=1e-6, atol=0.0, err_msg=units)


def test_solver_settings_from_config_parses_every_key_and_refuses_the_rest():
    block = {"method": "BDF", "rtol": 1e-9, "atol": {"A": {"value": 1e-12, "units": "mol/L"}},
             "max_step": {"value": 2, "units": "minute"}, "first_step": {"value": 1, "units": "ms"}, "jacobian": "compiled"}
    settings = SolverSettings.from_config(block)
    assert settings.method == "BDF" and settings.rtol == 1e-9 and settings.jacobian == "compiled"
    assert settings.atol["A"] == Q_(1e-12, "mol/L") and settings.max_step == Q_(2, "minute") and settings.first_step == Q_(1, "ms")
    assert SolverSettings.from_config({}) == SolverSettings()
    assert SolverSettings.from_config({"atol": 1e-9}).atol == 1e-9
    with pytest.raises(ValueError, match="unsupported keys"):
        SolverSettings.from_config({"methd": "BDF"})
    with pytest.raises(ValueError, match="'value' and 'units'"):
        SolverSettings.from_config({"max_step": 1.0})
    with pytest.raises(ValueError, match="'value' and 'units'"):
        SolverSettings.from_config({"atol": {"A": 1e-12}})
    with pytest.raises(ValueError, match="rtol"):
        SolverSettings.from_config({"rtol": 0})
    with pytest.raises(ValueError, match="mapping"):
        SolverSettings.from_config(["BDF"])
