"""Artificial verification of integrated material budgets; no empirical kinetics."""
from dataclasses import replace

import numpy as np
import pytest

from fungal_model.chemistry import ElementalComposition, MacrochemicalBalance, MacrochemicalSpecies
from fungal_model.core.numerics import SolverSettings
from fungal_model.core.parameters import Parameter
from fungal_model.core.provenance import ProvenanceError, UnknownParameterError
from fungal_model.core.units import Q_, UnitError
from fungal_model.fungi import DegradingCulture, ResourceLimitedCulture, RespiratoryGrowthModel, secretion_allocation

SOURCE = "Artificial chemical/kinetic test case, not measured biology."


def p(name, value, units):
    return Parameter(name, name, value, units, None, SOURCE, "testing", SOURCE)


def species(name, formula, charge=0):
    composition = (ElementalComposition.from_formula(formula, source=SOURCE) if isinstance(formula, str) else
                   ElementalComposition.from_elements(formula, source=SOURCE))
    return MacrochemicalSpecies(name, composition, charge, SOURCE)


def model(*, alternative=False, fraction=.1, catalytic=100, decay=.01, dilution=0):
    # Materially different chemistry: polyester -> hydroxyacid with nitrate,
    # versus polysaccharide -> sugar with ammonium. No substrate branch in API.
    s = species("S", "C4H8O3" if alternative else "C6H12O6")
    n = species("N", "NO3" if alternative else "NH4", -1 if alternative else 1)
    o, c, w, h = species("O", "O2"), species("C", "CO2"), species("W", "H2O"), species("H", "H", 1)
    x = species("X", {"C": 1, "H": 1.8, "N": .2, "O": .5})
    e = species("E", {"C": 1, "H": 1.6, "N": .3, "O": .3})
    inactive = replace(e, name="I")
    polymer = species("P", "C4H6O2" if alternative else "C6H10O5")
    metabolism = RespiratoryGrowthModel(MacrochemicalBalance("growth", (s, n, o, x, c, w, h), SOURCE),
        "S", "X", p("Y", 2 if alternative else 3, "mol/mol"), p("m", .001, "1/h"), SOURCE)
    culture = ResourceLimitedCulture(metabolism, "N", "O", ("C", "W", "H"), p("q", .1, "1/h"),
        p("ks", .001, "mol/L"), p("kn", .0001, "mol/L"), p("ko", .00001, "mol/L"),
        p("D", dilution, "1/h"), p("kla", 20, "1/h"), p("osat", .00025, "mol/L"),
        {n: Q_(0, "mol/L") for n in ("S", "N", "O")}, SOURCE)
    hydrolysis = MacrochemicalBalance("hydrolysis", (polymer, s, w), SOURCE).solve({"P": -1})
    secretion = MacrochemicalBalance("secretion", (s, n, o, e, c, w, h), SOURCE).solve({"E": 1, "S": -.5})
    return DegradingCulture(culture, polymer, e, inactive, hydrolysis, secretion,
        p("f", fraction, "dimensionless"), p("kh", catalytic, "1/h"), p("kp", .002, "mol/L"),
        p("kd", decay, "1/h"), Q_(0, "mol/L"), SOURCE)


def state(**changes):
    return {n: Q_(v, "mol/L") for n, v in dict({"S": .001, "X": .001, "N": .02, "O": .00025,
                                               "P": .02, "E": 0, "I": 0}, **changes).items()}


def test_growth_and_secretion_share_one_post_maintenance_carbon_budget():
    m = model(fraction=.3)
    rates = m.rates(state())
    base = m.culture.rates({n: v for n, v in state().items() if n in m.culture.names})
    available = float(base["growth"].magnitude) / 3 * .001
    consumed_for_synthesis = float(rates["growth"].magnitude) / 3 + float(rates["secretion"].magnitude) / 2
    assert consumed_for_synthesis == pytest.approx(available)
    assert rates["growth"].magnitude == pytest.approx(.7 * base["growth"].magnitude * .001)
    assert rates["maintenance"].magnitude == pytest.approx(.001 * .001)
    assert m.secretion.coefficients["N"] == pytest.approx(-.3)
    assert m.secretion.coefficients["H"] == pytest.approx(.3)


@pytest.mark.parametrize("name", ["S", "N", "O"])
def test_secretion_cannot_create_protein_without_its_resources(name):
    rates = model().rates(state(**{name: 0}))
    assert rates["growth"].magnitude == 0
    assert rates["secretion"].magnitude == 0


def test_catalysis_does_not_require_live_biomass_and_does_require_active_enzyme():
    assert model().rates(state(X=0, E=.001))["hydrolysis"].magnitude > 0
    assert model().rates(state(E=0, I=.001))["hydrolysis"].magnitude == 0
    assert model().rates(state(P=0, E=.001))["hydrolysis"].magnitude == 0


