"""The spatial mycelium core: grid, operators, field-process contract, compilation and results."""

from __future__ import annotations

import numpy as np
import pytest

from fungal_model.core.errors import InvalidMechanismError
from fungal_model.core.numerics import SolverSettings
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.units import Q_, UnitError
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
    continuum_process_types,
)
from fungal_model.mycelium.benchmarks import HYPHA_UNITS, SUBSTRATE_UNITS, TIP_UNITS, artificial_parameter
from fungal_model.mycelium.operators import (
    diffusive_tendency,
    divergence,
    drift_face_velocities,
    face_gradient,
    harmonic_face_mean,
    spatial_integral,
    upwind_face_flux,
)
from fungal_model.transport import BoundaryConditions1D, UniformCartesianGrid, finite_volume_laplacian_nd
from fungal_model.transport.cartesian import BoundaryConditionsND
from fungal_model.transport.geometry import BoundaryCondition


def _grid(shape: tuple[int, ...], *, periodic: bool = False, side_mm: float = 4.0) -> SpatialGrid:
    lengths = tuple(artificial_parameter(f"L{axis}", side_mm, "millimeter") for axis in range(len(shape)))
    return SpatialGrid.periodic(lengths, shape) if periodic else SpatialGrid.no_flux(lengths, shape)


# ---------------------------------------------------------------------------
# Grid and operators
# ---------------------------------------------------------------------------


def test_grid_supports_one_to_three_dimensions_and_refuses_bad_declarations() -> None:
    for shape in ((5,), (4, 6), (3, 3, 4)):
        grid = _grid(shape)
        assert grid.ndim == len(shape) and grid.cell_count == int(np.prod(shape))
        assert grid.cell_measure == pytest.approx(np.prod([4e-3 / n for n in shape]))
        assert all(len(axis) == n for axis, n in zip(grid.coordinates, shape, strict=True))
        assert grid.to_dict()["shape"] == list(shape)
    with pytest.raises(ValueError, match="dimensions"):
        _grid((2, 2, 2, 2))
    with pytest.raises(ValueError, match="at least two cells"):
        _grid((1, 4))
    with pytest.raises(ValueError, match="supports"):
        SpatialGrid(
            (artificial_parameter("L", 1.0, "millimeter"),),
            (4,),
            (BoundaryConditions1D(BoundaryCondition("fixed_value", Q_(1.0, "mole / liter")), BoundaryCondition("no_flux")),),
        )
    with pytest.raises(ValueError, match="positive"):
        _grid((4,), side_mm=-1.0)


def test_no_flux_diffusive_tendency_conserves_and_matches_the_transport_laplacian() -> None:
    grid = _grid((6, 5))
    rng = np.random.default_rng(1)
    values = rng.random(grid.shape)
    tendency = diffusive_tendency(values, grid=grid, diffusivity=0.7)
    assert spatial_integral(tendency, grid=grid) == pytest.approx(0.0, abs=1e-15)
    reference = finite_volume_laplacian_nd(
        Q_(values, "mole / liter"),
        grid=UniformCartesianGrid(grid.axis_lengths, grid.shape),
        boundary_conditions=BoundaryConditionsND.no_flux(2),
    )
    np.testing.assert_allclose(tendency, 0.7 * reference.to("mole / liter / meter ** 2").magnitude, rtol=1e-12, atol=1e-9)


def test_periodic_diffusive_tendency_matches_the_transport_laplacian_in_three_dimensions() -> None:
    grid = _grid((4, 5, 3), periodic=True)
    values = np.random.default_rng(2).random(grid.shape)
    reference = finite_volume_laplacian_nd(
        Q_(values, "mole / liter"),
        grid=UniformCartesianGrid(grid.axis_lengths, grid.shape),
        boundary_conditions=BoundaryConditionsND.periodic(3),
    )
    np.testing.assert_allclose(diffusive_tendency(values, grid=grid, diffusivity=1.0), reference.magnitude, rtol=1e-12, atol=1e-9)


