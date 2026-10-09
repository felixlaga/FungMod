"""BIO-004 M1 software benchmarks: synthetic values, no biological validation."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from fungal_model.api.user_data_adsorption import adsorption_case_unit_errors, adsorption_result_columns, adsorption_units_error
from fungal_model.core.kernels import KernelContext
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_, UnitError
from fungal_model.io.model_config import load_model_config
from fungal_model.kinetics.adsorption import enzyme_partition, partition_magnitudes
from fungal_model.processes.adsorption import AdsorbedEnzymeHydrolysisFactory, AdsorbedEnzymeHydrolysisProcess
from fungal_model.processes.factories import ProcessBuildContext
from fungal_model.processes.surface import ProductReleaseMap
from fungal_model.solvers import ProcessODESolver, RunRequest
from fungal_model.workflows.configured_model import ConfiguredInputLoader, ConfiguredProcessAssembler

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "Synthetic software benchmark; not scientific data."


def _parameter(symbol, value, units):
    return Parameter(symbol, symbol, value, units, None, SOURCE, "testing", SOURCE)


def _process(enzyme_units="mg/L", **changes):
    arguments = dict(name="adsorption", substrate_state="S", enzyme_state="ET", substrate_units="g/L", enzyme_units=enzyme_units, rate_units="g/L/hour", binding_capacity_symbol="Gamma", bound_rate_constant_symbol="kb", adsorption_dissociation_constant_symbol="Kd", product_release_map=ProductReleaseMap.one_to_one(substrate_state="S", product_state="P"), substrate_physical_state="solid_polymer", amount_basis="dry_mass")
    arguments.update(changes)
    return AdsorbedEnzymeHydrolysisProcess(**arguments)


def _parameters(enzyme_units="mg/L", capacity=0.2):
    return ParameterSet([_parameter("Gamma", capacity, f"({enzyme_units})/(g/L)"), _parameter("Kd", 0.5, enzyme_units), _parameter("kb", 0.1, f"(g/L/hour)/({enzyme_units})")])


@pytest.mark.parametrize("enzyme_units", ["mg/L", "umol/L", "FPU/L", "BGU/L"])
@pytest.mark.parametrize("capacity", [0.2, 20.0], ids=["synthetic_low_capacity_film", "synthetic_high_capacity_chitin_like_solid"])
def test_exact_partition_conservation_units_and_isotherm(enzyme_units, capacity):
    for substrate in (0.0, 1e-6, 2.0, 100.0):
        for total in (0.0, 1e-8, 1.0, 1e6):
            result = enzyme_partition(total_enzyme=Q_(total, enzyme_units), solid_substrate=Q_(substrate, "g/L"), binding_capacity=Q_(capacity, f"({enzyme_units})/(g/L)"), adsorption_dissociation_constant=Q_(0.5, enzyme_units))
            f, b = result.free.magnitude, result.bound.magnitude
            assert f + b == pytest.approx(total, rel=1e-12, abs=1e-25)
            assert b == pytest.approx(capacity * substrate * f / (0.5 + f), rel=1e-12, abs=1e-25)
            assert 0 <= b <= min(capacity * substrate, total) * (1 + 1e-12)


def test_association_and_dissociation_are_equivalent_and_scaled_units_work():
    values = dict(total_enzyme=Q_(1, "mg/L"), solid_substrate=Q_(0.01, "kg/L"), binding_capacity=Q_(200, "mg/kg"))
    association = enzyme_partition(**values, adsorption_constant=Q_(2, "L/mg"))
    dissociation = enzyme_partition(**values, adsorption_dissociation_constant=Q_(500, "ug/L"))
    assert association == dissociation


def test_low_coverage_and_negligible_depletion_recovers_apparent_first_order():
    # Both K*E_free and K*Gamma*S must be small; low coverage alone does not remove depletion.
    total, capacity, kd = 1.0, 100.0, 1e8
    free, bound = partition_magnitudes(total, capacity, kd)
    assert free == pytest.approx(total, rel=2e-6)
    assert bound == pytest.approx(capacity * total / kd, rel=2e-6)


def test_high_enzyme_saturates_binding_capacity():
    for total in (1e7, 1e8):
        _, bound = partition_magnitudes(total, 2.0, 0.5)
        assert bound == pytest.approx(2.0, rel=1e-7)


def test_stable_root_in_strong_and_weak_binding_regimes():
    for total, capacity, kd in ((1e10, 1e-10, 1.0), (1e-10, 1e10, 1.0), (1e100, 1e100, 1.0), (1e-20, 1.0, 1e20), (1e300, 1e300, 1e-300), (1e-300, 1e300, 1e-300)):
        free, bound = partition_magnitudes(total, capacity, kd)
        assert np.isfinite([free, bound]).all()
        assert free + bound == pytest.approx(total, rel=1e-12, abs=0.0)
        assert bound > 0


@pytest.mark.parametrize("enzyme_units", ["mg/L", "umol/L", "FPU/L"])
def test_rate_kernel_and_analytic_jacobian_have_unit_parity(enzyme_units):
    process, parameters = _process(enzyme_units), _parameters(enzyme_units)
    context = KernelContext(state_index={"S": 0, "ET": 1, "P": 2}, state_units={"S": "kg/L", "ET": enzyme_units, "P": "g/L"}, time_units="hour", parameters=parameters)
    rate, gradient = process.compile_rate(context), process.compile_jacobian(context)
    state = np.array([0.01, 1.0, 0.0])
    explicit = process.rate({"S": Q_(0.01, "kg/L"), "ET": Q_(1, enzyme_units)}, Q_(0, "hour"), parameters)
    assert rate(0.0, state) == pytest.approx(explicit.magnitude, rel=1e-13)
    expected = np.zeros(3)
    for index in (0, 1):
        delta = 1e-6 * state[index]
        high, low = state.copy(), state.copy()
        high[index] += delta
        low[index] -= delta
        expected[index] = (rate(0, high) - rate(0, low)) / (2 * delta)
    np.testing.assert_allclose(gradient(0, state), expected, rtol=2e-8, atol=1e-12)
    at_zero = gradient(0, np.zeros(3))
    np.testing.assert_array_equal(at_zero, np.zeros(3))


@pytest.mark.parametrize("changes", [{"adsorption_constant_symbol": "K"}, {"adsorption_dissociation_constant_symbol": None}, {"substrate_physical_state": "dissolved"}, {"amount_basis": "molar"}, {"substrate_units": "mmol/L"}])
def test_process_refuses_ambiguous_missing_and_non_solid_inputs(changes):
    with pytest.raises(ValueError):
        _process(**changes)


@pytest.mark.parametrize("quantity,units", [("binding_capacity", "mg/L"), ("adsorption_constant", "mg/L"), ("adsorption_dissociation_constant", "L/mg"), ("bound_rate_constant", "g/hour")])
def test_user_rows_refuse_incompatible_units(quantity, units):
    assert adsorption_units_error(quantity, units, solid=True)
    assert adsorption_units_error(quantity, "mg/g", solid=False)


def test_user_rows_require_same_enzyme_basis_and_exactly_one_binding_constant():
    values = {"binding_capacity": "mg/g", "adsorption_constant": "L/mg", "bound_rate_constant": "g/mg/hour", "enzyme_concentration": "mg/L", "substrate_initial_concentration": "g/L"}
    assert adsorption_case_unit_errors(values) == ()
    assert adsorption_case_unit_errors({**values, "enzyme_concentration": "FPU/L"})
    assert adsorption_case_unit_errors({**values, "adsorption_dissociation_constant": "mg/L"})
    assert adsorption_case_unit_errors({k: v for k, v in values.items() if k != "adsorption_constant"})
    with pytest.raises(UnitError):
        _process("FPU/L").rate({"S": Q_(10, "g/L"), "ET": Q_(1, "FPU/L")}, Q_(0, "h"), _parameters())


def test_factory_fails_closed_before_building():
    config = SimpleNamespace(states={"substrate": "S", "enzyme": "ET"}, parameters={}, product_map="missing")
    decision = AdsorbedEnzymeHydrolysisFactory().can_build(ProcessBuildContext(state_units={"S": "g/L", "ET": "mg/L"}), config)
    assert not decision.can_build
    assert "parameters.binding_capacity" in decision.missing_fields
    assert "exactly one" in decision.reasons[0]


def test_synthetic_config_integrates_with_conservation_and_derived_outputs():
    config = load_model_config(ROOT / "data/model_configs/toy_adsorbed_enzyme_hydrolysis.yml")
    inputs = ConfiguredInputLoader().load(config)
    model = ConfiguredProcessAssembler().assemble(config, inputs).model
    request = RunRequest(initial_state=inputs.initial_state, t_span=inputs.t_span, t_eval=inputs.t_eval)
    solver = ProcessODESolver(model)
    assert solver.compile(request).summary()["analytic_jacobian_count"] == 1
    result = solver.run(request)
    np.testing.assert_allclose((result.states["S"] + result.states["P"]).magnitude, 10, rtol=1e-12)
    process = model.processes[0]
    derived = adsorption_result_columns(process, model.parameters, result.states)
    np.testing.assert_allclose(derived["enzyme_conservation_residual"].magnitude, 0, atol=1e-12)
    np.testing.assert_allclose((derived["free_enzyme"] + derived["bound_enzyme"]).magnitude, result.states["ET"].magnitude, rtol=1e-12)
    assert result.states["S"].magnitude[-1] < 10
    assert derived["bound_enzyme"].magnitude[-1] < derived["bound_enzyme"].magnitude[0]
    from fungal_model.workflows.configured_outputs import _conservation_diagnostics
    diagnostics = _conservation_diagnostics(config, result)
    enzyme_row = next(row for row in diagnostics["rows"] if row["validator_id"].endswith("enzyme_pool_balance"))
    assert enzyme_row["max_absolute_drift"] < 1e-12
    assert enzyme_row["initial_conserved_total"] == 1.0


def test_unit_bearing_product_yield_is_applied_without_molar_mass_guess():
    process = _process(product_release_map=ProductReleaseMap(reactants={"S": 1}, products={"P": 2}, coefficient_units={"P": "mmol/g"}), state_units={"P": "mmol/L"})
    assert process.contributions(Q_(3, "g/L/hour"))["P"].to("mmol/L/hour").magnitude == 6


def test_modifier_delegates_partition_and_does_not_add_serialization_fields():
    from fungal_model.processes.rate_modifiers import RateModifierProcess
    from fungal_model.modifiers.reactivity import SubstrateReactivityModifier
    process = _process()
    modifier = SubstrateReactivityModifier(substrate_state="S", substrate_units="g/L", reference_concentration_symbol="S0", exponent_symbol="n")
    wrapped = RateModifierProcess(base_process=process, rate_modifiers=(modifier,))
    states = {"S": Q_([10.0, 5.0], "g/L"), "ET": Q_([1.0, 1.0], "mg/L")}
    derived = wrapped.derived_quantities(states, _parameters())
    assert "bound_enzyme" in derived
    assert "derived_quantities" not in wrapped.to_dict()
    assert "derived_quantities" not in process.to_dict()


def _write_csv(path, rows):
    import csv
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _user_dataset(path, *, enzyme_amount="mg", system="film", binding="adsorption_dissociation_constant", drop=()):
    import yaml
    source = "Illustrative synthetic inputs invented for software verification; no empirical data."
    path.mkdir(parents=True)
    bond, substrate_class = ("film_link", "film_like") if system == "film" else ("acetylated_link", "chitin_like")
    (path / "user_dataset.yml").write_text(yaml.safe_dump({"dataset_id": "adsorption_checks", "contributor": "FungMod maintainers", "date": "2026-10-09", "source": source, "notes": source, "simulation": {"duration": 48, "units": "hour", "points": 25}}))
    _write_csv(path / "strains.csv", [{"strain_id": "strain", "name": "Synthetic enzyme source"}])
    _write_csv(path / "enzyme_classes.csv", [{"class_id": "cutter", "name": "Synthetic cutter", "target_bond_classes": bond, "compatible_substrate_classes": substrate_class, "source": source}])
    _write_csv(path / "enzymes.csv", [{"strain_id": "strain", "enzyme_class": "cutter", "evidence": "synthetic software case", "source": source}])
    _write_csv(path / "conditions.csv", [{"condition_id": "assay", "temperature": 25, "temperature_units": "degC", "ph": 6, "notes": source}])
    _write_csv(path / "substrates.csv", [{"substrate_id": "solid", "name": "Synthetic " + system, "substrate_class": substrate_class, "physical_state": "solid_polymer", "bond_classes": bond, "amount_basis": "dry_mass", "product": "soluble", "product_yield": 1, "yield_basis": "g/g", "source": source}])
    rows = []
    affinity_units = f"L/{enzyme_amount}" if binding == "adsorption_constant" else f"{enzyme_amount}/L"
    for quantity, value, units in [("binding_capacity", .2 if system == "film" else 20, f"{enzyme_amount}/g"), (binding, 2 if binding == "adsorption_constant" else .5, affinity_units), ("bound_rate_constant", .1, f"g/{enzyme_amount}/hour"), ("substrate_initial_concentration", 10, "g/L"), ("enzyme_concentration", 1, f"{enzyme_amount}/L")]:
        if quantity in drop:
            continue
        rows.append({"strain_id": "strain", "enzyme_class": "cutter", "substrate_id": "solid", "condition_id": "assay", "quantity": quantity, "value": value, "units": units, "evidence_type": "estimate", "method": "synthetic test inputs", "source": source})
    _write_csv(path / "kinetics.csv", rows)
    return path


@pytest.mark.parametrize("amount,system,binding", [("mg", "film", "adsorption_constant"), ("umol", "chitin", "adsorption_dissociation_constant"), ("FPU", "chitin", "adsorption_constant")])
def test_user_data_runs_two_distinct_synthetic_systems_in_mass_molar_and_assay_bases(tmp_path, amount, system, binding):
    import csv
    from fungal_model import load_user_dataset, virtual_experiment
    path = _user_dataset(tmp_path / "data", enzyme_amount=amount, system=system, binding=binding)
    dataset = load_user_dataset(path)
    assert {item["process_type"] for item in dataset.records["process_compatibility"]} == {"adsorbed_enzyme_hydrolysis"}
    study = virtual_experiment(fungi="strain", substrates="solid", environments="assay", user_data=dataset)
    assert study.preflight()[0].status == "modelable"
    result = study.simulate(mode="exploratory", n_samples=1, seed=7, output_dir=tmp_path / "run", quicklook=False)
    rows = list(csv.DictReader(Path(result.tables.paths["time_series_long"]).open()))
    bound = [row for row in rows if row["state"].endswith("bound_enzyme")]
    residual = [float(row["value"]) for row in rows if row["state"].endswith("enzyme_conservation_residual")]
    assert len(bound) == 25
    assert {row["state_role"] for row in bound} == {"bound_enzyme"}
    np.testing.assert_allclose(residual, 0.0, atol=1e-12)
    mechanisms = list(csv.DictReader(Path(result.tables.paths["mechanism_summary"]).open()))
    assert any("E_T = E_f+E_b" in row["equation_or_law"] for row in mechanisms)
    template = dataset.records["case_templates"][0]
    assert "No enzyme adsorption or partitioning" not in " ".join(template["limitations"])


def test_user_data_unknown_rate_remains_an_explicit_gap(tmp_path):
    from fungal_model import load_user_dataset
    path = _user_dataset(tmp_path / "data", drop=("bound_rate_constant",))
    dataset = load_user_dataset(path)
    gaps = [row for row in dataset.records["parameter_records"] if row["value"]["kind"] == "unknown"]
    assert len(gaps) == 1
    assert "bound_rate_constant" in gaps[0]["parameter_symbol"]
    assert "bound enzyme" in gaps[0]["provenance"]["measurement_request"]


def test_user_data_refuses_no_affinity_and_legacy_morphology_columns(tmp_path):
    from fungal_model import UserDataError, load_user_dataset
    path = _user_dataset(tmp_path / "none", drop=("adsorption_dissociation_constant",))
    with pytest.raises(UserDataError, match="exactly one"):
        load_user_dataset(path)
    path = _user_dataset(tmp_path / "area")
    import csv
    with (path / "substrates.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["crystallinity_index"] = "0.8"
    _write_csv(path / "substrates.csv", rows)
    with pytest.raises(UserDataError, match="crystallinity"):
        load_user_dataset(path)


def test_sbml_export_explicitly_refuses_unimplemented_adsorption_law():
    pytest.importorskip("libsbml")
    from fungal_model.standards.sbml import SbmlExportError, to_sbml
    config = load_model_config(ROOT / "data/model_configs/toy_adsorbed_enzyme_hydrolysis.yml")
    inputs = ConfiguredInputLoader().load(config)
    model = ConfiguredProcessAssembler().assemble(config, inputs).model
    with pytest.raises(SbmlExportError, match="adsorbed_enzyme_hydrolysis.*not SBML-exportable"):
        to_sbml(model, initial_state=inputs.initial_state)


def test_zero_enzyme_has_no_partition_or_rate_but_undefined_bound_fraction():
    process = _process()
    parameters = _parameters()
    states = {"S": Q_([10., 0., 10.], "g/L"), "ET": Q_([0., 0., 1.], "mg/L")}
    derived = process.derived_quantities(states, parameters)
    for role in ("free_enzyme", "bound_enzyme", "total_enzyme", "enzyme_conservation_residual"):
        np.testing.assert_array_equal(derived[role].magnitude[:2], 0.)
    assert np.isnan(derived["bound_fraction"].magnitude[:2]).all()
    assert np.isfinite(derived["bound_fraction"].magnitude[2])
    np.testing.assert_array_equal(derived["bound_fraction_defined"].magnitude, [False, False, True])
    for substrate in (0., 10.):
        assert process.rate({"S": Q_(substrate, "g/L"), "ET": Q_(0., "mg/L")}, Q_(0., "h"), parameters).magnitude == 0.


def test_public_zero_enzyme_run_exports_explicit_unknown_fraction(tmp_path):
    import csv
    import json
    from fungal_model import load_user_dataset, virtual_experiment
    path = _user_dataset(tmp_path / "data")
    with (path / "kinetics.csv").open() as handle:
        kinetics = list(csv.DictReader(handle))
    for row in kinetics:
        if row["quantity"] == "enzyme_concentration":
            row["value"] = "0"
    _write_csv(path / "kinetics.csv", kinetics)
    dataset = load_user_dataset(path)
    result = virtual_experiment(fungi="strain", substrates="solid", environments="assay", user_data=dataset).simulate(
        mode="exploratory", n_samples=1, seed=7, output_dir=tmp_path / "run", quicklook=False)
    with Path(result.tables.paths["time_series_long"]).open() as handle:
        rows = list(csv.DictReader(handle))
    fractions = [row for row in rows if row["state_role"] == "enzyme_bound_fraction"]
    masks = [row for row in rows if row["state_role"] == "enzyme_bound_fraction_defined"]
    assert len(fractions) == len(masks) == 25
    assert all(row["value"] == "" for row in fractions)
    assert all(float(row["value"]) == 0. for row in masks)
    for role in ("free_enzyme", "bound_enzyme", "total_enzyme", "enzyme_conservation_residual"):
        assert all(float(row["value"]) == 0. for row in rows if row["state_role"] == role)
    records = list((tmp_path / "run").rglob("record.json"))
    assert records
    def reject_nonstandard_constant(value):
        raise AssertionError(f"Nonstandard JSON constant: {value}")
    for record in records:
        saved = json.loads(record.read_text(), parse_constant=reject_nonstandard_constant)
        fractions = [quantity for name, quantity in saved["derived_quantities"].items() if name.endswith(".bound_fraction")]
        assert len(fractions) == 1 and fractions[0]["value"] == [None] * 25
    metric_paths = list((tmp_path / "run").rglob("mechanism_metrics.csv"))
    assert metric_paths
    for metric_path in metric_paths:
        with metric_path.open() as handle:
            endpoints = [row for row in csv.DictReader(handle) if row["metric_name"].endswith("bound_fraction")]
        assert len(endpoints) == 2
        assert all(row["value"] == "" and row["status"] == "unknown" for row in endpoints)
