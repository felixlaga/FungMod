"""Artificial software verification; none of these coefficients are measurements."""
from dataclasses import replace

import numpy as np
import pytest

from fungal_model.chemistry import ElementalComposition, MacrochemicalBalance, MacrochemicalBalanceError, MacrochemicalSpecies
from fungal_model.core.numerics import SolverSettings
from fungal_model.core.parameters import Parameter
from fungal_model.core.provenance import ProvenanceError, UnknownParameterError
from fungal_model.core.units import Q_, UnitError
from fungal_model.fungi import ResourceLimitedCulture, RespiratoryGrowthModel

SOURCE = "Artificial stoichiometric and kinetic test fixture; no biological validation."


def parameter(name, value, units):
    return Parameter(name, name, value, units, None, SOURCE, "testing", SOURCE)


def model(*, substrate="C6H12O6", nitrogen="NH4", n_charge=1, true_yield=3, energies=False):
    species = []
    for name, formula, charge in (("S", substrate, 0), ("N", nitrogen, n_charge), ("O", "O2", 0),
                                 ("X", None, 0), ("C", "CO2", 0), ("W", "H2O", 0), ("H", "H", 1)):
        composition = (ElementalComposition.from_formula(formula, source=SOURCE) if formula else
                       ElementalComposition.from_elements({"C": 1, "H": 1.8, "O": .5, "N": .2}, source=SOURCE))
        species.append(MacrochemicalSpecies(name, composition, charge, SOURCE, formation_gibbs=(
            parameter(f"g_{name}", -400e3 if name == "C" else 0, "J/mol") if energies else None)))
    balance = MacrochemicalBalance("artificial growth", tuple(species), SOURCE,
                                    thermodynamic_conditions="Artificial common conditions at 300 K; no empirical claim.")
    return RespiratoryGrowthModel(balance, "S", "X", parameter("Y", true_yield, "mol/mol"),
                                  parameter("m", .002, "1/h"), SOURCE)


def culture(**changes):
    params = dict(metabolism=model(), nitrogen="N", oxidant="O", reservoir_species=("C", "W", "H"),
                  uptake_capacity=parameter("qmax", .08, "1/h"),
                  substrate_half_saturation=parameter("ks", .001, "mol/L"),
                  nitrogen_half_saturation=parameter("kn", .0001, "mol/L"),
                  oxidant_half_saturation=parameter("ko", .00001, "mol/L"),
                  dilution_rate=parameter("D", 0, "1/h"), gas_transfer_rate=parameter("kla", 0, "1/h"),
                  oxidant_saturation=parameter("Osat", .00025, "mol/L"),
                  feed={n: Q_(0, "mol/L") for n in ("S", "N", "O")}, source=SOURCE)
    params.update(changes)
    return ResourceLimitedCulture(**params)


def state(**changes):
    return {n: Q_(v, "mol/L") for n, v in dict({"S": .02, "X": .001, "N": .01, "O": .1}, **changes).items()}


def test_pirt_rates_and_ammonium_charge_stoichiometry():
    m = model()
    exchange = m.specific_exchange(Q_(.12, "1/h"))
    assert exchange["S"].magnitude == pytest.approx(-.042)
    assert exchange["X"].magnitude == pytest.approx(.12)
    assert exchange["N"].magnitude == pytest.approx(-.024)
    assert exchange["H"].magnitude == pytest.approx(.024)
    assert exchange["C"].magnitude == pytest.approx(6 * .042 - .12)
    assert all(abs(v) < 1e-12 for v in m.growth_reaction.residuals.values())


def test_materially_different_ethanol_nitrate_balance_and_kinetics():
    m = model(substrate="C2H6O", nitrogen="NO3", n_charge=-1, true_yield=1)
    assert m.maintenance_reaction.coefficients["O"] == pytest.approx(-3)
    assert m.maintenance_reaction.coefficients["C"] == pytest.approx(2)
    assert m.growth_reaction.coefficients["N"] == pytest.approx(-.2)
    assert m.growth_reaction.coefficients["H"] == pytest.approx(-.2)
    result = culture(metabolism=m).simulate(initial_state=state(), times=Q_(np.linspace(0, 30, 41), "h"))
    assert max(result.diagnostics["maximum_absolute_balance_residual_mol_L"].values()) < 1e-10
    assert result.concentrations["X"].magnitude[-1] > .001