def test_upwind_flux_conserves_mass_and_keeps_a_top_hat_non_negative() -> None:
    grid = _grid((40,), side_mm=40.0)
    x = grid.coordinates[0]
    values = np.where((x > 5e-3) & (x < 10e-3), 1.0, 0.0)
    potential = x.copy()  # unit gradient: a uniform interior face velocity equal to the mobility
    velocity = drift_face_velocities(potential, grid=grid, mobility=2.0)[0]
    assert np.allclose(velocity[1:-1], 2.0) and velocity[0] == 0.0 and velocity[-1] == 0.0
    flux = upwind_face_flux(values, velocity, axis=0, periodic=False)
    tendency = divergence([flux], cell_widths=grid.cell_widths)
    assert spatial_integral(tendency, grid=grid) == pytest.approx(0.0, abs=1e-15)
    dt = 0.4 * grid.cell_widths[0] / 2.0
    stepped = values + dt * tendency
    assert stepped.min() >= 0.0 and spatial_integral(stepped, grid=grid) == pytest.approx(spatial_integral(values, grid=grid))
    assert np.argmax(stepped - values) > np.argmax(values)  # mass moves towards higher potential


def test_no_flux_outer_faces_carry_no_gradient_or_advective_flux() -> None:
    values = np.array([3.0, 1.0, 2.0])
    gradient = face_gradient(values, axis=0, cell_width=0.5, periodic=False)
    assert gradient[0] == 0.0 and gradient[-1] == 0.0 and gradient[1] == pytest.approx(-4.0)
    flux = upwind_face_flux(values, np.full(4, -1.0), axis=0, periodic=False)
    assert flux[0] == 0.0 and flux[-1] == 0.0 and flux[1] == pytest.approx(-1.0)


def test_harmonic_face_mean_vanishes_next_to_an_empty_cell() -> None:
    mean = harmonic_face_mean(np.array([2.0, 0.0, 4.0, 4.0]), axis=0, periodic=False)
    assert mean[1] == 0.0 and mean[2] == 0.0 and mean[3] == pytest.approx(4.0) and mean[0] == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Process declarations
# ---------------------------------------------------------------------------


def test_every_shipped_process_type_is_registered_with_assumptions_and_validity() -> None:
    types = continuum_process_types()
    assert set(types) == {
        "field_diffusion", "tip_extension", "tip_motion", "lateral_branching", "dichotomous_branching",
        "anastomosis", "first_order_field_loss", "local_uptake", "translocation", "local_secretion",
    }
    process = TipExtension(name="e", tip_field="n", tip_units=TIP_UNITS, hypha_field="r", hypha_units=HYPHA_UNITS, speed_symbol="v")
    assert process.assumptions[0].source and "Edelstein" in process.assumptions[0].source
    assert {"spatial", "mycelium", "continuum", "growth"} <= set(process.validity.labels)
    assert process.failure_modes and process.rate_units == f"({HYPHA_UNITS}) / (hour)"
    assert [spec.name for spec in process.fields] == ["n", "r"]
    assert process.to_dict()["kernel_kind"] == "vectorised_numpy"


def test_process_declarations_refuse_partial_or_overdrawing_options() -> None:
    with pytest.raises(InvalidMechanismError, match="together"):
        TipExtension(name="e", tip_field="n", tip_units=TIP_UNITS, hypha_field="r", hypha_units=HYPHA_UNITS, speed_symbol="v", substrate_field="s")
    with pytest.raises(InvalidMechanismError, match="overdraw"):
        TipExtension(
            name="e", tip_field="n", tip_units=TIP_UNITS, hypha_field="r", hypha_units=HYPHA_UNITS, speed_symbol="v",
            cost_field="s", cost_units=SUBSTRATE_UNITS, cost_symbol="c",
        )
    with pytest.raises(InvalidMechanismError, match="overdraw"):
        LocalSecretion(
            name="s", hypha_field="r", hypha_units=HYPHA_UNITS, product_field="e", product_units=SUBSTRATE_UNITS, rate_symbol="k",
            cost_field="i", cost_units=SUBSTRATE_UNITS, cost_symbol="c",
        )
    with pytest.raises(InvalidMechanismError, match="diffusivity"):
        TipMotion(name="m", tip_field="n", tip_units=TIP_UNITS)
    with pytest.raises(InvalidMechanismError, match="direction"):
        TipMotion(name="m", tip_field="n", tip_units=TIP_UNITS, diffusivity_symbol="D", drift_direction=2)
    with pytest.raises(InvalidMechanismError, match="together"):
        Translocation(name="t", internal_field="i", internal_units=SUBSTRATE_UNITS, diffusivity_symbol="D", tip_field="n")
    with pytest.raises(InvalidMechanismError, match="together"):
        FirstOrderLoss(name="l", field="n", field_units=TIP_UNITS, rate_symbol="k", product_field="m")


