from copy import deepcopy
import importlib.util
from pathlib import Path
import shutil

import numpy as np
import pytest

from fungal_model.core.provenance import ProvenanceError
from fungal_model.core.units import Q_
from fungal_model.research.respiration_benchmark import fit_pirt, lameiras_glucose_model, load_respiration_data

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/benchmarks/lameiras_respiration"
SPEC = importlib.util.spec_from_file_location("respiration_extract", ROOT / "scripts/prepare_respiration_data.py")
assert SPEC and SPEC.loader
extractor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extractor)
RUNNER_SPEC = importlib.util.spec_from_file_location("respiration_runner", ROOT / "scripts/run_respiration_benchmark.py")
assert RUNNER_SPEC and RUNNER_SPEC.loader
runner = importlib.util.module_from_spec(RUNNER_SPEC)
RUNNER_SPEC.loader.exec_module(runner)


def test_source_extract_reproduces_byte_for_byte_and_retains_data_roles():
    extractor.prepare(DATA, check=True)
    data = load_respiration_data()
    records = data["lameiras_2015"]["records"]
    assert len(records) == 4
    assert records[0]["unreconciled"]["substrate_uptake"]["value"] == .014
    assert records[-1]["unreconciled"]["oxygen_uptake"]["value"] == .1065
    assert records[-1]["reconciled"]["oxygen_uptake"]["value"] == pytest.approx(.0964)
    assert "not independent validation" in data["lameiras_2017"]["role"]
    assert len(data["lameiras_2017"]["single_substrate_batch"]) == 6
    mixed = data["lameiras_2017"]["mixed_substrate_chemostat"]
    assert len(mixed) == 11
    assert len([r for r in mixed if r["quality_flags"]]) == 1
    assert mixed[7]["reconciled"]["carbon_dioxide_release"]["verbatim"] == "3.7 ± 3.9"
    assert mixed[7]["reconciled"]["unresolved_organic_carbon_release"]["verbatim"] == "1.2 ± 1.9"


def test_source_and_extract_tampering_fail_closed(tmp_path):
    directory = tmp_path / "data/benchmarks/lameiras_respiration"
    shutil.copytree(DATA, directory)
    for name in ("observations.json", "PMC4559092.xml"):
        original = (directory / name).read_bytes()
        (directory / name).write_bytes(original + b" ")
        with pytest.raises(ValueError, match="checksum mismatch"):
            load_respiration_data(tmp_path)
        (directory / name).write_bytes(original)


def test_pirt_recovers_artificial_parameters_and_zero_maintenance_boundary():
    mu = np.array([.02, .1, .2, .3])
    args = dict(growth_rates=Q_(mu, "1/h"), condition_ids=["a", "b", "c", "d"], source="Artificial verification only.")
    fit = fit_pirt(**args, substrate_uptake=Q_(mu / 3 + .002, "1/h"), include_maintenance=True)
    assert fit.true_yield.value == pytest.approx(3)
    assert fit.maintenance_demand.value == pytest.approx(.002)
    np.testing.assert_allclose(fit.predict(Q_(mu / 3600, "1/s")), mu / 3 + .002)
    zero = fit_pirt(**args, substrate_uptake=Q_(mu / 3, "1/h"), include_maintenance=True)
    assert zero.maintenance_demand.value == pytest.approx(0, abs=1e-15)
    baseline = fit_pirt(**args, substrate_uptake=Q_(mu / 3, "1/h"), include_maintenance=False)
    assert baseline.to_dict()["fitted_parameter_count"] == 1
    assert baseline.maintenance_demand.value == 0


def test_real_holdout_parameters_do_not_depend_on_held_out_values():
    records = load_respiration_data()["lameiras_2015"]["records"]

    def training_fit(rows):
        return fit_pirt(growth_rates=Q_([r["dilution_per_h"] for r in rows[:3]], "1/h"),
                        substrate_uptake=Q_([r["unreconciled"]["substrate_uptake"]["value"] for r in rows[:3]], "1/h"),
                        condition_ids=[r["id"] for r in rows[:3]], source="Lameiras 2015 Table 2 unreconciled", include_maintenance=True)
    before = training_fit(records)
    changed = deepcopy(records)
    changed[-1]["unreconciled"]["substrate_uptake"]["value"] = 999
    after = training_fit(changed)
    assert before.to_dict() == after.to_dict()
    assert records[-1]["id"] not in before.training_conditions
    model = lameiras_glucose_model(before, load_respiration_data())
    assert model.growth_reaction.coefficients["ammonium"] == pytest.approx(-.12)
    assert model.growth_reaction.coefficients["proton"] == pytest.approx(.12)


def test_holdout_runner_never_fits_gas_or_reconciled_data():
    data = load_respiration_data()
    original, metrics = runner.holdouts(data)
    changed = deepcopy(data)
    for row in changed["lameiras_2015"]["records"]:
        row["unreconciled"]["oxygen_uptake"]["value"] += 999
        row["unreconciled"]["carbon_dioxide_release"]["value"] += 999
        row["reconciled"]["substrate_uptake"]["value"] += 999
    alternative, _ = runner.holdouts(changed)
    assert [p["prediction"] for p in alternative] == [p["prediction"] for p in original]
    assert len(original) == 8
    assert all(p["condition"] not in p["fit"]["training_conditions"] for p in original)
    assert metrics["growth_maintenance"]["substrate_uptake"] == pytest.approx(.00038602054195323505)
    assert metrics["growth_only"]["substrate_uptake"] == pytest.approx(.0015557401731256726)


def test_error_corner_sensitivity_retains_zero_maintenance_and_flags_inadmissible_yields():
    result = runner.sensitivity(load_respiration_data())
    assert result["scenario_count"] == 256
    assert result["zero_maintenance_scenarios"] > 0
    assert result["maintenance_range_per_h"][0] == 0
    assert result["incompatible_with_aerobic_no_carbon_fixation_scenarios"] > 0
    assert result["aerobic_true_yield_range"][1] < result["true_yield_range"][1]
    assert "NOT a statistical confidence interval" in result["interpretation"]


def test_runner_preserves_existing_evidence(tmp_path):
    (tmp_path / "evidence.json").write_text("preserve")
    with pytest.raises(ValueError, match="empty"):
        runner.run(ROOT, tmp_path)
    assert (tmp_path / "evidence.json").read_text() == "preserve"


@pytest.mark.parametrize("changes,error", [
    ({"source": ""}, ProvenanceError), ({"condition_ids": ["a", "a", "b"]}, ValueError),
    ({"condition_ids": ["a", "b"]}, ValueError), ({"growth_rates": Q_([.1, .1, .1], "1/h")}, ValueError),
    ({"growth_rates": Q_([.1, -.1, .2], "1/h")}, ValueError),
    ({"substrate_uptake": Q_([0, 0, 0], "1/h")}, ValueError),
    ({"substrate_uptake": Q_([.1, float("nan"), .2], "1/h")}, ValueError),
])
def test_invalid_calibration_data_fail_closed(changes, error):
    args = dict(growth_rates=Q_([.1, .2, .3], "1/h"), substrate_uptake=Q_([.03, .06, .09], "1/h"),
                condition_ids=["a", "b", "c"], source="Artificial", include_maintenance=True)
    with pytest.raises(error):
        fit_pirt(**dict(args, **changes))
