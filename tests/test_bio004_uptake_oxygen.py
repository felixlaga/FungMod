"""Synthetic software tests for soluble-resource uptake and oxygen balances.

All numerical constants here are invented test inputs, never empirical data.
Two materially different solids and enzyme/sugar bases exercise composition.
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest
import yaml

from fungal_model import UserDataError, load_user_dataset, virtual_experiment
from fungal_model.core.kernels import KernelContext
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.entities.environment import Environment
from fungal_model.modifiers.oxygen import OxygenModifier
from fungal_model.processes.culture import ResourceLimitedGrowthProcess, ResourceLimitedMaintenanceProcess


def _write(path, rows, columns=None):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _dataset(path: Path, *, amount=False, oxygen=False, maintenance=.02, network=False):
    path.mkdir()
    manifest = {"dataset_id": "uptake_checks", "contributor": "FungMod maintainers", "date": "2026-10-09",
        "source": "Illustrative inputs invented for software verification; no empirical data.",
        "notes": "Synthetic software case, not scientific observations or fitted constants.",
        "simulation": {"duration": 12, "units": "hour", "points": 61}}
    if network:
        manifest["enzyme_network"] = {"entry_substrates": ["solid"]}
    (path / "user_dataset.yml").write_text(yaml.safe_dump(manifest))
    source = "Illustrative numerical inputs; no empirical observations."
    solid_class, bond, enzyme_units = ("starch_like", "alpha_1_4_glucosidic", "mg/L") if amount else ("cellulose_like", "beta_1_4_glucosidic", "FPU/L")
    _write(path / "strains.csv", [{"strain_id": "culture", "name": "Illustrative culture"}])
    _write(path / "enzyme_classes.csv", [{"class_id": "hydrolase", "name": "Illustrative hydrolase", "target_bond_classes": bond, "compatible_substrate_classes": solid_class, "source": source}])
    _write(path / "enzymes.csv", [{"strain_id": "culture", "enzyme_class": "hydrolase", "evidence": "explicit illustrative pool", "source": source}])
    _write(path / "conditions.csv", [{"condition_id": "c", "temperature": 25, "temperature_units": "degC", "ph": 6, "notes": source}])
    _write(path / "substrates.csv", [{"substrate_id": "solid", "name": "Illustrative " + solid_class, "substrate_class": solid_class,
        "physical_state": "solid_polymer", "bond_classes": bond, "amount_basis": "dry_mass", "product": "sugar",
        "product_yield": 6 if amount else 1, "yield_basis": "mmol/g" if amount else "g/g", "yield_evidence_type": "estimate", "yield_method": "illustrative estimate", "source": source}])
    (path / "kinetics.csv").write_text("strain_id,enzyme_class,substrate_id,condition_id,quantity,value,units,evidence_type,source,method\n")
    rows = []
    def row(quantity, value, units, pool="", evidence="estimate"):
        return {"strain_id": "culture", "substrate_id": "solid", "condition_id": "c", "quantity": quantity, "enzyme_class": pool,
            "value": value, "units": units, "evidence_type": evidence, "method": "illustrative estimate", "source": source}
    for quantity, value, units in [
        ("substrate_initial_concentration", 10, "g/L"), ("initial_biomass", .1, "g/L"),
        ("biomass_yield", .05 if amount else .4, "g/mmol" if amount else "g/g"),
        ("biomass_loss_rate", .01, "1/h"), ("induction_half_saturation", .5, "g/L"),
        ("uptake_capacity", 10 if amount else 3, "mmol/g/h" if amount else "1/h"),
        ("uptake_half_saturation", 1 if amount else .1, "mmol/L" if amount else "g/L"),
        ("maintenance_demand", maintenance, "mmol/g/h" if amount else "1/h"),
        ("initial_soluble_sugar", .2, "mmol/L" if amount else "g/L"),
    ]:
        rows.append(row(quantity, value, units))
    for quantity, value, units in [("hydrolysis_capacity", .1, "g/mg/h" if amount else "g/FPU/h"),
        ("hydrolysis_half_saturation", 1, "g/L"), ("initial_enzyme_concentration", 1, enzyme_units),
        ("specific_production_rate", 0, "mg/g/h" if amount else "FPU/g/h"), ("enzyme_loss_rate", 0, "1/h")]:
        rows.append(row(quantity, value, units, "hydrolase"))
    if oxygen:
        for quantity, value, units in [("oxygen_half_saturation", .01, "mmol/L"), ("oxygen_yield", 1, "mmol/g"),
            ("oxygen_maintenance", .5, "mmol/mmol" if amount else "mmol/g")]:
            rows.append(row(quantity, value, units))
        _write(path / "aeration.csv", [row("kla", 2, "1/h", evidence="measured"), row("oxygen_saturation", .25, "mmol/L"), row("initial_dissolved_oxygen", .2, "mmol/L")])
    _write(path / "culture.csv", rows)
    return path


def _run(path):
    study = virtual_experiment(fungi="culture", substrates="solid", environments="c", user_data=path)
    assert study.preflight()[0].status == "modelable"
    result = study.simulate(mode="exploratory", n_samples=1, seed=7, output_dir=path / "run", quicklook=False)
    rows = [row for row in csv.DictReader(Path(result.tables.paths["time_series_long"]).open()) if row["value"]]
    roles = {role: np.array([float(row["value"]) for row in rows if row["state_role"] == role]) for role in {row["state_role"] for row in rows}}
    return result, roles


@pytest.mark.parametrize("amount", [False, True])
@pytest.mark.parametrize("oxygen", [False, True])
def test_two_distinct_cultures_close_resource_and_oxygen_at_every_time(tmp_path, amount, oxygen):
    dataset = _dataset(tmp_path / "data", amount=amount, oxygen=oxygen, network=True)
    result, roles = _run(dataset)
    release, growth_yield = (6, .05) if amount else (1, .4)
    total = roles["substrate"] + roles["soluble_product"] / release + (roles["biomass"] + roles["ledger_biomass_loss"]) / (release * growth_yield) + roles["ledger_respired_carbon"] / release
    np.testing.assert_allclose(total, total[0], rtol=1e-9, atol=1e-10)
    assert roles["ledger_respired_carbon"][-1] > 0
    if oxygen:
        oxygen_total = roles["dissolved_oxygen"] + roles["ledger_oxygen_consumption"] - roles["ledger_oxygen_transfer"]
        np.testing.assert_allclose(oxygen_total, .2, rtol=1e-9, atol=1e-10)
        assert roles["ledger_oxygen_consumption"][-1] > 0
        assert np.min(roles["dissolved_oxygen"]) >= 0
    diagnostics = list(csv.DictReader(Path(result.tables.paths["conservation_diagnostics"]).open()))
    metrics = {row["metric"]: row for row in csv.DictReader(Path(result.tables.paths["final_metrics"]).open())}
    assert float(metrics["peak_soluble_sugar"]["value"]) == pytest.approx(float(np.max(roles["soluble_product"])))
    assert float(metrics["final_biomass"]["value"]) == pytest.approx(float(roles["biomass"][-1]))
    if oxygen:
        assert float(metrics["minimum_dissolved_oxygen"]["value"]) == pytest.approx(float(np.min(roles["dissolved_oxygen"])))
        assert metrics["time_below_oxygen_threshold"]["status"] == "unknown"
    assert len(diagnostics) == (2 if oxygen else 1)
    assert all(float(row["relative_max_absolute_drift"]) < 1e-9 for row in diagnostics)


def test_zero_maintenance_removes_ledger_exactly(tmp_path):
    _, roles = _run(_dataset(tmp_path / "data", maintenance=0))
    np.testing.assert_array_equal(roles["ledger_respired_carbon"], 0)


def test_missing_uptake_value_remains_an_explicit_gap(tmp_path):
    path = _dataset(tmp_path / "data")
    rows = list(csv.DictReader((path / "culture.csv").open()))
    _write(path / "culture.csv", [row for row in rows if row["quantity"] != "uptake_capacity"])
    dataset = load_user_dataset(path)
    unknowns = [record for record in dataset.records["parameter_records"] if record["value"]["kind"] == "unknown"]
    assert any("uptake_capacity" in record["record_id"] for record in unknowns)


@pytest.mark.parametrize("failure", ["yield_evidence", "uptake_units", "kla_units", "kla_estimate", "repression"])
def test_unsupported_or_unbacked_inputs_fail_closed(tmp_path, failure):
    path = _dataset(tmp_path / "data", oxygen=True)
    filename = "substrates.csv" if failure == "yield_evidence" else "aeration.csv" if failure.startswith("kla") else "culture.csv"
    rows = list(csv.DictReader((path / filename).open()))
    if failure == "yield_evidence":
        rows[0]["yield_evidence_type"] = ""
    elif failure == "repression":
        rows.append({**rows[0], "quantity": "catabolite_repression"})
    else:
        target = next(row for row in rows if row["quantity"] == ("kla" if failure.startswith("kla") else "uptake_capacity"))
        target["evidence_type" if failure == "kla_estimate" else "units"] = "estimate" if failure == "kla_estimate" else "kelvin"
    _write(path / filename, rows)
    with pytest.raises(UserDataError):
        load_user_dataset(path)


def _parameters():
    return ParameterSet([Parameter(name=symbol, symbol=symbol, value=value, units=units, source="Synthetic unit check", confidence_level="testing", notes="No empirical data", uncertainty=None)
        for symbol, value, units in [("Y", .05, "g/mmol"), ("m", .2, "mmol/g/h"), ("q", 10, "mmol/g/h"), ("K", 1, "mmol/L"), ("KO", .01, "mmol/L")]])


@pytest.mark.parametrize("oxidant", [False, True])
@pytest.mark.parametrize("cls", [ResourceLimitedGrowthProcess, ResourceLimitedMaintenanceProcess])
def test_optional_closure_jacobian_on_separate_bases(cls, oxidant):
    units = {"G": "mmol/L", "X": "g/L", "O": "mmol/L"}
    process = cls(name="uptake", substrate_state="G", biomass_state="X", oxidant_state="O" if oxidant else None,
        concentration_units="mmol/L", state_units=units, time_units="h", true_yield_symbol="Y", maintenance_demand_symbol="m", uptake_capacity_symbol="q",
        substrate_half_saturation_symbol="K", oxidant_half_saturation_symbol="KO" if oxidant else None,
        stoichiometry={"G": {"value": -20, "units": "mmol/g"}} if cls is ResourceLimitedGrowthProcess else {"G": -1})
    context = KernelContext(state_index={"G": 0, "X": 1, "O": 2}, state_units=units, time_units="h", parameters=_parameters())
    kernel, derivative = process.compile_rate(context), process.compile_jacobian(context)
    vector = np.array([2., .3, .2])
    numerical = np.array([(kernel(0, vector + np.eye(3)[i]*1e-6) - kernel(0, vector - np.eye(3)[i]*1e-6))/(2e-6) for i in range(3)])
    np.testing.assert_allclose(derivative(0, vector), numerical, rtol=1e-7, atol=1e-9)
    state = {name: Q_(vector[i], units[name]) for name, i in context.state_index.items()}
    assert kernel(0, vector) == pytest.approx(process.rate(state, Q_(0,"h"), context.parameters).magnitude)


def test_oxygen_modifier_static_equivalence_and_analytic_derivative():
    parameters = _parameters()
    environment = Environment(name="Synthetic oxygen condition", oxygen_concentration=Q_(.2, "mmol/L"))
    static = OxygenModifier("KO", "mmol/L")
    dynamic = OxygenModifier("KO", "mmol/L", state_source="oxygen")
    context = KernelContext(state_index={"oxygen": 0}, state_units={"oxygen": "mmol/L"}, time_units="h", parameters=parameters, environment=environment)
    vector = np.array([.2])
    assert static.compile_activity(context)(0, vector) == dynamic.compile_activity(context)(0, vector)
    derivative = dynamic.compile_activity_jacobian(context)(0, vector)[0]
    kernel = dynamic.compile_activity(context)
    assert derivative == pytest.approx((kernel(0, vector+1e-6)-kernel(0,vector-1e-6))/2e-6, rel=1e-8)


def _change_rows(path, filename, changes):
    rows = list(csv.DictReader((path / filename).open()))
    for row in rows:
        row.update(changes.get(row.get("quantity", ""), {}))
    _write(path / filename, rows)


def test_fast_uptake_reproduces_direct_growth_limit(tmp_path):
    path = _dataset(tmp_path / "fast", maintenance=0)
    _change_rows(path, "culture.csv", {"uptake_capacity": {"value": 100}, "uptake_half_saturation": {"value": 1e-5}, "initial_soluble_sugar": {"value": 0}})
    _, fast = _run(path)
    legacy_path = _dataset(tmp_path / "legacy")
    rows = list(csv.DictReader((legacy_path / "culture.csv").open()))
    omitted = {"uptake_capacity", "uptake_half_saturation", "maintenance_demand", "initial_soluble_sugar"}
    _write(legacy_path / "culture.csv", [row for row in rows if row["quantity"] not in omitted])
    substrates = list(csv.DictReader((legacy_path / "substrates.csv").open()))
    substrates[0].update(yield_evidence_type="", yield_method="")
    _write(legacy_path / "substrates.csv", substrates)
    _, legacy = _run(legacy_path)
    # Same enzyme-mediated release; instantaneous uptake differs only by the tiny retained sugar pool.
    assert np.max(fast["soluble_product"]) < 1e-6
    np.testing.assert_allclose(fast["substrate"], legacy["substrate"], rtol=2e-7)
    np.testing.assert_allclose(fast["biomass"], legacy["biomass"], rtol=2e-6, atol=1e-7)


def test_oxygen_transfer_approaches_saturation_analytically_even_from_above(tmp_path):
    path = _dataset(tmp_path / "transfer", oxygen=True, maintenance=0)
    _change_rows(path, "culture.csv", {"uptake_capacity": {"value": 0}})
    _change_rows(path, "aeration.csv", {"initial_dissolved_oxygen": {"value": 1.0}})
    _, roles = _run(path)
    times = np.linspace(0, 12, 61)
    expected = .25 + .75 * np.exp(-2*times)
    np.testing.assert_allclose(roles["dissolved_oxygen"], expected, rtol=2e-7, atol=1e-9)
    np.testing.assert_allclose(roles["ledger_oxygen_transfer"], expected-1, rtol=2e-7, atol=1e-9)
    np.testing.assert_array_equal(roles["ledger_oxygen_consumption"], 0)


def test_large_transfer_and_saturating_oxygen_approach_unlimited_growth(tmp_path):
    _, unlimited = _run(_dataset(tmp_path / "unlimited"))
    path = _dataset(tmp_path / "aerated", oxygen=True)
    _change_rows(path, "culture.csv", {"oxygen_half_saturation": {"value": 1e-7}})
    _change_rows(path, "aeration.csv", {"kla": {"value": 1e4}, "oxygen_saturation": {"value": 1}, "initial_dissolved_oxygen": {"value": 1}})
    _, aerated = _run(path)
    np.testing.assert_allclose(aerated["biomass"], unlimited["biomass"], rtol=1e-5, atol=1e-8)


def test_dynamic_oxygen_response_reads_state_and_requires_unlimited_capacity_declaration(tmp_path):
    _, reference = _run(_dataset(tmp_path / "reference", oxygen=True))
    path = _dataset(tmp_path / "responsive", oxygen=True)
    response = {"strain_id": "culture", "enzyme_class": "hydrolase", "substrate_id": "solid", "law": "oxygen_monod",
        "parameter": "half_saturation", "value": .2, "units": "mmol/L", "evidence_type": "estimate", "source": "Illustrative response parameter",
        "method": "illustrative estimate", "kinetics_at_reference": "yes"}
    _write(path / "responses.csv", [response])
    result, responsive = _run(path)
    assert responsive["substrate"][-1] > reference["substrate"][-1]
    dataset = load_user_dataset(path)
    records = [record for record in dataset.records["parameter_records"] if "oxygen_response_half_saturation" in record["record_id"]]
    assert records and records[0]["provenance"]["fungmod_user_dataset"]["file"] == "responses.csv"
    response["kinetics_at_reference"] = "no"
    _write(path / "responses.csv", [response])
    with pytest.raises(UserDataError, match="oxygen-unlimited"):
        load_user_dataset(path)


def test_sugar_biomass_oxygen_timecourse_comparison_uses_pool_concentrations(tmp_path):
    from fungal_model.api.user_data_fit import compare_with_timecourses
    path = _dataset(tmp_path / "observed", amount=True, oxygen=True)
    # Explicit synthetic observations at t=0 avoid implying external biological validation.
    observations = []
    for observable, value, units in [("substrate",10,"g/L"), ("soluble_sugar",.2,"mmol/L"), ("biomass",.1,"g/L"), ("dissolved_oxygen",.2,"mmol/L")]:
        observations.append({"strain_id":"culture", "enzyme_class":"hydrolase", "substrate_id":"solid", "condition_id":"c", "observable":observable,
            "time":0,"time_units":"h","value":value,"units":units,"sd":.01,"source":"Synthetic numerical verification values", "method":"synthetic self-consistency check"})
    _write(path / "timecourse.csv", observations)
    result, _ = _run(path)
    comparison = compare_with_timecourses(result, load_user_dataset(path))
    assert len(comparison.series) == 4
    assert not comparison.not_compared
    assert all(float(series["rmse"]) < 1e-12 for series in comparison.series)
    observations[1]["units"] = "g/L"
    _write(path / "timecourse.csv", observations)
    with pytest.raises(UserDataError, match="state units"):
        load_user_dataset(path)


@pytest.mark.parametrize("biomass_units", ["g/L", "umol/L"])
def test_costed_secretion_refuses_mixed_or_rescaled_extent_bases(biomass_units):
    from fungal_model.processes.culture import CostedSecretionProcess
    with pytest.raises(ValueError, match="same concentration basis and scale"):
        CostedSecretionProcess(name="secretion", substrate_state="G", biomass_state="X",
            concentration_units="mmol/L", state_units={"G":"mmol/L", "X":biomass_units},
            time_units="h", true_yield_symbol="Y", maintenance_demand_symbol="m", uptake_capacity_symbol="q",
            substrate_half_saturation_symbol="K", allocation_fraction_symbol="f", secretion_yield_symbol="Ys",
            stoichiometry={"G":-1,"E":1})


def test_culture_timecourses_do_not_enter_assay_only_fitter(tmp_path):
    from fungal_model.api.user_data_fit import UserDataFitError, fit_user_dataset
    path = _dataset(tmp_path / "culture")
    with pytest.raises(UserDataFitError, match="comparison, not parameter fitting"):
        fit_user_dataset(path, parameters=[("culture", "hydrolase", "solid", "uptake_capacity")],
            bounds={"uptake_capacity":(.1,10,"1/h")})


def test_timecourses_of_second_consumer_compare_shared_culture_pool(tmp_path):
    from fungal_model.api.user_data_fit import compare_with_timecourses
    path = _dataset(tmp_path / "shared")
    for filename, key in [("enzyme_classes.csv","class_id"),("enzymes.csv","enzyme_class")]:
        rows = list(csv.DictReader((path / filename).open()))
        rows.append({**rows[0],key:"other", **({"name":"Other illustrative hydrolase"} if key=="class_id" else {})})
        _write(path / filename, rows)
    rows = list(csv.DictReader((path / "culture.csv").open()))
    rows.extend({**row, "enzyme_class":"other"} for row in list(rows) if row["enzyme_class"])
    _write(path / "culture.csv", rows)
    _write(path / "timecourse.csv", [{"strain_id":"culture", "enzyme_class":"other", "substrate_id":"solid",
        "condition_id":"c", "observable":"soluble_sugar", "time":0,"time_units":"h","value":.2,"units":"g/L",
        "sd":.01,"source":"Synthetic numerical verification value", "method":"synthetic self-consistency check"}])
    result, _ = _run(path)
    comparison = compare_with_timecourses(result, load_user_dataset(path))
    assert len(comparison.series) == 1
    assert not comparison.not_compared
    assert float(comparison.series[0]["rmse"]) < 1e-12