def _two_field_model(tip_units: str = TIP_UNITS, hypha_units: str = HYPHA_UNITS, *, speed: float = 0.5, speed_units: str = "millimeter / hour", process_tip_units: str | None = None) -> MyceliumModel:
    grid = _grid((8,), side_mm=8.0)
    return MyceliumModel(
        grid=grid,
        fields=(FieldSpec("tips", tip_units), FieldSpec("hyphae", hypha_units)),
        processes=(
            TipExtension(name="extension", tip_field="tips", tip_units=process_tip_units or tip_units, hypha_field="hyphae", hypha_units=hypha_units, speed_symbol="v"),
            DichotomousBranching(name="branching", tip_field="tips", tip_units=process_tip_units or tip_units, rate_symbol="alpha"),
        ),
        parameters=ParameterSet([artificial_parameter("v", speed, speed_units), artificial_parameter("alpha", 0.1, "1 / hour")]),
    )


def test_compile_checks_fields_units_and_parameters_before_any_kernel_runs() -> None:
    model = _two_field_model()
    assert model.compile().summary()["process_count"] == 2
    with pytest.raises(InvalidMechanismError, match="does not have"):
        MyceliumModel(grid=model.grid, fields=model.fields[:1], processes=model.processes, parameters=model.parameters).compile()
    with pytest.raises(UnitError):
        _two_field_model(process_tip_units="1 / millimeter ** 3").compile()
    with pytest.raises(KeyError, match="not present"):
        MyceliumModel(grid=model.grid, fields=model.fields, processes=model.processes, parameters=ParameterSet([artificial_parameter("v", 0.5, "millimeter / hour")])).compile()
    with pytest.raises(ValueError, match="non-negative"):
        _two_field_model(speed=-1.0).compile()
    with pytest.raises(UnitError):
        _two_field_model(speed_units="millimeter").compile()
    with pytest.raises(InvalidMechanismError, match="unique"):
        MyceliumModel(grid=model.grid, fields=(FieldSpec("a", TIP_UNITS), FieldSpec("a", TIP_UNITS)), processes=model.processes, parameters=model.parameters)
    with pytest.raises(InvalidMechanismError, match="at least one process"):
        MyceliumModel(grid=model.grid, fields=model.fields, processes=(), parameters=model.parameters)