def test_maintenance_consumes_substrate_without_destroying_biomass():
    exchange = model().specific_exchange(Q_(0, "1/h"))
    assert exchange["X"].magnitude == 0
    assert exchange["S"].magnitude == pytest.approx(-.002)
    assert exchange["O"].magnitude == pytest.approx(-.012)
    assert exchange["C"].magnitude == pytest.approx(.012)
    realized = model().specific_exchange(Q_(0, "1/h"), maintenance_rate=Q_(0, "1/h"))
    assert all(v.magnitude == 0 for v in realized.values())
    with pytest.raises(ValueError, match="cannot exceed"):
        model().specific_exchange(Q_(0, "1/h"), maintenance_rate=Q_(.003, "1/h"))


@pytest.mark.parametrize("missing", ["S", "N", "O"])
def test_resource_exhaustion_stops_the_appropriate_pathway(missing):
    s = state()
    s[missing] = Q_(0, "mol/L")
    rates = culture().rates(s)
    assert rates["growth"].magnitude == 0
    if missing == "N":
        assert rates["maintenance"].magnitude == .002
        assert rates["unmet_maintenance"].magnitude == 0
    else:
        assert rates["maintenance"].magnitude == 0
        assert rates["unmet_maintenance"].magnitude == .002


def test_maintenance_demand_cannot_exceed_available_substrate_uptake():
    c = culture(uptake_capacity=parameter("qmax", .001, "1/h"))
    rates = c.rates(state())
    assert rates["growth"].magnitude == 0
    assert 0 < rates["maintenance"].magnitude < .001
    assert rates["maintenance"].magnitude + rates["unmet_maintenance"].magnitude == pytest.approx(.002)


@pytest.mark.parametrize("method", ["LSODA", "BDF", "Radau", "DOP853"])
def test_batch_depletion_conserves_atoms_charge_and_retains_unmet_maintenance(method):
    c = culture()
    result = c.simulate(initial_state=state(), times=Q_(np.linspace(0, 300, 61), "h"),
                        solver_settings=SolverSettings(method=method, rtol=1e-9, atol=1e-12))
    assert max(result.diagnostics["maximum_absolute_balance_residual_mol_L"].values()) < 1e-10
    assert result.diagnostics["minimum_dynamic_pool_mol_L"] >= -1e-11
    assert result.diagnostics["maximum_unmet_maintenance_per_h"] > .001
    x, s = result.concentrations["X"].magnitude, result.concentrations["S"].magnitude
    exported_carbon = -result.cumulative_boundary_exchange["C"].magnitude
    np.testing.assert_allclose(6 * s + x + exported_carbon, 6 * .02 + .001, rtol=1e-9, atol=1e-11)
    assert result.diagnostics["empirical_validation"] is False


def test_sterile_chemostat_matches_analytic_feed_and_gas_transfer():
    c = culture(dilution_rate=parameter("D", .1, "1/h"), gas_transfer_rate=parameter("kla", 2, "1/h"),
                feed={"S": Q_(.1, "mol/L"), "N": Q_(.01, "mol/L"), "O": Q_(0, "mol/L")})
    s = state(X=0, O=0)
    t = np.linspace(0, 40, 51)
    result = c.simulate(initial_state=s, times=Q_(t, "h"), solver_settings=SolverSettings(rtol=1e-10, atol=1e-13))
    np.testing.assert_allclose(result.concentrations["S"].magnitude, .1 + (.02 - .1) * np.exp(-.1*t), rtol=1e-8)
    expected = 2 * .00025 / 2.1 * (1 - np.exp(-2.1*t))
    np.testing.assert_allclose(result.concentrations["O"].magnitude, expected, rtol=1e-8, atol=1e-12)
    assert max(result.diagnostics["maximum_absolute_balance_residual_mol_L"].values()) < 1e-12


def test_chemostat_washout_and_oxygen_transfer_have_complete_open_balance():
    c = culture(dilution_rate=parameter("D", .4, "1/h"), gas_transfer_rate=parameter("kla", 10, "1/h"),
                feed={"S": Q_(.02, "mol/L"), "N": Q_(.01, "mol/L"), "O": Q_(0, "mol/L")})
    result = c.simulate(initial_state=state(), times=Q_(np.linspace(0, 100, 51), "h"))
    assert result.concentrations["X"].magnitude[-1] < 1e-9
    assert max(result.diagnostics["maximum_absolute_balance_residual_mol_L"].values()) < 1e-10


