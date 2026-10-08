"""The analytic sparse Jacobian of the spatial mycelium core (SPATIAL-003).

Verification first: the assembled matrix equals centred finite differences of
the right-hand side on every grid geometry and boundary kind, has no entry
outside the declared stencil, and gives the same trajectories as the
finite-difference paths; then the solver wiring, its refusals and the
regression of default results against the pre-SPATIAL-003 default.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pytest

from fungal_model.core.numerics import SolverSettings
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_
from fungal_model.mycelium import (
    Anastomosis,
    DichotomousBranching,
    FieldDiffusion,
    FieldSpec,
    FirstOrderLoss,
    LateralBranching,
    LocalSecretion,
    LocalUptake,
    MyceliumModel,
    SpatialGrid,
    TipExtension,
    TipMotion,
    Translocation,
)
from fungal_model.mycelium.benchmarks import (
    HYPHA_UNITS,
    SUBSTRATE_UNITS,
    TIP_UNITS,
    artificial_colony_model,
    artificial_front_model,
    artificial_parameter,
    central_inoculum,
)
from fungal_model.mycelium.jacobian import StencilBlock, stencil_colours
from fungal_model.mycelium.model import (
    ANALYTIC_BANDED_JACOBIAN_STRUCTURE,
    ANALYTIC_DENSE_JACOBIAN_STRUCTURE,
    ANALYTIC_JACOBIAN_STRUCTURE,
    BANDED_JACOBIAN_STRUCTURE,
    FINITE_DIFFERENCE_JACOBIAN_STRUCTURE,
    JACOBIAN_STRUCTURE,
)
from fungal_model.transport.geometry import BoundaryConditions1D

ENZYME_UNITS = "nanogram / millimeter ** 2"
TIPS_CM = "1 / centimeter ** 2"
NO_FLUX, PERIODIC = BoundaryConditions1D.no_flux(), BoundaryConditions1D.periodic()


def _length(index: int, millimetres: float = 4.0):
    return artificial_parameter(f"L{index}", millimetres, "millimeter")


GRIDS = {
    "1d_no_flux": lambda: SpatialGrid((_length(0),), (7,), (NO_FLUX,)),
    "1d_periodic": lambda: SpatialGrid((_length(0),), (7,), (PERIODIC,)),
    "1d_periodic_two_cells": lambda: SpatialGrid((_length(0),), (2,), (PERIODIC,)),
    "2d_no_flux": lambda: SpatialGrid((_length(0), _length(1, 3.0)), (5, 4), (NO_FLUX, NO_FLUX)),
    "2d_periodic_and_no_flux": lambda: SpatialGrid((_length(0), _length(1, 3.0)), (4, 5), (PERIODIC, NO_FLUX)),
    "3d_periodic": lambda: SpatialGrid((_length(0), _length(1), _length(2)), (3, 4, 5), (PERIODIC, PERIODIC, PERIODIC)),
    "3d_mixed": lambda: SpatialGrid((_length(0), _length(1), _length(2)), (3, 2, 4), (NO_FLUX, PERIODIC, NO_FLUX)),
    "axisymmetric": lambda: SpatialGrid.axisymmetric(artificial_parameter("R", 3.0, "millimeter"), 9),
}


def _every_process_model(grid: SpatialGrid) -> MyceliumModel:
    """Every shipped process type in every declared option, with fields in more than one unit system."""

    fields = (
        FieldSpec("tips", TIP_UNITS), FieldSpec("hyphae", HYPHA_UNITS), FieldSpec("inactive", HYPHA_UNITS),
        FieldSpec("internal", SUBSTRATE_UNITS), FieldSpec("external", SUBSTRATE_UNITS), FieldSpec("enzyme", ENZYME_UNITS),
        FieldSpec("tips_cm", TIPS_CM),
    )
    substrate = {"substrate_field": "internal", "substrate_units": SUBSTRATE_UNITS}
    processes = (
        TipExtension(name="extension", tip_field="tips", tip_units=TIP_UNITS, hypha_field="hyphae", hypha_units=HYPHA_UNITS, speed_symbol="v",
                     half_saturation_symbol="Kv", cost_field="internal", cost_units=SUBSTRATE_UNITS, cost_symbol="c", **substrate),
        TipExtension(name="extension_cm", tip_field="tips_cm", tip_units=TIPS_CM, hypha_field="hyphae", hypha_units=HYPHA_UNITS, speed_symbol="v_cm"),
        TipMotion(name="motion", tip_field="tips", tip_units=TIP_UNITS, diffusivity_symbol="Dn", drift_field="hyphae", drift_units=HYPHA_UNITS,
                  mobility_symbol="chi", drift_direction=-1),
        TipMotion(name="drift_only", tip_field="tips_cm", tip_units=TIPS_CM, drift_field="external", drift_units=SUBSTRATE_UNITS,
                  mobility_symbol="chi_up", drift_direction=1),
        TipMotion(name="self_repulsion", tip_field="enzyme", tip_units=ENZYME_UNITS, diffusivity_symbol="Dn", drift_field="enzyme",
                  drift_units=ENZYME_UNITS, mobility_symbol="chi_self", drift_direction=-1),
        LateralBranching(name="lateral", tip_field="tips", tip_units=TIP_UNITS, hypha_field="hyphae", hypha_units=HYPHA_UNITS, rate_symbol="b", **substrate),
        LateralBranching(name="lateral_cm", tip_field="tips_cm", tip_units=TIPS_CM, hypha_field="hyphae", hypha_units=HYPHA_UNITS, rate_symbol="b_cm"),
        DichotomousBranching(name="dichotomous", tip_field="tips", tip_units=TIP_UNITS, rate_symbol="alpha"),
        Anastomosis(name="anastomosis", tip_field="tips", tip_units=TIP_UNITS, hypha_field="hyphae", hypha_units=HYPHA_UNITS, rate_symbol="a"),
        FirstOrderLoss(name="inactivation", field="hyphae", field_units=HYPHA_UNITS, rate_symbol="d", product_field="inactive", product_units=HYPHA_UNITS),
        FirstOrderLoss(name="death", field="tips_cm", field_units=TIPS_CM, rate_symbol="d"),
        LocalUptake(name="uptake", external_field="external", external_units=SUBSTRATE_UNITS, internal_field="internal", internal_units=SUBSTRATE_UNITS,
                    hypha_field="hyphae", hypha_units=HYPHA_UNITS, rate_symbol="u", half_saturation_symbol="Ku"),
        LocalUptake(name="uptake_linear", external_field="external", external_units=SUBSTRATE_UNITS, internal_field="internal",
                    internal_units=SUBSTRATE_UNITS, hypha_field="inactive", hypha_units=HYPHA_UNITS, rate_symbol="u_lin"),
        Translocation(name="translocation", internal_field="internal", internal_units=SUBSTRATE_UNITS, diffusivity_symbol="Di", tip_field="tips",
                      tip_units=TIP_UNITS, active_diffusivity_symbol="Da"),
        Translocation(name="medium_diffusion", internal_field="external", internal_units=SUBSTRATE_UNITS, diffusivity_symbol="Di"),
        LocalSecretion(name="secretion", hypha_field="hyphae", hypha_units=HYPHA_UNITS, product_field="enzyme", product_units=ENZYME_UNITS, rate_symbol="k",
                       half_saturation_symbol="Ks", cost_field="internal", cost_units=SUBSTRATE_UNITS, cost_symbol="cs", **substrate),
        LocalSecretion(name="secretion_linear", hypha_field="inactive", hypha_units=HYPHA_UNITS, product_field="enzyme", product_units=ENZYME_UNITS,
                       rate_symbol="k"),
        LocalSecretion(name="secretion_free", hypha_field="hyphae", hypha_units=HYPHA_UNITS, product_field="external", product_units=SUBSTRATE_UNITS,
                       rate_symbol="k_ext", half_saturation_symbol="Ks", **substrate),
        FieldDiffusion(name="enzyme_diffusion", field="enzyme", field_units=ENZYME_UNITS, diffusivity_symbol="De"),
    )
    parameters = ParameterSet([
        artificial_parameter("v", 0.2, "millimeter / hour"), artificial_parameter("v_cm", 0.03, "centimeter / hour"),
        artificial_parameter("Kv", 0.5, SUBSTRATE_UNITS), artificial_parameter("c", 0.1, "microgram / millimeter"),
        artificial_parameter("Dn", 0.02, "millimeter ** 2 / hour"), artificial_parameter("chi", 0.01, "millimeter ** 3 / hour"),
        artificial_parameter("chi_up", 0.05, "millimeter ** 4 / hour / microgram"), artificial_parameter("chi_self", 0.003, "millimeter ** 4 / hour / nanogram"),
        artificial_parameter("b", 0.3, "1 / (millimeter * hour * microgram / millimeter ** 2)"), artificial_parameter("b_cm", 0.2, "1 / (centimeter * hour)"),
        artificial_parameter("alpha", 0.1, "1 / hour"), artificial_parameter("a", 0.2, "millimeter / hour"), artificial_parameter("d", 0.05, "1 / hour"),
        artificial_parameter("u", 0.4, "microgram / millimeter / hour"), artificial_parameter("u_lin", 0.07, "millimeter / hour"),
        artificial_parameter("Ku", 1.0, SUBSTRATE_UNITS), artificial_parameter("Di", 0.1, "millimeter ** 2 / hour"),
        artificial_parameter("Da", 0.05, "millimeter ** 4 / hour"), artificial_parameter("k", 2.0, "nanogram / millimeter / hour"),
        artificial_parameter("k_ext", 0.02, "microgram / millimeter / hour"), artificial_parameter("Ks", 0.5, SUBSTRATE_UNITS),
        artificial_parameter("cs", 0.001, "dimensionless"), artificial_parameter("De", 0.05, "millimeter ** 2 / hour"),
    ])
    return MyceliumModel(grid=grid, fields=fields, processes=processes, parameters=parameters)


def _random_state(compiled, rng: np.random.Generator, *, negative_fraction: float = 0.15) -> np.ndarray:
    """Values of order one, bounded away from zero, some negative, so no difference step crosses a kink."""

    size = compiled.field_count * compiled.model.grid.cell_count
    return rng.uniform(0.2, 2.0, size) * np.where(rng.random(size) < negative_fraction, -1.0, 1.0)


def _centred_differences(compiled, state: np.ndarray) -> np.ndarray:
    jacobian = np.zeros((state.size, state.size))
    steps = np.cbrt(np.finfo(float).eps) * np.maximum(np.abs(state), 1.0)
    for column in range(state.size):
        up, down = state.copy(), state.copy()
        up[column] += steps[column]
        down[column] -= steps[column]
        jacobian[:, column] = (compiled.rhs(0.0, up) - compiled.rhs(0.0, down)) / (2.0 * steps[column])
    return jacobian


# ---------------------------------------------------------------------------
# The matrix
# ---------------------------------------------------------------------------


@lru_cache(maxsize=None)
def _verification_case(kind: str):
    """The every-process model on one grid, a random state, its analytic Jacobian and centred differences."""

    compiled = _every_process_model(GRIDS[kind]()).compile()
    state = _random_state(compiled, np.random.default_rng(sum(map(ord, kind))))
    return compiled, state, compiled.analytic_jacobian(0.0, state), _centred_differences(compiled, state)


@pytest.mark.parametrize("kind", sorted(GRIDS))
def test_analytic_jacobian_equals_centred_differences_on_every_grid_and_boundary(kind: str) -> None:
    compiled, _, analytic, reference = _verification_case(kind)
    assert compiled.has_analytic_jacobian and compiled.summary()["jacobian_structure"] == ANALYTIC_JACOBIAN_STRUCTURE
    scale = np.abs(reference).max()
    dense = analytic.toarray()
    # Centred differences are accurate to about 1e-10 of the largest entry here (measured at most 8e-11).
    assert np.abs(dense - reference).max() <= 1e-8 * scale
    large = np.abs(reference) > 1e-3 * scale
    assert (np.abs(dense - reference)[large] / np.abs(reference)[large]).max() <= 1e-6


@pytest.mark.parametrize("kind", sorted(GRIDS))
def test_no_dependency_lies_outside_the_declared_stencil(kind: str) -> None:
    compiled, state, analytic, reference = _verification_case(kind)
    pattern = compiled.analytic_jacobian_sparsity()
    # The analytic matrix is stored on exactly the declared pattern, which the finite-difference path shares ...
    assert np.array_equal(analytic.indices, pattern.indices) and np.array_equal(analytic.indptr, pattern.indptr)
    assert (compiled.jacobian_sparsity() != pattern.tocsr()).nnz == 0
    assert pattern.nnz > 0 and pattern.shape == (state.size, state.size)
    # ... and the right-hand side depends on nothing outside it: perturbing a state outside a
    # row's stencil leaves that row bit for bit unchanged, so its difference is exactly zero.
    assert np.abs(reference[~pattern.toarray()]).max(initial=0.0) == 0.0


def test_projection_derivative_zeroes_negative_columns_and_takes_the_right_derivative_at_zero() -> None:
    compiled = _every_process_model(GRIDS["2d_no_flux"]()).compile()
    rng = np.random.default_rng(11)
    state = rng.uniform(0.2, 2.0, compiled.field_count * compiled.model.grid.cell_count)
    negative = rng.choice(state.size, 12, replace=False)
    zero = np.setdiff1d(rng.choice(state.size, 12, replace=False), negative)
    state[negative] *= -1.0
    state[zero] = 0.0
    dense = compiled.analytic_jacobian(0.0, state).toarray()
    assert np.all(dense[:, negative] == 0.0)
    for column in zero:
        step = 1e-7
        forward = state.copy()
        forward[column] = step
        right = (compiled.rhs(0.0, forward) - compiled.rhs(0.0, state)) / step
        np.testing.assert_allclose(dense[:, column], right, rtol=1e-5, atol=1e-6 * np.abs(dense).max())


def test_artificial_models_at_simulated_states_match_differences_of_their_right_hand_side() -> None:
    """The benchmark colony (every substrate coupling, drift and active translocation) and the Edelstein front."""

    model = artificial_colony_model(cells=8)
    compiled = model.compile()
    result = compiled.simulate(
        initial_fields=central_inoculum(model.grid, radius_mm=2.0), t_span=(Q_(0, "hour"), Q_(3, "hour")),
        t_eval=Q_([0.0, 3.0], "hour"), solver_settings=SolverSettings(method="BDF", rtol=1e-6, atol=1e-9), record_rates=False,
    )
    # Off the kinks: positive (the projection) and with no two neighbouring drift potentials within many
    # difference steps of each other (the upwind switch at zero face velocity): a smooth oblique ramp.
    rows, columns = np.meshgrid(np.arange(8), np.arange(8), indexing="ij")
    ramp = (0.05 * (1.0 + 0.37 * rows + 0.61 * np.sqrt(2.0) * columns))[np.newaxis] * np.array([1.0, 1.3, 0.7, 1.1]).reshape(4, 1, 1)
    fields = np.stack([result.fields[name].magnitude[-1] for name in model.field_names]) + ramp
    for potential in (fields[0], fields[1]):  # tips steer translocation, hyphae steer tip motion
        assert min(np.abs(np.diff(potential, axis=axis)).min() for axis in (0, 1)) > 1e-4
    state = fields.ravel()
    reference = _centred_differences(compiled, state)
    analytic = compiled.analytic_jacobian(0.0, state).toarray()
    assert np.abs(analytic - reference).max() <= 1e-8 * np.abs(reference).max()
    front = artificial_front_model(cells=40, length_mm=10.0).compile()
    x = front.model.grid.coordinates[0] * 1e3
    state = np.concatenate([np.exp(-x / 2.0) + 0.1, 1.0 + x / 10.0])
    reference = _centred_differences(front, state)
    assert np.abs(front.analytic_jacobian(0.0, state).toarray() - reference).max() <= 1e-8 * np.abs(reference).max()


# ---------------------------------------------------------------------------
# The coloured finite-difference Jacobian on the same stencil
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("extent", [2, 3, 4, 5, 7, 8, 9])
@pytest.mark.parametrize("periodic", [False, True])
def test_stencil_colours_never_put_two_cells_of_one_stencil_in_one_colour(extent: int, periodic: bool) -> None:
    boundary = PERIODIC if periodic else NO_FLUX
    grid = SpatialGrid((_length(0), _length(1)), (extent, 3), (boundary, PERIODIC))
    colours = stencil_colours(grid)
    for i in range(extent):
        for j in range(3):
            stencil = {(i, j)}
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ni, nj = i + di, (j + dj) % 3
                if 0 <= ni < extent:
                    stencil.add((ni, nj))
                elif periodic:
                    stencil.add((ni % extent, nj))
            cells = sorted(stencil)
            assert len({int(colours[cell]) for cell in cells}) == len(cells), (i, j, cells)


@pytest.mark.parametrize("kind", ["1d_no_flux", "1d_periodic", "2d_periodic_and_no_flux", "3d_periodic", "axisymmetric"])
def test_coloured_finite_differences_agree_with_the_analytic_jacobian(kind: str) -> None:
    """Forward differences, one right-hand side per colour, on the declared stencil (about sqrt(eps) accurate).

    The grids include periodic axes of 4, 5 and 7 cells (not multiples of three), where the colouring
    before SPATIAL-003 joined two columns of one colour in a row and mixed their entries.
    """

    compiled = _every_process_model(GRIDS[kind]()).compile()
    state = np.abs(_random_state(compiled, np.random.default_rng(3)))
    analytic = compiled.analytic_jacobian(0.0, state).toarray()
    differences = compiled.jacobian(0.0, state).toarray()
    assert np.abs(differences - analytic).max() <= 1e-6 * np.abs(analytic).max()


def test_finite_differences_carry_no_coupling_across_a_no_flux_wall() -> None:
    """Before SPATIAL-003 the pattern held wrap entries on no-flux axes, and with 800 cells (not a multiple of three)
    the colouring filled ``J[0, 799]`` with ``J[0, 1]``; the declared stencil has no such entry."""

    compiled = artificial_front_model().compile()
    x = compiled.model.grid.coordinates[0] * 1e3
    state = compiled.initial_state({"tips": Q_(np.exp(-x / 20.0), TIP_UNITS), "hyphae": Q_(np.exp(-x / 30.0), HYPHA_UNITS)})
    differences = compiled.jacobian(0.0, state).tocsr()
    assert differences[0, 799] == 0.0 and differences[799, 0] == 0.0
    assert differences[0, 1] == pytest.approx(16.0, rel=1e-6)  # D / dx^2 = 1 / 0.25^2 per hour


# ---------------------------------------------------------------------------
# Solutions
# ---------------------------------------------------------------------------


def _colony(geometry: str = "cartesian", cells: int = 16, hours: float = 6.0, **options):
    model = artificial_colony_model(cells=cells, geometry=geometry)
    settings = options.pop("settings")
    return model.compile().simulate(
        initial_fields=central_inoculum(model.grid), t_span=(Q_(0, "hour"), Q_(hours, "hour")),
        t_eval=Q_(np.linspace(0.0, hours, 4), "hour"), solver_settings=settings, record_rates=False, **options,
    )


def _assert_same_fields(result, reference) -> None:
    for name in reference.fields:
        np.testing.assert_allclose(result.fields[name].magnitude, reference.fields[name].magnitude, rtol=2e-4, atol=1e-7, err_msg=name)


@pytest.mark.parametrize("geometry", ["cartesian", "axisymmetric"])
def test_analytic_and_finite_difference_paths_give_the_same_colony(geometry: str) -> None:
    """Every Jacobian path agrees with LSODA's own differences (the LSODA default before SPATIAL-003) to the documented 2e-4."""

    cells = 16 if geometry == "cartesian" else 60
    reference = _colony(geometry, cells, settings=SolverSettings(method="LSODA", rtol=1e-6, atol=1e-9), jacobian="finite_difference")
    expected_lsoda = BANDED_JACOBIAN_STRUCTURE if geometry == "axisymmetric" else "backend_default"
    assert reference.solver_metadata["jacobian_structure"] == expected_lsoda
    runs = {
        ANALYTIC_JACOBIAN_STRUCTURE: _colony(geometry, cells, settings=SolverSettings(method="BDF", rtol=1e-6, atol=1e-9)),
        FINITE_DIFFERENCE_JACOBIAN_STRUCTURE: _colony(geometry, cells, settings=SolverSettings(method="BDF", rtol=1e-6, atol=1e-9), jacobian="finite_difference"),
        ANALYTIC_BANDED_JACOBIAN_STRUCTURE: _colony(geometry, cells, settings=SolverSettings(method="LSODA", rtol=1e-6, atol=1e-9)),
        "radau": _colony(geometry, cells, settings=SolverSettings(method="Radau", rtol=1e-6, atol=1e-9)),
    }
    for label, result in runs.items():
        _assert_same_fields(result, reference)
        if label != "radau":
            assert result.solver_metadata["jacobian_structure"] == label
    assert runs["radau"].solver_metadata["jacobian_structure"] == ANALYTIC_JACOBIAN_STRUCTURE
    assert runs[ANALYTIC_BANDED_JACOBIAN_STRUCTURE].solver_metadata["jacobian_bandwidths"] == list(
        artificial_colony_model(cells=cells, geometry=geometry).compile().analytic_band_widths()
    )