def test_zero_seed_and_no_soluble_nutrients_cannot_bootstrap_an_enzyme():
    m = model()
    result = m.simulate(initial_state=state(S=0), times=Q_([0, 100], "h"))
    assert result.concentrations["P"].magnitude[-1] == pytest.approx(.02)
    assert result.concentrations["E"].magnitude[-1] == 0
    assert result.unmet_maintenance_rate.magnitude[-1] == .001


@pytest.mark.parametrize("method", ["LSODA", "BDF", "Radau", "DOP853"])
def test_complete_feedback_loop_conserves_all_material_and_reaches_degradation_threshold(method):
    m = model()
    result = m.simulate(initial_state=state(), times=Q_(np.linspace(0, 120, 241), "h"),
                        solver_settings=SolverSettings(method=method, rtol=1e-9, atol=1e-13, max_step=Q_(.5, "h")))
    assert result.concentrations["E"].magnitude.max() > 0
    assert result.concentrations["I"].magnitude[-1] > 0
    assert result.concentrations["X"].magnitude[-1] > .001
    assert result.concentrations["P"].magnitude[-1] < .002
    assert max(result.diagnostics["maximum_absolute_balance_residual_mol_L"].values()) < 1e-10
    assert result.diagnostics["minimum_pool_mol_L"] > -1e-12
    summary = result.batch_degradation("P")
    assert 0 < summary["threshold_times_hour"]["0.5"] < summary["threshold_times_hour"]["0.9"] < 120
    assert summary["maximum_output_step_hour"] == .5


def test_different_polyester_nitrate_chemistry_conserves_elements_and_charge():
    m = model(alternative=True)
    assert m.hydrolysis.coefficients["W"] == pytest.approx(-1)
    assert m.secretion.coefficients["H"] == pytest.approx(-.3)
    result = m.simulate(initial_state=state(), times=Q_(np.linspace(0, 80, 41), "h"))
    assert result.concentrations["P"].magnitude[-1] < .01
    assert max(result.diagnostics["maximum_absolute_balance_residual_mol_L"].values()) < 1e-10


def test_zero_allocation_reduces_to_existing_respiration_model():
    m = model(fraction=0, catalytic=0)
    times = Q_(np.linspace(0, 20, 41), "h")
    settings = SolverSettings(rtol=1e-10, atol=1e-13)
    before = m.culture.simulate(initial_state={n: v for n, v in state().items() if n in m.culture.names},
                              times=times, solver_settings=settings)
    after = m.simulate(initial_state=state(), times=times, solver_settings=settings)
    for name in m.culture.names:
        np.testing.assert_allclose(after.concentrations[name].magnitude, before.concentrations[name].magnitude, rtol=2e-7, atol=1e-10)


def test_inactivation_preserves_protein_and_matches_analytic_solution_with_dilution():
    m = model(fraction=0, catalytic=0, decay=.1, dilution=.02)
    t = np.linspace(0, 30, 31)
    result = m.simulate(initial_state=state(X=0, E=.002), times=Q_(t, "h"),
                        solver_settings=SolverSettings(rtol=1e-10, atol=1e-13))
    active, inactive = result.concentrations["E"].magnitude, result.concentrations["I"].magnitude
    np.testing.assert_allclose(active, .002*np.exp(-.12*t), rtol=1e-7)
    np.testing.assert_allclose(active+inactive, .002*np.exp(-.02*t), rtol=1e-8)
    assert max(result.diagnostics["maximum_absolute_balance_residual_mol_L"].values()) < 1e-10
    with pytest.raises(ValueError, match="zero dilution"):
        result.batch_degradation("P")


def test_full_allocation_can_secrete_without_biomass_growth():
    rates = model(fraction=1).rates(state())
    assert rates["growth"].magnitude == 0
    assert rates["secretion"].magnitude > 0


def test_unknown_threshold_is_explicit_and_wrong_observable_is_rejected():
    result = model(catalytic=0).simulate(initial_state=state(), times=Q_([0, 1], "h"))
    assert result.batch_degradation("P")["threshold_times_hour"] == {"0.5": None, "0.9": None}
    for fractions in ((0.,), (1.1,), (.5, .5), (float("nan"),)):
        with pytest.raises(ValueError, match="Threshold"):
            result.batch_degradation("P", fractions=fractions)
    with pytest.raises(ValueError, match="configured"):
        result.batch_degradation("X")


def test_allocation_conversion_has_explicit_chemical_basis_and_provenance():
    f = secretion_allocation(protein_per_biomass=p("r", .1, "g/g"), biomass_formula_mass=p("mx", 30, "g/mol"),
                            protein_formula_mass=p("me", 20, "g/mol"), growth_yield=p("yx", 3, "mol/mol"),
                            secretion_yield=p("ye", 2, "mol/mol"))
    assert f.value == pytest.approx(.15/(2/3+.15))
    assert f.uncertainty is None
    assert "Conditional" in f.notes


