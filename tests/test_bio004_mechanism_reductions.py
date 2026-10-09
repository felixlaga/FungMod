"""Unit-aware finite-run reporting, counterfactual guards and user-table forwarding."""
from __future__ import annotations

import csv
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from fungal_model.api.mechanism_reductions import trajectory_metrics
from fungal_model.core.units import Q_, UnitError
from fungal_model.io.model_config import load_model_config
from fungal_model.workflows import run_configured_model
from fungal_model.workflows.mechanism_metrics import summarize_mechanisms

ROOT = Path(__file__).resolve().parents[1]


def _peroxide():
    config = load_model_config(ROOT / "data/model_configs/toy_peroxide_oxidation.yml")
    config = replace(config, raw={**config.raw, "metric_definitions": {
        "peroxide_ledgers": {"H": {"feed": "feed", "decay": "H_decay"}}
    }})
    # Deliberately nonzero initial ledgers and three amount scales; these are hypothetical reporting inputs.
    result = SimpleNamespace(time=Q_([0, 2], "hour"), derived_quantities={}, states={
        "S": Q_([10, 8], "mM"), "P": Q_([2, 10], "uM"), "E": Q_([2000, 500], "nM"),
        "H": Q_([.3, .1], "mM"), "cuts": Q_([1, 5], "uM"),
        "feed": Q_([20, 80], "uM"), "H_decay": Q_([.01, .04], "mM"),
    })
    return config, result


def _metrics(config, result):
    return {row["metric_name"]: row for row in trajectory_metrics(config, result)}


def test_turnover_remaining_activity_and_exchange_convert_units_and_subtract_initial_ledgers():
    config, result = _peroxide()
    metrics = _metrics(config, result)
    expected = {"finite_run_turnover": 2, "remaining_active_fraction": .25,
                "productive_peroxide_consumed": .004, "peroxide_fed": .06,
                "peroxide_decayed": .03, "total_modeled_peroxide_consumed": .034,
                "final_oxidative_cuts": 5, "final_oxidized_product": 10}
    for name, value in expected.items():
        assert metrics["oxidation." + name]["value"] == pytest.approx(value)
    assert metrics["oxidation.finite_run_turnover"]["units"] == "dimensionless"
    assert metrics["oxidation.peroxide_fed"]["units"] == "millimolar"
    assert "not asymptotic" in metrics["oxidation.finite_run_turnover"]["notes"]


def test_zero_enzyme_unknown_exchange_and_explicit_null_are_distinct():
    config, result = _peroxide()
    result.states["E"] = Q_([0, 0], "nM")
    config = replace(config, raw={**config.raw, "metric_definitions": {"peroxide_ledgers": {"H": {"feed": None}}}})
    metrics = _metrics(config, result)
    for name in ("finite_run_turnover", "remaining_active_fraction", "peroxide_decayed", "total_modeled_peroxide_consumed"):
        assert metrics["oxidation." + name]["status"] == "unknown"
        assert metrics["oxidation." + name]["value"] == ""
    assert metrics["oxidation.peroxide_fed"]["value"] == 0
    assert "boundary" in metrics["oxidation.peroxide_fed"]["notes"]


def test_invalid_ledger_units_and_nonfinite_trajectories_are_refused():
    config, result = _peroxide()
    result.states["feed"] = Q_([0, 1], "g/L")
    with pytest.raises(UnitError):
        _metrics(config, result)
    result.states["feed"] = Q_([0, float("nan")], "mM")
    with pytest.raises(ValueError, match="finite"):
        _metrics(config, result)


def _chains():
    config = load_model_config(ROOT / "data/model_configs/toy_chain_scission.yml")
    chains = {int(i): name for i, name in config.processes[0].states["chains"].items()}
    states = {name: Q_([0, .5 if i == 4 else 1 if i == 2 else 0], "mM").to("uM" if i % 2 == 0 else "mM")
              for i, name in chains.items()}
    return config, SimpleNamespace(time=Q_([0, 1], "s"), states=states, derived_quantities={})


def test_chain_populations_are_deduplicated_with_unit_aware_final_observables():
    config, result = _chains()
    metrics = _metrics(config, result)
    assert len(metrics) == 5  # All endo/exo channels share one structural population.
    for name, value in {"chain_ends": .5, "solid_equivalents": 2, "soluble_equivalents": 2, "material_equivalents": 4}.items():
        row = metrics["chain_population_1.final_" + name]
        assert Q_(row["value"], row["units"]).to("mM").magnitude == pytest.approx(value)
    assert metrics["chain_population_1.degree_of_synergy"]["status"] == "unknown"