def test_a_periodic_colony_agrees_between_the_analytic_paths_and_explicit_integration() -> None:
    """The wrap of a periodic line lies outside any band: LSODA's analytic band leaves those couplings out, and records how many."""

    grid = SpatialGrid((_length(0, 6.0),), (24,), (PERIODIC,))
    model = MyceliumModel(
        grid=grid,
        fields=(FieldSpec("tips", TIP_UNITS), FieldSpec("hyphae", HYPHA_UNITS)),
        processes=(
            TipExtension(name="extension", tip_field="tips", tip_units=TIP_UNITS, hypha_field="hyphae", hypha_units=HYPHA_UNITS, speed_symbol="v"),
            TipMotion(name="motion", tip_field="tips", tip_units=TIP_UNITS, diffusivity_symbol="Dn", drift_field="hyphae", drift_units=HYPHA_UNITS,
                      mobility_symbol="chi", drift_direction=-1),
            DichotomousBranching(name="branching", tip_field="tips", tip_units=TIP_UNITS, rate_symbol="alpha"),
            Anastomosis(name="anastomosis", tip_field="tips", tip_units=TIP_UNITS, hypha_field="hyphae", hypha_units=HYPHA_UNITS, rate_symbol="a"),
        ),
        parameters=ParameterSet([
            artificial_parameter("v", 0.5, "millimeter / hour"), artificial_parameter("Dn", 0.05, "millimeter ** 2 / hour"),
            artificial_parameter("chi", 0.01, "millimeter ** 3 / hour"), artificial_parameter("alpha", 0.2, "1 / hour"),
            artificial_parameter("a", 0.3, "millimeter / hour"),
        ]),
    )
    compiled = model.compile()
    x = grid.coordinates[0] * 1e3
    initial = {"tips": Q_(np.where(np.abs(x - 1.0) < 0.6, 1.0, 0.0), TIP_UNITS), "hyphae": Q_(np.where(np.abs(x - 1.0) < 0.6, 1.0, 0.0), HYPHA_UNITS)}

    def run(method: str, **options):
        settings = options.pop("settings", None) or SolverSettings(method=method, rtol=1e-8, atol=1e-11)
        return compiled.simulate(initial_fields=initial, t_span=(Q_(0, "hour"), Q_(8, "hour")), t_eval=Q_([0.0, 4.0, 8.0], "hour"),
                                 solver_settings=settings, record_rates=False, **options)

    reference = run("DOP853")
    banded = run("LSODA", settings=SolverSettings(method="LSODA", rtol=1e-8, atol=1e-11, jacobian="compiled"))
    assert banded.solver_metadata["jacobian_structure"] == ANALYTIC_BANDED_JACOBIAN_STRUCTURE
    pattern = compiled.analytic_jacobian_sparsity().tocoo()
    wraps = int(np.count_nonzero(np.abs(pattern.row % 24 - pattern.col % 24) > 1))
    assert banded.solver_metadata["jacobian_entries_outside_band"] == wraps == 4  # tips on tips and on hyphae, both ends
    for result in (banded, run("BDF"), run("BDF", jacobian="finite_difference"), run("Radau")):
        _assert_same_fields(result, reference)
    totals = run("BDF").spatial_integral("hyphae").magnitude
    assert totals[-1] > totals[0]