@pytest.mark.parametrize("field,value,error", [
    ("source", "", ProvenanceError), ("maturity", "validated", ValueError),
    ("allocation_fraction", p("f", 1.1, "dimensionless"), ValueError),
    ("allocation_fraction", p("f", None, "dimensionless"), UnknownParameterError),
    ("catalytic_capacity", p("k", -1, "1/h"), ValueError),
    ("enzyme_inactivation_rate", p("k", 1, "g"), UnitError),
    ("substrate_half_saturation", p("k", 0, "mol/L"), ValueError),
    ("feed_substrate", Q_(-1, "mol/L"), ValueError),
])
def test_invalid_parameters_fail_closed(field, value, error):
    with pytest.raises(error):
        replace(model(), **{field: value})


def test_inconsistent_or_tampered_chemistry_is_rejected():
    m = model()
    with pytest.raises(ValueError, match="identical"):
        replace(m, inactive_enzyme=species("I", "C"))
    with pytest.raises(ValueError, match="distinct"):
        replace(m, active_enzyme=replace(m.active_enzyme, name="X"))
    bad = replace(m.hydrolysis, coefficients=dict(m.hydrolysis.coefficients, S=2))
    with pytest.raises(ValueError, match="conserve"):
        replace(m, hydrolysis=bad)
    bad_species = tuple(replace(s, charge=1) if s.name == "S" else s for s in m.hydrolysis.balance.species)
    bad = replace(m.hydrolysis, balance=replace(m.hydrolysis.balance, species=bad_species))
    with pytest.raises(ValueError, match="Conflicting"):
        replace(m, hydrolysis=bad)


def test_initial_values_times_and_tolerances_fail_closed():
    m = model()
    with pytest.raises(ValueError, match="exactly"):
        m.simulate(initial_state={"P": Q_(1, "mol/L")}, times=Q_([0, 1], "h"))
    with pytest.raises(ValueError, match="nonnegative"):
        m.rates(state(E=-1))
    for times in ([0], [1, 0], [0, float("nan")]):
        with pytest.raises(ValueError, match="times"):
            m.simulate(initial_state=state(), times=Q_(times, "h"))
    with pytest.raises(ValueError, match="exactly"):
        m.simulate(initial_state=state(), times=Q_([0, 1], "h"), solver_settings=SolverSettings(atol={"P": Q_(1e-12, "mol/L")}))


@pytest.mark.parametrize("pools", [(.001, .001, .02, .00025, .02, .0001, .0002),
    (1e-7, .001, .02, 1e-6, .02, .0001, .0002), (-.001, .001, -.002, .00025, -.002, .0001, 0)])
def test_piecewise_rate_jacobian_matches_independent_finite_differences(pools):
    m = model(fraction=.3)
    values = np.array(pools)
    analytic = m._rate_jacobian_kernel()(values)
    numerical = np.zeros_like(analytic)
    for j in range(7):
        step = max(abs(values[j])*1e-5, 1e-12)
        displacement = np.eye(7)[j]*step
        numerical[:, j] = (m._rate_kernel()(values+displacement)[0]-m._rate_kernel()(values-displacement)[0])/(2*step)
    np.testing.assert_allclose(analytic, numerical, rtol=1e-7, atol=1e-9)


def test_full_augmented_jacobian_has_no_fictitious_ledger_feedback(monkeypatch):
    from fungal_model.fungi import degradation, respiration
    from fungal_model.core.numerics import solve_checked

    def checking_solve(fun, span, initial, **options):
        # Independent central differences cover dynamic rows, reaction extents
        # and boundary exchanges; use interior pools away from physical kinks.
        y = initial.copy()
        y[:4 if len(initial) == 10 else 7] += .002
        analytic = options["jac"](0, y)
        numerical = np.empty_like(analytic)
        for j in range(len(y)):
            d = np.eye(len(y))[j]*1e-8
            numerical[:, j] = (fun(0, y+d)-fun(0, y-d))/(2e-8)
        np.testing.assert_allclose(analytic, numerical, rtol=1e-6, atol=1e-8)
        return solve_checked(fun, span, initial, **options)

    monkeypatch.setattr(degradation, "solve_checked", checking_solve)
    monkeypatch.setattr(respiration, "solve_checked", checking_solve)
    m = model(dilution=.01)
    m.simulate(initial_state=state(E=.001), times=Q_([0, 1], "h"), solver_settings=SolverSettings(method="BDF"))
    m.culture.simulate(initial_state={n: v for n, v in state().items() if n in m.culture.names},
                       times=Q_([0, 1], "h"), solver_settings=SolverSettings(method="Radau"))