def test_the_same_physics_in_two_unit_systems_gives_the_same_trajectory() -> None:
    millimetre = _two_field_model().compile()
    centimetre = _two_field_model("1 / centimeter ** 2", "1 / centimeter", speed=0.05, speed_units="centimeter / hour").compile()
    tips = np.linspace(0.0, 1.0, 8)
    times = Q_([0.0, 2.0, 5.0], "hour")
    settings = SolverSettings(rtol=1e-10, atol=1e-13)
    first = millimetre.simulate(initial_fields={"tips": Q_(tips, TIP_UNITS), "hyphae": Q_(0.0, HYPHA_UNITS)}, t_span=(Q_(0, "hour"), Q_(5, "hour")), t_eval=times, solver_settings=settings)
    second = centimetre.simulate(initial_fields={"tips": Q_(tips * 100.0, "1 / centimeter ** 2"), "hyphae": Q_(0.0, "1 / centimeter")}, t_span=(Q_(0, "hour"), Q_(5, "hour")), t_eval=times, solver_settings=settings)
    np.testing.assert_allclose(second.fields["hyphae"].to(HYPHA_UNITS).magnitude, first.fields["hyphae"].magnitude, rtol=1e-8, atol=1e-12)
    np.testing.assert_allclose(second.fields["tips"].to(TIP_UNITS).magnitude, first.fields["tips"].magnitude, rtol=1e-8, atol=1e-12)
    # hyphae grow as v * n with n = n0 exp(alpha t): closed form per cell
    expected = tips * 0.5 * (np.exp(0.1 * 5.0) - 1.0) / 0.1
    np.testing.assert_allclose(first.fields["hyphae"].magnitude[-1], expected, rtol=1e-7)
    rates = first.process_rates
    assert rates is not None and set(rates) == {"extension", "branching"}
    np.testing.assert_allclose(rates["extension"].to("1 / millimeter / hour").magnitude[0], 0.5 * tips, rtol=1e-12)


def test_tendency_kernels_report_each_mechanism_in_its_declared_units() -> None:
    grid = _grid((3,), side_mm=3.0)
    fields = (
        FieldSpec("tips", TIP_UNITS), FieldSpec("hyphae", HYPHA_UNITS), FieldSpec("inactive", HYPHA_UNITS),
        FieldSpec("internal", SUBSTRATE_UNITS), FieldSpec("external", SUBSTRATE_UNITS), FieldSpec("enzyme", "nanogram / millimeter ** 2"),
    )
    processes = (
        LateralBranching(name="lateral", tip_field="tips", tip_units=TIP_UNITS, hypha_field="hyphae", hypha_units=HYPHA_UNITS, rate_symbol="b", substrate_field="internal", substrate_units=SUBSTRATE_UNITS),
        Anastomosis(name="anastomosis", tip_field="tips", tip_units=TIP_UNITS, hypha_field="hyphae", hypha_units=HYPHA_UNITS, rate_symbol="a"),
        FirstOrderLoss(name="inactivation", field="hyphae", field_units=HYPHA_UNITS, rate_symbol="d", product_field="inactive", product_units=HYPHA_UNITS),
        LocalUptake(name="uptake", external_field="external", external_units=SUBSTRATE_UNITS, internal_field="internal", internal_units=SUBSTRATE_UNITS, hypha_field="hyphae", hypha_units=HYPHA_UNITS, rate_symbol="u", half_saturation_symbol="Ku"),
        LocalSecretion(name="secretion", hypha_field="hyphae", hypha_units=HYPHA_UNITS, product_field="enzyme", product_units="nanogram / millimeter ** 2", rate_symbol="k", substrate_field="internal", substrate_units=SUBSTRATE_UNITS, half_saturation_symbol="Ks", cost_field="internal", cost_units=SUBSTRATE_UNITS, cost_symbol="cs"),
        FieldDiffusion(name="enzyme_diffusion", field="enzyme", field_units="nanogram / millimeter ** 2", diffusivity_symbol="De"),
    )
    parameters = ParameterSet([
        artificial_parameter("b", 0.3, "1 / (millimeter * hour * microgram / millimeter ** 2)"),
        artificial_parameter("a", 0.2, "millimeter / hour"),
        artificial_parameter("d", 0.05, "1 / hour"),
        artificial_parameter("u", 0.4, "microgram / millimeter / hour"),
        artificial_parameter("Ku", 1.0, SUBSTRATE_UNITS),
        artificial_parameter("k", 2.0, "nanogram / millimeter / hour"),
        artificial_parameter("Ks", 0.5, SUBSTRATE_UNITS),
        artificial_parameter("cs", 0.001, "dimensionless"),
        artificial_parameter("De", 0.0, "millimeter ** 2 / hour"),
    ])
    compiled = MyceliumModel(grid=grid, fields=fields, processes=processes, parameters=parameters).compile()
    state = compiled.initial_state({
        "tips": Q_(2.0, TIP_UNITS), "hyphae": Q_(3.0, HYPHA_UNITS), "inactive": Q_(0.0, HYPHA_UNITS),
        "internal": Q_(1.5, SUBSTRATE_UNITS), "external": Q_(1.0, SUBSTRATE_UNITS), "enzyme": Q_(0.0, "nanogram / millimeter ** 2"),
    })
    derivative = compiled.unflatten(compiled.rhs(0.0, state))
    uptake = 0.4 * 3.0 * 1.0 / (1.0 + 1.0)
    secretion = 2.0 * 3.0 * 1.5 / (0.5 + 1.5)
    np.testing.assert_allclose(derivative[0], 0.3 * 3.0 * 1.5 - 0.2 * 2.0 * 3.0)  # tips
    np.testing.assert_allclose(derivative[1], -0.05 * 3.0)  # hyphae
    np.testing.assert_allclose(derivative[2], 0.05 * 3.0)  # inactive
    np.testing.assert_allclose(derivative[3], uptake - 0.001 * secretion * 1e-3)  # internal: nanogram cost converted to microgram
    np.testing.assert_allclose(derivative[4], -uptake)
    np.testing.assert_allclose(derivative[5], secretion)
    rates = compiled.rates(0.0, state)
    assert set(rates) == {"lateral", "anastomosis", "inactivation", "uptake", "secretion"}
    np.testing.assert_allclose(rates["secretion"], secretion)