@pytest.mark.parametrize("kind", ["2d_no_flux", "2d_periodic_and_no_flux", "3d_mixed", "1d_periodic"])
def test_banded_storage_holds_the_same_matrix_in_cell_major_order(kind: str) -> None:
    """Every entry within one slice of the first axis is in the band; only the wrap of a periodic first axis is left out."""

    compiled = _every_process_model(GRIDS[kind]()).compile()
    grid = compiled.model.grid
    state = _random_state(compiled, np.random.default_rng(5))
    permutation, _ = compiled._cell_major
    lower, upper = compiled.analytic_band_widths()
    dense = compiled.analytic_jacobian(0.0, state).toarray()[np.ix_(permutation, permutation)]
    pattern = compiled.analytic_jacobian_sparsity().toarray()[np.ix_(permutation, permutation)]
    cells = np.arange(state.size) // compiled.field_count  # cell of each cell-major state
    slice_cells = grid.cell_count // grid.shape[0]
    outside = pattern & (np.abs(cells[:, np.newaxis] - cells[np.newaxis, :]) > slice_cells)
    assert compiled.analytic_entries_outside_band() == int(outside.sum())
    assert (int(outside.sum()) > 0) == (grid.periodic_axes[0] and grid.shape[0] > 2)
    rows, columns = np.nonzero(pattern & ~outside)
    assert lower == (rows - columns).max() and upper == (columns - rows).max()
    field_count = compiled.field_count
    assert max(lower, upper) <= field_count * slice_cells + field_count - 1  # one slice of cells and the fields of a cell
    banded = compiled.analytic_jacobian_banded(0.0, state[permutation])
    size = state.size
    rebuilt = np.zeros((size, size))
    for i in range(size):
        for j in range(max(0, i - lower), min(size, i + upper + 1)):
            rebuilt[i, j] = banded[upper + i - j, j]
    np.testing.assert_array_equal(rebuilt, np.where(outside, 0.0, dense))
    two_cells = _every_process_model(GRIDS["1d_periodic_two_cells"]()).compile()
    assert two_cells.jacobian_structure_for(SolverSettings(method="LSODA", jacobian="compiled")) == ANALYTIC_DENSE_JACOBIAN_STRUCTURE


