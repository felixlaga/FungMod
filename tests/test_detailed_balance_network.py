"""Artificial physical-law verification, not fungal observations or validation."""
from dataclasses import replace

import numpy as np
import pytest
from scipy.linalg import expm

from fungal_model.chemistry import (
    DetailedBalanceNetwork, DetailedBalanceReaction, ElementalComposition,
    MacrochemicalBalance, MacrochemicalSpecies,
)
from fungal_model.core.numerics import SolverSettings
from fungal_model.core.parameters import Parameter
from fungal_model.core.units import Q_, UnitError

SOURCE = "Artificial test coefficients and energies; no empirical interpretation."


def parameter(name, value, units):
    return Parameter(name=name, symbol=name, value=value, units=units, source=SOURCE, uncertainty=None, confidence_level="testing", notes="Artificial software test")


def species(name, formula, energy, charge=0):
    return MacrochemicalSpecies(name, ElementalComposition.from_formula(formula, source=SOURCE), charge, SOURCE,
                               formation_gibbs=parameter(name, energy, "J/mol"))


def network(*, nonlinear=False, cyclic=False):
    members = (species("A", "C2H4", 0), species("B", "C2H4", -1000), species("C", "C2H4", -2000))
    reactions = [DetailedBalanceReaction("one", {"A": 1}, {"B": 1}, parameter("k1", .3, "mol/L/s"), SOURCE),
                 DetailedBalanceReaction("two", {"B": 1}, {"C": 1}, parameter("k2", .1, "mol/L/s"), SOURCE)]
    if cyclic:
        reactions.append(DetailedBalanceReaction("cycle", {"C": 1}, {"A": 1}, parameter("k3", .2, "mol/L/s"), SOURCE))
    if nonlinear:
        # Materially different charged association, with a catalyst on both sides.
        members = (species("X", "H", 0, 1), species("Y", "Cl", -500, -1),
                   species("Z", "HCl", -2000), species("cat", "He", 0))
        reactions = [DetailedBalanceReaction("association", {"X": 1, "Y": 1, "cat": 1},
                                             {"Z": 1, "cat": 1}, parameter("k", .2, "mol/L/s"), SOURCE)]
    balance = MacrochemicalBalance("test network", members, SOURCE, thermodynamic_conditions=SOURCE)
    return DetailedBalanceNetwork(balance=balance, reactions=tuple(reactions), temperature=parameter("T", 300, "K"),
                                  gas_constant=parameter("R", 8.31446261815324, "J/mol/K"),
                                  standard_concentration=parameter("c0", 1, "mol/L"))


@pytest.mark.parametrize("method", ["LSODA", "BDF", "Radau", "DOP853"])
def test_cyclic_relaxation_matches_matrix_exponential_and_dissipates(method):
    model = network(cyclic=True)
    initial = np.array([.8, .15, .05])
    times = np.linspace(0, 30, 100)
    result = model.simulate(initial_state=dict(zip(model.names, [Q_(x, "mol/L") for x in initial], strict=True)),
                            times=Q_(times, "s"), solver_settings=SolverSettings(method=method, rtol=1e-10, atol=1e-12))
    matrix = model._jacobian(initial)
    expected = np.array([expm(matrix*t) @ initial for t in times]).T
    values = np.array([v.magnitude for v in result.concentrations.values()])
    np.testing.assert_allclose(values, expected, rtol=2e-8, atol=2e-10)
    assert np.max(np.diff(result.free_energy_density.magnitude)) <= 1e-9
    assert result.entropy_production_density.magnitude.min() >= -1e-14
    np.testing.assert_allclose(values.sum(axis=0), 1, atol=1e-12)
    # A closed cycle cannot generate a net free-energy driving force.
    assert sum(model.standard_reaction_gibbs) == pytest.approx(0)
    assert result.maturity == "exploratory_software_tested"


def test_free_energy_gradient_identity_and_nonlinear_analytic_jacobian():
    model = network(nonlinear=True)
    c = np.array([.3, .4, .2, .1])
    state = dict(zip(model.names, [Q_(x, "mol/L") for x in c], strict=True))
    row = model.evaluate(state)
    assert row["free_energy_derivative_J_L_s"] == pytest.approx(-300 * sum(row["entropy_production_J_L_K_s"]))
    h = 1e-6
    finite = np.column_stack([
        model.stoichiometry @ (model._fluxes(c + np.eye(4)[i]*h)[2] - model._fluxes(c - np.eye(4)[i]*h)[2]) / (2*h)
        for i in range(4)])
    np.testing.assert_allclose(model._jacobian(c), finite, rtol=1e-8, atol=1e-10)
    gradient = []
    for i in range(4):
        points = [dict(zip(model.names, [Q_(x, "mol/L") for x in c + sign*np.eye(4)[i]*h], strict=True))
                  for sign in (-1, 1)]
        gradient.append((model.evaluate(points[1])["free_energy_density_J_L"]
                         - model.evaluate(points[0])["free_energy_density_J_L"])/(2*h))
    assert np.asarray(gradient) @ (model.stoichiometry @ model._fluxes(c)[2]) == pytest.approx(
        -300*sum(row["entropy_production_J_L_K_s"]), rel=1e-7)
    trajectory = model.simulate(initial_state=state, times=Q_(np.linspace(0, 40, 60), "s"))
    assert max(trajectory.diagnostics["max_conserved_drift_mol_L"].values()) < 1e-12
    np.testing.assert_allclose(trajectory.concentrations["cat"].magnitude, .1)
    assert np.max(np.diff(trajectory.free_energy_density.magnitude)) < 0