def test_negative_fields_are_projected_in_kernels_but_not_clipped_in_results() -> None:
    compiled = _two_field_model().compile()
    state = compiled.initial_state({"tips": Q_(1.0, TIP_UNITS), "hyphae": Q_(0.0, HYPHA_UNITS)})
    state[0] = -5.0
    derivative = compiled.unflatten(compiled.rhs(0.0, state))
    assert derivative[1][0] == 0.0 and derivative[1][1] == pytest.approx(0.5)
    with pytest.raises(ValueError, match="non-negative"):
        compiled.initial_state({"tips": Q_(-1.0, TIP_UNITS), "hyphae": Q_(0.0, HYPHA_UNITS)})
    with pytest.raises(ValueError, match="exactly"):
        compiled.initial_state({"tips": Q_(1.0, TIP_UNITS)})
    assert compiled.summary()["negative_field_policy"].startswith("kernels evaluated at max(field, 0)")


def test_result_api_reports_integrals_extent_front_and_summary() -> None:
    compiled = _two_field_model().compile()
    x = compiled.model.grid.coordinates[0] * 1e3
    result = compiled.simulate(
        initial_fields={"tips": Q_(np.where(x < 3.0, 1.0, 0.0), TIP_UNITS), "hyphae": Q_(0.0, HYPHA_UNITS)},
        t_span=(Q_(0, "hour"), Q_(2, "hour")),
        t_eval=Q_([0.0, 1.0, 2.0], "hour"),
        solver_settings=SolverSettings(method="RK45", rtol=1e-8, atol=1e-11),
    )
    integral = result.spatial_integral("tips").to("1 / millimeter").magnitude  # a per-area density integrated along a line
    assert integral[0] == pytest.approx(3.0, rel=1e-12)
    assert np.all(np.diff(integral) > 0)
    extent = result.occupied_measure("hyphae", Q_(0.05, HYPHA_UNITS)).to("millimeter").magnitude
    assert extent[0] == 0.0 and extent[-1] == pytest.approx(3.0)
    front = result.front_position("hyphae", Q_(0.05, HYPHA_UNITS)).to("millimeter").magnitude
    assert np.isnan(front[0]) and 2.0 < front[-1] <= 3.5
    summary = result.results_summary()
    assert summary["maturity"] == "exploratory" and summary["fields"]["tips"]["units"] == TIP_UNITS
    assert summary["solver_metadata"]["jacobian_structure"] == "backend_default" and summary["steps"] == 3
    assert {assumption for assumption in summary["assumptions"]} == {"tip_extension_lays_down_hyphae", "dichotomous_branching_proportional_to_tips"}
    assert any("Exploratory" in limitation for limitation in result.limitations)