# ---------------------------------------------------------------------------
# Choices, records and refusals
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class _DiffusionWithoutJacobian(FieldDiffusion):
    """A process that offers no analytic Jacobian, as a third-party process may not."""

    def compile_jacobian(self, context):
        del context
        return None


def _model_without_a_kernel() -> MyceliumModel:
    grid = SpatialGrid((_length(0), _length(1)), (5, 4), (PERIODIC, NO_FLUX))
    return MyceliumModel(
        grid=grid,
        fields=(FieldSpec("tips", TIP_UNITS), FieldSpec("enzyme", ENZYME_UNITS)),
        processes=(
            DichotomousBranching(name="branching", tip_field="tips", tip_units=TIP_UNITS, rate_symbol="alpha"),
            _DiffusionWithoutJacobian(name="spread", field="enzyme", field_units=ENZYME_UNITS, diffusivity_symbol="De"),
        ),
        parameters=ParameterSet([artificial_parameter("alpha", 0.1, "1 / hour"), artificial_parameter("De", 0.05, "millimeter ** 2 / hour")]),
    )


def test_a_process_without_a_kernel_falls_back_to_recorded_finite_differences_and_refuses_the_analytic_request() -> None:
    compiled = _model_without_a_kernel().compile()
    assert not compiled.has_analytic_jacobian and compiled.processes_without_analytic_jacobian == ("spread",)
    summary = compiled.summary()
    assert summary["jacobian_kernels"] == {"branching": "analytic", "spread": "none"}
    assert summary["jacobian_structure"] == FINITE_DIFFERENCE_JACOBIAN_STRUCTURE
    bdf = SolverSettings(method="BDF", rtol=1e-6, atol=1e-9)
    assert compiled.jacobian_structure_for(bdf) == FINITE_DIFFERENCE_JACOBIAN_STRUCTURE
    assert compiled.jacobian_structure_for(SolverSettings(method="LSODA")) == "backend_default"  # LSODA's own differences
    with pytest.raises(ValueError, match="spread"):
        compiled.jacobian_structure_for(bdf, "analytic")
    with pytest.raises(ValueError, match="spread"):
        compiled.jacobian_structure_for(SolverSettings(method="LSODA", jacobian="compiled"))
    with pytest.raises(ValueError, match="spread"):
        compiled.analytic_jacobian(0.0, np.ones(compiled.field_count * compiled.model.grid.cell_count))
    # The finite-difference pattern still holds the undeclared process's neighbour couplings.
    state = np.random.default_rng(2).uniform(0.5, 1.5, compiled.field_count * compiled.model.grid.cell_count)
    differences = compiled.jacobian(0.0, state).toarray()
    np.testing.assert_allclose(differences, _centred_differences(compiled, state), rtol=1e-6, atol=1e-6 * np.abs(differences).max())


