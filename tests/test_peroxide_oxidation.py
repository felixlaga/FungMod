"""Synthetic oxidative cleavage checks; no experimental validation is implied."""

from __future__ import annotations

from pathlib import Path
import csv
import json
import numpy as np
import pytest
from scipy.integrate import solve_ivp

from fungal_model.core.kernels import KernelContext
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.kinetics.peroxide import peroxide_rate_and_gradient, peroxide_inactivation_rate_and_gradient
from fungal_model.processes.peroxide import PeroxideOxidativeCleavageProcess, PeroxideInactivationProcess
from fungal_model.processes import ModelBuilder, ProcessRegistry
from fungal_model.processes.homogeneous import FirstOrderDecayProcess, MassActionProcess
from fungal_model.io.model_config import load_model_config
from fungal_model.workflows.configured_model import ConfiguredInputLoader, ConfiguredProcessAssembler
from fungal_model.solvers import ProcessODESolver, RunRequest

SOURCE = "Synthetic peroxide benchmark, not scientific data."
ROOT = Path(__file__).resolve().parents[1]


def system(label):
    # These are intentionally distinct hypothetical preparations, not transferred constants.
    # Chitin: substrate-protected, peroxide-rich closed batch.
    # Cellulose: weak protection and low peroxide with an explicit fed/decaying boundary.
    fed = label == "cellulose"
    substrate_units, peroxide_units, enzyme_units = (
        ("micromolar", "millimolar", "micromolar") if fed
        else ("millimolar", "micromolar", "nanomolar")
    )
    common = dict(
        substrate_state=f"{label}_solid", peroxide_state="H", enzyme_state="E",
        state_units=substrate_units, peroxide_units=peroxide_units, enzyme_units=enzyme_units,
        source=SOURCE,
    )
    oxidation = PeroxideOxidativeCleavageProcess(
        name="oxidation",
        **common,
        product_state=f"{label}_oxidized",
        cuts_state="cuts",
        kcat_symbol="kcat",
        peroxide_km_symbol="Kh",
        substrate_km_symbol="Ks",
        substrate_binding_symbol="Ki",
        product_yield=Q_(3 if fed else 2, "micromole/micromole"),
        yield_source=SOURCE + (" Explicit illustrative trimer-equivalent yield." if fed else " Explicit illustrative dimer-equivalent yield."),
    )
    damage = PeroxideInactivationProcess(
        name="damage", **common, inactive_state="inactive", inactivation_constant_symbol="ki", substrate_km_symbol="Ks"
    )
    constants = (
        [("kcat", 1.25, "1/s"), ("Kh", .08, "millimolar"), ("Ks", 600, "micromolar"),
         ("Ki", 1800, "micromolar"), ("ki", .3, "1/(millimolar*s)"),
         ("feed", .0004, "millimolar/s"), ("decay", .04, "1/s")]
        if fed else
        [("kcat", .5, "1/s"), ("Kh", 200, "micromolar"), ("Ks", 1, "millimolar"),
         ("Ki", .8, "millimolar"), ("ki", .0001, "1/(micromolar*s)")]
    )
    parameters = ParameterSet([Parameter(s, s, v, u, None, SOURCE, "testing", SOURCE) for s, v, u in constants])
    initial = {
        f"{label}_solid": Q_(400 if fed else 10, substrate_units),
        f"{label}_oxidized": Q_(0, substrate_units),
        "H": Q_(.015 if fed else 1000, peroxide_units),
        "E": Q_(4 if fed else 100000, enzyme_units),
        "inactive": Q_(0, enzyme_units),
        "cuts": Q_(0, peroxide_units),
    }
    processes = [oxidation, damage]
    if fed:
        initial.update(H_feed=Q_(0, peroxide_units), H_decay=Q_(0, peroxide_units))
        processes.extend([
            MassActionProcess(name="explicit_feed", reactants={}, products={"H":1, "H_feed":1},
                state_units={"H":peroxide_units, "H_feed":peroxide_units}, rate_constant_symbol="feed",
                rate_constant_units=f"{peroxide_units}/s", rate_units=f"{peroxide_units}/s", source=SOURCE),
            FirstOrderDecayProcess(name="explicit_decay", substrate_state="H", product_state="H_decay",
                state_units=peroxide_units, rate_constant_symbol="decay", source=SOURCE),
        ])
    model = ModelBuilder(process_library=ProcessRegistry(processes), parameters=parameters).assemble()
    return model, initial