def test_supplied_counterfactual_requires_matching_conditions_and_singletons():
    config, result = _chains()
    comparison = {"source": "Synthetic matched counterfactual test", "matched_conditions": True,
                  "full_increment": {"value": 9, "units": "mM"},
                  "individual_increments": [{"value": 1000, "units": "uM"}, {"value": 2, "units": "mM"}]}
    config = replace(config, raw={**config.raw, "metric_definitions": {"synergy_comparisons": {"chain_population_1": comparison}}})
    assert _metrics(config, result)["chain_population_1.degree_of_synergy"]["value"] == 3
    comparison["individual_increments"] = [{"value": 0, "units": "mM"}]
    assert _metrics(config, result)["chain_population_1.degree_of_synergy"]["status"] == "unknown"
    comparison["matched_conditions"] = False
    with pytest.raises(ValueError, match="matched_conditions"):
        _metrics(config, result)


@pytest.mark.parametrize("filename,required", [
    ("toy_adsorbed_enzyme_hydrolysis.yml", {"initial_bound_fraction", "final_bound_fraction", "max_absolute_enzyme_conservation_residual"}),
    ("toy_chain_scission.yml", {"final_chain_ends", "final_solid_equivalents", "final_soluble_equivalents"}),
    ("toy_peroxide_oxidation.yml", {"finite_run_turnover", "remaining_active_fraction", "peroxide_fed", "peroxide_decayed"}),
])
def test_configured_runs_write_expected_finite_run_metric_artifacts(tmp_path, filename, required):
    config = load_model_config(ROOT / "data/model_configs" / filename)
    result = run_configured_model(config.path, output_dir=tmp_path)
    saved = json.loads((tmp_path / "mechanism_metrics.json").read_text())
    assert saved == summarize_mechanisms(config, result)
    assert required <= {row["metric_name"].split(".", 1)[1] for row in saved}
    with (tmp_path / "mechanism_metrics.csv").open() as stream:
        assert len(list(csv.DictReader(stream))) == len(saved)
    if "adsorbed" in filename:
        for row in saved:
            if row["metric_name"].endswith("bound_fraction"):
                assert 0 <= row["value"] <= 1
            elif row["metric_name"].endswith("residual"):
                assert row["value"] < 1e-12


def test_mechanism_sample_reader_preserves_absence_and_refuses_wrong_schema(tmp_path):
    from fungal_model.api.result_tables import _read_mechanism_metrics
    sample = SimpleNamespace(output_directory=tmp_path)
    assert _read_mechanism_metrics(sample) == []
    (tmp_path / "mechanism_metrics.json").write_text('{}')
    with pytest.raises(ValueError, match="schema"):
        _read_mechanism_metrics(sample)


def test_user_table_and_summary_receive_adsorption_metrics_without_duplicates(tmp_path):
    from fungal_model import load_user_dataset, virtual_experiment
    from tests.test_bio004_adsorption import _user_dataset
    dataset = load_user_dataset(_user_dataset(tmp_path / "data"))
    study = virtual_experiment(fungi="strain", substrates="solid", environments="assay", user_data=dataset)
    run = study.simulate(mode="exploratory", n_samples=1, seed=7, output_dir=tmp_path / "run", quicklook=False)
    with Path(run.tables.paths["final_metrics"]).open() as stream:
        final = list(csv.DictReader(stream))
    with Path(run.tables.paths["summary_metrics"]).open() as stream:
        summary = list(csv.DictReader(stream))
    for suffix in ("initial_bound_fraction", "final_bound_fraction", "max_absolute_enzyme_conservation_residual"):
        assert len([r for r in final if r["metric"].endswith(suffix)]) == 1
        assert len([r for r in summary if r["metric"].endswith(suffix)]) == 1
    assert len({row["metric"] for row in final}) == len(final)


def test_existing_culture_metrics_are_not_duplicated_when_configured_rows_are_forwarded(tmp_path):
    from tests.test_bio004_uptake_oxygen import _dataset, _run
    run, _ = _run(_dataset(tmp_path / "data", oxygen=True))
    with Path(run.tables.paths["final_metrics"]).open() as stream:
        rows = list(csv.DictReader(stream))
    for name in ("minimum_dissolved_oxygen", "time_below_oxygen_threshold", "final_biomass", "peak_soluble_sugar"):
        assert len([r for r in rows if r["metric"] == name]) == 1
    assert len({row["metric"] for row in rows}) == len(rows)


def test_adsorption_zero_total_fraction_is_unknown_without_json_nan():
    config = load_model_config(ROOT / "data/model_configs/toy_adsorbed_enzyme_hydrolysis.yml")
    process = config.processes[0]
    result = SimpleNamespace(time=Q_([0, 1], "s"), states={process.states["enzyme"]: Q_([0, 2], "mg/L")},
        derived_quantities={process.id + ".bound_fraction": Q_([np.nan, .25], "dimensionless"),
                            process.id + ".enzyme_conservation_residual": Q_([0, 0], "ug/L")})
    rows = trajectory_metrics(config, result)
    metrics = {r["metric_name"]: r for r in rows}
    assert metrics[process.id + ".initial_bound_fraction"]["status"] == "unknown"
    assert metrics[process.id + ".initial_bound_fraction"]["value"] == ""
    assert metrics[process.id + ".final_bound_fraction"]["value"] == .25
    json.dumps(rows, allow_nan=False)