def test_jacobian_choices_are_recorded_and_contradictions_refused() -> None:
    compiled = artificial_colony_model(cells=6).compile()
    one_axis = artificial_colony_model(cells=12, geometry="axisymmetric").compile()

    def structure(model, method: str, choice: str | None = None, compiled_option: bool = False) -> str:
        settings = SolverSettings(method=method, jacobian="compiled" if compiled_option else "finite_difference_by_backend")
        return model.jacobian_structure_for(settings, choice)

    assert JACOBIAN_STRUCTURE == ANALYTIC_JACOBIAN_STRUCTURE  # the default sparse Jacobian of BDF and Radau
    for method in ("BDF", "Radau"):
        assert structure(compiled, method) == ANALYTIC_JACOBIAN_STRUCTURE
        assert structure(compiled, method, "analytic") == ANALYTIC_JACOBIAN_STRUCTURE
        assert structure(compiled, method, compiled_option=True) == ANALYTIC_JACOBIAN_STRUCTURE
        assert structure(compiled, method, "finite_difference") == FINITE_DIFFERENCE_JACOBIAN_STRUCTURE
    for model in (compiled, one_axis):
        assert structure(model, "LSODA") == ANALYTIC_BANDED_JACOBIAN_STRUCTURE
        assert structure(model, "LSODA", "analytic") == ANALYTIC_BANDED_JACOBIAN_STRUCTURE
        assert structure(model, "LSODA", compiled_option=True) == ANALYTIC_BANDED_JACOBIAN_STRUCTURE
    assert structure(compiled, "LSODA", "finite_difference") == "backend_default"
    assert structure(one_axis, "LSODA", "finite_difference") == BANDED_JACOBIAN_STRUCTURE
    for method in ("RK45", "DOP853"):
        assert structure(compiled, method, "analytic") == "backend_default"
    with pytest.raises(ValueError, match="contradicts"):
        structure(compiled, "BDF", "finite_difference", compiled_option=True)
    with pytest.raises(ValueError, match="one of"):
        structure(compiled, "BDF", "exact")
    assert compiled.summary()["jacobian_kernels"] == {process.name: "analytic" for process in compiled.processes}