def test_zero_initial_product_uses_exact_polynomial_limit_without_activity_floor():
    model = network()
    state = {"A": Q_(1, "mol/L"), "B": Q_(0, "mol/L"), "C": Q_(0, "mol/L")}
    row = model.evaluate(state)
    assert np.isfinite(row["free_energy_density_J_L"])
    assert row["net_rates_mol_L_s"] == pytest.approx([.3, 0])
    assert row["entropy_production_J_L_K_s"] is None
    result = model.simulate(initial_state=state, times=Q_(np.linspace(0, 2, 10), "s"))
    assert result.entropy_production_density is None
    assert result.diagnostics["boundary_diagnostic_count"] == 1
    assert result.concentrations["C"].magnitude[-1] > 0
    assert np.isfinite(model._jacobian(np.array([1., 0, 0]))).all()


def test_equilibrium_and_both_directions_produce_nonnegative_entropy():
    model = network(cyclic=True)
    equilibrium = np.exp(-model.mu_standard/model.rt)
    equilibrium /= equilibrium.sum()
    for initial in (equilibrium, np.array([.99, .005, .005]), np.array([.005, .005, .99])):
        row = model.evaluate(dict(zip(model.names, [Q_(x, "mol/L") for x in initial], strict=True)))
        assert min(row["entropy_production_J_L_K_s"]) >= -1e-25
    np.testing.assert_allclose(model._fluxes(equilibrium)[2], 0, atol=1e-15)


def test_unit_invariance_and_quantity_tolerances():
    model = network()
    result = model.simulate(initial_state={"A": Q_(800, "mmol/L"), "B": Q_(150, "mmol/L"), "C": Q_(50, "mmol/L")},
                            times=Q_([0, .5], "minute"), solver_settings=SolverSettings(
                                method="BDF", atol={n: Q_(1e-9, "mmol/L") for n in model.names}))
    assert result.time.magnitude[-1] == 30
    assert sum(v.magnitude[-1] for v in result.concentrations.values()) == pytest.approx(1)


@pytest.mark.parametrize("problem", ["unbalanced", "charge", "fractional", "missing_species", "source", "unknown_energy", "conditions"])
def test_invalid_physics_and_missing_evidence_fail_closed(problem):
    old = network()
    balance, reactions = old.balance, old.reactions
    if problem == "unbalanced":
        reactions = (replace(reactions[0], products={"B": 2}),)
    elif problem == "charge":
        balance = replace(balance, species=(replace(balance.species[0], charge=1), *balance.species[1:]))
    elif problem == "fractional":
        reactions = (replace(reactions[0], reactants={"A": .5}),)
    elif problem == "missing_species":
        reactions = (replace(reactions[0], products={"unknown": 1}),)
    elif problem == "source":
        reactions = (replace(reactions[0], source=""),)
    elif problem == "unknown_energy":
        balance = replace(balance, species=(replace(balance.species[0], formation_gibbs=None), *balance.species[1:]))
    else:
        balance = replace(balance, thermodynamic_conditions="")
    with pytest.raises(ValueError):
        DetailedBalanceNetwork(balance=balance, reactions=reactions, temperature=old.temperature,
                               gas_constant=old.gas_constant, standard_concentration=old.standard_concentration)


@pytest.mark.parametrize("bad", [-1, np.nan, np.inf])
def test_bad_concentrations_rejected(bad):
    with pytest.raises(ValueError):
        network().evaluate({"A": Q_(bad, "mol/L"), "B": Q_(.1, "mol/L"), "C": Q_(.1, "mol/L")})


def test_array_concentration_is_not_a_scalar():
    with pytest.raises(ValueError, match="scalars"):
        network().evaluate({"A": Q_([1], "mol/L"), "B": Q_(.1, "mol/L"), "C": Q_(.1, "mol/L")})


def test_no_mass_to_molar_guessing():
    with pytest.raises(UnitError):
        network().evaluate({"A": Q_(1, "g/L"), "B": Q_(.1, "mol/L"), "C": Q_(.1, "mol/L")})


@pytest.mark.parametrize("nonlinear", [False, True])
def test_free_energy_equilibrium_solver_matches_long_time_dynamics(nonlinear):
    model = network(nonlinear=nonlinear)
    initial = {n: Q_(.2 + .1*i, "mol/L") for i, n in enumerate(model.names)}
    equilibrium = model.equilibrium(initial)
    trajectory = model.simulate(initial_state=initial, times=Q_([0, 2000], "s"),
                                solver_settings=SolverSettings(method="BDF", rtol=1e-10, atol=1e-12))
    for name in model.names:
        assert trajectory.concentrations[name].magnitude[-1] == pytest.approx(
            equilibrium["concentrations"][name].magnitude, rel=1e-7)
    assert equilibrium["free_energy_density"].magnitude <= model.evaluate(initial)["free_energy_density_J_L"]
    assert equilibrium["maximum_scaled_residual"] < 1e-10
    assert equilibrium["conservation_law_count"] == (3 if nonlinear else 1)


def test_equilibrium_boundary_class_is_explicitly_unsupported():
    with pytest.raises(ValueError, match="strictly positive"):
        network().equilibrium({"A": Q_(1, "mol/L"), "B": Q_(0, "mol/L"), "C": Q_(0, "mol/L")})