@pytest.mark.parametrize("label", ["chitin", "cellulose"])
def test_peroxide_enzyme_and_material_ledgers_with_distinct_units(label):
    model, initial = system(label)
    result = model.run(initial_state=initial, t_span=(Q_(0, "s"), Q_(60, "s")), t_eval=Q_(np.linspace(0, 60, 31), "s"))
    state = result.states
    for values, expected, units in [
        (state[f"{label}_solid"] + state[f"{label}_oxidized"], initial[f"{label}_solid"], "millimolar"),
        (state["E"] + state["inactive"], initial["E"], "micromolar"),
    ]:
        np.testing.assert_allclose(values.to(units).magnitude, expected.to(units).magnitude, rtol=1e-9)
    peroxide_total = state["H"] + state["cuts"]
    if label == "cellulose":
        peroxide_total = peroxide_total + state["H_decay"] - state["H_feed"]
        assert state["H_feed"].to("millimolar").magnitude[-1] == pytest.approx(.024)
        assert state["H_decay"].magnitude[-1] > 0
    else:
        assert "H_feed" not in state and "H_decay" not in state
    np.testing.assert_allclose(peroxide_total.to("millimolar").magnitude, initial["H"].to("millimolar").magnitude, rtol=1e-9)
    yield_value = model.processes[0].product_yield.to("dimensionless").magnitude
    np.testing.assert_allclose(state[f"{label}_oxidized"].to("micromolar").magnitude,
        yield_value * state["cuts"].to("micromolar").magnitude, rtol=1e-9)
    assert state["inactive"].magnitude[-1] > 0


def test_synthetic_preparations_have_different_saturation_protection_and_boundary_conditions():
    chitin, chitin_initial = system("chitin")
    cellulose, cellulose_initial = system("cellulose")
    def ratios(model, initial, label):
        s, h = initial[f"{label}_solid"], initial["H"]
        ks = model.parameters.require_quantity("Ks", str(s.units))
        kh = model.parameters.require_quantity("Kh", str(h.units))
        return (s / ks).to("dimensionless").magnitude, (h / kh).to("dimensionless").magnitude
    assert ratios(chitin, chitin_initial, "chitin") == pytest.approx((10, 5))
    assert ratios(cellulose, cellulose_initial, "cellulose") == pytest.approx((2/3, .1875))
    assert len(chitin.processes) == 2 and len(cellulose.processes) == 4
    assert chitin.processes[0].product_yield.magnitude != cellulose.processes[0].product_yield.magnitude
    assert chitin.processes[0].yield_source != cellulose.processes[0].yield_source
    assert chitin_initial["E"].units != cellulose_initial["E"].units


def test_zero_peroxide_and_substrate_limits_and_saturation():
    def rate(s, h):
        return peroxide_rate_and_gradient(
            substrate=s, peroxide=h, enzyme=0.1, kcat=1, peroxide_km=1, substrate_km=1, substrate_binding=1
        )[0]

    assert rate(10, 0) == 0 and rate(0, 10) == 0
    assert rate(10, 2e-7) / rate(10, 1e-7) == pytest.approx(2, rel=1e-6)
    assert rate(1e8, 1e8) == pytest.approx(0.1, rel=1e-6)
    for bad in [-1, float("nan"), float("inf")]:
        with pytest.raises(ValueError):
            rate(10, bad)


def test_constant_substrate_peroxide_total_turnover_matches_exact_integral():
    # Controlled reservoirs isolate the constant-H analytic limit; no finite-pool ledger is claimed here.
    s, h, e0, kcat, kh, ks, kiS, kin = 10, 2, 0.3, 0.5, 0.2, 1, 0.8, 0.1
    alpha = kin * h * ks / (ks + s)
    beta = kcat * s * h / (kiS * kh + kh * s + ks * h + s * h)

    def rhs(t, y):
        rate = peroxide_rate_and_gradient(
            substrate=s, peroxide=h, enzyme=y[0], kcat=kcat, peroxide_km=kh, substrate_km=ks, substrate_binding=kiS
        )[0]
        damage = peroxide_inactivation_rate_and_gradient(
            substrate=s, peroxide=h, enzyme=y[0], inactivation_constant=kin, substrate_km=ks
        )[0]
        return [-damage, rate]

    times = np.linspace(0, 500, 101)
    result = solve_ivp(rhs, (0, 500), [e0, 0], t_eval=times, rtol=1e-10, atol=1e-12)
    np.testing.assert_allclose(result.y[0], e0 * np.exp(-alpha * times), rtol=1e-7)
    np.testing.assert_allclose(result.y[1], e0 * beta / alpha * (-np.expm1(-alpha * times)), rtol=1e-9, atol=1e-10)