def test_stencil_blocks_and_kernels_refuse_inconsistent_declarations() -> None:
    with pytest.raises(ValueError, match="step 0"):
        StencilBlock(0, 0, None, 1)
    with pytest.raises(ValueError, match="step of"):
        StencilBlock(0, 0, 0, 2)
    with pytest.raises(ValueError, match="non-negative"):
        StencilBlock(-1, 0)
    compiled = _every_process_model(GRIDS["1d_no_flux"]()).compile()
    assembler, ids = compiled._stencil
    data = np.zeros(assembler.nnz)
    first = ids[0]
    assert first is not None
    with pytest.raises(ValueError, match="declared blocks"):
        assembler.scatter(data, first, [np.ones(7)])


# ---------------------------------------------------------------------------
# Regression: default results of existing spatial cases
# ---------------------------------------------------------------------------

# Produced by the default paths before SPATIAL-003 (main at 4c75b51: BDF with the coloured
# finite-difference Jacobian on the old pattern, LSODA with its own banded differences) on
# Linux with Python 3.11, numpy 2.4.6 and scipy 1.17.1, by the same calls as the tests
# below. FRONT_TIPS_DOP853 is the front's tip integral from the explicit DOP853 method at
# rtol 1e-11 (no Jacobian involved).
PRE_SPATIAL_003_DEFAULT = {
    "colony_bdf": {
        "integrals": {
            "tips": [1.5625e-06, 1.4797442432165373e-06, 1.3953240389773318e-06, 1.3278043378131662e-06],
            "hyphae": [1.5625e-06, 1.993154884041055e-06, 2.3390764625266137e-06, 2.6365373097816465e-06],
            "internal": [3.125e-06, 3.5888703428870216e-06, 4.100193880156912e-06, 4.620932853243121e-06],
            "external": [0.0003, 0.00029949306416875274, 0.00029894714847453696, 0.0002983966634195444],
        },
        "diagonal": {
            "tips": [9.025096265912135e-16, 4.3915548321927837e-13, 1.7019784442301527e-10, 4.613453507751787e-08, 8.090661567554156e-06, 0.0008144070818957641, 0.03811817778852482, 0.4674308247499331, 0.467430824749933, 0.03811817778852482, 0.0008144070818957641, 8.090661567554156e-06, 4.613453507751788e-08, 1.701978444230153e-10, 4.3915548321927837e-13, 9.025096265912135e-16],
            "hyphae": [2.2564819965457003e-23, 2.23753713046767e-19, 1.8934161452241255e-15, 8.783245004059665e-12, 1.992069223933142e-08, 1.870999449907661e-05, 0.005760646858289336, 1.5782699121475685, 1.5782699121475685, 0.0057606468582893375, 1.8709994499076613e-05, 1.992069223933142e-08, 8.783245004059667e-12, 1.893416145224126e-15, 2.23753713046767e-19, 2.2564819965457003e-23],
            "internal": [2.4177759997115304e-07, 4.120616948470756e-06, 7.328013549905755e-05, 0.000972685474516871, 0.009144558285069692, 0.05822776192585024, 0.2467021831233567, 0.8420370771810295, 0.8420370771810295, 0.24670218312335673, 0.05822776192585025, 0.009144558285069692, 0.000972685474516871, 7.328013549905753e-05, 4.1206169484707556e-06, 2.4177759997115304e-07],
            "external": [3.0, 3.0, 3.0, 2.9999999999994134, 2.999999998209753, 2.999997495534698, 2.998650343414084, 2.0086058031724665, 2.0086058031724665, 2.998650343414084, 2.999997495534698, 2.999999998209753, 2.9999999999994134, 3.0, 3.0, 3.0],
        },
    },
    "front_bdf": {
        "front_mm": [5.12475, 21.085338871281028, 30.87513058387229, 40.41940886398791, 49.97222600933872, 59.5676762393753, 69.20920645222877, 78.88655140433315, 88.59941502468384],
        "hyphae": [0.005, 0.018242628197620205, 0.024891460622661652, 0.03284768534823227, 0.041605356079530816, 0.05074893684955025, 0.06009756150151936, 0.06957259149318533, 0.07913581477472591],
        "tips": [0.005, 0.0006071812032694746, 0.0007350555743770837, 0.0008452264998637973, 0.0008995092530320734, 0.0009264458770123346, 0.000942057974478884, 0.0009523256259069766, 0.0009601779698486949],
    },
    "radial_colony_bdf": {
        "tips": [1.5707963267948962e-06, 2.116732530845309e-06, 2.9787476589254375e-06, 4.309660404872163e-06, 5.968515278209994e-06],
        "hyphae": [1.5707963267948962e-06, 4.632425598605944e-06, 8.495526785207069e-06, 1.408467701136054e-05, 2.2092050934792772e-05],
        "internal": [3.1415926535897925e-06, 3.872305487070229e-06, 5.1469917054370486e-06, 6.577081278920993e-06, 7.98097203949405e-06],
        "external": [0.00047123889803846886, 0.00047020202227927784, 0.0004685410259554195, 0.0004665520213601833, 0.000464347393206717],
    },
    "reserve_radial_bdf": {
        "hours": [1, 6, 12, 24, 36, 48, 62],
        "tip_count": [0.0, 198.910675094828, 5219.991519655687, 7845.008399467085, 9023.351274245739, 8208.80104970057, 7020.203859048426, 5965.221966292935],
        "mycelial_area_cm2": [0.7853981633974483, 0.8992023572737384, 3.6983614116222427, 7.40229915020461, 14.122873838747584, 15.890873968251777, 16.0, 16.0],
    },
    "front_lsoda": {
        "front_mm": [5.12475, 21.085338881062402, 30.8751304753514, 40.419409022080096, 49.972226656793445, 59.56767760259716, 69.20920893587208, 78.88655527081693, 88.59941992561569],
        "hyphae": [0.005, 0.018242628204722954, 0.024891460628776285, 0.03284768533932084, 0.04160535595667093, 0.050748935422447204, 0.060097543208998724, 0.06957236494269105, 0.07913304601615856],
        "tips": [0.005, 0.000607181203419792, 0.0007350555742074097, 0.0008452264959863824, 0.0008995092252145335, 0.0009264455114938069, 0.0009420533452334676, 0.0009522688315206257, 0.0009594855435948895],
    },
    "reserve_radial_lsoda": {
        "hours": [1, 6, 12, 24, 36, 48, 62],
        "tip_count": [0.0, 198.91067444793444, 5219.991366019338, 7845.008393055837, 9023.351206514571, 8208.801084271021, 7020.203818333239, 5965.221923553186],
        "mycelial_area_cm2": [0.7853981633974483, 0.8992023572737384, 3.6983614116222427, 7.40229915020461, 14.122873838747584, 15.890873968251777, 16.0, 16.0],
    },
}
FRONT_TIPS_DOP853 = [0.005, 0.0006071812032563867, 0.0007350555741634992, 0.0008452264972907222, 0.0008995092215649573, 0.0009264454937938754, 0.0009420533069374167, 0.0009522687669663857, 0.0009594854530366044]


