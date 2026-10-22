"""Mass-scaled accessible area and the enzyme-site binding surface law (WP3)."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.provenance import UnknownParameterError
from fungal_model.core.units import Q_
from fungal_model.core.validators import validate_mass_balance, validate_non_negative
from fungal_model.io.model_config import ProcessConfig
from fungal_model.kinetics.langmuir import langmuir_coverage_derivative, langmuir_surface_coverage
from fungal_model.kinetics.site_binding import (
    SITE_BINDING_MATURITY,
    bound_enzyme_derivative_magnitudes,
    bound_enzyme_magnitude,
    site_binding_bound_enzyme,
    site_binding_bound_enzyme_derivatives,
)
from fungal_model.kinetics.surface_kinetics import site_binding_bound_enzyme as reexported_bound_enzyme
from fungal_model.processes import (
    AccessibleSitePool,
    LangmuirAdsorptionModel,
    ModelBuilder,
    ProcessRegistry,
    ProductReleaseMap,
    SurfaceCatalysisModel,
    SurfaceCatalysisProcess,
)
from fungal_model.processes.factories import (
    ProcessBuildContext,
    SiteBindingSurfaceCatalysisFactory,
    SurfaceCatalysisFactory,
    default_foundation_factories,
)
from fungal_model.processes.surface import (
    CONSTANT_UNTIL_DEPLETION,
    MASS_SCALED,
    AccessibleSurfaceAreaModel,
    SiteBindingSurfaceCatalysisProcess,
    mass_scaled_area_factor_derivative,
)
from fungal_model.solvers import ProcessODESolver, RunRequest

SOURCE = "Artificial generic surface benchmark value; no physical claim."


def parameter(symbol: str, value, units: str) -> Parameter:
    return Parameter(
        name=f"benchmark {symbol}",
        symbol=symbol,
        value=value,
        units=units,
        uncertainty=0.0 if value is not None else None,
        source=SOURCE,
        confidence_level="testing",
        notes="Used to test the surface site-balance laws.",
        measurement_method="defined benchmark value",
    )


def richardson_central(function, point: np.ndarray, index: int, scale: float) -> float:
    """(4 D(h/2) - D(h)) / 3 of central differences with a state-scaled step."""

    def central(step: float) -> float:
        upper = np.array(point, dtype=float)
        lower = np.array(point, dtype=float)
        upper[index] += step
        lower[index] -= step
        return (function(upper) - function(lower)) / (2.0 * step)

    step = 1.0e-3 * scale
    return (4.0 * central(step / 2.0) - central(step)) / 3.0


def richardson_forward(function, point: np.ndarray, index: int, scale: float) -> float:
    """2 D(h/2) - D(h) of forward differences (first-order stencil), for the non-negative boundary."""

    def forward(step: float) -> float:
        upper = np.array(point, dtype=float)
        upper[index] += step
        return (function(upper) - function(point)) / step

    step = 1.0e-3 * scale
    return 2.0 * forward(step / 2.0) - forward(step)


# --------------------------------------------------------------------------------------
# Mass-scaled accessible area
# --------------------------------------------------------------------------------------


def surface_parameters(exponent: float) -> ParameterSet:
    return ParameterSet(
        [
            parameter("K_ads", 1.0, "liter / mole"),
            parameter("k_surface", 1.0e-6, "kilogram / meter ** 2 / second"),
            parameter("m_0", 1.0e-6, "kilogram"),
            parameter("n_area", exponent, "dimensionless"),
        ]
    )


def surface_process(area_model: str) -> SurfaceCatalysisProcess:
    if area_model == MASS_SCALED:
        surface_model = AccessibleSurfaceAreaModel.mass_scaled(
            name="dummy chitin-like accessible surface",
            area=Q_(1.0, "meter ** 2"),
            reference_mass_symbol="m_0",
            exponent_symbol="n_area",
        )
    else:
        surface_model = AccessibleSurfaceAreaModel.from_quantity(
            name="dummy chitin-like accessible surface",
            area=Q_(1.0, "meter ** 2"),
        )
    return SurfaceCatalysisProcess(
        name="dummy chitin-like surface cleavage",
        substrate_state="chitin_like_mass",
        enzyme_state="E",
        substrate_units="kilogram",
        enzyme_units="mole / liter",
        accessible_site_pool=AccessibleSitePool(name="dummy accessible linkages", bond_type="generic_linkage"),
        accessible_surface_model=surface_model,
        adsorption_model=LangmuirAdsorptionModel(adsorption_symbol="K_ads", enzyme_units="mole / liter", source=SOURCE),
        catalytic_model=SurfaceCatalysisModel(surface_rate_symbol="k_surface", rate_units="kilogram / second", source=SOURCE),
        product_release_map=ProductReleaseMap.one_to_one(substrate_state="chitin_like_mass", product_state="released_mass"),
        state_units={"chitin_like_mass": "kilogram", "released_mass": "kilogram", "E": "mole / liter"},
    )


def depletion_state(mass: float) -> dict:
    return {
        "chitin_like_mass": Q_(mass, "kilogram"),
        "released_mass": Q_(0.0, "kilogram"),
        "E": Q_(1.0, "mole / liter"),
    }


def assembled(process: SurfaceCatalysisProcess, parameters: ParameterSet):
    return ModelBuilder(
        process_library=ProcessRegistry([process]),
        requested_processes=("surface_catalysis",),
        parameters=parameters,
        validators=[validate_non_negative],
    ).assemble()


@pytest.mark.parametrize("method", ["LSODA", "BDF", "RK45"])
def test_mass_scaled_film_runs_the_report_depletion_case_cheaply(method: str) -> None:
    """The audit case: 1e-6 kg, K = 1 L/mol, E = 1 mol/L, k = 1e-6 kg/m^2/s, A = 1 m^2, 10 s."""

    model = assembled(surface_process(MASS_SCALED), surface_parameters(1.0))
    model = replace(model, solver_settings=replace(model.solver_settings, method=method))
    atol = float(model.solver_settings.atol)
    result = ProcessODESolver(model).run(
        RunRequest(
            initial_state=depletion_state(1.0e-6),
            t_span=(Q_(0.0, "second"), Q_(10.0, "second")),
            t_eval=Q_(np.linspace(0.0, 10.0, 101), "second"),
            validators=(validate_non_negative,),
        )
    )
    mass = result.states["chitin_like_mass"].to("kilogram").magnitude
    assert result.solver_metadata["success"]
    assert result.solver_metadata["nfev"] < 2000
    assert mass.min() >= -atol
    assert all(validation.passed for validation in result.validation_results)
    # n = 1 with theta = 0.5 is exact first-order decay: m(t) = m_0 exp(-k theta A_0 t / m_0).
    # The shipped atol (1e-10 kg) is 1e-4 of the loading, so the global error is set by atol, not rtol.
    expected = 1.0e-6 * np.exp(-0.5 * 1.0e-6 * np.linspace(0.0, 10.0, 101) / 1.0e-6)
    assert mass == pytest.approx(expected, rel=5.0e-3, abs=atol)


@pytest.mark.parametrize("method", ["LSODA", "BDF", "RK45"])
def test_mass_scaled_shrinking_particle_depletes_without_a_step(method: str) -> None:
    model = assembled(surface_process(MASS_SCALED), surface_parameters(2.0 / 3.0))
    model = replace(model, solver_settings=replace(model.solver_settings, method=method))
    result = ProcessODESolver(model).run(
        RunRequest(
            initial_state=depletion_state(1.0e-6),
            t_span=(Q_(0.0, "second"), Q_(10.0, "second")),
            t_eval=Q_(np.linspace(0.0, 10.0, 101), "second"),
            validators=(validate_non_negative,),
        )
    )
    mass = result.states["chitin_like_mass"].to("kilogram").magnitude
    assert result.solver_metadata["success"]
    assert result.solver_metadata["nfev"] < 2000
    assert all(validation.passed for validation in result.validation_results)
    # The particle is gone at t = 3 m_0 / (k theta A_0) = 6 s and stays there.
    assert mass[-1] == pytest.approx(0.0, abs=1.0e-9)
    assert mass[30] == pytest.approx(1.0e-6 * (1.0 - 3.0 / 6.0) ** 3, rel=1.0e-3)


def test_mass_scaled_rate_is_continuous_to_zero() -> None:
    process = surface_process(MASS_SCALED)
    parameters = surface_parameters(1.0)
    rates = [
        process.rate(depletion_state(mass), Q_(0.0, "second"), parameters).to("kilogram / second").magnitude
        for mass in (1.0e-6, 1.0e-9, 1.0e-12, 0.0)
    ]
    assert rates == pytest.approx([5.0e-7, 5.0e-10, 5.0e-13, 0.0], rel=1.0e-12, abs=1.0e-30)


@pytest.mark.parametrize("exponent", [1.0, 2.0 / 3.0, 1.5])
def test_mass_scaled_compiled_jacobian_matches_richardson_in_the_interior(exponent: float) -> None:
    model = assembled(surface_process(MASS_SCALED), surface_parameters(exponent))
    compiled = ProcessODESolver(model).compile(
        RunRequest(initial_state=depletion_state(1.0e-6), t_span=(Q_(0.0, "second"), Q_(1.0, "second")))
    )
    assert compiled.summary()["jacobian_kernels"] == {"dummy chitin-like surface cleavage": "analytic"}
    index = {name: position for position, name in enumerate(compiled.state_names)}
    rate = lambda y: float(compiled.rates(0.0, y)[0])  # noqa: E731
    for mass, enzyme in ((1.0e-6, 1.0), (3.0e-7, 0.2), (1.0e-9, 5.0)):
        point = np.zeros(len(compiled.state_names))
        point[index["chitin_like_mass"]] = mass
        point[index["E"]] = enzyme
        jacobian = compiled.jacobian(0.0, point)
        analytic_mass = -jacobian[index["chitin_like_mass"], index["chitin_like_mass"]]
        analytic_enzyme = -jacobian[index["chitin_like_mass"], index["E"]]
        reference_mass = richardson_central(rate, point, index["chitin_like_mass"], mass)
        reference_enzyme = richardson_central(rate, point, index["E"], enzyme)
        assert analytic_mass == pytest.approx(reference_mass, rel=1.0e-6)
        assert analytic_mass == pytest.approx(exponent * rate(point) / mass, rel=1.0e-12)
        assert analytic_enzyme == pytest.approx(reference_enzyme, rel=1.0e-6)
        coverage_slope = 1.0 / (1.0 + enzyme) ** 2
        assert analytic_enzyme == pytest.approx(1.0e-6 * (mass / 1.0e-6) ** exponent * coverage_slope, rel=1.0e-12)


def test_mass_scaled_compiled_jacobian_at_zero_mass() -> None:
    """n = 1: the one-sided slope A_0/m_0; n < 1: the documented finite choice 0; n > 1: 0."""

    for exponent, expected in ((1.0, 0.5 * 1.0e-6 / 1.0e-6), (2.0 / 3.0, 0.0), (1.5, 0.0)):
        model = assembled(surface_process(MASS_SCALED), surface_parameters(exponent))
        compiled = ProcessODESolver(model).compile(
            RunRequest(initial_state=depletion_state(0.0), t_span=(Q_(0.0, "second"), Q_(1.0, "second")))
        )
        index = {name: position for position, name in enumerate(compiled.state_names)}
        point = np.zeros(len(compiled.state_names))
        point[index["E"]] = 1.0
        jacobian = compiled.jacobian(0.0, point)
        assert -jacobian[index["chitin_like_mass"], index["chitin_like_mass"]] == pytest.approx(expected, abs=1.0e-15)
        assert jacobian[index["chitin_like_mass"], index["E"]] == 0.0
        if exponent == 1.0:
            rate = lambda y: float(compiled.rates(0.0, y)[0])  # noqa: E731
            assert richardson_forward(rate, point, index["chitin_like_mass"], 1.0e-6) == pytest.approx(expected, rel=1.0e-9)
    assert mass_scaled_area_factor_derivative(0.0, 1.0e-6, 1.0) == 1.0e6
    assert mass_scaled_area_factor_derivative(0.0, 1.0e-6, 2.0 / 3.0) == 0.0


def test_constant_law_stays_the_default_and_is_recorded() -> None:
    process = surface_process(CONSTANT_UNTIL_DEPLETION)
    assert process.area_model == CONSTANT_UNTIL_DEPLETION
    data = process.to_dict()
    assert data["area_model"] == CONSTANT_UNTIL_DEPLETION
    assert data["accessible_surface_model"]["area_model"] == CONSTANT_UNTIL_DEPLETION
    assert data["accessible_surface_model"]["maturity"] is None
    assert any("constant_until_depletion" in item for item in data["validity"]["limitations"])
    assert "area_model=constant_until_depletion" in data["validity"]["labels"]
    # Same rate as before for any positive mass, zero at zero: the step is unchanged.
    parameters = surface_parameters(1.0)
    rates = [
        process.rate(depletion_state(mass), Q_(0.0, "second"), parameters).to("kilogram / second").magnitude
        for mass in (1.0, 1.0e-12, 0.0)
    ]
    assert rates == pytest.approx([5.0e-7, 5.0e-7, 0.0])


def test_constant_law_compiled_jacobian_has_no_spurious_substrate_entry() -> None:
    model = assembled(surface_process(CONSTANT_UNTIL_DEPLETION), surface_parameters(1.0))
    compiled = ProcessODESolver(model).compile(
        RunRequest(initial_state=depletion_state(1.0e-6), t_span=(Q_(0.0, "second"), Q_(1.0, "second")))
    )
    assert compiled.summary()["jacobian_kernels"] == {"dummy chitin-like surface cleavage": "analytic"}
    index = {name: position for position, name in enumerate(compiled.state_names)}
    for mass in (1.0e-6, 1.0e-9, 0.0):
        point = np.zeros(len(compiled.state_names))
        point[index["chitin_like_mass"]] = mass
        point[index["E"]] = 1.0
        jacobian = compiled.jacobian(0.0, point)
        assert jacobian[index["chitin_like_mass"], index["chitin_like_mass"]] == 0.0
        expected_enzyme = 0.0 if mass == 0.0 else 1.0e-6 * 0.25
        assert -jacobian[index["chitin_like_mass"], index["E"]] == pytest.approx(expected_enzyme)


def test_mass_scaled_model_records_law_provenance_and_maturity() -> None:
    process = surface_process(MASS_SCALED)
    data = process.to_dict()
    assert data["area_model"] == MASS_SCALED
    assert data["accessible_surface_model"]["maturity"] == "literature_backed_software_tested"
    assert data["accessible_surface_model"]["equation"] == "A(m) = A_0 * (m / m_0)**n"
    names = [assumption["name"] for assumption in data["assumptions"]]
    assert "mass-scaled accessible surface area" in names
    law = next(item for item in data["assumptions"] if item["name"] == "mass-scaled accessible surface area")
    assert "Kadam" in law["source"] and "2004" in law["source"]
    symbols = {item["symbol"] for item in data["required_parameters"]}
    assert {"m_0", "n_area", "K_ads", "k_surface"} <= symbols
    assert any("mass_scaled" in item for item in data["validity"]["limitations"])


def test_mass_scaled_model_refuses_incomplete_or_invalid_definitions() -> None:
    with pytest.raises(ValueError):
        AccessibleSurfaceAreaModel(name="x", area=Q_(1.0, "meter ** 2"), area_model="mass_scaled")
    with pytest.raises(ValueError):
        AccessibleSurfaceAreaModel(name="x", area=Q_(1.0, "meter ** 2"), area_model="shrinking_core")
    with pytest.raises(ValueError):
        AccessibleSurfaceAreaModel(name="x", area=Q_(1.0, "meter ** 2"), reference_mass_symbol="m_0")
    with pytest.raises(ValueError):
        AccessibleSurfaceAreaModel.mass_scaled(name="x", reference_mass_symbol="m_0", exponent_symbol="n")
    process = surface_process(MASS_SCALED)
    with pytest.raises(ValueError):
        process.rate(depletion_state(1.0e-6), Q_(0.0, "second"), ParameterSet([*surface_parameters(1.0)][:-1] + [parameter("n_area", -1.0, "dimensionless")]))


def test_langmuir_coverage_derivative_matches_richardson() -> None:
    constant = Q_(2.0, "liter / mole")
    for enzyme in (0.0, 0.3, 4.0):
        analytic = langmuir_coverage_derivative(free_enzyme=Q_(enzyme, "mole / liter"), adsorption_equilibrium_constant=constant)
        assert str(analytic.to("liter / mole").units) == "liter / mole"
        coverage = lambda y: float(  # noqa: E731
            langmuir_surface_coverage(free_enzyme=Q_(y[0], "mole / liter"), adsorption_equilibrium_constant=constant).magnitude
        )
        if enzyme == 0.0:
            reference = richardson_forward(coverage, np.array([0.0]), 0, 1.0e-2)
        else:
            reference = richardson_central(coverage, np.array([enzyme]), 0, enzyme)
        assert analytic.to("liter / mole").magnitude == pytest.approx(reference, rel=1.0e-7)
        assert analytic.to("liter / mole").magnitude == pytest.approx(2.0 / (1.0 + 2.0 * enzyme) ** 2)


# --------------------------------------------------------------------------------------
# Enzyme-site binding
# --------------------------------------------------------------------------------------


def test_site_binding_reaches_both_michaelis_menten_limits() -> None:
    dissociation = 1.0
    # Enzyme-limited: E_T << S_0 -> conventional MM in sites, E_b = E_T S_0 / (K_d + S_0).
    sites = 1.0
    total = 1.0e-3 * sites
    bound = bound_enzyme_magnitude(total, sites, dissociation)
    assert bound == pytest.approx(total * sites / (dissociation + sites), rel=1.0e-3)
    # Site-limited: S_0 << E_T -> inverse MM, E_b = S_0 E_T / (K_d + E_T).
    total = 1.0
    sites = 1.0e-3 * total
    bound = bound_enzyme_magnitude(total, sites, dissociation)
    assert bound == pytest.approx(sites * total / (dissociation + total), rel=1.0e-3)
    # Exact identities: the root satisfies the balance and never exceeds either pool.
    for total, sites, dissociation in ((0.5, 2.0, 0.1), (3.0, 3.0, 0.0), (1.0e-9, 1.0e-6, 1.0e-6)):
        bound = bound_enzyme_magnitude(total, sites, dissociation)
        assert 0.0 <= bound <= min(total, sites) + 1.0e-15
        assert dissociation * bound == pytest.approx((total - bound) * (sites - bound), rel=1.0e-9, abs=1.0e-18)
    assert bound_enzyme_magnitude(0.0, 0.0, 0.0) == 0.0
    assert bound_enzyme_magnitude(0.0, 1.0, 1.0) == 0.0
    assert bound_enzyme_magnitude(1.0, 0.0, 1.0) == 0.0
    assert bound_enzyme_derivative_magnitudes(3.0, 3.0, 0.0) == (0.0, 0.0)


def test_site_binding_unit_aware_helpers_and_reexport() -> None:
    bound = site_binding_bound_enzyme(
        total_enzyme=Q_(2.0, "micromolar"),
        site_concentration=Q_(1.0e-3, "millimolar"),
        dissociation_constant=Q_(1.0, "micromolar"),
    )
    assert str(bound.units) == "micromolar"
    assert bound.magnitude == pytest.approx(bound_enzyme_magnitude(2.0, 1.0, 1.0))
    by_total, by_sites = site_binding_bound_enzyme_derivatives(
        total_enzyme=Q_(2.0, "micromolar"),
        site_concentration=Q_(1.0, "micromolar"),
        dissociation_constant=Q_(1.0, "micromolar"),
    )
    assert (by_total.magnitude, by_sites.magnitude) == pytest.approx(bound_enzyme_derivative_magnitudes(2.0, 1.0, 1.0))
    assert reexported_bound_enzyme is site_binding_bound_enzyme


def site_binding_parameters(sites_per_mass=2.0e-3) -> ParameterSet:
    return ParameterSet(
        [
            parameter("a_s", sites_per_mass, "mole / kilogram"),
            parameter("K_d", 1.0e-6, "mole / liter"),
            parameter("k_cat_s", 0.5, "1 / second"),
            parameter("V_liquid", 0.1, "liter"),
        ]
    )


def site_binding_process() -> SiteBindingSurfaceCatalysisProcess:
    return SiteBindingSurfaceCatalysisProcess(
        name="dummy keratin-like site-binding cleavage",
        substrate_state="keratin_like_mass",
        enzyme_state="E_total",
        substrate_units="kilogram",
        enzyme_units="mole / liter",
        rate_units="kilogram / second",
        sites_per_mass_symbol="a_s",
        dissociation_constant_symbol="K_d",
        site_turnover_symbol="k_cat_s",
        volume_symbol="V_liquid",
        product_release_map=ProductReleaseMap.one_to_one(substrate_state="keratin_like_mass", product_state="released_mass"),
        primary_source="Andersen et al. 2018 Math Biosci 296:93; Kari et al. 2017 ACS Catal 7:4904.",
        maturity=SITE_BINDING_MATURITY,
        state_units={"keratin_like_mass": "kilogram", "released_mass": "kilogram", "E_total": "mole / liter"},
    )


def site_binding_state(mass: float, enzyme: float) -> dict:
    return {
        "keratin_like_mass": Q_(mass, "kilogram"),
        "released_mass": Q_(0.0, "kilogram"),
        "E_total": Q_(enzyme, "mole / liter"),
    }


def test_site_binding_process_is_generic_and_conserves_total_enzyme() -> None:
    process = site_binding_process()
    assert process.process_type == "site_binding_surface_catalysis"
    assert "E_total" not in {spec.name for spec in process.changed_state_variables}
    model = ModelBuilder(
        process_library=ProcessRegistry([process]),
        requested_processes=("site_binding_surface_catalysis",),
        parameters=site_binding_parameters(),
        validators=[
            validate_non_negative,
            lambda result: validate_mass_balance(result, conserved_weights={"keratin_like_mass": 1.0, "released_mass": 1.0}),
        ],
    ).assemble()
    result = ProcessODESolver(model).run(
        RunRequest(
            initial_state=site_binding_state(1.0e-3, 1.0e-6),
            t_span=(Q_(0.0, "second"), Q_(200.0, "second")),
            t_eval=Q_(np.linspace(0.0, 200.0, 21), "second"),
            validators=(validate_non_negative,),
        )
    )
    enzyme = result.states["E_total"].to("mole / liter").magnitude
    mass = result.states["keratin_like_mass"].to("kilogram").magnitude
    assert np.max(np.abs(enzyme - 1.0e-6)) <= 1.0e-12 * 1.0e-6
    assert mass[-1] < mass[0]
    assert mass.min() >= -float(model.solver_settings.atol)
    assert all(validation.passed for validation in result.validation_results)


def test_site_binding_rate_limits_through_the_process() -> None:
    process = site_binding_process()
    parameters = site_binding_parameters()
    # S_0 = a_s m / V = 2e-3 * 1e-3 / 0.1 = 2e-5 mol/L; K_d = 1e-6.
    sites = 2.0e-3 * 1.0e-3 / 0.1
    # Enzyme-limited (E_T = 1e-3 S_0): v = k E_T S_0/(K_d + S_0) * V / a_s.
    total = 1.0e-3 * sites
    rate = process.rate(site_binding_state(1.0e-3, total), Q_(0.0, "second"), parameters).to("kilogram / second").magnitude
    assert rate == pytest.approx(0.5 * total * sites / (1.0e-6 + sites) * 0.1 / 2.0e-3, rel=1.0e-3)
    # Site-limited (S_0 = 1e-3 E_T): v = k S_0 E_T/(K_d + E_T) * V / a_s = k m E_T/(K_d + E_T).
    total = 1.0e3 * sites
    rate = process.rate(site_binding_state(1.0e-3, total), Q_(0.0, "second"), parameters).to("kilogram / second").magnitude
    assert rate == pytest.approx(0.5 * 1.0e-3 * total / (1.0e-6 + total), rel=1.0e-3)
    # Zero states give zero rate without error.
    assert process.rate(site_binding_state(0.0, total), Q_(0.0, "second"), parameters).magnitude == 0.0
    assert process.rate(site_binding_state(1.0e-3, 0.0), Q_(0.0, "second"), parameters).magnitude == 0.0


def test_site_binding_compiled_kernel_matches_unit_aware_rate_and_richardson() -> None:
    process = site_binding_process()
    parameters = site_binding_parameters()
    model = ModelBuilder(
        process_library=ProcessRegistry([process]),
        requested_processes=("site_binding_surface_catalysis",),
        parameters=parameters,
    ).assemble()
    compiled = ProcessODESolver(model).compile(
        RunRequest(initial_state=site_binding_state(1.0e-3, 1.0e-6), t_span=(Q_(0.0, "second"), Q_(1.0, "second")))
    )
    assert compiled.summary()["jacobian_kernels"] == {"dummy keratin-like site-binding cleavage": "analytic"}
    index = {name: position for position, name in enumerate(compiled.state_names)}
    rate = lambda y: float(compiled.rates(0.0, y)[0])  # noqa: E731
    cases = [(1.0e-3, 1.0e-6), (1.0e-3, 2.0e-5), (5.0e-5, 1.0e-6), (1.0e-6, 1.0e-2)]
    for mass, enzyme in cases:
        point = np.zeros(len(compiled.state_names))
        point[index["keratin_like_mass"]] = mass
        point[index["E_total"]] = enzyme
        unit_aware = process.rate(site_binding_state(mass, enzyme), Q_(0.0, "second"), parameters).to("kilogram / second").magnitude
        assert rate(point) == pytest.approx(unit_aware, rel=1.0e-12)
        jacobian = compiled.jacobian(0.0, point)
        assert -jacobian[index["keratin_like_mass"], index["keratin_like_mass"]] == pytest.approx(
            richardson_central(rate, point, index["keratin_like_mass"], mass), rel=1.0e-6
        )
        assert -jacobian[index["keratin_like_mass"], index["E_total"]] == pytest.approx(
            richardson_central(rate, point, index["E_total"], enzyme), rel=1.0e-6
        )
        assert jacobian[index["E_total"], :].tolist() == [0.0, 0.0, 0.0]
    # Zero states: forward Richardson against the analytic one-sided value.
    for mass, enzyme in ((0.0, 1.0e-6), (1.0e-3, 0.0), (0.0, 0.0)):
        point = np.zeros(len(compiled.state_names))
        point[index["keratin_like_mass"]] = mass
        point[index["E_total"]] = enzyme
        jacobian = compiled.jacobian(0.0, point)
        assert -jacobian[index["keratin_like_mass"], index["keratin_like_mass"]] == pytest.approx(
            richardson_forward(rate, point, index["keratin_like_mass"], 1.0e-4), rel=1.0e-5, abs=1.0e-18
        )
        assert -jacobian[index["keratin_like_mass"], index["E_total"]] == pytest.approx(
            richardson_forward(rate, point, index["E_total"], 1.0e-6), rel=1.0e-5, abs=1.0e-18
        )


def test_site_binding_unknown_sites_per_mass_stays_unknown() -> None:
    process = site_binding_process()
    parameters = site_binding_parameters(sites_per_mass=None)
    with pytest.raises(UnknownParameterError):
        process.rate(site_binding_state(1.0e-3, 1.0e-6), Q_(0.0, "second"), parameters)


def test_site_binding_process_refuses_unsupported_records() -> None:
    kwargs = dict(
        name="x",
        substrate_state="m",
        enzyme_state="E",
        substrate_units="kilogram",
        enzyme_units="mole / liter",
        rate_units="kilogram / second",
        sites_per_mass_symbol="a_s",
        dissociation_constant_symbol="K_d",
        site_turnover_symbol="k",
        volume_symbol="V",
        product_release_map=ProductReleaseMap.one_to_one(substrate_state="m", product_state="p"),
        primary_source="source",
        maturity=SITE_BINDING_MATURITY,
    )
    with pytest.raises(ValueError):
        SiteBindingSurfaceCatalysisProcess(**{**kwargs, "maturity": "exploratory"})
    with pytest.raises(ValueError):
        SiteBindingSurfaceCatalysisProcess(**{**kwargs, "primary_source": "  "})
    with pytest.raises(ValueError):
        SiteBindingSurfaceCatalysisProcess(**{**kwargs, "product_release_map": ProductReleaseMap.one_to_one(substrate_state="other", product_state="p")})
    with pytest.raises(ValueError):
        SiteBindingSurfaceCatalysisProcess(**{**kwargs, "product_release_map": ProductReleaseMap.one_to_one(substrate_state="m", product_state="E")})
    with pytest.raises(ValueError):
        SiteBindingSurfaceCatalysisProcess(**{**kwargs, "rate_units": "mole / second"})
    data = SiteBindingSurfaceCatalysisProcess(**kwargs).to_dict()
    assert data["maturity"] == SITE_BINDING_MATURITY
    assert data["primary_source"] == "source"
    assert "E_b" in data["equation"]


# --------------------------------------------------------------------------------------
# Factories
# --------------------------------------------------------------------------------------


def build_context() -> ProcessBuildContext:
    return ProcessBuildContext(
        state_units={"solid": "kilogram", "released": "kilogram", "enzyme": "mole / liter"},
        product_maps={"release": ProductReleaseMap.one_to_one(substrate_state="solid", product_state="released")},
    )


def surface_config(parameters: dict) -> ProcessConfig:
    return ProcessConfig.from_mapping(
        {
            "id": "configured surface cleavage",
            "process_type": "surface_catalysis",
            "states": {"substrate": "solid", "catalyst": "enzyme", "product": "released"},
            "parameters": {"adsorption_constant": "K_ads", "surface_rate_constant": "k_surface", "accessible_surface_area": "A_0", **parameters},
            "product_map": "release",
        }
    )


def test_surface_factory_defaults_to_the_constant_law_and_reads_the_mass_scaled_keys() -> None:
    factory = SurfaceCatalysisFactory()
    context = build_context()
    default = factory.build(context, surface_config({}))
    assert default.area_model == CONSTANT_UNTIL_DEPLETION
    scaled = factory.build(context, surface_config({"area_model": "mass_scaled", "reference_mass": "m_0", "area_exponent": "n_area"}))
    assert scaled.area_model == MASS_SCALED
    assert scaled.accessible_surface_model.reference_mass_symbol == "m_0"
    assert scaled.accessible_surface_model.exponent_symbol == "n_area"
    assert {item["symbol"] for item in scaled.to_dict()["required_parameters"]} >= {"A_0", "m_0", "n_area"}


def test_surface_factory_refuses_mass_scaled_without_reference_mass() -> None:
    factory = SurfaceCatalysisFactory()
    context = build_context()
    decision = factory.can_build(context, surface_config({"area_model": "mass_scaled", "area_exponent": "n_area"}))
    assert not decision.can_build
    assert "parameters.reference_mass" in decision.missing_fields
    with pytest.raises(ValueError):
        factory.build(context, surface_config({"area_model": "mass_scaled", "area_exponent": "n_area"}))
    unknown = factory.can_build(context, surface_config({"area_model": "amorphous_fraction"}))
    assert not unknown.can_build and "parameters.area_model" in unknown.incompatible_entities
    stray = factory.can_build(context, surface_config({"reference_mass": "m_0"}))
    assert not stray.can_build and "parameters.area_model" in stray.incompatible_entities


def site_binding_config(parameters: dict, **raw) -> ProcessConfig:
    return ProcessConfig.from_mapping(
        {
            "id": "configured site-binding cleavage",
            "process_type": "site_binding_surface_catalysis",
            "states": {"enzyme": "enzyme", "substrate": "solid"},
            "parameters": {"dissociation_constant": "K_d", "site_turnover": "k_cat_s", "volume": "V", "rate_units": "kilogram / second", **parameters},
            "product_map": "release",
            "primary_source": "Andersen et al. 2018 Math Biosci 296:93.",
            "maturity": SITE_BINDING_MATURITY,
            **raw,
        }
    )


def test_site_binding_factory_builds_and_is_registered() -> None:
    assert any(isinstance(factory, SiteBindingSurfaceCatalysisFactory) for factory in default_foundation_factories())
    process = SiteBindingSurfaceCatalysisFactory().build(build_context(), site_binding_config({"sites_per_mass": "a_s"}))
    assert isinstance(process, SiteBindingSurfaceCatalysisProcess)
    assert process.sites_per_mass_symbol == "a_s"
    assert process.rate_units == "kilogram / second"


def test_site_binding_factory_refuses_missing_sites_per_mass_or_bad_records() -> None:
    factory = SiteBindingSurfaceCatalysisFactory()
    context = build_context()
    decision = factory.can_build(context, site_binding_config({}))
    assert not decision.can_build
    assert "parameters.sites_per_mass" in decision.missing_fields
    with pytest.raises(ValueError):
        factory.build(context, site_binding_config({}))
    bad_maturity = factory.can_build(context, site_binding_config({"sites_per_mass": "a_s"}, maturity="exploratory"))
    assert not bad_maturity.can_build and "process.maturity" in bad_maturity.incompatible_entities
    no_source = factory.can_build(context, site_binding_config({"sites_per_mass": "a_s"}, primary_source=" "))
    assert not no_source.can_build and "process.primary_source" in no_source.incompatible_entities