def test_compiled_gradients_and_quantity_rates_agree_in_different_units():
    model, initial = system("chitin")
    for process in model.processes:
        names = [v.name for v in process.state_variables]
        context = KernelContext(
            {n: i for i, n in enumerate(names)}, dict.fromkeys(names, "molar"), "second", model.parameters
        )
        y = np.array([initial[n].to("molar").magnitude for n in names])
        kernel = process.compile_rate(context)
        gradient = process.compile_jacobian(context)
        assert kernel(0, y) == pytest.approx(process.rate(initial, Q_(0, "s"), model.parameters).magnitude)
        expected = []
        for i in range(len(y)):
            up, down = y.copy(), y.copy()
            up[i] += 1e-9
            down[i] -= 1e-9
            expected.append((kernel(0, up) - kernel(0, down)) / 2e-9)
        np.testing.assert_allclose(gradient(0, y), expected, rtol=1e-6, atol=1e-6)


def test_configured_example_has_all_three_balance_checks():
    config = load_model_config(ROOT / "data/model_configs/toy_peroxide_oxidation.yml")
    inputs = ConfiguredInputLoader().load(config)
    model = ConfiguredProcessAssembler().assemble(config, inputs).model
    request = RunRequest(initial_state=inputs.initial_state, t_span=inputs.t_span, t_eval=inputs.t_eval)
    solver = ProcessODESolver(model)
    assert solver.compile(request).summary()["analytic_jacobian_count"] == len(model.processes)
    validations = solver.run(request).validation_results
    assert len(validations) == 4 and all(v.passed for v in validations)


def test_factory_refuses_missing_peroxide_km_and_yield_units():
    from fungal_model.processes.oxidative_factories import OxidativeMechanismFactory
    from fungal_model.processes.factories import ProcessBuildContext
    from fungal_model.io.model_config import ProcessConfig

    factory = OxidativeMechanismFactory("peroxide_oxidative_cleavage")
    config = ProcessConfig.from_mapping(
        {
            "id": "bad",
            "process_type": factory.process_type,
            "states": {"substrate": "S", "enzyme": "E"},
            "parameters": {"kcat": "k"},
        }
    )
    decision = factory.can_build(ProcessBuildContext({"S": "molar", "E": "molar"}), config)
    assert not decision.can_build
    assert {"states.peroxide", "parameters.peroxide_km", "options.units"} <= set(decision.missing_fields)


@pytest.mark.parametrize("scalar", [float, np.float64])
def test_peroxide_numerical_overflow_fails_closed_for_native_and_quantity_scalars(scalar):
    with pytest.raises(ValueError, match="numerical range"):
        peroxide_rate_and_gradient(substrate=scalar(1e300), peroxide=scalar(1e300), enzyme=scalar(1),
            kcat=1, peroxide_km=1, substrate_km=1, substrate_binding=1)
    with pytest.raises(ValueError, match="numerical range"):
        peroxide_inactivation_rate_and_gradient(substrate=scalar(1), peroxide=scalar(1e300), enzyme=scalar(1e300),
            inactivation_constant=1, substrate_km=1)


def test_explicit_configured_output_contains_peroxide_trajectories_and_ledgers(tmp_path):
    from fungal_model.api.user_data_oxidative import write_mechanism_config
    from fungal_model.workflows import run_configured_model

    config = write_mechanism_config(ROOT / "data/user_mechanisms/peroxide_oxidation", tmp_path / "peroxide.yml")
    output = tmp_path / "run"
    result = run_configured_model(config, output_dir=output)
    record = json.loads((output / "record.json").read_text())
    required = {"E", "inactive", "H", "P", "mechanism_cuts", "mechanism_peroxide_feed", "mechanism_peroxide_decay"}
    assert required <= set(record["states"])
    with (output / "state_trajectories.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert rows
    assert required <= {row["name"] for row in rows}
    assert result.states["mechanism_cuts"].magnitude[-1] > 0
    # The finite-run summaries use the same explicit trajectory normalization.
    turnover = (result.states["mechanism_cuts"][-1] / result.states["E"][0]).to("dimensionless")
    remaining = (result.states["E"][-1] / result.states["E"][0]).to("dimensionless")
    assert turnover.magnitude > 0 and 0 < remaining.magnitude < 1
    metrics = {row["metric_name"]: row for row in json.loads((output / "mechanism_metrics.json").read_text())}
    assert metrics["oxidative_cleavage.finite_run_turnover"]["value"] == pytest.approx(turnover.magnitude)
    assert metrics["oxidative_cleavage.remaining_active_fraction"]["value"] == pytest.approx(remaining.magnitude)
    assert metrics["oxidative_cleavage.peroxide_fed"]["value"] == pytest.approx(1.2)