def _assert_within_documented_agreement(values, expected, *, atol: float = 0.0) -> None:
    np.testing.assert_allclose(np.asarray(values, dtype=float), np.asarray(expected, dtype=float), rtol=2e-4, atol=atol)


def test_default_colony_results_are_unchanged_within_the_documented_agreement() -> None:
    expected = PRE_SPATIAL_003_DEFAULT["colony_bdf"]
    result = _colony(settings=SolverSettings(method="BDF", rtol=1e-6, atol=1e-9))
    assert result.solver_metadata["jacobian_structure"] == ANALYTIC_JACOBIAN_STRUCTURE
    for name, integrals in expected["integrals"].items():
        _assert_within_documented_agreement(result.spatial_integral(name).magnitude, integrals)
    for name, diagonal in expected["diagonal"].items():
        _assert_within_documented_agreement(np.diagonal(result.fields[name].magnitude[-1]), diagonal, atol=1e-7)
    radial = PRE_SPATIAL_003_DEFAULT["radial_colony_bdf"]
    model = artificial_colony_model(cells=60, geometry="axisymmetric", overrides={"v": 1.0, "b": 0.1})
    result = model.compile().simulate(
        initial_fields=central_inoculum(model.grid), t_span=(Q_(0, "hour"), Q_(10.0, "hour")), t_eval=Q_(np.linspace(0.0, 10.0, 5), "hour"),
        solver_settings=SolverSettings(method="BDF", rtol=1e-7, atol=1e-10), record_rates=False,
    )
    for name, integrals in radial.items():
        _assert_within_documented_agreement(result.spatial_integral(name).magnitude, integrals)