def test_unit_conversion_and_named_solver_tolerances():
    c = culture()
    names = (*c.names, "extent:growth", "extent:maintenance", *(f"boundary:{n}" for n in c.names))
    units = {n: Q_(1e-9, "mmol/L") for n in names}
    a = c.simulate(initial_state={n: v.to("mmol/mL") for n, v in state().items()}, times=Q_([0, 60], "min"),
                   solver_settings=SolverSettings(atol=units, max_step=Q_(10, "min")))
    b = c.simulate(initial_state=state(), times=Q_([0, 1], "h"), solver_settings=SolverSettings(atol=1e-12))
    for name in c.names:
        np.testing.assert_allclose(a.concentrations[name].magnitude, b.concentrations[name].magnitude, rtol=1e-7)
    with pytest.raises(ValueError, match="exactly"):
        c.simulate(initial_state=state(), times=Q_([0, 1], "h"), solver_settings=SolverSettings(atol={"S": Q_(1e-9, "mol/L")}))


def test_entropy_budget_requires_complete_energies_and_checks_each_pathway():
    args = dict(growth_extent_rate=Q_(.01, "mol/L/h"), maintenance_extent_rate=Q_(.1, "mol/L/h"), temperature=Q_(300, "K"))
    with pytest.raises(MacrochemicalBalanceError, match="formation_gibbs"):
        model().entropy_production(**args)
    m = model(energies=True)
    actual = m.entropy_production(**args)
    expected = -(m.growth_reaction.reaction_gibbs() * args["growth_extent_rate"] +
                 m.maintenance_reaction.reaction_gibbs() * args["maintenance_extent_rate"]) / args["temperature"]
    assert actual.to("W/L/K").magnitude == pytest.approx(expected.to("W/L/K").magnitude)
    bad_species = tuple(replace(s, formation_gibbs=parameter("g_X", 1e7, "J/mol")) if s.name == "X" else s
                        for s in m.balance.species)
    bad = replace(m, balance=replace(m.balance, species=bad_species))
    with pytest.raises(ValueError, match="negative entropy"):
        bad.entropy_production(**args)
    with pytest.raises(ValueError, match="nonnegative"):
        m.entropy_production(**dict(args, growth_extent_rate=Q_(-1, "mol/s")))


@pytest.mark.parametrize("field,value,error", [
    ("source", "", ProvenanceError), ("maturity", "validated", ValueError),
    ("substrate", "X", ValueError), ("substrate", "missing", MacrochemicalBalanceError),
    ("true_yield", parameter("Y", 0, "mol/mol"), ValueError),
    ("true_yield", parameter("Y", None, "mol/mol"), UnknownParameterError),
    ("maintenance_demand", parameter("m", -1, "1/h"), ValueError),
    ("maintenance_demand", parameter("m", 1, "gram"), UnitError),
    ("true_yield", replace(parameter("Y", 3, "mol/mol"), source=None), ProvenanceError),
])
def test_invalid_metabolism_inputs_fail_closed(field, value, error):
    with pytest.raises(error):
        replace(model(), **{field: value})


@pytest.mark.parametrize("changes", [
    {"nitrogen": "O"}, {"oxidant": "missing"}, {"source": ""}, {"reservoir_species": ("C", "W")},
    {"feed": {"S": Q_(0, "mol/L")}}, {"substrate_half_saturation": parameter("ks", 0, "mol/L")},
    {"gas_transfer_rate": parameter("kla", float("nan"), "1/h")},
    {"nitrogen": "C", "reservoir_species": ("N", "W", "H")},
])
def test_invalid_culture_configuration_fails_closed(changes):
    with pytest.raises((ValueError, ProvenanceError)):
        culture(**changes)


@pytest.mark.parametrize("grid", [[0], [1, 1], [2, 1], [0, float("nan")], [[0, 1]]])
def test_invalid_times_fail_before_integration(grid):
    with pytest.raises(ValueError, match="times"):
        culture().simulate(initial_state=state(), times=Q_(grid, "h"))


def test_negative_unknown_and_missing_initial_states_are_rejected():
    for s in ({"S": Q_(1, "mol/L")}, dict(state(), S=Q_(-1, "mol/L")), dict(state(), X=Q_(float("inf"), "mol/L"))):
        with pytest.raises(ValueError):
            culture().simulate(initial_state=s, times=Q_([0, 1], "h"))
