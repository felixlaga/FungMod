"""Held-out Gelain 2020 cellulose loadings: digitized data, registry conditions and frozen predictions.

These tests pin the contract of the held-out study: the digitizer reproduces
its committed files and refuses to write unless it reproduces the deposited
training means; the two held-out registry conditions are exact and modelable
in scientific mode without touching the calibrated constants; a virtual loading
is the registry condition rebuilt with only its loading overridden; and the
frozen held-out scores keep their recorded values and ranking.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from fungal_model.registry import load_registry
from fungal_model.research import gelain_heldout as gh
from fungal_model.screening import assess_modelability

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / gh.HELDOUT_DIR
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
DIGITIZER = ROOT / "scripts" / "digitize_gelain_2020_figures_2_3.py"


def _digitizer():
    spec = importlib.util.spec_from_file_location("digitize_gelain_2020_figures_2_3", DIGITIZER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def registry():
    return load_registry(REGISTRY_INDEX)


@pytest.fixture(scope="module")
def predictor(registry):
    return gh.FrozenPredictor(ROOT, registry)


def test_digitizer_reproduces_the_committed_files_and_passes_its_calibration_check() -> None:
    digitizer = _digitizer()
    assert digitizer.main(["--check", "--output-dir", str(DATASET)]) == 0
    recorded = json.loads((DATASET / "digitization_calibration.json").read_text(encoding="utf-8"))
    check = recorded["calibration_check"]
    assert check["passed"] is True
    assert check["median_error_fraction_of_span"] <= check["tolerance_median_fraction"]
    assert check["max_error_fraction_of_span"] <= check["tolerance_max_fraction"]
    assert check["censored_points_consistent"] == check["censored_zero_line_points"]
    assert check["uncensored_points"] >= 80
    assert len(check["deposited_points_not_found"]) <= digitizer.MAXIMUM_UNFOUND_REFERENCE_POINTS
    assert recorded["article_sha256"] == digitizer.ARTICLE_SHA256
    for axes in recorded["axes"].values():
        for name in ("x", "y_left", "y_right"):
            if axes[name] is not None:
                assert axes[name]["max_residual_pixels"] <= 1.0


def test_calibration_check_rejects_a_shifted_digitization() -> None:
    digitizer = _digitizer()
    frames, points = digitizer.digitize(digitizer.load_figures())
    shifted = [
        digitizer.Point(**{**point.__dict__, "mean": point.mean * 1.05 + 0.5}) if point.censored_upper_limit is None else point
        for point in points
    ]
    assert digitizer.calibration_check(shifted, frames)["passed"] is False


def test_held_out_dataset_holds_two_loadings_with_explicit_censoring_and_uncertainty() -> None:
    observations = gh.load_digitized(ROOT)
    assert len(observations) == 62
    assert {o.condition_g_l for o in observations} == set(gh.HELDOUT_LOADINGS)
    keys = [(o.condition_g_l, o.observable, o.time_h) for o in observations]
    assert len(keys) == len(set(keys))
    assert all(o.time_h in gh.SAMPLING_TIMES_H for o in observations)
    censored = [o for o in observations if o.censored]
    assert censored and all(o.mean == 0.0 and (o.censored_upper_limit or 0.0) > 0.0 for o in censored)
    measured = [o for o in observations if o.sd is not None]
    assert len(measured) == 41 and all(o.sd is not None and o.sd > 0.0 for o in measured)
    assert all(o.scoring_sd > 0.0 for o in observations)
    with (DATASET / "gelain_2020_figure_3_heldout.csv").open(encoding="utf-8") as handle:
        assert {row["figure"] for row in csv.DictReader(handle)} == {"figure_3"}


@pytest.mark.parametrize("loading", gh.HELDOUT_LOADINGS)
def test_held_out_conditions_are_exact_registry_records_modelable_in_scientific_mode(registry, loading: float) -> None:
    environment_id = gh.ENVIRONMENTS[loading]
    environment = registry.get_environment(environment_id)
    assert environment.conditions["initial_cellulose_loading"].value == loading
    assert "not included in parameter estimation" in environment.provenance["source"]
    assert "held_out_from" in environment.provenance
    (record,) = [
        r for r in registry.get_parameter_records(parameter_symbol=gh.INITIAL_LOADING_SYMBOL) if r.environment_id == environment_id
    ]
    assert record.value.is_exact and record.value.value == loading
    report = assess_modelability(
        fungus_id=gh.FUNGUS_ID, substrate_id=gh.SUBSTRATE_ID, environment_id=environment_id, registry=registry, mode="scientific"
    )
    assert report.status == "modelable", report.to_dict()


def test_calibrated_constants_stay_shared_across_every_condition(registry) -> None:
    for symbol in gh.FrozenPredictor(ROOT, registry).registry_symbols:
        (record,) = registry.get_parameter_records(parameter_symbol=symbol)
        assert record.environment_id is None and record.maturity == "calibrated"


def test_a_virtual_loading_is_the_registry_condition_with_only_its_loading_overridden(predictor) -> None:
    registry_20 = predictor.predict("registry_M0", 20.0, gh.SAMPLING_TIMES_H)
    rebuilt = predictor._predictor("registry_M0", gh.VIRTUAL_BASE_ENVIRONMENT).predict_values(  # noqa: SLF001
        {**predictor.registry_defaults(), gh.INITIAL_LOADING_SYMBOL: 20.0}, gh.VIRTUAL_BASE_ENVIRONMENT, np.array(gh.SAMPLING_TIMES_H)
    )
    np.testing.assert_allclose(rebuilt, registry_20, rtol=1e-9, atol=1e-9)
    assert predictor.environment_for(17.5) == (gh.VIRTUAL_BASE_ENVIRONMENT, True)
    assert predictor.environment_for(40.0) == (gh.ENVIRONMENTS[40.0], False)
    virtual = predictor.predict("registry_M0", 17.5, gh.SAMPLING_TIMES_H)
    assert virtual[0, 1] < 17.5 and np.all(np.isfinite(virtual))


def test_only_the_registry_case_takes_posterior_draws(predictor) -> None:
    with pytest.raises(Exception, match="Only the registry case"):
        predictor.predict("M2_soluble_product_pool", 20.0, gh.SAMPLING_TIMES_H, values={"gelain_hydrolysis_Y": 0.5})
    with pytest.raises(Exception, match="published parameters only"):
        predictor.predict("gelain_published", 20.0, gh.SAMPLING_TIMES_H, values={"mu": 0.1})


def test_scoring_is_zero_for_a_perfect_prediction_and_checks_censored_limits() -> None:
    observations = gh.load_digitized(ROOT)
    scales = gh.training_scales(ROOT)

    def perfect(loading: float) -> np.ndarray:
        table = np.zeros((len(gh.SAMPLING_TIMES_H), 4))
        for o in observations:
            if o.condition_g_l == loading:
                table[gh.SAMPLING_TIMES_H.index(o.time_h), gh.OBSERVABLES.index(o.observable)] = o.mean
        return table

    score = gh.score_model(perfect, observations, scales)
    assert score["mean_normalized_mse"] == 0.0
    assert all(cell["censored_consistent"] == cell["censored_points"] for cell in score["cells"].values())
    overshoot = gh.score_model(lambda loading: perfect(loading) + 1.0e4, observations, scales)
    assert all(cell["censored_consistent"] == 0 for cell in overshoot["cells"].values())


def test_threshold_time_and_apparent_yield_follow_their_definitions() -> None:
    times = [0.0, 10.0, 20.0, 30.0]
    assert gh.threshold_time(times, [10.0, 8.0, 4.0, 0.0], 10.0, 0.5) == pytest.approx(17.5)
    assert gh.threshold_time(times, [10.0, 9.0, 8.0, 7.0], 10.0, 0.5) is None
    summary = gh.apparent_yield(times, [1.0, 3.0, 5.0, 4.0], [10.0, 8.0, 4.0, 1.0], 1.0, 10.0)
    assert summary["time_of_peak_h"] == 20.0 and summary["apparent_yield"] == pytest.approx(4.0 / 6.0)


def test_frozen_held_out_scores_and_ranking(predictor) -> None:
    """Recorded 2026-10-09: the first scoring of the held-out loadings with every model frozen."""

    observations = gh.load_digitized(ROOT)
    scales = gh.training_scales(ROOT)
    recorded = {
        "gelain_published": 0.0215,
        "M2_soluble_product_pool": 0.1282,
        "registry_M0": 0.1534,
        "M1_induction_state": 0.1578,
        "M3_conversion_dependent_accessibility": 0.1584,
    }
    scores = {
        model: gh.score_model(lambda loading, model=model: predictor.predict(model, loading, gh.SAMPLING_TIMES_H), observations, scales)[
            "mean_normalized_mse"
        ]
        for model in gh.MODEL_IDS
    }
    for model, value in recorded.items():
        assert scores[model] == pytest.approx(value, abs=5e-4), model
    assert sorted(scores, key=lambda model: scores[model])[:3] == ["gelain_published", "M2_soluble_product_pool", "registry_M0"]