def test_default_front_is_unchanged_and_its_tip_integral_now_meets_the_converged_reference() -> None:
    """The pre-SPATIAL-003 default drifted from the converged tip integral by 7.2e-4 at 80 h (6.0e-5 at 70 h):
    its finite-difference Jacobian coupled the two ends of the no-flux line (``J[0, 799] = J[0, 1]``), which
    slowed Newton (398 Jacobians, 7218 right-hand sides). The front position and hyphae agree with it."""

    expected = PRE_SPATIAL_003_DEFAULT["front_bdf"]
    compiled = artificial_front_model().compile()
    x = compiled.model.grid.coordinates[0] * 1e3
    result = compiled.simulate(
        initial_fields={"tips": Q_(np.where(x < 5.0, 1.0, 0.0), TIP_UNITS), "hyphae": Q_(np.where(x < 5.0, 1.0, 0.0), HYPHA_UNITS)},
        t_span=(Q_(0, "hour"), Q_(80, "hour")), t_eval=Q_(np.arange(0.0, 81.0, 10.0), "hour"),
        solver_settings=SolverSettings(method="BDF", rtol=1e-8, atol=1e-11), record_rates=False,
    )
    _assert_within_documented_agreement(result.front_position("tips", Q_(1e-3, TIP_UNITS)).to("millimeter").magnitude, expected["front_mm"])
    _assert_within_documented_agreement(result.spatial_integral("hyphae").magnitude, expected["hyphae"])
    tips = result.spatial_integral("tips").magnitude
    _assert_within_documented_agreement(tips[:8], expected["tips"][:8])
    np.testing.assert_allclose(tips, FRONT_TIPS_DOP853, rtol=1e-5)
    assert result.solver_metadata["nfev"] < 7218


def test_default_colony_comparison_check_solver_is_unchanged_on_the_plan_model() -> None:
    """The frozen plan's BDF check solve (stage 0 check values, artificial) on its 450-cell radial grid."""

    from pathlib import Path

    from fungal_model.research import colony_comparison as study

    plan = study.load_plan(Path(__file__).resolve().parents[1])
    expected = PRE_SPATIAL_003_DEFAULT["reserve_radial_bdf"]
    result = study.simulate_condition(
        plan, dict(study.STAGE_0_CHECK_VALUES), study.STAGE_0_CHECK_PHI, hours=expected["hours"], solver=study.plan_solver(plan, "check")
    )
    assert result.solver_metadata["jacobian_structure"] == ANALYTIC_JACOBIAN_STRUCTURE
    observed = study.observables(result, plan)
    _assert_within_documented_agreement(observed["tip_count"][1:], expected["tip_count"][1:])
    _assert_within_documented_agreement(observed["mycelial_area_cm2"][1:], expected["mycelial_area_cm2"][1:])


def test_default_lsoda_results_are_unchanged_within_the_documented_agreement() -> None:
    """LSODA's default moved from its own banded differences to the analytic band (one-axis grids here)."""

    expected = PRE_SPATIAL_003_DEFAULT["front_lsoda"]
    compiled = artificial_front_model().compile()
    x = compiled.model.grid.coordinates[0] * 1e3
    result = compiled.simulate(
        initial_fields={"tips": Q_(np.where(x < 5.0, 1.0, 0.0), TIP_UNITS), "hyphae": Q_(np.where(x < 5.0, 1.0, 0.0), HYPHA_UNITS)},
        t_span=(Q_(0, "hour"), Q_(80, "hour")), t_eval=Q_(np.arange(0.0, 81.0, 10.0), "hour"),
        solver_settings=SolverSettings(method="LSODA", rtol=1e-8, atol=1e-11), record_rates=False,
    )
    assert result.solver_metadata["jacobian_structure"] == ANALYTIC_BANDED_JACOBIAN_STRUCTURE
    assert result.solver_metadata["jacobian_bandwidths"] == [2, 2] and result.solver_metadata["jacobian_entries_outside_band"] == 0
    _assert_within_documented_agreement(result.front_position("tips", Q_(1e-3, TIP_UNITS)).to("millimeter").magnitude, expected["front_mm"])
    _assert_within_documented_agreement(result.spatial_integral("hyphae").magnitude, expected["hyphae"])
    _assert_within_documented_agreement(result.spatial_integral("tips").magnitude, expected["tips"])

    from pathlib import Path

    from fungal_model.research import colony_comparison as study

    plan = study.load_plan(Path(__file__).resolve().parents[1])
    expected = PRE_SPATIAL_003_DEFAULT["reserve_radial_lsoda"]
    result = study.simulate_condition(plan, dict(study.STAGE_0_CHECK_VALUES), study.STAGE_0_CHECK_PHI, hours=expected["hours"])
    assert result.solver_metadata["jacobian_structure"] == ANALYTIC_BANDED_JACOBIAN_STRUCTURE
    observed = study.observables(result, plan)
    _assert_within_documented_agreement(observed["tip_count"][1:], expected["tip_count"][1:])
    _assert_within_documented_agreement(observed["mycelial_area_cm2"][1:], expected["mycelial_area_cm2"][1:])
