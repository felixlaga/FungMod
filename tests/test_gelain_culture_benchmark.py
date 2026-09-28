"""Numerical/software evidence only; artificial cases never count as biology."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from fungal_model.core.units import Q_, UnitError
from fungal_model.research import gelain_culture as culture

ROOT = Path(__file__).resolve().parents[1]
PLAN = json.loads((ROOT / "data/benchmarks/gelain_2020/plan.json").read_text())
SPEC = importlib.util.spec_from_file_location("culture_runner", ROOT / "scripts/run_gelain_2020_culture_benchmark.py")
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def design(**changes):
    return culture.CultureDesign(**(dict(condition_id="artificial_math_test", family="glycerol",
        times=Q_(np.linspace(0, 48, 97), "hour"), initial_biomass=Q_(0.5, "gram/liter"),
        initial_substrate=Q_(10, "gram/liter"), source="Artificial mathematical test, not experimental") | changes))


def parameters(**changes):
    values = dict(mu=0.1, K=2.0, Y=0.5, kd=0.01) | changes
    return culture.parameters_from_records([
        dict(symbol=k, value=v, units=culture.REDUCED_UNITS[k], source="Artificial mathematical test")
        for k, v in values.items()])


def simulate(case=None, params=None, **options):
    return culture.simulate_culture(case or design(), params or parameters(), model="effective_monod_loss_v1",
                                   hypothesis_source="Artificial test only", **options)


def test_effective_model_conserves_apparent_yield_without_loss_and_converts_units():
    case, params = design(), parameters(kd=0)
    result = simulate(case, params)
    np.testing.assert_allclose(result.substrate.magnitude + result.biomass.magnitude / 0.5, 11, atol=1e-8)
    converted = replace(case, times=case.times.to("second"), initial_biomass=case.initial_biomass.to("kg/m^3"),
                        initial_substrate=case.initial_substrate.to("milligram/liter"))
    converted_params = culture.parameters_from_records([
        dict(symbol=p.symbol, value=p.quantity.to("1/minute").magnitude, units="1/minute", source=p.source)
        if p.symbol in {"mu", "kd"} else p.to_dict() for p in params])
    np.testing.assert_allclose(simulate(converted, converted_params).observations_g_l, result.observations_g_l,
                               rtol=1e-8, atol=1e-8)
    assert result.induced_proxy is None
    assert result.maturity == "exploratory_software_tested"


def test_zero_growth_has_analytical_biomass_loss_and_no_substrate_consumption():
    result = simulate(params=parameters(mu=0))
    np.testing.assert_allclose(result.biomass.magnitude, 0.5 * np.exp(-0.01 * result.time.magnitude), rtol=1e-7)
    np.testing.assert_allclose(result.substrate.magnitude, 10)
    zero_substrate = simulate(design(initial_substrate=Q_(0, "gram/liter")))
    np.testing.assert_allclose(zero_substrate.biomass.magnitude, result.biomass.magnitude, rtol=1e-8)


@pytest.mark.parametrize("changes", [dict(times=Q_([1, 0], "hour")), dict(times=Q_([0], "hour")),
    dict(times=Q_([0, np.nan], "hour")), dict(initial_biomass=Q_(-1, "gram/liter")),
    dict(initial_substrate=Q_(np.inf, "gram/liter")), dict(source=""), dict(family="unreviewed_species")])
def test_invalid_designs_fail(changes):
    with pytest.raises(culture.CultureBenchmarkError):
        design(**changes)


def test_explicit_units_and_parameter_provenance_are_required():
    with pytest.raises(UnitError):
        design(initial_biomass=1)
    with pytest.raises(UnitError):
        design(initial_biomass=Q_(1, "mole/liter"))
    bad = culture.parameters_from_records([dict(p.to_dict(), source=None) for p in parameters()])
    with pytest.raises(ValueError, match="missing a source"):
        simulate(params=bad)
    unknown = culture.parameters_from_records([dict(p.to_dict(), value=None) for p in parameters()])
    with pytest.raises(ValueError, match="explicitly unknown"):
        simulate(params=unknown)
    with pytest.raises(culture.CultureBenchmarkError, match="yield"):
        simulate(params=parameters(Y=2))


@pytest.mark.parametrize("override", [dict(method="invalid"), dict(rtol=0), dict(atol=Q_(0, "gram/liter"))])
def test_invalid_solver_configuration_fails(override):
    with pytest.raises(culture.CultureBenchmarkError):
        simulate(**override)


@pytest.mark.parametrize("success,values", [(False, np.ones((2, 97))), (True, np.ones((2, 2))),
    (True, np.full((2, 97), np.nan)), (True, np.full((2, 97), -1.0))])
def test_failed_incomplete_nonfinite_or_negative_solutions_fail_closed(monkeypatch, success, values):
    monkeypatch.setattr(culture, "solve_ivp", lambda *a, **k: SimpleNamespace(success=success, y=values,
        message="deliberate solver fault", nfev=0))
    with pytest.raises(culture.CultureBenchmarkError):
        simulate()


def test_deposited_source_projection_reproduces_all_six_reference_simulations():
    source = json.loads((ROOT / "data/benchmarks/gelain_2020/source_parameters.json").read_text())
    results = runner.source_parity(ROOT, PLAN, source)
    assert len(results) == 6 and all(r["passed"] for r in results)
    discrepant = next(r for r in results if r["family"] == "glycerol" and r["initial_substrate_g_l"] == 20)
    assert discrepant["paper_vs_deposited_max_biomass_difference_g_l"] > 0.8
    assert all(r["role"] == "software_parity_only" for r in results)


def test_loaded_observation_mapping_retains_unknowns_and_source_initial_values():
    conditions = culture.load_culture_conditions(ROOT)
    assert len(conditions) == 6
    assert all(c.values.shape == (8, 2) for c in conditions)
    assert all(c.design.times.magnitude[0] == 8 for c in conditions)
    assert conditions[3].design.initial_biomass.magnitude == pytest.approx(0.3990672957214788)
    assert not hasattr(conditions[0].design, "values")
    with pytest.raises(culture.CultureBenchmarkError):
        culture.CultureObservations(conditions[0].design, Q_(np.ones((7, 2)), "gram/liter"))


def test_fit_recovers_an_artificial_curve_and_is_deterministic():
    case = design(times=Q_(np.linspace(1, 60, 16), "hour"))
    truth = simulate(case)
    observations = culture.CultureObservations(case, Q_(truth.observations_g_l, "gram/liter"))
    plan = dict(PLAN, starts=1)
    # An explicit artificial starting box for this numerical recovery test only.
    plan["parameters"] = [dict(r, lower=v / 2, upper=v * 2)
                          for r, v in zip(PLAN["parameters"], [0.1, 2, 0.5, 0.01], strict=True)]
    a = culture.fit_effective_culture([observations], plan, weighting="training_max")
    b = culture.fit_effective_culture([observations], plan, weighting="training_max")
    assert a == b
    np.testing.assert_allclose([r["value"] for r in a["parameters"]], [0.1, 2, 0.5, 0.01], rtol=1e-5)
    assert a["uncertainty"] is None
    assert a["normalization_is_measurement_uncertainty"] is False


def test_all_start_failure_is_not_reported_as_a_fit(monkeypatch):
    def fail(*args, **kwargs):
        raise culture.CultureBenchmarkError("deliberate integration failure")
    monkeypatch.setattr(culture, "simulate_culture", fail)
    with pytest.raises(culture.CultureBenchmarkError, match="All optimization starts failed"):
        culture.fit_effective_culture(culture.load_culture_conditions(ROOT)[:2], PLAN, weighting="training_max")


def test_training_contract_rejects_mixed_groups_and_bad_normalization():
    conditions = culture.load_culture_conditions(ROOT)
    with pytest.raises(culture.CultureBenchmarkError, match="one substrate"):
        culture.fit_effective_culture([conditions[0], conditions[3]], PLAN, weighting="training_max")
    with pytest.raises(culture.CultureBenchmarkError, match="unique"):
        culture.fit_effective_culture([conditions[0], conditions[0]], PLAN, weighting="training_max")
    zero = replace(conditions[0], values=Q_(np.zeros((8, 2)), "gram/liter"))
    with pytest.raises(culture.CultureBenchmarkError, match="normalization"):
        culture.fit_effective_culture([zero], PLAN, weighting="training_max")
    with pytest.raises(culture.CultureBenchmarkError, match="Unknown weighting"):
        culture.fit_effective_culture([conditions[0]], PLAN, weighting="invented_sd")


def test_descriptive_score_units_shape_and_scale_validation():
    score = culture.score_predictions(np.array([[1, 3], [1, 3]]), Q_([[0, 1000], [0, 1000]], "milligram/liter"), [1, 2])
    assert score["rmse_g_l"] == [1, 2]
    assert score["normalized_rmse"] == 1
    assert score["error_model"] is None
    with pytest.raises(culture.CultureBenchmarkError):
        culture.score_predictions(np.ones((2, 2)), Q_(np.ones((2, 2)), "gram/liter"), [0, 1])
    with pytest.raises(culture.CultureBenchmarkError):
        culture.score_predictions(np.full((2, 2), np.nan), Q_(np.ones((2, 2)), "gram/liter"), [1, 1])


def test_runner_freezes_before_scoring_and_heldout_response_cannot_change_its_fit(monkeypatch, tmp_path):
    real_score = runner.score_predictions
    active_output = tmp_path / "first"
    calls = []

    def checked_score(*args, **kwargs):
        assert list((active_output / "frozen_predictions").glob("*.json"))
        return real_score(*args, **kwargs)

    def quick_fit(training, plan, *, weighting):
        # This stub tests orchestration isolation, not parameter estimation.
        calls.append([c.design.condition_id for c in training])
        scales = np.max(np.concatenate([c.values.magnitude for c in training]), axis=0)
        return {"parameters": [dict(symbol=p.symbol, value=p.value, units=p.units) for p in parameters()],
                "parameter_source": "Artificial orchestration test", "normalization_g_l": scales.tolist(),
                "training_conditions": calls[-1], "weighting": weighting}

    monkeypatch.setattr(runner, "score_predictions", checked_score)
    monkeypatch.setattr(runner, "fit_effective_culture", quick_fit)
    first = runner.run(ROOT, active_output)
    assert len(calls) == 14
    assert all(len(ids) == (3 if i in {6, 13} else 2) for i, ids in enumerate(calls))
    original = culture.load_culture_conditions(ROOT)
    modified = [replace(original[0], values=original[0].values * 10)] + original[1:]
    monkeypatch.setattr(runner, "load_culture_conditions", lambda root: modified)
    active_output = tmp_path / "second"
    second = runner.run(ROOT, active_output)
    a, b = first["folds"][0], second["folds"][0]
    assert a["fit"] == b["fit"]
    assert a["heldout_score"] != b["heldout_score"]
    assert a["frozen_prediction_sha256"] == b["frozen_prediction_sha256"]
    assert first["biological_validation"] is False
    for fold in second["folds"]:
        assert fold["condition"] not in fold["fit"]["training_conditions"]
        frozen = active_output / fold["frozen_prediction_file"]
        assert hashlib.sha256(frozen.read_bytes()).hexdigest() == fold["frozen_prediction_sha256"]
        assert "observed_g_l" not in frozen.read_text()
    artifacts = json.loads((active_output / "artifacts.json").read_text())
    assert all(runner.digest(active_output / path) == expected for path, expected in artifacts.items())
    with pytest.raises(culture.CultureBenchmarkError, match="empty"):
        runner.run(ROOT, active_output)


def test_recorded_empirical_result_integrity_and_scores_recompute():
    """Check frozen artifacts without expensive refits or biological pass claims."""
    output = ROOT / "data/benchmarks/gelain_2020/results"
    report = json.loads((output / "report.json").read_text())
    plan = json.loads((output / "plan.json").read_text())
    artifacts = json.loads((output / "artifacts.json").read_text())
    assert all(runner.digest(output / path) == expected for path, expected in artifacts.items())
    conditions = {c.design.condition_id: c for c in culture.load_culture_conditions(ROOT)}
    assert report["measurement_uncertainty"] is None and report["biological_validation"] is False
    assert len(report["folds"]) == 12 and len(report["full_data_fits"]) == 2
    for fold in report["folds"]:
        path = output / fold["frozen_prediction_file"]
        assert runner.digest(path) == fold["frozen_prediction_sha256"]
        frozen = json.loads(path.read_text())
        condition = conditions[fold["condition"]]
        predicted = culture.predict_effective_culture(condition.design, fold["fit"], plan).observations_g_l
        np.testing.assert_allclose(predicted, frozen["predicted_biomass_substrate_g_l"], atol=1e-6, rtol=1e-6)
        score = culture.score_predictions(predicted, condition.values, fold["fit"]["normalization_g_l"])
        np.testing.assert_allclose(score["rmse_g_l"], fold["heldout_score"]["rmse_g_l"], atol=1e-6, rtol=1e-6)
        assert fold["condition"] not in fold["fit"]["training_conditions"]
    text = (ROOT / "docs/gelain-culture-benchmark.md").read_text()
    assert "not independent" in text
    assert "**not SD estimates**" in text
    assert "5/40 g/L cellulose assays were tried during estimation" in text
